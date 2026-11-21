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

HTTP 客户端在初始化和后续请求中携带相同的凭据。服务逐请求从请求头读取 Key，用完整凭据组合绑定会话，并按接口和 Key 隔离缓存与限频。工具参数只包含业务数据。写入需要 MCP 表单确认或浏览器确认。饮食模板查询和套用等待官方请求字段公开。

## Windows 和 Linux

克隆仓库后执行 `uv sync --locked --no-dev --python 3.12`。`uv` 会在需要时安装 Python 3.12。

- 客户端启动 Stdio 时使用 `uv --directory "<仓库绝对路径>" run --locked --no-dev xunji-private-mcp stdio`，在客户端的环境变量配置中填写 Key。
- 单独启动 HTTP 服务时使用 `uv run --locked --no-dev xunji-private-mcp http`，本机端点为 `http://127.0.0.1:8765/mcp`。
- 使用 GitHub Releases 下载的 wheel 时，执行 `uv tool install --python 3.12 ./<wheel 文件名>`。安装后可使用 `xunji-private-mcp stdio` 或 `xunji-private-mcp http`。

## Docker 与公开部署

在仓库目录执行 `docker compose up -d --build`。Compose 默认仅将 `8765` 发布到宿主机回环地址。也可以使用对应版本的 GHCR 镜像。

```sh
docker run -d --name xunji-private-mcp -p 127.0.0.1:8765:8765 --read-only --cap-drop ALL --security-opt no-new-privileges ghcr.io/vdk1639/xunji-private-mcp:<版本标签>
```

公开部署时，在 HTTPS 反向代理后运行 MCP，并发布 `https://mcp.example.com/mcp`。代理应保留原始 `Host`、MCP 会话头、`Authorization` 和 `X-Xunji-*` 请求头，关闭 `/mcp` 的响应缓冲、缓存和请求头日志，并设置请求速率及连接数上限。允许客户端等待至少 180 秒以便完成写入确认。

在 Compose 同目录的 `.env` 中设置 `XUNJI_HTTP_ALLOWED_HOSTS=mcp.example.com`，再运行 `docker compose up -d --force-recreate`。原生部署设置同名进程环境变量，`docker run` 部署通过 `-e` 传入。若客户端发送 `Origin`，通过 `XUNJI_HTTP_ALLOWED_ORIGINS` 设置其完整来源，例如 `https://chat.example.com`。多个值用逗号分隔，保留 `Host` 和 `Origin` 校验。使用一个 HTTP 服务实例以维持 MCP 会话。

公开端点的部署者和 TLS 终止代理能接触请求中的训记 Key 和返回数据。只连接可信端点。每套客户端凭据可以访问对应训记数据。多人共用一个 AstrBot 实例时，其一份 MCP 配置会被使用该工具的对话共用，因此应限制工具的使用范围，或为不同用户分别配置客户端实例。

只需私下跨主机访问时，可通过 SSH 转发远端回环端口，客户端仍连接 `http://127.0.0.1:8765/mcp`。

```sh
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 user@server.example.com
```

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

**写入确认**。AstrBot 使用网页确认时选择 Streamable HTTP。在训记 MCP 的 Compose `.env` 或容器环境里设置 `XUNJI_APPROVAL_BASE_URL=https://mcp.example.com`，重建 MCP 容器。该地址须能在用户的浏览器打开，只填写站点地址。支持 HTTPS 和回环 HTTP，例如经 SSH 转发的 `http://127.0.0.1:8765`。反向代理需把 `/approve/` 和 `/mcp` 转发到同一 MCP 实例，并关闭 `/approve/` 的缓存、访问日志和请求体日志。

AstrBot 可将工具返回的 `approval_url` 发给用户。用户在 **5 分钟内**打开自己的 MCP 确认页，输入对应业务的训记 API Key 查看摘要，然后点击确认或取消。提交结果显示在网页上。Key 在网页填写，避免发到聊天里。原生支持 MCP 表单的客户端继续使用原有确认流程。未启用网页确认时，AstrBot 的 Stdio 和不支持表单的 HTTP 客户端只能读取。

## 密钥轮换与故障处理

- HTTP 从服务端 `.env` 迁移时，把 Key 移到客户端的 `Authorization` 或 `X-Xunji-*` 请求头，并从部署配置删除旧值。Stdio 原用 `.env` 或 `--env-file` 的用户改用客户端环境变量。
- 获取新 Key 后更新客户端配置并重新连接。Stdio 客户端会启动新进程，HTTP 客户端会建立新会话。HTTP 服务可继续运行。训记拒绝 Key 或限频时，工具会返回对应错误。

## 开发与发布

`uv sync --locked --python 3.12` 安装测试依赖，`uv run pytest` 运行离线测试。GitHub Actions 在 Windows 和 Linux 验证 wheel 的 Stdio 接入，并在 Linux 验证 Compose 的 HTTP 接入。

发布时将与 `pyproject.toml` 版本一致的 `v*` 标签推送到 GitHub。发布流程上传 wheel 到 GitHub Releases，并将 `linux/amd64` 和 `linux/arm64` 镜像推送到 GHCR。新建镜像包时请在 GitHub Packages 确认镜像为公开可见，使用户可匿名拉取。

本项目采用 [MIT 许可](LICENSE)。
