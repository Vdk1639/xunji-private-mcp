import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from xunji_private_mcp import templates, training
from xunji_private_mcp.interaction import ToolError
from xunji_private_mcp.upstream import UpstreamError


class RecordedTools(dict):
    def tool(self, **options):
        def register(function):
            self[function.__name__] = function
            return function

        return register


def _setup(module, monkeypatch, *responses):
    tools = RecordedTools()
    call = AsyncMock(side_effect=responses)
    confirm = AsyncMock()
    monkeypatch.setattr(module, "confirm", confirm)
    module.register_tools(tools, SimpleNamespace(call=call))
    return tools, call, confirm


def test_training_update_preserves_times_unfinished_sets_and_note_metadata(monkeypatch):
    day = date(2026, 11, 20)
    monkeypatch.setattr(training, "_today", lambda: day)
    original = {
        "datestr": day.isoformat(), "localid": 7, "title": "旧标题", "start": 123, "end": 456,
        "note": "保留原备注和隐藏元数据", "trainColor": "#222222",
        "movements": [{"name": "杠铃卧推", "key": "internal", "sets": [{"reps": "8", "done": False, "rpe": "7"}]}],
    }
    snapshot = {"trains": [original]}
    tools, call, confirm = _setup(training, monkeypatch, snapshot, snapshot, {"trains": []})
    patch = {"datestr": day.isoformat(), "localid": 7, "title": "新标题", "note": {"trainColor": "#123456"}}
    asyncio.run(tools["upsert_training"](None, [patch], "training-request"))
    read_call, verify_call, write_call = call.await_args_list
    assert read_call.args[1]["include_full_data"] is True
    assert read_call.kwargs["rate_seconds"] == 30
    assert verify_call == read_call
    assert write_call.kwargs["invalidate"] == ("training_read",)
    assert write_call.args[1]["res"][0] == {
        **patch, "start": 123, "end": 456,
        "movements": [{"name": "杠铃卧推", "sets": [{"reps": "8", "done": False, "rpe": "7"}]}],
    }
    assert "旧标题" in confirm.await_args.args[1] and "新标题" in confirm.await_args.args[1]


def test_declined_cardio_write_never_reaches_upstream(monkeypatch):
    monkeypatch.setattr(training, "_today", lambda: date(2026, 11, 30))
    tools, call, confirm = _setup(training, monkeypatch)
    confirm.side_effect = ToolError("用户拒绝")
    trains = [{
        "datestr": "2026-05-30",
        "movements": [{"name": "跑步", "cardio": True, "recordPreset": "running", "metrics": {"distance": "5"}}],
    }]
    with pytest.raises(ToolError, match="用户拒绝"):
        asyncio.run(tools["upsert_training"](None, trains, "training-request"))
    confirm.assert_awaited_once()
    call.assert_not_awaited()


def test_training_drift_after_confirmation_requires_new_review(monkeypatch):
    day = date(2026, 11, 20)
    monkeypatch.setattr(training, "_today", lambda: day)
    original = {"localid": 7, "title": "原训练", "movements": [{"name": "杠铃卧推", "sets": [{"reps": "8"}]}]}
    current = {**original, "title": "App 新标题"}
    tools, call, confirm = _setup(training, monkeypatch, {"trains": [original]}, {"trains": [current]})
    patch = {"datestr": day.isoformat(), "localid": 7, "title": "计划修改"}
    with pytest.raises(ToolError, match="原训练发生变化"):
        asyncio.run(tools["upsert_training"](None, [patch], "training-request"))
    confirm.assert_awaited_once()
    assert [request.args[0] for request in call.await_args_list] == ["training_read", "training_read"]


