import json
from datetime import date
from typing import Annotated, Any, Literal
from uuid import uuid4

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .interaction import ToolError, confirm
from .upstream import ApiClient


BodyMetric = Literal[
    "weight",
    "bodyfat",
    "neck",
    "chest",
    "weist",
    "shoulder",
    "bot",
    "arm_left",
    "arm_right",
    "forearm_left",
    "forearm_right",
    "leg_left",
    "leg_right",
    "cav_left",
    "cav_right",
]
RequestId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BodyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datestr: date
    type: BodyMetric
    value: Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]


def register_tools(server: FastMCP, api: ApiClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    async def query_body_metrics(
        start_date: date,
        end_date: date,
        types: Annotated[list[BodyMetric], Field(min_length=1)] | None = None,
        include_latest: bool = True,
        include_records: bool = True,
        limit: Annotated[int, Field(ge=1)] = 500,
        offset: Annotated[int, Field(ge=0)] = 0,
    ) -> Any:
        """Read personal Xunji body metric records. Omit types to include all metrics.

        Use the wire name weist for waist circumference. Use limit and offset to paginate records.
        """
        if start_date > end_date:
            raise ToolError("身体数据查询的开始日期不能晚于结束日期。")
        body = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "include_latest": include_latest,
            "include_records": include_records,
            "limit": limit,
            "offset": offset,
        }
        if types is not None:
            body["types"] = sorted(set(types))
        return await api.call("body_query", body, cache_ttl=15)

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
        )
    )
    async def upsert_body_metrics(
        records: Annotated[list[BodyRecord], Field(min_length=1)],
        ctx: Context,
        client_request_id: RequestId | None = None,
    ) -> Any:
        """Preview and confirm adding or updating body metrics by date and type.

        Use kg for weight, % for bodyfat, and cm for circumference or size. Reuse client_request_id
        if retrying the same request after an uncertain result.
        """
        if len({(record.datestr, record.type) for record in records}) != len(records):
            raise ToolError("每个日期和身体指标组合只能提交一次。")
        if any(record.type == "bodyfat" and record.value > 100 for record in records):
            raise ToolError("体脂率必须在 0% 至 100% 之间。")
        body = {
            "schema_version": "body_open_api_v1",
            "client_request_id": client_request_id or str(uuid4()),
            "records": [record.model_dump(mode="json") for record in records],
        }
        preview = await api.call("body_write", {**body, "dry_run": True})
        if not isinstance(preview, dict) or preview.get("summary") is None:
            raise ToolError("训记未返回身体数据预检摘要，写入已停止。")
        unit_by_type = {"weight": "kg", "bodyfat": "%"}
        changes = "\n".join(
            f"{record.datestr} · {record.type} · {record.value} {unit_by_type.get(record.type, 'cm')}"
            for record in records
        )
        summary = json.dumps(preview["summary"], ensure_ascii=False, indent=2)
        await confirm(ctx, f"确认新增或更新以下身体指标：\n{changes}\n训记预检摘要：\n{summary}")
        await api.wait_for_rate_limit("body_write")
        return await api.call(
            "body_write",
            {**body, "dry_run": False, "confirmed": True},
            invalidate=("body_query",),
        )
