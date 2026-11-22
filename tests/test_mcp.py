import asyncio
import gzip
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session
from starlette.testclient import TestClient

from xunji_private_mcp import upstream
from xunji_private_mcp.credentials import (
    BODY, FOOD, FOOD_SEARCH, KEY_HEADERS, KEY_NAMES, REQUEST_KEYS, TEMPLATE, TRAIN, load_stdio_keys,
)
from xunji_private_mcp.server import create_server
from xunji_private_mcp.upstream import ROUTES, ApiClient, UpstreamError


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
def test_stdio_key_missing_revoked_and_rotated(monkeypatch, route, name):
    paths = {item: endpoint.url for item, endpoint in ROUTES.items()}
    for key_name in KEY_NAMES:
        monkeypatch.delenv(key_name, raising=False)

    def respond(request):
        if request.headers["Authorization"] == "Bearer fake-revoked-key":
            return httpx.Response(401, json={"message": "apikey invalid: fake-revoked-key"})
        assert str(request.url) in paths.values()
        return httpx.Response(200, json={"success": True, "res": {"ok": True}})

    async def run():
        transport = httpx.MockTransport(respond)
        with pytest.raises(UpstreamError, match=name) as error:
            await ApiClient(load_stdio_keys(), transport).call(route, {})
        assert error.value.code == "key_missing"

        for key_name in KEY_NAMES:
            monkeypatch.setenv(key_name, f"fake-{key_name}")
        monkeypatch.setenv(name, "fake-revoked-key")
        with pytest.raises(UpstreamError, match=name) as error:
            await ApiClient(load_stdio_keys(), transport).call(route, {})
        assert error.value.code == "key_invalid"
        assert "fake-revoked-key" not in str(error.value)

        monkeypatch.setenv(name, "fake-rotated-key")
        api = ApiClient(load_stdio_keys(), transport)
        for other_route in ("training_read", "food_query", "food_search", "body_query", "template_sync"):
            assert await api.call(other_route, {}) == {"ok": True}

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


def test_successful_write_invalidates_only_its_credential_reads(monkeypatch):
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
        account = REQUEST_KEYS.set({TRAIN: "fake-other-account"})
        try:
            assert await api.call("training_read", {}, cache_ttl=100) == {"reads": 2}
        finally:
            REQUEST_KEYS.reset(account)
        await api.call("training_write", {}, invalidate=("training_read",))
        clock += 15
        assert await api.call("training_read", {}, cache_ttl=100) == {"reads": 3}
        account = REQUEST_KEYS.set({TRAIN: "fake-other-account"})
        try:
            assert await api.call("training_read", {}, cache_ttl=100) == {"reads": 2}
        finally:
            REQUEST_KEYS.reset(account)

    asyncio.run(run())


def test_real_mcp_direct_write_execution():
    """Test that writes execute directly without approval."""
    writes = []

    def respond(request):
        data = json.loads(request.content)
        if not data["dry_run"]:
            writes.append(data)
        return httpx.Response(200, json={"success": True, "res": {"summary": "72.4 kg"}})

    async def run():
        api = ApiClient({BODY: "fake-key"}, httpx.MockTransport(respond))

        async def call(route, body, **kwargs):
            return await ApiClient.call(api, route, body, rate_seconds=0, **kwargs)

        api.call = call
        server = create_server(api)
        async with create_connected_server_and_client_session(server) as session:
            assert any(tool.name == "upsert_body_metrics" for tool in (await session.list_tools()).tools)
            result = await session.call_tool("upsert_body_metrics", {
                "records": [{"datestr": "2026-06-28", "type": "weight", "value": 72.4}],
                "client_request_id": "test-request",
            })
            assert not result.isError
        assert len(writes) == 1
        assert writes[0]["confirmed"] is True

    asyncio.run(run())


HTTP_HEADERS = {"Accept": "application/json, text/event-stream"}
INITIALIZE = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
}


