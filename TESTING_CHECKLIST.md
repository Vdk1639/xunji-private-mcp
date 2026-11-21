# 训记 MCP v0.3.4 功能验证清单

## 修复内容

### 1. Approval 机制修复
- **问题**：AstrBot 客户端不支持 elicitation，且未配置浏览器确认时会卡死 60 秒
- **修复**：提前检测客户端能力，返回清晰的错误提示而非尝试 elicit
- **文件**：`src/xunji_private_mcp/interaction.py`

### 2. 新增 delete_training 工具
- **说明**：由于上游 API 不提供删除接口，工具会返回清晰说明，指导用户在 App 中操作
- **文件**：`src/xunji_private_mcp/training.py`, `server.py`

## 测试环境

- **树莓派**：192.168.1.10
- **MCP 容器**：xunji-private-mcp (内部地址 http://xunji-private-mcp:8765/mcp)
- **AstrBot 容器**：astrbot
- **当前版本**：0.3.3 → 0.3.4

## 测试步骤

### Phase 1: 基础连通性测试

```bash
# 1. 检查容器状态
docker ps | grep -E "astrbot|xunji"

# 2. 检查网络连接
docker network inspect $(docker inspect astrbot -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}') | grep xunji

# 3. 测试 tools/list 端点
curl -X POST http://xunji-private-mcp:8765/mcp \
  -H "Content-Type: application/json" \
  -H "X-Xunji-Train-Key: <TRAIN_KEY>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Phase 2: Approval 机制测试

**场景 A：未配置 XUNJI_APPROVAL_BASE_URL**
- 预期：调用 upsert_training 时立即返回清晰错误，不会卡死
- 错误应包含："不支持 MCP 表单确认" 和 "XUNJI_APPROVAL_BASE_URL"

**场景 B：配置 XUNJI_APPROVAL_BASE_URL**
- 设置环境变量：`XUNJI_APPROVAL_BASE_URL=http://192.168.1.10:8765`
- 预期：返回 approval_url
- 验证：打开链接能显示确认页面

### Phase 3: 工具列表验证

验证所有 12 个工具（原 11 个 + 新增的 delete_training）：

#### Training Tools (5)
- [ ] get_training
- [ ] upsert_training
- [ ] delete_training ⭐ 新增
- [ ] list_official_plans
- [ ] get_official_plan

#### Food Tools (4)
- [ ] query_food_records
- [ ] search_official_food
- [ ] upsert_food_records
- [ ] upsert_custom_food

#### Body Tools (2)
- [ ] query_body_metrics
- [ ] upsert_body_metrics

#### Template Tools (2)
- [ ] sync_agent_templates
- [ ] mutate_agent_templates

### Phase 4: 核心功能测试

#### 4.1 读取训练记录
```bash
# 测试 get_training（轻量模式）
curl -X POST http://xunji-private-mcp:8765/mcp \
  -H "X-Xunji-Train-Key: <KEY>" \
  -d '{
    "jsonrpc":"2.0",
    "id":2,
    "method":"tools/call",
    "params":{
      "name":"get_training",
      "arguments":{"datestr":"2026-11-21","include_full_data":false}
    }
  }'

# 测试完整模式
curl -X POST http://xunji-private-mcp:8765/mcp \
  -H "X-Xunji-Train-Key: <KEY>" \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
      "name":"get_training",
      "arguments":{"datestr":"2026-11-21","include_full_data":true}
    }
  }'
```

#### 4.2 测试写入（带确认）
```bash
# 应返回 approval_url 或明确错误
curl -X POST http://xunji-private-mcp:8765/mcp \
  -H "X-Xunji-Train-Key: <KEY>" \
  -d '{
    "jsonrpc":"2.0",
    "id":4,
    "method":"tools/call",
    "params":{
      "name":"upsert_training",
      "arguments":{
        "trains":[{
          "datestr":"2026-11-22",
          "title":"测试训练",
          "start":1732233600000,
          "end":1732237200000,
          "movements":[{
            "name":"杠铃卧推",
            "sets":[{"weight":"60","unit":"kg","reps":"10","done":true}]
          }]
        }],
        "client_request_id":"test-001"
      }
    }
  }'
```

#### 4.3 测试新增的 delete_training
```bash
# 应返回清晰的说明消息
curl -X POST http://xunji-private-mcp:8765/mcp \
  -H "X-Xunji-Train-Key: <KEY>" \
  -d '{
    "jsonrpc":"2.0",
    "id":5,
    "method":"tools/call",
    "params":{
      "name":"delete_training",
      "arguments":{
        "datestr":"2026-11-21",
        "localid":1795203247936001,
        "client_request_id":"del-001"
      }
    }
  }'
```

### Phase 5: 回归测试

- [ ] lite 模式能返回未完成训练（验证之前的修复未退化）
- [ ] 读取功能的缓存和限频正常工作
- [ ] 其他模块（food, body, templates）未受影响

### Phase 6: AstrBot 集成测试

1. 在 AstrBot 的 MCP 配置中更新镜像
2. 重启 AstrBot 服务
3. 在对话中测试调用训练读取工具
4. 测试写入工具的确认流程
5. 验证 delete_training 返回的说明信息

## 验收标准

### 必须通过
- [x] Docker 镜像构建成功
- [ ] tools/list 返回 12 个工具
- [ ] 未配置 XUNJI_APPROVAL_BASE_URL 时返回清晰错误（不卡死）
- [ ] 配置后能返回 approval_url
- [ ] delete_training 返回清晰的说明消息
- [ ] get_training 读取功能正常

### 应该通过
- [ ] 浏览器确认流程完整可用
- [ ] AstrBot 能成功调用所有读取工具
- [ ] 所有 4 类工具（训练/饮食/身体/模板）正常工作

### 已知限制
- delete_training 不会真正删除记录（上游 API 限制）
- 写入操作需要配置 XUNJI_APPROVAL_BASE_URL 才能在 AstrBot 中使用

## 问题记录

### 发现的问题
（在测试过程中记录）

### 已解决的问题
1. ✅ Approval 机制卡死 → 提前检测能力并返回清晰错误
2. ✅ 缺少 delete_training 工具 → 已添加（带说明）

## 下一步

测试通过后：
1. 提交代码到 git
2. 打标签 v0.3.4
3. 推送到 GitHub
4. 验证 GitHub Actions 构建和发布
