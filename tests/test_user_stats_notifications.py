from datetime import UTC, datetime

from server.services import user_stats_notifications as notifications


def test_next_report_is_today_when_time_is_still_ahead(monkeypatch):
    monkeypatch.setenv("USER_STATS_REPORT_TIME", "18:00")
    now = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)

    assert notifications._next_report_at(now) == datetime(
        2026, 7, 28, 18, 0, tzinfo=notifications.ZoneInfo("Asia/Shanghai")
    )


def test_next_report_rolls_to_tomorrow_after_scheduled_time(monkeypatch):
    monkeypatch.setenv("USER_STATS_REPORT_TIME", "18:00")
    now = datetime(2026, 7, 28, 11, 0, tzinfo=UTC)

    assert notifications._next_report_at(now) == datetime(
        2026, 7, 29, 18, 0, tzinfo=notifications.ZoneInfo("Asia/Shanghai")
    )


def test_user_list_is_limited_to_discord_embed_size():
    assert notifications._user_list_value([]) == "暂无已注册用户"
    assert len(notifications._user_list_value(["a" * 64] * 20)) <= 1024
