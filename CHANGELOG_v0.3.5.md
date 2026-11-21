# v0.3.5 更新日志

**发布日期**: 2026-11-21

## 🎯 核心变更

### 简化架构：移除写入确认机制

**背景**: 
- 写入确认机制（approval）为可选特性，增加了部署复杂度
- 大多数用户场景不需要额外确认步骤
- 浏览器确认需要额外配置和路由设置

**改进**: 
- **完全移除** approval 机制相关代码
- 写入操作现在直接执行，无需确认步骤
- 简化了服务器配置（移除 `XUNJI_APPROVAL_BASE_URL`）
- 减少了依赖和代码维护成本

### 移除 delete_training 工具

**原因**:
- 上游训记 API 不提供删除训练记录的接口
- 工具无法实现真正的删除功能
- 保留该工具会误导用户

**影响**: 
- 工具总数从 12 个减少到 11 个
- 用户需要在训记 App 中手动删除记录

## 📋 详细变更

### 删除的文件
- `src/xunji_private_mcp/interaction.py` - approval 核心逻辑
- `src/xunji_private_mcp/approval.py` - 浏览器确认功能

### 新增的文件
- `src/xunji_private_mcp/exceptions.py` - 统一的异常定义（`ToolError`）

### 修改的文件

#### `training.py`
- 移除 `delete_training` 工具定义
- 移除 `upsert_training` 中的 `approve_write` 调用
- 直接调用上游 API，无确认步骤

#### `food.py`
- 移除 `upsert_food` 中的 `approve_write` 调用
- 直接执行写入操作

#### `body.py`
- 移除 `upsert_body` 中的 `approve_write` 调用
- 直接执行写入操作

#### `templates.py`
- 移除 `upsert_template` 中的 `approve_write` 调用
- 直接执行写入操作

#### `server.py`
- 移除 `approval_origin` 参数
- 移除 `BrowserApprovals` 初始化
- 移除 `/approve/` 路由
- 简化 server instructions，移除确认相关说明
- 移除 `XUNJI_APPROVAL_BASE_URL` 环境变量读取

#### `upstream.py`
- 更新导入：从 `exceptions` 导入 `ToolError`

#### `README.md`
- 移除"写入确认"整个章节
- 移除 approval 相关配置说明
- 简化部署说明

#### `tests/test_server.py`
- 移除 `test_delete_training_tool` 测试
- 更新工具总数断言：12 → 11

## 🔧 配置变更

### 移除的环境变量
- `XUNJI_APPROVAL_BASE_URL` - 不再需要

### 移除的路由
- `/approve/` - 浏览器确认页面

## ⚡ 性能影响

- **响应速度提升**: 写入操作不再需要等待用户确认
- **代码量减少**: 删除约 400+ 行 approval 相关代码
- **部署简化**: 无需配置额外的确认 URL 和路由

## 🧪 测试建议

1. **基础功能测试**
   ```bash
   # 本地测试
   uv run pytest
   
   # Docker 部署测试
   docker compose up --build
   ```

2. **写入操作测试**
   - 测试 `upsert_training` 直接写入
   - 测试 `upsert_food` 直接写入
   - 测试 `upsert_body` 直接写入
   - 测试 `upsert_template` 直接写入
   - 验证所有写入操作无需确认即可完成

3. **工具列表验证**
   - 确认工具总数为 11 个
   - 确认 `delete_training` 不在列表中

## 📝 升级指南

### 从 v0.3.4 升级

1. **移除配置**（如果之前设置过）
   ```bash
   # docker-compose.yaml 或 .env 中删除
   # XUNJI_APPROVAL_BASE_URL=...
   ```

2. **重新构建镜像**
   ```bash
   docker compose down
   docker compose up --build -d
   ```

3. **验证部署**
   ```bash
   curl http://localhost:8765/health
   # 应返回: OK
   ```

4. **更新客户端预期**
   - 写入操作将立即执行
   - 不再返回 `approval_url`
   - `delete_training` 工具不再可用

## ⚠️ 破坏性变更

1. **写入操作行为变更**
   - 之前: 返回 `approval_required` 等待确认
   - 现在: 直接执行并返回结果
   
2. **工具移除**
   - `delete_training` 工具不再存在
   - 调用该工具会返回"工具不存在"错误

3. **配置参数移除**
   - `XUNJI_APPROVAL_BASE_URL` 不再有效
   - `/approve/` 路由返回 404

## 🎉 优势总结

- ✅ **部署更简单**: 无需配置确认 URL
- ✅ **代码更清晰**: 移除可选特性，降低维护成本
- ✅ **响应更快**: 写入操作直接执行
- ✅ **配置更少**: 减少环境变量和路由设置

## 🔮 未来计划

- 如果用户需要"确认"功能，可以在客户端层面实现
- 专注于核心 MCP 工具功能
- 考虑添加更多训记 API 支持的功能
