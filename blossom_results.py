"""Blossom Bot settled-original-call scoreboards (read-only).

Trust only official_outcomes settlement values for the EXACT market slug and
matching timeframe/round-end. Never infer a winner from last trades, price,
market midpoints, or missing settlement values. Market-price-tier original calls
and independently trained AI original calls are kept in DIFFERENT rows.

This module never creates a database table, updates an existing call, or
submits an order. It is safe to run against a live SQLite database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
import sqlite3
from typing import Literal

Timeframe = Literal['5m','15m','1h']
Source = Literal['market', 'ai']
Mode = Literal['rolling', 'batch']
VALID_TF = ('5m','15m','1h')
MAX_BOXES = 20


def _read_db(path: Path, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    if not path.is_file():
        return []
    conn = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=8)
    conn.execute('PRAGMA query_only=ON')
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA busy_timeout=8000')
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        # An empty/older project database may not have the new tables yet.
        if 'no such table' in str(exc).lower() or 'no such column' in str(exc).lower():
            return []
        raise
    finally:
        conn.close()


def settled_original_calls(db: Path, timeframe: str, source: Source = 'market') -> list[dict]:
    """Read permanently stored grades written ONLY by local grade sync.

    The public viewer makes zero writes; each first call is graded at most once.
    """
    if timeframe not in VALID_TF or source not in ('market','ai'):
        return []
    if source == 'ai' and timeframe != '5m':
        return []
    rows = _read_db(db, """SELECT market_slug AS slug,timeframe,source,
          original_pick AS pick, official_result AS outcome, correct, called_at,
          round_end,verified_by FROM blossom_verified_grades
          WHERE timeframe=? AND source=?
          ORDER BY round_end ASC,called_at ASC,market_slug ASC""",(timeframe,source))
    return [dict(r) for r in rows]


def select_display_results(history: list[dict], mode: Mode = 'rolling', limit: int = MAX_BOXES) -> dict:
    """Select rolling latest 20 or a reset-after-every-20 batch.

    In batch mode results 1..20 appear together. As the 21st result settles,
    the board starts a new batch containing that result alone.
    """
    limit = max(1, min(MAX_BOXES, int(limit)))
    count = len(history)
    if mode == 'batch':
        page_start = ((count - 1) // limit) * limit if count else 0
        visible = history[page_start:page_start + limit]
        batch_number = page_start // limit + 1
    else:
        visible = history[-limit:]
        batch_number = None
    return {
        'items': visible,
        'right': sum(bool(v['correct']) for v in visible),
        'scored': len(visible),
        'total': count,
        'batch': batch_number,
        'limit': limit,
        'mode': mode,
    }


def result_health(db: Path, timeframe: str, source: Source = 'market') -> dict:
    """Display saved vs graded counts without treating pending as wrong.

    Official-outcome data is only INPUT to the LOCAL score keeper. A missing
    verifier or a stopped score keeper is visible instead of disappearing.
    """
    from blossom_contracts import verified_standard_series
    health = {k:0 for k in ('saved','graded','unverified_mapping',
             'awaiting_settlement','round_mismatch','invalid_call','awaiting_grade_sync')}
    health['last_graded_end'] = None
    health['last_sync'] = None
    if timeframe not in VALID_TF or source not in ('market','ai') or (source == 'ai' and timeframe != '5m'):
        return health
    graded = settled_original_calls(db,timeframe,source)
    health['graded'] = len(graded)
    if graded:
        health['last_graded_end'] = max(float(r['round_end']) for r in graded)
    try:
        sync = _read_db(db,'SELECT last_sync FROM blossom_grade_health WHERE id=1')
        if sync: health['last_sync'] = float(sync[0]['last_sync'])
    except sqlite3.Error:
        pass
    if source == 'market':
        rows = _read_db(db, """SELECT j.market_slug AS slug,j.round_start,j.round_end,
           j.first_side AS side,j.first_at AS called_at,j.mapping_verified AS verified,
           o.timeframe AS outcome_timeframe,o.end_time AS outcome_end,o.settlement,
           g.market_slug AS graded_slug
           FROM price_call_journal j
           LEFT JOIN official_outcomes o ON o.market_slug=j.market_slug
           LEFT JOIN blossom_verified_grades g ON g.source='market' AND g.market_slug=j.market_slug
           WHERE j.timeframe=?""", (timeframe,))
    else:
        rows = _read_db(db,"""SELECT a.slug,a.round_start,a.round_end,
           a.original_side AS side,a.original_at AS called_at,1 AS verified,
           o.timeframe AS outcome_timeframe,o.end_time AS outcome_end,o.settlement,
           g.market_slug AS graded_slug
           FROM ai5m_rounds a LEFT JOIN official_outcomes o ON o.market_slug=a.slug
           LEFT JOIN blossom_verified_grades g ON g.source='ai' AND g.market_slug=a.slug""")
    for row in rows:
        health['saved']+=1
        try:
            valid = (row['side'] in ('UP','DOWN') and row['called_at'] is not None
                     and row['round_start'] is not None and row['round_end'] is not None
                     and float(row['round_start']) <= float(row['called_at']) < float(row['round_end']))
        except (TypeError,ValueError): valid=False
        if not valid:
            health['invalid_call']+=1
        elif row['graded_slug']:
            pass
        elif row['verified'] != 1 and not verified_standard_series(
                row['slug'],timeframe,row['round_start'],row['round_end']):
            health['unverified_mapping']+=1
        elif row['settlement'] is None:
            health['awaiting_settlement']+=1
        elif (row['settlement'] not in (0,1) or row['outcome_timeframe'] != timeframe
              or row['outcome_end'] is None or abs(row['outcome_end']-row['round_end']) > 2):
            health['round_mismatch']+=1
        else:
            health['awaiting_grade_sync']+=1
    return health


def pending_count(db: Path, timeframe: str, source: Source = 'market') -> int:
    return result_health(db, timeframe, source)['awaiting_settlement']


def _health_note(health: dict) -> str:
    # These are *explanations*, not evidence that a prediction was accurate.
    if health['saved'] == 0:
        return 'No original calls saved yet'
    parts = []
    if health['awaiting_settlement']:
        parts.append(f"{health['awaiting_settlement']} awaiting official result")
    if health['unverified_mapping']:
        parts.append(f"{health['unverified_mapping']} mapping not verified")
    if health['round_mismatch']:
        parts.append(f"{health['round_mismatch']} unmatched settlement/round")
    if health['invalid_call']:
        parts.append(f"{health['invalid_call']} invalid call time/side")
    if health['awaiting_grade_sync']:
        parts.append(f"{health['awaiting_grade_sync']} ready for local grade sync")
    if health['last_sync'] is None:
        parts.append('start AI_RESEARCH.py or run BLOSSOM_LAST20_SYNC.py --sync')
    elif __import__('time').time() - health['last_sync'] > 180:
        parts.append('grade sync paused')
    if not parts:
        parts.append(f"{health['graded']} officially graded")
    return ' · '.join(parts)


def render_scoreboard(db: Path, mode: Mode = 'rolling') -> str:
    """Return a compact, accessible floral scoreboard. No external requests."""
    e = lambda obj: escape(str(obj), quote=True)
    rows_html: list[str] = []
    for tf, short in [('5m','5 MIN'),('15m','15 MIN'),('1h','1 HOUR')]:
        history = settled_original_calls(db, tf, source='market')
        state = select_display_results(history, mode)
        health = result_health(db, tf, source='market')
        rows_html.append(_render_row(state,short,'Market-price calls',health,e))
    ai_history = settled_original_calls(db,'5m',source='ai')
    ai_state = select_display_results(ai_history, mode)
    ai_health = result_health(db,'5m',source='ai')
    # Separate AI row avoids falsely labeling market odds as AI predictions.
    ai_html = _render_row(ai_state,'5 MIN AI','Original AI calls',ai_health,e)
    return (
        '<section class="blossom-board" aria-label="Last twenty officially settled original calls">'
        '<div class="bb-heading"><div><span class="bb-overline">✿ THE BLOSSOM RECORD</span>'
        '<div class="bb-title">🌸 Last 20 calls <span class="bb-hint">· first pick only</span></div></div>'
        f'<span class="bb-mode">{ "New batch every 20" if mode == "batch" else "Rolling latest 20" }</span></div>'
        '<div class="bb-note">🌿 Green = correct · 🌹 red = wrong · muted = no settled call. '
        'Only exact, officially settled outcomes are graded. A market-price call is <b>not</b> an AI forecast.</div>'
        '<div class="bb-results">'+''.join(rows_html)+'</div>'
        '<div class="bb-ai-divider"><span>❀ INDEPENDENT AI · 5 MIN</span><small>Prototype / unvalidated</small></div>'
        '<div class="bb-results">'+ai_html+'</div>'
        '<div class="bb-foot">Boxes show original UP/DOWN calls, even if the current pick changed later. '
        'Only verified standard US BTC series (or explicitly mapped contracts) count. '
        'These scores are not proof of profitability. A separate BTC worker can trade live.</div>'
        '</section>'
    )


def _render_row(state: dict, title: str, subtitle: str, health: dict, escape_fn) -> str:
    e=escape_fn
    boxes: list[str] = []
    for i, result in enumerate(state['items']):
        ok = result['correct']
        icon = '✓' if ok else '×'
        label = 'Correct' if ok else 'Wrong'
        moment = datetime.fromtimestamp(result['round_end'], tz=timezone.utc).strftime('%b %d %H:%M UTC')
        tooltip = f"{label} · {moment} · original {result['pick']} · final {result['outcome']} · {result['slug']}"
        boxes.append(f'<span class="bb-square {"right" if ok else "wrong"}" title="{e(tooltip)}" '
                     f'aria-label="{e(tooltip)}">{icon}</span>')
    for i in range(MAX_BOXES - len(boxes)):
        boxes.append('<span class="bb-square empty" title="No settled call yet" aria-label="Unfilled">·</span>')
    scored=state['scored']
    note = _health_note(health)
    if state['mode'] == 'batch' and state['total']:
        note = f'Batch {state["batch"]} · {note}'
    if health['graded'] and health['last_graded_end']:
        moment = datetime.fromtimestamp(health['last_graded_end'], timezone.utc).strftime('%b %d %H:%M UTC')
        note += f' · latest graded {moment}' 
    return (
        '<div class="bb-row">'
        f'<div class="bb-row-label"><b>{e(title)}</b><small>{e(subtitle)}</small></div>'
        '<div class="bb-strip">'+''.join(boxes)+'</div>'
        '<div class="bb-row-score">'
        f'<b>{state["right"]} <span>/ {scored}</span></b>'
        f'<small>{e(note)}</small></div></div>'
    )


BLOSSOM_STYLES = r'''<style>
:root {--bb-green:#8bdfb3; --bb-red:#ff8d9b; --bb-lilac:#c4a2e7;}
.blossom-board{position:relative;overflow:hidden;padding:19px 21px 17px;margin:15px 0 19px;
  border:1px solid rgba(255,173,213,.23);border-radius:19px;
  background:radial-gradient(ellipse 45% 110% at 100% 0%,rgba(255,151,208,.12),transparent 85%),
             linear-gradient(135deg,#271a2a,#19151f 75%);
  box-shadow:0 8px 29px rgba(19,10,23,.20)}
.blossom-board:before{content:'✿';position:absolute;right:-20px;top:-47px;font-size:152px;
  color:rgba(255,142,199,.062);pointer-events:none;line-height:1}
.bb-heading{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:8px;flex-wrap:wrap;position:relative;}
.bb-overline{font-size:10px;letter-spacing:1.8px;color:#f7a7d1;font-weight:800}
.bb-title{font-size:21px;font-weight:850;color:#ffe5f2;letter-spacing:-.45px;margin-top:4px}
.bb-hint{font-size:12px;color:#c6a9c0;font-weight:550}
.bb-mode{font-size:11px;color:#ffc1df;padding:6px 10px;border:1px solid rgba(255,177,218,.25);
 border-radius:999px;background:rgba(255,148,204,.08)}
.bb-note{color:#dbc1d2;font-size:11px;line-height:1.65;margin:8px 0 15px}
.bb-results{display:grid;gap:11px}
.bb-row{display:grid;grid-template-columns:148px minmax(0,1fr) 130px;align-items:center;gap:14px;
 background:rgba(255,255,255,.018);border:1px solid rgba(255,153,202,.09);border-radius:11px;
 padding:10px 12px;position:relative}
.bb-row-label b{display:block;color:#ffe1ee;font-size:13px}
.bb-row-label small{display:block;color:#a994a7;font-size:10px;margin-top:3px}
.bb-strip{display:grid;grid-template-columns:repeat(20,minmax(11px,1fr));gap:4px;align-items:center;}
.bb-square{display:grid;place-items:center;height:24px;min-width:0;border-radius:5px;font-size:12px;
 font-weight:900;color:#18231b;transition:filter .15s ease,transform .15s ease;cursor:help;}
.bb-square:hover{transform:translateY(-2px);filter:brightness(1.16)}
.bb-square.right{background:linear-gradient(160deg,#a9e7be,#7ad5a8);box-shadow:0 0 0 1px rgba(139,223,179,.18)}
.bb-square.wrong{background:linear-gradient(160deg,#ffadb6,#f28195);box-shadow:0 0 0 1px rgba(255,141,155,.19)}
.bb-square.empty{background:#342939;border:1px dashed #5c435a;color:#624d60;font-size:12px}
.bb-row-score{text-align:right}
.bb-row-score b{display:block;font-size:16px;color:#fce1ed;font-variant-numeric:tabular-nums}
.bb-row-score b span{font-size:11px;color:#b6a0b2;font-weight:650}
.bb-row-score small{display:block;color:#9f8b9d;font-size:10px;margin-top:3px;line-height:1.4}
.bb-ai-divider{display:flex;justify-content:space-between;align-items:center;gap:9px;border-top:1px solid rgba(251,168,211,.14);
 margin:15px 0 10px;padding-top:12px;color:#f5add0;font-size:10px;font-weight:850;letter-spacing:1.1px}
.bb-ai-divider small{font-weight:550;letter-spacing:0;color:#b49eae}
.bb-foot{color:#a993a7;font-size:10px;line-height:1.6;margin-top:12px}
@media(max-width:1050px){.bb-row{grid-template-columns:110px minmax(0,1fr) 95px;gap:9px}.bb-strip{gap:3px}.bb-square{height:20px}}
@media(max-width:730px){.bb-row{display:block;padding:12px}.bb-row-label{margin-bottom:8px}
  .bb-row-score{text-align:left;margin-top:6px}.bb-row-score b{display:inline;margin-right:10px}
  .bb-row-score small{display:inline}.bb-strip{gap:2px}.bb-square{height:21px;border-radius:3px}}
@media(prefers-reduced-motion:reduce){.bb-square{transition:none}}
</style>'''

BLOSSOM_STYLES += r'''<style>
.bb-row-score {min-width:0}
.bb-row-score small {word-break:normal;overflow-wrap:anywhere}
.bb-row-label small {line-height:1.5}
@media(max-width:730px){.bb-row-score small{display:block;margin-top:5px}}
</style>'''
