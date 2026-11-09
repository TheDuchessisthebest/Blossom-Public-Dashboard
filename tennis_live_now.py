"""Read-only match cards and live/upcoming/completed navigation."""
from datetime import datetime,timezone
from html import escape
import pandas as pd
import streamlit as st
from tennis_match_status import groups,fresh


def stamp(at):return datetime.fromtimestamp(at,timezone.utc).strftime('%H:%M:%S UTC') if at else 'Unavailable'
def money(cents):return f'${cents/100:,.2f}'


def match_card(card,data,group,reason,now,healthy):
    m=card['match'];slug=m['slug'];call=card.get('call') or {};q=card.get('quote')
    mode=data.get('control',{}).get('mode','EXPERIMENTAL')
    positions=[p for p in data.get('positions',[]) if p['slug']==slug and p['mode']==mode]
    marks={p['position_id']:p for p in data.get('marks',[])}
    decision=next((d for d in data.get('decisions',[]) if d['slug']==slug and d['mode']==mode),{})
    if q and (not healthy or not fresh(q.get('exchange_at'),now,20) or not fresh(card.get('quote_at'),now,10)):q=None
    score_fresh=healthy and fresh(m.get('score_at'),now,120)
    period=str(m.get('period') or '')
    if period.startswith('S') and period[1:].isdigit():period='Set '+period[1:]
    label='🔴 LIVE — '+period if group=='LIVE' else '📅 UPCOMING' if group=='UPCOMING' else '✅ COMPLETED / TERMINAL'
    with st.container(border=True,key='tennis_card_'+slug):
        st.markdown('#### 🎾 '+' vs. '.join(m['players']))
        color='#ff7c91' if group=='LIVE' else '#e5b2d0'
        st.html('<div style="color:'+color+';font-weight:700;margin:4px 0 10px">'+escape(label)+'</div>')
        st.caption(m['league'].upper()+' · '+m.get('tournament','')+' · '+reason)
        score=m.get('score') if score_fresh else None
        st.write('**Current score:** '+(str(score) if score else 'Score unavailable'))
        server=m['players'][m['player_ids'].index(m.get('serving_id'))] if score_fresh and m.get('serving_id') in m['player_ids'] else 'Unavailable'
        st.caption('Serving: '+server+' · status updated '+stamp(m.get('score_at'))+
                   (f" · {max(0,now-m['score_at']):.0f}s old" if m.get('score_at') else ''))
        if q:
            with st.container(horizontal=True):
                st.metric(m['players'][0]+' · market implied',f"{q['mid']:.1%}",border=True)
                st.metric(m['players'][1]+' · market implied',f"{1-q['mid']:.1%}",border=True)
            st.caption(f"Executable-depth observations before fees/slippage: A ask {q['ask']:.3f} / bid {q['bid']:.3f}; B ask {1-q['bid']:.3f} / bid {1-q['ask']:.3f}. Exchange age {max(0,now-q['exchange_at']):.1f}s.")
        else:st.caption('Current market odds unavailable — '+str(card.get('quote_problem') or 'fresh depth is missing'))
        side=call.get('current');original=call.get('original')
        if side in ('A','B'):
            name=m['players'][0 if side=='A' else 1];tier=call.get('tier','HOLDING')
            st.write('**🌸 Blossom call: PLAYER '+side+' — '+name+'**')
            st.write('**Confidence category: '+tier+'** · UNVALIDATED market-support call'+(' · last reported' if not q else ''))
            if tier=='LOCKED':st.html('<div class="tn-lock">🌸 LOCKED market support · not a guarantee</div>')
            st.caption('Original: '+(m['players'][0 if original=='A' else 1] if original in ('A','B') else 'Unavailable')+' · '+stamp(call.get('original_at')))
            if call.get('warning'):st.warning(call['warning'])
        else:st.write('**🌸 Blossom call: Waiting for fresh qualifying observations**')
        st.caption('Calibrated model win probability: unavailable. Market-implied probability is not calibrated AI confidence.')
        if positions:
            p=positions[0];mark=marks.get(p['id'],{});mark_fresh=healthy and fresh(mark.get('at'),now,20)
            st.write('**Paper trade: '+('POSITION OPEN — PAPER ONLY' if p['status']=='OPEN' else p['status']+' — PAPER ONLY')+'**')
            st.caption(f"Budget {money(p['budget'])} · modeled entry {p['entry']:.3f} · {p['quantity']} share(s) · entry fee {money(p['entry_fee'])}")
            st.caption('Potential gross payout if this player wins: '+money(100*p['quantity'])+
                       ' · hypothetical winning net profit '+money(100*p['quantity']-p['principal']-p['entry_fee'])+' · not guaranteed')
            pnl=p.get('realized') if p['status']!='OPEN' else mark.get('unrealized') if mark_fresh else None
            st.write('**'+('Realized' if p['status']!='OPEN' else 'Unrealized')+' simulated P&L:** '+(money(pnl) if pnl is not None else 'Unavailable — fresh executable exit depth missing'))
        else:
            st.write('**Paper trade: Monitoring — no simulated entry**')
            st.caption('Automatic budget: '+money(decision.get('stake',0))+' · '+str(decision.get('reason') or 'Waiting for worker evaluation'))
        detail=st.expander('Match details · statistics, call history, prices & trades',key='tennis_details_'+slug,on_change='rerun')
        with detail:
            if detail.open:
                if score_fresh and m.get('sets'):
                    rows=[]
                    for period in m['sets']:
                        values={str(x.get('competitorId')):x.get('score') for x in period.get('scores',[])}
                        rows.append({'Set':period.get('label'),m['players'][0]:values.get(m['player_ids'][0]),m['players'][1]:values.get(m['player_ids'][1])})
                    st.dataframe(rows,hide_index=True,alt='Verified set and game scores')
                st.write('Rankings: '+str(m.get('rankings'))+' · surface: '+str(m.get('surface') or 'Unavailable'))
                st.caption('Recent form, head-to-head and break-point data remain unavailable without a verified provider.')
                prices=card.get('prices',[])
                if prices:
                    frame=pd.DataFrame([{'Time':datetime.fromtimestamp(p['at'],timezone.utc),
                        'Player A midpoint':p['mid'],'Player B midpoint':1-p['mid'],
                        'Player A executable ask':p['ask'],'Player B executable ask':1-p['bid']} for p in prices]).set_index('Time')
                    st.line_chart(frame,alt='Observed tennis market probabilities and entry prices over time')
                    st.caption('Observed market-price movement only. No calibrated model probability series is available; gaps are not filled with invented prices.')
                else:st.caption('Price movement: waiting for fresh saved observations.')
                events=card.get('events',[])
                if events:st.dataframe([dict(Time=stamp(e['at']),Player=e['side'],Category=e['tier'],Market_support=e['strength'],Warning=e.get('warning')) for e in events],hide_index=True,alt='Original and revised tennis prediction history')
                if positions:st.dataframe([{k:p.get(k) for k in ('mode','side','entry','quantity','budget','entry_fee','entered','status','settlement','realized')} for p in positions],hide_index=True,alt='This match simulated trading history')
                else:st.caption('No simulated position was opened on this match.')
                outcome=call.get('outcome')
                if outcome in ('A','B'):
                    st.write('**Official winner:** '+m['players'][0 if outcome=='A' else 1])
                    st.write('**Original call:** '+('Correct' if original==outcome else 'Incorrect'))
                elif outcome=='NON_BINARY':st.write('Official non-binary settlement: '+str(call.get('settlement'))+' · excluded from winner accuracy')
                elif group=='COMPLETED':st.caption('Official outcome pending; no winner is inferred from score alone.')
                st.write(m.get('rules','Settlement rules unavailable'))
                st.caption('US event '+m['event_id']+' · market '+m['market_id']+' · '+slug)


