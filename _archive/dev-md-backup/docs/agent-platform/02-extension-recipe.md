# 02 · 接入新 agent 能力的标准动作

Author: wanghaobo

01 章梳理过：业务包通过 **① Profile / ② SDK MCP Tools / ③ Router/Service + task_type 分支** 三个接入点搭在平台核心上。本章给出一份**改动清单**和**最小可用模板**，便于把任何 LLM-orchestrated 视频/媒体能力包装成 ArcReel 的一个 agent。

---

## 0. 决策树：你的能力是什么形态？

| 形态 | 描述 | 接入路线 |
| --- | --- | --- |
| **A. 闭环 LLM agent** | 需要一个会话式 agent 用多步工具调用完成任务（例：短剧、营销脚本生成） | 全套 ① + ② + ③ |
| **B. 远端单体 API** | 业务方已有一个 HTTP 接口（同步或异步），agent 只需"提交→等回调→拿结果" | ② + ③（① 可选，简单包一个 skill） |
| **C. 纯人工编排工具** | 只是给 agent 加一个新的"工具"，不改变现有工作流 | 只加 ② |

**高光时刻 agent（cybercut `CYBERCUT_REEL_CLIP_ENHANCE`）属于 B**——03 章是它的样板。

---

## 1. 改动清单（A 类完整接入）

### ① Profile 层

```
agent_runtime_profile/
├── CLAUDE.<your_mode>.md          ← 新内容模式 system prompt（按需）
└── .claude/
    ├── skills/
    │   └── <your-skill>/
    │       ├── SKILL.md            ← user-invocable: true 时会出现在前端 skill 抽屉
    │       └── scripts/*.py        ← 可选，沙箱内运行的辅助脚本
    └── agents/
        └── <your-subagent>.md      ← Subagent 定义（按需）
```

**注意点**：

- 新加 user-invocable skill 时，要在 `frontend/src/i18n/{zh,en,vi}/dashboard.ts` 的 `skill_name_<id>` 加翻译；CI 有 `tests/test_frontend_skill_i18n.py` 做交叉校验。
- 新增 `CLAUDE.<mode>.md` 变体后，`lib/profile_manifest.py::VALID_CONTENT_MODES` 也要扩。
- 修改后下次 server 启动会通过 `ProjectManager.sync_all_agent_profiles()` 同步到所有项目；开发期可以手动调 `force_resync_profile`。

### ② SDK MCP Tools 层

每个工具结构：

```python
# server/agent_runtime/sdk_tools/<your_feature>.py
from claude_agent_sdk import tool

from lib.generation_queue_client import enqueue_and_wait
from server.agent_runtime.sdk_tools._context import ToolContext, tool_error


def your_tool(ctx: ToolContext):
    @tool(
        name="your_action",
        description="一句话告诉 LLM 这个工具能做什么、什么时候该用",
        input_schema={
            "type": "object",
            "properties": {
                "param_a": {"type": "string"},
                "param_b": {"type": "integer", "default": 1},
            },
            "required": ["param_a"],
        },
    )
    async def handler(args):
        try:
            result = await enqueue_and_wait(
                project_name=ctx.project_name,
                task_type="your_task",         # ★ 与 ③ 的 dispatch 对齐
                media_type="video",            # 或 "image" / "text"
                resource_id=args["param_a"],
                payload=args,
                source="agent",
            )
            return {
                "content": [{"type": "text", "text": f"任务成功: {result['result']}"}],
            }
        except Exception as exc:
            return tool_error("your_action", exc)

    return handler
```

注册到 [`server/agent_runtime/sdk_tools/__init__.py`](../../server/agent_runtime/sdk_tools/__init__.py)：

```python
from server.agent_runtime.sdk_tools.your_feature import your_tool

ARCREEL_MCP_TOOL_IDS: tuple[str, ...] = (
    ...,
    "your_action",   # 加到清单
)

def build_arcreel_mcp_server(*, project_name, projects_root):
    ctx = ToolContext(project_name=project_name, projects_root=projects_root)
    return create_sdk_mcp_server(
        name="arcreel",
        version="1.0.0",
        tools=[
            ...,
            your_tool(ctx),  # 注册
        ],
    )
```

**可选**：当能力数量明显增长时，把 `name="arcreel"` 拆成多个 server（`name="arcreel-shortdrama"` / `name="arcreel-highlight"` 等），`build_arcreel_mcp_server` 改成根据项目模式或显式 capability 列表组合返回。

### ③ Router / Service / Worker 分支

最小步骤：

