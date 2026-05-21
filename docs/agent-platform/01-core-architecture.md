# 01 · 核心架构抽丝剥茧

Author: wanghaobo

本章把 ArcReel 后端从外向内一层层剥开，每剥一层都明确：**哪些是通用 agent 平台的核心，哪些是短剧业务的特化**。

---

## 0. 进入点：FastAPI App

文件：[`server/app.py`](../../server/app.py)

`lifespan()` 启动时按顺序做了 8 件事，可以全部记住：

1. **Fail-fast 安全红线** — `assert_no_provider_secrets_in_environ()`：父进程 env 不能持有任何 provider 密钥（必须沉到 DB）
2. **沙箱探测** — `check_sandbox_available()`：macOS `sandbox-exec` / Linux `bwrap+socat` / Windows 自动降级
3. **DB 初始化** — `init_db()` 跑 Alembic 迁移
4. **项目数据迁移** — `run_project_migrations()` 跑 file-based schema 升级
5. **源文件编码迁移** — 一次性把存量项目的小说源文件统一成 UTF-8
6. **Session Store transcript 迁移** — 把本地 jsonl transcript 镜像进 DB
7. **JSON→DB 配置迁移** — 把老版 `.system_config.json` 升级到 ConfigService
8. **Agent Profile 同步** — 把 `agent_runtime_profile/` 物化到所有项目（manifest + sha256）
9. **启动后台服务** — 共享 httpx client / `AssistantService.startup()` / `GenerationWorker.start()` / `ProjectEventService.start()`

**架构关键点**：app 启动只做**装配 + 校验**，业务逻辑全部在 service / lib 中。这是后续你能在不动 app.py 的前提下挂入新 agent 能力的前提。

---

## 1. 基础设施层（Platform Infra）

> 完全通用，所有 agent 共享。

### 1.1 数据库与持久化

[`lib/db/`](../../lib/db/) — SQLAlchemy Async ORM。

```
lib/db/
├── engine.py              ← async engine + session factory（DATABASE_URL 默认 sqlite+aiosqlite）
├── base.py                ← Base / UserOwnedMixin / DEFAULT_USER_ID
├── models/
│   ├── task.py            ← Task / TaskEvent / WorkerLease  ★执行层核心
│   ├── api_call.py        ← UsageTracker 记录每次调用 + 费用
│   ├── api_key.py
│   ├── asset.py           ← 跨项目复用的全局资产库
│   ├── config.py          ← 系统/项目级配置
│   ├── credential.py      ← 多 API Key + 活跃切换
│   ├── custom_provider.py ← 用户自定义供应商 + 模型子表
│   ├── session.py         ← AgentSession（agent runtime transcript 镜像）
│   └── user.py
└── repositories/          ← 与 model 一一对应的异步 Repo
```

**通用与否**：这一层完全是平台基建。`Task` 和 `WorkerLease` 不区分业务类型，`task_type` 是个字符串字段，未来加 `highlight_clip` / `marketing_video` 等都不需要改 schema。

### 1.2 配置 & 供应商目录（关键解耦）

[`lib/config/`](../../lib/config/) — 三件套：

| 文件 | 角色 |
| --- | --- |
| `registry.py` | 预置供应商注册表 `PROVIDER_REGISTRY: dict[str, ProviderMeta]`，每条带 `models / required_keys / secret_keys / default_base_url` |
| `service.py` | `ConfigService`：读写 system/project 级配置（DB 持久化） |
| `resolver.py` | `ConfigResolver`：把"项目偏好 → 全局默认 → 注册表 fallback"的解析逻辑收敛在这 |
| `repository.py` | 凭证脱敏与持久化 |

**架构关键点**：所有"用什么供应商 / 用什么模型 / 用什么 API Key"的解析全部走 `ConfigResolver`。Agent 运行时不感知具体供应商。

### 1.3 项目管理与目录结构

[`lib/project_manager.py`](../../lib/project_manager.py) — `ProjectManager`：

