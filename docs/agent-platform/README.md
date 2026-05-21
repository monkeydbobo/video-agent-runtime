# ArcReel Agent 平台架构

Author: wanghaobo

> 本目录把 ArcReel 当前后端"短剧 agent"的实现，重新拆解成一个**可承载多种 agent 能力**的通用平台架构，并给出"高光时刻 agent"的最小接入示例。

阅读顺序：

1. [01-core-architecture.md](./01-core-architecture.md) — 抽丝剥茧：从外到内看清四层结构、每层职责与边界
2. [02-extension-recipe.md](./02-extension-recipe.md) — 接入一个新 agent 能力需要改动哪些层（清单 + 模板）
3. [03-highlight-moments-example.md](./03-highlight-moments-example.md) — 高光时刻 agent 接入示例（基于 CyberCut `CYBERCUT_REEL_CLIP_ENHANCE` HTTP API）

## 一句话定位

ArcReel 后端 = **「LLM Agent Runtime（Claude Agent SDK）」+「异步媒体生成任务队列」+「多供应商执行池」+「项目化资产/会话存储」** 四件套组合而成的工作空间。

短剧只是当前装在它上面的第一个业务包；架构上完全可以把"短剧"换成"营销视频 / 高光时刻 / 知识图文 / 任意 LLM 编排出来的视频流水线"，**核心层一行代码不改**。

## 顶层视图

```
┌──────────────────────────────────────────────────────────────────┐
│                     业务能力包 (Capability Pack)                 │
│   短剧 agent  |  营销视频 agent  |  高光时刻 agent  |  ...      │
│   = Profile (CLAUDE.md + skills + subagents) + 业务 SDK Tools    │
│     + 业务 Router/Service                                       │
└──────────────────────────────────────────────────────────────────┘
                              ▲ 装载 / 卸载（profile manifest 同步）
┌──────────────────────────────────────────────────────────────────┐
│                  Agent Runtime（Claude Agent SDK 适配层）        │
│  AssistantService → SessionManager → SessionActor → ClaudeSDK    │
│  StreamProjector  Hooks/Permissions  Sandbox  Session Store      │
│  ── 进程内 MCP 工具网关：build_arcreel_mcp_server() ──            │
└──────────────────────────────────────────────────────────────────┘
                              ▲ 工具调用（mcp__<server>__<tool>）
┌──────────────────────────────────────────────────────────────────┐
│              执行层（Async Generation Engine）                    │
│  GenerationQueue (DB)  GenerationWorker (image/video lanes)       │
│  enqueue_and_wait      MediaGenerator + VersionManager            │
│  ImageBackend / VideoBackend / TextBackend Registry+Factory       │
└──────────────────────────────────────────────────────────────────┘
                              ▲ 读写 DB / 文件系统
┌──────────────────────────────────────────────────────────────────┐
│                  基础设施层（Platform Infra）                     │
│  SQLAlchemy Async (Task / ApiCall / Asset / Session / ...)        │
│  ConfigService（多供应商 + 凭证）  i18n  Sandbox 探测              │
│  ProjectManager（项目目录）  ProfileManifest（profile 同步）       │
│  HTTP/SSE 路由（FastAPI）  Project Events SSE                      │
└──────────────────────────────────────────────────────────────────┘
```

## 四层职责一句话

| 层级 | 职责 | 通用 vs 业务 |
| --- | --- | --- |
| 基础设施 | 给上层提供"持久化/配置/凭证/沙箱/项目目录/SSE 推送"等共享能力 | **完全通用** |
| 执行层 | 把"生成一个图/一个视频/一段文本"统一抽象成入队-Worker-后端三段式，按供应商隔离并发 | **完全通用** |
| Agent Runtime | 把 Claude Agent SDK 的 session / 流式 / 工具调用 / 沙箱包装成一个稳定的 service | **完全通用** |
| 业务能力包 | 把上面这些通用能力组合成"短剧 / 营销视频 / 高光时刻 ..."的具体工作流 | **业务相关** |

> 理解这张图是后续模块化拆分的基础：**前三层是平台，第四层是 Capability Pack**。

## 关键设计模式（贯穿全栈）

| 模式 | 出现位置 | 价值 |
| --- | --- | --- |
| **Spec/Registry 驱动** | `lib/asset_types.py::ASSET_SPECS`、`lib/config/registry.py::PROVIDER_REGISTRY`、`lib/image_backends/registry.py` | 新增资产类型/供应商=改一处注册表，路由/池/工厂全部自动接住 |
| **进程内 MCP 工具** | `server/agent_runtime/sdk_tools/` | Agent 的"业务 API"以 MCP 工具形式暴露，跑在 server 主进程，不受沙箱网络白名单影响 |
| **入队-等待 (`enqueue_and_wait`)** | `lib/generation_queue_client.py` | 同步式调用语义，但底层是 DB 任务+独立 Worker，天然抗崩溃、可监控 |
| **Profile manifest 同步** | `lib/profile_manifest.py` | `agent_runtime_profile/` 是单一事实源，按 sha256 区分"内置/用户改/用户删"，跨项目分发 prompt+skills+subagents |
| **读时计算状态** | `lib/status_calculator.py` | 项目状态/进度不持久化、不一致性自动消失 |
| **依赖注入 + Translator** | FastAPI `Annotated[..., Depends(...)]` + `lib/i18n` | 路由函数零状态、便于测试、天然多租户/多语 |

## 为什么"短剧 agent"不是平台的负担

很多人会担心："你这平台是不是被短剧绑得很死？"

实际上短剧业务的耦合点只集中在三个文件夹：

- `agent_runtime_profile/.claude/skills/` + `.claude/agents/` + `CLAUDE.{narration,drama}.md`
- `server/agent_runtime/sdk_tools/` 中的业务工具（`enqueue_assets / enqueue_storyboards / enqueue_videos / enqueue_grid / text_generation`）
- `server/services/generation_tasks.py` + `server/services/reference_video_tasks.py`（具体怎么把"分镜生图"转成 backend 调用）

**其它一切都是通用的**。01 章会逐层验证这一点；02 章给出新增 agent 能力的标准动作；03 章用一个真实的"高光时刻 agent"案例走一遍流程。
