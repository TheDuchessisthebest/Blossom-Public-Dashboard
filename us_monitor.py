"""Read-only Polymarket US BTC time-window monitoring helpers.

No auth, wallet handling or order-writing code. Market window times derived
from UTC timestamped slugs are ESTIMATES, not settlement verification.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
import time
from typing import Any

DURATIONS = {"5m": 300, "15m": 900, "1h": 3600}
BTC_PATTERN = re.compile(r"\b(?:btc|bitcoin)\b", re.I)
DIRECTION_PATTERN = re.compile(r"(?:\bup\s*(?:or|/)\s*down\b|\bupdown\b)", re.I)
TIMEFRAME_PATTERNS = {
    "5m": re.compile(r"\b(?:5\s*[- ]?(?:m|min|mins|minute|minutes)|five[- ]minute[s]?)\b", re.I),
    "15m": re.compile(r"\b(?:15\s*[- ]?(?:m|min|mins|minute|minutes)|fifteen[- ]minute[s]?)\b", re.I),
    "1h": re.compile(r"\b(?:1\s*[- ]?(?:h|hr|hrs|hour|hours)|60\s*[- ]?(?:m|min|mins|minute|minutes)|one[- ]hour|hourly)\b", re.I),
}
STAMP = re.compile(r"(?<!\d)(20\d{2})[-_](\d{2})[-_](\d{2})[-_](\d{2})(\d{2})z(?:$|[-_])", re.I)


def timeframe_of(text: str) -> str | None:
    hits = [k for k, pat in TIMEFRAME_PATTERNS.items() if pat.search(text)]
    return hits[0] if len(hits) == 1 else None


def market_matches(text: str, timeframe: str | None = None) -> bool:
    tf = timeframe_of(text)
    return bool(BTC_PATTERN.search(text) and DIRECTION_PATTERN.search(text) and tf and (timeframe is None or tf == timeframe))


def date_ts(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000 if float(value) > 1e11 else float(value)
    try:
        s = str(value).strip()
        if s.isdigit():
            return date_ts(float(s))
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError, TypeError):
        return None


def slug_start_ts(slug: str) -> float | None:
    """Parse candidate start time from an explicitly UTC-stamped market slug.

    Do not treat catalog 'endTime' (possibly an event end) as market settlement.
    """
    match = STAMP.search(slug)
    if not match:
        return None
    try:
        y, mo, d, h, mi = map(int, match.groups())
        return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def price(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("value")
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if 0 <= n <= 1 else None
    except (TypeError, ValueError):
        return None


def unpack_bbo(payload: dict) -> dict:
    md = payload.get("marketData") or {}
    if not isinstance(md, dict):
        md = {}
    return {
        "bid": price(md.get("bestBid")),
        "ask": price(md.get("bestAsk")),
        "last": price(md.get("lastTradePx")),
        "exchange_time": md.get("transactTime"),
    }


def _label(node: dict) -> str:
    keys = ("title", "name", "question", "description", "slug", "marketSlug", "ticker", "symbol")
    return " ".join(str(node[k]) for k in keys if k in node and node[k] is not None and not isinstance(node[k], (list, dict)))


def discover_candidates(response: Any) -> list[dict]:
    """Discover nested US BTC Up/Down market slugs, by exact timeframe.

    Prefer the market slug's timeframe to parent event label; avoid falsely
    interpreting event endTime as the five-/fifteen-/sixty-minute close.
    """
    found: dict[str, dict] = {}

    def walk(obj: Any, ancestry: str = "", in_markets: bool = False) -> None:
        if isinstance(obj, list):
            for item in obj:
                walk(item, ancestry, in_markets)
            return
        if not isinstance(obj, dict):
            return
        label = _label(obj)
        context = f"{ancestry} {label}".strip()
        slug = obj.get("marketSlug") or obj.get("slug")
        if in_markets and isinstance(slug, str) and slug:
            # market-specific duration wins over ancestor event duration
            tf = timeframe_of(slug) or timeframe_of(label) or timeframe_of(ancestry)
            if tf and BTC_PATTERN.search(context) and DIRECTION_PATTERN.search(context):
                stamp = slug_start_ts(slug)
                # Only use metadata time for an independently consistent duration.
                if stamp is None:
                    meta_start = date_ts(obj.get("startTime") or obj.get("startDate") or obj.get("openingTime"))
                    meta_end = date_ts(obj.get("closeTime") or obj.get("endTime") or obj.get("closingTime"))
                    if meta_start is not None and meta_end is not None and abs((meta_end - meta_start) - DURATIONS[tf]) < 30:
                        stamp = meta_start
                found[slug] = {
                    "slug": slug,
                    "title": str(obj.get("title") or obj.get("question") or obj.get("name") or ancestry).strip(),
                    "timeframe": tf,
                    "start": stamp,
                    "end": stamp + DURATIONS[tf] if stamp is not None else None,
                    "catalog_end": next((date_ts(obj.get(k)) for k in ("endTime", "closeTime", "closingTime") if date_ts(obj.get(k)) is not None), None),
                    "active": obj.get("active"),
                }
        for key, value in obj.items():
            if isinstance(value, (list, dict)):
                walk(value, context[:250], in_markets or key in ("markets", "market", "marketData"))
    walk(response)
    return list(found.values())


def market_status(market: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    if market.get("active") is False:
        return "inactive"
    start, end = market.get("start"), market.get("end")
    if start is None or end is None:
        return "unverified"
    if now < start:
        return "upcoming"
    if now >= end:
        return "expired"
    return "estimated_active"


def prioritize(candidates: list[dict], now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    priority = {"estimated_active": 0, "upcoming": 1, "unverified": 2, "expired": 3, "inactive": 4}
    return sorted(candidates, key=lambda c: (priority[market_status(c, now)], abs((c.get("start") or now) - now)))


def active_for(candidates: list[dict], timeframe: str, now: float | None = None) -> dict | None:
    now = time.time() if now is None else now
    possibilities = [m for m in candidates if m.get("timeframe") == timeframe and market_status(m, now) == "estimated_active"]
    # If duplicates overlap, prefer the latest-starting round.
    return max(possibilities, key=lambda x: x["start"]) if possibilities else None


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at REAL NOT NULL,
            market_slug TEXT NOT NULL,
            bid REAL,
            ask REAL,
            last_trade REAL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_us_quotes ON quotes(market_slug, recorded_at)")


def store_quote(path: Path, slug: str, row: dict) -> None:
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute("INSERT INTO quotes(recorded_at,market_slug,bid,ask,last_trade) VALUES(?,?,?,?,?)",
                     (time.time(), slug, row["bid"], row["ask"], row["last"]))


def quote_history(path: Path, slug: str, limit: int = 500) -> list[dict]:
    if not path.exists():
        return []
    with sqlite3.connect(path, timeout=10) as conn:
        rows = conn.execute("SELECT recorded_at,bid,ask,last_trade FROM quotes WHERE market_slug=? ORDER BY recorded_at DESC LIMIT ?", (slug, limit)).fetchall()
    return [dict(recorded_at=x[0], bid=x[1], ask=x[2], last_trade=x[3]) for x in reversed(rows)]

# V0.6: all timestamps below are UTC; a generated slug is NEVER trusted unless
# an official market retrieval returns the matching slug.
from collections.abc import Callable


def probe_slugs(tf: str, now: float, before: int = 1, after: int = 1) -> list[str]:
    """Candidate official US slugs around the current UTC window.

    5m catalog results can lag after rollover. A probe is just a candidate,
    and does not constitute evidence that a contract exists or is tradeable.
    """
    if tf not in DURATIONS:
        raise ValueError(f"Unsupported timeframe: {tf}")
    step = DURATIONS[tf]
    base = int(now // step) * step
    results = []
    for i in range(-before, after + 1):
        dt = datetime.fromtimestamp(base + i * step, tz=timezone.utc)
        results.append(f"cpc-btc-updown-{tf}-{dt:%Y-%m-%d-%H%M}z")
    return results


def verified_market_reply(response: Any, requested_slug: str) -> dict | None:
    """Only return a candidate when US API confirms exact requested slug.

    The upstream API response might be a market dict or a {market: {...}}
    wrapper. NEVER accept an arbitrary 200 response that lacks identity.
    """
    if not isinstance(response, dict):
        return None
    pool = [response]
    for key in ("market", "data", "result"):
        item = response.get(key)
        if isinstance(item, dict):
            pool.append(item)
    for obj in pool:
        actual_slug = obj.get("marketSlug") or obj.get("slug")
        if actual_slug != requested_slug:
            continue
        tf = timeframe_of(requested_slug)
        start = slug_start_ts(requested_slug)
        if not tf or start is None or not market_matches(requested_slug, tf):
            return None
        # An explicit closed/disabled market must not appear as live.
        if obj.get("active") is False or obj.get("closed") is True:
            return None
        return {
            "slug": requested_slug, "title": str(obj.get("title") or obj.get("question") or "BTC Up or Down"),
            "timeframe": tf, "start": start, "end": start + DURATIONS[tf],
            "active": obj.get("active"), "verified": True, "source": "US retrieve_by_slug",
        }
    return None


def discover_by_direct_lookup(client: Any, timeframe: str, now: float, *,
                              max_requests: int = 3) -> list[dict]:
    """Verify current/neighbor rounds through official Polymarket US SDK.

    Only query a few candidates. Earlier/current markets are checked before
    future ones; provider 404s are normal and quietly ignored.
    """
    candidates = probe_slugs(timeframe, now)
    # current -> previous -> upcoming; no display of unverified guesses
    order = [1, 0, 2]
    found = []
    for index in order[:max_requests]:
        slug = candidates[index]
        try:
            market = verified_market_reply(client.markets.retrieve_by_slug(slug), slug)
        except Exception:
            continue
        if market is not None:
            found.append(market)
    return found


def assess_market_lean(quote: dict | None, market: dict | None, now: float,
                       *, max_spread: float = .06, min_seconds: int = 20) -> dict:
    """Observed order-book lean ONLY, not AI probability or a trading signal.

    YES is a share contract outcome. Its relationship to Bitcoin direction
    must be confirmed from US contract rules before any execution strategy.
    """
    wait = {"lean": "WAIT", "mid": None, "reason": "No fresh, usable quote", "strength": None}
    if market is None or market_status(market, now) != "estimated_active":
        return {**wait, "reason": "Active contract not verified"}
    if market.get("end") is None or market["end"] - now < min_seconds:
        return {**wait, "reason": "Too close to estimated window end"}
    if not quote:
        return wait
    # A stale, closed or otherwise invalid response is never a research signal.
    health = quote.get("health")
    if health is not None and health not in ("BBO_OK", "BOOK_OK", "CACHED_OK"):
        return {**wait, "reason": quote_health_explanation(quote)}
    if health == "CACHED_OK" and quote.get("sample_age_seconds", 99999) > 30:
        return {**wait, "reason": "Cached observation is older than 30 seconds"}
    bid, ask = quote.get("bid"), quote.get("ask")
    if bid is None or ask is None or not (0 <= bid <= ask <= 1):
        return {**wait, "reason": "Bid/ask missing or invalid"}
    spread = ask - bid
    if spread > max_spread:
        return {**wait, "reason": f"Spread {spread:.3f} is too wide"}
    mid = (bid + ask) / 2
    if mid >= .60:
        side, reason = "YES LEAN", "Market favors YES; NOT an independent forecast"
    elif mid <= .40:
        side, reason = "NO LEAN", "Market favors NO; NOT an independent forecast"
    else:
        side, reason = "NO LEAN YET", "Order-book midpoint is near 50/50"
    if health == "CACHED_OK":
        reason = f"Cached {int(quote.get('sample_age_seconds', 0))}s ago; " + reason
    return {"lean": side, "mid": mid, "reason": reason, "strength": abs(mid-.5)*2}


def init_calls_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS market_calls (
            market_slug TEXT PRIMARY KEY,
            recorded_at REAL NOT NULL,
            timeframe TEXT NOT NULL,
            lean TEXT NOT NULL,
            yes_bid REAL,
            yes_ask REAL,
            midpoint REAL,
            result TEXT NOT NULL DEFAULT 'PENDING',
            checked_at REAL NOT NULL DEFAULT 0,
            settlement REAL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_us_calls_date ON market_calls(recorded_at DESC)")


def record_market_call(path: Path, market: dict, quote: dict, assessment: dict,
                       now: float) -> None:
    """One first qualified call per round, deduped across 5-second reruns.

    An initial neutral/WAIT observation can be replaced by a later first
    directional lean, but a directional call is immutable afterward. This
    never rewrites a call in light of the winning outcome.
    """
    if market_status(market, now) != "estimated_active":
        return
    with sqlite3.connect(path, timeout=10) as conn:
        params = (
            market["slug"], now, market["timeframe"], assessment["lean"],
            quote.get("bid"), quote.get("ask"), assessment.get("mid"),
        )
        conn.execute("""INSERT OR IGNORE INTO market_calls(
            market_slug,recorded_at,timeframe,lean,yes_bid,yes_ask,midpoint)
            VALUES (?,?,?,?,?,?,?)""", params)
        if assessment["lean"] in ("YES LEAN", "NO LEAN"):
            conn.execute("""UPDATE market_calls SET recorded_at=?, lean=?,
                yes_bid=?, yes_ask=?, midpoint=?
                WHERE market_slug=? AND result='PENDING'
                AND lean IN ('WAIT','NO LEAN YET')""",
                (now, assessment["lean"], quote.get("bid"), quote.get("ask"),
                 assessment.get("mid"), market["slug"]))


def recent_market_calls(path: Path, limit: int = 30) -> list[dict]:
    if not path.exists():
        return []
    with sqlite3.connect(path, timeout=10) as conn:
        rows = conn.execute("""SELECT market_slug, recorded_at, timeframe, lean,
            yes_bid, yes_ask, midpoint, result, checked_at, settlement
            FROM market_calls ORDER BY recorded_at DESC LIMIT ?""", (limit,)).fetchall()
    keys = ("market_slug", "recorded_at", "timeframe", "lean", "yes_bid",
            "yes_ask", "midpoint", "result", "checked_at", "settlement")
    return [dict(zip(keys, row)) for row in rows]


def settlement_outcome(response: Any) -> float | None:
    """Only accept the unambiguous binary 0/1 final settlement value."""
    if not isinstance(response, dict):
        return None
    raw = response.get("settlement")
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        v = float(raw)
    except (ValueError, TypeError):
        return None
    return v if v in (0.0, 1.0) else None


def resolve_old_calls(path: Path, client: Any, now: float,
                      *, max_checks: int = 2, retry_seconds: int = 180) -> None:
    """Read official final 0/1 settlement after close, bounded and throttled.

    A correct majority observation is NOT an AI accuracy metric. Pending
    stays pending until the US settlement endpoint returns a final 0 or 1.
    """
    with sqlite3.connect(path, timeout=10) as conn:
        jobs = conn.execute("""SELECT market_slug, lean FROM market_calls
            WHERE result='PENDING' AND checked_at<?
            AND recorded_at<? ORDER BY recorded_at DESC LIMIT ?""",
            (now - retry_seconds, now - 400, max_checks * 10)).fetchall()
        processed = 0
        for slug, lean in jobs:
            end = slug_start_ts(slug)
            tf = timeframe_of(slug)
            if end is None or tf not in DURATIONS or end + DURATIONS[tf] + 90 >= now:
                continue
            # Store attempt timestamp even on API failure to prevent requests every 5s
            conn.execute("UPDATE market_calls SET checked_at=? WHERE market_slug=?", (now, slug))
            processed += 1
            try:
                response = client.markets.settlement(slug)
                v = settlement_outcome(response)
            except Exception:
                v = None
            if v is not None:
                expected = "YES LEAN" if v == 1 else "NO LEAN"
                result = ("CORRECT" if lean == expected else "INCORRECT") if lean in ("YES LEAN", "NO LEAN") else "NO CALL"
                conn.execute("UPDATE market_calls SET result=?, settlement=? WHERE market_slug=?", (result, v, slug))
            if processed >= max_checks:
                break

# v0.7: quote health / order-book fallback.
# Official US SDK: markets.bbo(slug)['marketData'] for best bid/ask;
# markets.book(slug)['marketData'] has bids[].px and offers[].px.


def cents(value: float | None) -> str:
    """Display a binary-contract USD/share price in Polymarket-style cents.

    Prices are stored and computed as 0..1 dollar values; ONLY the presentation
    is scaled to 0..100. 64 cents is a price, not a model confidence score.
    """
    val = price(value)
    if val is None:
        return "—"
    number = f"{val * 100:.2f}".rstrip("0").rstrip(".")
    return f"{number}¢"


def _best_level(rows: Any, high: bool) -> tuple[float | None, int]:
    """Read best valid nonzero-size order-book level, regardless of ordering."""
    if not isinstance(rows, list):
        return None, 0
    prices = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        px = price(row.get("px"))
        if px is None:
            continue
        # Missing size is ambiguous; use only an explicitly positive quantity.
        try:
            qty = float(row.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0.0
        if not 0 < qty < float("inf"):
            continue
        prices.append(px)
    return (max(prices) if high else min(prices), len(prices)) if prices else (None, 0)


def unpack_book(payload: Any, expected_slug: str | None = None) -> dict:
    """Safely read a complete/partial order-book snapshot from the official SDK."""
    md = (payload.get("marketData") or {}) if isinstance(payload, dict) else {}
    if not isinstance(md, dict):
        md = {}
    actual = md.get("marketSlug")
    if expected_slug and actual and actual != expected_slug:
        raise ValueError("Order book identity mismatch")
    bid, bids = _best_level(md.get("bids"), True)
    ask, offers = _best_level(md.get("offers"), False)
    stats = md.get("stats") if isinstance(md.get("stats"), dict) else {}
    state = md.get("state") or "UNKNOWN"
    return {
        "bid": bid, "ask": ask, "last": price(stats.get("lastTradePx")),
        "bids": bids, "offers": offers, "state": state,
        "exchange_time": md.get("transactTime"),
    }


def _quote_time_stale(timestamp: Any, observed_at: float, *, max_age: int = 120) -> bool:
    """Only declare stale when the exchange explicitly supplies an old tick time."""
    parsed = date_ts(timestamp)
    return parsed is not None and observed_at - parsed > max_age


def is_rate_limit_error(exc: Exception) -> bool:
    """Recognize the SDK's RateLimitError without relying on SDK internals.

    This is only for market-data requests; order-latency errors use distinct
    wording and must not be interpreted as REST HTTP 429s.
    """
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return ("ratelimit" in name or "rate_limit" in name
            or "429" in message or "too many requests" in message)


def fetch_market_quote(client: Any, slug: str, now: float | None = None,
                       *, allow_book_fallback: bool = True) -> dict:
    """Read BBO first; inspect full US order book if a side is missing.

    A 200 response with empty bestBid/bestAsk is not a valid bid or ask. Never
    infer a quote from lastTradePx, outcomePrices or guess a complement side.
    No authentication or order submission is involved.
    """
    now = time.time() if now is None else now
    out = {
        "bid": None, "ask": None, "last": None, "exchange_time": None,
        "health": "UNKNOWN", "source": "—", "detail": "No quote available",
        "bids": None, "offers": None, "book_state": None,
    }
    err_bbo = None
    try:
        raw = client.markets.bbo(slug)
        md = raw.get("marketData") if isinstance(raw, dict) else None
        if not isinstance(md, dict):
            raise ValueError("Missing marketData")
        reported_slug = md.get("marketSlug")
        if reported_slug and reported_slug != slug:
            raise ValueError("BBO identity mismatch")
        out.update(unpack_bbo(raw))
        out["source"] = "BBO"
        out["book_state"] = md.get("state")
        if md.get("state") == "MARKET_STATE_CLOSED":
            out.update(bid=None, ask=None, health="BOOK_CLOSED",
                       detail="BBO reports a closed market; no tradable quote")
            return out
        if out["bid"] is not None and out["ask"] is not None and out["bid"] <= out["ask"]:
            if _quote_time_stale(out.get("exchange_time"), now):
                out.update(health="STALE", detail="BBO exchange timestamp older than 120 seconds")
            else:
                out.update(health="BBO_OK", detail="Both sides available from the US BBO endpoint")
            return out
        if out["bid"] is not None and out["ask"] is not None:
            err_bbo = "Crossed BBO (bid exceeds ask)"
    except Exception as exc:
        if is_rate_limit_error(exc):
            # Critical: do not immediately follow a 429 with a BOOK request.
            # That would amplify rate limiting across all three timeframes.
            out.update(bid=None, ask=None, last=None, health="RATE_LIMIT",
                       source="BBO", detail="US API rate limited BBO (HTTP 429); request cooldown needed")
            return out
        err_bbo = type(exc).__name__

    if not allow_book_fallback:
        partial = out["bid"] is not None or out["ask"] is not None
        out.update(health="BBO_PARTIAL" if partial else "BBO_EMPTY",
                   detail="BBO did not give two valid sides; full-book probe deferred to reduce API load")
        return out

    # The US order-book endpoint is the authoritative fallback for prices.
    try:
        book = unpack_book(client.markets.book(slug), expected_slug=slug)
        out.update(bids=book["bids"], offers=book["offers"], book_state=book["state"], exchange_time=book.get("exchange_time"))
        if out["last"] is None:
            out["last"] = book["last"]
        if book["state"] == "MARKET_STATE_CLOSED":
            out.update(bid=None, ask=None, health="BOOK_CLOSED", source="BOOK",
                       detail="Exchange reports the order book is closed")
            return out
        bid, ask = book["bid"], book["ask"]
        if bid is not None and ask is not None and bid > ask:
            out.update(bid=None, ask=None, health="INVALID_BOOK", source="BOOK",
                       detail="Full book has crossed prices; ignoring quote")
            return out
        if bid is not None and ask is not None:
            out.update(bid=bid, ask=ask, source="BOOK", exchange_time=book.get("exchange_time"))
            if _quote_time_stale(book.get("exchange_time"), now):
                out.update(health="STALE", detail="Order-book exchange timestamp older than 120 seconds")
            else:
                out.update(health="BOOK_OK", detail="Both sides recovered from full order book")
            return out
        # Keep any BBO partial side if the book could not supply it, but never
        # merge disjoint snapshots into a fabricated two-sided quote.
        if bid is not None or ask is not None:
            out.update(bid=bid, ask=ask, health="ONE_SIDED", source="BOOK",
                       detail=f"Book has {book['bids']} bid level(s) and {book['offers']} offer level(s)")
        elif out["bid"] is not None or out["ask"] is not None:
            out.update(health="ONE_SIDED", source="BBO",
                       detail="BBO contains one side; full book has no valid levels")
        else:
            out.update(health="EMPTY_BOOK", source="BOOK",
                       detail="No usable bid or offer levels on the US order book")
    except Exception as exc:
        if is_rate_limit_error(exc):
            out.update(bid=None, ask=None, last=None, health="RATE_LIMIT",
                       source="BOOK", detail="US API rate limited book request (HTTP 429); cooldown needed")
            return out
        if out["bid"] is not None or out["ask"] is not None:
            out.update(health="ONE_SIDED", detail=f"Partial BBO; book request: {type(exc).__name__}")
        else:
            info = f"BBO: {err_bbo or 'no bid/ask'}; book: {type(exc).__name__}"
            out.update(health="API_ERROR", detail=info)
    return out


def quote_health_explanation(quote: dict | None) -> str:
    if not quote:
        return "No successful quote response yet"
    return {
        "BBO_OK": "Two-sided best bid/ask returned",
        "BOOK_OK": "Two-sided quote recovered from full order book",
        "ONE_SIDED": "Only one side has available liquidity",
        "EMPTY_BOOK": "Market exists, but its order book has no usable bids/offers",
        "BOOK_CLOSED": "Order book is closed, even if slug window looks active",
        "INVALID_BOOK": "Conflicting/crossed order-book prices",
        "STALE": "Exchange timestamp indicates stale prices",
        "API_ERROR": "A market-data request failed",
        "RATE_LIMIT": "US API returned a rate-limit response; polling paused",
        "RATE_LIMIT_COOLDOWN": "Cooling down after HTTP 429; last prices are not live",
        "BBO_EMPTY": "Best bid/ask unavailable; full-book check is scheduled less frequently",
        "BBO_PARTIAL": "Only part of the best bid/ask returned; full-book check is scheduled",
        "CACHED_OK": "Previously observed two-sided quote (cached; check age)",
        "QUOTE_EXPIRED": "Last quote is too old to present as current",
        "POLL_QUEUED": "Waiting its turn in the staggered request schedule",
    }.get(quote.get("health"), "Quote availability unknown")


# v0.8: conservative, rate-limit-aware REST polling.
# A Streamlit fragment rerun every 5 seconds must NOT cause three synchronous
# BBO+book fetches (plus settlements and catalog searches) every cycle.
# This scheduler polls *at most one* BTC market per fragment cycle, spreads
# requests across timeframes, and suppresses requests after a 429.
class QuoteScheduler:
    INTERVALS = {"5m": 12.0, "15m": 20.0, "1h": 35.0}
    MAX_AGE = {"5m": 18.0, "15m": 30.0, "1h": 48.0}
    BOOK_PROBE_INTERVAL = 90.0
    FIVE_MINUTE_BOOK_PROBE_INTERVAL = 20.0

    def __init__(self):
        self.entries: dict[str, dict] = {}
        self.cooldown_until = 0.0
        self.limit_streak = 0
        self.last_request: float = 0.0

    @staticmethod
    def _history_label(entry: dict, now: float) -> str:
        good = entry.get("good")
        good_at = entry.get("good_at")
        if not good or good_at is None:
            return "No prior verified two-sided quote"
        return (f"Last observed two-sided quote {cents(good.get('bid'))} / "
                f"{cents(good.get('ask'))}, {max(0, int(now-good_at))}s ago; not a live quote")

    def poll(self, client: Any, current: dict[str, dict | None],
             now: float) -> dict[str, dict | None]:
        # Forget finished rounds, retaining only the small active working set.
        active = {m['slug'] for m in current.values() if m is not None}
        self.entries = {slug: value for slug, value in self.entries.items() if slug in active}
        freshly_polled: str | None = None
        due: list[tuple[float, int, str, dict]] = []
        for idx, (tf, market) in enumerate(current.items()):
            if not market:
                continue
            slug = market['slug']
            entry = self.entries.setdefault(slug, {"last_polled": 0.0, "last_book_probe": -1e20,
                                                   "quote": None, "good": None, "good_at": None})
            if now - entry['last_polled'] >= self.INTERVALS[tf]:
                # Oldest overdue request goes first; brand-new round 5m takes priority.
                due.append((entry['last_polled'] + self.INTERVALS[tf], idx, tf, market))

        # A minimum 4.5-second gap also prevents manual reruns from piling up.
        if now >= self.cooldown_until and now - self.last_request >= 4.5 and due:
            _, _, tf, market = min(due)
            slug = market['slug']
            entry = self.entries[slug]
            # Recover missing five-minute BBOs sooner, without reducing 429
            # cooldowns or the shared minimum gap between market requests.
            probe_interval=self.FIVE_MINUTE_BOOK_PROBE_INTERVAL if tf=='5m' else self.BOOK_PROBE_INTERVAL
            allow_book = now - entry['last_book_probe'] >= probe_interval
            if allow_book:
                entry['last_book_probe'] = now
            self.last_request = now
            try:
                quote = fetch_market_quote(client, slug, now, allow_book_fallback=allow_book)
            except Exception as exc:
                quote = {"bid": None, "ask": None, "last": None,
                         "health": "RATE_LIMIT" if is_rate_limit_error(exc) else "API_ERROR",
                         "source": "—", "detail": type(exc).__name__}
            quote['fetched_at'] = now
            quote['fresh_poll'] = True
            entry['last_polled'] = now
            entry['quote'] = quote
            freshly_polled = slug
            if quote.get('health') == 'RATE_LIMIT':
                self.limit_streak += 1
                # Pauses apply to ALL timeframes, not just the failing market.
                self.cooldown_until = now + min(240.0, 20.0 * (2 ** min(self.limit_streak-1, 4)))
            elif quote.get('health') in ('BBO_OK', 'BOOK_OK'):
                self.limit_streak = 0
                entry['good'] = dict(quote)
                entry['good_at'] = now

        result: dict[str, dict | None] = {}
        for tf, market in current.items():
            if market is None:
                result[tf] = None
                continue
            slug = market['slug']
            entry = self.entries[slug]
            stored = entry.get('quote')
            age = now - entry['last_polled']
            if now < self.cooldown_until:
                result[tf] = {
                    "bid": None, "ask": None, "last": None,
                    "health": "RATE_LIMIT_COOLDOWN", "source": "—",
                    "detail": (f"Retry after {int(self.cooldown_until-now)+1}s. "
                               + self._history_label(entry, now)),
                    "fresh_poll": False,
                    "next_retry_seconds": int(self.cooldown_until-now)+1,
                }
                continue
            if stored is None:
                result[tf] = {"bid": None, "ask": None, "last": None,
                              "health": "POLL_QUEUED", "source": "—",
                              "detail": "Awaiting staggered initial market-data request",
                              "fresh_poll": False}
                continue
            if slug == freshly_polled:
                result[tf] = dict(stored)
                continue
            if stored.get('health') in ('BBO_OK', 'BOOK_OK') and age <= self.MAX_AGE[tf]:
                result[tf] = {**stored, "health": "CACHED_OK", "source": "CACHED",
                              "fresh_poll": False, "sample_age_seconds": age,
                              "detail": f"Last observed {int(age)}s ago; exchange may have moved since polling"}
            elif age <= self.MAX_AGE[tf]:
                result[tf] = {**stored, "fresh_poll": False}
            else:
                result[tf] = {
                    "bid": None, "ask": None, "last": None,
                    "health": "QUOTE_EXPIRED", "source": "—", "fresh_poll": False,
                    "detail": self._history_label(entry, now),
                }
        return result
