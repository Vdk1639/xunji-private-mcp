#!/usr/bin/env python3
"""测试 approval 机制修复的脚本"""
import asyncio
from unittest.mock import Mock, AsyncMock
from src.xunji_private_mcp.interaction import approve_write, ToolError
from src.xunji_private_mcp.credentials import REQUEST_KEYS


async def test_no_elicitation_no_browser():
    """测试：客户端不支持 elicitation 且未配置浏览器确认时，应该返回清晰错误"""
    # 模拟 HTTP 模式（REQUEST_KEYS 不为空）
    REQUEST_KEYS.set({"TRAIN": "dummy_key"})

    # 创建模拟的 context
    ctx = Mock()
    ctx.fastmcp = Mock()
    ctx.fastmcp.approvals = None  # 未配置浏览器确认
    ctx.session = Mock()
    ctx.session.client_params = Mock()
    ctx.session.client_params.capabilities = Mock()
    ctx.session.client_params.capabilities.elicitation = None  # 不支持 elicitation

    # 模拟 submit 函数
    submit = AsyncMock(return_value={"success": True})

    # 应该抛出清晰的错误
    try:
        await approve_write(ctx, "training_write", "测试摘要", submit)
        print("❌ 测试失败：应该抛出 ToolError")
        return False
    except ToolError as e:
        error_msg = str(e)
        if "不支持 MCP 表单确认" in error_msg and "XUNJI_APPROVAL_BASE_URL" in error_msg:
            print(f"✅ 测试通过：收到预期的错误消息")
            print(f"   错误内容：{error_msg}")
            return True
        else:
            print(f"❌ 测试失败：错误消息不符合预期")
            print(f"   实际错误：{error_msg}")
            return False
    finally:
        REQUEST_KEYS.set(None)


async def test_with_browser_approval():
    """测试：配置了浏览器确认时，应该返回 approval_url"""
    REQUEST_KEYS.set({"TRAIN": "dummy_key"})

    ctx = Mock()

    # 模拟浏览器确认配置
    browser = Mock()
    browser.stage = Mock(return_value={
        "status": "approval_required",
        "approval_url": "http://127.0.0.1:8765/approve/test123",
        "expires_in_seconds": 300
    })
    ctx.fastmcp = Mock()
    ctx.fastmcp.approvals = browser

    ctx.session = Mock()
    ctx.session.client_params = Mock()
    ctx.session.client_params.capabilities = Mock()
    ctx.session.client_params.capabilities.elicitation = None

    submit = AsyncMock(return_value={"success": True})

    try:
        result = await approve_write(ctx, "training_write", "测试摘要", submit)
        if result.get("status") == "approval_required" and "approval_url" in result:
            print("✅ 测试通过：正确返回 approval_url")
            print(f"   返回内容：{result}")
            return True
        else:
            print(f"❌ 测试失败：返回内容不符合预期")
            print(f"   实际返回：{result}")
            return False
    except Exception as e:
        print(f"❌ 测试失败：抛出异常 {e}")
        return False
    finally:
        REQUEST_KEYS.set(None)


async def main():
    print("=" * 60)
    print("开始测试 approval 机制修复")
    print("=" * 60)
    print()

    test1 = await test_no_elicitation_no_browser()
    print()
    test2 = await test_with_browser_approval()
    print()

    print("=" * 60)
    if test1 and test2:
        print("✅ 所有测试通过")
    else:
        print("❌ 部分测试失败")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
