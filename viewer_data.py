"""Blossom Bot PUBLIC viewer data layer.

READ-ONLY by construction: only opens SQLite via URI mode=ro plus
PRAGMA query_only=ON. Never imports the private dashboard or SDK, opens
credentials, sends orders, calls external APIs, or mutates research data.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
import json
import re
import sqlite3
import time

DURATIONS = {'5m': 300, '15m': 900, '1h': 3600}
PATTERN = re.compile(r'^cpc-btc-updown-(5m|15m|1h)-(20\d\d)-(\d\d)-(\d\d)-(\d\d)(\d\d)z$')


@contextmanager
def reader(db: Path):
    """Returns an SQLite connection that cannot write to the DB."""
    if not db.is_file():
        yield None
        return
    # as_uri percent-encodes spaces in folder names such as C:\\Bit coin.
    uri = db.resolve().as_uri() + '?mode=ro'
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('PRAGMA busy_timeout=2000')
        yield conn
    finally:
        conn.close()


def safe_query(conn, sql: str, args: tuple=()) -> list[dict]:
    if conn is None:
        return []
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    except sqlite3.OperationalError as exc:
        if 'no such table' in str(exc).lower() or 'no such column' in str(exc).lower():
            return []  # Older versions of the project have fewer tables/columns.
        raise


def parsed_round(slug: str | None):
    if not isinstance(slug, str):
        return None
    match = PATTERN.fullmatch(slug)
    if not match:
        return None
    tf, yyyy, mm, dd, hh, minute = match.groups()
    try:
        start = int(datetime(int(yyyy), int(mm), int(dd), int(hh), int(minute), tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None
    if start % DURATIONS[tf] != 0:
        return None
    return {'slug': slug, 'timeframe': tf, 'start': start, 'end': start+DURATIONS[tf]}


def _last_call(con, tf, market):
    # A saved call is shown as LIVE only if it matches the IDENTIFIED round.
    # The previous round is never silently presented as a current prediction.
    slug = market['slug'] if market else None
    recent = safe_query(con, '''SELECT market_slug, timeframe, round_start, round_end,
                 first_side, first_tier, first_strength, first_at,
                 current_side, current_tier, current_strength, current_at,
                 switches FROM price_call_journal
                 WHERE timeframe=? ORDER BY round_end DESC LIMIT 1''', (tf,))
    if not recent:
        return None
    r=recent[0]
    if r['first_side'] not in ('UP','DOWN') or r['current_side'] not in ('UP','DOWN'):
        return None
    r['is_current']=bool(slug and r['market_slug']==slug)
    return r


def _last_ai(con, market):
    recent = safe_query(con, '''SELECT slug, round_start, round_end,
         original_side, original_probability, original_at,
         current_side, current_probability, current_at, switches, model_validation
         FROM ai5m_rounds ORDER BY round_end DESC LIMIT 1''')
    if not recent:
        return None
    r=recent[0]
    if r['original_side'] not in ('UP','DOWN') or r['current_side'] not in ('UP','DOWN'):
        return None
    r['is_current']=bool(market and r['slug']==market['slug'])
    return r


def _quote(con, market, now):
    if not market:
        return None
    rows = safe_query(con, '''SELECT recorded_at, bid, ask, last_trade
            FROM quotes WHERE market_slug=? AND recorded_at<=?
            ORDER BY recorded_at DESC LIMIT 1''', (market['slug'], now+3))
    if not rows:
        return None
    q = rows[0]
    age=max(0,now-float(q['recorded_at']))
    bid,ask=q['bid'],q['ask']
    valid=all(isinstance(v,(float,int)) and isfinite(v) and 0<v<1 for v in (bid,ask)) and bid<=ask
    q['age']=age
    q['fresh']=valid and age<=25
    q['valid']=valid
    q['status']='FRESH' if q['fresh'] else ('STALE' if valid else 'INCOMPLETE')
    return q


def _reference(con, market, now):
    if not market:
        return {'status':'NO_MARKET'}
    start = market['start']
    opening = safe_query(con, '''SELECT timestamp,close FROM btci_ticks
        WHERE timestamp>=? AND timestamp<? ORDER BY timestamp ASC''', (start-60,start))
    if len(opening)!=60 or any(int(r['timestamp'])!=start-60+i for i,r in enumerate(opening)):
        return {'status':'NO_OPENING_REFERENCE'}
    prices=[float(r['close']) for r in opening]
    if not all(isfinite(p) and p>0 for p in prices):
        return {'status':'NO_OPENING_REFERENCE'}
    strike=sum(prices)/60
    latest=safe_query(con, '''SELECT timestamp,close FROM btci_ticks
        WHERE timestamp>=? AND timestamp<=? ORDER BY timestamp DESC LIMIT 1''', (start, int(now)-1))
    if not latest:
        return {'status':'NO_CURRENT_REFERENCE','strike':strike}
    px=float(latest[0]['close'])
    ts=int(latest[0]['timestamp'])
    if not isfinite(px) or px<=0:
        return {'status':'NO_CURRENT_REFERENCE'}
    return {'status':'FRESH' if now-ts <= 40 else 'STALE', 'strike':strike, 'price':px,
        'delta':px-strike, 'age':round(max(0,now-ts),1),'timestamp':ts}


def read_snapshot(db: Path, now: float | None=None) -> dict:
    """Public-safe snapshot. No credentials, raw DB paths, or write operations."""
    now=time.time() if now is None else now
    result={'time':now, 'markets':{}, 'counts':{}, 'ai':None, 'db_available':db.is_file()}
    with reader(db) as con:
        # Use saved local observations; never invent a current contract from wall clock.
        observed=safe_query(con, '''SELECT market_slug, MAX(recorded_at) AS seen
            FROM quotes WHERE recorded_at>=? AND recorded_at<=?
            GROUP BY market_slug ORDER BY seen DESC LIMIT 150''', (now-3700,now+3))
        candidates=[]
        for row in observed:
            m=parsed_round(row['market_slug'])
            if m and m['start']<=now<m['end']:
                candidates.append(m)
        latest_index=safe_query(con, 'SELECT MAX(timestamp) AS last_seen FROM btci_ticks')
        index_seen=latest_index[0].get('last_seen') if latest_index else None
        for tf in DURATIONS:
            matching=[m for m in candidates if m['timeframe']==tf]
            market=max(matching,key=lambda m:m['start']) if matching else None
            # A last observed time is useful even if the current round has NO live quote.
            # It is NOT treated as a tradable quote or as proof that this round is active.
            recent_quote=safe_query(con, '''SELECT MAX(recorded_at) AS last_seen FROM quotes
                WHERE market_slug LIKE ? AND recorded_at<=?''',
                (f'cpc-btc-updown-{tf}-%', now+3))
            quote_seen=recent_quote[0].get('last_seen') if recent_quote else None
            ref=_reference(con,market,now)
            if isinstance(index_seen,(int,float)) and isfinite(index_seen):
                ref['source_timestamp']=float(index_seen)
                ref['source_age']=max(0,now-float(index_seen))
            result['markets'][tf]={'round':market,'quote':_quote(con,market,now),
                'last_quote_seen':quote_seen,
                'call':_last_call(con,tf,market),'reference':ref}
            feed=safe_query(con,'SELECT checked_at,status FROM public_feed_health WHERE timeframe=?',(tf,))
            result['markets'][tf]['feed_health']=feed[0] if feed else None
        result['ai']=_last_ai(con,result['markets']['5m']['round'])
        rows=safe_query(con, 'SELECT timeframe, COUNT(*) AS n FROM official_outcomes GROUP BY timeframe')
        result['counts']={r['timeframe']:r['n'] for r in rows if r.get('timeframe') in DURATIONS}
    return result


def public_training_status(models_dir: Path):
    p=models_dir/'training_status.json'
    if not p.is_file() or p.stat().st_size > 100_000:
        return {}
    try:
        raw=json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    output={}
    for tf in DURATIONS:
        entry=raw.get(tf) if isinstance(raw,dict) else None
        if not isinstance(entry,dict):
            continue
        output[tf]={k:entry[k] for k in ('status','rounds_with_features', 'holdout_brier','market_brier', 'holdout_samples') if k in entry}
    return output


def directional_model_probability(side: str, p_up: float | None) -> float | None:
    """The AI ledger persists P(UP). Convert it to P(displayed direction).

    E.g. a stored 0.36 P(UP) shown beside DOWN must display 64%, not 36%.
    This is a model estimate and is NOT a validated success rate.
    """
    if side not in ('UP','DOWN') or not isinstance(p_up,(int,float)) or not isfinite(p_up) or not 0 <= p_up <= 1:
        return None
    return 100 * (float(p_up) if side=='UP' else 1.0-float(p_up))


def read_quote_timeline(db: Path, market_slug: str | None, now: float | None = None,
                        limit: int = 180) -> list[dict]:
    """Public read-only historical quote chart for an exact known contract.

    Never interpolates missing prices or replaces prices with settlement outcomes.
    """
    if not isinstance(market_slug, str) or parsed_round(market_slug) is None:
        return []
    now = time.time() if now is None else float(now)
    limit = max(1, min(500, int(limit)))
    with reader(db) as con:
        rows = safe_query(con, '''SELECT recorded_at,bid,ask,last_trade FROM quotes
            WHERE market_slug=? AND recorded_at<=?
            ORDER BY recorded_at DESC LIMIT ?''', (market_slug,now+3,limit))
    out=[]
    for r in reversed(rows):
        if not isinstance(r.get('recorded_at'),(int,float)):
            continue
        obs={'recorded_at':float(r['recorded_at'])}
        for k in ('bid','ask','last_trade'):
            val=r.get(k)
            obs[k]=float(val)*100 if isinstance(val,(int,float)) and isfinite(val) and 0<=val<=1 else None
        out.append(obs)
    return out
