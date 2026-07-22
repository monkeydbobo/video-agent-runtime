"""Run a real E2B lifecycle smoke test without printing credentials or sandbox IDs."""

from __future__ import annotations

import asyncio
import json
import os

from e2b import AsyncSandbox


async def main() -> None:
    if not os.environ.get("E2B_API_KEY", "").strip():
        raise RuntimeError("E2B_API_KEY is not configured")

    template = os.environ.get("ARCREEL_E2B_TEMPLATE", "base").strip() or "base"
    sandbox: AsyncSandbox | None = None
    sandbox_id: str | None = None
    checks: dict[str, bool] = {
        "created": False,
        "command": False,
        "file_read": False,
        "paused": False,
        "resumed": False,
        "persistence": False,
        "killed": False,
    }
    try:
        sandbox = await AsyncSandbox.create(
            template,
            timeout=120,
            metadata={"application": "arcreel", "purpose": "smoke-test"},
            secure=True,
            allow_internet_access=False,
            lifecycle={"on_timeout": "pause", "auto_resume": True},
        )
        sandbox_id = sandbox.sandbox_id
        checks["created"] = True

        result = await sandbox.commands.run(
            "printf 'e2b-ok' > /tmp/arcreel-e2b-smoke.txt",
            timeout=30,
        )
        checks["command"] = result.exit_code == 0
        checks["file_read"] = await sandbox.files.read("/tmp/arcreel-e2b-smoke.txt", format="text") == "e2b-ok"

        await sandbox.pause()
        checks["paused"] = True
        sandbox = await AsyncSandbox.connect(sandbox_id, timeout=120)
        checks["resumed"] = await sandbox.is_running()
        checks["persistence"] = await sandbox.files.read("/tmp/arcreel-e2b-smoke.txt", format="text") == "e2b-ok"
    finally:
        if sandbox is not None:
            await sandbox.kill()
            checks["killed"] = True
        elif sandbox_id is not None:
            await AsyncSandbox.kill(sandbox_id)
            checks["killed"] = True

    if not all(checks.values()):
        raise RuntimeError(f"E2B smoke test failed: {json.dumps(checks, sort_keys=True)}")
    print(json.dumps({"ok": True, "checks": checks}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
