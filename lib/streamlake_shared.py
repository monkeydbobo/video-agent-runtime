"""StreamLake (快手万擎) 视频 API shared constants and response helpers."""

from __future__ import annotations

from typing import Any

STREAMLAKE_BASE_URL = "https://wanqing.streamlakeapi.com/api/gateway/v1"

STREAMLAKE_STATUS_PENDING = "PENDING"
STREAMLAKE_STATUS_RUNNING = "RUNNING"
STREAMLAKE_STATUS_SUCCESS = "SUCCESS"
STREAMLAKE_STATUS_FAILED = "FAILED"
STREAMLAKE_STATUS_CANCELED = "CANCELED"


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("data")
    return value if isinstance(value, dict) else {}


def extract_streamlake_task_id(payload: dict[str, Any]) -> str:
    task_id = _data(payload).get("task_id") or payload.get("task_id")
    if isinstance(task_id, str) and task_id:
        return task_id
    raise RuntimeError(f"StreamLake 创建任务返回体缺少 task_id（字段: {sorted(payload)}）")


def streamlake_status(payload: dict[str, Any]) -> str | None:
    status = _data(payload).get("task_status") or payload.get("task_status")
    return status.upper() if isinstance(status, str) else None


def streamlake_is_done(payload: dict[str, Any]) -> bool:
    return streamlake_status(payload) in {
        STREAMLAKE_STATUS_SUCCESS,
        STREAMLAKE_STATUS_FAILED,
        STREAMLAKE_STATUS_CANCELED,
    }


def streamlake_failure_reason(payload: dict[str, Any]) -> str | None:
    status = streamlake_status(payload)
    if status not in {STREAMLAKE_STATUS_FAILED, STREAMLAKE_STATUS_CANCELED}:
        return None
    data = _data(payload)
    error = data.get("error") or payload.get("error") or data.get("message") or payload.get("message")
    if isinstance(error, dict):
        error = error.get("message") or error.get("code")
    return f"StreamLake 视频任务失败: {error or status}"


def extract_streamlake_video_url(payload: dict[str, Any]) -> str:
    content = _data(payload).get("content")
    if not isinstance(content, list):
        content = payload.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"]:
                return item["url"]
            if isinstance(item, str) and item:
                return item
    raise RuntimeError("StreamLake 任务完成但返回体缺少视频 URL")
