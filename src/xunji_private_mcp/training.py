import calendar
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .exceptions import ToolError
from .upstream import ApiClient

TRAIN_SCHEMA = "train_open_api_v2"
PLAN_SCHEMA = "plan_open_api_v1"
TRAIN_FIELDS = {"datestr", "localid", "start", "end", "title", "movements", "note", "trainColor"}
SET_FIELDS = {"weight", "weight_kg", "reps", "time", "duration_s", "selfWeight"}
RPE_VALUES = {"", "6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5", "10"}


def _shift_months(day: date, months: int) -> date:
    year, month_index = divmod(day.year * 12 + day.month - 1 + months, 12)
    month = month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def _training_day(trains: list[dict[str, Any]]) -> date:
    if not 1 <= len(trains) <= 4:
        raise ToolError("每次写入需要 1 至 4 条同日训练。")
    try:
        day = date.fromisoformat(trains[0].get("datestr", ""))
    except (ValueError, TypeError):
        raise ToolError("每条训练必须提供 YYYY-MM-DD 格式的 datestr。") from None
    if any(train.get("datestr") != day.isoformat() for train in trains):
        raise ToolError("每次只可写入同一天的训练，日期格式为 YYYY-MM-DD。")
    today = _today()
    if not _shift_months(today, -6) <= day <= _shift_months(today, 6):
        raise ToolError("只能写入今天前后各 6 个月内的训练。")
    return day


def _validated_set(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict) or not SET_FIELDS.intersection(source):
        raise ToolError("每个训练组必须提供重量、次数、时长或自重之一。")
    if "rpe" in source and (not isinstance(source["rpe"], str) or source["rpe"] not in RPE_VALUES):
        raise ToolError("RPE 必须是从 6 到 10 的半分档字符串，清空用空字符串。")
    if "items" in source:
        raise ToolError("训练超级组不支持嵌套。")
    return source


def _named_movement(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict) or not isinstance(source.get("name"), str) or not source["name"].strip():
        raise ToolError("动作必须提供非空中文 name，使用训记动作库名称。")
    return {key: value for key, value in source.items() if key != "key"}


def _validated_movements(source: Any) -> list[dict[str, Any]]:
    if not isinstance(source, list) or not source or len(source) > 15:
        raise ToolError("每条训练应包含 1 至 15 个动作。")
    movements = []
    movement_count = 0
    for raw in source:
        movement = _named_movement(raw)
        if "moves" in movement:
            raise ToolError("训练超级组请使用 sets[].items，不可传入 App 内部 moves。")
        if "difficulty" in movement and movement["difficulty"] not in ("easy", "normal", "hard"):
            raise ToolError("difficulty 只支持 easy、normal 或 hard。")
        for rest_field in ("restTime", "warn_restTime"):
            if rest_field in movement and (
                type(movement[rest_field]) is not int or not 0 <= movement[rest_field] <= 86400
            ):
                raise ToolError(f"{rest_field} 必须是 0 至 86400 秒的整数。")
        if movement.get("cardio") is True:
            if len(source) != 1 or "sets" in movement:
                raise ToolError("原生有氧日只能包含一个动作，指标放在动作的 metrics 中，不传 sets。")
            movement_count += 1
            movements.append(movement)
            continue
        sets = movement.get("sets")
        if not isinstance(sets, list) or len(sets) > 20:
            raise ToolError("每个普通动作或超级组必须提供 sets，最多 20 组或轮。")
        normalized_sets = []
        largest_round = 1
        for entry in sets:
            if not isinstance(entry, dict) or "items" not in entry:
                normalized_sets.append(_validated_set(entry))
                continue
            items = entry["items"]
            if not isinstance(items, list) or not 1 <= len(items) <= 15:
                raise ToolError("每轮超级组必须包含 1 至 15 个子动作。")
            largest_round = max(largest_round, len(items))
            normalized_items = []
            for raw_item in items:
                item = _named_movement(raw_item)
                if "moves" in item or "sets" in item:
                    raise ToolError("训练超级组子动作必须包含单个 set，不支持嵌套。")
                normalized_items.append({**item, "set": _validated_set(item.get("set"))})
            normalized_sets.append({**entry, "items": normalized_items})
        movement_count += largest_round
        movements.append({**movement, "sets": normalized_sets})
    if movement_count > 15:
        raise ToolError("每条训练最多 15 个动作，超级组按最大单轮子动作数计入。")
    return movements


