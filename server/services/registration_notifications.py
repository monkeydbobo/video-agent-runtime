"""Best-effort notifications for successful self-service registrations."""

import logging
import os
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DISCORD_WEBHOOK_HOSTS = {"discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"}


def _discord_webhook_url() -> str | None:
    """Return a configured Discord incoming-webhook URL only when it is safe to use."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return None

    parsed = urlparse(webhook_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _DISCORD_WEBHOOK_HOSTS
        or not parsed.path.startswith("/api/webhooks/")
    ):
        logger.warning("DISCORD_WEBHOOK_URL 格式无效，已跳过注册通知")
        return None
    return webhook_url


async def notify_new_registration(username: str) -> None:
    """Send a registration alert without ever affecting the sign-up result."""
    webhook_url = _discord_webhook_url()
    if webhook_url is None:
        return

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                webhook_url,
                json={"content": f"🎉 oioi.bio 有新用户注册：`{username}`"},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Discord 注册通知发送失败", exc_info=True)
