# xunji-private-mcp

使用训记官方 API 的私人 MCP 服务，支持 Windows、Linux 及 Docker，提供 `stdio` 和 Streamable HTTP 两种连接方式。

| 模块 | 能力 | 服务器环境变量 |
| --- | --- | --- |
| 训练 | 读取和写回训练记录，查询官方训练计划 | `XUNJI_TRAIN_KEY` |
| 饮食 | 读取和写回饮食记录，维护自定义食物 | `XUNJI_FOOD_KEY` |
| 食物搜索 | 搜索训记官方食物 | `XUNJI_FOOD_SEARCH_KEY` |
| 身体指标 | 按日期和指标读取和写入记录 | `XUNJI_BODY_KEY` |
| Agent 个人模板 | 同步、维护专属文件夹中的训练模板 | `XUNJI_AGENT_TEMPLATE_KEY` |

写入需要客户端支持 MCP 表单确认。客户端无法展示确认时，可以使用查询工具。饮食模板查询和套用等待官方请求字段公开。

## Windows 和 Linux

克隆本仓库并在仓库目录执行以下命令。`uv` 会在需要时安装 Python 3.12。

```powershell
uv sync --locked --no-dev --python 3.12
Copy-Item .env.example .env
```

Linux 使用 `cp .env.example .env`，可用 `chmod 600 .env` 限制文件权限。编辑 `.env`，按需填入从训记 App 获取的 Key。设置的进程环境变量优先于 `.env`。服务默认从当前目录读取 `.env`，也可用全局参数 `--env-file` 或 `XUNJI_ENV_FILE` 指定绝对路径。

- 客户端以子进程启动 `stdio`。配置命令为 `uv --directory "<仓库绝对路径>" run --locked --no-dev xunji-private-mcp stdio`。
- 单独启动本机 HTTP 服务时，执行 `uv run --locked --no-dev xunji-private-mcp http`。在客户端使用 `http://127.0.0.1:8765/mcp`。
- 使用 GitHub Releases 下载的 wheel 时，执行 `uv tool install --python 3.12 ./xunji_private_mcp-0.1.0-py3-none-any.whl`。替换为实际文件名后，可通过 `xunji-private-mcp --env-file "<.env 绝对路径>" stdio` 或对应的 `http` 子命令启动。

## Docker

在 Linux Docker 或 Windows Docker Desktop 的 Linux 容器模式下，在仓库目录配置 `.env`，然后运行：

```sh
docker compose up -d --build
```

GitHub 发布后也可使用对应版本的预构建镜像，将 `<owner>` 替换为小写的 GitHub 仓库所有者。

```sh
docker run -d --name xunji-private-mcp --env-file .env -p 127.0.0.1:8765:8765 --read-only --cap-drop ALL --security-opt no-new-privileges ghcr.io/<owner>/xunji-private-mcp:v0.1.0
```

本机 HTTP 地址为 `http://127.0.0.1:8765/mcp`。服务器检查 `Host` 和 `Origin`，端口上的其他本机进程也能访问 MCP。仅在可信的单用户环境中启用 HTTP。跨主机访问可使用 SSH 将远端回环端口转发到本机，并限制 SSH 账户的访问权限。

```sh
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 user@server.example.com
```

## 客户端配置

以下示例中的 `<仓库绝对路径>` 请替换为本机路径。图形客户端找不到 `uv` 时，可将 `command` 替换为 `uv` 的绝对路径。已安装 wheel 的用户可改用 `xunji-private-mcp` 命令及 `--env-file`。

### Codex

在 `~/.codex/config.toml` 中添加 `stdio` 配置。若要用 HTTP，则只保留 `url = "http://127.0.0.1:8765/mcp"` 与 `tool_timeout_sec`，并提前启动 HTTP 服务。写入时在客户端弹出的 MCP 表单里审核变更。

```toml
[mcp_servers.xunji-private-mcp]
command = "uv"
args = ["--directory", "<仓库绝对路径>", "run", "--locked", "--no-dev", "xunji-private-mcp", "stdio"]
tool_timeout_sec = 180
```

### VS Code

用 `MCP: Open User Configuration` 打开用户级 MCP 配置。HTTP 连接示例如下。使用 `stdio` 时可把 `type` 改为 `stdio`，并将 `url` 换成与上例相同的 `command` 和 `args`。

```json
{
  "servers": {
    "xunji-private-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

### Claude Code

任选一种连接，HTTP 方式需要先启动服务。

```sh
claude mcp add --scope user --transport stdio xunji-private-mcp -- uv --directory "<仓库绝对路径>" run --locked --no-dev xunji-private-mcp stdio
claude mcp add --scope user --transport http xunji-private-mcp http://127.0.0.1:8765/mcp
```

## 密钥轮换与故障处理

- 在训记 App 获取新 Key 后更新对应的环境变量或 `.env` 项。原生部署重启 MCP 进程，Compose 运行 `docker compose up -d --force-recreate`，`docker run` 部署重建容器。轮换无需改源码或重新构建镜像。
- 缺少或失效的 Key 只影响对应工具。失效提示出现时核对 App 中的授权及会员状态。如遇限频，按工具给出的等待时间再试。
- 真实 Key 和含 Key 的训记附件请保存在本机。`.env.example` 可提交，`.env` 不应提交。HTTP MCP 复用服务器所配的训记账户。

## 开发与发布

`uv sync --locked --python 3.12` 安装测试依赖，`uv run pytest` 运行离线测试。GitHub Actions 在 Windows 和 Linux 验证 wheel 的 `stdio` 接入，并在 Linux 验证 Compose 的 HTTP 接入。

发布时将与 `pyproject.toml` 版本一致的 `v*` 标签推送到 GitHub。发布流程上传 wheel 到 GitHub Releases，并将 `linux/amd64` 和 `linux/arm64` 镜像推送到 GHCR。首发后在 GitHub Packages 为该镜像设置公开可见性，使用户可匿名拉取。

本项目采用 [MIT 许可](LICENSE)。
