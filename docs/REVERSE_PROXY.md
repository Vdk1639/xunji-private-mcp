# 反向代理配置示例

本文档提供常见反向代理的完整配置示例。

## Nginx

### 完整配置

```nginx
# /etc/nginx/conf.d/xunji-mcp.conf

# 速率限制（可选）
limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=mcp_conn:10m;

# 上游服务器
upstream xunji_mcp {
    # 如果 MCP 在 Docker 内部网络
    server xunji-private-mcp:8765;
    
    # 如果 MCP 映射到宿主机
    # server 127.0.0.1:8765;
    
    # 如果 Nginx 也在 Docker 中，确保在同一网络
    # 或者使用 host.docker.internal（Docker Desktop）
    
    keepalive 32;
}

server {
    listen 80;
    server_name mcp.yourdomain.com;
    
    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name mcp.yourdomain.com;

    # SSL 证书
    ssl_certificate /etc/letsencrypt/live/mcp.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.yourdomain.com/privkey.pem;
    
    # SSL 优化
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 访问日志（注意：会记录请求头，生产环境需要过滤敏感头）
    access_log /var/log/nginx/mcp-access.log;
    error_log /var/log/nginx/mcp-error.log;

    # MCP 主端点
    location /mcp {
        # 速率限制
        limit_req zone=mcp_limit burst=20 nodelay;
        limit_conn mcp_conn 10;
        
        proxy_pass http://xunji_mcp/mcp;
        
        # 保留原始头
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 传递 MCP 会话头
        proxy_pass_request_headers on;
        
        # SSE 支持（Server-Sent Events）
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        chunked_transfer_encoding on;
        proxy_buffering off;
        proxy_cache off;
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 180s;
        proxy_read_timeout 180s;
        
        # 请求体大小限制
        client_max_body_size 10M;
    }

    # 审批端点
    location /approve/ {
        proxy_pass http://xunji_mcp/approve/;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 关闭缓存
        proxy_buffering off;
        proxy_cache off;
        
        # 关闭请求体日志（避免记录 API Key）
        access_log off;
        
        # 超时
        proxy_connect_timeout 30s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # 健康检查（内部使用）
    location /health {
        proxy_pass http://xunji_mcp/health;
        access_log off;
        
        # 仅允许内部访问（可选）
        # allow 10.0.0.0/8;
        # allow 172.16.0.0/12;
        # allow 192.168.0.0/16;
        # deny all;
    }
}
```

### Docker Compose 中的 Nginx

如果 Nginx 也运行在 Docker 中：

```yaml
# docker-compose.full.yaml
services:
  xunji-private-mcp:
    build: .
    image: xunji-private-mcp:local
    container_name: xunji-private-mcp
    environment:
      XUNJI_HTTP_ALLOWED_HOSTS: xunji-private-mcp,mcp.yourdomain.com
      XUNJI_HTTP_ALLOWED_ORIGINS: https://chat.yourdomain.com
      XUNJI_APPROVAL_BASE_URL: https://mcp.yourdomain.com
    expose:
      - "8765"
    networks:
      - web
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=5)\" || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    container_name: nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./ssl:/etc/letsencrypt:ro
    networks:
      - web
    depends_on:
      xunji-private-mcp:
        condition: service_healthy
    restart: unless-stopped

networks:
  web:
    driver: bridge
```

### 验证 Nginx 配置

```bash
# 测试配置
nginx -t

# 重载配置
nginx -s reload

# 或重启
systemctl restart nginx
```

## Caddy

Caddy 自动管理 HTTPS 证书，配置更简洁。

### 完整配置

