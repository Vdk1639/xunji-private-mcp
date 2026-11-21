import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from mcp.server.fastmcp import FastMCP

from xunji_private_mcp import body, food
from xunji_private_mcp.exceptions import ToolError


@pytest.fixture
def tools():
    server = FastMCP("test")
    api = AsyncMock()
    api.call.return_value = {"summary": {"updated": 1}}
    food.register_tools(server, api)
    body.register_tools(server, api)
    return server, api


def test_food_reads_validate_dates_and_use_separate_routes(tools):
    server, api = tools
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()

    asyncio.run(server.call_tool("query_food_records", {"start_date": today, "end_date": today}))
    api.call.assert_awaited_once_with(
        "food_query", {"start_date": today, "end_date": today, "include_detail": True}, cache_ttl=15
    )
    with pytest.raises(Exception):  # FastMCP wraps ToolError
        asyncio.run(
            server.call_tool("query_food_records", {"start_date": "2000-01-01", "end_date": today})
        )
    assert api.call.await_count == 1
    asyncio.run(server.call_tool("search_official_food", {"keyword": " 鸡蛋 "}))
    api.call.assert_awaited_with("food_search", {"keyword": "鸡蛋", "limit": 8}, cache_ttl=15)
    assert food.shift_months(date(2024, 2, 29), -12) == date(2023, 2, 28)
    assert food.shift_months(date(2024, 1, 31), 3) == date(2024, 4, 30)


def test_food_write_directly_executes_and_invalidates_cache(tools):
    """Test that food write operations execute directly without approval."""
    server, api = tools
    record = {
        "id": 24,
        "date": "2026-06-28",
        "meal_type": "lunch",
        "name": "鸡胸肉",
        "amount": 150.0,
        "unit": "g",
        "uniquekey": "mock-food",
        "ntr": {"cal": 165.0, "protein": 31.0, "fat": 3.6, "carb": 0.0},
    }

    asyncio.run(
        server.call_tool("upsert_food_records", {"foods": [record], "client_request_id": "retry-id"})
    )
    api.call.assert_awaited_once_with(
        "food_write",
        {"client_request_id": "retry-id", "dry_run": False, "foods": [record]},
        invalidate=("food_query",),
    )


def test_custom_food_validates_units_and_executes_directly(tools):
    """Test that custom food operations validate and execute directly."""
    server, api = tools
    arguments = {
        "name": "鸡胸肉",
        "ntr": {
            "cal": 165,
            "protein": 31,
            "fat": 3.6,
            "carb": 0,
            "foodUnit": [{"unit": "份", "count": "1", "gram": 100}],
        },
        "nutrition_source": "实物包装营养成分表",
        "units": [{"unit": "份", "count": "1", "gram": 120}],
    }

    # Should fail validation: units mismatch
    with pytest.raises(Exception, match="必须一致"):
        asyncio.run(server.call_tool("upsert_custom_food", arguments))
    api.call.assert_not_awaited()

    # Fix validation issue and execute
    arguments.pop("units")
    asyncio.run(server.call_tool("upsert_custom_food", arguments))
    route, payload = api.call.await_args.args
    assert route == "food_custom"
    assert payload["food"]["ntr"]["foodUnit"] == payload["food"]["units"]
    assert payload["food"]["units"] == [{"unit": "份", "count": "1", "gram": 100.0}]
    assert "nutrition_source" not in payload


def test_body_query_filters_and_paginates_using_upstream_metric_names(tools):
    server, api = tools
    options = {
        "start_date": "2026-01-01",
        "end_date": "2026-06-28",
        "types": ["weist"],
        "limit": 20,
        "offset": 40,
    }
    asyncio.run(server.call_tool("query_body_metrics", options))
    api.call.assert_awaited_once_with(
        "body_query", {**options, "include_latest": True, "include_records": True}, cache_ttl=15
    )
    with pytest.raises(Exception):  # FastMCP wraps ToolError
        asyncio.run(server.call_tool("query_body_metrics", {**options, "types": ["waist"]}))
    assert api.call.await_count == 1


def test_body_write_previews_and_executes_directly(tools):
    """Test that body metrics write operations preview and execute directly."""
    server, api = tools
    records = [{"datestr": "2026-06-28", "type": "weist", "value": 72.1234567}]
    payload = {
        "schema_version": "body_open_api_v1",
        "client_request_id": "retry-id",
        "records": records,
    }

    args = {"records": records, "client_request_id": "retry-id"}
    asyncio.run(server.call_tool("upsert_body_metrics", args))

    # Should call dry_run first, then actual write
    assert api.call.await_count == 2
    api.call.assert_any_call("body_write", {**payload, "dry_run": True})
    api.wait_for_rate_limit.assert_awaited_once_with("body_write")
    api.call.assert_awaited_with(
        "body_write",
        {**payload, "dry_run": False, "confirmed": True},
        invalidate=("body_query",),
    )
