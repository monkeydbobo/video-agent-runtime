# 03 · 高光时刻 Agent 接入示例

Author: wanghaobo

> 本章把 02 章的 **B 类接入（远端 API + 异步回调）** 套到一个真实场景上：基于公司内部已有的 [`CYBERCUT_REEL_CLIP_ENHANCE` HTTP 接口](../../../cybercut_x_wps/docs/cybercut-reel-clip-enhance-api.md) 实现一个**高光时刻 agent**。

> 我们**不关心 cybercut 内部怎么生成高光片段**——它已经把"长视频→短视频"的工作流封装好了。本章只演示 ArcReel 这边怎么把它**当作一个 agent 能力**接进来，让用户可以用对话的方式触发：「帮我把这条 30 分钟会议剪成几条高光短视频」。

---

## 1. 业务流程总览

```
┌──────────────┐       ① 上传/绑定输入视频
│ 用户对话框   │       ② 触发 generate_highlights tool
│ （前端）     │
└──────┬───────┘
       │ 自然语言
       ▼
┌──────────────────┐       ③ submitSmartSlice（cybercut HTTP）
│ ArcReel Agent    │ ──►  POST /api/task/submitSmartSlice
│ (Claude SDK)     │       biz_key=cybercut, video_source, kafka_topic, additional_params
└──────┬───────────┘
       │ ④ 返回 cybercut_task_id
       ▼
┌──────────────────┐       ⑤ ArcReel 自己创建一条 task (queued)
│ ArcReel          │       resource_id=cybercut_task_id
│ tasks 表         │
└──────┬───────────┘
       │ ⑥ tool 内部 enqueue_and_wait 阻塞等待
       │     ┊
       │     ┊  时间流逝 ...
       ▼     ▼
┌────────────────────────────────────────────┐
│ Kafka 回调监听器 (ArcReel 服务)             │
│  CyberCutMessage → mark_task_succeeded     │
└──────┬─────────────────────────────────────┘
       │
       ▼
   Tool 返回结果给 agent，agent 给用户回 markdown 列表
```

**关键设计**：把"提交→等回调"这段逻辑**伪同步化**——在 ArcReel 的 `tasks` 表里挂一条占位任务，让 SDK tool 用现有的 `enqueue_and_wait` 阻塞等结果，Kafka 监听器只负责"把外部状态映射到 ArcReel task 状态"。这样：

- Agent 端代码与短剧工具完全一致（都是 `enqueue_and_wait` 风格）
- 前端任务列表 / SSE 推送 / 取消 / 重试机制全部白嫖
- 远端服务挂掉时 worker liveness 检测会自动给 agent 报错而不是永远挂着

---

## 2. 改动清单（精确到文件）

```
新增/修改：

server/agent_runtime/sdk_tools/
└── highlight_clips.py               ← ② 新增 SDK MCP tool
server/agent_runtime/sdk_tools/__init__.py
                                    ← ② 注册 tool

server/services/
└── highlight_tasks.py              ← ③ 新增任务执行器（提交 cybercut + 占位 task）

server/routers/
├── highlight_callbacks.py          ← ③ 新增 Kafka/Webhook 回调入口
└── highlights.py                   ← ③（可选）前端直触发的 HTTP 入口

server/app.py                       ← 注册两个新路由 + 启动 Kafka consumer

lib/
└── highlight/                      ← 业务模型 + cybercut HTTP client
    ├── __init__.py
    ├── client.py                   ← cybercut HTTP API client（async）
    ├── models.py                   ← Pydantic schema
    └── kafka_consumer.py           ← 后台监听 cybercut 回调

agent_runtime_profile/.claude/skills/
└── generate-highlights/
    └── SKILL.md                    ← ①（可选）skill 入口

frontend/src/i18n/{zh,en,vi}/dashboard.ts
                                    ← skill_name_generate-highlights / tool_name_generate_highlights 三语
```

---

## 3. 最小可用代码

### 3.1 `lib/highlight/client.py` — cybercut HTTP 包装

