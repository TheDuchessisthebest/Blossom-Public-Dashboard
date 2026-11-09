"""Bounded allowlist for a read-only US tennis public summary. No local access."""
import math
from tennis_match_status import classify
import time


def scalar(value):
    if value is None or isinstance(value,bool):return value
    if isinstance(value,(int,float)):return value if math.isfinite(value) else None
    if isinstance(value,str):return value[:4500]
    return None


def fields(row,names):
    return {key:scalar(row[key]) for key in names.split() if key in row} if isinstance(row,dict) else {}


def sanitize(value):
    if not isinstance(value,dict):return {}
    out=dict(status=fields(value.get('status'),'updated_at state paper_only real_enabled discovery_at discovery_complete known_matches eligible_matches processed fresh_books transport model confirmed_live_matches live_books_processed discovery_interval_seconds status_interval_seconds'),
             control=fields(value.get('control'),'mode stop'),cards=[],history=[],accounts=[],positions=[],decisions=[],marks=[],charts={})
    out['status']['real_enabled']=False
    cards=value.get('cards',[]) if isinstance(value.get('cards'),list) else []
    # Prefer fresh books and live matches; never export private position payloads.
    now=time.time()
    cards=sorted((r for r in cards if isinstance(r,dict) and isinstance(r.get('match'),dict)),key=lambda r:(classify(r['match'],now,r.get('call'))[0]!='LIVE',not bool(r.get('quote'))))
    if len(cards)>80:out['status']['discovery_complete']=False
    for card in cards[:80]:
        raw=card['match'];m=fields(raw,'slug market_id event_id league start received_at score_at score period serving_id live ended active closed status rules tournament surface source status_confirmed tradable special_status')
        for key in ('players','player_ids','rankings'):
            v=raw.get(key);m[key]=[scalar(x) for x in v[:2]] if isinstance(v,list) else []
        if len(m['players'])!=2 or len(m['player_ids'])!=2:continue
        m['sets']=[]
        for period in raw.get('sets',[])[:5] if isinstance(raw.get('sets'),list) else []:
            p=fields(period,'number label type');p['scores']=[fields(r,'competitorId score') for r in period.get('scores',[])[:2]];m['sets'].append(p)
        call=fields(card.get('call'),'slug original original_at original_tier current tier updated warning outcome settlement settled_at')
        out['cards'].append(dict(match=m,call=call or None,quote=fields(card.get('quote'),'bid ask mid age exchange_at') or None,
                                quote_at=scalar(card.get('quote_at')),quote_problem=scalar(card.get('quote_problem')),
                                prices=[fields(p,'at bid ask mid') for p in card.get('prices',[])[:30]],
                                events=[fields(p,'at side tier strength warning') for p in card.get('events',[])[:30]]))
    for row in value.get('history',[])[:20]:
        c=fields(row,'slug original original_at original_tier current tier updated warning outcome settlement settled_at')
        c['players']=[scalar(n) for n in row.get('players',[])[:2]]
        if len(c['players'])==2:out['history'].append(c)
    for row in value.get('accounts',[])[:2]:
        a=fields(row,'mode cash available enabled realized unrealized wins losses closed max_drawdown');a['settings']=fields(row.get('settings'),'starting_cents reserve_cents stake_cents max_stake_cents max_positions');out['accounts'].append(a)
    for row in value.get('positions',[])[:50]:out['positions'].append(fields(row,'id mode slug side quantity entry principal entry_fee exit_reserve budget entered quote_age status proceeds realized closed settlement'))
    for row in value.get('decisions',[])[:100]:out['decisions'].append(fields(row,'mode slug at reason stake'))
    for row in value.get('marks',[])[:50]:out['marks'].append(fields(row,'position_id at warning value unrealized reason'))
    charts=value.get('charts') or {}
    for card in out['cards']:
        slug=card['match']['slug'];points=charts.get(slug,[])
        out['charts'][slug]=[fields(p,'at probability') for p in points[:100] if isinstance(p,dict)]
    return out
