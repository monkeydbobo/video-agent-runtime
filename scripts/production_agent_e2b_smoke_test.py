"""Exercise the production ArcReel Agent → E2B → Railway file-sync path."""

from __future__ import annotations

import asyncio
import json
import os
import time
from uuid import uuid4

import httpx


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


async def _request(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> httpx.Response:
    response = await client.request(method, path, **kwargs)
    if response.is_error:
        detail = response.text[:2_000]
        raise RuntimeError(f"{method} {path} failed with HTTP {response.status_code}: {detail}")
    return response


async def main() -> None:
    base_url = os.environ.get("ARCREEL_SMOKE_BASE_URL", "https://oioi.bio").rstrip("/")
    username = _required_env("AUTH_USERNAME")
    password = _required_env("AUTH_PASSWORD")
    project_name = f"e2b-smoke-{uuid4().hex[:10]}"
    session_id: str | None = None
    project_created = False
    checks = {
        "authenticated": False,
        "project_created": False,
        "session_created": False,
        "e2b_tool_observed": False,
        "turn_completed": False,
        "file_synced": False,
        "session_deleted": False,
        "project_deleted": False,
    }

    timeout = httpx.Timeout(90, connect=20)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout, follow_redirects=True) as client:
        token_response = await _request(
            client,
            "POST",
            "/api/v1/auth/token",
            data={"username": username, "password": password},
        )
        token = token_response.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        checks["authenticated"] = True

        credentials_response = await _request(client, "GET", "/api/v1/agent/credentials")
        credentials = credentials_response.json().get("credentials", [])
        active_credentials = [credential for credential in credentials if credential.get("is_active")]
        if not active_credentials:
            safe_summary = [
                {
                    "preset_id": credential.get("preset_id"),
                    "model": credential.get("model"),
                    "is_active": credential.get("is_active"),
                }
                for credential in credentials
            ]
            raise RuntimeError(f"no active Agent credential; configured={safe_summary}")

        try:
            await _request(
                client,
                "POST",
                "/api/v1/projects",
                json={
                    "name": project_name,
                    "title": "E2B 生产验收",
                    "content_mode": "marketing",
                    "aspect_ratio": "9:16",
                    "generation_mode": "storyboard",
                },
            )
            project_created = True
            checks["project_created"] = True

            send_response = await _request(
                client,
                "POST",
                f"/api/v1/projects/{project_name}/assistant/sessions/send",
                json={
                    "content": (
                        "这是生产沙盒验收。必须调用 mcp__e2b__bash，执行命令 "
                        "printf 'agent-e2b-ok' > agent_e2b_smoke.txt；"
                        "不要使用本地 Bash 或其他写入工具。完成后只回复 E2B_SMOKE_OK。"
                    )
                },
            )
            session_id = send_response.json()["session_id"]
            checks["session_created"] = True

            deadline = time.monotonic() + 240
            last_snapshot: dict = {}
            while time.monotonic() < deadline:
                snapshot_response = await _request(
                    client,
                    "GET",
                    f"/api/v1/projects/{project_name}/assistant/sessions/{session_id}/snapshot",
                )
                last_snapshot = snapshot_response.json()
                serialized = json.dumps(last_snapshot, ensure_ascii=False)
                checks["e2b_tool_observed"] = "mcp__e2b__bash" in serialized or '"name": "bash"' in serialized
                status = str(last_snapshot.get("status", ""))
                if status in {"idle", "completed", "error", "interrupted"}:
                    checks["turn_completed"] = status in {"idle", "completed"}
                    break
                await asyncio.sleep(2)
            else:
                raise RuntimeError("Agent turn did not reach a terminal status within 240 seconds")

            file_response = await client.get(f"/api/v1/files/{project_name}/agent_e2b_smoke.txt")
            checks["file_synced"] = file_response.status_code == 200 and file_response.text == "agent-e2b-ok"

            if not all(
                checks[key]
                for key in (
                    "authenticated",
                    "project_created",
                    "session_created",
                    "e2b_tool_observed",
                    "turn_completed",
                    "file_synced",
                )
            ):
                status = last_snapshot.get("status", "unknown")
                # This is a dedicated temporary project containing only the
                # fixed smoke prompt, so a bounded snapshot is safe and makes
                # model/tool-routing failures diagnosable without exposing auth.
                snapshot = json.dumps(last_snapshot, ensure_ascii=False, sort_keys=True)[-8_000:]
                raise RuntimeError(
                    f"production Agent E2B checks failed (status={status}): {checks}; snapshot={snapshot}"
                )
        finally:
            if session_id is not None:
                response = await client.delete(f"/api/v1/projects/{project_name}/assistant/sessions/{session_id}")
                checks["session_deleted"] = response.status_code in {200, 404}
            if project_created:
                response = await client.delete(f"/api/v1/projects/{project_name}")
                checks["project_deleted"] = response.status_code in {200, 404}

    print(json.dumps({"ok": all(checks.values()), "checks": checks}, sort_keys=True))
    if not all(checks.values()):
        raise RuntimeError("production Agent E2B cleanup checks failed")


if __name__ == "__main__":
    asyncio.run(main())
