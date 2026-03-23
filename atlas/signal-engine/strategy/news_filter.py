"""
signal-engine/strategy/news_filter.py
News Event Filter — Rule 7.4 of TJR Operational Document.
Checks economic calendar for high-impact events within the LKZ.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Dict, Any
import pytz

from config import LKZ_START_EST, LKZ_END_EST

EST = pytz.timezone("America/New_York")


def is_news_blocked(
    news_events: List[Dict[str, Any]],
    now_utc: datetime,
) -> bool:
    """
    Rule 7.4a: Returns True if a red-folder (high-impact) news event
    is scheduled between 02:00–05:00 EST today.

    If True, the entire session is a NO_TRADE — do not attempt to
    classify any Judas sweep.

    News event dict format:
        {
            "datetime_utc": "2024-03-17T08:30:00",
            "impact": "red",    # "red" | "orange" | "yellow"
            "currency": "USD",  # or "EUR"
            "event": "CPI m/m",
            "hour_est": 3       # pre-computed EST hour
        }

    Args:
        news_events: List of events from Redis news_cache.
        now_utc:     Current UTC datetime.

    Returns:
        True if session is blocked by high-impact news.
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_est = now_utc.astimezone(EST)
    today = now_est.date()

    for ev in news_events:
        # Accept pre-computed hour_est or parse from datetime_utc
        ev_hour_est = ev.get("hour_est")
        if ev_hour_est is None:
            dt_str = ev.get("datetime_utc", "")
            if not dt_str:
                continue
            try:
                ev_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                ev_est = ev_dt.astimezone(EST)
                ev_hour_est = ev_est.hour
                # Only consider today's events
                if ev_est.date() != today:
                    continue
            except (ValueError, TypeError):
                continue

        impact   = ev.get("impact", "").lower()
        currency = ev.get("currency", "").upper()

        # Only EUR and USD events affect EUR/USD (Rule 7.4)
        if currency not in ("EUR", "USD"):
            continue

        # Rule 7.4a: red-folder within LKZ hours → session blocked
        if impact == "red" and LKZ_START_EST <= ev_hour_est < LKZ_END_EST:
            return True

    return False


def get_lkz_news_warnings(
    news_events: List[Dict[str, Any]],
    now_utc: datetime,
) -> List[Dict[str, Any]]:
    """
    Rule 7.4b/7.4c: Returns non-blocking news warnings for dashboard display.

    - Orange events within LKZ: logged, reduce confluence score
    - Red events 05:00–08:00 EST: close runner 15 min before (Rule 7.4b)
    """
    warnings = []
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_est = now_utc.astimezone(EST)
    today = now_est.date()

    for ev in news_events:
        ev_hour_est = ev.get("hour_est")
        currency    = ev.get("currency", "").upper()
        impact      = ev.get("impact", "").lower()

        if currency not in ("EUR", "USD"):
            continue

        if ev_hour_est is None:
            dt_str = ev.get("datetime_utc", "")
            if not dt_str:
                continue
            try:
                ev_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                ev_est = ev_dt.astimezone(EST)
                if ev_est.date() != today:
                    continue
                ev_hour_est = ev_est.hour
            except (ValueError, TypeError):
                continue

        # Warn about orange events in LKZ (Rule 10, Factor 8 score 1)
        if impact == "orange" and LKZ_START_EST <= ev_hour_est < LKZ_END_EST:
            warnings.append({**ev, "warning_type": "ORANGE_IN_LKZ"})

        # Warn about red events post-LKZ (Rule 7.4b: close runner 15 min before)
        if impact == "red" and LKZ_END_EST <= ev_hour_est < 8:
            warnings.append({**ev, "warning_type": "RED_POST_LKZ_CLOSE_RUNNER"})

    return warnings