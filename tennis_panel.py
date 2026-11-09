"""Pink tennis viewer; public rendering accepts only an explicit read-only summary."""
from datetime import datetime,timezone
import json
from html import escape
import time
import pandas as pd
import streamlit as st


def stamp(value):return datetime.fromtimestamp(value,timezone.utc).strftime('%b %d %H:%M:%S UTC') if value else 'Unavailable'
def money(value):return f'${value/100:,.2f}'


def view_data(path=None):
    import tennis_core as core
    now=time.time();path=path or core.DB;s=core.snapshot(path);cards=[]
    calls={c['slug']:c for c in s['calls']};marks={m['position_id']:m for m in s['marks']}
    with core.connect(path) as c:
        for m in s['matches']:
            row=c.execute('select at,health,detail,book from snapshots where slug=? order by id desc limit 1',(m['slug'],)).fetchone();q=None
            if row and row['book']:
                try:q=core.quote(m,json.loads(row['book']),now)
                except core.costs.PaperRejected:pass
            cards.append(dict(match=m,call=calls.get(m['slug']),quote=q,quote_at=row['at'] if row else None,
                quote_problem=row['detail'] if row else 'Waiting for book'))
        history=[]
        for call in s['calls'][:20]:
            match=next((m for m in s['matches'] if m['slug']==call['slug']),None)
            if match:history.append(dict(call,players=match['players']))
        series=[]
        for mode in ('EXPERIMENTAL','VALIDATED'):
            a=next(a for a in s['accounts'] if a['mode']==mode);conf=json.loads(a['settings'])
            positions=[p for p in s['positions'] if p['mode']==mode];closed=[p for p in positions if p['status']!='OPEN'];opened=[p for p in positions if p['status']=='OPEN']
            peak=conf['starting_cents'];dd=0
            for row in c.execute('select value from equity where mode=? order by at',(mode,)):peak=max(peak,row[0]);dd=max(dd,peak-row[0])
            peak_r=level=conf['starting_cents']
            for p in sorted(closed,key=lambda p:p['closed']):level+=p['realized'];peak_r=max(peak_r,level);dd=max(dd,peak_r-level)
            unrealized=sum(marks[p['id']]['unrealized'] for p in opened) if all(p['id'] in marks and marks[p['id']]['unrealized'] is not None and now-marks[p['id']]['at']<=20 for p in opened) else None
            series.append(dict(mode=mode,cash=a['cash'],available=max(0,a['cash']-sum(p['exit_reserve'] for p in opened)-conf['reserve_cents']),
                enabled=bool(a['enabled']),settings=conf,realized=sum(p['realized'] for p in closed),unrealized=unrealized,
                wins=sum(p['realized']>0 for p in closed),losses=sum(p['realized']<0 for p in closed),closed=len(closed),max_drawdown=dd))
        charts={}
        for m in s['matches'][:100]:
            charts[m['slug']]=[dict(at=r[0],probability=r[1]) for r in c.execute('select at,strength from call_history where slug=? order by at desc limit 100',(m['slug'],))]
    return dict(status=s['status'],control=s['control'],cards=cards,history=history,accounts=series,
        positions=s['positions'][:50],decisions=s['decisions'],marks=s['marks'],charts=charts)