```python
# lib/highlight/client.py
"""
CyberCut REEL_CLIP_ENHANCE HTTP client.

环境基址 / 业务 key 通过 ConfigService 注入，不在 env 暴露密钥。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class CybercutSubmitResult:
    success: bool
    task_id: str | None
    message: str | None


class CybercutClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0):
        # 例：https://streamlake-platform.staging.kuaishou.com/ai
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def submit_smart_slice(
        self,
        *,
        kafka_topic: str,
        video_source: dict[str, Any],
        custom_output_message: dict[str, Any],
        additional_params: str | None = None,
        video_id: str | None = None,
        biz_key: str = "cybercut",
    ) -> CybercutSubmitResult:
        """提交 CYBERCUT_REEL_CLIP_ENHANCE 工作流。"""
        body = {
            "biz_key": biz_key,
            "kafka_topic": kafka_topic,
            "video_source": video_source,
            "custom_output_message": custom_output_message,
        }
        if additional_params is not None:
            body["additional_params"] = additional_params
        if video_id is not None:
            body["video_id"] = video_id

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/task/submitSmartSlice",
                json=body,
                headers={"Content-Type": "application/json"},
            )
        resp.raise_for_status()
        data = resp.json()
        return CybercutSubmitResult(
            success=bool(data.get("success")),
            task_id=data.get("task_id"),
            message=data.get("message"),
        )
```

### 3.2 `lib/highlight/models.py` — Pydantic schema

```python
# lib/highlight/models.py
from __future__ import annotations

from pydantic import BaseModel, Field


class BlobLocation(BaseModel):
    db: str
    table: str
    key: str


class BlobOutputLocation(BaseModel):
    db: str
    table: str
    prefix: str


class HighlightSubmitInput(BaseModel):
    """SDK tool 入参（由 LLM 生成）。"""

    input_video: BlobLocation
    output_prefix: BlobOutputLocation
    description: str = Field(default="", description="可选场景说明，仅用于排查")
    video_id: str | None = None


class HighlightClipResult(BaseModel):
    """单条高光视频结果（与 cybercut 回调 clip_results 元素对齐）。"""

    db: str
    table: str
    key: str
    cover_key: str | None = None
    title: str
    summary: str = ""
    description: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    draft_segments: list[dict] = Field(default_factory=list)


class HighlightTaskResult(BaseModel):
    """ArcReel task succeeded 时存进 result_json 的内容。"""

    cybercut_task_id: str
    clips: list[HighlightClipResult]
```

### 3.3 `server/services/highlight_tasks.py` — 任务执行器

