import asyncio

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field


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
