"""Shared presentation only: no accounts, orders, settings or database access."""
from html import escape
import math

CSS='''<style>
:root{--bp-pink:#f08bbd;--bp-line:rgba(240,139,189,.19);--bp-muted:#b9a5b5}
.hero,.hero-public{padding:8px 0 18px!important;gap:12px!important}
.hero-title,.hero-title-public{font-size:clamp(27px,4vw,38px)!important;letter-spacing:-1.3px!important;line-height:1.14!important}
.hero-sub,.hero-desc-public{max-width:620px;font-size:13px!important;line-height:1.6!important}
.hero::after{opacity:.25!important}.eyebrow,.eyebrow-public{font-size:10px!important;letter-spacing:1.8px!important}
.strategy-strip{padding:8px 12px!important;border-radius:10px!important;font-size:11px!important;line-height:1.6!important;opacity:.8}
.notice,.notice-public{padding:12px 15px!important;font-size:12px!important;line-height:1.6!important;margin:10px 0 20px!important}
.section-heading{margin:20px 0 12px!important}.section-heading strong{font-size:18px!important}
.training-mini{box-shadow:none!important}.blossom-falling-petal{opacity:.14!important}
.blossom-falling-petal:nth-child(n+7){display:none!important}
.bp-call{border:1px solid var(--bp-line);border-radius:17px;padding:18px 18px 14px;background:linear-gradient(145deg,rgba(48,28,45,.95),rgba(23,18,28,.96));min-height:220px;margin-bottom:7px;box-sizing:border-box}
.bp-top{display:flex;align-items:center;justify-content:space-between;gap:8px;color:#edcee1;font-size:12px;font-weight:700}
.bp-chip{font-size:9px;letter-spacing:.7px;border:1px solid var(--bp-line);border-radius:30px;padding:5px 8px;color:#cdb3c5;white-space:nowrap}
.bp-side{font-size:34px;font-weight:800;letter-spacing:-1px;line-height:1.15;margin:15px 0 7px;color:#d4bdce}
.bp-up{color:#93dfb3}.bp-down{color:#ff9da9}.bp-small{font-size:11px;color:var(--bp-muted);line-height:1.6}
.bp-picks{display:flex;gap:20px;border-top:1px solid var(--bp-line);padding-top:11px;margin-top:13px;font-size:11px;color:var(--bp-muted)}
.bp-picks b{display:block;font-size:13px;color:#f2dce9;margin-top:3px}
.bp-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0 14px}
.bp-metric{border:1px solid var(--bp-line);border-radius:12px;padding:13px 14px;background:rgba(45,29,43,.55);min-width:0}
.bp-metric span{display:block;font-size:11px;color:var(--bp-muted);line-height:1.4;margin-bottom:8px}
.bp-metric b{font-size:25px;letter-spacing:-.7px;color:#ffe5f2;font-weight:700;white-space:nowrap}
.bp-line{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:8px 0;font-size:12px;color:#cdb4c6;line-height:1.6}
.bp-status{display:inline-flex;gap:7px;align-items:center;border-radius:30px;padding:7px 11px;background:#18362b;color:#a2dfbd;border:1px solid #315a44;font-size:11px;font-weight:700;letter-spacing:.3px}
.bp-status.paused{background:#342b23;color:#e7c7a0;border-color:#584331}
.bp-studio{font-size:10px;color:#ce9dbb;text-transform:uppercase;letter-spacing:1.4px;margin:3px 0 8px}
.st-key-auto_paper_primary{border-color:var(--bp-line)!important;border-radius:18px!important;background:rgba(27,19,30,.73);padding:20px!important}
.st-key-auto_paper_primary h3{font-size:23px!important;line-height:1.25!important;margin:0 0 10px!important}
.st-key-auto_paper_pause_resume button{font-size:12px!important;padding:6px 13px!important;border-radius:9px!important}
.st-key-auto_paper_primary p{line-height:1.6}.blossom-board{border-radius:18px!important}
@media(max-width:650px){.bp-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.bp-metric{padding:12px}.bp-metric b{font-size:23px}.bp-call{min-height:0;padding:16px}.bp-side{font-size:30px}.hero .pills,.hero-public .pills{padding-top:0!important}.st-key-auto_paper_primary{padding:14px!important}.bp-picks{gap:18px}.hero-sub,.hero-desc-public{font-size:12px!important}}
@media(prefers-reduced-motion:reduce){.blossom-falling-petal{display:none!important}}
</style>'''


def metric_strip(items):
    return '<div class="bp-metrics">'+''.join(f'<div class="bp-metric"><span>{escape(str(label))}</span><b>{escape(str(value))}</b></div>' for label,value in items)+'</div>'


def compact_call(tf,market,call,quote,now,reference=None):
    names={'5m':'5 minutes','15m':'15 minutes','1h':'1 hour'};quote=quote or {};call=call or {};reference=reference or {}
    current=bool(market and call.get('market_slug')==market.get('slug') and market.get('start',now+1)<=now<market.get('end',0))
    side=call.get('current_side') if current else 'WAIT';tier=call.get('current_tier') if current else 'NO CALL'
    at=quote.get('fetched_at',quote.get('recorded_at'));bid=quote.get('bid');ask=quote.get('ask')
    valid=all(isinstance(v,(int,float)) and math.isfinite(v) for v in (at,bid,ask))
    fresh=bool(valid and 0<=now-at<=20 and 0<bid<=ask<1 and quote.get('health') in ('STREAM_OK','BOOK_OK','BBO_OK'))
    left=max(0,int(market['end']-now)) if market else None
    timer=f'{left//60:02}:{left%60:02}' if left is not None else '—'
    timer_html=f'<span data-btc-clock data-end-ms="{int(market["end"]*1000)}" data-btc-round="{escape(market["slug"])}">{timer}</span>' if market else timer
    prices=f'UP {ask*100:.1f}¢ · DOWN {(1-bid)*100:.1f}¢' if fresh else 'Fresh two-sided quotes unavailable'
    strength=call.get('current_strength') if current else None
    strength_text=f'{strength*100:.1f}% market strength' if isinstance(strength,(int,float)) and math.isfinite(strength) else 'Waiting for a qualifying call'
    ref=''
    if isinstance(reference.get('price'),(int,float)) and reference.get('status') in ('LIVE','FRESH'):
        ref=f'<div class="bp-small">BTC index ${reference["price"]:,.2f}</div>'
    return f'''<article class="bp-call"><div class="bp-top"><span>{escape(names.get(tf,tf))}</span><span class="bp-chip">{timer_html} remaining</span></div>
<div class="bp-side {'bp-up' if side=='UP' else 'bp-down' if side=='DOWN' else ''}">{escape(str(side))} <span style="font-size:10px;letter-spacing:1px;vertical-align:middle">{escape(str(tier))}</span></div>
<div class="bp-small">{escape(strength_text)} · not AI confidence</div><div class="bp-small">{escape(prices)}</div>{ref}
<div class="bp-picks"><span>Original<b>{escape(str(call.get('first_side','—') if current else '—'))}</b></span><span>Revised<b>{escape(str(side))}</b></span><span>Feed<b>{'Fresh quote' if fresh else 'Waiting'}</b></span></div></article>'''
