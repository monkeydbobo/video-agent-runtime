"""
任务队列与 SSE 路由。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from lib.api_errors import BadRequestError, NotFoundError
from lib.generation_queue import (
    get_generation_queue,
    read_queue_poll_interval,
)
from lib.i18n import Translator
from lib.project_manager import get_project_manager
from lib.task_failure import render_failure
from server.auth import CurrentUser, CurrentUserFlexible, CurrentUserInfo
from server.project_access import (
    accessible_project_names,
    ensure_project_access,
    require_project_access,
)

router = APIRouter()


def get_task_queue():
    return get_generation_queue()


async def _resolve_task_scope(
    user: CurrentUserInfo,
    project_name: str | None,
    _t: Callable[..., str],
) -> tuple[str | None, list[str] | None, str | None]:
    """解析全局任务视图的过滤参数 (project_name, project_names, user_id)。

    指定 project_name 时校验归属后按单项目过滤；未指定时限定在当前用户
    及其拥有的项目集合内。管理员普通业务查询也不隐式跨用户。
    """
    if project_name:
        await ensure_project_access(project_name, user, _t)
        return project_name, None, user.id
    owned = await accessible_project_names(get_project_manager().list_projects(), user)
    return None, owned, user.id


async def _ensure_task_access(task_id: str, user: CurrentUserInfo, _t: Callable[..., str]) -> None:
    """按任务 user_id 与所属项目校验归属；任务不存在时交由后续队列操作报错。"""
    task = await get_task_queue().get_task(task_id)
    if task is None:
        return
    task_user = task.get("user_id")
    if task_user and task_user != user.id:
        raise NotFoundError("task_not_found", id=task_id)
    project_name = task.get("project_name")
    if project_name:
        await ensure_project_access(project_name, user, _t)


def _localize_task(task: dict[str, Any], translate: Callable[..., str]) -> dict[str, Any]:
    """Return ``task`` with its stored failure reason rendered for the request locale.

    Known structured codes become localized text; raw exception text and legacy
    rows pass through unchanged (see ``lib.task_failure.render_failure``). The input
    dict is never mutated — a rendered copy is returned — so dicts owned by the queue
    layer stay locale-neutral and cannot be polluted across requests.
    """
    message = task.get("error_message")
    if not message:
        return task
    return {**task, "error_message": render_failure(message, translate)}


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_last_event_id(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return max(0, parsed)


def _transform_task_event(raw_event: dict, stats: dict) -> dict:
    """将原始 task_events 行转换为前端期望的 TaskStreamTaskPayload 结构。"""
    event_type = raw_event.get("event_type", "")
    action = "created" if event_type == "queued" else "updated"
    return {
        "action": action,
        "task": raw_event.get("data", {}),
        "stats": stats,
    }


@router.get("/tasks/stats")
async def get_task_stats(_user: CurrentUser, _t: Translator, project_name: str | None = None):
    scoped_name, scoped_names, scoped_user = await _resolve_task_scope(_user, project_name, _t)
    queue = get_task_queue()
    stats = await queue.get_task_stats(
        project_name=scoped_name,
        user_id=scoped_user,
        project_names=scoped_names,
    )
    return {"stats": stats}


@router.get("/tasks")
async def list_tasks(
    _user: CurrentUser,
    _t: Translator,
    project_name: str | None = None,
    status: str | None = None,
    task_type: str | None = None,
    source: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
):
    scoped_name, scoped_names, scoped_user = await _resolve_task_scope(_user, project_name, _t)
    queue = get_task_queue()
    result = await queue.list_tasks(
        project_name=scoped_name,
        user_id=scoped_user,
        project_names=scoped_names,
        status=status,
        task_type=task_type,
        source=source,
        page=page,
        page_size=page_size,
    )
    result["items"] = [_localize_task(task, _t) for task in result.get("items", [])]
    return result


@router.get("/projects/{project_name}/tasks", dependencies=[Depends(require_project_access)])
async def list_project_tasks(
    project_name: str,
    _user: CurrentUser,
    _t: Translator,
    status: str | None = None,
    task_type: str | None = None,
    source: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
):
    queue = get_task_queue()
    result = await queue.list_tasks(
        project_name=project_name,
        user_id=_user.id,
        status=status,
        task_type=task_type,
        source=source,
        page=page,
        page_size=page_size,
    )
    result["items"] = [_localize_task(task, _t) for task in result.get("items", [])]
    return result


@router.get("/tasks/stream", response_class=EventSourceResponse, deprecated=True)
async def stream_tasks(
    request: Request,
    _user: CurrentUserFlexible,
    _t: Translator,
    project_name: str | None = None,
    last_event_id: int | None = Query(default=None, ge=0),
    last_event_header: str | None = Header(default=None, alias="Last-Event-ID"),
) -> AsyncIterator[ServerSentEvent]:
    scoped_name, scoped_names, scoped_user = await _resolve_task_scope(_user, project_name, _t)
    queue = get_task_queue()
    poll_interval = read_queue_poll_interval()

    header_last_id = _parse_last_event_id(last_event_header)
    resume_requested = (last_event_id is not None) or (header_last_id is not None)
    cursor = last_event_id if last_event_id is not None else header_last_id
    if cursor is None:
        cursor = 0
    cursor = max(0, int(cursor))

    latest_event_id = await queue.get_latest_event_id(
        project_name=scoped_name, user_id=scoped_user, project_names=scoped_names
    )
    snapshot_last_event_id = max(cursor, latest_event_id) if resume_requested else latest_event_id
    snapshot = {
        "project_name": project_name,
        "tasks": await queue.get_recent_tasks_snapshot(
            project_name=scoped_name, user_id=scoped_user, project_names=scoped_names, limit=1000
        ),
        "stats": await queue.get_task_stats(project_name=scoped_name, user_id=scoped_user, project_names=scoped_names),
        "last_event_id": snapshot_last_event_id,
        "generated_at": _utc_now_iso(),
    }
    yield ServerSentEvent(event="snapshot", data=snapshot)
    cursor = snapshot_last_event_id

    while True:
        if await request.is_disconnected():
            break

        events = await queue.get_events_since(
            last_event_id=cursor,
            user_id=scoped_user,
            project_name=scoped_name,
            project_names=scoped_names,
            limit=200,
        )
        if events:
            batch_stats = await queue.get_task_stats(
                project_name=scoped_name, user_id=scoped_user, project_names=scoped_names
            )
            for event in events:
                cursor = int(event["id"])
                transformed = _transform_task_event(event, batch_stats)
                yield ServerSentEvent(
                    event="task",
                    data=transformed,
                    id=str(cursor),
                )
            continue

        await asyncio.sleep(poll_interval)


@router.get("/tasks/{task_id}/cancel-preview")
async def cancel_preview(task_id: str, _user: CurrentUser, _t: Translator):
    await _ensure_task_access(task_id, _user, _t)
    queue = get_task_queue()
    try:
        preview = await queue.get_cancel_preview(task_id)
    except ValueError as e:
        raise BadRequestError("task_not_found", id=task_id) from e
    return preview


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, _user: CurrentUser, _t: Translator):
    await _ensure_task_access(task_id, _user, _t)
    queue = get_task_queue()
    try:
        result = await queue.cancel_task(task_id)
    except ValueError as e:
        raise BadRequestError("task_not_found", id=task_id) from e
    return result


@router.get("/projects/{project_name}/tasks/cancel-all-preview", dependencies=[Depends(require_project_access)])
async def cancel_all_preview(project_name: str, _user: CurrentUser):
    queue = get_task_queue()
    queued_count = await queue.get_cancel_all_preview(project_name, user_id=_user.id)
    return {"queued_count": queued_count}


@router.post("/projects/{project_name}/tasks/cancel-all", dependencies=[Depends(require_project_access)])
async def cancel_all_queued(project_name: str, _user: CurrentUser):
    queue = get_task_queue()
    result = await queue.cancel_all_queued(project_name, user_id=_user.id)
    return result


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    _user: CurrentUser,
    _t: Translator,
):
    queue = get_task_queue()
    task = await queue.get_task(task_id)
    if not task:
        raise NotFoundError("task_not_found", id=task_id)
    task_user = task.get("user_id")
    if task_user and task_user != _user.id:
        raise NotFoundError("task_not_found", id=task_id)
    task_project = task.get("project_name")
    if task_project:
        await ensure_project_access(task_project, _user, _t)
    return {"task": _localize_task(task, _t)}
