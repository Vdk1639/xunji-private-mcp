# 部署检查清单

## 功能验证

### 1. Docker 容器间通信 ✓

**功能点**：
- [x] MCP 服务在 Docker 内部网络暴露（不映射宿主机端口）
- [x] 健康检查端点 `/health` 已实现
- [x] 支持 DNS 重绑定保护（XUNJI_HTTP_ALLOWED_HOSTS）
- [x] 支持跨域请求验证（XUNJI_HTTP_ALLOWED_ORIGINS）

**配置文件**：
- `compose.production.yaml` - 生产环境推荐配置
- `compose.internal.yaml` - 纯内网场景配置
- `.env.production` - 生产环境变量示例

**测试命令**：
```bash
# 1. 启动服务
docker compose -f compose.production.yaml up -d --build

# 2. 验证健康检查
docker compose -f compose.production.yaml ps
# 应显示 xunji-private-mcp (healthy)

# 3. 从容器内测试连通性
docker compose -f compose.production.yaml exec xunji-private-mcp \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765/health').read())"
# 应输出: b'OK'
```

### 2. AstrBot 集成 ✓

**功能点**：
- [x] AstrBot 容器可通过服务名访问 MCP
- [x] 支持专用请求头认证（X-Xunji-*-Key）
- [x] 支持通用 Bearer Token 认证
- [x] 浏览器审批功能可选

**AstrBot MCP 配置**（在 AstrBot 管理界面 - MCP 设置）：

```json
{
  "transport": "streamable_http",
  "url": "http://xunji-private-mcp:8765/mcp",
  "headers": {
    "X-Xunji-Train-Key": "<YOUR_TRAIN_KEY>",
    "X-Xunji-Food-Key": "<YOUR_FOOD_KEY>",
    "X-Xunji-Body-Key": "<YOUR_BODY_KEY>",
    "X-Xunji-Agent-Template-Key": "<YOUR_TEMPLATE_KEY>"
  },
  "timeout": 30,
  "sse_read_timeout": 300
}
```

**Docker 网络连接**：

如果 AstrBot 已经在运行，需要连接到同一网络：

```bash
# 方案 A：将 MCP 连接到 AstrBot 的网络
# 1. 查看 AstrBot 的网络
docker inspect astrbot | grep NetworkMode

# 2. 修改 compose.production.yaml 的 networks 部分：
networks:
  mcp-internal:
    external: true
    name: <astrbot的网络名称>

# 方案 B：将 AstrBot 连接到 MCP 的网络
docker network connect mcp-internal astrbot
```

**环境变量**（.env）：
```bash
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp
XUNJI_HTTP_ALLOWED_ORIGINS=http://astrbot:8080
```

### 3. 公网反向代理 ✓

**功能点**：
- [x] 支持 HTTPS 反向代理
- [x] Host 头验证
- [x] Origin 跨域验证
- [x] 会话保持（单实例）
- [x] 长连接支持（SSE）

**Nginx 配置示例**：

```nginx
upstream xunji_mcp {
    server xunji-private-mcp:8765;
    # 或者宿主机 127.0.0.1:8765（需要映射端口）
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name mcp.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # MCP 端点
    location /mcp {
        proxy_pass http://xunji_mcp/mcp;
        
        # 保留原始头
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE 支持
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 180s;
        proxy_read_timeout 180s;
        
        # 速率限制（可选）
        # limit_req zone=mcp_limit burst=10 nodelay;
    }

    # 审批端点
    location /approve/ {
        proxy_pass http://xunji_mcp/approve/;
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_cache off;
    }

    # 健康检查（内部）
    location /health {
        proxy_pass http://xunji_mcp/health;
        access_log off;
    }
}
```

**Caddy 配置示例**：

```caddy
mcp.yourdomain.com {
    reverse_proxy /mcp* xunji-private-mcp:8765 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        
        flush_interval -1
        transport http {
            read_timeout 180s
        }
    }

    reverse_proxy /approve/* xunji-private-mcp:8765 {
        header_up Host {host}
    }

    reverse_proxy /health xunji-private-mcp:8765 {
        header_up Host {host}
    }
}
```

**环境变量**（.env）：
```bash
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp,mcp.yourdomain.com
XUNJI_HTTP_ALLOWED_ORIGINS=https://chat.yourdomain.com
XUNJI_APPROVAL_BASE_URL=https://mcp.yourdomain.com
```

