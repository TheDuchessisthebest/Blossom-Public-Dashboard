"""Blossom Bot v2.8 — private-admin-inspired read-only public viewer, cherry blossoms.

Start on a separate local port (8504); tunnel ONLY this viewer to the public.
Never imports the admin dashboard, Polymarket SDK, or any order-writing code.
All SQLite access is mode=ro, query_only=ON. No API keys or wallet access.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
import math
import time

import streamlit as st

from viewer_data import read_snapshot, public_training_status, directional_model_probability, read_quote_timeline
from viewer_timers import timer_html
from blossom_results import BLOSSOM_STYLES, render_scoreboard, settled_original_calls
from blossom_theme import render_theme
from viewer_admin_mirror import MIRROR_CSS, market_overview_card, training_tiles

ROOT=Path(__file__).resolve().parent
DB=ROOT/'us_data'/'quotes.sqlite3'
MODELS=DB.parent/'models'
NAMES={'5m':'5 MINUTES', '15m':'15 MINUTES','1h':'1 HOUR'}

def call_snapshot():
    import json
    from shared_call_feed import fetch
    config=json.loads((ROOT/'shared_feed.json').read_text(encoding='utf-8'))
    if config.get('mode')=='personal_shared':
        url=config.get('url')
        if not url:raise ValueError('Shared feed is not configured')
        return fetch(url)
    return read_snapshot(DB)

st.set_page_config(page_title='🌸 Blossom Bot · Live Viewer',page_icon='🌸',layout='wide',initial_sidebar_state='collapsed')

st.markdown('''<style>
:root {--pink:#ff8dc7;--line:rgba(255,169,215,.23);--pale:#ffe9f4;--soft:#d3b5c9;}
.stApp{background:radial-gradient(ellipse 65% 46% at 95% 0%,#3b1a36 0%,transparent 65%),radial-gradient(ellipse 43% 28% at 0% 70%,#281a2d,transparent 80%),#120e17;color:#f9eafa;}
.block-container{max-width:1220px;padding:1.75rem 1rem 4rem;}
header[data-testid="stHeader"]{background:transparent;}
#MainMenu,footer{visibility:hidden;}
.hero-public{padding:15px 0 19px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px;}
.eyebrow-public{font-size:10px;letter-spacing:2.5px;font-weight:900;color:#ffb1d7;}
.hero-title-public{font-size:clamp(30px,5vw,45px);font-weight:900;letter-spacing:-1.6px;color:#fff0fa;line-height:1.1;margin-top:9px;}
.hero-title-public em{color:#ff80bd;font-style:normal;}
.hero-desc-public{font-size:13px;color:#c6aec3;line-height:1.7;margin-top:9px;}
.viewer-chip{border:1px solid #794a68;background:#321f31;border-radius:50px;padding:9px 14px;color:#ffd5e9;font-weight:750;font-size:11px;white-space:nowrap;}
.notice-public{background:linear-gradient(115deg,#281728,#231923);border-left:3px solid #ee77b0;border-radius:12px;padding:13px 16px;color:#eec5df;font-size:12px;margin:8px 0 20px;line-height:1.65;}
.section-public{font-size:20px;font-weight:850;color:#ffe8f6;margin:22px 0 13px;letter-spacing:-.4px;}
.public-card{background:linear-gradient(160deg,#2a1a2d,#1b1622 82%);border:1px solid var(--line);border-radius:20px;padding:18px 18px 16px;min-height:238px;position:relative;overflow:hidden;box-shadow:0 14px 32px rgba(5,0,5,.14);}
.public-card:before{content:"✿";position:absolute;right:10px;top:-19px;font-size:93px;color:rgba(255,164,206,.046);pointer-events:none;}
.public-head{display:flex;justify-content:space-between;align-items:center;gap:8px;position:relative;}
.public-tf{font-size:15px;font-weight:850;color:#ffe4f2;}
.public-status{font-size:10px;letter-spacing:.5px;font-weight:750;border-radius:50px;padding:6px 9px;background:#3d2940;color:#d7b5d1;border:1px solid #694662;}
.public-status.live{background:rgba(74,159,111,.12);color:#a0eac0;border-color:#507a62;}
.public-status.stale{color:#ffe2b5;border-color:#75603c;}
.public-call{font-size:clamp(23px,3vw,30px);font-weight:900;letter-spacing:-.7px;margin-top:23px;position:relative;}
.public-call.up{color:#92e6b2;}.public-call.down{color:#ff8d9b;}.public-call.wait{color:#c6acc6;}
.public-call.locked.up{text-shadow:0 0 19px rgba(133,240,176,.55);}
.public-call.locked.down{text-shadow:0 0 19px rgba(255,113,143,.48);}
.public-caption{font-size:11px;color:#c6acc3;line-height:1.65;margin-top:5px;position:relative;}
.public-picks{display:flex;gap:9px;margin-top:19px;position:relative;}
.public-pick{flex:1;border:1px solid #583950;background:#251b2b;border-radius:10px;padding:10px 9px;min-width:0;}
.public-pick small{display:block;font-size:9px;letter-spacing:1.1px;font-weight:800;color:#ad8ea8;}
.public-pick b{font-size:16px;display:block;margin-top:4px;}
.public-pick b.up{color:#9becc0;}.public-pick b.down{color:#ffa3b1;}
.public-market{margin-top:11px;color:#f7d0e8;font-size:12px;position:relative;}
.public-caution{font-size:10px;color:#ae92a9;line-height:1.65;margin-top:11px;position:relative;}
.public-ref{border:1px solid #4b3548;background:#1d1822;border-radius:16px;padding:17px 18px;margin:7px 0 10px;}
.ref-head{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:#e7cae0;font-weight:800;}
.ref-up{color:#9be7b2}.ref-down{color:#f3a2ad}
.ref-rail{height:13px;position:relative;border-radius:20px;background:linear-gradient(90deg,#e8a9a2,#d6c9bd 50%,#badcbf);margin-top:19px;}
.ref-mid{position:absolute;top:-8px;bottom:-8px;left:50%;border-left:2px dashed #fff2fa;opacity:.85;}
.ref-marker{position:absolute;top:-7px;left:50%;transform:translateX(-50%);width:15px;height:27px;border:2px solid #fdf1f9;border-radius:9px;background:#2e2934;box-shadow:0 0 0 2px rgba(18,13,21,.65);}
.ref-meta{display:flex;justify-content:space-between;margin-top:13px;font-size:10px;color:#bba3b8;gap:10px;}
.ref-meta b{color:#ffe7f2;font-size:11px;}
.small-muted{color:#bd9eb7;font-size:11px;line-height:1.75;}
.stTabs [data-baseweb="tab-list"] {gap:8px;}
.stTabs [data-baseweb="tab"] {border-radius:8px;background:#2b202d;color:#f0bede;}
@media(max-width:640px){.block-container{padding:1.1rem .75rem 3rem}.public-card{min-height:0;margin-bottom:3px}.public-picks{flex-wrap:wrap}.hero-public{padding-top:7px}.ref-meta{font-size:9px}}
</style>''',unsafe_allow_html=True)
st.markdown(BLOSSOM_STYLES,unsafe_allow_html=True)
st.markdown(render_theme(ROOT),unsafe_allow_html=True)
st.markdown(MIRROR_CSS,unsafe_allow_html=True)
st.markdown('''<style>
.mini-ref{border:1px solid rgba(230,163,198,.2);border-radius:11px;padding:10px 11px;margin:13px 0 4px;background:rgba(14,10,17,.28)}
.mini-ref-top{display:flex;justify-content:space-between;gap:8px;font-size:9px;letter-spacing:.5px;color:#c6b2c0;font-weight:760}
.mini-ref-track{position:relative;height:9px;border-radius:99px;margin-top:12px;background:linear-gradient(90deg,#eba5a5,#d7c0bd 50%,#a8d6b5)}
.mini-ref-center{position:absolute;left:50%;top:-5px;bottom:-5px;border-left:2px dashed #ffe7f4}
.mini-ref-pointer{position:absolute;top:-6px;height:21px;width:11px;border-radius:9px;background:#231c26;border:2px solid #ffe7f6;transform:translateX(-50%);box-shadow:0 0 0 2px #151017}
.mini-ref-caption{margin-top:11px;color:#c9a9be;font-size:10px;line-height:1.5}.mini-ref-caption b.up{color:#8ce4ae}.mini-ref-caption b.down{color:#ff90a0}
.mini-ref-note{font-size:10px;color:#c1a1b8;margin:13px 0 4px}
</style>''',unsafe_allow_html=True)

# A VIEW-ONLY navigation control. It changes only this browser's selected chart;
# it never writes to SQLite or the private bot's strategy settings.
with st.sidebar:
    st.markdown('<div class="sidebar-kicker">YOUR WORKSPACE</div><div class="sidebar-brand">🌸 Blossom Bot</div>'
                '<div class="sidebar-note">Polymarket US · BTC prediction garden</div>',unsafe_allow_html=True)
    st.divider()
    st.markdown('<div class="sidebar-header">🌸 Select timeframe</div>',unsafe_allow_html=True)
    selected_tf = st.radio('Public detail view', ['5m','15m','1h'],
                           format_func=lambda tf:{'5m':'5 minutes','15m':'15 minutes','1h':'1 hour'}[tf],
                           label_visibility='collapsed', key='blossom_public_tf')
    st.divider()
    st.markdown('<div class="sidebar-foot">🔒 <strong>PUBLIC VIEWER · READ ONLY</strong><br>'
                'Same market results and cherry-blossom theme as your admin studio.<br>'
                'No bot controls, private keys, or order submission.</div>',unsafe_allow_html=True)
    st.markdown('<div class="sidebar-note" style="margin-top:15px">Live market snapshots refresh ~8s; '
                'saved result grades refresh ~10s. UTC time; availability depends on the home PC.</div>',unsafe_allow_html=True)



def fmt_time(ts):
    if not isinstance(ts,(float,int)) or not math.isfinite(float(ts)):
        return '—'
    return datetime.fromtimestamp(ts,timezone.utc).strftime('%H:%M UTC')


def fmt_time_seconds(ts):
    """Show the time an observation was recorded, never a guessed update time."""
    if not isinstance(ts,(float,int)) or not math.isfinite(float(ts)):
        return 'not recorded'
    return datetime.fromtimestamp(ts,timezone.utc).strftime('%H:%M:%S UTC')


def fmt_age(seconds):
    if not isinstance(seconds,(float,int)) or not math.isfinite(float(seconds)):
        return 'unknown age'
    s=max(0,int(seconds))
    if s < 60:
        return f'{s}s ago'
    if s < 3600:
        return f'{s//60}m {s%60}s ago'
    return f'{s//3600}h {(s%3600)//60}m ago'


def fmt_price(value):
    return f'{float(value)*100:.1f}¢' if isinstance(value,(float,int)) and math.isfinite(value) else '—'


def side_color(side):
    return 'up' if side=='UP' else 'down' if side=='DOWN' else 'wait'


def call_card(tf, view, snapshot_time):
    rnd=view['round']
    call=view['call']
    q=view['quote']
    fresh=bool(q and q.get('fresh'))
    status='FRESH' if fresh else 'NO LIVE QUOTE' if not q else 'STALE/INCOMPLETE'
    badge_cls='live' if fresh else 'stale'
    if call and call['is_current']:
        side=call['current_side']
        tier=call['current_tier']
        first=call['first_side']
        title=f'{tier} {side}' if fresh else f'SAVED {tier} {side}'
        note=('Shared personal-dashboard call; original and current picks retain their source timestamps. '
              'LOCKED is a price tier, not a guarantee.')
        if not fresh:
            note='Saved call retained; no fresh quote confirms its present strength. '+note
        strength=call.get('first_strength')
        score=(f'{float(strength)*100:.1f}¢ market-priced at first call' if isinstance(strength,(float,int)) and strength<=1 else
               f'{float(strength):.1f}¢ market-priced at first call' if isinstance(strength,(float,int)) else 'First-call price unavailable')
        picks=f'''<div class="public-picks"><div class="public-pick"><small>ORIGINAL</small><b class="{side_color(first)}">{first}</b></div>
             <div class="public-pick"><small>CURRENT</small><b class="{side_color(side)}">{side}</b></div></div>'''
    elif call:
        side='WAIT';tier='WAIT';title='WAIT · NO CURRENT CALL'
        note='Previous saved call is archived; this round has no confirmed call yet.'
        score=f'Last saved round ended {fmt_time(call["round_end"])}'
        picks=f'''<div class="public-picks"><div class="public-pick"><small>PREVIOUS ORIGINAL</small><b class="{side_color(call["first_side"])}">{call["first_side"]}</b></div>
        <div class="public-pick"><small>PREVIOUS CURRENT</small><b class="{side_color(call["current_side"])}">{call["current_side"]}</b></div></div>'''
    else:
        side='WAIT';tier='WAIT';title='WAIT · NO CALL'
        note='Awaiting a saved UP or DOWN call for this market.'
        score='No saved call available'
        picks=''
    bidask=(f'YES bid {fmt_price(q["bid"])} · ask {fmt_price(q["ask"])}' if q and q.get('valid') else 'No usable two-sided price')
    latest_time=(q.get('recorded_at') if q else view.get('last_quote_seen'))
    if isinstance(latest_time,(float,int)) and math.isfinite(float(latest_time)):
        last_update=f'Last quote: {fmt_time_seconds(latest_time)} · {fmt_age(snapshot_time-float(latest_time))}'
        if not q:
            last_update+=' · may be from a previous round'
    else:
        last_update='No quote timestamp recorded yet'
    rnd_text=('Expected round end '+fmt_time(rnd['end']) if rnd else 'Current market not confirmed')
    feed=view.get('feed_health')
    if feed:
        rnd_text+=' | Feed: '+str(feed.get('status','Unknown'))+' at '+fmt_time_seconds(feed.get('checked_at'))
    # Compact price-to-beat bar INSIDE each live call panel, like the admin.
    ref=view.get('reference') or {}
    mini_ref='<div class="mini-ref-note">🌿 Reference price unavailable — no fabricated price-to-beat.</div>'
    if ref.get('status') in ('FRESH','STALE') and isinstance(ref.get('strike'),(float,int)) and isinstance(ref.get('price'),(float,int)):
        strike=float(ref['strike']); px=float(ref['price']); delta=px-strike
        half=max(75.0,strike*.001)
        pos=max(0.0,min(100.0,50.0+delta/half*50.0))
        arrow='UP' if delta>=0 else 'DOWN'
        mini_ref=(f'<div class="mini-ref"><div class="mini-ref-top">'
                  f'<span>DOWN</span><span>BTC PRICE TO BEAT · {strike:,.2f}</span><span>UP</span></div>'
                  f'<div class="mini-ref-track"><span class="mini-ref-center"></span>'
                  f'<span class="mini-ref-pointer" style="left:{pos:.2f}%"></span></div>'
                  f'<div class="mini-ref-caption">Observed BTC: ${px:,.2f} · '
                  f'<b class="{side_color(arrow)}">{arrow} ${abs(delta):,.2f}</b>'
                  f'{" · STALE" if ref["status"]=="STALE" else ""}</div></div>')
    markup=f'''<article class="public-card"><div class="public-head"><span class="public-tf">🌸 {NAMES[tf]}</span><span class="public-status {badge_cls}">{status}</span></div>
     <div class="public-call {side_color(side)} {'locked' if tier=='LOCKED' else ''}">{escape(title)}</div>
     <div class="public-caption">{escape(note)}</div>{picks}
     {mini_ref}
     <div class="public-market">{escape(bidask)}</div>
     <div class="public-caution">{escape(last_update)}<br>{escape(score)}<br>{escape(rnd_text)} · UTC · Research observations only</div></article>'''
    return markup


def reference_bar(ref):
    if ref.get('status') not in ('FRESH','STALE'):
        last=ref.get('source_timestamp')
        when=(f'Last BTC reference tick: {fmt_time_seconds(last)} · {fmt_age(ref.get("source_age"))}'
              if isinstance(last,(float,int)) else 'No BTC reference tick recorded yet')
        return ('''<div class="public-ref"><div class="ref-head">🌿 BTC movement · BRTI reference</div>'''
                '''<div class="small-muted" style="margin-top:12px">No live price motion available. The price-to-beat bar needs 60 consecutive opening reference ticks and a current BRTI tick.</div>'''
                f'''<div class="small-muted" style="margin-top:10px">{escape(when)}</div></div>''')
    strike=ref['strike'];px=ref['price'];delta=px-strike
    half=max(75.,strike*.001)
    left=max(0,min(100,50+delta/half*50))
    direction='UP' if delta>=0 else 'DOWN'
    return f'''<div class="public-ref"><div class="ref-head"><span>🌿 BTC movement · published BRTI</span><span class="{'ref-up' if delta>=0 else 'ref-down'}">{direction} ${abs(delta):,.2f}</span></div>
    <div class="ref-rail"><span class="ref-mid"></span><span class="ref-marker" style="left:{left:.2f}%"></span></div>
    <div class="ref-meta"><span>${strike-half:,.2f}</span><span style="text-align:center">PRICE TO BEAT*<br><b>${strike:,.2f}</b></span><span>${strike+half:,.2f}</span></div>
    <div class="small-muted" style="margin-top:11px">Latest observed index ${px:,.2f} · {fmt_time_seconds(ref.get('timestamp'))} · {'Fresh' if ref['status']=='FRESH' else 'STALE'} ({fmt_age(ref['age'])}). *Opening average is reconstructed, not independently verified against official strike. This is not the final 60-second settlement average.</div></div>'''


def ai_card(ai):
    if not ai:
        return '<div class="public-ref"><b>🧠 5-minute AI · Awaiting recorded independent forecasts</b><div class="small-muted">Research model predictions will appear here after the private collector records qualifying calls.</div></div>'
    original=ai['original_side']; current=ai['current_side']
    old=not ai['is_current']
    first=directional_model_probability(original,ai.get('original_probability'))
    latest=directional_model_probability(current,ai.get('current_probability'))
    first_text=f'{first:.1f}%' if first is not None else '—'
    latest_text=f'{latest:.1f}%' if latest is not None else '—'
    status='ARCHIVED — PRIOR ROUND' if old else 'CURRENT ROUND'
    note=('The original and current model scores are estimated directional probabilities, NOT verified accuracy. '
          'An archived call is not a live trade signal.')
    return (f'<div class="public-ref"><div class="ref-head"><span>🧠 5-minute independent AI</span><span>{status}</span></div>'
            f'<div class="public-picks">'
            f'<div class="public-pick"><small>ORIGINAL PICK</small><b class="{side_color(original)}">{escape(original)} · {escape(first_text)}</b></div>'
            f'<div class="public-pick"><small>CURRENT PICK</small><b class="{side_color(current)}">{escape(current)} · {escape(latest_text)}</b></div>'
            f'</div><div class="small-muted" style="margin-top:12px">{note}</div></div>')




# Public adapters: presentation only; no private database or execution imports.
SHORT={'5m':'5 MIN','15m':'15 MIN','1h':'1 HOUR'}
def market_status(m,now):
    return 'estimated_active' if m.get('start',now+1)<=now<m.get('end',0) else 'ended'
def paper_call_for(*args): return None
def current_research_call(*args): return None
def cents(v): return f'{v*100:.1f}¢' if isinstance(v,(int,float)) else '—'
def quote_health_explanation(q): return 'Observed two-sided quote' if q.get('health')=='STREAM_OK' else 'No fresh two-sided quote'
def public_quote(entry):
    q=entry.get('quote') or {}
    return {**q,'last':q.get('last_trade'),'fetched_at':q.get('recorded_at'),'health':'STREAM_OK' if q.get('fresh') and q.get('valid') else 'STALE'}

def change_aware_call_state(signal: dict, saved: dict | None) -> dict:
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

def x(value: object) -> str:
    """HTML escape all values that can originate in external market data."""
    return escape(str(value), quote=True)

def utc_hm(ts: float | None) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M UTC") if ts is not None else "—"

def market_tile(tf: str, market: dict | None, quote: dict | None, now: float, upcoming: dict | None):
    if market is None:
        note = (
            f"Next candidate around {utc_hm(upcoming['start'])}"
            if upcoming is not None else "No confidently identified active market yet"
        )
        return f"""
        <div class="market-card muted">
          <div class="market-top"><div class="market-name"><span class="coin-icon">₿</span>{x(SHORT[tf])}</div><span class="status idle">SEARCHING</span></div>
          <div class="market-caption">YES bid / ask <span class="quote-unit">· 0–100¢</span></div>
          <div class="market-quote"><span class="empty">—</span></div>
          <div class="market-empty">{x(note)}</div>
          <div class="market-bottom"><div><div class="mini-label">LAST TRADE</div><div class="mini-value">—</div></div><div><div class="mini-label">WINDOW</div><div class="mini-value">—</div></div></div>
        </div>"""
    status = market_status(market, now)
    status_label = "EST. ACTIVE" if status == "estimated_active" else status.upper().replace("_", " ")
    quote = quote or {}
    bid, ask, last = quote.get("bid"), quote.get("ask"), quote.get("last")
    price_text = (
        f'{x(cents(bid))}<span class="slash">/</span>{x(cents(ask))}'
        if bid is not None and ask is not None else '<span class="empty">—</span>'
    )
    feed_health = quote.get("health", "UNKNOWN")
    feed_note = quote_health_explanation(quote)
    quote_css = "ok" if feed_health in ("BBO_OK", "BOOK_OK", "STREAM_OK") else ""
    return f"""
    <div class="market-card">
      <div class="market-top"><div class="market-name"><span class="coin-icon">₿</span>{x(SHORT[tf])}</div><span class="status">{x(status_label)}</span></div>
      <div class="market-caption">YES bid / ask <span class="quote-unit">· 0–100¢</span></div>
      <div class="market-quote">{price_text}</div>
      <div class="feed-message {x(quote_css)}">{x(feed_health)} · {x(feed_note)}
      {(' · ' + x(quote.get('detail', ''))) if feed_health in ('RATE_LIMIT', 'RATE_LIMIT_COOLDOWN','QUOTE_EXPIRED') else ''}</div>
      <div class="market-bottom">
        <div><div class="mini-label">LAST TRADE</div><div class="mini-value">{x(cents(last))}</div></div>
        <div><div class="mini-label">EST. WINDOW END</div><div class="mini-value">{x(utc_hm(market.get('end')))}</div></div>
      </div>
      <div class="market-slug" title="{x(market['slug'])}">{x(market['slug'])}</div>
    </div>"""

def model_forecast_tile(tf: str, forecast: dict) -> str:
    """Report honest model state separately from observed-price CALL status."""
    ready = forecast.get('status') == 'RESEARCH_FORECAST'
    if ready:
        pct = float(forecast['prob_up']) * 100
        direction = forecast['direction']
        chosen_pct = pct if direction == 'UP' else 100-pct
        headline = f'Experimental model: {direction} · {chosen_pct:.1f}% {direction}'
        warning = ('Research-validated holdout (still no trading)' if forecast.get('validated')
                   else 'PROTOTYPE · not validated; do not trade')
        details = (f"Test Brier {forecast.get('holdout_brier', '—')} · "
                   f"market benchmark {forecast.get('market_brier', '—')}")
    else:
        headline = 'AI: '+str(forecast.get('status','WAIT')).replace('_',' ')
        warning = str(forecast.get('reason','Collecting index prices and resolved outcomes'))
        details = 'Price-tier CALL above is NOT the model prediction.'
    return (f'<div class="ai-forecast" style="margin-top:8px;padding:13px 16px;'
            f'background:rgba(160,83,143,.12);border:1px solid rgba(254,159,206,.22);'
            f'border-radius:13px;"><div style="font-size:11px;color:#ffabd4;'
            f'font-weight:700;letter-spacing:1px;">BTC AI · {x(tf.upper())} · READ ONLY</div>'
            f'<div style="font-size:14px;font-weight:700;color:#ffe8f3;margin-top:6px;">'
            f'{x(headline)}</div><div style="font-size:11px;color:#d9bdd0;margin-top:5px;">'
            f'{x(warning)}</div><div style="font-size:10px;color:#a99cad;margin-top:5px;">'
            f'{x(details)}</div></div>')

def render_ai5m_lab(forecast: dict, saved: dict | None, archived: dict | None,
                    record_event: dict, mapping_ok: bool, paper_enabled: bool,
                    market: dict | None, quote: dict | None, now: float,
                    metrics: dict) -> str:
    ready = forecast.get('status') == 'RESEARCH_FORECAST'
    p = forecast.get('prob_up') if ready else None
    if not isinstance(p, (int,float)) or not 0 <= p <= 1:
        p = None
    model_dir = ('UP' if p >= .5 else 'DOWN') if p is not None else None
    model_pct = (max(p, 1-p)*100) if p is not None else None
    live_label = (f'{model_dir} · {model_pct:.1f}% prototype score'
                  if model_dir else 'WAIT · no fresh model forecast')
    explanation = (f'Model test Brier: {forecast.get("holdout_brier", "—")} · '
                   f'Market benchmark: {forecast.get("market_brier", "—")}'
                   if ready else str(forecast.get('reason', 'Research feed unavailable')))
    current='—'; first='—'; age='—'; sw='0'; msg='No qualifying model call recorded for this round.'
    if saved:
        first = f'{saved["original_side"]} · {max(saved["original_probability"],1-saved["original_probability"])*100:.1f}%'
        current = f'{saved["current_side"]} · {max(saved["current_probability"],1-saved["current_probability"])*100:.1f}%'
        age = utc_hm(saved['original_at']); sw=str(saved['switches'])
        msg='Saved original and current AI calls persist through quote dropouts and page refreshes.'
    elif archived:
        msg=(f'Previous round archived: {archived["original_side"]} originally; '
             f'{archived["current_side"]} finally. No call for the new round yet.')
    if not mapping_ok:
        msg='Verify YES=UP and NO=DOWN in the sidebar before saving AI UP/DOWN calls.'
    if saved and saved.get('outcome') in (0,1):
        msg += f' Officially settled: {"UP" if saved["outcome"] == 1 else "DOWN"}.'
    color = '#86E7AD' if model_dir=='UP' else ('#FF899A' if model_dir=='DOWN' else '#cbb7c7')
    def pick_html(label: str, value: str, side: str | None):
        pc='#91E8AD' if side=='UP' else '#FF93A1' if side=='DOWN' else '#ecd7e7'
        return (f'<div class="ai5-pick"><small>{x(label)}</small>'
                f'<strong style="color:{pc}">{x(value)}</strong></div>')
    first_side=saved['original_side'] if saved else None
    current_side=saved['current_side'] if saved else None
    paper_note='SIMULATION OFF · no order placed'
    if paper_enabled:
        paper_note=paper_decision_reason(market,quote,forecast,now,mapping_ok,paper_enabled,saved)
    if saved and saved.get('paper_direction'):
        basis='actual YES ask observation' if saved['paper_price_basis']=='OBSERVED_YES_ASK' else 'INFERRED NO reference · not an executable ask'
        paper_note=(f'PAPER ONLY: {saved["paper_direction"]} at {saved["paper_price"]*100:.1f}¢ '
                    f'({basis}); 1 hypothetical share, gross before fees')
        if saved.get('outcome') in (0,1):
            won = (saved['paper_direction']=='UP')==(saved['outcome']==1)
            gross=(1 if won else 0)-saved['paper_price']
            paper_note+=f' · settled gross {gross:+.2f} USD'
    if not market:
        model_caption='No active verified round. Prior calls remain archived.'
    elif not ready:
        model_caption='Model unavailable; saved picks shown from local SQLite only.'
    else:
        model_caption='Prototype probability, NOT calibrated confidence or a verified edge.'
    n=metrics['resolved']
    accuracy=(f'{100*metrics["original_correct"]:.1f}%' if n else '—')
    current_accuracy=(f'{100*metrics["current_correct"]:.1f}%' if n else '—')
    brier=(f'{metrics["first_brier"]:.4f}' if n else '—')
    market_brier=(f'{metrics["market_brier"]:.4f}' if n else '—')
    return f"""<div class="ai5-lab">
      <div class="ai5-top"><strong>🧠 5-MINUTE · AI OUTCOME LAB</strong>
      <span>MODEL: PROTOTYPE / NOT VALIDATED</span></div>
      <div class="ai5-model"><small>LATEST INDEPENDENT AI FORECAST</small>
      <strong style="color:{color}">{x(live_label)}</strong>
      <p>{x(explanation)}<br>{x(model_caption)}</p></div>
      <div class="ai5-two">{pick_html('ORIGINAL AI PICK · NEVER ERASED',first,first_side)}
          {pick_html('CURRENT AI PICK · 2-QUOTE REVERSALS',current,current_side)}</div>
      <div class="ai5-note">{x(msg)}<br>First call: {x(age)} · Side switches: {x(sw)} ·
      Ledger: {x(record_event.get('status','WAIT'))}</div>
      <div class="ai5-paper"><small>🌸 AUTOMATIC PAPER SIMULATION · NO REAL ORDER</small>
          <div>{x(paper_note)}</div></div>
      <div class="ai5-metrics"><span>Resolved AI calls: <b>{n}</b></span>
          <span>Original accuracy: <b>{accuracy}</b></span>
          <span>Current accuracy: <b>{current_accuracy}</b></span>
          <span>First-call Brier: <b>{brier}</b></span>
          <span>Market Brier: <b>{market_brier}</b></span></div>
      <div class="ai5-disclaimer">Unvalidated statistical research. A hypothetical price is not a filled bet; P&amp;L excludes fees,
      slippage and execution limits. No wallets, orders or trading credentials are used.</div>
    </div>"""

def call_panel(tf: str, market: dict | None, quote: dict | None,
               signal: dict, now: float, entries: list[dict],
               auto_tracking: bool = True, journal_state: dict | None = None,
               previous_saved: dict | None = None, display_note: str = '',
               brti_bar_html: str = '') -> str:
    """Observed UP/DOWN tier cards. Prices ≠ AI confidence; no actual fills."""
    if market and market.get('end') is not None and market_status(market, now) == 'estimated_active':
        seconds = max(0, int(market['end'] - now))
    else:
        seconds = 0
    # v1.4: original call is immutable; current call follows logged SWITCH events.
    entry = next((r for r in entries if market and r['market_slug'] == market['slug']), None)
    if entry is None and market:
        entry = paper_call_for(DB, market['slug'])
    # The independent journal persists even if the user has not enabled
    # the (separate) hypothetical paper-entry recorder. A legacy database
    # remains readable; neither a missing quote nor a session restart erases it.
    saved = ({'original_tier':journal_state['first_tier'],
              'original_direction':journal_state['first_side'],
              'original_at':journal_state['first_at'],
              'original_strength':journal_state.get('first_strength'),
              'current_tier':journal_state['current_tier'],
              'current_direction':journal_state['current_side'],
              'current_at':journal_state['current_at'],
              'current_strength':journal_state['current_strength'],
              'switches':journal_state['switches'], 'last_event':'ORIGINAL'}
             if journal_state else
             (current_research_call(DB, market['slug']) if market else None))
    shown = change_aware_call_state(signal, saved)
    status, side, strength = shown['status'], shown['side'], shown['strength']
    headline = (f'{status} {side}' if status != 'WAIT' and side else 'WAIT · NO CALL')
    strength_label = f'{strength*100:.1f}¢' if strength is not None else '—'
    strength_kind = 'Strength at latest saved call' if shown['persisted'] else 'Current market-price dominance'
    width = round(strength*100) if strength is not None else 0
    if saved:
        first_strength = saved.get('original_strength')
        first_pct = (f'{float(first_strength)*100:.1f}% market-priced at first call'
                     if isinstance(first_strength,(int,float)) and 0 <= first_strength <= 1
                     else 'First call price not recorded')
        current_strength = saved.get('current_strength')
        current_pct = (f'{float(current_strength)*100:.1f}% market-priced at current call'
                       if isinstance(current_strength,(int,float)) and 0 <= current_strength <= 1
                       else 'Current call price not recorded')
        original_text = f"{saved['original_tier']} {saved['original_direction']}"
        current_text = f"{saved['current_tier']} {saved['current_direction']}"
        original_time = datetime.fromtimestamp(saved['original_at'], timezone.utc).strftime('%H:%M:%S UTC')
        latest_time = datetime.fromtimestamp(saved['current_at'], timezone.utc).strftime('%H:%M:%S UTC')
        pick_rows = (f'<div class="cp-picks"><div class="cp-pick"><small>ORIGINAL PICK · NEVER ERASED</small>'
                     f'<strong class="{x(saved["original_direction"].lower())}">{x(original_text)}</strong><small>{x(original_time)}</small>'
                     f'<span class="call-pct">{x(first_pct)}</span></div>'
                     f'<div class="cp-pick current"><small>CURRENT PICK</small><strong class="{x(saved["current_direction"].lower())}">{x(current_text)}</strong>'
                     f'<small>{x(latest_time)}</small><span class="call-pct">{x(current_pct)}</span></div></div>'
                     f'<div class="cp-switch-note">{saved["switches"]} confirmed side switch(es) recorded for this round.</div>')
    else:
        pick_rows = ('<div class="cp-switch-note">No saved call for this new round yet. A fresh market-price tier is needed.</div>')
    if previous_saved and not saved:
        old_time=datetime.fromtimestamp(previous_saved['first_at'], timezone.utc).strftime('%m-%d %H:%M UTC')
        pick_rows += (f'<div class="cp-switch-note cp-prior"><strong>LAST SAVED CALL · PREVIOUS ROUND</strong><br>'
                      f'{x(previous_saved["first_tier"])} {x(previous_saved["first_side"])} → '
                      f'{x(previous_saved["current_tier"])} {x(previous_saved["current_side"])} '
                      f'· {x(old_time)}<br><small>Archived history only — not a prediction for this round.</small></div>')
    if entry is not None:
        at = datetime.fromtimestamp(entry['recorded_at'], timezone.utc).strftime('%H:%M:%S UTC')
        paper_note = (f'RECORDED {entry["direction"]} · {entry["tier"]} at {at} '
                      f'· reference {entry["indicative_price"]*100:.1f}¢')
        paper_detail = 'Unfilled hypothetical entry. No order was sent. DOWN reference may not be executable.'
    elif not auto_tracking:
        paper_note = 'AUTOMATIC RESEARCH LOG DISABLED'
        paper_detail = 'Public view only; research recording is managed by the personal dashboard.'
    elif journal_state is not None and not journal_state.get('mapping_verified'):
        paper_note = 'OBSERVATION SAVED · MAPPING UNVERIFIED'
        paper_detail = 'Original/current price tiers are saved. Confirm contract YES=UP / NO=DOWN before any paper-entry record.'
    elif signal.get('status') in ('CALLED','LOCKED') and not signal.get('mapping_verified'):
        paper_note = 'CALL VISIBLE · ENTRY NOT RECORDED'
        paper_detail = 'Confirm YES=UP / NO=DOWN in the sidebar before recording paper calls.'
    elif signal.get('status') == 'HOLDING':
        paper_note = 'HOLDING · NO ENTRY'
        paper_detail = 'An automatic research call records only after reaching CALLED or LOCKED.'
    elif signal.get('status') in ('CALLED','LOCKED'):
        paper_note = 'NO ENTRY · SAFETY GATE'
        paper_detail = 'Too close to round end, missing valid data, or quote did not pass safety checks.'
    else:
        paper_note = 'WAIT · NO ENTRY'
        paper_detail = 'Fresh evidence is not sufficient to record a directional call.'
    end_ms = (int(float(market['end'])*1000) if seconds and market and market.get('end') else 0)
    slug = market['slug'] if market else 'none'
    reason = signal.get('reason', 'Waiting for live data')
    if shown['persisted']:
        reason = ('Original pick remains visible. Current pick can switch on a NEW fresh opposite CALLED/LOCKED signal. '
                  'After LOCKED, switching requires an opposite LOCKED signal.')
        if signal.get('status') == 'WAIT':
            reason += ' Live quotes unavailable: keeping the last recorded pick.'
        elif signal.get('side') and signal['side'] != side:
            reason += f' Live market currently favors {signal["side"]}; reversal has not passed the switch rules.'
    if signal.get('provisional_stale') and not shown['persisted']:
        reason = 'LAST OBSERVED / STALE — ' + reason
    if journal_state and not journal_state.get('mapping_verified'):
        reason += ' Direction mapping has not been verified; this is only an observed YES/NO price tier.'
    if display_note:
        reason = display_note + ' · ' + reason
    if market and market.get('display_only'):
        reason = 'Feed/discovery unavailable; ORIGINAL and CURRENT are saved history, NOT a fresh forecast.'
    direction_label = (side if side else '—')
    return f"""<div class="call-panel">
      <div class="cp-top"><span class="cp-title">{x(NAMES[tf])}</span>
      <span class="cp-clock" data-btc-clock data-end-ms="{end_ms}" data-btc-round="{x(slug)}">{seconds//60:02}:{seconds%60:02}</span></div>
      <div class="cp-kicker">EXPERIMENTAL MARKET-PRICE TIER · NOT MODEL CONFIDENCE</div>
      <div class="cp-main {x(status.lower() if status in ('LOCKED','CALLED','HOLDING') else 'wait')} {x(side.lower() if side in ('UP','DOWN') else 'neutral')}">{x(headline)}</div>
      <div class="cp-sub">{x(reason)}</div>
      {pick_rows}
      {brti_bar_html}
      <div class="cp-prob-row"><span>{x(strength_kind)} · {x(direction_label)} side</span>
         <strong>{x(strength_label)}</strong></div>
      <div class="cp-progress"><div style="width:{width}%"></div></div>
      <div class="cp-late"><strong>Call policy:</strong> Your ORIGINAL UP/DOWN call is always shown.
      Your CURRENT call can switch on a new confirmed opposite signal, and every switch is logged.
      If CURRENT is LOCKED, an opposite LOCKED-tier signal is required to switch.<br>
      <strong>Tier rules:</strong> HOLDING 55–69¢ · CALLED 70–89¢ · LOCKED ≥90¢ (market-priced, not model confidence).</div>
      <div class="paper-decision"><div class="pd-kicker">🌸 AUTOMATIC RESEARCH PAPER CALL · NEVER FILLED</div>
        <div class="pd-status">{x(paper_note)}</div>
        <div class="pd-explain">{x(paper_detail)}</div></div>
      <div class="cp-bottom"><span>Actual orders placed</span><strong>0 · Paper observations only</strong></div>
    </div>"""
st.markdown('\n<style>\n:root {\n  --rose:#ff69b4; --rose-light:#ffc1df; --rose-pale:#ffe3f0;\n  --text:#faf4f9; --muted:#ad9bab; --line:rgba(253,173,218,.16);\n  --panel:#19131e; --panel2:#211827;\n}\nhtml, body, [class*="css"] { font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }\n.stApp {\n  color:var(--text);\n  background:\n    radial-gradient(ellipse 55% 35% at 100% 0%,rgba(177,61,126,.19) 0%,transparent 75%),\n    radial-gradient(ellipse 42% 30% at 0% 80%,rgba(91,37,86,.17),transparent 75%),\n    #100e14;\n}\n.block-container { padding-top:2.35rem; padding-bottom:3rem; max-width:1450px; }\nheader[data-testid="stHeader"] { background:transparent; }\nsection[data-testid="stSidebar"] {\n  background:linear-gradient(175deg,#1e1520 0%,#151119 90%);\n  border-right:1px solid var(--line);\n}\nsection[data-testid="stSidebar"] .block-container { padding-top:1.8rem; }\nsection[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p { color:#d8c7d4; }\n[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {\n  background:rgba(255,106,184,.11); border-radius:11px;\n}\n[data-testid="stSidebar"] [data-baseweb="input"] { background:#2c202d; }\n[data-testid="stSidebar"] [data-baseweb="input"] > div { background:#2c202d; border-color:rgba(255,140,195,.25); }\n.stButton > button { background:#ec5b9e; color:#1a0f18; border:0; border-radius:10px; }\n.stButton > button:hover { background:#ffc1dd; color:#1a0f18; }\n[data-testid="stNotification"], [data-testid="stAlert"] { border-radius:13px; }\nhr { border-color:var(--line); }\n.stMarkdown, .stCaption { color:inherit; }\n.hero { padding:7px 0 11px; display:flex; align-items:flex-start; justify-content:space-between; gap:14px; flex-wrap:wrap; }\n.eyebrow { text-transform:uppercase; color:#ee9aca; font-size:11px; font-weight:800; letter-spacing:2.2px; margin-bottom:10px; }\n.hero-title { font-size:clamp(26px,3.1vw,39px); font-weight:780; letter-spacing:-1.6px; line-height:1.15; color:#fff4fc; }\n.hero-sub { color:#b5a1b5; margin-top:11px; font-size:13px; line-height:1.6; }\n.bitcoin-mark { font-weight:850; color:#ff85bd; }\n.pills { display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding-top:24px; }\n.pill { border:1px solid rgba(255,147,197,.20); background:#281c2a; padding:8px 12px; border-radius:999px; color:#f3bed8; font-size:11px; font-weight:700; letter-spacing:.2px; white-space:nowrap; }\n.pill .dot { display:inline-block;width:7px;height:7px;border-radius:50%;background:#ff74b5;margin-right:7px; }\n.notice { background:linear-gradient(105deg,rgba(149,64,107,.20),rgba(96,58,97,.13)); border:1px solid rgba(255,153,203,.20); border-left:3px solid #f46daa; border-radius:12px; padding:13px 17px; color:#e4bdd2; font-size:12px; line-height:1.6; margin:6px 0 24px; }\n.section-heading { display:flex;align-items:baseline;justify-content:space-between; gap:10px; margin:13px 0 15px; flex-wrap:wrap; }\n.section-heading strong { color:#fff3fa; font-weight:760; font-size:19px; letter-spacing:-.45px; }\n.section-heading small { color:#9f8c9f; font-size:12px; }\n.market-card { min-height:252px; background:linear-gradient(155deg,#211725,#19141e); border:1px solid rgba(255,143,203,.17); border-radius:19px; padding:21px 21px 18px; position:relative;overflow:hidden; box-shadow:0 8px 35px rgba(0,0,0,.11); }\n.market-card::before { content:""; position:absolute; top:0; left:16px;right:16px; height:2px; background:linear-gradient(90deg,#ff5ea7,#9a6bb9,transparent); opacity:.95; }\n.market-card.muted { opacity:.80; }\n.market-top { display:flex;justify-content:space-between;align-items:center;gap:8px; }\n.market-name { display:flex;align-items:center;gap:9px;color:#f9e9f5;font-size:14px;font-weight:750; }\n.coin-icon { display:grid;place-items:center;width:28px;height:28px;border-radius:9px;background:rgba(255,115,173,.13);color:#ff88c2;font-size:19px; }\n.status { white-space:nowrap; font-size:10px;font-weight:800;letter-spacing:.7px;border-radius:30px;padding:6px 8px;color:#f6b6d8;background:rgba(252,106,174,.10); border:1px solid rgba(255,130,191,.17); }\n.status.idle { color:#ae9cae;background:rgba(255,255,255,.035);border-color:rgba(255,255,255,.10); }\n.market-caption { color:#b8a1b5;font-size:11px;margin-top:16px; }\n.market-quote { font-size:clamp(24px,2.3vw,34px);font-weight:800;letter-spacing:-1.2px;color:#ffe6f3;margin:5px 0 0; }\n.market-quote .slash {color:#967990;font-weight:400;margin:0 6px;}\n.market-quote .cents {font-size:14px;color:#dfbad0;font-weight:550;letter-spacing:0;}\n.feed-message {font-size:11px;color:#f4b9d7;margin-top:10px;line-height:1.35;min-height:30px;}\n.feed-message.ok {color:#b7a3b4;}\n.quote-unit {font-size:11px;color:#d8adcb;font-weight:520;}\n.market-quote .empty { color:#806e80; }\n.market-bottom { display:flex;justify-content:space-between;gap:10px;margin-top:25px;border-top:1px solid rgba(255,255,255,.07);padding-top:13px; }\n.market-bottom .mini-label { color:#a893a7;font-size:10px; }\n.market-bottom .mini-value { color:#f2c2dd;font-size:14px;font-weight:700;margin-top:4px; }\n.market-slug { margin-top:14px;font-size:10px;color:#867787;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }\n.market-empty { color:#ab96a8;font-size:12px;line-height:1.55;margin:17px 0 2px; }\n.detail-shell { background:linear-gradient(145deg,rgba(31,22,34,.87),rgba(24,20,29,.90));border:1px solid rgba(255,144,199,.13); border-radius:18px;padding:20px 20px 16px;margin-bottom:15px; }\n.detail-label { color:#f0b8d4;font-size:11px;text-transform:uppercase;letter-spacing:1.5px;font-weight:750; }\n.detail-title { color:#fcedf8;font-size:22px;font-weight:760;letter-spacing:-.55px;margin-top:5px; }\n.detail-sub { color:#aa95a9;font-size:11px;margin-top:9px;overflow-wrap:anywhere; }\n.kpi-card {background:#211825;border:1px solid rgba(255,143,196,.14);border-radius:13px;padding:15px 17px;min-height:104px;}\n.kpi-label {font-size:11px;color:#b3a0b0;margin-bottom:7px;}\n.kpi-number {font-size:clamp(22px,2.1vw,30px);font-weight:770;letter-spacing:-.8px;color:#ffdbed;}\n.st-key-pink-chart, .st-key-pink-snapshot { border:1px solid rgba(255,143,196,.14);background:linear-gradient(150deg,#1b1520,#17131b);border-radius:17px;padding:17px 19px;min-height:190px; }\n.chart-title { font-size:15px;color:#fff0f8;font-weight:750;margin:0 0 4px; }\n.chart-sub { font-size:11px;color:#9e8b9e;margin-bottom:2px; }\n.chart-empty {height:270px;display:flex;align-items:center;justify-content:center;text-align:center;color:#9e8c9e;font-size:13px;line-height:1.75;}\n.sidebar-brand { font-size:19px;font-weight:780;line-height:1.3;color:#ffe0f1;margin:3px 0 8px; }\n.sidebar-kicker {font-size:10px;color:#ee9aca;letter-spacing:1.5px;font-weight:780;text-transform:uppercase;}\n.sidebar-note {color:#b8a3b6;font-size:11px;line-height:1.7;margin-top:8px;}\n.sidebar-foot {margin-top:18px;border:1px solid rgba(255,129,187,.20);border-radius:13px;padding:13px;background:rgba(255,118,180,.065);font-size:11px;color:#dec0d3;line-height:1.65;}\n.bottom-note {color:#9e8a9d;font-size:11px;line-height:1.8;margin-top:12px;}\n\n/* v1.7: persistent market-price calls + prominent AI training ribbon. */\n.training-summary { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:11px 0 9px; }\n.training-mini {padding:14px 15px;border:1px solid rgba(255,125,190,.20);border-radius:15px;\n background:linear-gradient(135deg,#251a2b,#1b1520);display:flex;flex-direction:column;gap:7px;}\n.training-mini strong{color:#ffe9f7;font-size:13px;font-weight:800;}\n.training-mini span{color:#ffb6dc;font-size:11px;font-weight:650;}\n.training-mini small{color:#bca7ba;font-size:11px;}\n.training-track{height:7px;background:#3b293c;border-radius:100px;overflow:hidden;}\n.training-track div{height:100%;background:linear-gradient(90deg,#fc64aa,#b184db);border-radius:100px;}\n.cp-prior {border:1px dashed rgba(255,156,207,.32);border-radius:10px;padding:10px;margin-top:12px;}\n.cp-prior strong {color:#ffd0e4;font-size:11px;}\n@media(max-width:950px){.training-summary{grid-template-columns:1fr;}}\n</style>\n',unsafe_allow_html=True)
st.markdown('\n<style>\n.strategy-strip {background:linear-gradient(90deg,rgba(255,98,166,.16),rgba(168,89,161,.07));border:1px solid #89526d;border-left:4px solid #ff72b8;padding:12px 16px;border-radius:10px;color:#ffd4eb;font-size:12px;letter-spacing:.5px;margin:4px 0 22px;}\n.lean-card {min-height:203px;background:linear-gradient(155deg,#241829,#19141e);border:1px solid rgba(255,150,209,.19);padding:21px;border-radius:16px;}\n.lean-header {display:flex;align-items:center;justify-content:space-between;color:#ffb2dc;font-weight:750;font-size:13px;}\n.lean-main {color:#fff0f8;font-size:clamp(19px,2vw,26px);font-weight:790;letter-spacing:-.5px;margin-top:14px;}\n.lean-sub {font-size:12px;color:#c8a9bb;margin-top:10px;line-height:1.6;min-height:37px;}\n.lean-price {font-size:11px;color:#f4c3da;padding-top:13px;border-top:1px solid rgba(255,255,255,.08);margin-top:12px;}\n.call-hint {font-size:11px;color:#c49ab1;margin-top:2px;margin-bottom:14px;}\n\n.call-panel {border:1px solid rgba(255,161,208,.25); background:linear-gradient(145deg,#251a29,#19151e);border-radius:16px; padding:18px 19px;min-height:260px;box-shadow:0 8px 22px rgba(0,0,0,.12);}\n.call-panel .cp-top {display:flex;align-items:center;justify-content:space-between;gap:9px;}\n.call-panel .cp-title {font-size:19px;font-weight:770;color:#fff0f8;}\n.call-panel .cp-clock {font-variant-numeric:tabular-nums;min-width:70px;text-align:right;font-size:23px;letter-spacing:.6px;font-weight:800;color:#ffd4e8;}\n.call-panel .cp-kicker {font-size:10px;letter-spacing:1.3px;font-weight:750;color:#bb98b0;margin-top:8px;}\n.call-panel .cp-main {font-size:24px;font-weight:820;color:#ff99c8;letter-spacing:-.4px;margin-top:6px;}\n.call-panel .cp-main.wait {color:#e1cbd9;}\n.call-panel .cp-main.locked {color:#ff93ca; text-shadow:0 0 12px rgba(255,125,196,.2);}\n.call-panel .cp-main.called {color:#ffc4e1;}\n.call-panel .cp-main.holding {color:#e8bbd1;}\n/* v1.9: directional colors reflect the stored call, not model accuracy. */\n.call-panel .cp-main.up,.cp-pick strong.up {color:#95e9b3;}\n.call-panel .cp-main.down,.cp-pick strong.down {color:#ff8d9e;}\n.call-panel .cp-main.locked.up {color:#9cffba;text-shadow:0 0 9px rgba(92,255,147,.62),0 0 24px rgba(83,233,140,.45);}\n.call-panel .cp-main.locked.down {color:#ff8b9b;text-shadow:0 0 9px rgba(255,110,133,.6),0 0 24px rgba(244,86,128,.4);}\n.cp-pick .call-pct{display:block;font-size:11px;font-weight:650;color:#dcc1d0;margin-top:7px;letter-spacing:0;}\n\n.cp-picks {display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:13px;}\n.cp-pick {padding:10px;border-radius:11px;background:rgba(255,133,191,.07);border:1px solid rgba(255,157,206,.16);}\n.cp-pick.current {background:rgba(255,138,194,.14);border-color:rgba(255,156,206,.34);}\n.cp-pick small {display:block;font-size:9px;letter-spacing:1.1px;font-weight:800;color:#d5b0c7;}\n.cp-pick strong {display:block;font-size:17px;margin-top:5px;color:#ffe1f1;}\n.cp-switch-note {font-size:11px;color:#efbfdb;margin-top:8px;}\n\n.call-panel .cp-sub {font-size:11px;color:#f7c7df;margin-top:6px;line-height:1.6;min-height:19px;}\n.call-panel .cp-caption {font-size:11px;color:#b7a3b5;margin-top:10px;}\n.cp-prob-row {display:flex;align-items:center;justify-content:space-between;font-size:11px;color:#dbc0d0;margin-top:13px;gap:12px;}\n.cp-progress {height:7px;background:#44303e;border-radius:8px;overflow:hidden;margin-top:6px;}\n.cp-progress > div {height:100%;background:linear-gradient(90deg,#d976b8,#ff9acb);border-radius:8px;}\n.cp-late {border:1px dashed rgba(255,166,215,.21);border-radius:9px;padding:11px 12px;margin-top:15px;min-height:48px;color:#bda5b7;font-size:11px;line-height:1.55;}\n.cp-bottom {border-top:1px solid rgba(255,255,255,.08);margin-top:17px;padding-top:10px;display:flex;justify-content:space-between;color:#bfabba;font-size:11px;}\n.cp-muted {color:#a38e9f;}\n.call-panel .cp-clock.round-expired {color:#9b8293;}\n\n.paper-decision {margin-top:14px;padding:12px;border-radius:11px;border:1px solid rgba(255,151,205,.22);background:rgba(255,118,187,.065);min-height:80px;}\n.paper-decision .pd-kicker{font-size:10px;color:#dcb1cd;letter-spacing:1px;font-weight:800;}\n.paper-decision .pd-status{margin-top:4px;font-size:17px;color:#ffb0d8;font-weight:800;}\n.paper-decision .pd-status.wait{color:#d3bfd0;}\n.paper-decision .pd-explain{margin-top:6px;font-size:11px;color:#beafbe;line-height:1.5;}\n@media (prefers-reduced-motion:reduce){*{transition-duration:0.01ms!important;animation-duration:0.01ms!important;}}\n</style>\n',unsafe_allow_html=True)
st.markdown('\n<style>\n.ai5-lab {border:1px solid rgba(249,139,202,.27);border-radius:19px;padding:20px 23px;\n  background:linear-gradient(130deg,#211625,#17131d);box-shadow:0 8px 32px rgba(0,0,0,.15);margin-bottom:24px;}\n.ai5-top {display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;color:#ffd7ea;font-size:13px;letter-spacing:.6px;}\n.ai5-top span{color:#e3a4c6;font-size:10px;border:1px solid #72465e;padding:5px 8px;border-radius:20px;}\n.ai5-model{margin:15px 0 15px;padding:14px 16px;border-radius:12px;background:rgba(255,109,174,.065);}\n.ai5-model small,.ai5-pick small,.ai5-paper small{display:block;color:#dbaac5;font-size:10px;letter-spacing:.8px;margin-bottom:8px;}\n.ai5-model strong{font-size:clamp(22px,2.3vw,29px);}\n.ai5-model p{font-size:11px;color:#c6afc1;line-height:1.65;margin:8px 0 0;}\n.ai5-two {display:grid;grid-template-columns:1fr 1fr;gap:12px;}\n.ai5-pick {padding:14px;border:1px solid rgba(255,153,199,.17);border-radius:12px;background:#261b2a;}\n.ai5-pick strong{display:block;font-size:19px;}\n.ai5-note{font-size:11px;color:#d9c0d0;line-height:1.8;margin:12px 0;}\n.ai5-paper {border:1px solid rgba(255,159,207,.27);border-radius:12px;padding:14px;background:#301e2b;color:#ffe1ef;font-size:12px;}\n.ai5-metrics {display:flex;gap:16px;flex-wrap:wrap;margin-top:16px;color:#d1aabe;font-size:11px;}\n.ai5-metrics b{color:#ffdbec;}\n.ai5-disclaimer{font-size:10px;color:#aa91a5;margin-top:12px;line-height:1.55;}\n@media(max-width:640px){.ai5-two{grid-template-columns:1fr}}\n</style>\n',unsafe_allow_html=True)
st.markdown("<style>\n/* Blossom Bot floral polish; presentation only. */\n.stApp {background:\n  radial-gradient(ellipse 53% 35% at 100% 0%,rgba(239,111,174,.18),transparent 80%),\n  radial-gradient(ellipse 42% 30% at 0% 80%,rgba(126,79,147,.16),transparent 80%),\n  #110e16;}\n.hero-title {color:#ffe3f0;text-shadow:0 0 24px rgba(248,132,190,.13)}\n.hero::after{content:'✿ ❀';align-self:center;font-size:26px;letter-spacing:9px;\n  color:rgba(255,158,205,.42);transform:rotate(-12deg);pointer-events:none}\n.market-card:before,.call-panel:before{background:linear-gradient(90deg,#f67eb6,#c5a0e0,transparent)}\n.section-heading strong{color:#ffe5f2}\n.sidebar-brand{color:#ffd4e8;font-size:21px}\n.sidebar-brand::after{content:'  ✿';color:#fa9bcc;font-size:18px;opacity:.76}\n.bb-row:hover{border-color:rgba(255,166,205,.25)}\n@media(max-width:800px){.hero::after{display:none}}\n</style>",unsafe_allow_html=True)
from blossom_ui import CSS as BLOSSOM_POLISHED_CSS, compact_call
from public_dashboard_panels import render_paper, render_results
st.html(BLOSSOM_POLISHED_CSS)
st.markdown('<div class="hero"><div><div class="eyebrow">POLYMARKET US / MARKET INTELLIGENCE</div><div class="hero-title"><span class="bitcoin-mark">🌸</span> <span style="color:#ff8cc5">Blossom</span> Bot</div><div class="hero-sub">Bitcoin market signals and paper research, shared read only.</div></div><div class="pills"><span class="pill">US MARKET FEEDS</span><span class="pill">PUBLIC VIEW · READ ONLY</span></div></div><div class="strategy-strip">Live market observations · Verified outcomes · Public paper research</div><div class="notice"><strong>Research dashboard only.</strong> HOLDING/CALLED/LOCKED measure market price, NOT AI confidence. Quotes are observations, not guaranteed executable prices. Public visitors cannot change bot settings or place orders.</div>',unsafe_allow_html=True)

@st.fragment(run_every='30s')
def training_summary_at_top():
    try:
        live=call_snapshot().get('training_summary')
        if live:
            for tf,row in live.items():
                st.write(f"**{NAMES[tf]}** · {row.get('rounds_with_features',0)} usable rounds · {str(row.get('status','UNKNOWN')).replace('_',' ')}")
                if row.get('holdout_brier') is not None:
                    st.caption(f"Held-out Brier: model {row['holdout_brier']}; market {row.get('market_brier')} · lower is better")
            st.caption('Current training metadata from the personal research collector. Prototype status is not trading validation.')
            return
    except Exception:
        pass
    # Mirror the private admin's training ribbon; never read credentials/models.
    try:
        snap=read_snapshot(DB)
        models=public_training_status(MODELS)
        st.markdown('<div class="section-public">🧠 AI Training Progress</div>',unsafe_allow_html=True)
        st.markdown(training_tiles(models,snap.get('counts',{})),unsafe_allow_html=True)
        st.caption('Historical training snapshot, not live cloud retraining. 36 rounds is a prototype threshold, not proof of accuracy. Public UP/DOWN cards use market prices, not this unvalidated AI.')
        model=models.get('5m',{})
        if isinstance(model.get('holdout_brier'),(int,float)) and isinstance(model.get('market_brier'),(int,float)):
            st.caption(f"5m held-out Brier score: model {model['holdout_brier']:.5f}; market {model['market_brier']:.5f} (lower is better). No demonstrated model advantage; AI promotion disabled.")
    except Exception:
        st.info('Training summary temporarily unavailable. Calls can still be viewed below.')


PUBLIC_CLOCK_JS = "\n<script>\n(() => {\n  // The server time is anchored exactly ONCE. Re-anchoring during 5-second\n  // Streamlit rerenders previously caused clocks to gain/lose a second.\n  const KEY = '__blossomPublicClockV1';\n  const initialServerMs = __SERVER_MILLISECONDS__;\n  if (!window[KEY]) {\n    window[KEY] = {\n      serverAnchor: initialServerMs,\n      perfAnchor: performance.now(),\n      byRound: {},\n      timer: null\n    };\n  }\n  const state = window[KEY];\n  const tick = () => {\n    // performance.now() advances monotonically; never reset its time anchor.\n    const estimatedNow = state.serverAnchor + (performance.now() - state.perfAnchor);\n    document.querySelectorAll('[data-btc-clock]').forEach((element) => {\n      const end = Number(element.getAttribute('data-end-ms'));\n      const round = element.getAttribute('data-btc-round') || String(end);\n      if (!Number.isFinite(end) || end <= 0) {\n        element.textContent = '--:--';\n        return;\n      }\n      const rawRemaining = Math.max(0, Math.ceil((end - estimatedNow) / 1000));\n      // A rerender or system clock adjustment must never increase an ongoing\n      // round's countdown. A NEW slug gets a new countdown automatically.\n      const previous = state.byRound[round];\n      const remaining = previous === undefined ? rawRemaining : Math.min(previous, rawRemaining);\n      state.byRound[round] = remaining;\n      const minutes = String(Math.floor(remaining / 60)).padStart(2, '0');\n      const seconds = String(remaining % 60).padStart(2, '0');\n      element.textContent = `${minutes}:${seconds}`;\n      element.classList.toggle('round-expired', remaining === 0);\n      element.title = remaining === 0 ? 'Estimated window ended; awaiting next verified market' : 'Estimated time remaining; not official cutoff';\n    });\n    // Keep only a bounded set of round states for long-running sessions.\n    const keys = Object.keys(state.byRound);\n    if (keys.length > 40) for (const k of keys.slice(0, keys.length - 20)) delete state.byRound[k];\n  };\n  if (!state.timer) state.timer = window.setInterval(tick, 150);\n  tick();\n})();\n</script>\n"

def animate_public_countdowns(now):
    st.html(PUBLIC_CLOCK_JS.replace('__SERVER_MILLISECONDS__',str(round(now*1000))),unsafe_allow_javascript=True)

@st.fragment(run_every='8s')
def live_view():
    try:
        snapshot=call_snapshot()
    except Exception:
        st.warning('Personal dashboard feed offline or not configured. Public calls are paused; no independent or previous-round signal is substituted.')
        return
    if not snapshot['db_available']:
        st.info('Waiting for the private bot database. Start your normal collector on this PC; this viewer never creates or changes the database.')
        return
    st.markdown('<div class="section-heading"><strong>Live UP / DOWN calls · all three markets</strong><small>Experimental market-price tiers, not a trained model</small></div>',unsafe_allow_html=True)
    columns=st.columns(3,gap='medium')
    for tf,col in zip(NAMES,columns):
        with col:
            entry=snapshot['markets'][tf]; call=entry.get('call'); current=bool(call and call.get('is_current'))
            signal={'status':'WAIT','reason':'Waiting for a fresh two-sided quote','mapping_verified':bool(call and call.get('mapping_verified'))}
            if entry.get('quote',{} ) and entry['quote'].get('fresh'):
                signal['reason']='Shared personal-dashboard saved call; current strength requires fresh quotes.'
            st.markdown(compact_call(tf,entry.get('round'),call if current else None,public_quote(entry),snapshot['time'],entry.get('reference')),unsafe_allow_html=True)
            with st.expander('Call details · '+NAMES[tf],expanded=False):
                st.markdown(call_panel(tf,entry.get('round'),public_quote(entry),signal,snapshot['time'],[],False,
                    journal_state=call if current else None,previous_saved=call if call and not current else None,
                    brti_bar_html=reference_bar(entry.get('reference') or {})),unsafe_allow_html=True)
                st.info('Shared saved call · '+('fresh two-sided quote' if (entry.get('quote') or {}).get('fresh') else 'fresh two-sided quote unavailable; saved pick retained'))
                st.markdown(model_forecast_tile(tf,{'status':'WAIT','reason':'No verified live model forecast supplied'}),unsafe_allow_html=True)
    render_paper(snapshot.get('paper_summary'),snapshot['time'])
    with st.expander('Independent AI lab · research only',expanded=False):
        st.markdown('<div class="section-heading"><strong>🌸 Five-minute AI forecast & paper lab</strong><small>Independent outcome model · not market-price tiers</small></div>',unsafe_allow_html=True)
        # The shared feed does not publish a validated independent AI forecast.
        st.markdown(render_ai5m_lab({'status':'WAIT','reason':'No current independent AI forecast supplied by the shared feed'},None,None,{'status':'READ ONLY'},True,False,snapshot['markets']['5m'].get('round'),None,snapshot['time'],{'resolved':0}),unsafe_allow_html=True)
        st.caption('Live forecast and paper metrics are unavailable in the shared feed; no historical score is presented as current.')
    st.caption('Shared call feed · same saved journal as your personal dashboard · source '+fmt_time_seconds(snapshot.get('source_time',snapshot['time'])))
    animate_public_countdowns(snapshot['time'])


@st.fragment(run_every='20s')
def market_details_view():
    # More expensive chart refreshes independently of live call cards/timers.
    try:
        snapshot=call_snapshot()
    except Exception:
        st.info('Local market chart temporarily unavailable.')
        return
    st.markdown(f'<div class="section-public">🌸 {escape(NAMES[selected_tf])} · Market details</div>',unsafe_allow_html=True)
    selected_round=snapshot['markets'][selected_tf].get('round')
    if selected_round:
        # Exact slug only. Local SELECT never changes saved prices or calls.
        try:
            history=read_quote_timeline(DB,selected_round.get('slug'),snapshot['time'])
        except Exception:
            history=[]
        if history:
            try:
                import pandas as pd
                import plotly.graph_objects as go
                frame=pd.DataFrame(history)
                utc=pd.to_datetime(frame['recorded_at'],unit='s',utc=True)
                fig=go.Figure()
                for col,title,color in [('bid','YES bid','#f478b5'),('ask','YES ask','#b692da'),('last_trade','Last trade','#f1d1df')]:
                    if frame[col].notna().any():
                        fig.add_trace(go.Scatter(x=utc,y=frame[col],mode='lines',name=title,
                            connectgaps=False,line={'color':color,'width':2.2},
                            hovertemplate='%{x|%H:%M:%S} UTC · %{y:.1f}¢<extra>'+title+'</extra>'))
                fig.update_layout(height=300,margin={'l':8,'r':8,'t':15,'b':15},
                    paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
                    font={'color':'#e4c5d8','size':11},yaxis={'title':'Cents per contract','range':[0,100],
                    'gridcolor':'rgba(255,210,233,.08)'},
                    xaxis={'title':'UTC time','gridcolor':'rgba(255,210,233,.06)'},
                    legend={'orientation':'h','y':1.18})
                st.plotly_chart(fig,width="stretch",config={'displayModeBar':False})
            except ImportError:
                st.caption(f'{len(history)} saved quote observations available. Chart requires pandas and Plotly.')
        else:
            st.info('No local quote history for the current contract yet. Your private collector provides these observations.')
    else:
        st.info('No current round identified; no old round is presented as live.')


@st.fragment(run_every='10s')
def settled_results_view():
    try:
        live=call_snapshot()
        if 'verified_results' in live:
            render_results(live['verified_results'])
            return
    except Exception:
        pass
    st.caption('Historical saved results below; live verified-results feed unavailable.')
    # Independent refresh: a temporary market-feed error must not prevent the
    # past-settlement board from updating. Never writes to the private DB.
    st.markdown('<div class="section-public">🌸 Last 20 verified calls</div>', unsafe_allow_html=True)
    try:
        st.markdown(render_scoreboard(DB, mode='rolling'), unsafe_allow_html=True)
    except Exception as exc:
        st.warning('Settled-call history is temporarily unavailable. Please check the AI collector and database schema.')
    st.caption('Reads permanently stored grades every 10 seconds. The LOCAL BLOSSOM_GRADE_SYNC process saves results after the research collector records official settlements. It never grades unverified markets or changes original picks.')




@st.fragment(run_every='20s')
def last_5m_audit():
    with st.expander('🔎 Inspect the last 5-minute calls and official results'):
        st.caption('Rows below are verified, completed rounds only. Market-price calls and actual independent AI forecasts are separate; neither is a guaranteed prediction.')
        for source,label in [('ai','Independent AI'),('market','Market-price tier')]:
            records=settled_original_calls(DB,'5m',source=source)[-10:][::-1]
            st.markdown(f'**{label}**')
            if not records:
                st.caption('No eligible completed calls in this category yet.')
                continue
            rows=[]
            for r in records:
                rows.append({'Round ended (UTC)':fmt_time(r['round_end']),
                            'Original pick':r['pick'],
                            'Actual result':r['outcome'],
                            'Result':'✅ Correct' if r['correct'] else '❌ Wrong'})
            st.dataframe(rows,hide_index=True,width="stretch")


@st.fragment(run_every='8s')
def public_terminal():
    try: snapshot=call_snapshot()
    except Exception:
        st.warning('Shared feed offline; terminal paused.')
        return
    st.html('<style>.st-key-blossom_terminal{background:#0c0e10;border:1px solid #30343b;border-radius:18px;padding:20px;color:#eee}.bt-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.bt-head b{font-size:24px}.bt-head span{color:#42d685;font-size:11px;letter-spacing:2px}.bt-markets{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:12px 0}.bt-card{background:#202226;border:1px solid #35383e;border-radius:14px;padding:16px}.bt-card strong{display:block;margin-bottom:10px}.bt-up{color:#36d777}.bt-down{color:#ff625f}.bt-note{color:#b8a783;background:#241e10;padding:10px 14px;border-radius:8px;font-size:12px}@media(max-width:600px){.bt-markets{grid-template-columns:1fr}}</style>')
    with st.container(key='blossom_terminal'):
        st.html('<div class="bt-head"><b>Blossom <span>TERMINAL</span></b><span>BTC / UP &amp; DOWN</span></div><div class="bt-note">Research mode · Original calls and official results · Model remains experimental</div>')
        cards=[]
        for tf,e in snapshot['markets'].items():
            q=e.get('quote') or {}; fresh=q.get('fresh') and q.get('valid'); m=e.get('round')
            left=max(0,int(m['end']-snapshot['time'])) if m else 0
            up=cents(q.get('ask')) if fresh else '—'; down=cents(1-q['bid']) if fresh else '—'
            cards.append(f'<div class="bt-card"><strong>{tf} <span style="float:right" data-btc-clock data-end-ms="{int(m['end']*1000) if m else 0}" data-btc-round="{escape(m['slug']) if m else tf}">{left//60:02}:{left%60:02}</span></strong><b class="bt-up">UP {up}</b> &nbsp; <b class="bt-down">DOWN {down}</b><small>{"Fresh quote · ask prices" if fresh else "Waiting for fresh quotes"}</small></div>')
        st.html('<div class="bt-markets">'+''.join(cards)+'</div>')
        animate_public_countdowns(snapshot['time'])
        tf=st.segmented_control('Market window',['5m','15m','1h'],default='5m',key='public_terminal_tf') or '5m'
        ref=snapshot['markets'][tf].get('reference') or {}
        fmt=lambda v: f'${v:,.2f}' if isinstance(v,(int,float)) else '—'
        with st.container(horizontal=True):
            st.metric('BRTI',fmt(ref.get('price')),border=True)
            st.metric('Pre-open 60s average',fmt(ref.get('strike')),border=True)
            delta=ref['price']-ref['strike'] if isinstance(ref.get('price'),(int,float)) and isinstance(ref.get('strike'),(int,float)) else None
            st.metric('Distance from reference',fmt(delta),border=True)
            st.metric('Model P(Up)','Waiting',border=True)
        st.caption('Live BRTI history and model probabilities are not included in this public feed. No substitute data is invented.')
        st.markdown(reference_bar(ref),unsafe_allow_html=True)

# Same navigation as the personal dashboard, with Live Trading omitted.
dashboard_tab,terminal_tab,details_tab=st.tabs(['Dashboard','Trading terminal','Research & details'],on_change='rerun')
with dashboard_tab:
    live_view()
    with st.expander('Training progress & model evaluation',expanded=False):
        training_summary_at_top()
    settled_results_view()
with terminal_tab:
    if terminal_tab.open: public_terminal()
with details_tab:
    if details_tab.open:
        st.markdown('<div class="section-heading"><strong>Market overview</strong><small>Shared personal-dashboard observations</small></div>',unsafe_allow_html=True)
        try:
            snap=call_snapshot()
            for tf,col in zip(NAMES,st.columns(3)):
                with col: st.markdown(market_tile(tf,snap['markets'][tf].get('round'),public_quote(snap['markets'][tf]),snap['time'],None),unsafe_allow_html=True)
        except Exception: st.warning('Shared market feed unavailable.')
        market_details_view()
        last_5m_audit()
