# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.7] - 2026-11-22

### Changed

- **文档改进**：
  - 在 `get_training` 工具说明中明确 lite 模式的限制
  - 在 README 中新增"食物搜索功能"章节,说明 `search_official_food` 需要单独的搜索凭据
  - 优化文档结构,将重要提示分为两个小节

### Notes

- 根据功能测试报告,食物搜索工具(`search_official_food`)已在代码中实现,但需要单独配置 `XUNJI_FOOD_SEARCH_KEY`
- lite 模式不返回未完成训练的问题是上游 API 行为,无法在 MCP 层面修复

## [0.3.6] - 2026-11-22

### Added

- **饮食模板功能**：
  - `list_food_templates` - 列出用户保存的饮食模板
  - `apply_food_template` - 将饮食模板套用到指定日期

### Changed

- **工具总数**：从 11 增加到 13
- **文档改进**：
  - 添加关于 lite 模式行为的注意事项
  - 移除关于"等待字段公开"的过时说明

### Fixed

- **get_training 文档**：补充说明 lite 模式可能不返回未完成训练的原因

## [0.3.5] - 2026-11-20

### Added

- **健康检查端点**：新增 `/health` 端点用于容器健康检查和监控
- **容器间通信配置**：新增专用 Docker Compose 配置文件
  - `compose.production.yaml` - 生产环境推荐配置
  - `compose.internal.yaml` - 纯内网场景配置
  - `.env.production` - 生产环境变量示例
  - `.env.docker-internal` - 容器间通信环境变量示例
- **完整文档**：新增详细部署和集成文档
  - `docs/DEPLOYMENT_CHECKLIST.md` - 部署检查清单和功能验证
  - `docs/ASTRBOT_INTEGRATION.md` - AstrBot 集成指南
  - `docs/REVERSE_PROXY.md` - Nginx/Caddy/Traefik 反代配置
  - `docs/DOCKER_NETWORKING.md` - Docker 网络配置详解
  - `docs/DOCKER_CONTAINER_NETWORKING.md` - 容器间通信快速参考
  - `docs/README.md` - 文档索引

### Changed

- **优化 Docker Compose 配置**：
  - 添加 `container_name` 便于引用
  - 添加 `restart: unless-stopped` 策略
  - 集成健康检查配置（30s 间隔，10s 超时，3 次重试）
- **环境变量管理**：在 `.env.example` 中添加 `XUNJI_APPROVAL_BASE_URL`

### Improved

- **部署灵活性**：支持三种部署方案
  - 宿主机访问（本地开发）
  - 容器间通信（Docker 内部网络）
  - 公网访问（HTTPS 反向代理）
- **文档完整性**：提供端到端的部署和故障排查指南
- **安全性**：详细的安全配置建议和最佳实践

### Documentation

- 新增 AstrBot 完整集成示例（包含三种部署方案）
- 新增 Nginx、Caddy、Traefik 完整配置示例
- 新增容器间通信网络拓扑图示
- 新增故障排查指南和常见问题解决方案

## [0.2.0] - 2024-11-XX

### Added

- 客户端作用域的训记凭据支持
- 浏览器审批功能（`approval.py`）
- HTTP 凭据中间件绑定

### Changed

- 从服务端环境变量迁移到客户端请求头认证
- 支持专用业务请求头（`X-Xunji-*-Key`）
- 支持通用 Bearer Token 认证

## [0.1.0] - 2024-11-XX

### Added

- 初始版本发布
- Stdio 和 Streamable HTTP 传输支持
- 训练、饮食、身体指标、模板四大模块
- Docker 支持

[0.3.0]: https://github.com/VDK1639/xunji-private-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/VDK1639/xunji-private-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/VDK1639/xunji-private-mcp/releases/tag/v0.1.0
