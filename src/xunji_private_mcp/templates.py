import json
import re
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .exceptions import ToolError
from .upstream import ApiClient, UpstreamError

MAX_TEMPLATES = 14
MAX_MOVEMENTS = 15
MAX_SETS = 20
TEMPLATE_FIELDS = {"name", "color", "movements", "movement", "rules"}
NAME_PATTERN = re.compile(r"[A-Za-z0-9 \u3400-\u4dbf\u4e00-\u9fff]+")


def _name(value: Any, *, folder: bool = False) -> str:
    label = "文件夹名称" if folder else "模板名称"
    if not isinstance(value, str) or not NAME_PATTERN.fullmatch(value) or not value.strip(" "):
        raise ToolError(f"{label}不能为空，且仅允许中文、英文字母、数字和普通空格。")
    value = value.strip(" ")
    if folder and len(value) > 32:
        raise ToolError("文件夹名称不能超过 32 个字符。")
    return value


def _movement_layout(template: dict[str, Any]) -> None:
    is_native = "movement" in template
    if is_native and "movements" in template:
        raise ToolError("模板的 movement 和 movements 只能传其一。")
    movements = template.get("movement" if is_native else "movements")
    if not isinstance(movements, list) or not 1 <= len(movements) <= MAX_MOVEMENTS:
        raise ToolError("每个模板需要 1 至 15 个动作。")
    movement_count = 0
    for movement in movements:
        if not isinstance(movement, dict):
            raise ToolError("模板动作必须是对象。")
        if "moves" in movement or movement.get("superset") is True:
            rounds = movement.get("moves")
            if not is_native or "sets" in movement or not isinstance(rounds, list) or not 1 <= len(rounds) <= MAX_SETS:
                raise ToolError("模板超级组使用原生 movement[].moves，最多 20 轮，外层不提供 sets。")
            for round_items in rounds:
                if not isinstance(round_items, list) or not 1 <= len(round_items) <= MAX_MOVEMENTS:
                    raise ToolError("模板超级组每轮需要 1 至 15 个子动作。")
                if any(
                    not isinstance(item, dict) or "moves" in item or item.get("superset") is True
                    or not isinstance(item.get("sets"), dict) for item in round_items
                ):
                    raise ToolError("模板超级组子动作的 sets 必须是单个组对象，且不能嵌套超级组。")
            movement_count += max(map(len, rounds))
        else:
            if not is_native and (
                "key" in movement or not isinstance(movement.get("name"), str) or not movement["name"].strip()
            ):
                raise ToolError("公开结构的动作应提供训记官方中文 name，不传内部 key。")
            sets = movement.get("sets")
            if not isinstance(sets, list) or len(sets) > MAX_SETS or any(not isinstance(item, dict) for item in sets):
                raise ToolError("模板动作的 sets 必须是对象数组，每个动作最多 20 组。")
            movement_count += 1
    if movement_count > MAX_MOVEMENTS:
        raise ToolError("每个模板最多 15 个动作，超级组按最大单轮子动作数计入。")


def _template_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    templates = snapshot.get("templates", [])
    if isinstance(templates, list) and all(isinstance(item, dict) for item in templates):
        templates = {item.get("template_id", item.get("id")): item for item in templates}
    if not isinstance(templates, dict) or templates.keys() != snapshot["template_versions"].keys():
        raise ToolError("训记返回的模板列表不完整，请重新同步。")
    if any(not isinstance(item, dict) or not isinstance(item.get("data", item), dict) for item in templates.values()):
        raise ToolError("训记返回的模板格式不正确，已取消修改。")
    return {template_id: item.get("data", item) for template_id, item in templates.items()}


def _check_target(entry: dict[str, Any], versions: dict[str, int], affected: set[str]) -> str:
    template_id = entry.get("template_id")
    if not isinstance(template_id, str) or template_id not in versions:
        raise ToolError("只能修改已同步的 Agent 专属文件夹内的模板。")
    if template_id in affected:
        raise ToolError("一次修改中，同一模板只能出现一次。")
    if type(entry.get("base_version")) is not int or entry["base_version"] != versions[template_id]:
        raise ToolError(f"模板版本已变化（当前版本 {versions[template_id]}）。请重新查看内容后再提交修改。")
    affected.add(template_id)
    return template_id