```
projects/<project>/
├── project.json              ← 项目元数据 + 资产定义（character/scene/prop）单一事实源
├── source/                   ← 输入素材（小说 txt/docx/pdf）
├── scripts/                  ← 中间产物：剧本 JSON
├── characters/ scenes/ props/← 资产 sheet 图（资产规格在 lib/asset_types.py::ASSET_SPECS 统一）
├── storyboards/ grids/       ← 分镜图 / 宫格图
├── videos/ thumbnails/       ← 视频片段 + 缩略图
├── output/                   ← 最终成片
├── drafts/                   ← skill 中间过程（人类可读）
├── .claude/ + CLAUDE.md      ← profile manifest 同步过来的 agent 配置
└── .arcreel_profile_manifest.json
```

**业务相关 vs 通用**：`SUBDIRS` 列表是业务相关（短剧才需要 `storyboards`/`grids`），但 `ProjectManager` 本身是通用的——它提供"创建/校验/路径解析/原子写"等基础能力，每个 capability pack 可以按需扩展子目录。

### 1.4 Profile Manifest（agent 配置同步）

[`lib/profile_manifest.py`](../../lib/profile_manifest.py)

把 `agent_runtime_profile/` 下的 `.claude/skills/` `.claude/agents/` `CLAUDE.<mode>.md` 通过 manifest + sha256 同步到每个项目。区分三种状态：

- **内置（builtin）** — 跟着 profile 升级
- **用户改过（user-modified）** — 不覆盖
- **用户删过（tombstone）** — 不重新生成

**架构关键点**：这是"装载 capability pack"的物理通道。新增一个 agent 业务包，本质就是往 `agent_runtime_profile/` 加文件，让所有项目下次启动自动同步到位。

### 1.5 沙箱（Linux/macOS）+ Hooks（PreToolUse/PostToolUse）

`server/app.py::check_sandbox_available()` 和 SDK 的 `SandboxSettings` 一起，给 agent 的 `Bash`/`Read`/`Write` 工具加一层文件系统/网络隔离。Hooks 在工具调用前后做白名单校验、敏感文件保护、JSON 校验。

**通用**：与具体 agent 业务无关。

### 1.6 i18n

[`lib/i18n/`](../../lib/i18n/) — 翻译器 `Translator: Annotated[Callable[..., str], Depends(get_translator)]`。新加的 agent 能力在面向用户的文案里也走同一套 `_t("key")`。

---

## 2. 执行层（Async Generation Engine）

> 完全通用。是平台最具复用价值的一层。

### 2.1 任务模型

```
入队  ────►  GenerationQueue.enqueue_task(...)         ► tasks 表 (status=queued)
                     │
Worker ────►  claim_next_task(media_type)               ► status=running, lease 续约
                     │
执行  ────►  execute_generation_task(task)              ► server/services/generation_tasks.py
                     │
完成  ────►  mark_task_succeeded(...) / mark_task_failed(...)
                     │
事件  ────►  task_events 表（前端 SSE 增量获取）
```

[`lib/generation_queue.py`](../../lib/generation_queue.py)：单进程模式下也能跑，靠 `WorkerLease`（DB 行锁 + TTL）保证单 active worker，崩溃后自动回收 `running` 任务。

### 2.2 Worker 调度策略

[`lib/generation_worker.py`](../../lib/generation_worker.py) — `GenerationWorker`：

- 按 **供应商 × 媒体类型** 维度独立并发池（`ProviderPool`），每个池独立 `image_max` / `video_max`
- 池配置从 `ConfigService` 读，可热加载（`reload_limits()`），不影响 in-flight
- `_extract_provider()` 优先级：`payload 显式 > 项目级 video_backend/image_backend > 全局默认`
- 池满时把任务退回 `queued`（FIFO 兼容），避免无限循环领同一个

### 2.3 入队-等待客户端

[`lib/generation_queue_client.py`](../../lib/generation_queue_client.py)：

- `enqueue_and_wait()` — 入队并阻塞等待（轮询 + worker liveness 检测，遇到 worker 离线超过宽限期会主动失败而非永久挂起）
- `batch_enqueue_and_wait()` — 批量入队 + `asyncio.gather` 等待，依赖关系靠 `dependency_resource_id` 自动解析
- 同步 wrapper（`*_sync`）— 给 skill 子进程脚本用（脚本跑在沙箱子进程里，没有外部 event loop）

### 2.4 媒体后端（Registry + Factory）

