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
    # HTTP 模式检测
    if REQUEST_KEYS.get() is not None:
        browser = getattr(ctx.fastmcp, "approvals", None)
        client = ctx.session.client_params
        capability = client.capabilities.elicitation if client else None

        # 如果客户端不支持 form elicitation
        if capability is None or capability.form is None:
            # 如果浏览器确认可用，使用浏览器确认
            if browser is not None:
                return browser.stage(route, summary, submit)
            # 否则返回明确错误，而不是尝试 elicit（会导致卡死或超时）
            raise ToolError(
                "此客户端不支持 MCP 表单确认，且未配置浏览器确认。"
                "请在服务端设置 XUNJI_APPROVAL_BASE_URL 环境变量以启用浏览器确认，"
                "或使用支持 MCP elicitation 的客户端。"
            )

    # Stdio 模式或客户端支持 elicitation，使用 MCP 原生确认
    await confirm(ctx, summary)
    return await submit()
