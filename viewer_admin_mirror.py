"""Presentation-only components matching the private Blossom Bot's visual hierarchy.

No Streamlit imports, database writes, API calls, credentials, or trading features.
Values passed by the read-only viewer are escaped before insertion into HTML.
"""
from __future__ import annotations
from datetime import datetime, timezone
from html import escape
from math import isfinite

TIMEFRAMES = ('5m','15m','1h')
LABELS = {'5m':'5 MIN','15m':'15 MIN','1h':'1 HOUR'}

MIRROR_CSS = r'''<style>
:root{--blossom-pink:#ff83bc;--blossom-violet:#b88cce;--blossom-border:rgba(255,160,204,.25)}
/* Match the structure and spacing of the private Blossom Studio. */
.block-container{max-width:1440px!important;padding:2rem clamp(.75rem,3.5vw,3rem) 4rem!important}
section[data-testid="stSidebar"]{background:linear-gradient(175deg,rgba(31,20,34,.97),rgba(19,15,26,.97))!important;border-right:1px solid var(--blossom-border)!important}
section[data-testid="stSidebar"] .block-container{padding:1.75rem 1rem!important}
section[data-testid="stSidebar"] label,section[data-testid="stSidebar"] p{color:#e8c7dd}
.sidebar-kicker{color:#ffa8d2;font-size:10px;font-weight:850;letter-spacing:2px}
.sidebar-brand{color:#ffe0f0;font-size:23px;font-weight:880;margin:10px 0 5px}
.sidebar-note{font-size:11px;color:#bda0b9;line-height:1.7}
.sidebar-foot{padding:13px 14px;background:rgba(135,70,110,.17);border:1px solid rgba(246,154,201,.24);border-radius:12px;color:#edc7dc;font-size:11px;line-height:1.65}
.sidebar-header{font-size:12px;color:#ffe6f3;font-weight:750;margin:14px 0 4px}
.hero-public{padding:6px 0 15px!important}
.hero-title-public{font-size:clamp(30px,3.5vw,44px)!important}
.viewer-chip{color:#ffd8ea!important}
.strategy-strip-public{margin:3px 0 14px;background:linear-gradient(90deg,rgba(141,62,104,.29),rgba(59,31,62,.36));border:1px solid rgba(255,165,213,.26);border-left:4px solid #f875b4;border-radius:11px;padding:13px 17px;font-size:11px;color:#ffc8e2;font-weight:800;letter-spacing:.25px}
.notice-public{margin:9px 0 21px!important}
.section-public{margin:20px 0 12px!important;font-size:19px!important;color:#ffe4f1!important}
.section-lead{font-size:11px;color:#b79ab1;margin-top:-7px;margin-bottom:12px}
.market-overview-card{position:relative;overflow:hidden;background:linear-gradient(152deg,rgba(42,24,44,.93),rgba(23,17,31,.95));border:1px solid var(--blossom-border);border-radius:17px;padding:17px 18px;min-height:208px;box-shadow:0 12px 32px rgba(12,4,15,.17);margin-bottom:5px}
.market-overview-card:before{content:'';position:absolute;left:15px;right:15px;top:0;height:2px;background:linear-gradient(90deg,#f26fb2,#ae8bc6,transparent)}
.mo-top{display:flex;justify-content:space-between;align-items:center;gap:10px}
.mo-name{display:flex;gap:8px;align-items:center;color:#ffeaf4;font-size:13px;font-weight:800}
.mo-icon{border-radius:9px;padding:5px 8px;background:rgba(246,122,177,.15);color:#ff93c4;font-size:17px}
.mo-badge{white-space:nowrap;font-size:9px;font-weight:850;color:#f4b0d5;padding:6px 8px;border:1px solid rgba(246,140,194,.21);background:rgba(236,113,175,.12);border-radius:99px}
.mo-badge.live{color:#b0edc3;border-color:rgba(139,220,167,.37);background:rgba(97,183,124,.11)}
.mo-value{font-size:clamp(23px,2.5vw,32px);font-weight:850;color:#ffe6f4;letter-spacing:-.8px;margin-top:8px;font-variant-numeric:tabular-nums}
.mo-hint{margin-top:15px;font-size:10px;color:#c8a8c1;line-height:1.55;min-height:18px}
.mo-footer{display:flex;justify-content:space-between;gap:8px;margin-top:15px;padding-top:13px;border-top:1px solid rgba(255,220,237,.11);font-size:10px;color:#a98da7;flex-wrap:wrap}
.mo-footer b{color:#ffe2ee;font-size:11px}
.training-summary-public{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:12px}
.training-tile-public{background:linear-gradient(140deg,rgba(46,27,48,.93),rgba(29,21,35,.93));border:1px solid var(--blossom-border);border-radius:14px;padding:15px 15px 13px;min-width:0}
.tt-top{display:flex;justify-content:space-between;gap:7px;align-items:center;color:#ffe6f4;font-size:12px;font-weight:850}
.tt-status{color:#feb0d5;font-size:10px;font-weight:750;max-width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tt-bar{background:rgba(255,215,235,.12);height:7px;border-radius:99px;overflow:hidden;margin:13px 0 8px}
.tt-fill{height:100%;background:linear-gradient(90deg,#ef6cb0,#bf96d7);border-radius:99px}
.tt-footer{color:#d4afc7;font-size:10px;line-height:1.55}
.public-card{border-radius:17px!important;min-height:255px!important}
.public-card:before{content:'✿'!important}
.public-call{margin-top:15px!important}
.public-card .public-picks{margin-top:15px!important}
.viewer-call-guide{background:rgba(234,127,183,.08);border:1px solid rgba(243,139,190,.19);border-radius:12px;padding:12px 15px;color:#e6bbd3;font-size:11px;line-height:1.6}
.viewer-tabs-note{font-size:11px;color:#c6a8bf;margin:3px 0 12px}
.viewer-divider{height:1px;background:rgba(255,207,226,.13);margin:25px 0 10px}
.public-ref{margin-top:4px}
.viewer-muted{color:#c3a6bd;font-size:11px;line-height:1.6}
.viewer-fresh{color:#96e7b5}
.viewer-stale{color:#f8bc85}
.viewer-flower-badge{font-weight:800;font-size:10px;color:#ffc1df}
.viewer-footer-note{text-align:center;color:#a992a8;font-size:11px;padding:20px 0 8px}
@media(max-width:900px){.training-summary-public{grid-template-columns:1fr}.market-overview-card{min-height:185px}}
@media(max-width:640px){
.block-container{padding:1.05rem .75rem 3rem!important}
.market-overview-card{min-height:0;padding:15px!important}
.public-card{min-height:0!important}
.training-summary-public{gap:8px}
.strategy-strip-public{font-size:10px;padding:12px}
.hero-title-public{font-size:32px!important}
.mo-value{font-size:26px}
}
@media(prefers-reduced-motion:reduce){.tt-fill{transition:none}}
</style>'''


