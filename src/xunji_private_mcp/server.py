import argparse
import os
from contextlib import contextmanager
from typing import Any

from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from . import body, food, templates, training
from .credentials import BindHttpCredentials, REQUEST_KEYS, load_stdio_keys
from .upstream import ApiClient


LOOPBACK_NAMES = ("127.0.0.1", "localhost", "[::1]")
TOOL_ROUTES = {
    "get_training": "training_read",
    "upsert_training": "training_write",
    "list_official_plans": "plan",
    "get_official_plan": "plan",
    "query_food_records": "food_query",
    "upsert_food_records": "food_write",
    "upsert_custom_food": "food_custom",
    "search_official_food": "food_search",
    "list_food_templates": "food_templates_list",
    "apply_food_template": "food_templates_apply",
    "query_body_metrics": "body_query",
    "upsert_body_metrics": "body_write",
    "sync_agent_templates": "template_sync",
    "mutate_agent_templates": "template_mutate",
}


class XunjiMCP(FastMCP):
    def __init__(self, api: ApiClient, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api = api

    @contextmanager
    def _request_credentials(self):
        try:
            request = self.get_context().request_context.request
        except ValueError:
            request = None
        keys = None if request is None else request.state.xunji_keys
        token = REQUEST_KEYS.set(keys)
        try:
            yield
        finally:
            REQUEST_KEYS.reset(token)

    async def list_tools(self) -> list[types.Tool]:
        with self._request_credentials():
            tools = await super().list_tools()
            return [tool for tool in tools if self.api.has_credential(TOOL_ROUTES[tool.name])]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        with self._request_credentials():
            if name in TOOL_ROUTES:
                self.api.require_credential(TOOL_ROUTES[name])
            return await super().call_tool(name, arguments)

    def streamable_http_app(self) -> Starlette:
        app = super().streamable_http_app()

        async def health_check(_):
            return PlainTextResponse("OK", status_code=200)

        app.router.routes.append(Route("/health", health_check, methods=["GET"]))
        app.add_middleware(BindHttpCredentials)
        return app


def create_server(
    api: ApiClient,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    allowed_hosts: tuple[str, ...] = (),
    allowed_origins: tuple[str, ...] = (),
) -> XunjiMCP:
    loopback_hosts = [entry for name in LOOPBACK_NAMES for entry in (name, f"{name}:*")]

    # If allowed_hosts contains "*", disable DNS rebinding protection
    if "*" in allowed_hosts:
        enable_dns_protection = False
        final_allowed_hosts = []
    else:
        enable_dns_protection = True
        final_allowed_hosts = [*allowed_hosts, *loopback_hosts]

    server = XunjiMCP(
        api,
        "xunji-private-mcp",
        instructions=(
            "按用户指定的日期和范围访问训记。"
            "请提供能让用户核对的记录或变更，不要推测食物营养或未知数据。"
        ),
        host=host,
        port=port,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=enable_dns_protection,
            allowed_hosts=final_allowed_hosts,
            allowed_origins=[*allowed_origins, *(f"http://{entry}" for entry in loopback_hosts)],
        ),
    )
    for module in (training, food, body, templates):
        module.register_tools(server, api)
    return server


def main() -> None:
    parser = argparse.ArgumentParser(prog="xunji-private-mcp")
    transports = parser.add_subparsers(dest="transport")
    transports.add_parser("stdio", help="由 MCP 客户端启动，通过标准输入输出连接。")
    http = transports.add_parser("http", help="启动 Streamable HTTP /mcp 端点。")
    http.add_argument("--host", choices=("127.0.0.1", "localhost", "::1", "0.0.0.0"), default="127.0.0.1")
    http.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.transport == "http":
        if not 1 <= args.port <= 65535:
            parser.error("--port 必须介于 1 和 65535。")
        allowed_hosts = tuple(filter(None, map(str.strip, os.getenv("XUNJI_HTTP_ALLOWED_HOSTS", "").split(","))))
        allowed_origins = tuple(filter(None, map(str.strip, os.getenv("XUNJI_HTTP_ALLOWED_ORIGINS", "").split(","))))
        create_server(
            ApiClient(), host=args.host, port=args.port, allowed_hosts=allowed_hosts, allowed_origins=allowed_origins,
        ).run(transport="streamable-http")
    else:
        create_server(ApiClient(load_stdio_keys())).run(transport="stdio")