```
lib/
├── image_backends/  ← Registry（gemini/ark/grok/openai/vidu）+ ImageBackend 抽象
├── video_backends/  ← 同上 + newapi 中转
├── text_backends/   ← 同上 + factory.create_text_backend_for_task()
├── custom_provider/ ← 用户自定义供应商（OpenAI/Google 兼容）的工厂 + 包装
└── media_generator.py ← MediaGenerator：组合 backend + VersionManager + UsageTracker
```

**MediaGenerator** 是关键的"业务无关执行单元"：调用方传入 `(resource_type, resource_id, prompt, ...)`，它负责选 backend、产物落盘、版本管理、用量记账。

### 2.5 业务任务执行器

[`server/services/generation_tasks.py`](../../server/services/generation_tasks.py) `execute_generation_task(task)`：

- 这一层**是业务相关**的——它知道 `task_type=storyboard` 该走 `MediaGenerator.generate_storyboard()`、`task_type=video` 该走 `generate_video()` 等
- 但 Worker 不在乎，它只调 `execute_generation_task`，从而 dispatch 表驱动
- 新增 `task_type=highlight_clip` 时，只需在这里加一个分支（或更彻底地，把 dispatch 抽成 registry，见 02 章）

---

## 3. Agent Runtime（Claude Agent SDK 适配层）

> 完全通用。

### 3.1 整体协作

```
HTTP/SSE 路由        AssistantService           SessionManager           ClaudeSDKClient
─────────────        ────────────────           ──────────────           ───────────────
/sessions/send  ─►   send_or_create()      ─►   send_message()       ─►  query()
/sessions/.../stream ─► stream_events()    ─►   subscribe()           ─►  receive_response()
                                                  │
                                                  ▼
                                         SessionActor (per-session asyncio task)
                                           ├─ 串行化所有 SDK 调用
                                           ├─ 缓冲流式消息 → subscribers fan-out
                                           ├─ 维护 pending AskUserQuestion
                                           └─ Hooks/Permission 回调

                                         StreamProjector
                                           └─ 把流式 raw 消息投影成 v2 snapshot（前端可消费的 turn 结构）

                                         SDK Session Store
                                           └─ DbSessionStore：transcript 持久化进 agent_sessions 表
                                              （ARCREEL_SDK_SESSION_STORE=db|off）
```

文件分工：

| 文件 | 职责 |
| --- | --- |
| `service.py` | `AssistantService`：service-level API（list/get/delete/stream）+ snapshot 缓存 + 多模态 prompt 装配 |
| `session_manager.py` | 进程内 session 注册表 + ClaudeSDK options 装配（含 sandbox/hooks/MCP servers/system prompt） |
| `session_actor.py` | 每会话一个独立 asyncio task，把 send/interrupt/answer 等命令串行化 |
| `stream_projector.py` | 流式消息 → v2 snapshot 投影（前端用） |
| `session_store.py` | session 元数据 store（项目名、状态、标题等） |
| `sdk_transcript_adapter.py` | 从 DbSessionStore 读 raw 消息（snapshot 重建用） |
| `sdk_tools/` | **进程内 MCP 工具网关** ★ |

### 3.2 进程内 MCP 工具网关 ★

[`server/agent_runtime/sdk_tools/__init__.py`](../../server/agent_runtime/sdk_tools/__init__.py)

```python
def build_arcreel_mcp_server(*, project_name: str, projects_root: Path) -> Any:
    ctx = ToolContext(project_name=project_name, projects_root=projects_root)
    return create_sdk_mcp_server(
        name="arcreel",
        version="1.0.0",
        tools=[
            generate_assets_tool(ctx),
            generate_storyboards_tool(ctx),
            generate_grid_tool(ctx),
            generate_video_episode_tool(ctx),
            ...,
        ],
    )
```

**关键设计**：

1. 每个 session 独立 build 一份 MCP server，`project_name` 通过闭包绑定到 `ToolContext`，**agent 无法通过 prompt 注入越权访问别的项目**。
2. 工具跑在 server 主进程，**不受 sandbox 网络白名单约束**——所以可以直接读 DB、调 provider HTTP、入队任务。
3. 工具内部统一通过 `enqueue_and_wait` 回到执行层（2.3 节），保留任务可见性、可取消、可重试。
4. 失败统一走 `_context.tool_error()` 返回 `{"is_error": True}` 给 SDK。