def test_training_blocks_same_day_overlap_and_releases_on_decline(monkeypatch):
    day = date(2026, 11, 20)
    monkeypatch.setattr(training, "_today", lambda: day)
    tools, call, confirm = _setup(training, monkeypatch, {"trains": []})
    request = [{"datestr": day.isoformat(), "movements": [{"name": "杠铃卧推", "sets": [{"reps": "8"}]}]}]
    tool = tools["upsert_training"]

    async def reject_after_overlap(*_):
        with pytest.raises(ToolError, match="该日期已有训练写入"):
            await tool(None, request, "overlap")
        raise ToolError("用户拒绝")

    confirm.side_effect = reject_after_overlap
    with pytest.raises(ToolError, match="用户拒绝"):
        asyncio.run(tool(None, request, "first"))
    call.assert_not_awaited()
    confirm.side_effect = None
    asyncio.run(tool(None, request, "next"))
    assert call.await_args.args[1]["client_request_id"] == "next"


def test_official_plan_date_boundaries(monkeypatch):
    tools, call, _ = _setup(training, monkeypatch, {"days": []})
    tool = tools["get_official_plan"]
    with pytest.raises(ToolError, match="92 天"):
        asyncio.run(tool("platform:155", date(2026, 1, 1), date(2026, 4, 3)))
    call.assert_not_awaited()
    asyncio.run(tool("universal:155", date(2026, 1, 1), date(2026, 4, 2), False))
    assert call.await_args.args[1]["include_movements"] is False
    assert call.await_args.kwargs["rate_scope"] == "get:universal:155"


def _snapshot(count=1, version=2):
    movement = [{"key": "benchpress", "label": "杠铃卧推", "sets": [{"reps": "8", "comment": "保留"}]}]
    return {
        "folder": {"version": 1, "name": "我的模板"},
        "template_versions": {f"template{index}": version for index in range(count)},
        "templates": [
            {"template_id": f"template{index}", "data": {"name": f"推 {index}", "movement": movement, "rules": {"scheme": "manual"}}}
            for index in range(count)
        ],
    }


def test_template_replacement_preserves_capacity_and_shows_deletion(monkeypatch):
    tools, call, confirm = _setup(templates, monkeypatch, _snapshot(count=14), {"applied": []})
    create = {"client_id": "push", "name": "推 A", "movements": [{"name": "杠铃卧推", "sets": [{"reps": 8}]}]}
    delete = {"template_id": "template0", "base_version": 2}
    asyncio.run(tools["mutate_agent_templates"](None, "mutation", upserts=[create], deletes=[delete]))
    assert call.await_args.args[1]["deletes"] == [delete]
    assert call.await_args.args[1]["confirmed"] is True
    assert "推 0" in confirm.await_args.args[1] and "推 A" in confirm.await_args.args[1]


@pytest.mark.parametrize("entry", [
    {"template_id": "outside", "base_version": 2}, {"template_id": "template0", "base_version": 1},
])
def test_template_rejects_unlisted_and_stale_targets(monkeypatch, entry):
    tools, call, confirm = _setup(templates, monkeypatch, _snapshot())
    with pytest.raises(ToolError, match="专属文件夹|当前版本 2"):
        asyncio.run(tools["mutate_agent_templates"](None, "mutation", deletes=[entry]))
    confirm.assert_not_awaited()
    call.assert_awaited_once_with("template_sync", {})


def test_template_conflict_resyncs_without_silent_rebase(monkeypatch):
    original = _snapshot()
    tools, call, confirm = _setup(
        templates, monkeypatch, original, UpstreamError("version_conflict", "version conflict"), _snapshot(version=3),
    )
    entry = {"template_id": "template0", "base_version": 2, "name": "推 A"}
    with pytest.raises(ToolError, match='"template0": 3'):
        asyncio.run(tools["mutate_agent_templates"](None, "mutation", upserts=[entry]))
    assert [record.args[0] for record in call.await_args_list] == ["template_sync", "template_mutate", "template_sync"]
    assert call.await_args_list[1].args[1]["upserts"] == [{**original["templates"][0]["data"], **entry}]
    confirm.assert_awaited_once()
