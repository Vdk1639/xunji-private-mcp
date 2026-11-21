# AstrBot 与训记 MCP 集成部署指南

本指南提供三种方式帮助您将 AstrBot 连接到训记 MCP 服务器。

---

## 📋 目录

- [方案一：使用 AI Agent 自动部署（推荐）](#方案一使用-ai-agent-自动部署推荐)
- [方案二：手动部署（适合了解 Docker 的用户）](#方案二手动部署)
- [方案三：Docker Compose 集成（适合新部署）](#方案三docker-compose-集成)

---

## 方案一：使用 AI Agent 自动部署（推荐）

### 🤖 给 Claude 或其他 AI Agent 的提示词

将以下内容复制并发送给支持 Docker 操作的 AI Agent（如 Claude、Cursor 等）：

```
我需要将 AstrBot 容器与训记 MCP 服务器连接。请帮我完成以下操作：

## 环境信息
- AstrBot 容器名：astrbot
- 训记 MCP 容器名：xunji-private-mcp
- MCP 服务端口：8765

## 任务清单
1. 检查两个容器是否都在运行
2. 找到 AstrBot 所在的 Docker 网络（通常是 `docker inspect astrbot` 查看）
3. 将 xunji-private-mcp 容器连接到 AstrBot 的网络：
   ```bash
   docker network connect <astrbot-network-name> xunji-private-mcp
   ```
4. 在 AstrBot 的 MCP 配置文件中添加训记 MCP（通常在 `/AstrBot/data/mcp_server.json`）：
   ```json
   {
     "name": "训记mcp",
     "transport": {
       "type": "streamable-http",
       "url": "http://xunji-private-mcp:8765/mcp",
       "headers": {
         "X-Xunji-Train-Key": "xjllm_你的训练密钥",
         "X-Xunji-Food-Key": "xjfood_你的饮食密钥",
         "X-Xunji-Body-Key": "xjbody_你的身体指标密钥",
         "X-Xunji-Template-Key": "xjtpl_你的模板密钥"
       }
     }
   }
   ```
5. 重启 AstrBot 容器：`docker restart astrbot`
6. 验证连接：检查 AstrBot 日志，确认训记 MCP 成功初始化

## 验证标准
日志中应出现类似信息：
- `Connected to MCP server 训记mcp`
- `Tools: [11]` 或列出 11 个工具名称
- 最终显示 `X/X MCP 服务全部成功初始化`

请一步步执行，并在每步后告诉我结果。
```

### 🔑 获取 API 密钥

在发送提示词之前，请先准备好四个 API 密钥：

1. **训练密钥** (`X-Xunji-Train-Key`)
2. **饮食密钥** (`X-Xunji-Food-Key`)
3. **身体指标密钥** (`X-Xunji-Body-Key`)
4. **模板密钥** (`X-Xunji-Template-Key`)

> 💡 **提示**：密钥格式分别为 `xjllm_`、`xjfood_`、`xjbody_`、`xjtpl_` 开头。
> 请从训记官方获取或联系管理员。

---

## 方案二：手动部署

### 前置条件

- AstrBot 和训记 MCP 都已通过 Docker 部署并运行
- 有 SSH 或终端访问权限

### 步骤 1：检查容器状态

```bash
# 确认两个容器都在运行
docker ps | grep -E 'astrbot|xunji-private-mcp'
```

期望看到两行输出，显示两个容器都是 `Up` 状态。

### 步骤 2：查找 AstrBot 网络

```bash
# 查看 AstrBot 连接的网络
docker inspect astrbot --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}'
```

记录输出的网络名称（例如 `qq-ai-bot_astrbot_network`）。

### 步骤 3：连接网络

```bash
# 将 MCP 容器加入 AstrBot 网络
docker network connect <your-astrbot-network-name> xunji-private-mcp
```

将 `<your-astrbot-network-name>` 替换为步骤 2 中查到的网络名。

### 步骤 4：配置 AstrBot

找到 AstrBot 的 MCP 配置文件（通常在数据卷中）：

```bash
# 进入 AstrBot 容器
docker exec -it astrbot /bin/bash

# 查看当前 MCP 配置
cat /AstrBot/data/mcp_server.json
```

编辑该文件，添加训记 MCP 配置：

```json
{
  "mcpServers": {
    "训记mcp": {
      "name": "训记mcp",
      "transport": {
        "type": "streamable-http",
        "url": "http://xunji-private-mcp:8765/mcp",
        "headers": {
          "X-Xunji-Train-Key": "xjllm_你的训练密钥",
          "X-Xunji-Food-Key": "xjfood_你的饮食密钥",
          "X-Xunji-Body-Key": "xjbody_你的身体指标密钥",
          "X-Xunji-Template-Key": "xjtpl_你的模板密钥"
        }
      }
    }
  }
}
```

### 步骤 5：重启 AstrBot

```bash
docker restart astrbot
```

### 步骤 6：验证连接

```bash
# 查看日志
docker logs astrbot --tail 50 | grep -A 2 "训记mcp"
```

期望看到：
```
Connected to MCP server 训记mcp, Tools: [get_training, upsert_training, ...]
```

---

## 方案三：Docker Compose 集成

### 适用场景

- 全新部署 AstrBot 和训记 MCP
- 希望通过一个 `docker-compose.yaml` 管理所有服务

### 配置示例

创建或编辑 `docker-compose.yaml`：

```yaml
services:
  xunji-private-mcp:
    image: xunji-private-mcp:local
    container_name: xunji-private-mcp
    environment:
      XUNJI_HTTP_ALLOWED_HOSTS: xunji-private-mcp,xunji-private-mcp:8765
    expose:
      - "8765"
    networks:
      - astrbot-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=5)\" || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

  astrbot:
    image: soulter/astrbot:latest
    container_name: astrbot
    volumes:
      - ./astrbot-data:/AstrBot/data
    networks:
      - astrbot-network
    depends_on:
      xunji-private-mcp:
        condition: service_healthy
    restart: unless-stopped

networks:
  astrbot-network:
    driver: bridge
```

### 启动服务

```bash
docker compose up -d
```

然后按照方案二的步骤 4-6 配置 AstrBot 的 MCP 连接。

---

## 🔧 故障排查

### 问题 1：AstrBot 日志显示 "Connection refused"

**原因**：两个容器不在同一网络中。

**解决**：
```bash
# 检查网络连接
docker network inspect <astrbot-network-name> | grep xunji-private-mcp

# 如果没有输出，重新连接网络
docker network connect <astrbot-network-name> xunji-private-mcp
```

### 问题 2：日志显示 "Bad Request: Invalid Host header"

**原因**：MCP 服务器的 `ALLOWED_HOSTS` 配置不包含容器名或端口。

**解决**：
```bash
# 检查 MCP 环境变量
docker exec xunji-private-mcp env | grep ALLOWED_HOSTS

# 如果不包含 "xunji-private-mcp:8765"，更新配置
# 编辑 MCP 的 .env 文件或 docker-compose.yaml
# 确保 XUNJI_HTTP_ALLOWED_HOSTS 包含：xunji-private-mcp,xunji-private-mcp:8765

# 重启 MCP
docker restart xunji-private-mcp
```

### 问题 3：日志显示 "Authentication failed" 或 401 错误

**原因**：API 密钥错误或缺失。

**解决**：
1. 检查 AstrBot 的 `mcp_server.json` 中的密钥是否正确
2. 确认密钥格式（`xjllm_`、`xjfood_` 等前缀）
3. 联系管理员获取正确的密钥

### 问题 4：MCP 工具数量不是 11 个

**原因**：某些 API 密钥缺失或无效。

**解决**：
- 训练相关（2 个工具）需要 `X-Xunji-Train-Key`
- 饮食相关（3 个工具）需要 `X-Xunji-Food-Key`
- 身体指标（2 个工具）需要 `X-Xunji-Body-Key`
- 模板管理（2 个工具）需要 `X-Xunji-Template-Key`
- 官方计划（2 个工具）不需要密钥

确保所有四个密钥都已正确配置。

---

## 📚 相关文档

- [Docker 网络配置详解](./DOCKER_NETWORKING.md)
- [容器间通信快速参考](./DOCKER_CONTAINER_NETWORKING.md)
- [训记 MCP API 文档](../README.md)

---

## 💬 获取帮助

如果遇到问题：
1. 查看 [故障排查](#故障排查) 部分
2. 查看完整日志：`docker logs xunji-private-mcp` 和 `docker logs astrbot`
3. 提交 Issue 到 GitHub 仓库
