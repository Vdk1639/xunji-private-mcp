import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html import escape
from secrets import token_urlsafe
from time import monotonic
from typing import Any
from urllib.parse import parse_qs, urlsplit

from mcp.server.fastmcp.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import HTMLResponse

from .credentials import REQUEST_KEYS, fingerprint, valid_key
from .upstream import ROUTES, ApiClient

APPROVAL_PATH = "/approve/{token}"
TTL = 300


@dataclass
class PendingWrite:
    expires: float
    key_name: str
    owner: str
    summary: str
    submit: Callable[[], Awaitable[Any]]
    review_token: str = ""
    key: str = ""


def approval_page(content: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>训记写入确认</title><main><h1>训记写入确认</h1>' + content + "</main></html>",
        status_code=status,
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'",
            "Referrer-Policy": "same-origin",
        },
    )


class BrowserApprovals:
    def __init__(self, api: ApiClient, origin: str):
        url = urlsplit(origin)
        if (
            not url.hostname or url.username is not None or url.password is not None
            or url.query or url.fragment or url.path not in ("", "/")
            or not (url.scheme == "https" or url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1"))
            or any(char.isspace() or char in "\\%" for char in origin)
        ):
            raise ValueError("XUNJI_APPROVAL_BASE_URL 必须是 HTTPS 或回环 HTTP 的站点地址，不含路径。")
        host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
        port = f":{url.port}" if url.port not in (None, 443 if url.scheme == "https" else 80) else ""
        self.origin = f"{url.scheme}://{host}{port}"
        self.api = api
        self.pending: dict[str, PendingWrite] = {}

    def stage(self, route: str, summary: str, submit: Callable[[], Awaitable[Any]]) -> dict:
        now = monotonic()
        self.pending = {token: item for token, item in self.pending.items() if item.expires > now}
        if len(self.pending) >= 128 or len(summary.encode()) > 256 * 1024:
            raise ToolError("待确认请求过多或变更摘要过长，请稍后重试或缩小范围。")
        token = token_urlsafe(32)
        self.pending[token] = PendingWrite(now + TTL, ROUTES[route].key, self.api.credential_scope(route), summary, submit)
        return {
            "status": "approval_required",
            "approval_url": f"{self.origin}/approve/{token}",
            "expires_in_seconds": TTL,
            "message": "变更尚未写入。请把确认链接发给用户，让用户在浏览器核对并确认。不要在对话中索取 Key，或替用户打开和提交链接。",
        }

    async def handle(self, request: Request) -> HTMLResponse:
        token = request.path_params["token"]
        item = self.pending.get(token)
        if item is None or item.expires <= monotonic():
            self.pending.pop(token, None)
            return approval_page("<p>请求已过期或已处理。请返回对话重新发起。</p>", 404)
        if request.method in ("GET", "HEAD"):
            return approval_page(
                '<form method="post"><label>对应业务的训记 API Key '
                '<input type="password" name="key" autocomplete="off" required maxlength="1024"></label> '
                '<button name="action" value="review">查看变更</button></form>'
            )
        if request.headers.get("origin") != self.origin:
            return approval_page("<p>请求来源无效。</p>", 403)
        if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
            return approval_page("<p>请求格式无效。</p>", 415)
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 4096:
                return approval_page("<p>表单过大。</p>", 413)
            data.extend(chunk)
        try:
            fields = dict(parse_qs(data.decode("ascii"), max_num_fields=3, strict_parsing=True))
            action, = fields["action"]
        except (KeyError, ValueError):
            return approval_page("<p>表单无效。</p>", 400)
        if self.pending.get(token) is not item or item.expires <= monotonic():
            return approval_page("<p>请求已过期或已处理。</p>", 404)
        if action == "review":
            key = fields.get("key", [""])
            if len(key) != 1 or not valid_key(key[0]) or not hmac.compare_digest(
                fingerprint(f"{item.key_name}:{key[0]}"), item.owner
            ):
                return approval_page("<p>Key 与本次变更的账户不匹配。请返回重试。</p>", 403)
            item.key = key[0]
            item.review_token = token_urlsafe(32)
            return approval_page(
                '<pre style="white-space:pre-wrap;overflow-wrap:anywhere">' + escape(item.summary) + '</pre>'
                '<form method="post">'
                f'<input type="hidden" name="review_token" value="{item.review_token}">'
                '<button name="action" value="approve">确认写入</button> '
                '<button name="action" value="cancel">取消写入</button></form>'
            )
        proof = fields.get("review_token", [""])
        if (
            action not in ("approve", "cancel") or len(proof) != 1 or not proof[0].isascii()
            or not item.review_token or not hmac.compare_digest(item.review_token, proof[0])
        ):
            return approval_page("<p>请先验证 Key 并查看变更。</p>", 403)
        del self.pending[token]
        if action == "cancel":
            return approval_page("<p>已取消。未写入训记。</p>")
        credentials = REQUEST_KEYS.set({item.key_name: item.key})
        try:
            await item.submit()
        except Exception:
            return approval_page("<p>未能确认写入成功。请查询训记记录后再决定是否重试。</p>", 502)
        finally:
            REQUEST_KEYS.reset(credentials)
        return approval_page("<p>已写入训记。</p>")
