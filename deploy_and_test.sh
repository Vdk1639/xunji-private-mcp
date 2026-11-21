#!/bin/bash
# 训记 MCP v0.3.4 部署和测试脚本
# 在树莓派上运行

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

COMPOSE_DIR="/opt/dpanel/data/compose/xunji-mcp"
MCP_URL="http://xunji-private-mcp:8765/mcp"

echo "=========================================="
echo "训记 MCP v0.3.4 部署和测试"
echo "=========================================="
echo ""

# 步骤 1: 备份当前配置（如果还没备份）
echo -e "${BLUE}步骤 1: 检查配置备份${NC}"
cd "$COMPOSE_DIR"
if [ ! -f "docker-compose.yaml.backup-v0.3.3" ]; then
    cp docker-compose.yaml docker-compose.yaml.backup-v0.3.3
    echo -e "${GREEN}✓ 配置已备份${NC}"
else
    echo -e "${YELLOW}配置备份已存在，跳过${NC}"
fi
echo ""

# 步骤 2: 检查新镜像是否已导入
echo -e "${BLUE}步骤 2: 检查新镜像${NC}"
if docker images | grep -q "xunji-private-mcp.*0.3.4"; then
    echo -e "${GREEN}✓ v0.3.4 镜像已存在${NC}"
    docker images xunji-private-mcp:0.3.4
else
    echo -e "${RED}✗ v0.3.4 镜像未找到，请先导入镜像${NC}"
    echo "导入命令："
    echo "  gunzip -c /tmp/xunji-private-mcp-0.3.4.tar.gz | docker load"
    exit 1
fi
echo ""

# 步骤 3: 更新镜像标签
echo -e "${BLUE}步骤 3: 更新镜像标签${NC}"
docker tag xunji-private-mcp:0.3.4 ghcr.io/vdk1639/xunji-private-mcp:v0.3.4
docker tag xunji-private-mcp:0.3.4 ghcr.io/vdk1639/xunji-private-mcp:latest
echo -e "${GREEN}✓ 镜像标签已更新${NC}"
echo ""

# 步骤 4: 检查是否需要配置 XUNJI_APPROVAL_BASE_URL
echo -e "${BLUE}步骤 4: 检查环境变量配置${NC}"
if grep -q "XUNJI_APPROVAL_BASE_URL" docker-compose.yaml; then
    APPROVAL_URL=$(grep "XUNJI_APPROVAL_BASE_URL" docker-compose.yaml | cut -d: -f2- | tr -d ' "')
    if [ -z "$APPROVAL_URL" ]; then
        echo -e "${YELLOW}⚠ XUNJI_APPROVAL_BASE_URL 未设置（写入操作将返回清晰错误）${NC}"
        echo "如需启用浏览器确认，请在 docker-compose.yaml 中设置："
        echo "  XUNJI_APPROVAL_BASE_URL: http://192.168.1.10:8765"
    else
        echo -e "${GREEN}✓ XUNJI_APPROVAL_BASE_URL 已配置: $APPROVAL_URL${NC}"
    fi
else
    echo -e "${YELLOW}⚠ XUNJI_APPROVAL_BASE_URL 未在配置文件中${NC}"
fi
echo ""

# 步骤 5: 重启服务
echo -e "${BLUE}步骤 5: 重启 MCP 服务${NC}"
docker compose down
docker compose up -d
echo -e "${GREEN}✓ 服务已重启${NC}"
echo ""

# 等待服务就绪
echo -e "${BLUE}等待服务健康检查...${NC}"
for i in {1..10}; do
    if docker ps --filter "name=xunji-private-mcp" --filter "health=healthy" | grep -q xunji-private-mcp; then
        echo -e "${GREEN}✓ 服务已就绪${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${RED}✗ 服务健康检查超时${NC}"
        docker logs xunji-private-mcp --tail 20
        exit 1
    fi
    sleep 3
done
echo ""

# 步骤 6: 验证版本
echo -e "${BLUE}步骤 6: 验证容器版本${NC}"
CONTAINER_IMAGE=$(docker inspect xunji-private-mcp --format '{{.Config.Image}}')
echo "运行镜像: $CONTAINER_IMAGE"
docker exec xunji-private-mcp python -c "import importlib.metadata; print(f'包版本: {importlib.metadata.version(\"xunji-private-mcp\")}')" || echo "无法获取包版本"
echo ""

# 步骤 7: 功能测试
echo "=========================================="
echo "功能测试"
echo "=========================================="
echo ""

# 读取 API key（从环境变量或提示用户）
if [ -z "$XUNJI_TRAIN_KEY" ]; then
    echo -e "${YELLOW}请输入 XUNJI_TRAIN_KEY:${NC}"
    read -r XUNJI_TRAIN_KEY
