"""Read-only public display. No controls, database writes or trading imports."""
from html import escape
from datetime import datetime,timezone
import streamlit as st
from blossom_ui import metric_strip


def render_paper(summary,now):
    st.subheader('Automatic paper trading')
    st.caption('Public observation · simulated funds · read only')
    if not isinstance(summary,dict) or summary.get('kind')!='SIMULATED_ONLY':
        st.info('Live paper summary is not available. No balance or performance is invented.');return
    stamp=summary.get('updated_at',0);fresh=0<=now-stamp<=20
    active=fresh and summary.get('enabled')
    st.html('<span class="bp-status '+('' if active else 'paused')+'">'+('PAPER AUTO-TRADING ACTIVE' if active else 'PAPER AUTO-TRADING PAUSED / STALE')+'</span>')
    money=lambda key:f"${summary[key]/100:,.2f}" if key in summary else '—'
    st.html(metric_strip([('Paper balance',money('cash_cents')),('Available above reserve',money('available_cents')),
        ('Suggested stake',money('suggested_cents') if fresh else '—'),('Realized P&L',money('realized_cents'))]))
    st.caption('$20 initial paper balance · $15 protected reserve · $2 maximum per bet. No real funds, orders or visitor controls.')
    if fresh and summary.get('suggested_cents')==0:st.info('No validated positive edge qualifies for an entry.',title='NO BET RECOMMENDED · $0')
    closed=summary.get('closed',0)
    with st.expander('Simulated performance & limitations',expanded=False):
        st.write(f"Closed trades {closed} · wins {summary.get('wins',0)} · losses {summary.get('losses',0)} · open {summary.get('open_positions',0)}")
        st.caption('Hypothetical fills include modeled fees and adverse slippage. Displayed liquidity never guarantees execution. No profitability claim is supported without prospective results.')
        if stamp:st.caption('Paper source updated '+datetime.fromtimestamp(stamp,timezone.utc).strftime('%b %d %H:%M:%S UTC'))
        if not fresh:st.warning('Paper source heartbeat is stale. Values are last reported, not live execution data.')


def render_results(results):
    st.markdown('### Verified call record')
    st.caption('Latest 20 settled original calls · market-price observations, not AI confidence or executed trades')
    for tf,col in zip(('5m','15m','1h'),st.columns(3)):
        with col:
            rows=results.get(tf,[]);right=sum(r['correct'] for r in rows)
            st.write(f'**{tf} · {right}/{len(rows)} correct**')
            dots=[]
            for row in reversed(rows):
                label=f"{row['slug']} · original {row['pick']} · official {row['outcome']}"
                dots.append('<span title="'+escape(label)+'" style="display:inline-grid;place-items:center;width:22px;height:25px;border-radius:6px;margin:2px;background:'+('#204432;color:#b4e5c4' if row['correct'] else '#502b37;color:#f4b6c1')+'">'+('✓' if row['correct'] else '×')+'</span>')
            st.html('<div style="line-height:1.8">'+''.join(dots)+'</div>')
    with st.expander('Independent AI original-call record · prototype'):
        rows=results.get('ai5m',[])
        st.write(f"{sum(r['correct'] for r in rows)}/{len(rows)} verified original AI calls")
        st.caption('Separate from market-price calls. A small historical sample does not establish predictive or trading advantage.')
