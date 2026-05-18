<!-- author: wanghaobo -->

# ArcReel 本地开发启动指南

> 一键拉起 ArcReel 前后端开发环境。脚本位于本目录，所有运行时数据放在 `/tmp/arcreel-dev/`。

## TL;DR

```bash
# 启动（首次自动装依赖 + 跑数据库迁移）
bash scripts/dev/start.sh

# 状态
bash scripts/dev/status.sh

# 停止
bash scripts/dev/stop.sh
```

启动成功后访问：

- **前端入口**：<http://localhost:5173>
- **后端 API**：<http://127.0.0.1:1241>（Vite 已把 `/api` 代理过去）
- **登录账号**：`admin` / 密码自动生成并写回 `.env` 的 `AUTH_PASSWORD`
- **配置 API Key**：登录后进 `/settings`

## 环境前置要求

| 组件 | 版本要求 | 安装建议 |
|------|---------|---------|
| Python | 3.12+ | uv 自带托管 |
| [uv](https://docs.astral.sh/uv/) | 最新 | `brew install uv` 或 `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | **20.19+ 或 22.12+**（Vite 8 硬要求）| `nvm install 22` |
| pnpm | 10+ | `npm i -g pnpm` |
| ffmpeg | 任意 | `brew install ffmpeg`（视频拼接用） |

`start.sh` 会自动：

1. 加载 `~/.nvm/nvm.sh`，找一个已安装的兼容 Node 切过去；都不满足则 `nvm install 22`
2. 没有 `.venv` 时 `uv sync`；有但缺核心包时 fallback 到 `pip install -e .`
3. 没有 `frontend/node_modules` 时 `pnpm install`
4. 跑 `alembic upgrade head`
5. `nohup` 后台启动前后端，PID 与日志放在 `/tmp/arcreel-dev/`

## npm 镜像源说明

如果你机器 `~/.npmrc` 指向了内部镜像（例如 `npm.corp.kuaishou.com`），rolldown 的 `@rolldown/binding-darwin-arm64` 等 optional native 包可能拉不到。本项目已经在 `frontend/.npmrc` 写了：

```ini
registry=https://registry.npmjs.org/
```

仅在前端项目下覆盖，不动你全局 `~/.npmrc`。

## 环境变量（可选覆盖）

| 变量 | 默认 | 说明 |
|------|------|------|
| `BACKEND_HOST` | `127.0.0.1` | 后端绑定地址 |
| `BACKEND_PORT` | `1241` | 后端端口 |
| `FRONTEND_PORT` | `5173` | 前端端口 |
| `RUNTIME_DIR` | `/tmp/arcreel-dev` | PID / 日志目录 |

例：换端口启动

```bash
BACKEND_PORT=2241 FRONTEND_PORT=6173 bash scripts/dev/start.sh
```

## 运行时文件

```
/tmp/arcreel-dev/
├── backend.pid       # 后端 uvicorn 主进程 pid
├── backend.log       # 后端日志（uvicorn + 应用）
├── frontend.pid      # 前端 vite 进程 pid
└── frontend.log      # 前端日志（vite）
```

实时跟日志：

```bash
tail -f /tmp/arcreel-dev/backend.log
tail -f /tmp/arcreel-dev/frontend.log
```

## 常见问题

### 1. 启动后页面 502 / 拉不到 `/api/...`

后端可能还没就绪。查 `backend.log`：

```bash
tail -n 50 /tmp/arcreel-dev/backend.log
```

看到 `Application startup complete` 表示就绪。

### 2. 端口被占用

`start.sh` 会检测端口是否在用，被别的进程占了会直接报错。可以：

```bash
# 看看是谁
lsof -nP -iTCP:1241 -sTCP:LISTEN
# 或者换端口
BACKEND_PORT=2241 bash scripts/dev/start.sh
```

### 3. 忘了密码

`.env` 里的 `AUTH_PASSWORD` 就是。想重置：清空它，重启后端会重新生成。

```bash
# 编辑 .env，把 AUTH_PASSWORD= 后面留空
bash scripts/dev/stop.sh && bash scripts/dev/start.sh
```

### 4. Node 版本切换

`start.sh` 只对当前调用临时切 Node。想让新开终端也默认用 22：

```bash
nvm alias default 22
```

### 5. 数据库重建

开发态用 SQLite，文件在 `projects/.arcreel.db`。想清零：

```bash
bash scripts/dev/stop.sh
rm projects/.arcreel.db
.venv/bin/alembic upgrade head    # 或直接重启 start.sh
```

## 配置 API Key

启动后进 <http://localhost:5173/settings>：

1. **ArcReel 智能体**（必填）—— 配置 Anthropic API Key 与 Base URL，驱动 Claude Agent SDK
2. **AI 生图 / 生视频 / 生文本**（至少配一家）—— Gemini / 火山方舟 / Grok / OpenAI / Vidu，也可加自定义供应商

> 注意：根据 sandbox 设计，**所有 provider 密钥必须在 WebUI 配置**，不要写进 `.env` —— 父进程 `os.environ` 不能包含 provider 密钥。
