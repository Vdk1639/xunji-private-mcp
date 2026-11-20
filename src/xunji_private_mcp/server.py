import argparse
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import body, food, templates, training
from .upstream import ApiClient, load_keys


LOOPBACK_NAMES = ("127.0.0.1", "localhost", "[::1]")


def create_server(api: ApiClient, *, host: str = "127.0.0.1", port: int = 8765) -> FastMCP:
    server = FastMCP(
        "xunji-private-mcp",
        instructions=(
            "按用户指定的日期和范围访问训记。写入工具会请求用户确认；"
            "请提供能让用户核对的记录或变更，不要推测食物营养或未知数据。"
        ),
        host=host,
        port=port,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[entry for name in LOOPBACK_NAMES for entry in (name, f"{name}:*")],
            allowed_origins=[entry for name in LOOPBACK_NAMES for entry in (f"http://{name}", f"http://{name}:*")],
        ),
    )
    for module in (training, food, body, templates):
        module.register_tools(server, api)
    return server


def main() -> None:
    parser = argparse.ArgumentParser(prog="xunji-private-mcp")
    parser.add_argument("--env-file", type=Path, default=Path(os.environ.get("XUNJI_ENV_FILE") or ".env"))
    transports = parser.add_subparsers(dest="transport")
    transports.add_parser("stdio", help="由 MCP 客户端启动，通过标准输入输出连接。")
    http = transports.add_parser("http", help="启动本地 Streamable HTTP /mcp 端点。")
    http.add_argument("--host", choices=("127.0.0.1", "localhost", "::1", "0.0.0.0"), default="127.0.0.1")
    http.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    api = ApiClient(load_keys(args.env_file))
    if args.transport == "http":
        if not 1 <= args.port <= 65535:
            parser.error("--port 必须介于 1 和 65535。")
        create_server(api, host=args.host, port=args.port).run(transport="streamable-http")
    else:
        create_server(api).run(transport="stdio")
