"""Durable, market-price-based BTC call *observations* (never orders or AI forecasts).

SQLite is the source of truth, not Streamlit's session_state. A saved call never
turns into WAIT because market discovery, REST/WebSocket or UI refresh fails.
A new market round has its own call; the latest prior call remains visible as
ARCHIVED, never masquerades as the new round's prediction.

YES=UP/NO=DOWN mapping is an explicit user verification, not inferred here.
Unverified price observations are retained but must be displayed as tentative.
"""
from __future__ import annotations
from pathlib import Path
import sqlite3
from functools import lru_cache
import time
from typing import Any

DURATIONS = {'5m': 300, '15m': 900, '1h': 3600}
FRESH_HEALTH = frozenset({'STREAM_OK', 'BOOK_OK', 'BBO_OK'})
STRENGTH_TIERS = ('CALLED','LOCKED')


def _db(db: Path):
    con = sqlite3.connect(db, timeout=12)
    con.execute('PRAGMA busy_timeout=12000')
    return con


@lru_cache(maxsize=16)
def init_journal(db: Path):
    db.parent.mkdir(parents=True, exist_ok=True)
    with _db(db) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS price_call_journal (
            market_slug TEXT PRIMARY KEY, timeframe TEXT NOT NULL,
            round_start REAL NOT NULL, round_end REAL NOT NULL,
            first_side TEXT NOT NULL, first_tier TEXT NOT NULL,
            first_at REAL NOT NULL, first_strength REAL NOT NULL,
            current_side TEXT NOT NULL, current_tier TEXT NOT NULL,
            current_at REAL NOT NULL, current_strength REAL NOT NULL,
            last_quote_at REAL NOT NULL, mapping_verified INTEGER NOT NULL DEFAULT 0,
            switches INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'MARKET_PRICE_ONLY'
        )''')
        con.execute('CREATE INDEX IF NOT EXISTS ix_price_call_tf ON price_call_journal(timeframe,round_end DESC)')
        con.execute('''CREATE TABLE IF NOT EXISTS price_call_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_slug TEXT NOT NULL, observed_at REAL NOT NULL,
            event_type TEXT NOT NULL, new_side TEXT NOT NULL,
            new_tier TEXT NOT NULL, market_strength REAL NOT NULL
        )''')
        con.execute('''CREATE TABLE IF NOT EXISTS price_call_candidates (
            market_slug TEXT PRIMARY KEY,
            side TEXT NOT NULL, first_quote REAL NOT NULL,
            last_quote REAL NOT NULL, first_seen_at REAL NOT NULL
        )''')


def _row_to_dict(row):
    return dict(zip(('market_slug','timeframe','round_start','round_end','first_side',
        'first_tier','first_at','first_strength','current_side','current_tier',
        'current_at','current_strength','last_quote_at','mapping_verified',
        'switches','source'), row)) if row else None


def _read(con: sqlite3.Connection, slug: str):
    return _row_to_dict(con.execute('SELECT * FROM price_call_journal WHERE market_slug=?',(slug,)).fetchone())


def journal_for(db: Path, slug: str | None):
    if not slug or not db.exists(): return None
    try:
        with _db(db) as con: return _read(con,slug)
    except sqlite3.Error:
        return None


def latest_for(db: Path, timeframe: str):
    if timeframe not in DURATIONS or not db.exists(): return None
    try:
        with _db(db) as con:
            r=con.execute('SELECT * FROM price_call_journal WHERE timeframe=? ORDER BY round_start DESC, first_at DESC LIMIT 1',(timeframe,)).fetchone()
            return _row_to_dict(r)
    except sqlite3.Error: return None


def list_journal(db: Path, limit=60):
    if not db.exists(): return []
    try:
        with _db(db) as con:
            rows=con.execute('SELECT * FROM price_call_journal ORDER BY first_at DESC LIMIT ?',
                             (max(1,min(int(limit),500)),)).fetchall()
        return [_row_to_dict(r) for r in rows]
    except sqlite3.Error: return []


def observe(db: Path, market: dict|None, quote: dict|None, signal: dict, now: float,
            *, min_quote_gap=4.0, max_candidate_age=45.0) -> str:
    """Persist first CALLED/LOCKED tier, changes only after two separate opposite ticks.

    Bad/old/missing market quotes NEVER erase a call. Only a new confirmed
    fresh observation can update it. HOLDING and WAIT never overwrite it.
    """
    if not market or not quote or signal.get('status') not in STRENGTH_TIERS:
        return 'NO_QUALIFIED_SIGNAL'
    side=signal.get('side')
    tf=market.get('timeframe'); slug=market.get('slug')
    if side not in ('UP','DOWN') or tf not in DURATIONS or not isinstance(slug,str) or not slug:
        return 'BAD_MARKET'
    if quote.get('health') not in FRESH_HEALTH: return 'STALE_FEED'
    qt=quote.get('fetched_at')
    if not isinstance(qt,(int,float)) or not 0 <= now-qt <= 20: return 'STALE_FEED'
    start=market.get('start'); end=market.get('end')
    if not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or not start <= now < end:
        return 'WRONG_ROUND_OR_CUTOFF'
    strength=signal.get('strength')
    if not isinstance(strength,(int,float)) or not .7 <= strength <= 1: return 'BAD_STRENGTH'
    init_journal(db)
    with _db(db) as con:
        con.execute('BEGIN IMMEDIATE')
        saved=_read(con,slug)
        if not saved:
            con.execute('''INSERT INTO price_call_journal
               (market_slug,timeframe,round_start,round_end,first_side,first_tier,
               first_at,first_strength,current_side,current_tier,current_at,
               current_strength,last_quote_at,mapping_verified)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
               (slug,tf,start,end,side,signal['status'],now,strength,side,
                signal['status'],now,strength,qt,int(bool(signal.get('mapping_verified')))))
            con.execute('INSERT INTO price_call_events(market_slug,observed_at,event_type,new_side,new_tier,market_strength) VALUES (?,?,?,?,?,?)',
                        (slug,now,'FIRST',side,signal['status'],strength))
            return 'FIRST_SAVED'
        # Never accept later data for a slug whose timestamp bounds differ.
        if saved['timeframe']!=tf or abs(saved['round_start']-start)>1 or abs(saved['round_end']-end)>1:
            return 'ROUND_MISMATCH'
        if qt <= saved['last_quote_at'] + .001:
            return 'REPEATED_TICK'
        con.execute('UPDATE price_call_journal SET last_quote_at=?, mapping_verified=MAX(mapping_verified,?) WHERE market_slug=?',
                    (qt,int(bool(signal.get('mapping_verified'))),slug))
        if side == saved['current_side']:
            con.execute('DELETE FROM price_call_candidates WHERE market_slug=?',(slug,))
            if saved['current_tier'] != 'LOCKED' and signal['status']=='LOCKED':
                con.execute('''UPDATE price_call_journal SET current_tier='LOCKED',current_at=?,current_strength=? WHERE market_slug=?''',
                            (now,strength,slug))
                con.execute('INSERT INTO price_call_events(market_slug,observed_at,event_type,new_side,new_tier,market_strength) VALUES (?,?,?,?,?,?)',
                            (slug,now,'UPGRADE',side,'LOCKED',strength))
                return 'UPGRADED'
            return 'UNCHANGED'
        if saved['current_tier']=='LOCKED' and signal['status']!='LOCKED':
            con.execute('DELETE FROM price_call_candidates WHERE market_slug=?',(slug,))
            return 'LOCKED_REQUIRES_LOCKED_REVERSAL'
        candidate=con.execute('SELECT side,first_quote,last_quote,first_seen_at FROM price_call_candidates WHERE market_slug=?',(slug,)).fetchone()
        if (candidate is None or candidate[0]!=side or now-candidate[3] > max_candidate_age
                or qt <= candidate[2]):
            con.execute('''INSERT INTO price_call_candidates(market_slug,side,first_quote,last_quote,first_seen_at)
                     VALUES(?,?,?,?,?) ON CONFLICT(market_slug) DO UPDATE SET
                     side=excluded.side,first_quote=excluded.first_quote,
                     last_quote=excluded.last_quote,first_seen_at=excluded.first_seen_at''',
                        (slug,side,qt,qt,now))
            return 'REVERSAL_PENDING'
        if qt-candidate[1] < min_quote_gap:
            con.execute('UPDATE price_call_candidates SET last_quote=? WHERE market_slug=?',(qt,slug))
            return 'REVERSAL_PENDING'
        con.execute('DELETE FROM price_call_candidates WHERE market_slug=?',(slug,))
        con.execute('''UPDATE price_call_journal SET current_side=?,current_tier=?,current_at=?,current_strength=?,switches=switches+1 WHERE market_slug=?''',
                    (side,signal['status'],now,strength,slug))
        con.execute('INSERT INTO price_call_events(market_slug,observed_at,event_type,new_side,new_tier,market_strength) VALUES (?,?,?,?,?,?)',
                    (slug,now,'SWITCH',side,signal['status'],strength))
        return 'SWITCHED'