**这就是"业务能力"的接入点**——新增一个 agent 能力 ≈ 加几个 SDK MCP tool。

### 3.3 同步对话出口（外部 agent 友好）

[`server/routers/agent_chat.py`](../../server/routers/agent_chat.py)：把 SSE 流式助手包装成同步 request-response 模式（120s 超时），供 OpenClaw 等外部 agent 集成。**跨平台 agent 能复用 ArcReel agent 的最简通道**。

---

## 4. 业务能力包（Capability Pack）

> 业务相关。短剧只是其中一个。

ArcReel 当前装着的"短剧 capability pack"由四块拼成：

### 4.1 Profile（prompt + skills + subagents）

```
agent_runtime_profile/
├── CLAUDE.narration.md     ← 说书内容模式系统 prompt
├── CLAUDE.drama.md         ← 剧集动画内容模式系统 prompt
└── .claude/
    ├── skills/
    │   ├── manga-workflow/   SKILL.md + 脚本（端到端工作流）
    │   ├── generate-script/  SKILL.md
    │   ├── generate-storyboard/
    │   ├── generate-grid/
    │   ├── generate-video/
    │   ├── generate-assets/
    │   ├── compose-video/
    │   └── manage-project/
    └── agents/
        └── (subagent definitions)
```

通过 `lib/profile_manifest.py` 同步到每个项目。新增能力 ≈ 加一个 skill 子目录或新的 `CLAUDE.<mode>.md` 变体。

### 4.2 业务 SDK MCP Tools

`server/agent_runtime/sdk_tools/` 下的 11 个工具（参见 `ARCREEL_MCP_TOOL_IDS`）：

```
enqueue_assets       角色/场景/道具入队
enqueue_storyboards  分镜图入队
enqueue_grid         宫格图入队
enqueue_videos       视频片段入队（episode/scene/all/selected）
text_generation      生成集脚本 / 规范化剧本 / 查视频能力
```

每个工具 = 「参数 schema」+「`ToolContext` 闭包」+「调 `enqueue_and_wait` 或 backend」+「错误统一格式」。

### 4.3 业务 Service / Router

```
server/routers/
├── projects.py / characters.py / scenes.py / props.py   ← 项目级 CRUD
├── _asset_router_factory.py                              ← 由 ASSET_SPECS 驱动统一生成
├── generate.py                                           ← 触发分镜/视频/资产生成
├── reference_videos.py                                   ← 参考生视频
├── grids.py                                              ← 宫格图
└── ... usage / cost_estimation / providers / api_keys ...

server/services/
├── generation_tasks.py        ← execute_generation_task 的业务 dispatch
├── reference_video_tasks.py
├── jianying_draft_service.py  ← 剪映草稿导出
├── project_archive.py         ← ZIP 打包
├── project_cover.py
├── project_events.py          ← 项目变更事件 SSE
└── resolution_resolver.py
```

### 4.4 业务数据模型

```
lib/
├── script_models.py     ← NarrationSegment / DramaScene Pydantic schema
├── data_validator.py    ← project.json / 剧集 JSON 校验
├── asset_types.py       ← ASSET_SPECS（character/scene/prop 三类资产规格）
├── prompt_builders*.py  ← prompt 装配
├── source_loader/       ← 小说源文件导入（txt/docx/epub/pdf）
├── reference_video/     ← 参考生视频（按镜头解析 + 容量约束）
├── grid/                ← 宫格图布局/切割
└── style_templates.py   ← 视觉风格预设
```

---

## 5. 业务包到平台核心的边界一图看清

```
                    业务包 (短剧 / 营销 / 高光)
    ──────────────────┬─────────────────────────────
                      │ 通过下面三个接入点和平台对接：
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   ① Profile      ② SDK MCP     ③ Router/Service
   .claude/*      tools         + Worker 内 task_type
   CLAUDE.md      (sdk_tools/)   分支
                      │
    ──────────────────┴─────────────────────────────
                  平台核心层（不动）
              Agent Runtime / 执行层 / 基础设施
```

**接入新 agent 能力 = ① + ② + ③ 三件套**。下一章给清单与最小可用模板。
