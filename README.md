# xunji-private-mcp

使用训记官方 API 的 MCP 服务，支持 Windows、Linux 和 Docker，提供 Stdio 和 Streamable HTTP 两种连接方式。

| 模块 | 能力 | 客户端 Stdio 环境变量 | 客户端 HTTP 请求头 |
| --- | --- | --- | --- |
| 训练 | 读取和写回训练记录，查询官方训练计划 | `XUNJI_TRAIN_KEY` | `X-Xunji-Train-Key` |
| 饮食 | 读取和写回饮食记录，维护自定义食物 | `XUNJI_FOOD_KEY` | `X-Xunji-Food-Key` |
| 身体指标 | 按日期和指标读取和写入记录 | `XUNJI_BODY_KEY` | `X-Xunji-Body-Key` |
| Agent 个人模板 | 同步和维护专属文件夹中的训练模板 | `XUNJI_AGENT_TEMPLATE_KEY` | `X-Xunji-Agent-Template-Key` |

上表是训记账号的四个 Key。训记接口文档另为官方食物搜索接口 `api.xunjiapp.cn/open_agent/food/search_gzip` 列出一项独立凭据。只有拿到这项搜索凭据时才添加 `XUNJI_FOOD_SEARCH_KEY`（Stdio）或 `X-Xunji-Food-Search-Key`（HTTP）。普通饮食记录和自定义食物仅需饮食 Key。

按需配置客户端的环境变量或专用请求头。省略某个 Key 或将其留空，对应工具就不会出现在工具列表中，直接调用也会被拒绝。HTTP 兼容 `Authorization: Bearer <训记官方 Key>`。通用 Bearer 没有业务范围标记，服务会列出所有工具，对缺少专用请求头的调用交由训记验证。需要按已配置的 Key 精确启用工具时，只使用专用请求头。

HTTP 客户端在初始化和后续请求中携带相同的凭据。服务逐请求从请求头读取 Key，用完整凭据组合绑定会话，并按接口和 Key 隔离缓存与限频。工具参数只包含业务数据。

## ⚠️ 重要提示

### 食物搜索功能

食物搜索功能(`search_official_food`工具)需要单独的搜索凭据。只有配置了 `XUNJI_FOOD_SEARCH_KEY`(Stdio)或 `X-Xunji-Food-Search-Key`(HTTP)时,该工具才会出现在工具列表中。

普通饮食记录查询(`query_food_records`)、写入(`upsert_food_records`)和自定义食物(`upsert_custom_food`)仅需要饮食Key(`XUNJI_FOOD_KEY`)。

### 验证写入结果

写入训练后必须使用 `include_full_data=true` 验证。lite 模式（`include_full_data=false`）可能不返回未完成的训练，这是上游训记 API 的行为特性，MCP 无法在客户端修复。

## Windows 和 Linux

克隆仓库后执行 `uv sync --locked --no-dev --python 3.12`。`uv` 会在需要时安装 Python 3.12。

- 客户端启动 Stdio 时使用 `uv --directory "<仓库绝对路径>" run --locked --no-dev xunji-private-mcp stdio`，在客户端的环境变量配置中填写 Key。
- 单独启动 HTTP 服务时使用 `uv run --locked --no-dev xunji-private-mcp http`，本机端点为 `http://127.0.0.1:8765/mcp`。
- 使用 GitHub Releases 下载的 wheel 时，执行 `uv tool install --python 3.12 ./<wheel 文件名>`。安装后可使用 `xunji-private-mcp stdio` 或 `xunji-private-mcp http`。

## Docker 快速部署

### 私有部署（推荐）

无需克隆仓库，直接使用 GHCR 镜像部署：

```sh
# 使用 Docker Compose（推荐）
curl -O https://raw.githubusercontent.com/Vdk1639/xunji-private-mcp/main/docker-compose.quickstart.yaml
docker compose -f docker-compose.quickstart.yaml up -d

# 或使用 Docker Run
docker run -d \
  --name xunji-private-mcp \
  -p 127.0.0.1:8765:8765 \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --restart unless-stopped \
  ghcr.io/vdk1639/xunji-private-mcp:latest
```