```caddy
# /etc/caddy/Caddyfile

# 全局选项
{
    email your-email@example.com
}

mcp.yourdomain.com {
    # 自动 HTTPS
    
    # MCP 主端点
    reverse_proxy /mcp* xunji-private-mcp:8765 {
        # 保留头
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        
        # SSE 支持
        flush_interval -1
        
        # 超时
        transport http {
            read_timeout 180s
            write_timeout 180s
            dial_timeout 60s
        }
    }

    # 审批端点
    reverse_proxy /approve/* xunji-private-mcp:8765 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }

    # 健康检查
    reverse_proxy /health xunji-private-mcp:8765 {
        header_up Host {host}
    }

    # 安全头
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        X-XSS-Protection "1; mode=block"
    }

    # 日志
    log {
        output file /var/log/caddy/mcp-access.log
        format console
    }
}
```

### Docker Compose 中的 Caddy

```yaml
services:
  xunji-private-mcp:
    # ... MCP 配置同上

  caddy:
    image: caddy:alpine
    container_name: caddy
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - web
    depends_on:
      xunji-private-mcp:
        condition: service_healthy
    restart: unless-stopped

volumes:
  caddy_data:
  caddy_config:

networks:
  web:
    driver: bridge
```

### 验证 Caddy 配置

```bash
# 测试配置
caddy validate --config /etc/caddy/Caddyfile

# 重载配置
caddy reload --config /etc/caddy/Caddyfile

# 或重启
systemctl restart caddy
```

## Traefik

Traefik 适用于 Docker 环境，通过标签自动配置。

### Docker Compose 配置

```yaml
services:
  traefik:
    image: traefik:v3.0
    container_name: traefik
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=your-email@example.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"  # Traefik Dashboard
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - traefik_certs:/letsencrypt
    networks:
      - web
    restart: unless-stopped

  xunji-private-mcp:
    build: .
    image: xunji-private-mcp:local
    container_name: xunji-private-mcp
    environment:
      XUNJI_HTTP_ALLOWED_HOSTS: xunji-private-mcp,mcp.yourdomain.com
      XUNJI_HTTP_ALLOWED_ORIGINS: https://chat.yourdomain.com
      XUNJI_APPROVAL_BASE_URL: https://mcp.yourdomain.com
    expose:
      - "8765"
    networks:
      - web
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=5)\" || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
    labels:
      - "traefik.enable=true"
      
      # HTTP -> HTTPS 重定向
      - "traefik.http.routers.xunji-mcp-http.entrypoints=web"
      - "traefik.http.routers.xunji-mcp-http.rule=Host(`mcp.yourdomain.com`)"
      - "traefik.http.routers.xunji-mcp-http.middlewares=https-redirect"
      - "traefik.http.middlewares.https-redirect.redirectscheme.scheme=https"
      
      # HTTPS
      - "traefik.http.routers.xunji-mcp.entrypoints=websecure"
      - "traefik.http.routers.xunji-mcp.rule=Host(`mcp.yourdomain.com`)"
      - "traefik.http.routers.xunji-mcp.tls=true"
      - "traefik.http.routers.xunji-mcp.tls.certresolver=letsencrypt"
      
      # 服务配置
      - "traefik.http.services.xunji-mcp.loadbalancer.server.port=8765"
      
      # 安全头
      - "traefik.http.routers.xunji-mcp.middlewares=security-headers"
      - "traefik.http.middlewares.security-headers.headers.stsSeconds=31536000"
      - "traefik.http.middlewares.security-headers.headers.stsIncludeSubdomains=true"
      - "traefik.http.middlewares.security-headers.headers.contentTypeNosniff=true"
      - "traefik.http.middlewares.security-headers.headers.frameDeny=true"
      - "traefik.http.middlewares.security-headers.headers.browserXssFilter=true"

volumes:
  traefik_certs:

networks:
  web:
    driver: bridge
```

## 测试反向代理

### 健康检查

```bash
# HTTP (应自动重定向到 HTTPS)
curl -I http://mcp.yourdomain.com/health

# HTTPS
curl https://mcp.yourdomain.com/health
# 应返回: OK
```

### MCP 连接测试