def open_http_session(client, credentials):
    headers = {**HTTP_HEADERS, **credentials}
    result = client.post("/mcp", headers=headers, json=INITIALIZE)
    assert result.status_code == 200
    headers["Mcp-Session-Id"] = result.headers["Mcp-Session-Id"]
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert client.post("/mcp", headers=headers, json=initialized).status_code == 202
    return headers


def http_result(response):
    assert response.status_code == 200
    data = next(line.removeprefix("data: ") for line in response.text.splitlines() if line.startswith("data: "))
    return json.loads(data)["result"]


def test_http_lists_only_configured_scopes_and_rejects_unconfigured_calls():
    requests = []

    def respond(request):
        requests.append((str(request.url), request.headers["Authorization"]))
        return httpx.Response(200, json={"success": True, "res": {}})

    app = create_server(ApiClient({BODY: "fake-server-key"}, httpx.MockTransport(respond))).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        def list_tools(headers):
            response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            return {tool["name"] for tool in http_result(response)["tools"]}

        def search(headers):
            response = client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                    "name": "search_official_food", "arguments": {"keyword": "鸡蛋", FOOD_SEARCH: "fake-body-key"},
                },
            })
            return http_result(response)

        diet = open_http_session(client, {KEY_HEADERS[FOOD]: "fake-diet", KEY_HEADERS[BODY]: ""})
        assert list_tools(diet) == {"query_food_records", "upsert_food_records", "upsert_custom_food", "list_food_templates", "apply_food_template"}
        assert list_tools({name: value for name, value in diet.items() if name != KEY_HEADERS[BODY]}) == list_tools(diet)

        account = open_http_session(client, {KEY_HEADERS[name]: f"fake-{name}" for name in (TRAIN, FOOD, BODY, TEMPLATE)})
        assert list_tools(account) == {
            "get_training", "upsert_training", "delete_training", "list_official_plans", "get_official_plan",
            "query_food_records", "upsert_food_records", "upsert_custom_food", "list_food_templates", "apply_food_template",
            "query_body_metrics", "upsert_body_metrics", "sync_agent_templates", "mutate_agent_templates",
        }

        search_only = open_http_session(client, {KEY_HEADERS[FOOD_SEARCH]: "fake-search"})
        assert list_tools(search_only) == {"search_food", "search_official_food"}
        denied = search(diet)
        assert denied["isError"] and KEY_HEADERS[FOOD_SEARCH] in denied["content"][0]["text"]
        assert requests == []
        assert not search(search_only).get("isError", False)
        assert requests == [(ROUTES["food_search"].url, "Bearer fake-search")]
        assert list_tools(open_http_session(client, {})) == set()


def test_concurrent_http_requests_keep_keys_and_arguments_together():
    arrived = asyncio.Event()
    requests = []

    async def respond(request):
        payload = json.loads(request.content)
        key = request.headers["Authorization"]
        requests.append((key, payload["start_date"]))
        assert BODY not in payload
        if len(requests) == 2:
            arrived.set()
        await asyncio.wait_for(arrived.wait(), timeout=5)
        return httpx.Response(200, json={
            "success": True, "res": {"owner": key.removeprefix("Bearer fake-"), "date": payload["end_date"]},
        })

    app = create_server(ApiClient(transport=httpx.MockTransport(respond))).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8765") as client, ThreadPoolExecutor(max_workers=2) as executor:
        def query(headers, date, other_key):
            response = client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "query_body_metrics", "arguments": {"start_date": date, "end_date": date, BODY: other_key},
                },
            })
            result = http_result(response)
            assert not result.get("isError", False), result
            return json.loads(result["content"][0]["text"])

        alice = open_http_session(client, {KEY_HEADERS[BODY]: "fake-alice"})
        bob = open_http_session(client, {KEY_HEADERS[BODY]: "fake-bob"})
        alice_call = executor.submit(query, alice, "2026-06-27", "fake-bob")
        bob_call = executor.submit(query, bob, "2026-06-28", "fake-alice")
        assert alice_call.result() == {"owner": "alice", "date": "2026-06-27"}
        assert bob_call.result() == {"owner": "bob", "date": "2026-06-28"}
        assert sorted(requests) == [("Bearer fake-alice", "2026-06-27"), ("Bearer fake-bob", "2026-06-28")]