**访问地址**：`http://127.0.0.1:8765/mcp`

### 容器间通信（与 AstrBot 等容器集成）

```sh
# 使用 Docker Compose（推荐）
curl -O https://raw.githubusercontent.com/Vdk1639/xunji-private-mcp/main/docker-compose.quickstart-internal.yaml
docker compose -f docker-compose.quickstart-internal.yaml up -d

# 或连接到现有容器网络
docker run -d \
  --name xunji-private-mcp \
  --network <客户端容器的网络名> \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --restart unless-stopped \
  ghcr.io/vdk1639/xunji-private-mcp:latest
```

**容器内访问地址**：`http://xunji-private-mcp:8765/mcp`

**配置 AstrBot**：详见 [AstrBot 部署指南](docs/ASTRBOT_DEPLOYMENT.md)（包含 AI Agent 自动部署提示词）

更多配置见 [快速部署指南](docs/QUICKSTART.md) 和 [AstrBot 集成文档](docs/ASTRBOT_INTEGRATION.md)。

### 从源码构建

在仓库目录执行：

```sh
docker compose up -d --build
```

### ⚠️ 公网部署（不推荐）

**强烈不推荐公网部署**。公网暴露 MCP 服务存在以下风险：

- 🔓 请求中的训记 API Key 可能被代理、日志或监控系统记录
- 👁️ MCP 端点部署者和 TLS 终止代理能接触所有请求和返回数据
- 👥 多人共用同一客户端实例时，所有用户共享同一套 API Key
- 🚨 需要妥善配置反向代理、速率限制、访问控制和日志脱敏

**推荐替代方案**：

- ✅ **私有部署**：仅绑定本地回环地址 `127.0.0.1:8765`
- ✅ **SSH 隧道**：跨主机访问使用 SSH 端口转发

```sh
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 user@server.example.com
```

如果确实需要公网部署（例如团队内网或受控环境），**必须**：

1. ✅ 配置 HTTPS 反向代理（Nginx/Caddy/Traefik）
2. ✅ 禁用 `/mcp` 和 `/approve/` 的请求头日志（避免记录 API Key）
3. ✅ 配置速率限制和连接数上限
4. ✅ 限制访问来源（IP 白名单或基础认证）
5. ✅ 设置 `XUNJI_HTTP_ALLOWED_HOSTS` 为你的域名
6. ✅ 定期轮换训记 API Key

详细配置见 [反向代理文档](docs/REVERSE_PROXY.md)。

公开端点的部署者和 TLS 终止代理能接触请求中的训记 Key 和返回数据。只连接可信端点。每套客户端凭据可以访问对应训记数据。多人共用一个 AstrBot 实例时，其一份 MCP 配置会被使用该工具的对话共用，因此应限制工具的使用范围，或为不同用户分别配置客户端实例。

## 客户端配置

将示例中的地址、仓库路径和占位值替换为实际配置，并删除没有 Key 的配置项。真实 Key 请放在客户端的私有配置中，避免放进聊天内容或项目仓库。

### Codex

在用户级 `~/.codex/config.toml` 中选择一种配置。以下环境变量设置在运行 Codex 的环境中。

```toml
[mcp_servers.xunji-private-mcp]
command = "uv"
args = ["--directory", "<仓库绝对路径>", "run", "--locked", "--no-dev", "xunji-private-mcp", "stdio"]
env_vars = ["XUNJI_TRAIN_KEY", "XUNJI_FOOD_KEY", "XUNJI_BODY_KEY", "XUNJI_AGENT_TEMPLATE_KEY"]
tool_timeout_sec = 180
```

```toml
[mcp_servers.xunji-private-mcp]
url = "https://mcp.example.com/mcp"
env_http_headers = { "X-Xunji-Train-Key" = "XUNJI_TRAIN_KEY", "X-Xunji-Food-Key" = "XUNJI_FOOD_KEY", "X-Xunji-Body-Key" = "XUNJI_BODY_KEY", "X-Xunji-Agent-Template-Key" = "XUNJI_AGENT_TEMPLATE_KEY" }
tool_timeout_sec = 180
```