```bash
# 使用训记 Key 测试
curl -v -H "Authorization: Bearer YOUR_KEY" \
  https://mcp.yourdomain.com/mcp

# 应返回 MCP 协议响应（或 401 如果 Key 无效）
```

### SSE 流测试

```bash
# 测试 Server-Sent Events 是否正常工作
curl -N -H "Authorization: Bearer YOUR_KEY" \
  -H "Accept: text/event-stream" \
  https://mcp.yourdomain.com/mcp
```

### 完整 MCP 客户端测试

使用 Claude Code 测试：

```bash
# 临时测试配置
claude mcp add --scope user --transport http \
  --header "X-Xunji-Train-Key: YOUR_KEY" \
  test-mcp https://mcp.yourdomain.com/mcp

# 测试工具列表
claude mcp list test-mcp

# 清理
claude mcp remove test-mcp
```

## 监控和日志

### Nginx 日志分析

```bash
# 实时日志
tail -f /var/log/nginx/mcp-access.log

# 错误日志
tail -f /var/log/nginx/mcp-error.log

# 统计请求
cat /var/log/nginx/mcp-access.log | awk '{print $1}' | sort | uniq -c | sort -rn

# 查看响应时间
cat /var/log/nginx/mcp-access.log | awk '{print $NF}' | sort -n | tail -100
```

### Caddy 日志

```bash
# 实时日志
tail -f /var/log/caddy/mcp-access.log

# 或通过 journalctl
journalctl -u caddy -f
```

### Docker 日志

```bash
# MCP 服务日志
docker compose logs -f xunji-private-mcp

# 反向代理日志
docker compose logs -f nginx  # 或 caddy, traefik
```

## 安全建议

### 1. 隐藏敏感头日志

编辑 Nginx 日志格式，排除敏感头：

```nginx
log_format mcp_safe '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer"';

access_log /var/log/nginx/mcp-access.log mcp_safe;
```

### 2. IP 白名单（可选）

```nginx
# 仅允许特定 IP 访问
location /mcp {
    allow 1.2.3.4;      # 你的 IP
    allow 10.0.0.0/8;   # 内网
    deny all;
    
    # ... 其他配置
}
```

### 3. 基础认证（额外保护）

```nginx
location /mcp {
    auth_basic "MCP Access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    # ... 其他配置
}
```

生成密码文件：
```bash
htpasswd -c /etc/nginx/.htpasswd username
```

### 4. 速率限制

已在 Nginx 示例中包含，根据实际需求调整：

```nginx
# 每秒 10 个请求，突发最多 20 个
limit_req zone=mcp_limit burst=20 nodelay;

# 每个 IP 最多 10 个连接
limit_conn mcp_conn 10;
```

### 5. HTTPS 强制

确保所有 HTTP 请求重定向到 HTTPS，已在所有示例中包含。

## 故障排查

### 502 Bad Gateway

```bash
# 检查 MCP 服务是否运行
docker ps | grep xunji-private-mcp

# 检查网络连通性
docker exec nginx curl http://xunji-private-mcp:8765/health
```

### 504 Gateway Timeout

增加超时时间：

```nginx
proxy_connect_timeout 120s;
proxy_send_timeout 300s;
proxy_read_timeout 300s;
```

### 400 Bad Request (Host validation failed)

更新 MCP 环境变量：

```bash
XUNJI_HTTP_ALLOWED_HOSTS=xunji-private-mcp,mcp.yourdomain.com
docker compose up -d --force-recreate
```

### SSE 连接中断

确保禁用了缓冲：

```nginx
proxy_buffering off;
proxy_cache off;
chunked_transfer_encoding on;
```

## 相关文档

- [部署检查清单](DEPLOYMENT_CHECKLIST.md) - 完整部署流程
- [AstrBot 集成](ASTRBOT_INTEGRATION.md) - AstrBot 配置
- [Docker 容器间通信](DOCKER_NETWORKING.md) - 网络配置