fi

# 测试 7.1: 工具列表
echo -e "${YELLOW}测试 7.1: 检查工具列表${NC}"
TOOLS_RESPONSE=$(docker exec astrbot curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "X-Xunji-Train-Key: $XUNJI_TRAIN_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')

TOOL_COUNT=$(echo "$TOOLS_RESPONSE" | jq -r '.result.tools | length')
echo "工具数量: $TOOL_COUNT"

if [ "$TOOL_COUNT" -ge 12 ]; then
    echo -e "${GREEN}✓ 工具数量正常（≥12）${NC}"
else
    echo -e "${RED}✗ 工具数量异常（预期 ≥12，实际 $TOOL_COUNT）${NC}"
fi

if echo "$TOOLS_RESPONSE" | jq -e '.result.tools[] | select(.name=="delete_training")' > /dev/null; then
    echo -e "${GREEN}✓ delete_training 工具已添加${NC}"
else
    echo -e "${RED}✗ delete_training 工具未找到${NC}"
fi
echo ""

# 测试 7.2: 读取训练
echo -e "${YELLOW}测试 7.2: 读取训练记录${NC}"
TEST_DATE="2026-11-21"
READ_RESPONSE=$(docker exec astrbot curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "X-Xunji-Train-Key: $XUNJI_TRAIN_KEY" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"get_training\",\"arguments\":{\"datestr\":\"$TEST_DATE\",\"include_full_data\":false}}}")

if echo "$READ_RESPONSE" | jq -e '.result' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 读取训练成功${NC}"
    TRAIN_COUNT=$(echo "$READ_RESPONSE" | jq -r '.result.trains | length')
    echo "训练记录数: $TRAIN_COUNT"
else
    echo -e "${RED}✗ 读取失败${NC}"
    echo "$READ_RESPONSE" | jq -C '.'
fi
echo ""

# 测试 7.3: delete_training
echo -e "${YELLOW}测试 7.3: 测试 delete_training${NC}"
DELETE_RESPONSE=$(docker exec astrbot curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "X-Xunji-Train-Key: $XUNJI_TRAIN_KEY" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"delete_training","arguments":{"datestr":"2026-11-21","localid":1795203247936001,"client_request_id":"test-del-001"}}}')

if echo "$DELETE_RESPONSE" | jq -e '.error.message' | grep -q "官方 API 不提供"; then
    echo -e "${GREEN}✓ delete_training 返回预期消息${NC}"
    echo "消息: $(echo "$DELETE_RESPONSE" | jq -r '.error.message' | head -1)"
else
    echo -e "${YELLOW}⚠ 返回内容需检查${NC}"
    echo "$DELETE_RESPONSE" | jq -C '.'
fi
echo ""

# 测试 7.4: 写入测试（验证 approval 机制）
echo -e "${YELLOW}测试 7.4: 测试写入确认机制${NC}"
UPSERT_RESPONSE=$(docker exec astrbot curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "X-Xunji-Train-Key: $XUNJI_TRAIN_KEY" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"upsert_training","arguments":{"trains":[{"datestr":"2026-11-22","title":"测试","start":1732233600000,"end":1732237200000,"movements":[{"name":"杠铃卧推","sets":[{"weight":"60","unit":"kg","reps":"10","done":true}]}]}],"client_request_id":"test-001"}}}')

if echo "$UPSERT_RESPONSE" | jq -e '.result.approval_url' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 返回 approval_url${NC}"
    echo "URL: $(echo "$UPSERT_RESPONSE" | jq -r '.result.approval_url')"
elif echo "$UPSERT_RESPONSE" | jq -e '.error.message' | grep -q "不支持 MCP 表单确认"; then
    echo -e "${GREEN}✓ 返回清晰错误提示（未配置浏览器确认）${NC}"
    echo "消息: $(echo "$UPSERT_RESPONSE" | jq -r '.error.message' | head -1)"
else
    echo -e "${YELLOW}⚠ 响应需要检查${NC}"
    echo "$UPSERT_RESPONSE" | jq -C '.'
fi
echo ""

echo "=========================================="
echo "部署和测试完成"
echo "=========================================="
echo ""
echo -e "${GREEN}后续步骤：${NC}"
echo "1. 如需启用浏览器确认，编辑 docker-compose.yaml 添加："
echo "   XUNJI_APPROVAL_BASE_URL: http://192.168.1.10:8765"
echo "2. 在 AstrBot 中测试对话调用"
echo "3. 验证通过后推送镜像到 GitHub"