def render_match_tabs(data,now,healthy):
    split=groups(data.get('cards',[]),now,healthy)
    st.html('<style>.tn-lock{border:1px solid #ef91bd;border-radius:10px;padding:8px;color:#ffc4e2;animation:tnGlow 2.5s ease-in-out infinite}@keyframes tnGlow{50%{box-shadow:0 0 18px #ef91bd66}}@media(prefers-reduced-motion:reduce){.tn-lock{animation:none}}</style>')
    st.markdown('### 🎾 LIVE NOW — Tennis Matches')
    st.caption('Only fresh, verified in-play tennis status qualifies. An open betting market or a scheduled start never creates a LIVE label. This view refreshes automatically.')
    live,upcoming,completed=st.tabs([f'🔴 LIVE NOW ({len(split["LIVE"])})','📅 UPCOMING','✅ COMPLETED'],key='tennis_match_groups',on_change='rerun')
    for tab,group in ((live,'LIVE'),(upcoming,'UPCOMING'),(completed,'COMPLETED')):
        with tab:
            if not tab.open:continue
            rows=split[group]
            rows.sort(key=lambda x:(x[0]['match'].get('start') or 0))
            if group=='COMPLETED':
                rows.reverse();scored=[c for c,_ in rows if (c.get('call') or {}).get('outcome') in ('A','B')]
                st.caption(f"Original-call accuracy: {sum(c['call']['original']==c['call']['outcome'] for c in scored)}/{len(scored)} officially resolved matches in this view. Trading profitability is separate.")
            if not rows:st.info('No confirmed actively running matches in the current feed.' if group=='LIVE' else 'No verified matches in this category yet.')
            if group=='LIVE' and rows:st.caption(f'{len(rows)} actively running matches · all are monitored; a paper position is shown only after a recorded simulated fill.')
            page_size=20
            if len(rows)>page_size:
                page=st.selectbox('Match page',list(range((len(rows)+page_size-1)//page_size)),format_func=lambda p:f'{p*page_size+1}–{min(len(rows),(p+1)*page_size)} of {len(rows)}',key='tennis_page_'+group)
                rows=rows[page*page_size:(page+1)*page_size]
            for card,reason in rows:match_card(card,data,group,reason,now,healthy)
    unknown=len(split['UNCONFIRMED'])
    if unknown:st.caption(f'{unknown} listings excluded from LIVE NOW because active play, market availability or fresh status cannot be confirmed. They are not silently labeled upcoming or completed.')
    return split
