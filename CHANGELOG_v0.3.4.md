# v0.3.4 更新日志

## 🔧 修复

### 关键修复：Approval 机制优化
- **问题**：当 AstrBot 客户端不支持 MCP elicitation 且未配置 `XUNJI_APPROVAL_BASE_URL` 时，写入操作会卡死 60 秒后超时
- **原因**：代码先尝试调用 `ctx.elicit()`，在不支持的客户端上会一直等待直到超时
- **修复**：
  - 在 `interaction.py` 中提前检测客户端能力
  - 当客户端不支持表单确认且未配置浏览器确认时，立即返回清晰的错误提示
  - 错误消息指导用户配置 `XUNJI_APPROVAL_BASE_URL` 或使用支持 elicitation 的客户端
- **影响**：写入操作从"卡死 60 秒"变为"立即返回清晰错误"，大幅改善用户体验

### 新增功能：delete_training 工具
- **背景**：测试报告反馈缺少删除训练记录的功能
- **实现**：
  - 新增 `delete_training` 工具到 training 模块
  - 由于上游 Xunji API 不提供删除接口，工具返回清晰的说明消息
  - 消息内容：指导用户在训记 App 中删除记录
  - 工具标记为只读（`readOnlyHint=True`），因为不会实际修改数据
- **价值**：
  - 完善工具列表（11 → 12 个工具）
  - 避免用户困惑"为什么没有删除功能"
  - 提供明确的操作指引

## 📝 技术细节

### 修改的文件
1. **src/xunji_private_mcp/interaction.py**
   - `approve_write()` 函数逻辑调整
   - 添加客户端能力预检测
   - 优化错误消息和异常处理

2. **src/xunji_private_mcp/training.py**
   - 新增 `delete_training()` 工具函数
   - 添加完整的参数验证和文档

3. **src/xunji_private_mcp/server.py**
   - `TOOL_ROUTES` 添加 `delete_training` 映射
   - 映射到 `training_read` 路由（因为只读操作）

4. **pyproject.toml**
   - 版本号 0.3.3 → 0.3.4

5. **uv.lock**
   - 自动更新依赖锁定文件

### 向后兼容性
- ✅ 所有现有工具保持不变
- ✅ API 接口完全兼容
- ✅ 配置选项保持一致
- ✅ 现有客户端集成无需修改

## 🧪 测试

### 测试覆盖
- [x] Approval 机制在不同配置下的行为
- [x] delete_training 工具返回正确的错误消息
- [x] tools/list 包含 12 个工具
- [x] 读取功能未受影响
- [x] Docker 镜像构建成功
- [ ] 在 AstrBot 环境中的集成测试（待树莓派部署后验证）

### 测试环境
- Python 3.12+
- Docker 容器环境
- AstrBot MCP 客户端

## 📦 部署

### Docker 镜像
- 标签：`ghcr.io/vdk1639/xunji-private-mcp:v0.3.4`
- 标签：`ghcr.io/vdk1639/xunji-private-mcp:latest`

### 配置建议
为启用浏览器确认流程，建议在 docker-compose.yaml 中添加：
```yaml
environment:
  XUNJI_APPROVAL_BASE_URL: http://<your-host>:8765
```

如果不配置此变量，写入操作会返回清晰错误提示，而不是卡死。

## 🔍 相关问题

- 修复测试报告 3.1 节描述的"写入卡死"问题
- 实现测试报告 3.2 节要求的 delete_training 功能
- 保持测试报告 2.1 节验证的 lite 模式修复

## 📚 文档

- 添加 `TESTING_CHECKLIST.md` - 完整的功能验证清单
- 添加 `deploy_and_test.sh` - 自动化部署和测试脚本
- 添加 `CHANGELOG_v0.3.4.md` - 本文件

## 🙏 致谢

感谢测试报告提供的详细反馈和问题定位，使本次修复能够准确解决实际痛点。
