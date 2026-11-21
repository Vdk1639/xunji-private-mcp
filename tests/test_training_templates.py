import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from xunji_private_mcp import templates, training
from xunji_private_mcp.exceptions import ToolError
from xunji_private_mcp.upstream import UpstreamError


class RecordedTools(dict):
    def tool(self, **options):
        def register(function):
            self[function.__name__] = function
            return function

        return register


def _setup(module, monkeypatch, *responses):
    """Setup tools with mocked API calls (no approval mechanism)."""
    tools = RecordedTools()
    call = AsyncMock(side_effect=responses)
    module.register_tools(
        tools,
        SimpleNamespace(
            call=call, credential_scope=lambda route: "test-account", wait_for_rate_limit=AsyncMock()
        ),
    )
    return tools, call


def test_training_update_preserves_times_unfinished_sets_and_note_metadata(monkeypatch):
    """Test that training updates preserve existing metadata."""
    day = date(2026, 11, 20)
    monkeypatch.setattr(training, "_today", lambda: day)
    original = {
        "datestr": day.isoformat(),
        "localid": 7,
        "title": "旧标题",
        "start": 123,
        "end": 456,
        "note": "保留原备注和隐藏元数据",
        "trainColor": "#222222",
        "movements": [
            {"name": "杠铃卧推", "key": "internal", "sets": [{"reps": "8", "done": False, "rpe": "7"}]}
        ],
    }
    snapshot = {"trains": [original]}
    tools, call = _setup(training, monkeypatch, snapshot, snapshot, {"trains": []})
    patch = {
        "datestr": day.isoformat(),
        "localid": 7,
        "title": "新标题",
        "note": {"trainColor": "#123456"},
    }
    asyncio.run(tools["upsert_training"](None, [patch], "training-request"))
    read_call, verify_call, write_call = call.await_args_list
    assert read_call.args[1]["include_full_data"] is True
    assert read_call.kwargs["rate_seconds"] == 30
    assert verify_call == read_call
    assert write_call.kwargs["invalidate"] == ("training_read",)
    assert write_call.args[1]["res"][0] == {
        **patch,
        "start": 123,
        "end": 456,
        "movements": [
            {"name": "杠铃卧推", "sets": [{"reps": "8", "done": False, "rpe": "7"}]}
        ],
    }



def test_cardio_write_executes_directly_without_confirmation(monkeypatch):
    """Test that cardio training writes execute directly."""
    monkeypatch.setattr(training, "_today", lambda: date(2026, 11, 30))
    tools, call = _setup(training, monkeypatch, {"trains": []})
    trains = [
        {
            "datestr": "2026-05-30",
            "movements": [
                {
                    "name": "跑步",
                    "cardio": True,
                    "recordPreset": "running",
                    "metrics": {"distance": "5"},
                }
            ],
        }
    ]
    asyncio.run(tools["upsert_training"](None, trains, "training-request"))
    # Should call training_write once (no verification needed for new records without localid)
    assert call.await_count == 1
    assert call.await_args.args[0] == "training_write"


def test_training_drift_after_read_requires_new_review(monkeypatch):
    """Test that training drift detection works."""
    day = date(2026, 11, 20)
    monkeypatch.setattr(training, "_today", lambda: day)
    original = {
        "localid": 7,
        "title": "原训练",
        "movements": [{"name": "杠铃卧推", "sets": [{"reps": "8"}]}],
    }
    current = {**original, "title": "App 新标题"}
    tools, call = _setup(training, monkeypatch, {"trains": [original]}, {"trains": [current]})
    patch = {"datestr": day.isoformat(), "localid": 7, "title": "计划修改"}
    with pytest.raises(Exception, match="原训练发生变化"):
        asyncio.run(tools["upsert_training"](None, [patch], "training-request"))
    assert [request.args[0] for request in call.await_args_list] == [
        "training_read",
        "training_read",
    ]