```python
# server/services/highlight_tasks.py
"""
执行 highlight_clip 类型任务：调 cybercut 提交，把占位 task 状态停在 running，
真正完成由 Kafka 回调写入。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from lib.config.service import ConfigService
from lib.db import async_session_factory
from lib.highlight.client import CybercutClient
from lib.highlight.models import HighlightSubmitInput

logger = logging.getLogger(__name__)


async def execute_highlight_task(task: dict[str, Any]) -> dict[str, Any]:
    """
    被 server/services/generation_tasks.py::execute_generation_task 在
    task_type=='highlight_clip' 分支调用。

    与短剧的 image/video 任务不同：本函数**不会自己等到完成**——它只负责
    "提交 cybercut + 让 ArcReel task 进入 running 状态"，剩下的等回调写入。

    实现方式（关键）：
    payload 内含 ArcReel task_id。tool 在 enqueue_and_wait 之前先把
    payload['arcreel_task_id'] 注入，submit 成功后我们立即抛
    "wait_for_callback" 信号——但 ArcReel 当前 worker 是"返回即 succeeded"
    模式，所以这里改用：返回一个特殊 result 标记 'pending_callback'，
    并由 generation_tasks dispatch 识别后**保持 running 而不 mark succeeded**。

    👇 简化版直接演示思路（生产实现请用专门的 Kafka 监听器接 mark）：
    """
    payload = task.get("payload") or {}
    submit = HighlightSubmitInput(**payload["submit_input"])

    async with async_session_factory() as session:
        cfg = ConfigService(session)
        base_url = await cfg.get_config_value("highlight.cybercut_base_url")
        kafka_topic = await cfg.get_config_value("highlight.callback_topic")

    client = CybercutClient(base_url=base_url)
    result = await client.submit_smart_slice(
        kafka_topic=kafka_topic,
        video_source={
            "source_type": "BLOBSTORE",
            "media_info_bucket": submit.input_video.model_dump(),
        },
        custom_output_message={
            "storage_type": "BLOBSTORE",
            "output_info_bucket": submit.output_prefix.model_dump(),
        },
        additional_params=json.dumps({
            "arcreel_task_id": task["task_id"],
            "project_name": task["project_name"],
        }),
        video_id=submit.video_id,
    )
    if not result.success:
        raise RuntimeError(f"cybercut submit failed: {result.message}")

    logger.info("highlight 已提交 cybercut task_id=%s 对应 arcreel task=%s",
                result.task_id, task["task_id"])

    # 关键：这里不返回 succeeded 结果，让 worker 知道"还在等回调"
    # 实际实现可在 task_repo 加一个 status='awaiting_callback'，或者
    # 在 mark_task_succeeded 之前先写一个 cybercut_task_id 到 payload，由
    # Kafka 监听器调 mark_task_succeeded 收尾。
    return {"status": "submitted", "cybercut_task_id": result.task_id}
```

> ⚠️ 上面 docstring 提到的"awaiting_callback"是真正生产时需要的**第三种状态**——为了不污染现有 schema，最干净的实现是：在 `lib/highlight/kafka_consumer.py` 监听到回调后直接调 `GenerationQueue.mark_task_succeeded(task_id, result)`，并且**让 `execute_highlight_task` 不返回**——它通过 `await asyncio.Event` 等到回调来时再返回；超时 / 服务不可用走 `mark_task_failed`。这种实现下 worker 视角和短剧任务完全一致。

### 3.4 `server/agent_runtime/sdk_tools/highlight_clips.py` — SDK MCP Tool

```python
# server/agent_runtime/sdk_tools/highlight_clips.py
"""高光时刻 agent SDK MCP 工具。"""
from __future__ import annotations

from claude_agent_sdk import tool

from lib.generation_queue_client import enqueue_and_wait
from lib.highlight.models import HighlightSubmitInput, HighlightTaskResult
from server.agent_runtime.sdk_tools._context import ToolContext, tool_error


def generate_highlights_tool(ctx: ToolContext):
    @tool(
        name="generate_highlights",
        description=(
            "把一段长视频提交给 CyberCut 高光时刻引擎，等待生成完成后返回每条短视频的"
            "BlobStore 位置、标题、时长与原视频裁剪段落。"
            "适用于"用户给一段长视频，想剪出 N 条高光短视频"的场景。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "input_video": {
                    "type": "object",
                    "description": "输入视频 BlobStore 位置",
                    "properties": {
                        "db": {"type": "string"},
                        "table": {"type": "string"},
                        "key": {"type": "string"},
                    },
                    "required": ["db", "table", "key"],
                },
                "output_prefix": {
                    "type": "object",
                    "description": "短视频输出 BlobStore 位置（prefix 之下落多条 mp4）",
                    "properties": {
                        "db": {"type": "string"},
                        "table": {"type": "string"},
                        "prefix": {"type": "string"},
                    },
                    "required": ["db", "table", "prefix"],
                },
                "description": {"type": "string", "default": ""},
                "video_id": {"type": "string"},
            },
            "required": ["input_video", "output_prefix"],
        },
    )
    async def handler(args):
        try:
            submit = HighlightSubmitInput(**args)
            queue_result = await enqueue_and_wait(
                project_name=ctx.project_name,
                task_type="highlight_clip",
                media_type="video",
                resource_id=submit.input_video.key,   # 用输入视频 key 当 dedupe key
                payload={"submit_input": submit.model_dump()},
                source="agent",
            )
            result = HighlightTaskResult(**queue_result["result"])
            lines = [
                f"已生成 {len(result.clips)} 条高光视频（cybercut_task_id={result.cybercut_task_id}）：",
            ]
            for i, c in enumerate(result.clips, 1):
                lines.append(
                    f"{i}. {c.title} | {c.duration:.1f}s | "
                    f"{c.db}/{c.table}/{c.key}"
                )
            return {"content": [{"type": "text", "text": "\n".join(lines)}]}
        except Exception as exc:
            return tool_error("generate_highlights", exc)

    return handler
```

