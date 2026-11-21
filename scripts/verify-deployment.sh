#!/bin/bash
# 快速部署验证脚本

set -e

echo "=========================================="
echo "xunji-private-mcp v0.3.0 部署验证"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1"
        exit 1
    fi
}

info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# 1. 检查 Docker
echo "1. 检查 Docker 环境"
docker --version > /dev/null 2>&1
check "Docker 已安装"

docker compose version > /dev/null 2>&1
check "Docker Compose 已安装"

# 2. 检查配置文件
echo ""
echo "2. 检查配置文件"
[ -f "compose.production.yaml" ]
check "compose.production.yaml 存在"

[ -f "compose.internal.yaml" ]
check "compose.internal.yaml 存在"

[ -f ".env.example" ]
check ".env.example 存在"

# 3. 检查文档
echo ""
echo "3. 检查文档"
[ -f "docs/DEPLOYMENT_CHECKLIST.md" ]
check "部署检查清单存在"

[ -f "docs/ASTRBOT_INTEGRATION.md" ]
check "AstrBot 集成文档存在"

[ -f "docs/REVERSE_PROXY.md" ]
check "反向代理文档存在"

# 4. 构建镜像
echo ""
echo "4. 构建 Docker 镜像"
info "开始构建..."
docker compose -f compose.production.yaml build --quiet
check "镜像构建成功"

# 5. 创建临时环境变量
echo ""
echo "5. 创建测试环境配置"
cat > .env.test << EOF
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp
XUNJI_HTTP_ALLOWED_ORIGINS=
XUNJI_APPROVAL_BASE_URL=http://127.0.0.1:8765
EOF
check "测试环境变量已创建"

# 6. 启动服务（使用测试环境）
echo ""
echo "6. 启动服务"
info "使用 compose.production.yaml 启动..."
docker compose -f compose.production.yaml --env-file .env.test up -d
check "服务启动成功"

# 等待服务就绪
echo ""
echo "7. 等待服务就绪"
info "等待健康检查..."
sleep 5

# 检查容器状态
CONTAINER_STATUS=$(docker inspect -f '{{.State.Health.Status}}' xunji-private-mcp 2>/dev/null || echo "unknown")
if [ "$CONTAINER_STATUS" = "healthy" ]; then
    check "容器健康状态正常"
elif [ "$CONTAINER_STATUS" = "starting" ]; then
    info "容器正在启动，再等待 10 秒..."
    sleep 10
    CONTAINER_STATUS=$(docker inspect -f '{{.State.Health.Status}}' xunji-private-mcp)
    [ "$CONTAINER_STATUS" = "healthy" ]
    check "容器健康状态正常"
else
    echo -e "${RED}✗${NC} 容器状态异常: $CONTAINER_STATUS"
    docker compose -f compose.production.yaml logs xunji-private-mcp
    docker compose -f compose.production.yaml down
    rm .env.test
    exit 1
fi

# 8. 测试健康检查端点
echo ""
echo "8. 测试健康检查端点"
HEALTH_RESPONSE=$(docker compose -f compose.production.yaml exec -T xunji-private-mcp \
    python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=5).read().decode())" 2>/dev/null)

if [ "$HEALTH_RESPONSE" = "OK" ]; then
    check "健康检查端点正常"
else
    echo -e "${RED}✗${NC} 健康检查端点返回异常: $HEALTH_RESPONSE"
    docker compose -f compose.production.yaml down
    rm .env.test
    exit 1
fi

# 9. 测试容器间通信
echo ""
echo "9. 测试容器间通信（DNS 解析）"
docker run --rm --network mcp-internal alpine:latest \
    wget -q -O- http://xunji-private-mcp:8765/health > /dev/null 2>&1
check "容器间网络通信正常"

# 10. 清理
echo ""
echo "10. 清理测试环境"
docker compose -f compose.production.yaml down > /dev/null 2>&1
check "服务已停止"

rm .env.test
check "测试配置已删除"

# 完成
echo ""
echo "=========================================="
echo -e "${GREEN}✓ 所有验证通过！${NC}"
echo "=========================================="
echo ""
echo "部署建议："
echo "1. 复制 .env.example 为 .env 并配置环境变量"
echo "2. 使用 compose.production.yaml 部署生产环境"
echo "3. 参考 docs/ 目录配置 AstrBot 和反向代理"
echo ""
echo "快速启动："
echo "  docker compose -f compose.production.yaml up -d --build"
echo ""
echo "查看文档："
echo "  cat docs/README.md"
echo ""