def display_choice(db: Path, timeframe: str, live_market: dict|None, now: float):
    """(market, saved, archive, note). NEVER repurpose a prior round as LIVE."""
    saved=journal_for(db, live_market.get('slug')) if live_market else None
    latest=latest_for(db,timeframe)
    if saved:
        return live_market, saved, None, ''
    if latest and latest['round_start'] <= now < latest['round_end']:
        # A catalog response may briefly disagree with the still-open saved
        # round. Show the historical saved pick but do not claim live pricing.
        m={'slug':latest['market_slug'],'timeframe':timeframe,
           'start':latest['round_start'],'end':latest['round_end'],
           'active':True,'display_only':True}
        return m,latest,None,'LIVE MARKET ID NOT CONFIRMED · SAVED CALL'
    # Even after a real rollover, keep the old call in a separate ARCHIVE panel,
    # never under the heading CURRENT CALL for a different/new round.
    return live_market,None,latest,''


def import_v15_legacy(db: Path):
    """Idempotent migration: preserve existing first and current paper calls.

    New journal is *independent* from the original tables. No destructive schema
    changes. If older tables aren't present, exit quietly.
    """
    init_journal(db)
    from us_monitor import slug_start_ts
    from direction_signals import current_research_call
    with _db(db) as con:
        old=con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='research_paper_calls'").fetchone()
        if not old: return 0
        old_rows=con.execute('SELECT market_slug,timeframe,recorded_at,direction,tier,market_strength FROM research_paper_calls').fetchall()
    count=0
    for slug,tf,recorded_at,side,tier,strength in old_rows:
        if tf not in DURATIONS or side not in ('UP','DOWN') or tier not in STRENGTH_TIERS: continue
        start=slug_start_ts(slug)
        if start is None: continue
        existing=journal_for(db,slug)
        if existing: continue
        current=current_research_call(db,slug)
        cur_side=(current or {}).get('current_direction',side)
        cur_tier=(current or {}).get('current_tier',tier)
        cur_at=(current or {}).get('current_at',recorded_at)
        cur_strength=(current or {}).get('current_strength',strength)
        with _db(db) as con:
            cur=con.execute('''INSERT OR IGNORE INTO price_call_journal
                (market_slug,timeframe,round_start,round_end,first_side,first_tier,
                first_at,first_strength,current_side,current_tier,current_at,current_strength,
                last_quote_at,mapping_verified,switches,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (slug,tf,start,start+DURATIONS[tf],side,tier,recorded_at,strength,
                 cur_side,cur_tier,cur_at,cur_strength,cur_at,1,
                 int((current or {}).get('switches',0)),'LEGACY_RESEARCH_PAPER'))
            count+=cur.rowcount
    return count


def journal_events(db: Path, limit: int=50):
    if not db.exists(): return []
    try:
        with _db(db) as con:
            rows=con.execute('''SELECT id,market_slug,observed_at,event_type,new_side,new_tier,market_strength
                       FROM price_call_events ORDER BY id DESC LIMIT ?''',
                       (max(1,min(int(limit),500)),)).fetchall()
        return [dict(zip(('id','market_slug','observed_at','event_type','new_side','new_tier','market_strength'),r)) for r in rows]
    except sqlite3.Error: return []
