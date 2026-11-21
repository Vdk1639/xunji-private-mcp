# README 补充 - Docker 容器间通信

本文档补充主 README 中的 Docker 部署章节，专门说明容器间通信场景的配置。

## 快速开始

### 方案选择

| 场景 | 使用配置 | 端点地址 |
|------|---------|----------|
| 宿主机访问（默认） | `compose.yaml` | `http://127.0.0.1:8765/mcp` |
| 容器间通信 | `compose.internal.yaml` | `http://xunji-private-mcp:8765/mcp` |
| 公开部署 | `compose.yaml` + 反向代理 | `https://mcp.example.com/mcp` |

### 容���间通信部署

```bash
# 1. 复制环境变量示例
cp .env.docker-internal .env

# 2. 编辑 .env，设置允许的主机名和来源
#    XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp
#    XUNJI_HTTP_ALLOWED_ORIGINS=http://astrbot:8080

# 3. 启动服务
docker compose -f compose.internal.yaml up -d --build

# 4. 验证健康状态
docker compose -f compose.internal.yaml ps
docker compose -f compose.internal.yaml exec xunji-private-mcp \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765/health').read())"
```

## 与其他容器集成

### 示例：集成 AstrBot

创建统一的 `docker-compose.yml`：

```yaml
services:
  # 训记 MCP 服务
  xunji-private-mcp:
    build: .
    image: xunji-private-mcp:local
    container_name: xunji-private-mcp
    environment:
      XUNJI_HTTP_ALLOWED_HOSTS: xunji-private-mcp
      XUNJI_HTTP_ALLOWED_ORIGINS: http://astrbot:8080
    expose:
      - "8765"
    networks:
      - app-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=5)\" || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

  # AstrBot 服务
  astrbot:
    image: soulter/astrbot:latest
    container_name: astrbot
    ports:
      - "8080:8080"
    networks:
      - app-network
    depends_on:
      xunji-private-mcp:
        condition: service_healthy

networks:
  app-network:
    driver: bridge
```

在 AstrBot 的 MCP 配置中：

```json
{
  "transport": "streamable_http",
  "url": "http://xunji-private-mcp:8765/mcp",
  "headers": {
    "X-Xunji-Train-Key": "<YOUR_TRAIN_KEY>",
    "X-Xunji-Food-Key": "<YOUR_FOOD_KEY>"
  },
  "timeout": 30,
  "sse_read_timeout": 300
}
```

## 网络隔离选项

### 完全内部网络（无外网访问）

```yaml
networks:
  app-network:
    driver: bridge
    internal: true  # 禁止访问外网
```

适用于所有服务都在同一网络内，且不需要访问外部 API 的场景。

**注意**：`internal: true` 会阻止容器访问训记官方 API，导致 MCP 无法正常工作。只有当你使用本地模拟的训记 API 时才应设置此选项。

### 部分隔离（推荐）

```yaml
networks:
  app-network:
    driver: bridge
    internal: false  # 默认值，允许访问外网
```

MCP 服务可以访问训记官方 API，但不暴露到宿主机。

## 浏览器审批配置

容器间通信时，如果需要使用浏览器审批功能，需要配置可从用户浏览器访问的地址：

### 选项 1：通过反向代理（推荐）

```bash
# .env
XUNJI_APPROVAL_BASE_URL=https://mcp.example.com
```

### 选项 2：通过端口映射

```yaml
services:
  xunji-private-mcp:
    # ... 其他配置
    ports:
      - "127.0.0.1:8765:8765"  # 同时映射到宿主机
```

```bash
# .env
XUNJI_APPROVAL_BASE_URL=http://127.0.0.1:8765
```

### 选项 3：不使用浏览器审批

如果客户端支持 MCP 表单确认（如 Claude Code），可以不设置此变量：

```bash
# .env
XUNJI_APPROVAL_BASE_URL=
```

## 故障排查

### 客户端无法连接

```bash
# 检查服务状态
docker compose -f compose.internal.yaml ps

# 检查日志
docker compose -f compose.internal.yaml logs xunji-private-mcp

# 从客户端容器测试连通性
docker compose exec astrbot curl http://xunji-private-mcp:8765/health
```

### DNS 解析失败

确保客户端容器和 MCP 服务在同一 Docker 网络中：

```bash
# 检查网络
docker network ls
docker network inspect <network_name>
```

### Host 验证失败

错误：`Host header validation failed`

解决：在 `.env` 中添加容器服务名：

```bash
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp
```

## 性能调优

### 资源限制

```yaml
services:
  xunji-private-mcp:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```

### 日志管理

```yaml
services:
  xunji-private-mcp:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 相关文档

- [主 README](../README.md) - 完整的安装和配置说明
- [Docker 容器间通信详细指南](DOCKER_NETWORKING.md) - 详细的网络配置和示例
- [训记官方 API 文档](https://www.xunjiapp.cn/) - API 说明和凭据获取