def register_tools(server: FastMCP, api: ApiClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    async def sync_agent_templates() -> Any:
        """Fetch all Agent-folder templates and current versions. This never creates a folder."""
        snapshot = await api.call("template_sync", {})
        if (
            not isinstance(snapshot, dict) or "folder" not in snapshot
            or not isinstance(snapshot.get("template_versions"), dict)
            or any(type(version) is not int for version in snapshot["template_versions"].values())
        ):
            raise ToolError("训记返回的模板同步格式不正确。")
        return snapshot

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True, openWorldHint=True))
    async def mutate_agent_templates(
        ctx: Context,
        mutation_id: str,
        upserts: list[dict[str, Any]] | None = None,
        deletes: list[dict[str, Any]] | None = None,
        folder_update: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> Any:
        """Apply confirmed changes to the single Agent folder.

        First sync the templates. To create, pass stable client_id, name, and public movements with official
        Chinese names. To update, pass template_id, its base_version, and changed name/color/movements or native
        movement/rules. Specified movement lists replace the entire list. A delete uses template_id and
        base_version. To rename the folder, pass folder_update with name and the folder's current base_version.
        Reuse mutation_id for the same change. A new template is allowed to recreate a missing Agent folder.

        预演模式。为 true 时返回变更摘要但不实际写入；为 false 时执行真实写入。建议先用 dry_run: true 获取 res.summary，展示给用户确认后，再用 dry_run: false 执行真实操作。
        """
        upserts = upserts or []
        deletes = deletes or []
        if not mutation_id.strip() or not (upserts or deletes or folder_update):
            raise ToolError("请提供唯一 mutation_id 和至少一条明确的修改。")
        if len(upserts) > MAX_TEMPLATES or len(deletes) > MAX_TEMPLATES:
            raise ToolError("一次最多新增或更新 14 个模板、删除 14 个模板。")
        snapshot = await sync_agent_templates()
        versions = snapshot["template_versions"]
        folder = snapshot["folder"]
        templates = _template_index(snapshot)
        if folder is None and versions:
            raise ToolError("训记返回的 Agent 文件夹状态不一致，已取消修改。")
        if folder is None and (deletes or folder_update or any("template_id" in item for item in upserts)):
            raise ToolError("Agent 文件夹不存在。只有明确新建模板时才可以重建文件夹。")

        affected = set()
        new_clients = set()
        payload: dict[str, Any] = {"mutation_id": mutation_id, "upserts": [], "deletes": []}
        preview: dict[str, Any] = {"新增或更新": [], "删除": []}
        if folder is None:
            preview["创建 Agent 专属文件夹"] = True
        if folder_update is not None:
            if folder_update.keys() != {"name", "base_version"}:
                raise ToolError("文件夹改名只需提供 name 和 base_version。")
            folder_version = folder.get("version") if isinstance(folder, dict) else None
            if type(folder_version) is not int or type(folder_update["base_version"]) is not int or folder_update["base_version"] != folder_version:
                raise ToolError("文件夹版本已变化或不可用。请重新同步并查看文件夹后再改名。")
            name = _name(folder_update["name"], folder=True)
            payload["folder_update"] = {"name": name, "base_version": folder_version}
            preview["文件夹改名"] = {"原名称": folder.get("name"), "新名称": name}

        for entry in deletes:
            if entry.keys() != {"template_id", "base_version"}:
                raise ToolError("删除只需提供同步所得的 template_id 和 base_version。")
            template_id = _check_target(entry, versions, affected)
            payload["deletes"].append(entry)
            preview["删除"].append({"template_id": template_id, **{key: templates[template_id][key] for key in TEMPLATE_FIELDS if key in templates[template_id]}})

        for entry in upserts:
            changes = {key: entry[key] for key in TEMPLATE_FIELDS if key in entry}
            if "movement" in changes and "movements" in changes:
                raise ToolError("模板的 movement 和 movements 只能传其一。")
            if "template_id" in entry:
                if not changes or entry.keys() - (TEMPLATE_FIELDS | {"template_id", "base_version"}):
                    raise ToolError("更新模板须提供 template_id、base_version 及要修改的模板字段。")
                template_id = _check_target(entry, versions, affected)
                current = {key: templates[template_id][key] for key in TEMPLATE_FIELDS if key in templates[template_id]}
                merged = current | changes
                if "movements" in changes:
                    merged.pop("movement", None)
                if "movement" in changes:
                    merged.pop("movements", None)
                identity = {"template_id": template_id, "base_version": versions[template_id]}
                preview["新增或更新"].append({"更新": template_id, "原值": current, "新值": merged})
            else:
                if entry.keys() - (TEMPLATE_FIELDS | {"client_id"}) or "movements" not in changes:
                    raise ToolError("新建模板使用公开 movements 结构，并提供稳定的 client_id。")
                client_id = entry.get("client_id")
                if not isinstance(client_id, str) or not client_id.strip() or client_id in new_clients:
                    raise ToolError("每个新模板须提供非空且在此次修改中唯一的 client_id。")
                new_clients.add(client_id)
                merged = changes
                identity = {"client_id": client_id}
                preview["新增或更新"].append({"新建": merged})
            merged["name"] = _name(merged.get("name"))
            _movement_layout(merged)
            payload["upserts"].append(identity | merged)

        if len(versions) - len(deletes) + len(new_clients) > MAX_TEMPLATES:
            raise ToolError("Agent 文件夹最多保存 14 个模板。请明确选择要替换的模板后再提交。")

        try:
            return await api.call("template_mutate", {**payload, "confirmed": True, "dry_run": dry_run})
        except UpstreamError as error:
            if error.code != "version_conflict":
                raise
            try:
                latest = await sync_agent_templates()
            except ToolError:
                raise ToolError("训记报告模板版本冲突，重新同步失败。请同步后再发起并确认修改。") from None
            revisions = {template_id: latest["template_versions"].get(template_id) for template_id in sorted(affected)}
            if folder_update is not None:
                latest_folder = latest.get("folder")
                revisions["文件夹"] = latest_folder.get("version") if isinstance(latest_folder, dict) else None
            raise ToolError(
                "训记报告版本冲突。已重新同步，修改未提交。请重新查看、提交并确认修改。当前版本："
                + json.dumps(revisions, ensure_ascii=False)
            ) from None
