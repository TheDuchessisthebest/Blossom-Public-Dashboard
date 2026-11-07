"""Experimental, READ-ONLY UP/DOWN observation and paper-call ledger.

NOT an AI forecast. Confidence tiers are thresholds on MARKET CONTRACT PRICES,
not independently calibrated chances. NO exchange orders or assumed fills.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

TIERS = ((0.90, 'LOCKED'), (0.70, 'CALLED'), (0.55, 'HOLDING'))
LIVE_HEALTH = frozenset({'BBO_OK', 'BOOK_OK', 'STREAM_OK'})


def evaluate_direction(market: dict | None, quote: dict | None, now: float,
                       *, mapping_verified: bool = False,
                       max_spread: float = 0.05, min_call_seconds: float = 0.0,
                       max_quote_age: float = 20.0) -> dict[str, Any]:
    """Convert verified, fresh YES order-book dominance to a provisional UP/DOWN label.

    IMPORTANT: YES=UP and NO=DOWN is an assumption unless the user verified
    THIS series' official market rules. Without verification, no paper record.
    """
    result = {
        'status': 'WAIT', 'side': None, 'strength': None, 'mid': None,
        'reason': 'No current usable price', 'record_eligible': False,
        'mapping_verified': mapping_verified, 'price_kind': None,
        'paper_price': None,
    }
    if not market or not isinstance(market.get('slug'), str):
        return {**result, 'reason': 'No verified current BTC contract'}
    start, end = market.get('start'), market.get('end')
    if start is None or end is None or market.get('active') is False or not (start <= now < end):
        return {**result, 'reason': 'No open market within the estimated contract window'}
    if quote is None or quote.get('health') not in LIVE_HEALTH:
        return {**result, 'reason': 'Waiting for a fresh two-sided order book'}
    fetched_at = quote.get('fetched_at')
    if not isinstance(fetched_at, (int, float)) or now-fetched_at > max_quote_age or fetched_at > now + 3:
        return {**result, 'reason': 'Quote timestamp missing, stale, or in the future'}
    bid, ask = quote.get('bid'), quote.get('ask')
    if not isinstance(bid, (float, int)) or not isinstance(ask, (float, int)) or not (0 < bid <= ask < 1):
        return {**result, 'reason': 'Order book is empty, one-sided, or invalid'}
    spread = ask - bid
    if spread > max_spread + 1e-9:
        return {**result, 'reason': f'Spread {spread*100:.1f}¢ exceeds {max_spread*100:.1f}¢ limit'}
    mid = (bid+ask)/2
    strength = max(mid, 1-mid)
    side = 'UP' if mid >= 0.5 else 'DOWN'  # Assumption is disclosed until confirmed.
    tier = next((status for cutoff, status in TIERS if strength >= cutoff), 'WAIT')
    if tier == 'WAIT':
        return {**result, 'mid': mid, 'strength': strength, 'side': side,
                'reason': 'Market price is too close to 50¢ for a directional call'}
    if not mapping_verified:
        reason = 'Provisional: confirm YES=UP / NO=DOWN against official contract rules'
    elif tier == 'LOCKED':
        reason = 'Strong market consensus; LOCKED is a high market-price tier, NOT certainty'
    elif tier == 'CALLED':
        reason = 'Market-priced directional call, NOT an independently trained forecast'
    else:
        reason = 'Moderate market-priced lean; watch for a stronger move'
    remaining = end-now
    if remaining < min_call_seconds:
        reason += f'; {int(remaining)}s remaining is inside paper entry cutoff'
    # An indicative DOWN price derived as 1-YES bid is not an executable NO quote.
    indicative = ask if side == 'UP' else 1-bid
    price_kind = 'observed_yes_ask_not_filled' if side == 'UP' else 'derived_no_price_not_executable'
    eligible = bool(mapping_verified and tier in ('CALLED', 'LOCKED') and remaining >= min_call_seconds)
    return {**result, 'status': tier, 'side': side, 'mid': mid, 'strength': strength,
            'reason': reason, 'record_eligible': eligible,
            'price_kind': price_kind, 'paper_price': indicative}


def init_paper_calls(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS research_paper_calls (
            market_slug TEXT PRIMARY KEY,
            timeframe TEXT NOT NULL,
            recorded_at REAL NOT NULL,
            direction TEXT NOT NULL,
            tier TEXT NOT NULL,
            yes_bid REAL NOT NULL,
            yes_ask REAL NOT NULL,
            market_strength REAL NOT NULL,
            indicative_price REAL NOT NULL,
            price_kind TEXT NOT NULL,
            note TEXT NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_paper_calls_recent ON research_paper_calls(recorded_at DESC)')
        conn.execute('''CREATE TABLE IF NOT EXISTS research_call_changes (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_slug TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            changed_at REAL NOT NULL,
            quote_timestamp REAL NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('SWITCH','UPGRADE')),
            direction TEXT NOT NULL CHECK(direction IN ('UP','DOWN')),
            tier TEXT NOT NULL CHECK(tier IN ('CALLED','LOCKED')),
            market_strength REAL NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS ix_research_change_round ON research_call_changes(market_slug,event_id DESC)')
        conn.execute("""CREATE TABLE IF NOT EXISTS research_locked_calls (
            market_slug TEXT PRIMARY KEY,
            locked_at REAL NOT NULL,
            timeframe TEXT NOT NULL,
            direction TEXT NOT NULL,
            strength REAL NOT NULL
        )""")


def record_research_paper_call(path: Path, market: dict | None, quote: dict | None,
                               signal: dict, now: float) -> bool:
    """Record ONE hypothetical entry reference per contract, never an actual fill.

    A price observation has no guaranteed matching liquidity or executable price.
    This ledger contains no trading API calls, wallet keys, or true position data.
    """
    if not market or not quote or not signal.get('record_eligible'):
        return False
    if signal.get('status') not in ('CALLED', 'LOCKED'):
        return False
    if quote.get('health') not in LIVE_HEALTH:
        return False
    if now - quote.get('fetched_at', -1e10) > 20:
        return False
    init_paper_calls(path)
    with sqlite3.connect(path, timeout=10) as conn:
        already_locked = conn.execute('SELECT direction FROM research_locked_calls WHERE market_slug=?',
                                      (market['slug'],)).fetchone()
        if already_locked and already_locked[0] != signal['side']:
            return False  # A previously locked direction can never be overwritten.
        result = conn.execute('''INSERT OR IGNORE INTO research_paper_calls
             (market_slug, timeframe, recorded_at, direction, tier, yes_bid, yes_ask,
              market_strength, indicative_price, price_kind, note)
             VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (market['slug'], market['timeframe'], now, signal['side'], signal['status'],
             float(quote['bid']), float(quote['ask']), float(signal['strength']),
             float(signal['paper_price']), signal['price_kind'],
             'SIMULATED RESEARCH CALL ONLY. No order, no fill, no proven model edge.'))
        return result.rowcount == 1


def paper_calls_for(path: Path, limit: int = 30) -> list[dict]:
    if not path.exists():
        return []
    try:
        with sqlite3.connect(path, timeout=10) as conn:
            rows = conn.execute('''SELECT market_slug,timeframe,recorded_at,direction,tier,
               yes_bid,yes_ask,market_strength,indicative_price,price_kind,note
               FROM research_paper_calls ORDER BY recorded_at DESC LIMIT ?''',
               (max(1, min(int(limit), 1000)),)).fetchall()
    except sqlite3.OperationalError:
        return []
    keys = ('market_slug','timeframe','recorded_at','direction','tier','yes_bid',
            'yes_ask','market_strength','indicative_price','price_kind','note')
    return [dict(zip(keys,row)) for row in rows]



def lock_research_call(path: Path, market: dict | None, signal: dict, now: float) -> bool:
    """Freeze a research observation per round at >=90¢, not a guarantee."""
    if not market or signal.get('status') != 'LOCKED' or not signal.get('mapping_verified'):
        return False
    if not (market.get('start', now+1) <= now < market.get('end', now)):
        return False
    if market['end'] - now < 15:
        return False
    init_paper_calls(path)
    with sqlite3.connect(path, timeout=10) as conn:
        first = conn.execute('SELECT direction FROM research_paper_calls WHERE market_slug=?',
                             (market['slug'],)).fetchone()
        if first is not None and first[0] != signal['side']:
            return False  # Never lock the opposite side after an earlier CALL.
        cur = conn.execute("""INSERT OR IGNORE INTO research_locked_calls
            (market_slug, locked_at, timeframe, direction, strength)
            VALUES (?,?,?,?,?)""",
            (market['slug'], now, market['timeframe'], signal['side'], signal['strength']))
        return cur.rowcount == 1


def locked_for(path: Path, slug: str) -> dict | None:
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path, timeout=10) as conn:
            row = conn.execute("""SELECT locked_at,direction,strength
                FROM research_locked_calls WHERE market_slug=?""", (slug,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(locked_at=row[0], direction=row[1], strength=row[2]) if row else None


def paper_call_for(path: Path, slug: str) -> dict | None:
    """First recorded call for this exact market slug; permanent across Streamlit reruns."""
    if not path.exists() or not slug:
        return None
    columns = ('market_slug','timeframe','recorded_at','direction','tier','yes_bid',
               'yes_ask','market_strength','indicative_price','price_kind','note')
    try:
        with sqlite3.connect(path, timeout=10) as conn:
            row = conn.execute("""SELECT market_slug,timeframe,recorded_at,direction,tier,
                yes_bid,yes_ask,market_strength,indicative_price,price_kind,note
                FROM research_paper_calls WHERE market_slug=?""", (slug,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(zip(columns, row)) if row else None


def persistent_call_state(signal: dict, first_call: dict | None,
                          locked: dict | None) -> dict[str, Any]:
    """Never change a recorded CALLED/LOCKED direction within the same round.

    Live quotes may continue to move; they cannot alter the frozen research call.
    Only a new contract slug allows a new call. A lock may upgrade the tier
    ONLY if the lock's direction matches the first recorded call.
    """
    if first_call:
        side = first_call['direction']
        matching_lock = locked if locked and locked.get('direction') == side else None
        status = 'LOCKED' if matching_lock or first_call['tier'] == 'LOCKED' else 'CALLED'
        strength = (matching_lock['strength'] if matching_lock else
                    first_call['market_strength'])
        return {'status': status, 'side': side, 'strength': strength,
                'persisted': True, 'called_at': first_call['recorded_at'],
                'locked_at': matching_lock['locked_at'] if matching_lock else None,
                'market_status': signal.get('status'),
                'market_side': signal.get('side')}
    if locked:
        return {'status': 'LOCKED', 'side': locked['direction'],
                'strength': locked['strength'], 'persisted': True,
                'called_at': locked['locked_at'], 'locked_at': locked['locked_at'],
                'market_status': signal.get('status'), 'market_side': signal.get('side')}
    return {'status': signal.get('status', 'WAIT'), 'side': signal.get('side'),
            'strength': signal.get('strength'), 'persisted': False,
            'called_at': None, 'locked_at': None,
            'market_status': signal.get('status'), 'market_side': signal.get('side')}


# v1.4 — The ORIGINAL record remains immutable, while CURRENT can switch.
# Price-tier labels are observations of the market, NOT calibrated AI confidence.
# All mutations are confined to the experimental research ledger. No orders.

def call_changes_for(path: Path, slug: str | None = None, limit: int = 100) -> list[dict]:
    """Chronological research SWITCH/UPGRADE events, newest first."""
    if not path.exists():
        return []
    columns = ('event_id','market_slug','timeframe','changed_at','quote_timestamp',
               'event_type','direction','tier','market_strength')
    try:
        with sqlite3.connect(path, timeout=10) as conn:
            if slug is None:
                rows = conn.execute('''SELECT event_id,market_slug,timeframe,changed_at,
                        quote_timestamp,event_type,direction,tier,market_strength
                        FROM research_call_changes ORDER BY event_id DESC LIMIT ?''',
                        (max(1, min(500, int(limit))),)).fetchall()
            else:
                rows = conn.execute('''SELECT event_id,market_slug,timeframe,changed_at,
                        quote_timestamp,event_type,direction,tier,market_strength
                        FROM research_call_changes WHERE market_slug=?
                        ORDER BY event_id DESC LIMIT ?''',
                        (slug, max(1, min(500, int(limit))))).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(zip(columns, row)) for row in rows]


def current_research_call(path: Path, slug: str) -> dict | None:
    """Get current recorded CALL and immutable first call for the same contract.

    The earliest call always exists independently of any newer switches.
    """
    first = paper_call_for(path, slug)
    if not first:
        return None
    latest = call_changes_for(path, slug, 500)
    last = latest[0] if latest else None
    # Support already-written v1.3 LOCKED state until first v1.4 switch.
    legacy_lock = locked_for(path, slug) if not latest else None
    legacy_matches = legacy_lock and legacy_lock['direction'] == first['direction']
    active_side = last['direction'] if last else first['direction']
    active_tier = last['tier'] if last else ('LOCKED' if legacy_matches else first['tier'])
    active_at = last['changed_at'] if last else (legacy_lock['locked_at'] if legacy_matches else first['recorded_at'])
    first_tier = first['tier']
    return {
        'market_slug': slug,
        'original_direction': first['direction'],
        'original_tier': first_tier,
        'original_at': first['recorded_at'],
        'current_direction': active_side,
        'current_tier': active_tier,
        'current_at': active_at,
        'current_strength': last['market_strength'] if last else
                            (legacy_lock['strength'] if legacy_matches else first['market_strength']),
        'switches': sum(1 for change in latest if change['event_type'] == 'SWITCH'),
        'last_event': last['event_type'] if last else 'ORIGINAL',
    }


def record_research_signal_update(path: Path, market: dict | None, quote: dict | None,
                                  signal: dict, now: float) -> bool:
    """Switch current side on a NEW, qualified opposite market quote.

    Current CALLED may switch on opposite CALLED/LOCKED (>=70c). Current
    LOCKED only switches on opposite LOCKED (>=90c), to avoid chattering.
    The first-ever research_paper_calls row is NEVER updated or deleted.
    The change is a market-price signal; it is not an order or a model forecast.
    """
    if not market or not quote or not signal.get('record_eligible'):
        return False
    if signal.get('status') not in ('CALLED', 'LOCKED') or signal.get('side') not in ('UP','DOWN'):
        return False
    if quote.get('health') not in LIVE_HEALTH:
        return False
    qt = quote.get('fetched_at')
    if not isinstance(qt, (int, float)) or qt > now + 3 or now - qt > 20:
        return False
    if not (market.get('start', float('inf')) <= now < market.get('end', -1)):
        return False
    init_paper_calls(path)
    with sqlite3.connect(path, timeout=10) as conn:
        # Each check and insert is atomic, even across concurrent fragment refreshes.
        conn.execute('BEGIN IMMEDIATE')
        first = conn.execute('''SELECT direction,tier,recorded_at,market_strength
                              FROM research_paper_calls WHERE market_slug=?''',
                              (market['slug'],)).fetchone()
        if not first:
            return False
        last = conn.execute('''SELECT direction,tier,quote_timestamp,changed_at
                              FROM research_call_changes WHERE market_slug=?
                              ORDER BY event_id DESC LIMIT 1''', (market['slug'],)).fetchone()
        legacy = None if last else conn.execute('''SELECT direction,locked_at FROM research_locked_calls
                      WHERE market_slug=?''', (market['slug'],)).fetchone()
        current_direction = last[0] if last else first[0]
        current_tier = last[1] if last else ('LOCKED' if legacy and legacy[0] == first[0] else first[1])
        # A previously-used quote cannot cause a new change later. Also block
        # out-of-order snapshots arriving after fresher market observations.
        previously_seen = last[2] if last else first[2]
        if qt <= previously_seen + 1e-3:
            return False
        new_side, new_tier = signal['side'], signal['status']
        if new_side != current_direction:
            if current_tier == 'LOCKED' and new_tier != 'LOCKED':
                return False
            event = 'SWITCH'
        elif current_tier != 'LOCKED' and new_tier == 'LOCKED':
            event = 'UPGRADE'
        else:
            return False
        conn.execute('''INSERT INTO research_call_changes
                      (market_slug,timeframe,changed_at,quote_timestamp,event_type,
                       direction,tier,market_strength) VALUES (?,?,?,?,?,?,?,?)''',
                     (market['slug'], market['timeframe'], now, qt, event,
                      new_side, new_tier, float(signal['strength'])))
        return True


def change_aware_call_state(signal: dict, saved: dict | None) -> dict[str, Any]:
    """Stable first pick + most-recent recorded pick, regardless of live feed outages."""
    if saved:
        return {'status': saved['current_tier'], 'side': saved['current_direction'],
                'strength': saved['current_strength'], 'persisted': True,
                'first_side': saved['original_direction'], 'first_status': saved['original_tier'],
                'first_at': saved['original_at'], 'current_at': saved['current_at'],
                'switches': saved.get('switches', 0), 'last_event': saved.get('last_event', 'ORIGINAL'),
                'market_status': signal.get('status'), 'market_side': signal.get('side')}
    return {'status': signal.get('status', 'WAIT'), 'side': signal.get('side'),
            'strength': signal.get('strength'), 'persisted': False,
            'first_side': None, 'first_status': None, 'first_at': None,
            'current_at': None, 'switches': 0, 'last_event': None,
            'market_status': signal.get('status'), 'market_side': signal.get('side')}
