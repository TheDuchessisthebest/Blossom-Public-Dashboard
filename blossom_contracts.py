"""Pure, read-only rules for recognizing official Polymarket US BTC series.

Series mapping is based on the published public contract rules for the
standardized 5m, 15m and hourly BTC Up/Down instruments. This helper does NOT
perform trading, modify a database, or access the network.
"""
from __future__ import annotations
from datetime import datetime, timezone
import re
from typing import Any

DURATIONS = {'5m': 300, '15m': 900, '1h': 3600}
# THIS PATTERN IS NOT A SUBSTITUTE FOR AN EXCHANGE LOOKUP; it only matches
# previously stored market records whose outcomes came from official API.
STANDARD = re.compile(r'^cpc-btc-updown-(5m|15m|1h)-(20\d\d)-(\d\d)-(\d\d)-(\d\d)(\d\d)z$')
SERIES_RULES = 'POLYMARKET_US_PUBLISHED_BTC_UP_DOWN_BRTI_RULES_2026_11'


def verified_standard_series(slug: str, timeframe: str, start: Any, end: Any) -> bool:
    """Allow published-rule mapping only for exact contract ID + correct window."""
    if not isinstance(slug, str) or timeframe not in DURATIONS:
        return False
    m = STANDARD.fullmatch(slug)
    if not m or m[1] != timeframe:
        return False
    try:
        start_from_slug = datetime(*(int(x) for x in m.groups()[1:]), tzinfo=timezone.utc).timestamp()
        # Date args are Y, M, D, H, Minute. Check the series interval aligns.
        return (int(start_from_slug) % DURATIONS[timeframe] == 0
                and abs(float(start)-start_from_slug) <= 2
                and abs(float(end)-(start_from_slug + DURATIONS[timeframe])) <= 2)
    except (ValueError, TypeError, OverflowError):
        return False

