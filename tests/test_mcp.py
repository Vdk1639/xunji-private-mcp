import asyncio
import gzip
import json

import httpx
import pytest
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session
from starlette.testclient import TestClient

from xunji_private_mcp import upstream
from xunji_private_mcp.server import create_server
from xunji_private_mcp.upstream import BODY, FOOD, FOOD_SEARCH, ROUTES, TEMPLATE, TRAIN, ApiClient, UpstreamError


def test_each_route_selects_only_its_own_key():
    expected = {
        "training_read": TRAIN, "training_write": TRAIN, "plan": TRAIN,
        "food_query": FOOD, "food_write": FOOD, "food_custom": FOOD, "food_search": FOOD_SEARCH,
        "body_query": BODY, "body_write": BODY, "template_sync": TEMPLATE, "template_mutate": TEMPLATE,
    }
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"success": True, "res": {}})

    async def run():
        for route, key_name in expected.items():
            api = ApiClient({key_name: f"fake-{key_name}"}, httpx.MockTransport(respond))
            await api.call(route, {"date": "example"})
            request = requests[-1]
            assert str(request.url) == ROUTES[route].url
            assert request.headers["Authorization"] == f"Bearer fake-{key_name}"
            assert json.loads(request.content) == {"date": "example"}

    asyncio.run(run())


@pytest.mark.parametrize("route,name", [
    ("training_read", TRAIN), ("food_query", FOOD), ("food_search", FOOD_SEARCH),
    ("body_query", BODY), ("template_sync", TEMPLATE),
])
def test_key_missing_revoked_and_rotated(tmp_path, monkeypatch, route, name):
    paths = {item: endpoint.url for item, endpoint in ROUTES.items()}
    env_file = tmp_path / ".env"
    for key_name in upstream.KEY_NAMES:
        monkeypatch.delenv(key_name, raising=False)

    def respond(request):
        if request.headers["Authorization"] == "Bearer fake-revoked-key":
            return httpx.Response(401, json={"message": "apikey invalid: fake-revoked-key"})
        assert str(request.url) in paths.values()
        return httpx.Response(200, json={"success": True, "res": {"ok": True}})

    async def run():
        transport = httpx.MockTransport(respond)
        with pytest.raises(UpstreamError, match=name) as error:
            await ApiClient(upstream.load_keys(env_file), transport).call(route, {})
        assert error.value.code == "key_missing"

        file_keys = {key_name: f"fake-{key_name}" for key_name in upstream.KEY_NAMES}
        file_keys[name] = "fake-revoked-key"
        env_file.write_text("\n".join(f"{key}={value}" for key, value in file_keys.items()), encoding="utf-8-sig")
        with pytest.raises(UpstreamError, match=name) as error:
            await ApiClient(upstream.load_keys(env_file), transport).call(route, {})
        assert error.value.code == "key_invalid"
        assert "fake-revoked-key" not in str(error.value)

        env_file.write_text(env_file.read_text(encoding="utf-8").replace("fake-revoked-key", "fake-rotated-key"), encoding="utf-8")
        assert upstream.load_keys(env_file)[name] == "fake-rotated-key"
        api = ApiClient(upstream.load_keys(env_file), transport)
        for other_route in ("training_read", "food_query", "food_search", "body_query", "template_sync"):
            assert await api.call(other_route, {}) == {"ok": True}

        monkeypatch.setenv(name, "fake-process-override")
        assert upstream.load_keys(env_file)[name] == "fake-process-override"

    asyncio.run(run())


def test_gzip_cache_and_server_rate_limit():
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) > 1:
            return httpx.Response(429, json={"retry_after_ms": 20000})
        data = gzip.compress(b'{"res":{"trains":[{"localid":1}]}}')
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=data)

    async def run():
        api = ApiClient({TRAIN: "fake-key"}, httpx.MockTransport(respond))
        body = {"datestr": "2026-01-01"}
        result = await api.call("training_read", body, cache_ttl=15, rate_scope="first")
        result["trains"].clear()
        assert await api.call("training_read", body, cache_ttl=15, rate_scope="first") == {"trains": [{"localid": 1}]}
        with pytest.raises(UpstreamError, match="20 秒") as limited:
            await api.call("training_read", body, rate_scope="second")
        assert limited.value.code == "rate_limited"
        with pytest.raises(UpstreamError, match="限频"):
            await api.call("training_read", body, rate_scope="second")
        assert len(calls) == 2

    asyncio.run(run())


def test_successful_write_invalidates_reads(monkeypatch):
    clock = 1.0
    monkeypatch.setattr(upstream, "time", type("Clock", (), {"monotonic": staticmethod(lambda: clock)}))
    reads = 0

    def respond(request):
        nonlocal reads
        if str(request.url) == ROUTES["training_read"].url:
            reads += 1
        return httpx.Response(200, json={"res": {"reads": reads}})

    async def run():
        nonlocal clock
        api = ApiClient({TRAIN: "fake-key"}, httpx.MockTransport(respond))
        assert await api.call("training_read", {}, cache_ttl=100) == {"reads": 1}
        await api.call("training_write", {}, invalidate=("training_read",))
        clock += 15
        assert await api.call("training_read", {}, cache_ttl=100) == {"reads": 2}

    asyncio.run(run())


@pytest.mark.parametrize("action,approved", [(None, False), ("decline", False), ("accept", False), ("accept", True)])
def test_real_mcp_confirmation_gate(action, approved):
    writes = []

    def respond(request):
        data = json.loads(request.content)
        if not data["dry_run"]:
            writes.append(data)
        return httpx.Response(200, json={"success": True, "res": {"summary": "72.4 kg"}})

    async def elicit(context, params):
        assert "72.4" in params.message
        return types.ElicitResult(action=action, content={"approve": approved} if action == "accept" else None)

    async def run():
        api = ApiClient({BODY: "fake-key"}, httpx.MockTransport(respond))

        async def call(route, body, **kwargs):
            return await ApiClient.call(api, route, body, rate_seconds=0, **kwargs)

        api.call = call
        server = create_server(api)
        async with create_connected_server_and_client_session(server, elicitation_callback=elicit if action else None) as session:
            assert any(tool.name == "upsert_body_metrics" for tool in (await session.list_tools()).tools)
            result = await session.call_tool("upsert_body_metrics", {
                "records": [{"datestr": "2026-06-28", "type": "weight", "value": 72.4}],
                "client_request_id": "test-request",
            })
            assert result.isError is (not approved)
        assert len(writes) == int(approved)
        if approved:
            assert writes[0]["confirmed"] is True

    asyncio.run(run())


def test_http_transport_rejects_nonlocal_host_and_origin():
    app = create_server(ApiClient({})).streamable_http_app()
    headers = {"Accept": "application/json, text/event-stream"}
    initialize = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
    }
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.post("/mcp", headers={**headers, "Host": "other.invalid"}, json=initialize).status_code == 421
        assert client.post("/mcp", headers={**headers, "Origin": "https://other.invalid"}, json=initialize).status_code == 403
        result = client.post("/mcp", headers=headers, json=initialize)
        assert result.status_code == 200
        assert "xunji-private-mcp" in result.text
