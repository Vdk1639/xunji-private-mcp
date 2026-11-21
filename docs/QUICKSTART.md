# 快速部署命令参考

## 私有部署（推荐）

### 方式 1：Docker Compose（推荐）

```bash
# 下载配置文件
curl -O https://raw.githubusercontent.com/Vdk1639/xunji-private-mcp/main/docker-compose.quickstart.yaml

# 启动服务
docker compose -f docker-compose.quickstart.yaml up -d

# 验证
curl http://127.0.0.1:8765/health
# 应返回: OK
```

**访问地址**：`http://127.0.0.1:8765/mcp`

### 方式 2：Docker Run

```bash
docker run -d \
  --name xunji-private-mcp \
  -p 127.0.0.1:8765:8765 \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --restart unless-stopped \
  ghcr.io/vdk1639/xunji-private-mcp:latest
```

**访问地址**：`http://127.0.0.1:8765/mcp`

### 健康检查

```bash
# 检查容器状态
docker ps | grep xunji-private-mcp

# 测试健康端点
curl http://127.0.0.1:8765/health

# 查看日志
docker logs xunji-private-mcp
```

---

## 容器间通信部署（与 AstrBot 等容器集成）

### 方式 1：Docker Compose（推荐）

```bash
# 下载配置文件
curl -O https://raw.githubusercontent.com/Vdk1639/xunji-private-mcp/main/docker-compose.quickstart-internal.yaml

# 启动服务
docker compose -f docker-compose.quickstart-internal.yaml up -d

# 验证容器间通信
docker run --rm --network mcp-internal alpine:latest \
  wget -q -O- http://xunji-private-mcp:8765/health
# 应返回: OK
```

**容器内访问地址**：`http://xunji-private-mcp:8765/mcp`

### 方式 2：连接到现有容器网络

如果你的客户端容器（如 AstrBot）已经在运行：

```bash
# 1. 查看客户端容器的网络
NETWORK=$(docker inspect <客户端容器名> --format '{{range $key, $value := .NetworkSettings.Networks}}{{$key}}{{end}}')
echo "客户端网络: $NETWORK"

# 2. 启动 MCP 容器并连接到该网络
docker run -d \
  --name xunji-private-mcp \
  --network $NETWORK \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --restart unless-stopped \
  ghcr.io/vdk1639/xunji-private-mcp:latest

# 3. 从客户端容器测试
docker exec <客户端容器名> curl http://xunji-private-mcp:8765/health
```

### 方式 3：将现有 MCP 容器连接到客户端网络

如果 MCP 容器已经在运行：

```bash
# 查看客户端网络
NETWORK=$(docker inspect <客户端容器名> --format '{{range $key, $value := .NetworkSettings.Networks}}{{$key}}{{end}}')

# 连接 MCP 容器到该网络
docker network connect $NETWORK xunji-private-mcp

# 验证
docker exec <客户端容器名> curl http://xunji-private-mcp:8765/health
```

---

## 公网部署（不推荐，需额外安全配置）

⚠️ **警告**：公网部署会暴露 MCP 服务到互联网，存在以下风险：
- 请求中的训记 API Key 可能被代理、日志或监控系统记录
- MCP 端点部署者和 TLS 终止代理能接触所有请求和返回数据
- 多人共用同一客户端实例时，所有用户共享同一套 API Key
- 需要妥善配置反向代理、速率限制、访问控制

**强烈推荐使用私有部署或 SSH 隧道**，而非公网暴露。

如果确实需要公网部署（例如团队内网或受控环境），请务必：

### 必要条件

1. ✅ 配置 HTTPS 反向代理（Nginx/Caddy/Traefik）
2. ✅ 设置 `XUNJI_HTTP_ALLOWED_HOSTS` 为你的域名
3. ✅ 配置速率限制和连接数上限
4. ✅ 禁用 `/mcp` 路径的请求头日志（避免记录 API Key）
5. ✅ 限制访问来源（IP 白名单或基础认证）
6. ✅ 定期轮换训记 API Key

### Docker Run（配合反向代理）

```bash
docker run -d \
  --name xunji-private-mcp \
  -e XUNJI_HTTP_ALLOWED_HOSTS=mcp.yourdomain.com \
  -e XUNJI_HTTP_ALLOWED_ORIGINS=https://chat.yourdomain.com \
  -e XUNJI_APPROVAL_BASE_URL=https://mcp.yourdomain.com \
  --expose 8765 \
  --network reverse-proxy-network \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --restart unless-stopped \
  ghcr.io/vdk1639/xunji-private-mcp:latest
```

**注意**：
- 不要使用 `-p` 映射端口到公网接口
- 必须通过反向代理访问，详见 [反向代理配置文档](docs/REVERSE_PROXY.md)
- 使用 `--network` 连接到反向代理所在的网络

### 反向代理简化配置（Nginx）

```nginx
upstream xunji_mcp {
    server xunji-private-mcp:8765;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name mcp.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /mcp {
        proxy_pass http://xunji_mcp/mcp;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE 支持
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        
        # 超时
        proxy_read_timeout 180s;
        
        # 关闭请求头日志（避免记录 API Key）
        access_log off;
    }
}
```

完整反向代理配置和安全建议，请参见 [docs/REVERSE_PROXY.md](docs/REVERSE_PROXY.md)。

---

## SSH 隧道（推荐用于远程私有访问）

如果只需要跨主机访问远端部署的 MCP 服务，推荐使用 SSH 隧道，无需公网暴露：

```bash
# 在本地机器运行，转发远端服务器的 MCP 端口
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 user@server.example.com

# 在另一个终端访问
curl http://127.0.0.1:8765/health
```

客户端配置仍然使用 `http://127.0.0.1:8765/mcp`，就像本地部署一样。

---

## 停止和清理

```bash
# Docker Compose 部署
docker compose -f docker-compose.quickstart.yaml down
docker compose -f docker-compose.quickstart-internal.yaml down

# Docker Run 部署
docker stop xunji-private-mcp
docker rm xunji-private-mcp

# 清理镜像（可选）
docker rmi ghcr.io/vdk1639/xunji-private-mcp:latest
```

---

## 更新版本

```bash
# 拉取最新镜像
docker pull ghcr.io/vdk1639/xunji-private-mcp:latest

# 重新创建容器（Docker Compose）
docker compose -f docker-compose.quickstart.yaml up -d --force-recreate

# 重新创建容器（Docker Run）
docker stop xunji-private-mcp
docker rm xunji-private-mcp
# 然后重新运行上面的 docker run 命令
```

---

## 相关文档

- [AstrBot 集成指南](docs/ASTRBOT_INTEGRATION.md) - AstrBot 完整配置
- [反向代理配置](docs/REVERSE_PROXY.md) - Nginx/Caddy/Traefik 配置
- [部署检查清单](docs/DEPLOYMENT_CHECKLIST.md) - 完整部署验证
- [主 README](README.md) - 完整项目文档
