import hmac
import json
import os
from contextvars import ContextVar
from secrets import token_bytes

from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from starlette.requests import HTTPConnection
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


TRAIN = "XUNJI_TRAIN_KEY"
FOOD = "XUNJI_FOOD_KEY"
FOOD_SEARCH = "XUNJI_FOOD_SEARCH_KEY"
BODY = "XUNJI_BODY_KEY"
TEMPLATE = "XUNJI_AGENT_TEMPLATE_KEY"
KEY_NAMES = (TRAIN, FOOD, FOOD_SEARCH, BODY, TEMPLATE)
KEY_HEADERS = {name: "X-" + name.replace("_", "-").title() for name in KEY_NAMES}
AUTHORIZATION = "Authorization"
REQUEST_KEYS: ContextVar[dict[str, str] | None] = ContextVar("xunji_request_keys", default=None)
_FINGERPRINT_SECRET = token_bytes(32)


def fingerprint(value: str) -> str:
    return hmac.digest(_FINGERPRINT_SECRET, value.encode(), "sha256").hex()


def load_stdio_keys() -> dict[str, str]:
    return {name: os.environ[name].strip() for name in KEY_NAMES if name in os.environ}


def valid_key(key: str) -> bool:
    return 0 < len(key) <= 1024 and key.isascii() and key.isprintable() and not any(
        char.isspace() or char == "," for char in key
    )


class BindHttpCredentials:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (b"cache-control", b"no-store")]
            await send(message)

        request = HTTPConnection(scope)
        keys = {}
        authorization = request.headers.getlist(AUTHORIZATION)
        if authorization:
            scheme, _, key = authorization[0].partition(" ")
            if len(authorization) != 1 or scheme.lower() != "bearer" or not valid_key(key):
                await PlainTextResponse("Invalid Authorization header", status_code=400)(scope, receive, no_store)
                return
            keys[AUTHORIZATION] = key
        for name, header in KEY_HEADERS.items():
            values = request.headers.getlist(header)
            if not values or values == [""]:
                continue
            if len(values) != 1 or not valid_key(values[0]):
                await PlainTextResponse(f"Invalid {header} header", status_code=400)(scope, receive, no_store)
                return
            keys[name] = values[0]

        scope.setdefault("state", {})["xunji_keys"] = keys
        profile = fingerprint(json.dumps(keys, sort_keys=True))
        scope["user"] = AuthenticatedUser(AccessToken(token="", client_id=profile, scopes=[]))
        await self.app(scope, receive, no_store)
