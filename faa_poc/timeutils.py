"""Time parsing and alert-anchored windows."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def parse_dt(value: str | None) -> datetime | None:
    if not value: return None
    text = str(value).strip()
    if not text: return None
    variants = [text, text.replace("Z", "+00:00"), text.replace(" ", "T"), text.replace("Z", "+00:00").replace(" ", "T")]
    for v in variants:
        try:
            dt = datetime.fromisoformat(v)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y%m%d%H%M", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None

def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def alert_search_window(alert_opened_at: str | None, *, pre_hours: int, post_hours: int, now: datetime | None = None) -> tuple[str, str, str]:
    """Return (publishedAfter, publishedBefore, source).

    The primary window is anchored to the alert opening, not to run time.
    A marked fallback is retained only for malformed alert timestamps and
    cannot support a substantive absence-of-visibility inference.
    """
    now = now or utcnow()
    opened = parse_dt(alert_opened_at)
    if opened:
        start = opened - timedelta(hours=pre_hours)
        end = min(now, opened + timedelta(hours=post_hours))
        return iso_z(start), iso_z(end), "alert_anchored"
    start = now - timedelta(hours=post_hours)
    return iso_z(start), iso_z(now), "fallback_run_anchored"

def hours_from_alert(comment_published_at: str | None, alert_opened_at: str | None) -> float | None:
    comment, alert = parse_dt(comment_published_at), parse_dt(alert_opened_at)
    if not comment or not alert: return None
    return round((comment - alert).total_seconds() / 3600, 3)

def in_event_window(comment_published_at: str | None, alert_opened_at: str | None, window_hours: int) -> bool | None:
    h = hours_from_alert(comment_published_at, alert_opened_at)
    return None if h is None else abs(h) <= window_hours