1. **Router**（可选）— 提供 HTTP 入口给前端按钮直接触发
   ```python
   # server/routers/your_feature.py
   from fastapi import APIRouter
   router = APIRouter(prefix="/your-feature")

   @router.post("/projects/{project_name}/run")
   async def run_your_feature(project_name: str, req: YourRequest, ...):
       result = await enqueue_and_wait(project_name=project_name, task_type="your_task", ...)
       return result
   ```
   在 `server/app.py` 注册 `app.include_router(your_feature.router, prefix="/api/v1", tags=["你的能力"])`。

2. **Worker dispatch** — 在 `server/services/generation_tasks.py::execute_generation_task` 加一个 `task_type` 分支（或更彻底地把 dispatch 抽成 registry，见下文）。

3. **数据模型**（按需）— `lib/your_feature/` 放业务 model、prompt builder、外部 API client 等。

### ④（可选）Worker dispatch registry 化

当前 `execute_generation_task` 是 if-elif 分支。如果要长期承载多种 capability，建议在 02→03 章试点后，把它抽成：

```python
# lib/task_dispatch.py
TASK_HANDLERS: dict[str, Callable[[dict], Awaitable[dict]]] = {}

def register_task_handler(task_type: str):
    def deco(fn):
        TASK_HANDLERS[task_type] = fn
        return fn
    return deco


# 各 capability 包按需挂载：
# server/services/highlight_tasks.py
@register_task_handler("highlight_clip")
async def execute_highlight_clip(task: dict) -> dict: ...
```

`generation_tasks.py::execute_generation_task` 退化成查表 + 调用，未来新增 capability 不再需要改它。这一步**不是当前接入新能力的硬性要求**，但如果要长期承载多种 agent，强烈推荐做掉。

---

## 2. B 类接入（远端 API + 异步回调）

如果你的能力本身就是一个外部 HTTP API（如 cybercut `submitSmartSlice`）：

| 层 | 改动 |
| --- | --- |
| ① Profile | 一个简单的 SKILL.md 教 agent "在什么场景调这个 tool"（也可以省略，agent 自己读 tool description 就够了） |
| ② SDK Tool | 一个 `submit_<thing>_tool`，内部 `httpx.AsyncClient` 调外部 API，返回 `task_id` 给 agent；不要在工具里阻塞等回调 |
| ③ Router | **关键**：加一个 Kafka/Webhook 接收路由（或拉取 Kafka 的 sidecar），把回调结果写入 ArcReel 自己的 `tasks` 表 → 让 agent 通过查询任务状态拿到结果 |

如果你不想搭 Kafka 接收端，最简方案是用 ArcReel 的任务队列做"伪同步"：
- Tool 返回 `task_id` 后，**在 server 这边创建一个 ArcReel `task`，状态 `running`**
- 起一个 worker thread / asyncio task 定期 poll 远端状态（或监听 Kafka）
- 远端完成时 mark ArcReel task succeeded
- Agent 这边只需 `enqueue_and_wait` 就能等到结果

03 章会用这个模式具体演示一遍。

---

## 3. C 类接入（纯加工具）

最简单：只写一个 tool，挂进 `build_arcreel_mcp_server`，profile 不动、router 不加。例如给 agent 加一个"查股票价格"工具：

```python
def quote_tool(ctx: ToolContext):
    @tool(name="get_quote", description="...", input_schema={...})
    async def handler(args):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://api.example.com/quote/{args['symbol']}")
        return {"content": [{"type": "text", "text": resp.text}]}
    return handler
```

---

## 4. 验收 checklist

接入完成前请确认：

- [ ] **i18n** — 新加面向用户文案在 `zh`/`en`/`vi` 三语 key 都有（`tests/test_i18n_consistency.py`）
- [ ] **Skill 翻译** — 如果是 user-invocable skill，`frontend/src/i18n/.../dashboard.ts::skill_name_<id>` 已加（`tests/test_frontend_skill_i18n.py`）
- [ ] **MCP Tool 翻译** — 新增 `mcp__arcreel__<id>` 工具在 `tool_name_<id>` 三语 key 已加（`tests/test_frontend_mcp_tool_i18n.py`）
- [ ] **Pydantic schema** — 远端 API 入参 / 队列 payload 都用 Pydantic 验证
- [ ] **沙箱兼容** — 如果 skill 内有脚本，确认沙箱网络白名单 / 文件白名单足够（不够时通过 SDK MCP tool 在主进程兜底）
- [ ] **类型检查** — `uv run basedpyright` 不引入新错误（CI 强制 0）
- [ ] **测试** — 至少给新 SDK tool / dispatch handler 加 happy path + 一个失败用例
