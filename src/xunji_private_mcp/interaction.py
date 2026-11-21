import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from .credentials import REQUEST_KEYS


class WriteApproval(BaseModel):
    approve: bool = Field(description="只有同意按所示内容写入训记时才选是。")


async def confirm(ctx: Context, summary: str) -> None:
    try:
        async with asyncio.timeout(120):
            result = await ctx.elicit(
                message=f"请确认以下训记变更：\n{summary}",
                schema=WriteApproval,
            )
    except TimeoutError:
        raise ToolError("等待用户确认超时，未写入训记。") from None
    except Exception:
        raise ToolError("客户端无法完成 MCP 用户确认，未写入训记。") from None

    if result.action != "accept" or result.data.approve is not True:
        raise ToolError("用户未批准此次变更，未写入训记。")


async def approve_write(
    ctx: Context, route: str, summary: str, submit: Callable[[], Awaitable[Any]],
) -> Any:
    if REQUEST_KEYS.get() is not None:
        browser = getattr(ctx.fastmcp, "approvals", None)
        if browser is not None:
            client = ctx.session.client_params
            capability = client.capabilities.elicitation if client else None
            if capability is None or capability.form is None:
                return browser.stage(route, summary, submit)
    await confirm(ctx, summary)
    return await submit()
