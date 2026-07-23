"""将本地 SQLite 中启用的供应商配置安全同步到 ArcReel 生产 API。

脚本不会输出 API Key；默认仅预览，显式传入 ``--apply`` 才会修改生产配置。
生产账号从 ``AUTH_USERNAME`` / ``AUTH_PASSWORD`` 环境变量读取。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from lib.agent_provider_catalog import get_preset

SYNCED_SYSTEM_KEYS = (
    "default_video_backend",
    "default_image_backend",
    "default_image_backend_t2i",
    "default_image_backend_i2i",
    "default_text_backend",
    "text_backend_script",
    "text_backend_overview",
    "text_backend_style",
    "video_generate_audio",
)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def _rows(connection: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(query).fetchall()]


def _clean(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _local_configuration(database: Path) -> dict[str, Any]:
    with sqlite3.connect(database) as connection:
        provider_credentials = _rows(
            connection,
            """
            SELECT provider, name, api_key, base_url
            FROM provider_credential
            WHERE is_active = 1
            ORDER BY provider, id
            """,
        )
        provider_configs = _rows(
            connection,
            "SELECT provider, key, value FROM provider_config ORDER BY provider, key",
        )
        agent_credentials = _rows(
            connection,
            """
            SELECT preset_id, display_name, base_url, api_key, model,
                   haiku_model, sonnet_model, opus_model, subagent_model
            FROM agent_anthropic_credentials
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
        )
        system_rows = _rows(
            connection,
            "SELECT key, value FROM system_setting",
        )

    settings = {row["key"]: _clean(row["value"]) for row in system_rows if row["key"] in SYNCED_SYSTEM_KEYS}
    if "video_generate_audio" in settings:
        settings["video_generate_audio"] = str(settings["video_generate_audio"]).lower() in {"1", "true", "yes"}

    agent = agent_credentials[0] if agent_credentials else None
    if agent:
        agent = {key: _clean(value) for key, value in agent.items()}
        preset = get_preset(agent["preset_id"])
        if preset and (
            not agent.get("model")
            or (agent["preset_id"] == "ark-coding-plan" and agent["model"] != preset.default_model)
        ):
            agent["model"] = preset.default_model

    return {
        "provider_credentials": [
            {key: _clean(value) for key, value in credential.items()} for credential in provider_credentials
        ],
        "provider_configs": [{key: _clean(value) for key, value in config.items()} for config in provider_configs],
        "agent_credential": agent,
        "system_settings": settings,
    }


def _request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response


def _authenticate(client: httpx.Client) -> None:
    response = _request(
        client,
        "POST",
        "/api/v1/auth/token",
        data={"username": _required_env("AUTH_USERNAME"), "password": _required_env("AUTH_PASSWORD")},
    )
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


def _safe_preview(local: dict[str, Any]) -> dict[str, Any]:
    agent = local["agent_credential"]
    return {
        "providers": [
            {"provider": row["provider"], "name": row["name"], "key_configured": bool(row["api_key"])}
            for row in local["provider_credentials"]
        ],
        "provider_config_keys": [f"{row['provider']}.{row['key']}" for row in local["provider_configs"]],
        "agent": {
            "preset_id": agent["preset_id"],
            "model": agent["model"],
            "key_configured": bool(agent["api_key"]),
        }
        if agent
        else None,
        "system_settings": local["system_settings"],
    }


def _sync_provider_credentials(client: httpx.Client, local: dict[str, Any], operations: list[str]) -> None:
    for credential in local["provider_credentials"]:
        provider = credential["provider"]
        current = _request(client, "GET", f"/api/v1/providers/{provider}/credentials").json()["credentials"]
        matched = next((item for item in current if item["name"] == credential["name"]), None)
        payload = {
            "name": credential["name"],
            "api_key": credential["api_key"],
            "base_url": credential["base_url"] or None,
        }
        if matched:
            credential_id = matched["id"]
            _request(client, "PATCH", f"/api/v1/providers/{provider}/credentials/{credential_id}", json=payload)
            operations.append(f"updated provider credential: {provider}/{credential['name']}")
        else:
            created = _request(client, "POST", f"/api/v1/providers/{provider}/credentials", json=payload).json()
            credential_id = created["id"]
            operations.append(f"created provider credential: {provider}/{credential['name']}")
        _request(client, "POST", f"/api/v1/providers/{provider}/credentials/{credential_id}/activate")
        operations.append(f"activated provider credential: {provider}/{credential['name']}")


def _sync_provider_configs(client: httpx.Client, local: dict[str, Any], operations: list[str]) -> None:
    grouped: dict[str, dict[str, str]] = {}
    for row in local["provider_configs"]:
        grouped.setdefault(row["provider"], {})[row["key"]] = row["value"]
    for provider, values in grouped.items():
        _request(client, "PATCH", f"/api/v1/providers/{provider}/config", json=values)
        operations.append(f"updated provider config: {provider} ({', '.join(sorted(values))})")


def _sync_agent_credential(client: httpx.Client, local: dict[str, Any], operations: list[str]) -> None:
    credential = local["agent_credential"]
    if not credential:
        return
    current = _request(client, "GET", "/api/v1/agent/credentials").json()["credentials"]
    matched = next((item for item in current if item["preset_id"] == credential["preset_id"]), None)
    payload = {
        "display_name": credential["display_name"],
        "base_url": credential["base_url"],
        "api_key": credential["api_key"],
        "model": credential["model"],
        "haiku_model": credential["haiku_model"] or None,
        "sonnet_model": credential["sonnet_model"] or None,
        "opus_model": credential["opus_model"] or None,
        "subagent_model": credential["subagent_model"] or None,
    }
    if matched:
        credential_id = matched["id"]
        _request(client, "PATCH", f"/api/v1/agent/credentials/{credential_id}", json=payload)
        operations.append(f"updated Agent credential: {credential['preset_id']}")
    else:
        created = _request(
            client,
            "POST",
            "/api/v1/agent/credentials",
            json={"preset_id": credential["preset_id"], "activate": True, **payload},
        ).json()
        credential_id = created["id"]
        operations.append(f"created Agent credential: {credential['preset_id']}")
    _request(client, "POST", f"/api/v1/agent/credentials/{credential_id}/activate")
    operations.append(f"activated Agent credential: {credential['preset_id']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("projects/.arcreel.db"))
    parser.add_argument("--base-url", default="https://oioi.bio")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    local = _local_configuration(args.database)
    if not args.apply:
        print(
            json.dumps({"mode": "preview", "configuration": _safe_preview(local)}, ensure_ascii=False, sort_keys=True)
        )
        return

    operations: list[str] = []
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=90, follow_redirects=True) as client:
        _authenticate(client)
        _sync_provider_credentials(client, local, operations)
        _sync_provider_configs(client, local, operations)
        if local["system_settings"]:
            _request(client, "PATCH", "/api/v1/system/config", json=local["system_settings"])
            operations.append("updated system defaults")
        _sync_agent_credential(client, local, operations)

    print(json.dumps({"mode": "apply", "ok": True, "operations": operations}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
