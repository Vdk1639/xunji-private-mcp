# xunji-private-mcp 文档

本目录包含 xunji-private-mcp 项目的详细文档。

## 快速开始

- **[快速部署指南](QUICKSTART.md)** ⭐ **推荐首选**
  - 无需克隆仓库，直接使用 Docker 镜像
  - 私有部署一行命令（推荐）
  - 容器间通信部署（AstrBot 集成）
  - 公网部署警告和配置（不推荐）
  - SSH 隧道使用

## 部署指南

### 基础部署

- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - 部署检查清单
  - 功能验证流程
  - Docker 容器间通信验证
  - AstrBot 集成验证
  - 公网反向代理验证
  - 故障排查指南

- **[DOCKER_NETWORKING.md](DOCKER_NETWORKING.md)** - Docker 网络详解
  - 三种部署场景详解（宿主机/容器间/公开部署）
  - 网络拓扑和安全配置
  - 环境变量完整说明

- **[DOCKER_CONTAINER_NETWORKING.md](DOCKER_CONTAINER_NETWORKING.md)** - 容器间通信快速参考
  - 快速开始命令
  - 常见场景配置
  - 网络隔离选项

### 集成指南

- **[ASTRBOT_DEPLOYMENT.md](ASTRBOT_DEPLOYMENT.md)** - AstrBot 部署快速指南 ⭐ **新用户推荐**
  - AI Agent 自动部署提示词（最简单）
  - 手动部署步骤详解
  - Docker Compose 集成示例
  - 完整故障排查指南

- **[ASTRBOT_INTEGRATION.md](ASTRBOT_INTEGRATION.md)** - AstrBot 集成指南
  - 三种网络连接方案
  - MCP 完整配置示例
  - 浏览器审批配置
  - 故障排查和对话示例

- **[REVERSE_PROXY.md](REVERSE_PROXY.md)** - 反向代理配置
  - Nginx 完整配置
  - Caddy 完整配置
  - Traefik 完整配置
  - SSL/TLS、SSE 流支持
  - 安全加固和监控

## 配置文件

项目根目录提供以下配置文件：

```
├── docker-compose.quickstart.yaml          # 快速部署：私有访问（推荐）
├── docker-compose.quickstart-internal.yaml # 快速部署：容器间通信
├── compose.yaml                            # 默认配置（从源码构建）
├── compose.production.yaml                 # 生产环境配置
├── compose.internal.yaml                   # 纯内网配置
└── .env.example                            # 环境变量模板
```

## 快速选择

| 你的场景 | 阅读文档 | 使用配置 |
|---------|---------|---------|
| **本地开发测试** | [QUICKSTART.md](QUICKSTART.md) | `docker-compose.quickstart.yaml` |
| **多容器部署（如 AstrBot）** | [QUICKSTART.md](QUICKSTART.md) + [ASTRBOT_INTEGRATION.md](ASTRBOT_INTEGRATION.md) | `docker-compose.quickstart-internal.yaml` |
| **远程访问** | [QUICKSTART.md - SSH 隧道](QUICKSTART.md#ssh-隧道推荐用于远程私有访问) | `docker-compose.quickstart.yaml` + SSH |
| **公开 HTTPS 服务（不推荐）** | ⚠️ [QUICKSTART.md - 公网警告](QUICKSTART.md#公网部署不推荐需额外安全配置) + [REVERSE_PROXY.md](REVERSE_PROXY.md) | `compose.production.yaml` + 反向代理 |

## 推荐阅读顺序

### 新用户

1. [主 README](../README.md) - 了解项目功能和凭据配置
2. **[QUICKSTART.md](QUICKSTART.md)** - 选择部署方式并执行
3. [主 README - 客户端配置](../README.md#客户端配置) - 配置客户端连接

### AstrBot 用户

1. **[QUICKSTART.md - 容器间通信](QUICKSTART.md#容器间通信部署与-astrbot-等容器集成)** - 部署 MCP 服务
2. **[ASTRBOT_DEPLOYMENT.md](ASTRBOT_DEPLOYMENT.md)** - 最简单：使用 AI Agent 自动部署 ⭐ 或查看手动步骤
3. **[ASTRBOT_INTEGRATION.md](ASTRBOT_INTEGRATION.md)** - 进阶配置和最佳实践

### 公网部署（不推荐）

⚠️ **请务必先阅读安全警告**：[QUICKSTART.md - 公网部署警告](QUICKSTART.md#公网部署不推荐需额外安全配置)

1. [REVERSE_PROXY.md](REVERSE_PROXY.md) - 配置 HTTPS 反向代理
2. [DEPLOYMENT_CHECKLIST.md - 公网验证](DEPLOYMENT_CHECKLIST.md#3-公网反向代理) - 验证配置安全性

## 主文档

- **[README](../README.md)** - 项目概览
  - 功能说明和凭据管理
  - Windows/Linux 安装
  - Docker 快速部署命令
  - 客户端配置（Codex/Claude Code/AstrBot）
  - 开发和发布指南

- **[CHANGELOG](../CHANGELOG.md)** - 版本变更记录

## 工具

- **[部署验证脚本](../scripts/verify-deployment.sh)** - 自动化验证部署
  - 检查 Docker 环境
  - 验证容器构建和启动
  - 测试健康检查和网络通信
  - 自动清理测试环境

## 支持

如有问题，请在 [GitHub Issues](https://github.com/VDK1639/xunji-private-mcp/issues) 提交反馈。
