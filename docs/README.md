# xunji-private-mcp 文档

本目录包含 xunji-private-mcp 项目的详细文档。

## 文档索引

### 部署指南

- **[DOCKER_NETWORKING.md](DOCKER_NETWORKING.md)** - Docker 容器间通信完整指南
  - 三种部署方案详解（宿主机/容器间/公开部署）
  - 网络拓扑和安全配置
  - 客户端集成示例（AstrBot 等）
  - 故障排查和性能优化

- **[DOCKER_CONTAINER_NETWORKING.md](DOCKER_CONTAINER_NETWORKING.md)** - Docker 容器间通信快速参考
  - 快速开始指南
  - 环境变量配置说明
  - 常见集成场景示例

### 配置文件

项目根目录提供以下配置文件：

```
├── compose.yaml                 # 默认 Docker Compose 配置（宿主机访问）
├── compose.internal.yaml        # 容器间通信专用配置
├── .env.example                 # 环境变量模板
└── .env.docker-internal         # 容器间通信环境变量示例
```

## 快速选择

| 你的场景 | 阅读文档 | 使用配置 |
|---------|---------|---------|
| 本地开发测试 | 主 README | `compose.yaml` |
| 多容器部署（如 AstrBot） | [DOCKER_NETWORKING.md](DOCKER_NETWORKING.md) | `compose.internal.yaml` + `.env.docker-internal` |
| 公开 HTTPS 服务 | 主 README + [DOCKER_NETWORKING.md](DOCKER_NETWORKING.md) | `compose.yaml` + 反向代理 |

## 支持

如有问题，请在项目 [GitHub Issues](https://github.com/VDK1639/xunji-private-mcp/issues) 提交反馈。
