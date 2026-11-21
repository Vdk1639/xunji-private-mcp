# AstrBot 集成指南

本文档说明如何将已部署的 AstrBot 容器与 xunji-private-mcp 集成。

## 前置条件

- AstrBot 容器已运行
- 拥有训记账号的 API Key

## 部署方案

### 方案 A：连接到 AstrBot 现有网络（推荐）

如果你的 AstrBot 已经在运行，这是最简单的方式。

#### 1. 查看 AstrBot 的网络

```bash
# 查看 AstrBot 容器信息
docker inspect astrbot | grep -A 10 Networks

# 或者
docker inspect astrbot --format '{{range $key, $value := .NetworkSettings.Networks}}{{$key}}{{end}}'
```

假设输出为 `astrbot_default` 或 `bridge`。

#### 2. 修改 MCP 配置连接到该网络

编辑 `compose.production.yaml`，修改 networks 部分：

```yaml
networks:
  mcp-internal:
    external: true
    name: astrbot_default  # 替换为 AstrBot 的实际网络名
```

#### 3. 配置环境变量

```bash
# .env
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp
XUNJI_HTTP_ALLOWED_ORIGINS=
XUNJI_APPROVAL_BASE_URL=http://127.0.0.1:8765
```

如果需要公网反代，添加：
```bash
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp,mcp.yourdomain.com
XUNJI_APPROVAL_BASE_URL=https://mcp.yourdomain.com
```

#### 4. 启动 MCP 服务

```bash
docker compose -f compose.production.yaml up -d --build
```

#### 5. 验证连通性

```bash
# 从 AstrBot 容器测试
docker exec astrbot curl http://xunji-private-mcp:8765/health
# 应返回: OK
```

### 方案 B：将 AstrBot 连接到 MCP 网络

如果想保持网络独立，可以将 AstrBot 连接到 MCP 的网络。

```bash
# 1. 启动 MCP（创建 mcp-internal 网络）
docker compose -f compose.production.yaml up -d --build

# 2. 将 AstrBot 连接到该网络
docker network connect mcp-internal astrbot

# 3. 验证
docker exec astrbot curl http://xunji-private-mcp:8765/health
```

### 方案 C：使用统一的 Compose 文件

如果想统一管理，可以创建包含两个服务的 Compose 文件。

```yaml
# docker-compose.full.yaml
services:
  xunji-private-mcp:
    build: ./xunji-private-mcp
    image: xunji-private-mcp:local
    container_name: xunji-private-mcp
    environment:
      XUNJI_HTTP_ALLOWED_HOSTS: ${XUNJI_HTTP_ALLOWED_HOSTS:-xunji-private-mcp}
      XUNJI_HTTP_ALLOWED_ORIGINS: ${XUNJI_HTTP_ALLOWED_ORIGINS:-}
      XUNJI_APPROVAL_BASE_URL: ${XUNJI_APPROVAL_BASE_URL:-}
    expose:
      - "8765"
    networks:
      - app-network
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=5)\" || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  astrbot:
    image: soulter/astrbot:latest
    container_name: astrbot
    ports:
      - "8080:8080"
    volumes:
      - ./astrbot-data:/app/data
    networks:
      - app-network
    depends_on:
      xunji-private-mcp:
        condition: service_healthy
    restart: unless-stopped

networks:
  app-network:
    driver: bridge
```

## AstrBot MCP 配置

### 1. 打开 AstrBot 管理界面

访问 `http://your-astrbot-ip:8080`，进入「插件 → MCP → 新增服务器」。

### 2. 填写配置

**服务器名称**：`xunji-private-mcp`

**传输类型**：选择「Streamable HTTP」

**服务器配置**：

```json
{
  "transport": "streamable_http",
  "url": "http://xunji-private-mcp:8765/mcp",
  "headers": {
    "X-Xunji-Train-Key": "YOUR_TRAIN_KEY_HERE",
    "X-Xunji-Food-Key": "YOUR_FOOD_KEY_HERE",
    "X-Xunji-Body-Key": "YOUR_BODY_KEY_HERE",
    "X-Xunji-Agent-Template-Key": "YOUR_TEMPLATE_KEY_HERE"
  },
  "timeout": 30,
  "sse_read_timeout": 300
}
```

**重要提示**：
- 将 `YOUR_*_KEY_HERE` 替换为实际的训记 API Key
- 没有某个 Key 时，删除对应的行
- 不要在配置中留空字符串，会导致连接失败

### 3. 测试连接

点击「测试连接」，应该显示连接成功，并列出可用的工具。

### 4. 启用工具

在「人格能力」中勾选需要使用的训记工具：
- `get_training` - 读取训练记录
- `upsert_training` - 写入训练记录
- `query_food_records` - 查询饮食记录
- `upsert_food_records` - 写入饮食记录
- `query_body_metrics` - 查询身体指标
- `upsert_body_metrics` - 写入身体指标
- `list_official_plans` - 列出官方训练计划
- `get_official_plan` - 获取训练计划详情
- `search_official_food` - 搜索官方食物库
- `upsert_custom_food` - 管理自定义食物
- `sync_agent_templates` - 同步训练模板
- `mutate_agent_templates` - 修改训练模板