注册：

```python
# server/agent_runtime/sdk_tools/__init__.py（diff）
from server.agent_runtime.sdk_tools.highlight_clips import generate_highlights_tool

ARCREEL_MCP_TOOL_IDS: tuple[str, ...] = (
    ...,
    "generate_highlights",
)

def build_arcreel_mcp_server(*, project_name, projects_root):
    ctx = ToolContext(project_name=project_name, projects_root=projects_root)
    return create_sdk_mcp_server(
        name="arcreel",
        version="1.0.0",
        tools=[
            ...,
            generate_highlights_tool(ctx),
        ],
    )
```

### 3.5 `server/routers/highlight_callbacks.py` — Kafka 回调入口

> 如果 ArcReel 部署所在环境无法直连 Kafka，可以让一个独立的 sidecar 把消息转成 HTTP webhook 推到下面这个路由。

```python
# server/routers/highlight_callbacks.py
"""CyberCut Kafka 回调 → ArcReel task 收尾。"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from lib.generation_queue import get_generation_queue
from lib.highlight.models import HighlightClipResult, HighlightTaskResult

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/highlights/callback")
async def cybercut_callback(message: dict):
    """
    Webhook 形态：要么由 Kafka sidecar 投递，要么 cybercut 自己直接 POST。
    Body 与 docs/cybercut-reel-clip-enhance-api.md 中的 CyberCutMessage 对齐。
    """
    additional_params = message.get("additional_params") or "{}"
    try:
        ap = json.loads(additional_params) if isinstance(additional_params, str) else additional_params
    except json.JSONDecodeError:
        ap = {}
    arcreel_task_id = ap.get("arcreel_task_id")
    if not arcreel_task_id:
        raise HTTPException(status_code=400, detail="缺少 additional_params.arcreel_task_id")

    queue = get_generation_queue()
    status = message.get("workflowStatusType")
    if status == "COMPLETED":
        clips = [HighlightClipResult(**c) for c in (message.get("clip_results") or [])]
        result = HighlightTaskResult(
            cybercut_task_id=str(message.get("task_id")),
            clips=clips,
        )
        await queue.mark_task_succeeded(arcreel_task_id, result.model_dump())
        logger.info("highlight 完成 arcreel=%s clips=%d", arcreel_task_id, len(clips))
        return {"ok": True}
    elif status == "FAILED":
        await queue.mark_task_failed(
            arcreel_task_id,
            f"cybercut error_code={message.get('error_code')}",
        )
        return {"ok": True}
    else:
        return {"ok": False, "reason": f"unknown status: {status}"}
```

注册到 `server/app.py`（与现有 router 一致）：

```python
from server.routers import highlight_callbacks

app.include_router(highlight_callbacks.router, prefix="/api/v1", tags=["高光时刻回调"])
```

### 3.6 把任务类型挂进 worker dispatch

`server/services/generation_tasks.py::execute_generation_task` 加分支（最小改动）：

```python
async def execute_generation_task(task: dict) -> dict:
    task_type = task.get("task_type")
    if task_type == "highlight_clip":
        from server.services.highlight_tasks import execute_highlight_task
        return await execute_highlight_task(task)
    # ... 其它现有分支 ...
```

