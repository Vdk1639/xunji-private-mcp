#!/bin/bash
# 训记 MCP v0.3.4 功能测试脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

MCP_URL="http://xunji-private-mcp:8765/mcp"
TEST_DATE="2026-11-22"
TRAIN_KEY="${XUNJI_TRAIN_KEY}"

if [ -z "$TRAIN_KEY" ]; then
    echo -e "${RED}错误：请设置 XUNJI_TRAIN_KEY 环境变量${NC}"
    exit 1
fi

echo "=========================================="
echo "训记 MCP v0.3.4 功能测试"
echo "=========================================="
echo ""

# 测试 1: 检查工具列表
echo -e "${YELLOW}测试 1: 检查工具列表（应包含 12 个工具）${NC}"
TOOLS_RESPONSE=$(docker exec astrbot curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "X-Xunji-Train-Key: $TRAIN_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')

TOOL_COUNT=$(echo "$TOOLS_RESPONSE" | jq -r '.result.tools | length')
echo "工具数量: $TOOL_COUNT"

if echo "$TOOLS_RESPONSE" | jq -e '.result.tools[] | select(.name=="delete_training")' > /dev/null; then
    echo -e "${GREEN}✓ delete_training 工具已添加${NC}"
else
    echo -e "${RED}✗ delete_training 工具未找到${NC}"
fi

echo ""

# 测试 2: 读取训练记录（轻量模式）
echo -e "${YELLOW}测试 2: 读取训练记录（轻量模式）${NC}"
READ_RESPONSE=$(docker exec astrbot curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "X-Xunji-Train-Key: $TRAIN_KEY" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"get_training\",\"arguments\":{\"datestr\":\"$TEST_DATE\",\"include_full_data\":false}}}")

if echo "$READ_RESPONSE" | jq -e '.result' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 读取训练记录成功${NC}"
    echo "$READ_RESPONSE" | jq -r '.result' | head -5
else
    echo -e "${RED}✗ 读取失败${NC}"
    echo "$READ_RESPONSE" | jq '.'
fi

echo ""

# 测试 3: 测试 delete_training（应返回清晰说明）
echo -e "${YELLOW}测试 3: 测试 delete_training 工具${NC}"
DELETE_RESPONSE=$(docker exec astrbot curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "X-Xunji-Train-Key: $TRAIN_KEY" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"delete_training","arguments":{"datestr":"2026-11-21","localid":1795203247936001,"client_request_id":"test-del-001"}}}')

if echo "$DELETE_RESPONSE" | jq -e '.error.message' | grep -q "官方 API 不提供.*删除接口"; then
    echo -e "${GREEN}✓ delete_training 返回预期的说明消息${NC}"
    echo "错误消息："
    echo "$DELETE_RESPONSE" | jq -r '.error.message'
else
    echo -e "${RED}✗ 返回内容不符合预期${NC}"
    echo "$DELETE_RESPONSE" | jq '.'
fi

echo ""

# 测试 4: 测试 upsert_training（验证 approval 机制）
echo -e "${YELLOW}测试 4: 测试写入训练（验证 approval 机制）${NC}"
UPSERT_RESPONSE=$(docker exec astrbot curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "X-Xunji-Train-Key: $TRAIN_KEY" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"upsert_training\",\"arguments\":{\"trains\":[{\"datestr\":\"$TEST_DATE\",\"title\":\"测试训练\",\"start\":1732233600000,\"end\":1732237200000,\"movements\":[{\"name\":\"杠铃卧推\",\"sets\":[{\"weight\":\"60\",\"unit\":\"kg\",\"reps\":\"10\",\"done\":true}]}]}],\"client_request_id\":\"test-upsert-001\"}}}")

if echo "$UPSERT_RESPONSE" | jq -e '.result.approval_url' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 返回 approval_url（浏览器确认已配置）${NC}"
    echo "Approval URL: $(echo "$UPSERT_RESPONSE" | jq -r '.result.approval_url')"
elif echo "$UPSERT_RESPONSE" | jq -e '.error.message' | grep -q "不支持 MCP 表单确认"; then
    echo -e "${GREEN}✓ 返回清晰错误（未配置浏览器确认）${NC}"
    echo "错误消息："
    echo "$UPSERT_RESPONSE" | jq -r '.error.message'
else
    echo -e "${YELLOW}⚠ 返回内容需要进一步检查${NC}"
    echo "$UPSERT_RESPONSE" | jq '.'
fi

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
