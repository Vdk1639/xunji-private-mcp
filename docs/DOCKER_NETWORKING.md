# Docker 容器间通信部署指南

本文档说明如何将 xunji-private-mcp 部署为 Docker 服务，供其他容器通过内部网络访问。

## 部署方案概览

### 方案一：宿主机访问（默认 compose.yaml）
- MCP 服务端口映射到宿主机 `127.0.0.1:8765`
- 适用于本地开发、宿主机上的客户端访问
- 客户端连接地址：`http://127.0.0.1:8765/mcp`

### 方案二：容器间通信（compose.internal.yaml）
- MCP 服务仅在 Docker 内部网络暴露
- 适用于多容器编排部署（如 AstrBot、其他 AI 客户端）
- 客户端连接地址：`http://xunji-private-mcp:8765/mcp`
- 更安全，服务不暴露到宿主机

## 快速开始

### 1. 宿主机访问部署

```bash
# 使用默认 compose.yaml
docker compose up -d --build

# 验证服务运行
curl http://127.0.0.1:8765/health
# 应返回: OK

# 查看日志
docker compose logs -f xunji-private-mcp
```

客户端配置示例（AstrBot Streamable HTTP）：
```json
{
  "transport": "streamable_http",
  "url": "http://127.0.0.1:8765/mcp",
  "headers": {
    "X-Xunji-Train-Key": "<YOUR_TRAIN_KEY>"
  },
  "timeout": 30,
  "sse_read_timeout": 300
}
```

### 2. 容器间通信部署

```bash
# 使用内部网络配置
docker compose -f compose.internal.yaml up -d --build

# 从容器内验证（需要在同一网络的容器中执行）
# docker compose -f compose.internal.yaml exec xunji-private-mcp wget -O- http://127.0.0.1:8765/health
```

客户端容器配置示例（同一 Compose 文件中的其他服务）：

```yaml
services:
  astrbot:
    image: soulter/astrbot:latest
    environment:
      # 通过服务名访问
      MCP_URL: http://xunji-private-mcp:8765/mcp
    networks:
      - mcp-internal
    depends_on:
      xunji-private-mcp:
        condition: service_healthy
```

### 3. 混合部署（调试用）

如果需要容器间通信，同时宿主机也能访问（用于调试），修改 `compose.internal.yaml`：

```yaml
services:
  xunji-private-mcp:
    # ... 其他配置保持不变
    ports:
      - "127.0.0.1:8765:8765"  # 取消注释这两行
    expose:
      - "8765"
```

## 环境变量配置

### .env 文件示例

**本地开发（宿主机访问）**：
```bash
# .env
XUNJI_HTTP_ALLOWED_HOSTS=
XUNJI_HTTP_ALLOWED_ORIGINS=
XUNJI_APPROVAL_BASE_URL=http://127.0.0.1:8765
```

**容器间通信**（参考 `.env.docker-internal`）：
```bash
# .env
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp
XUNJI_HTTP_ALLOWED_ORIGINS=http://astrbot:8080
XUNJI_APPROVAL_BASE_URL=
```

**公开部署（HTTPS 反向代理）**：
```bash
# .env
XUNJI_HTTP_ALLOWED_HOSTS=mcp.example.com
XUNJI_HTTP_ALLOWED_ORIGINS=https://chat.example.com
XUNJI_APPROVAL_BASE_URL=https://mcp.example.com
```

### 环境变量说明

| 变量 | 说明 | 示例 |
|------|------|------|
| `XUNJI_HTTP_ALLOWED_HOSTS` | 允许的主机名（逗号分隔），用于 DNS 重绑定保护。使用 `*` 禁用保护（不推荐用于生产） | `xunji-private-mcp,mcp.example.com` 或 `*` |
| `XUNJI_HTTP_ALLOWED_ORIGINS` | 允许的跨域来源（逗号分隔） | `http://astrbot:8080` |
| `XUNJI_APPROVAL_BASE_URL` | 浏览器审批确认页的基础地址 | `http://127.0.0.1:8765` |

## 客户端凭据配置

MCP 服务支持两种凭据传递方式：