def test_training_blocks_same_day_overlap(monkeypatch):
    """Test that concurrent writes to same day are blocked."""
    day = date(2026, 11, 20)
    monkeypatch.setattr(training, "_today", lambda: day)

    # Create a slow mock that holds the lock
    async def slow_call(route, *args, **kwargs):
        await asyncio.sleep(0.1)  # Hold the lock for 100ms
        return {"code": 0, "trains": []}

    tools, call = _setup(training, monkeypatch, {"trains": []})
    call.side_effect = slow_call

    request = [
        {"datestr": day.isoformat(), "movements": [{"name": "杠铃卧推", "sets": [{"reps": "8"}]}]}
    ]
    tool = tools["upsert_training"]

    # Simulate concurrent write attempt while first is in progress
    async def test_overlap():
        # First write (will take 100ms)
        task1 = asyncio.create_task(tool(None, request, "first"))
        # Give it time to acquire the lock
        await asyncio.sleep(0.01)
        # Second concurrent write should fail immediately
        with pytest.raises(Exception, match="该日期已有训练写入"):
            await tool(None, request, "overlap")
        await task1

    asyncio.run(test_overlap())


def test_official_plan_date_boundaries(monkeypatch):
    """Test that official plan queries validate date ranges."""
    tools, call = _setup(training, monkeypatch, {"days": []})
    tool = tools["get_official_plan"]
    with pytest.raises(Exception, match="92 天"):
        asyncio.run(tool("platform:155", date(2026, 1, 1), date(2026, 4, 3)))
    call.assert_not_awaited()
    asyncio.run(tool("universal:155", date(2026, 1, 1), date(2026, 4, 2), False))
    assert call.await_args.args[1]["include_movements"] is False
    assert call.await_args.kwargs["rate_scope"] == "get:universal:155"


def _snapshot(count=1, version=2):
    """Create template snapshot fixture."""
    movement = [
        {
            "key": "benchpress",
            "label": "杠铃卧推",
            "sets": [{"reps": "8", "comment": "保留"}],
        }
    ]
    return {
        "folder": {"version": 1, "name": "我的模板"},
        "template_versions": {f"template{index}": version for index in range(count)},
        "templates": [
            {
                "template_id": f"template{index}",
                "data": {
                    "name": f"推 {index}",
                    "movement": movement,
                    "rules": {"scheme": "manual"},
                },
            }
            for index in range(count)
        ],
    }


def test_template_replacement_preserves_capacity_and_executes(monkeypatch):
    """Test that template mutations preserve capacity and execute directly."""
    tools, call = _setup(templates, monkeypatch, _snapshot(count=14), {"applied": []})
    create = {
        "client_id": "push",
        "name": "推 A",
        "movements": [{"name": "杠铃卧推", "sets": [{"reps": 8}]}],
    }
    delete = {"template_id": "template0", "base_version": 2}
    asyncio.run(
        tools["mutate_agent_templates"](None, "mutation", upserts=[create], deletes=[delete])
    )
    assert call.await_args.args[1]["deletes"] == [delete]
    assert call.await_args.args[1]["confirmed"] is True


@pytest.mark.parametrize(
    "entry",
    [
        {"template_id": "outside", "base_version": 2},
        {"template_id": "template0", "base_version": 1},
    ],
)
def test_template_rejects_unlisted_and_stale_targets(monkeypatch, entry):
    """Test that template mutations validate version and existence."""
    tools, call = _setup(templates, monkeypatch, _snapshot())
    with pytest.raises(Exception, match="专属文件夹|当前版本 2"):
        asyncio.run(tools["mutate_agent_templates"](None, "mutation", deletes=[entry]))
    call.assert_awaited_once_with("template_sync", {})


def test_template_conflict_resyncs_without_silent_rebase(monkeypatch):
    """Test that version conflicts trigger resync."""
    original = _snapshot()
    tools, call = _setup(
        templates,
        monkeypatch,
        original,
        UpstreamError("version_conflict", "version conflict"),
        _snapshot(version=3),
    )
    entry = {"template_id": "template0", "base_version": 2, "name": "推 A"}
    with pytest.raises(Exception, match='"template0": 3'):
        asyncio.run(tools["mutate_agent_templates"](None, "mutation", upserts=[entry]))
    assert [record.args[0] for record in call.await_args_list] == [
        "template_sync",
        "template_mutate",
        "template_sync",
    ]
    assert call.await_args_list[1].args[1]["upserts"] == [
        {**original["templates"][0]["data"], **entry}
    ]
