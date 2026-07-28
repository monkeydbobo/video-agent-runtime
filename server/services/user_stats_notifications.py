"""Daily Discord report for registered oioi.bio users."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import func, select

from lib.db import async_session_factory
from lib.db.models.user import User
from server.services.registration_notifications import _discord_webhook_url

logger = logging.getLogger(__name__)

_DEFAULT_REPORT_TIME = "18:00"
_DEFAULT_TIMEZONE = "Asia/Shanghai"
_MAX_USERNAMES = 20
_DISCORD_EMBED_FIELD_LIMIT = 1024


def _report_schedule() -> tuple[int, int, ZoneInfo]:
    """Read the report schedule, falling back safely when configuration is invalid."""
    raw_time = os.getenv("USER_STATS_REPORT_TIME", _DEFAULT_REPORT_TIME).strip()
    raw_timezone = os.getenv("USER_STATS_REPORT_TIMEZONE", _DEFAULT_TIMEZONE).strip()
    try:
        hour_text, minute_text = raw_time.split(":", maxsplit=1)
        hour, minute = int(hour_text), int(minute_text)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError
    except ValueError:
        logger.warning("USER_STATS_REPORT_TIME=%r 无效，已回退到 %s", raw_time, _DEFAULT_REPORT_TIME)
        hour, minute = (18, 0)

    try:
        timezone = ZoneInfo(raw_timezone)
    except ZoneInfoNotFoundError:
        logger.warning("USER_STATS_REPORT_TIMEZONE=%r 无效，已回退到 %s", raw_timezone, _DEFAULT_TIMEZONE)
        timezone = ZoneInfo(_DEFAULT_TIMEZONE)
    return hour, minute, timezone


def _next_report_at(now: datetime | None = None) -> datetime:
    """Return the next scheduled report timestamp in the configured timezone."""
    hour, minute, timezone = _report_schedule()
    local_now = now.astimezone(timezone) if now is not None else datetime.now(timezone)
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


def _user_list_value(usernames: list[str]) -> str:
    """Keep the Discord embed field valid even when names grow in the future."""
    if not usernames:
        return "暂无已注册用户"
    value = "\n".join(usernames[:_MAX_USERNAMES])
    return value[:_DISCORD_EMBED_FIELD_LIMIT]


async def notify_daily_user_stats() -> bool:
    """Post the current registered-user count to Discord, without affecting the app."""
    webhook_url = _discord_webhook_url()
    if webhook_url is None:
        logger.info("未设置 Discord Webhook，跳过每日用户统计")
        return False

    try:
        async with async_session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(User))
            usernames = list(
                (
                    await session.scalars(select(User.username).order_by(User.created_at.desc()).limit(_MAX_USERNAMES))
                ).all()
            )

        now = datetime.now(ZoneInfo(_DEFAULT_TIMEZONE))
        payload = {
            "allowed_mentions": {"parse": []},
            "embeds": [
                {
                    "title": "📊 oioi.bio 每日用户统计",
                    "description": f"统计时间：{now:%Y-%m-%d %H:%M}（北京时间）",
                    "fields": [
                        {"name": "注册用户总数", "value": str(count or 0), "inline": True},
                        {
                            "name": f"最近注册用户（最多 {_MAX_USERNAMES} 位）",
                            "value": _user_list_value(usernames),
                            "inline": False,
                        },
                    ],
                    "color": 3447003,
                    "footer": {"text": "oioi.bio 自动统计"},
                }
            ],
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        logger.info("Discord 每日用户统计发送成功：%d 位用户", count or 0)
        return True
    except Exception:
        logger.exception("Discord 每日用户统计发送失败")
        return False


async def run_daily_user_stats_reporter(stop_event: asyncio.Event) -> None:
    """Wait until the next configured time, report, and repeat until shutdown."""
    while True:
        next_report_at = _next_report_at()
        delay_seconds = max((next_report_at - datetime.now(next_report_at.tzinfo)).total_seconds(), 0)
        logger.info("每日用户统计已安排在 %s", next_report_at.isoformat())
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay_seconds)
            return
        except TimeoutError:
            await notify_daily_user_stats()
