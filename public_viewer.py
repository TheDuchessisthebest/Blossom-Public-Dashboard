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

st.set_page_config(page_title='🌸 Blossom Bot · Live Viewer',page_icon='🌸',layout='wide',initial_sidebar_state='expanded')

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
        title=f'{tier} {side}'
        note='Original pick preserved; current pick can change in the private bot.'
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


st.markdown('''<div class="hero-public"><div><div class="eyebrow-public">POLYMARKET US / MARKET INTELLIGENCE</div>
<div class="hero-title-public">🌸 <em>Blossom</em> Bot</div><div class="hero-desc-public">Your flower-themed research garden for Bitcoin’s 5-minute, 15-minute and 1-hour markets.</div></div>
<div class="viewer-chip">◉ PUBLIC VIEW · READ ONLY</div></div>
<div class="strategy-strip-public">🌸 BLOSSOM BOT · v2.8 &nbsp; • &nbsp; Read-only calls &nbsp; • &nbsp; BRTI movement &nbsp; • &nbsp; Verified results &nbsp; • &nbsp; No orders</div>
<div class="notice-public">🌷 This page is a <b>view-only companion</b>. You cannot change bot settings, train models, make paper entries, or place bets here. UP/DOWN market-price calls are <b>not</b> independently validated AI forecasts. All prices and predictions are experimental.</div>''',unsafe_allow_html=True)

@st.fragment(run_every='30s')
def training_summary_at_top():
    # Mirror the private admin's training ribbon; never read credentials/models.
    try:
        snap=read_snapshot(DB)
        models=public_training_status(MODELS)
        st.markdown('<div class="section-public">🧠 AI Training Progress</div>',unsafe_allow_html=True)
        st.markdown(training_tiles(models,snap.get('counts',{})),unsafe_allow_html=True)
        st.caption('Experimental models · 36 rounds is a prototype threshold, not proof of accuracy.')
    except Exception:
        st.info('Training summary temporarily unavailable. Calls can still be viewed below.')

training_summary_at_top()

# Rendered outside the eight-second market-data fragment. This iframe stays
# mounted while market prices and saved calls are refreshed independently.
st.markdown('<div class="section-public">🌸 Live round countdowns</div>',unsafe_allow_html=True)
try:
    if hasattr(st, 'iframe'):
        st.iframe(timer_html(), height=155, width='stretch')
    else:
        import streamlit.components.v1 as components
        components.html(timer_html(), height=155, scrolling=False)
except Exception:
    st.caption('Countdown display is unavailable in this browser. Market data is available below.')
st.caption('Countdowns are synchronized to the Windows host clock at page load (not the phone clock) and show scheduled UTC boundaries, not verified contract settlement times. Live-market verification appears below.')



@st.fragment(run_every='8s')
def live_view():
    try:
        snapshot=read_snapshot(DB)
    except Exception:
        st.warning('The live local data feed is temporarily unavailable. The private bot may still be collecting data.')
        return
    if not snapshot['db_available']:
        st.info('Waiting for the private bot database. Start your normal collector on this PC; this viewer never creates or changes the database.')
        return
    timestamp=fmt_time(snapshot['time'])
    st.markdown(f'<div class="section-public">✿ Current calls <span style="float:right;color:#b28ca9;font-size:11px;font-weight:500">Snapshot {escape(timestamp)} · updates about every 8 seconds</span></div>',unsafe_allow_html=True)
    columns=st.columns(3,gap='medium')
    for tf,col in zip(NAMES,columns):
        with col:
            st.markdown(call_card(tf,snapshot['markets'][tf],snapshot['time']),unsafe_allow_html=True)
    st.markdown('<div class="section-public">🌷 Market overview</div>',unsafe_allow_html=True)
    st.markdown('<div class="section-lead">Same 0–100¢ bid/ask cards as the private studio. Prices are labeled stale when old.</div>',unsafe_allow_html=True)
    over=st.columns(3,gap='medium')
    for tf,col in zip(NAMES,over):
        with col:
            st.markdown(market_overview_card(tf,snapshot['markets'][tf],snapshot['time']),unsafe_allow_html=True)
    st.markdown('<div class="section-public">🌿 Live BTC movement</div>',unsafe_allow_html=True)
    st.caption('Based on locally recorded BRTI seconds. Missing or stale reference data is never filled with an invented strike.')
    tabs=st.tabs(['5 MIN','15 MIN','1 HOUR'])
    for tf,tab in zip(NAMES,tabs):
        with tab:
            st.markdown(reference_bar(snapshot['markets'][tf]['reference']),unsafe_allow_html=True)
    st.markdown('<div class="section-public">🧠 Independent AI · 5-minute model</div>',unsafe_allow_html=True)
    st.markdown(ai_card(snapshot['ai']),unsafe_allow_html=True)
    st.markdown('<div class="viewer-footer-note">🌸 Data and calls are read from local read-only files. No trading APIs or admin settings are available in this viewer.</div>',unsafe_allow_html=True)


@st.fragment(run_every='20s')
def market_details_view():
    # More expensive chart refreshes independently of live call cards/timers.
    try:
        snapshot=read_snapshot(DB)
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
    # Independent refresh: a temporary market-feed error must not prevent the
    # past-settlement board from updating. Never writes to the private DB.
    st.markdown('<div class="section-public">🌸 Last 20 verified calls</div>', unsafe_allow_html=True)
    try:
        st.markdown(render_scoreboard(DB, mode='rolling'), unsafe_allow_html=True)
    except Exception as exc:
        st.warning('Settled-call history is temporarily unavailable. Please check the AI collector and database schema.')
    st.caption('Reads permanently stored grades every 10 seconds. The LOCAL BLOSSOM_GRADE_SYNC process saves results after the research collector records official settlements. It never grades unverified markets or changes original picks.')


live_view()
market_details_view()
settled_results_view()


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

last_5m_audit()