### 1. 通用 Bearer Token
```bash
Authorization: Bearer <YOUR_XUNJI_KEY>
```
- 会列出所有工具
- 由训记后端验证凭据范围

### 2. 专用业务请求头（推荐）
```bash
X-Xunji-Train-Key: <TRAIN_KEY>
X-Xunji-Food-Key: <FOOD_KEY>
X-Xunji-Body-Key: <BODY_KEY>
X-Xunji-Agent-Template-Key: <TEMPLATE_KEY>
```
- 只列出已配置 Key 对应的工具
- 按业务范围精确控制功能

客户端配置示例（Claude Code）：
```bash
claude mcp add --scope user --transport http \
  --header "X-Xunji-Train-Key: <TRAIN_KEY>" \
  --header "X-Xunji-Food-Key: <FOOD_KEY>" \
  xunji-private-mcp http://xunji-private-mcp:8765/mcp
```

## 健康检查

服务提供 `/health` 端点用于健康检查：

```bash
# 返回 200 OK
curl http://xunji-private-mcp:8765/health
```

Docker Compose 已配置自动健康检查：
- 检查间隔：30 秒
- 超时时间：10 秒
- 重试次数：3 次
- 启动等待：10 秒

## 网络拓扑

### 容器间通信网络图

```
┌─────────────────────────────────────────┐
│  Docker 内部网络 (mcp-internal)          │
│                                         │
│  ┌──────────────────┐                  │
│  │  xunji-private-  │                  │
│  │  mcp:8765        │                  │
│  │  /mcp            │◄─────┐           │
│  │  /health         │      │           │
│  └──────────────────┘      │           │
│                            │           │
│  ┌──────────────────┐      │           │
│  │  astrbot:8080    │──────┘           │
│  │  (MCP 客户端)     │                  │
│  └──────────────────┘                  │
│                                         │
│  ┌──────────────────┐                  │
│  │  其他服务        │──────┐            │
│  └──────────────────┘      │            │
│                            │            │
└────────────────────────────┼────────────┘
                             │
                             ▼
                    (可选) 宿主机 127.0.0.1:8765
```

## 安全建议

### 容器间通信场景
1. **不暴露到宿主机**：使用 `expose` 而非 `ports`
2. **内部网络隔离**：设置 `internal: true`（如不需要外网）
3. **最小权限**：保持 `read_only: true` 和 `cap_drop: [ALL]`
4. **凭据分离**：不同服务使用独立的训记 Key

### 公开部署场景
1. **HTTPS 终止**：使用反向代理（Nginx、Caddy）
2. **访问控制**：配置 `XUNJI_HTTP_ALLOWED_HOSTS` 和 `ALLOWED_ORIGINS`
3. **速率限制**：在反向代理层实施
4. **日志隐私**：关闭 `/mcp` 和 `/approve/` 的请求头日志

## 故障排查

### 无法连接到 MCP 服务

```bash
# 检查服务状态
docker compose ps

# 检查服务日志
docker compose logs xunji-private-mcp

# 检查网络连通性（从客户端容器）
docker compose exec astrbot curl http://xunji-private-mcp:8765/health
```

### DNS 重绑定保护错误

错误信息：`Host header validation failed`

解决方法：
```bash
# 在 .env 中添加容器服务名
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp
```

### 客户端无法列出工具

检查凭据配置：
```bash
# 测试通用 Bearer
curl -H "Authorization: Bearer <YOUR_KEY>" \
  http://xunji-private-mcp:8765/mcp

# 测试专用请求头
curl -H "X-Xunji-Train-Key: <YOUR_KEY>" \
  http://xunji-private-mcp:8765/mcp
```

## 性能优化

### 会话保持
- 使用一个 HTTP 服务实例维持 MCP 会话
- 避免频繁重启容器导致会话丢失

### 资源限制
在 `compose.yaml` 中添加：
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

### 日志轮转
```yaml
services:
  xunji-private-mcp:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 参考配置文件

- `compose.yaml` - 默认配置（宿主机访问）
- `compose.internal.yaml` - 容器间通信配置
- `.env.example` - 环境变量模板
- `.env.docker-internal` - 容器间通信环境变量示例