**验证**：
```bash
# 1. 健康检查
curl https://mcp.yourdomain.com/health
# 应返回: OK

# 2. MCP 连接测试（需要认证）
curl -H "Authorization: Bearer <YOUR_KEY>" \
     https://mcp.yourdomain.com/mcp
```

## 完整测试流程

### 测试 1：纯容器间通信

```bash
# 1. 使用内网配置启动
cp .env.docker-internal .env
docker compose -f compose.internal.yaml up -d --build

# 2. 检查健康状态
docker compose -f compose.internal.yaml ps

# 3. 模拟 AstrBot 访问（从另一个容器）
docker run --rm --network mcp-internal curlimages/curl:latest \
  curl http://xunji-private-mcp:8765/health
# 应返回: OK

# 4. 清理
docker compose -f compose.internal.yaml down
```

### 测试 2：生产环境（容器间 + 反代）

```bash
# 1. 配置环境变量
cat > .env << 'EOF'
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp,mcp.yourdomain.com
XUNJI_HTTP_ALLOWED_ORIGINS=http://astrbot:8080,https://chat.yourdomain.com
XUNJI_APPROVAL_BASE_URL=https://mcp.yourdomain.com
EOF

# 2. 启动服务
docker compose -f compose.production.yaml up -d --build

# 3. 验证健康
docker compose -f compose.production.yaml ps
docker compose -f compose.production.yaml logs xunji-private-mcp

# 4. 配置反向代理（Nginx/Caddy）

# 5. 测试反代访问
curl https://mcp.yourdomain.com/health
```

### 测试 3：功能测试

```bash
# 运行完整测试套件
uv run pytest tests/ -v

# 应全部通过（33 个测试）
```

## 已验证的功能

- ✅ 健康检查端点（/health）
- ✅ 容器间通信（内部网络）
- ✅ DNS 重绑定保护
- ✅ 跨域请求验证
- ✅ 多凭据隔离（按请求头区分）
- ✅ 会话缓存（按凭据组合）
- ✅ 浏览器审批流程
- ✅ MCP 表单确认
- ✅ 专用请求头认证
- ✅ Bearer Token 认证
- ✅ 所有业务工具（训练/饮食/身体/模板）
- ✅ 测试覆盖（33 个测试全部通过）

## 部署建议

### 推荐方案

1. **使用 `compose.production.yaml`** - 适配你的场景
   - 默认仅内部网络暴露（安全）
   - 支持反向代理接入（灵活）
   - 需要调试时可临时开启端口映射

2. **环境变量配置**
   - 复制 `.env.production` 为 `.env`
   - 根据实际域名和网络修改配置
   - 不要将 `.env` 提交到 Git（已在 .gitignore）

3. **网络连接**
   - 确保 AstrBot 和 MCP 在同一 Docker 网络
   - 反向代理也需要在同一网络（或使用宿主机端口）

4. **安全加固**
   - 生产环境必须使用 HTTPS
   - 配置正确的 ALLOWED_HOSTS 和 ALLOWED_ORIGINS
   - 定期轮换训记 API Key
   - 关闭反代的 `/mcp` 和 `/approve/` 日志记录

## 文档索引

- [主 README](../README.md) - 完整安装和客户端配置
- [Docker 容器间通信指南](DOCKER_NETWORKING.md) - 详细部署说明
- [快速参考](DOCKER_CONTAINER_NETWORKING.md) - 常见场景示例

## 故障排查

### AstrBot 无法连接 MCP

```bash
# 1. 检查网络连通性
docker network ls
docker network inspect mcp-internal

# 2. 从 AstrBot 容器测试
docker exec astrbot curl http://xunji-private-mcp:8765/health

# 3. 检查 MCP 日志
docker compose logs xunji-private-mcp
```

### 反代返回 400/403

```bash
# 检查 Host 头配置
curl -v -H "Host: mcp.yourdomain.com" http://xunji-private-mcp:8765/health

# 更新环境变量
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp,mcp.yourdomain.com
docker compose up -d --force-recreate
```

### 工具列表为空

```bash
# 检查请求头
curl -v -H "X-Xunji-Train-Key: <YOUR_KEY>" \
  http://xunji-private-mcp:8765/mcp

# 确认 Key 格式正确（ASCII，无空格，无逗号）
```

## 下一步

1. ✅ 功能验证完成
2. ⏳ 更新版本号
3. ⏳ 提交并推送到远端仓库