def _validate_color(color: Any) -> None:
    if not isinstance(color, str) or (color and not re.fullmatch(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", color)):
        raise ToolError("trainColor 必须是 CSS 十六进制颜色，清空用空字符串。")


def _validate_note(train: dict[str, Any]) -> bool:
    _validate_color(train.get("trainColor", ""))
    if "note" not in train:
        return False
    note = train["note"]
    if isinstance(note, str) and note.lstrip().startswith("{"):
        try:
            note = json.loads(note)
        except ValueError:
            pass
    if isinstance(note, dict):
        if len(json.dumps(note, ensure_ascii=False).encode("utf-8")) > 16 * 1024:
            raise ToolError("训练 note 补丁不能超过 16 KB。")
        if "trainColor" in note:
            _validate_color(note["trainColor"])
            if "trainColor" in train and train["trainColor"] != note["trainColor"]:
                raise ToolError("顶层和 note 中的 trainColor 必须一致。")
            return True
    elif not isinstance(note, str) or len(note) > 1000:
        raise ToolError("训练备注必须是至多 1000 字符的文本或 note 补丁对象。")
    return False


def register_tools(server: FastMCP, api: ApiClient) -> None:
    pending_days: set[tuple[str, date]] = set()
    committing_days: set[tuple[str, date]] = set()

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    async def get_training(datestr: date, include_full_data: bool = False) -> Any:
        """Get training for one day. Use full data for heart rate, rest times, RPE and unfinished sets.

        Note: lite mode (include_full_data=false) may not return unfinished trainings due to upstream API behavior.
        Always use include_full_data=true to verify writes.
        """
        seconds = 30 if include_full_data else 15
        return await api.call(
            "training_read",
            {"schema_version": TRAIN_SCHEMA, "datestr": datestr.isoformat(), "include_full_data": include_full_data},
            cache_ttl=seconds,
            rate_scope=f"{datestr}:{include_full_data}",
            rate_seconds=seconds,
        )

    async def training_index(day: date) -> dict[str, dict[str, Any]]:
        current = await get_training(day, include_full_data=True)
        if not isinstance(current, dict) or not isinstance(current.get("trains"), list):
            raise ToolError("训记返回的完整训练格式不正确，已取消更新。")
        return {
            str(train["localid"]): train for train in current["trains"]
            if isinstance(train, dict) and "localid" in train
        }

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True, openWorldHint=True))
    async def upsert_training(ctx: Context, trains: list[dict[str, Any]], client_request_id: str, dry_run: bool = False) -> Any:
        """Create or patch up to four same-day trainings.

        Provide datestr and movements for new records. Use localid for updates and include only changed fields.
        If movements are supplied for an update they replace the entire list, including unfinished sets.
        Use verified Chinese movement names and reuse client_request_id when retrying the same write.

        预演模式。为 true 时返回变更摘要但不实际写入；为 false 时执行真实写入。建议先用 dry_run: true 获取 res.summary，展示给用户确认后，再用 dry_run: false 执行真实操作。
        """
        if not client_request_id.strip():
            raise ToolError("请提供唯一 client_request_id，重试相同写入时保留此值。")
        day = _training_day(trains)
        pending = (api.credential_scope("training_write"), day)
        if pending in pending_days:
            raise ToolError("该日期已有训练写入待确认或提交，请稍后重试。")
        pending_days.add(pending)
        try:
            return await apply_training_update(ctx, trains, day, client_request_id, dry_run)
        finally:
            pending_days.remove(pending)

    async def apply_training_update(
        ctx: Context, trains: list[dict[str, Any]], day: date, client_request_id: str, dry_run: bool = False,
    ) -> Any:
        identifiers = [train.get("localid") for train in trains if "localid" in train]
        if any(type(value) not in (int, str) or not str(value).strip() for value in identifiers):
            raise ToolError("请使用读取结果中的 localid；新建训练时省略该字段。")
        if len(set(map(str, identifiers))) != len(identifiers):
            raise ToolError("同一条训练不能在一次写入里重复出现。")
        originals = await training_index(day) if identifiers else {}
        payload = []
        preview = []
        for patch in trains:
            if patch.keys() - TRAIN_FIELDS:
                raise ToolError("训练只接受 datestr、localid、start、end、title、movements、note 和 trainColor。")
            color_in_note = _validate_note(patch)
            if "localid" in patch:
                original = originals.get(str(patch["localid"]))
                if original is None:
                    raise ToolError("指定 localid 不在该日的训练记录中，已取消更新。")
                merged = {key: original[key] for key in TRAIN_FIELDS if key in original and key != "note"}
                merged.update({key: value for key, value in patch.items() if key != "localid"})
                if color_in_note and "trainColor" not in patch:
                    merged.pop("trainColor", None)
                preview.append({"更新": merged["localid"], "原值": {key: original.get(key) for key in patch}, "新值": patch})
            else:
                merged = patch.copy()
                preview.append({"新建": merged})
            merged["movements"] = _validated_movements(merged.get("movements"))
            payload.append(merged)
        pending = (api.credential_scope("training_write"), day)
        if pending in committing_days:
            raise ToolError("该日期已有训练写入正在提交，请稍后重新核对。")
        committing_days.add(pending)
        try:
            if identifiers:
                await api.wait_for_rate_limit("training_read", f"{day}:True")
                current = await training_index(day)
                if any(current.get(str(identifier)) != originals[str(identifier)] for identifier in identifiers):
                    raise ToolError("确认期间原训练发生变化。请重新读取、提交并确认修改。")
            return await api.call(
                "training_write",
                {"schema_version": TRAIN_SCHEMA, "client_request_id": client_request_id, "dry_run": dry_run,
                 "include_full_data": True, "res": payload},
                rate_scope=day.isoformat(),
                invalidate=("training_read",),
            )
        finally:
            committing_days.remove(pending)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    async def delete_training(datestr: date, localid: int | None = None) -> dict[str, Any]:
        """Delete a training record. Note: the upstream API does not provide deletion functionality.

        Deletion must be performed within the 训记 App. This tool provides guidance on alternatives:
        - To modify an existing training, use upsert_training
        - To clear training movements, use upsert_training with an empty movements array
        """
        try:
            day = date.fromisoformat(datestr.isoformat() if isinstance(datestr, date) else datestr)
        except (ValueError, TypeError, AttributeError):
            raise ToolError("请提供 YYYY-MM-DD 格式的 datestr。")

        return {
            "success": False,
            "message": "上游 API 不提供删除接口。请在训记 App 内手动删除训练记录。",
            "note": "如需修改已有训练，可以使用 upsert_training 工具；如需清空训练内容，可以传入空的 movements 数组。"
        }

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    async def list_official_plans() -> Any:
        """List official PlatformPlan and UniversalPlan instances and their plan_ref values."""
        return await api.call("plan", {"schema_version": PLAN_SCHEMA, "action": "list"}, cache_ttl=15, rate_scope="list")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    async def get_official_plan(
        plan_ref: str, start_date: date | None = None, end_date: date | None = None, include_movements: bool = True,
    ) -> Any:
        """Read the days for a listed plan_ref. Omit dates for the default range or supply a range of at most 92 days."""
        if not re.fullmatch(r"(?:platform|universal):[^:\s]+", plan_ref):
            raise ToolError("请使用列出官方计划时返回的 plan_ref。")
        if (start_date is None) != (end_date is None):
            raise ToolError("请同时提供起止日期，或同时省略以使用默认范围。")
        body = {"schema_version": PLAN_SCHEMA, "action": "get", "plan_ref": plan_ref,
                "include_movements": include_movements}
        if start_date is not None and end_date is not None:
            if not 0 <= (end_date - start_date).days < 92:
                raise ToolError("计划日期需按先后排列，且最多包含 92 天。")
            body.update(start_date=start_date.isoformat(), end_date=end_date.isoformat())
        return await api.call("plan", body, cache_ttl=15, rate_scope=f"get:{plan_ref}")