## 浏览器审批配置（可选）

AstrBot 不支持 MCP 原生表单确认，写入操作需要使用浏览器审批。

### 启用浏览器审批

#### 情况 1：仅内网使用，映射端口到宿主机

1. 修改 `compose.production.yaml`，取消端口映射的注释：
```yaml
ports:
  - "127.0.0.1:8765:8765"
```

2. 设置环境变量：
```bash
# .env
XUNJI_APPROVAL_BASE_URL=http://127.0.0.1:8765
```

3. 重启服务：
```bash
docker compose -f compose.production.yaml up -d --force-recreate
```

#### 情况 2：通过公网反代

1. 配置反向代理（参见 [部署检查清单](DEPLOYMENT_CHECKLIST.md#3-公网反向代理)）

2. 设置环境变量：
```bash
# .env
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp,mcp.yourdomain.com
XUNJI_APPROVAL_BASE_URL=https://mcp.yourdomain.com
```

3. 重启服务

### 使用审批流程

1. 在 AstrBot 对话中发起写入操作（如「记录今天的训练」）

2. MCP 会返回一个审批链接，类似：
   ```
   http://127.0.0.1:8765/approve/xxxxx
   或
   https://mcp.yourdomain.com/approve/xxxxx
   ```

3. 在浏览器打开该链接（**5 分钟内有效**）

4. 输入对应业务的训记 API Key

5. 查看变更摘要，点击「确认写入」或「取消写入」

6. 回到 AstrBot，操作结果会自动返回

**注意事项**：
- 不要在 AstrBot 对话中粘贴 API Key
- 不要让他人代为操作审批链接
- 审批链接只能使用一次，过期需重新发起

## 故障排查

### AstrBot 提示「无法连接 MCP 服务器」

```bash
# 1. 检查 MCP 服务是否运行
docker ps | grep xunji-private-mcp

# 2. 检查健康状态
docker compose -f compose.production.yaml ps

# 3. 从 AstrBot 容器测试连通性
docker exec astrbot curl -v http://xunji-private-mcp:8765/health

# 4. 检查网络
docker network inspect mcp-internal | grep -A 5 astrbot
```

### 工具列表为空

检查 AstrBot MCP 配置中的请求头：
- 确保 Key 格式正确（无空格、无换行）
- 确认 Key 是有效的训记 API Key
- 至少配置一个业务 Key

### 写入操作失败

```bash
# 检查 MCP 日志
docker compose -f compose.production.yaml logs xunji-private-mcp

# 确认浏览器审批配置
curl http://127.0.0.1:8765/health  # 或公网地址
```

如果未配置 `XUNJI_APPROVAL_BASE_URL`，AstrBot 无法完成写入确认。

### Host header validation failed

```bash
# 更新允许的主机名
echo "XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp" >> .env
docker compose -f compose.production.yaml up -d --force-recreate
```

## 完整示例

### 单命令部署（连接到 AstrBot 网络）

```bash
# 1. 进入 MCP 项目目录
cd /path/to/xunji-private-mcp

# 2. 查看 AstrBot 网络
ASTRBOT_NETWORK=$(docker inspect astrbot --format '{{range $key, $value := .NetworkSettings.Networks}}{{$key}}{{end}}')
echo "AstrBot 网络: $ASTRBOT_NETWORK"

# 3. 创建配置
cat > .env << EOF
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp
XUNJI_HTTP_ALLOWED_ORIGINS=
XUNJI_APPROVAL_BASE_URL=http://127.0.0.1:8765
EOF

# 4. 创建 Compose override
cat > docker-compose.override.yaml << EOF
services:
  xunji-private-mcp:
    ports:
      - "127.0.0.1:8765:8765"
networks:
  mcp-internal:
    external: true
    name: $ASTRBOT_NETWORK
EOF

# 5. 启动服务
docker compose -f compose.production.yaml up -d --build

# 6. 验证
docker exec astrbot curl http://xunji-private-mcp:8765/health
```

### 清理

```bash
# 停止并删除
docker compose -f compose.production.yaml down

# 删除 override 文件
rm docker-compose.override.yaml
```

## 相关文档

- [部署检查清单](DEPLOYMENT_CHECKLIST.md) - 完整功能验证
- [Docker 容器间通信](DOCKER_NETWORKING.md) - 详细网络配置
- [主 README](../README.md) - 项目概览和安装

## AstrBot 对话示例

配置成功后，可以在 AstrBot 中使用以下命令：

```
用户：今天做了多少组深蹲？
AI：[调用 get_training 工具查询]

用户：记录今天的训练：深蹲 4 组，每组 15 次
AI：[返回审批链接]

用户：今天吃了什么？
AI：[调用 query_food_records 工具查询]

用户：帮我查询本周的体重变化
AI：[调用 query_body_metrics 工具查询]
```
