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
            prices=[dict(at=r[0],bid=r[1],ask=r[2],mid=(r[1]+r[2])/2) for r in c.execute(
                "select at,json_extract(features,'$.market_bid'),json_extract(features,'$.market_ask') from snapshots where slug=? and health='FRESH' and json_extract(features,'$.market_bid') is not null order by id desc limit 30",(m['slug'],))]
            prices.reverse()
            events=[dict(r) for r in c.execute('select at,side,tier,strength,warning from call_history where slug=? order by id desc limit 30',(m['slug'],))]
            cards.append(dict(match=m,call=calls.get(m['slug']),quote=q,quote_at=row['at'] if row else None,
                quote_problem=row['detail'] if row else 'Waiting for book',prices=prices,events=events))
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
    st.caption('League discovery targets 30s; exact event status targets 10s; depth prioritizes confirmed live matches. UI refreshes every 5s. Exchange quote limit 20s; match-status limit 120s. Provider delays and API cooldowns may slow updates; displayed depth never guarantees a fill.')
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
    from tennis_live_now import render_match_tabs
    render_match_tabs(data,now,healthy)
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
