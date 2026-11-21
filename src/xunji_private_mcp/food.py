import json
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import uuid4

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .exceptions import ToolError
from .upstream import ApiClient


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Quantity = Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]
Nutrient = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]


class FoodUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit: Text
    count: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    gram: Quantity


class Nutrition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cal: Nutrient
    protein: Nutrient
    fat: Nutrient
    carb: Nutrient
    foodpic: str | None = None
    foodUnit: list[FoodUnit] | None = None


class FoodRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    meal_type: Text
    name: Text
    amount: Quantity
    unit: Text
    uniquekey: Text
    ntr: Nutrition
    units: list[FoodUnit] | None = None
    id: Annotated[int, Field(gt=0, strict=True)] | Text | None = None


def shift_months(day: date, months: int) -> date:
    year, month_index = divmod(day.year * 12 + day.month - 1 + months, 12)
    month = month_index + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def register_tools(server: FastMCP, api: ApiClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    async def query_food_records(
        start_date: date, end_date: date, include_detail: bool = True
    ) -> Any:
        """Read the requested inclusive date range of Xunji food records."""
        today = datetime.now(timezone(timedelta(hours=8))).date()
        earliest, latest = shift_months(today, -12), shift_months(today, 3)
        if not earliest <= start_date <= end_date <= latest:
            raise ToolError(f"饮食查询范围须按日期升序，且在 {earliest} 至 {latest} 之间。")
        return await api.call(
            "food_query",
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "include_detail": include_detail,
            },
            cache_ttl=15,
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    async def search_official_food(
        keyword: Text, limit: Annotated[int, Field(ge=1)] = 8
    ) -> Any:
        """Search Xunji's official foods. Prefer foods over the compact d array in the result.

        Each d row is [id, name, cal, carb, fat, protein, foodpic, uniquekey, units].
        Nutrition values are per 100 g. Preserve uniquekey, ntr and units when recording a match.
        """
        return await api.call("food_search", {"keyword": keyword, "limit": limit}, cache_ttl=15)

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True
        )
    )
    async def upsert_food_records(
        foods: Annotated[list[FoodRecord], Field(min_length=1)],
        ctx: Context,
        client_request_id: Text | None = None,
    ) -> Any:
        """Add or update food records. Supply the record id for updates.

        Obtain uniquekey, per-100g ntr and any units from official search or the saved custom food.
        Ask the user to resolve uncertain food matches, meal types, amounts or units.
        Reuse client_request_id if retrying the same request after an uncertain result.
        """
        records = [food.model_dump(mode="json", exclude_none=True) for food in foods]
        request_id = client_request_id or str(uuid4())
        return await api.call(
            "food_write", {"client_request_id": request_id, "dry_run": False, "foods": records},
            invalidate=("food_query",),
        )

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True
        )
    )
    async def upsert_custom_food(
        name: Text,
        ntr: Nutrition,
        nutrition_source: Text,
        ctx: Context,
        units: list[FoodUnit] | None = None,
        uniquekey: Text | None = None,
        client_request_id: Text | None = None,
    ) -> Any:
        """Save a custom food. Use a custom food when official search
        has no suitable match or the user requests one. For updates, supply its existing uniquekey.

        Provide a real nutrition source and known kcal, protein, fat and carbohydrate per 100 g.
        The source is shown to the user. Omit portion units for gram-based tracking.
        Use food from the result when recording that food.
        """
        if units is not None and ntr.foodUnit is not None and units != ntr.foodUnit:
            raise ToolError("units 与 ntr.foodUnit 必须一致。")
        portion_units = [
            unit.model_dump(mode="json") for unit in (units if units is not None else ntr.foodUnit or [])
        ]
        nutrition = ntr.model_dump(mode="json", exclude_none=True)
        nutrition["foodUnit"] = portion_units
        food = {"name": name, "ntr": nutrition, "units": portion_units}
        if uniquekey is not None:
            food["uniquekey"] = uniquekey
        summary = json.dumps(
            {"营养来源": nutrition_source, "食物（营养按每 100 g）": food},
            ensure_ascii=False,
            indent=2,
        )
        request_id = client_request_id or str(uuid4())
        return await api.call(
            "food_custom", {"client_request_id": request_id, "dry_run": False, "food": food},
        )