> 02 章 §1.④ 提到的 dispatch registry 化是更优解：把 if-elif 替换为查表。新能力只在自己的 module 中 `@register_task_handler("highlight_clip")` 即可，`generation_tasks.py` 不再被业务包污染。

### 3.7 Profile（可选）

如果希望前端 skill 抽屉里有"高光时刻"按钮，加一个 user-invocable skill：

```markdown
<!-- agent_runtime_profile/.claude/skills/generate-highlights/SKILL.md -->
---
name: generate-highlights
description: 把一段长视频剪成多条高光短视频。当用户说"剪高光"、"做精彩片段"、"长转短"时使用。
user-invocable: true
---

# 生成高光短视频

调用 `mcp__arcreel__generate_highlights` 工具，把项目中的输入视频提交到 CyberCut 高光时刻引擎。

输入：
- `input_video`: BlobStore 位置（db/table/key）
- `output_prefix`: 输出 BlobStore prefix（db/table/prefix）

生成完成后向用户报告每条高光的标题、时长与裁剪段落。
```

并在 `frontend/src/i18n/{zh,en,vi}/dashboard.ts` 加 `skill_name_generate-highlights` / `tool_name_generate_highlights` 三语 key。

---

## 4. 平台核心层动了什么？

```
✗ lib/db                — 不动
✗ lib/generation_queue  — 不动
✗ lib/generation_worker — 不动
✗ lib/media_generator   — 不动
✗ lib/image_backends    — 不动
✗ lib/video_backends    — 不动
✗ server/agent_runtime/service.py / session_manager.py / session_actor.py — 不动

✓ server/agent_runtime/sdk_tools/__init__.py            — 加一行注册
✓ server/services/generation_tasks.py                    — 加一个 task_type 分支
✓ server/app.py                                          — 加一行 include_router
```

**新业务包代码 100% 落在新建文件里**：`lib/highlight/`、`server/services/highlight_tasks.py`、`server/routers/highlight_callbacks.py`、`server/agent_runtime/sdk_tools/highlight_clips.py`、`agent_runtime_profile/.claude/skills/generate-highlights/`。

这就是 01 章 §5 那张图想要表达的隔离边界。

---

## 5. 验证 / 联调步骤

1. **本地起服务**：`uv run uvicorn server.app:app --reload --reload-dir server --reload-dir lib --port 1241`
2. **配置 cybercut 基址 + topic**：在 `/settings` 页面或者直接 `INSERT INTO config` 加 `highlight.cybercut_base_url` / `highlight.callback_topic`
3. **创建一个项目**：`POST /api/v1/projects`，名字随便（高光场景甚至不需要小说源文件，可以新建一种 content_mode=`highlight` 跳过校验）
4. **直接调用接口（无 agent）**：
   ```bash
   curl -X POST http://localhost:1241/api/v1/highlights/callback \
        -H 'Content-Type: application/json' \
        -d '{
          "task_id": "fake_cybercut_001",
          "biz_key": "cybercut",
          "workflowStatusType": "COMPLETED",
          "additional_params": "{\"arcreel_task_id\":\"<existing-arcreel-task-id>\"}",
          "clip_results": [...]
        }'
   ```
   预期 ArcReel 对应 task 立刻变 succeeded。
5. **跑通 agent 路径**：在前端聊"把 sl/cybercut-test/input/demo.mp4 剪成高光"，观察 SSE 日志：
   - `mcp__arcreel__generate_highlights` 被 LLM 调用
   - cybercut 提交日志输出
   - 任务列表里出现一条 `task_type=highlight_clip` 的任务
   - 收到 Kafka/Webhook 回调后任务 succeeded
   - Agent 在对话中输出 markdown 列表

---

## 6. 写在最后

把这张接入流程倒过来再看一次：

> **接入新 agent 能力 = 写一个 SDK MCP tool（或 Skill），把这个能力背后的"提交→等结果"伪装成 ArcReel 的一个任务类型，剩下交给平台。**

短剧、营销视频、高光时刻、未来的任意 LLM-orchestrated 视频流水线，都是同一个模板。