def render(public=False,data=None,path=None):
    if data is None:
        if public:st.info('Tennis feed unavailable. No matches or scores are invented.');return
        data=view_data(path)
    now=time.time();status=data.get('status',{});healthy=0<=now-status.get('updated_at',0)<=60
    st.subheader('🎾 Live tennis')
    st.caption('POLYMARKET US · ATP / WTA / ITF SINGLES · INDEPENDENT TENNIS STUDIO')
    st.html('<style>@keyframes tennisGlow{50%{box-shadow:0 0 22px #ef91bd66}} .st-key-tennis_locked{animation:tennisGlow 2.5s ease-in-out infinite;border:1px solid #ef91bd;border-radius:12px;padding:12px;color:#f7b9da}@media(prefers-reduced-motion:reduce){.st-key-tennis_locked{animation:none}}</style>')
    st.info('Tennis model: UNVALIDATED. HOLDING / CALLED / LOCKED describe market support, not calibrated AI confidence. Real tennis trading is disabled.',title='Market calls & paper research')
    if not healthy:st.warning('Background tennis heartbeat is unavailable or stale. Last-reported information is not live.')
    st.caption('Public event/score polling ~60s; depth updates rotate across matches. Exchange quote limit 20s; live-score timestamp limit 120s. Displayed depth does not guarantee a fill.')
    if status.get('discovery_errors'):st.warning('Discovery limitations: '+', '.join(status['discovery_errors']))
    if not status.get('discovery_complete',False):st.caption('Discovery is partial or still starting; do not interpret this list as complete coverage.')
    if not public:
        import tennis_core as core
        path=path or core.DB;control=data['control'];mode=control['mode']
        chosen=st.segmented_control('Tennis paper mode',['EXPERIMENTAL','VALIDATED'],default=mode,key='tennis_paper_mode')
        if chosen and chosen!=mode:core.set_control(mode=chosen,path=path);st.rerun()
        a=next(a for a in data['accounts'] if a['mode']==mode)
        with st.container(horizontal=True):
            if st.button('Pause tennis paper' if a['enabled'] else 'Resume tennis paper',key='tennis_pause'):
                core.set_control(enabled=not a['enabled'],path=path);st.rerun()
            if st.button('Tennis emergency STOP',key='tennis_emergency_stop',type='primary'):
                core.set_control(stop=True,path=path);(path.parent/'REAL_STOP').write_text('Tennis stop requested locally');st.rerun()
            if control['stop'] and st.button('Resume tennis paper only',key='tennis_resume_after_stop'):
                core.set_control(stop=False,path=path);st.rerun()
        if control['stop']:st.error('Tennis STOP is set. New tennis paper entries are blocked; official settlement continues. BTC controls are separate.')
        with st.expander('Independent tennis paper budget'):
            with st.form('tennis_paper_limits'):
                conf=a['settings'];initial=st.number_input('Starting paper balance ($)',min_value=1,value=conf['starting_cents']//100,max_value=1000,disabled=bool(data['positions']))
                reserve=st.number_input('Protected tennis paper reserve ($)',min_value=0,value=conf['reserve_cents']//100,max_value=999)
                stake=st.number_input('Fixed experimental budget (cents, including fees)',min_value=1,max_value=200,value=conf['stake_cents'])
                if st.form_submit_button('Save tennis paper settings'):
                    try:core.configure(dict(starting_cents=initial*100,reserve_cents=reserve*100,stake_cents=stake),mode,path);st.rerun()
                    except core.costs.PaperRejected as exc:st.error(str(exc))
    else:mode=data.get('control',{}).get('mode','EXPERIMENTAL')
    selected_account=next((a for a in data.get('accounts',[]) if a['mode']==mode),{})
    if not healthy:st.caption('TENNIS PAPER — OFFLINE / STALE')
    elif data.get('control',{}).get('stop') or not selected_account.get('enabled'):st.warning('TENNIS PAPER — PAUSED / STOPPED. Official settlement continues.')
    elif mode=='VALIDATED':st.info('TENNIS PAPER — MONITORING, WAITING FOR VALIDATION. Recommended stake $0.')
    elif selected_account.get('available',0)<selected_account.get('settings',{}).get('stake_cents',100):
        st.warning('TENNIS PAPER — MONITORING POSITIONS. New entries blocked: insufficient available paper funds above reserve; no automatic top-up.')
    else:st.caption('EXPERIMENTAL TENNIS PAPER — MONITORING. Automatic entries require a fresh qualifying call, depth and risk checks; per-match blockers appear below.')
    with st.container(horizontal=True):
        st.metric('Tennis paper balance',money(selected_account.get('cash',0)),border=True)
        st.metric('Realized hypothetical P&L',money(selected_account.get('realized',0)),border=True)
        st.metric('Paper wins / losses',f"{selected_account.get('wins',0)} / {selected_account.get('losses',0)}",border=True)
        closed=selected_account.get('closed',0)
        st.metric('Paper win rate',f"{selected_account.get('wins',0)/closed:.1%}" if closed else 'Pending',border=True)
    cards=data.get('cards',[])
    # Fresh qualifying books are interesting to observe; this is not an EV ranking.
    cards=sorted(cards,key=lambda c:(not bool(c.get('quote')),not c['match'].get('live'),c['match'].get('start') or 0))
    st.caption('Fresh, narrow-spread matches appear first for research attention. This is not a claim of positive expected value.')
    if not cards:st.info('No verified ATP, WTA or ITF singles markets discovered yet. Discovery continues automatically.')
    else:
        lookup={c['match']['slug']:c for c in cards}
        slug=st.selectbox('Select a tennis match',list(lookup),format_func=lambda k:' vs. '.join(lookup[k]['match']['players'])+' · '+lookup[k]['match']['league'].upper(),key='tennis_match')
        card=lookup[slug];m=card['match'];call=card.get('call');q=card.get('quote')
        if not public:
            with core.connect(path) as c:c.execute('insert or replace into watchlist values(?,?)',(slug,now))
        if q and (not healthy or not -1<=now-q['exchange_at']<=20):q=None
        with st.container(border=True):
            st.markdown('#### '+' vs. '.join(m['players']))
            st.caption(m['tournament']+' · '+m['league'].upper()+' · start '+stamp(m['start']))
            fresh_score=m.get('score_at') and -1<=now-m['score_at']<=120 and healthy
            st.write(('LIVE' if m['live'] else 'ENDED' if m['ended'] else 'UPCOMING')+' · '+(str(m.get('score')) if fresh_score else 'Score unavailable / delayed'))
            st.caption('Score source updated '+stamp(m.get('score_at'))+' · '+(str(round(now-m['score_at'],1))+'s old' if m.get('score_at') else 'timestamp unavailable'))
            serving=m['players'][m['player_ids'].index(m['serving_id'])] if fresh_score and m['serving_id'] in m['player_ids'] else 'Unavailable'
            st.write('Serving: '+serving+' · period: '+(str(m.get('period')) if fresh_score else 'Unavailable'))
            if fresh_score and m.get('sets'):
                rows=[]
                for period in m['sets']:
                    scores={str(v.get('competitorId')):v.get('score') for v in period.get('scores',[])}
                    rows.append({'Set':period.get('label'),m['players'][0]:scores.get(m['player_ids'][0]),m['players'][1]:scores.get(m['player_ids'][1])})
                st.dataframe(rows,hide_index=True,alt='Verified provider set and game scores')
            if call:
                side=call['current'];name=m['players'][0 if side=='A' else 1];tier=call['tier']
                st.markdown('**PLAYER '+side+' WINS · '+name+' · '+tier+' 🌸**')
                if tier=='LOCKED':
                    with st.container(key='tennis_locked'):st.write('🌸 LOCKED market support · '+name+' · not a guarantee')
                st.caption('UNVALIDATED · original '+m['players'][0 if call['original']=='A' else 1]+' · '+call['original_tier']+' · '+stamp(call['original_at']))
                if call.get('warning'):st.warning(call['warning'])
                if not q:st.warning('Call is last reported; fresh execution quote unavailable.')
            else:st.write('Waiting for a fresh two-sided market call.')
            if q:
                with st.container(horizontal=True):
                    st.metric(m['players'][0]+' · market implied',f"{q['mid']:.1%}",border=True)
                    st.metric(m['players'][1]+' · market implied',f"{1-q['mid']:.1%}",border=True)
                st.write(f"Player A entry ask {q['ask']:.3f}, exit bid {q['bid']:.3f} · Player B entry ask {1-q['bid']:.3f}, exit bid {1-q['ask']:.3f}")
                st.caption('Exchange '+stamp(q['exchange_at'])+' · quote age '+f"{now-q['exchange_at']:.1f}s"+' · before modeled fees and slippage')
            else:st.caption('No live odds: '+str(card.get('quote_problem') or 'quote is stale'))
            with st.expander('Tennis intelligence & model evidence'):
                st.write('Model win probability: **Unavailable — calibration and positive edge unvalidated**. Validated recommended stake: **$0.00**.')
                st.write('Rankings from US metadata: '+str(m['rankings'])+' · surface: '+str(m.get('surface') or 'Unavailable'))
                st.caption('Recent results, head-to-head, surface form and break-point statistics require a verified point-in-time data source. No values are fabricated or inferred from market strength.')
            with st.expander('Market support history & settlement rules'):
                points=data.get('charts',{}).get(slug,[])
                if points:
                    st.line_chart(pd.DataFrame([{'Time':datetime.fromtimestamp(p['at'],timezone.utc),'Market support at call change':p['probability']} for p in reversed(points)]).set_index('Time'),alt='Market support at tennis call changes; not model probability')
                st.write(m['rules']);st.caption('Official US settlement only. A retirement, walkover or cancellation never becomes a guessed winner; fractional official settlement is supported.')
                st.caption('Verified event '+m['event_id']+' · market '+m['market_id']+' · '+m['slug'])
    st.markdown('### Last 20 tennis calls')
    history=[]
    for c in data.get('history',[])[:20]:
        outcome=c.get('outcome');label='⚪ Unresolved' if outcome is None else '⚪ Non-binary settlement' if outcome=='NON_BINARY' else '🟢 Correct' if outcome==c['original'] else '🔴 Incorrect'
        history.append({'Result':label,'Original winner':c['players'][0 if c['original']=='A' else 1],
                        'Call time':stamp(c['original_at']),'Original level':c['original_tier'],'Current player':c['players'][0 if c['current']=='A' else 1],
                        'Official winner':c['players'][0 if outcome=='A' else 1] if outcome in ('A','B') else 'Pending / non-binary'})
    if history:st.dataframe(history,hide_index=True,alt='Last twenty original tennis calls and official results')
    else:st.caption('No fresh tennis calls recorded yet.')
    resolved=[c for c in data.get('history',[]) if c.get('outcome') in ('A','B')]
    st.caption(f"Original-call accuracy in this last-20 window: {sum(c['original']==c['outcome'] for c in resolved)}/{len(resolved)} resolved. This is separate from paper trading returns.")
    st.markdown('### Tennis trading terminal')
    st.caption(mode+' · PAPER ONLY · UNVALIDATED · automatic entries only after a qualifying call, fresh depth and budget checks; hold to official settlement.')
    if selected_account:
        st.write('Fixed experimental budget '+money(selected_account['settings']['stake_cents'])+' · available '+money(selected_account['available'])+' · maximum drawdown '+money(selected_account['max_drawdown']))
        st.write('Unrealized simulated P&L: '+(money(selected_account['unrealized']) if healthy and selected_account.get('unrealized') is not None else 'Unavailable'))
    positions=[]
    marks={m['position_id']:m for m in data.get('marks',[])}
    for p in data.get('positions',[]):
        if p['mode']!=mode:continue
        mark=marks.get(p['id'],{});live_mark=healthy and 0<=now-mark.get('at',0)<=20
        positions.append({'Mode':p['mode'],'Market':p['slug'],'Player':p['side'],'Entry':p['entry'],'Shares':p['quantity'],'Entry fee ($)':p['entry_fee']/100,
                          'Stake incl. fee reserves ($)':(p['principal']+p['entry_fee']+p['exit_reserve'])/100,'Estimated value ($)':mark.get('value')/100 if live_mark and mark.get('value') is not None else None,
                          'Realized ($)':p['realized']/100 if p['realized'] is not None else None,'Settlement':p['settlement'],'Status':p['status']})
    if positions:st.dataframe(positions,hide_index=True,alt='Simulated tennis positions separate from real positions')
    else:st.caption('No tennis paper positions in this mode yet.')
    reasons=[{'Market':d['slug'],'Budget ($)':d['stake']/100,'Decision':d['reason']} for d in data.get('decisions',[]) if d['mode']==mode]
    if reasons:
        with st.expander('Tennis decisions & exact blockers',expanded=True):st.dataframe(reasons[:20],hide_index=True,alt='Automatic tennis decisions and skip reasons')
    st.markdown('**Real tennis positions: none connected. Real trading DISABLED.**')
    st.caption('The official US order request planner is fail-closed. No authenticated order endpoint is called. Separate local authorization, validated positive EV, and an atomic shared BTC/tennis bankroll coordinator are required before any real execution can be connected. BTC permissions never authorize tennis.')
    st.caption('Experimental and validated tennis results use separate simulated accounts; neither is combined with Bitcoin or real-money records.')