def test_http_transport_checks_public_host_origin_and_key_format():
    app = create_server(
        ApiClient(), allowed_hosts=("mcp.example.com",), allowed_origins=("https://chat.example.com",),
    ).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.post("/mcp", headers={**HTTP_HEADERS, "Host": "other.invalid"}, json=INITIALIZE).status_code == 421
        assert client.post("/mcp", headers={**HTTP_HEADERS, "Origin": "https://other.invalid"}, json=INITIALIZE).status_code == 403
        result = client.post("https://mcp.example.com/mcp", headers={
            **HTTP_HEADERS, "Origin": "https://chat.example.com",
        }, json=INITIALIZE)
        assert result.status_code == 200
        assert "xunji-private-mcp" in result.text
        assert "no-store" in {directive.strip() for directive in result.headers["cache-control"].split(",")}
        key_header = KEY_HEADERS[BODY]
        result = client.post("/mcp", headers=[*HTTP_HEADERS.items(), (key_header, "fake-one"), (key_header, "fake-two")], json=INITIALIZE)
        assert result.status_code == 400
        assert "fake-one" not in result.text and "fake-two" not in result.text
        result = client.post("/mcp", headers={**HTTP_HEADERS, "Authorization": "Basic fake-invalid"}, json=INITIALIZE)
        assert result.status_code == 400
        assert "fake-invalid" not in result.text


@pytest.mark.parametrize("auth_header,prefix", [("Authorization", "Bearer "), (KEY_HEADERS[BODY], "")])
def test_http_sessions_and_caches_follow_request_keys(auth_header, prefix):
    keys_used = []

    def respond(request):
        key = request.headers["Authorization"]
        keys_used.append(key)
        if key == "Bearer fake-alice":
            return httpx.Response(200, json={"success": True, "res": {"label": "alice-private"}})
        if key == "Bearer fake-revoked":
            return httpx.Response(401, json={"message": "apikey invalid: fake-revoked"})
        return httpx.Response(200, json={"success": True, "res": {"label": "bob-private"}})

    app = create_server(ApiClient({BODY: "fake-server-key"}, httpx.MockTransport(respond))).streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        def open_session(key=None, **headers_override):
            credentials = {auth_header: f"{prefix}{key}"} if key else {}
            return open_http_session(client, {**credentials, **headers_override})

        def query(headers):
            return client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "query_body_metrics", "arguments": {"start_date": "2026-06-28", "end_date": "2026-06-28"},
                },
            })

        alice, bob, anonymous = (open_session(key) for key in ("fake-alice", "fake-bob", None))
        assert "alice-private" in query(alice).text
        assert "bob-private" in query(bob).text
        assert "alice-private" in query(alice).text
        assert KEY_HEADERS[BODY] in query(anonymous).text
        assert query({**alice, auth_header: f"{prefix}fake-bob"}).status_code == 404
        assert client.delete("/mcp", headers={**HTTP_HEADERS, "Mcp-Session-Id": alice["Mcp-Session-Id"]}).status_code == 404
        assert "bob-private" in query(open_session("fake-rotated")).text
        revoked = query(open_session("fake-revoked"))
        assert "训记拒绝了" in revoked.text and "fake-revoked" not in revoked.text
        assert keys_used == ["Bearer fake-alice", "Bearer fake-bob", "Bearer fake-rotated", "Bearer fake-revoked"]
        if auth_header == "Authorization":
            mixed = open_session("fake-revoked", **{KEY_HEADERS[BODY]: "fake-alice"})
            assert "alice-private" in query(mixed).text
            assert keys_used[-1] == "Bearer fake-revoked"