只使用训练 Key 时，可在 `env_http_headers` 中仅保留 `X-Xunji-Train-Key`。使用通用 Bearer 的配置为 `bearer_token_env_var = "XUNJI_TRAIN_KEY"`，替换整个 `env_http_headers` 项。

### Claude Code

以下命令使用用户级配置，客户端直接使用训练 Key。需要使用其他功能时，可以按上表追加 `--env` 或 `--header`。

```sh
claude mcp add --scope user --transport stdio --env "XUNJI_TRAIN_KEY=<TRAIN_KEY>" xunji-private-mcp -- uv --directory "<仓库绝对路径>" run --locked --no-dev xunji-private-mcp stdio
claude mcp add --scope user --transport http --header "X-Xunji-Train-Key: <TRAIN_KEY>" xunji-private-mcp https://mcp.example.com/mcp
```

### AstrBot

在 `插件 → MCP → 新增服务器` 输入名称 `xunji-private-mcp`，选择对应的传输模板，将下面一个 JSON 对象粘贴到「服务器配置」。替换占位值后测试连接、保存，并在人格能力中启用所需工具。两种配置的字段可参阅 [AstrBot MCP 文档](https://docs.astrbot.app/use/mcp.html)。

**Stdio**。`uv` 和仓库必须位于 AstrBot 的运行环境中。AstrBot 若运行在容器中，这里的路径使用容器内路径。

```json
{
  "command": "uv",
  "args": ["--directory", "<仓库绝对路径>", "run", "--locked", "--no-dev", "xunji-private-mcp", "stdio"],
  "env": {
    "XUNJI_TRAIN_KEY": "<TRAIN_KEY>",
    "XUNJI_FOOD_KEY": "<FOOD_KEY>",
    "XUNJI_BODY_KEY": "<BODY_KEY>",
    "XUNJI_AGENT_TEMPLATE_KEY": "<AGENT_TEMPLATE_KEY>"
  }
}
```

**Streamable HTTP**。`url` 使用 AstrBot 运行环境可访问的地址。容器内的 `127.0.0.1` 指向容器自身。`headers` 中保留要启用的功能对应的 `X-Xunji-*` 请求头。

```json
{
  "transport": "streamable_http",
  "url": "https://mcp.example.com/mcp",
  "headers": {
    "X-Xunji-Train-Key": "<TRAIN_KEY>",
    "X-Xunji-Food-Key": "<FOOD_KEY>",
    "X-Xunji-Body-Key": "<BODY_KEY>",
    "X-Xunji-Agent-Template-Key": "<AGENT_TEMPLATE_KEY>"
  },
  "timeout": 30,
  "sse_read_timeout": 300
}
```

## 密钥轮换与故障处理

- HTTP 从服务端 `.env` 迁移时，把 Key 移到客户端的 `Authorization` 或 `X-Xunji-*` 请求头，并从部署配置删除旧值。Stdio 原用 `.env` 或 `--env-file` 的用户改用客户端环境变量。
- 获取新 Key 后更新客户端配置并重新连接。Stdio 客户端会启动新进程，HTTP 客户端会建立新会话。HTTP 服务可继续运行。训记拒绝 Key 或限频时，工具会返回对应错误。

## 开发与发布

`uv sync --locked --python 3.12` 安装测试依赖，`uv run pytest` 运行离线测试。GitHub Actions 在 Windows 和 Linux 验证 wheel 的 Stdio 接入，并在 Linux 验证 Compose 的 HTTP 接入。

发布时将与 `pyproject.toml` 版本一致的 `v*` 标签推送到 GitHub。发布流程上传 wheel 到 GitHub Releases，并将 `linux/amd64` 和 `linux/arm64` 镜像推送到 GHCR。新建镜像包时请在 GitHub Packages 确认镜像为公开可见，使用户可匿名拉取。

本项目采用 [MIT 许可](LICENSE)。