def _value(value) -> str:
    return escape(str(value),quote=True)


def _number(v) -> bool:
    return isinstance(v,(int,float)) and not isinstance(v,bool) and isfinite(float(v))


def price_cents(v) -> str:
    return f'{float(v)*100:.1f}¢' if _number(v) and 0<=v<=1 else '—'


def utc_time(ts) -> str:
    if not _number(ts): return '—'
    return datetime.fromtimestamp(float(ts),timezone.utc).strftime('%H:%M:%S UTC')


def market_overview_card(tf: str, entry: dict, now:float) -> str:
    """Only show quotes as LIVE when freshness and two-sided validity agree."""
    if tf not in TIMEFRAMES: raise ValueError('Invalid timeframe')
    market=entry.get('round') or {}
    q=entry.get('quote') or {}
    usable=bool(q.get('fresh') and q.get('valid'))
    valid=bool(q.get('valid'))
    label='FRESH' if usable else ('STALE' if valid else 'NO LIVE QUOTE')
    value=f'{price_cents(q.get("bid"))} <span style="color:#ac8b9d">/</span> {price_cents(q.get("ask"))}' if valid else '—'
    end=market.get('end')
    end_text=utc_time(end)
    seen=q.get('recorded_at') or entry.get('last_quote_seen')
    seen_text=utc_time(seen)
    slug=market.get('slug')
    msg=('Two-sided observed YES quote (not guaranteed executable).' if usable else
        'Last known quote — not live.' if valid else
        'Waiting for valid bid and ask prices.')
    if not slug:
        msg='No currently observed contract identified.'
    last=price_cents(q.get('last_trade')) if _number(q.get('last_trade')) else '—'
    return (f'<article class="market-overview-card"><div class="mo-top"><div class="mo-name"><span class="mo-icon">₿</span>{LABELS[tf]}</div>'
            f'<span class="mo-badge {"live" if usable else ""}">{_value(label)}</span></div>'
            f'<div class="public-caption" style="margin-top:15px">YES BID / ASK · 0–100¢</div>'
            f'<div class="mo-value">{value}</div>'
            f'<div class="mo-hint">{_value(msg)}</div>'
            f'<div class="mo-footer"><span>LAST TRADE<br><b>{last}</b></span>'
            f'<span>EXPECTED END<br><b>{_value(end_text)}</b></span>'
            f'<span>LAST SEEN<br><b>{_value(seen_text)}</b></span></div></article>')


def training_tiles(models:dict, counts:dict, goal:int=36) -> str:
    parts=['<div class="training-summary-public">']
    for tf in TIMEFRAMES:
        state=models.get(tf,{}) or {}
        n=state.get('rounds_with_features')
        if not isinstance(n,int) or n<0: n=None
        status=str(state.get('status','COLLECTING')).replace('_',' ')
        width=max(0,min(100,int((n or 0)*100/goal)))
        details=(f'{n}/{goal} usable rounds' if n is not None else 'Training count not available')
        settled=counts.get(tf)
        if isinstance(settled,int) and settled>=0:
            details+=f' · {settled} settled'
        parts.append(f'<article class="training-tile-public"><div class="tt-top"><span>{LABELS[tf]}</span>'
                     f'<span class="tt-status">{_value(status)}</span></div><div class="tt-bar">'
                     f'<div class="tt-fill" style="width:{width}%"></div></div><div class="tt-footer">'
                     f'{_value(details)}</div></article>')
    parts.append('</div>')
    return ''.join(parts)
