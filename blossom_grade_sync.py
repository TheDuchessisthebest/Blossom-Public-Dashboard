"""Blossom Bot local, durable settlement grader — NEVER import into public viewer.

Uses only locally saved ORIGINAL calls and locally stored *official* settlement
records. Neither live prices nor a guessed BRTI strike can determine a result.
Standard Polymarket US BTC Up/Down contracts are recognized by an exact,
time-aligned slug and public series rules; other series require the existing
mapping_verified=1 flag. Nothing writes to the original calls/outcomes tables.
No keys, passwords, API requests or trade placement.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import time

from blossom_contracts import DURATIONS, SERIES_RULES, verified_standard_series


def _conn(path: Path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=15000')
    return db


def ensure_grades(path: Path) -> None:
    """Create only separate grade and health tables, never alter model tables."""
    if not path.is_file():
        raise FileNotFoundError(f'Private research DB not found: {path}')
    with _conn(path) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS blossom_verified_grades (
          source TEXT NOT NULL CHECK(source IN ('market','ai')),
          market_slug TEXT NOT NULL, timeframe TEXT NOT NULL,
          round_end REAL NOT NULL, called_at REAL NOT NULL,
          original_pick TEXT NOT NULL CHECK(original_pick IN ('UP','DOWN')),
          official_result TEXT NOT NULL CHECK(official_result IN ('UP','DOWN')),
          correct INTEGER NOT NULL CHECK(correct IN (0,1)),
          verified_by TEXT NOT NULL, graded_at REAL NOT NULL,
          PRIMARY KEY(source,market_slug))''')
        c.execute('''CREATE INDEX IF NOT EXISTS ix_blossom_grades_recent
                     ON blossom_verified_grades(source,timeframe,round_end DESC)''')
        c.execute('''CREATE TABLE IF NOT EXISTS blossom_grade_health (
                     id INTEGER PRIMARY KEY CHECK(id=1), last_sync REAL NOT NULL,
                     added INTEGER NOT NULL, waiting INTEGER NOT NULL,
                     unmapped INTEGER NOT NULL, inconsistent INTEGER NOT NULL,
                     conflicts INTEGER NOT NULL)''')


def _candidates(c: sqlite3.Connection):
    for source, sql in (
        ('market', '''SELECT j.market_slug AS slug,j.timeframe,j.round_start,j.round_end,
          j.first_side AS pick,j.first_at AS called_at,j.mapping_verified AS mapped,
          o.timeframe AS settlement_tf,o.end_time AS settlement_end,o.settlement
          FROM price_call_journal j LEFT JOIN official_outcomes o ON o.market_slug=j.market_slug'''),
        ('ai', '''SELECT a.slug AS slug,'5m' AS timeframe,a.round_start,a.round_end,
          a.original_side AS pick,a.original_at AS called_at,1 AS mapped,
          o.timeframe AS settlement_tf,o.end_time AS settlement_end,o.settlement
          FROM ai5m_rounds a LEFT JOIN official_outcomes o ON o.market_slug=a.slug''')):
        try:
            yield source, c.execute(sql).fetchall()
        except sqlite3.OperationalError as exc:
            if 'no such table' in str(exc).lower() or 'no such column' in str(exc).lower():
                continue
            raise


def reconcile(path: Path, *, now: float | None = None) -> dict[str,int]:
    """Insert completed verified grades once. Existing grades are immutable.

    Failed DB writes are not swallowed. A conflicting official settlement is
    counted but NEVER silently modifies a previously graded result.
    """
    now = time.time() if now is None else now
    ensure_grades(path)
    stats = {'added':0,'cached':0,'waiting':0,'unmapped':0,'inconsistent':0,'conflicts':0}
    with _conn(path) as c:
        for source, rows in _candidates(c):
            for row in rows:
                tf,slug = row['timeframe'],row['slug']
                start,end,called = row['round_start'],row['round_end'],row['called_at']
                if tf not in DURATIONS or row['pick'] not in ('UP','DOWN'):
                    stats['inconsistent'] += 1; continue
                try:
                    valid_times = (start is not None and end is not None and called is not None
                                   and float(start) <= float(called) < float(end)
                                   and abs(float(end)-float(start)-DURATIONS[tf]) <= 2)
                except (ValueError,TypeError,OverflowError):
                    valid_times = False
                if not valid_times:
                    stats['inconsistent'] += 1; continue
                known_series = verified_standard_series(slug,tf,start,end)
                if not known_series and row['mapped'] != 1:
                    stats['unmapped'] += 1; continue
                if row['settlement'] is None:
                    stats['waiting'] += 1; continue
                if (row['settlement'] not in (0,1) or row['settlement_tf'] != tf
                        or row['settlement_end'] is None
                        or abs(float(row['settlement_end'])-float(end)) > 2
                        or now < float(end)+60):
                    stats['inconsistent'] += 1; continue
                official_result = 'UP' if row['settlement'] == 1 else 'DOWN'
                record=(source,slug,tf,float(end),float(called),row['pick'],official_result,
                        int(row['pick'] == official_result),
                        SERIES_RULES if known_series else 'PRIVATELY_VERIFIED_CONTRACT_MAPPING',now)
                existing = c.execute('''SELECT original_pick,official_result,round_end FROM
                        blossom_verified_grades WHERE source=? AND market_slug=?''',(source,slug)).fetchone()
                if existing:
                    if (existing['original_pick'] != row['pick'] or
                        existing['official_result'] != official_result or
                        abs(float(existing['round_end'])-float(end)) > 2):
                        stats['conflicts'] += 1
                    else:
                        stats['cached'] += 1
                    continue
                c.execute('''INSERT INTO blossom_verified_grades
                    (source,market_slug,timeframe,round_end,called_at,original_pick,
                     official_result,correct,verified_by,graded_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?)''',record)
                stats['added'] += 1
        c.execute('''INSERT INTO blossom_grade_health
            (id,last_sync,added,waiting,unmapped,inconsistent,conflicts)
            VALUES(1,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET last_sync=excluded.last_sync,
              added=excluded.added,waiting=excluded.waiting,
              unmapped=excluded.unmapped,inconsistent=excluded.inconsistent,
              conflicts=excluded.conflicts''',
            (now,stats['added'],stats['waiting'],stats['unmapped'],
             stats['inconsistent'],stats['conflicts']))
    return stats
