"""Public call transport only. No credentials, account state, order APIs or execution."""
import json, math, os, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

TIMEFRAMES=('5m','15m','1h')
ROUND_FIELDS=('slug','timeframe','start','end')
CALL_FIELDS=('market_slug','timeframe','round_start','round_end','first_side','first_tier','first_strength','first_at','current_side','current_tier','current_strength','current_at','switches','is_current','mapping_verified')
QUOTE_FIELDS=('recorded_at','bid','ask','last_trade','age','fresh','valid','status')
REF_FIELDS=('status','strike','price','timestamp','age','source_timestamp','source_age')

def pick(value,fields):
    return {k:value[k] for k in fields if k in value} if isinstance(value,dict) else None

def public_payload(snapshot):
    return {'schema':1,'source':'PERSONAL_DASHBOARD','generated_at':snapshot['time'],
      'db_available':bool(snapshot.get('db_available')), 'counts':snapshot.get('counts',{}),
      'ai':None,'markets':{tf:{'round':pick(v.get('round'),ROUND_FIELDS),
        'call':pick(v.get('call'),CALL_FIELDS),'quote':pick(v.get('quote'),QUOTE_FIELDS),
        'reference':pick(v.get('reference'),REF_FIELDS) or {'status':'UNAVAILABLE'},
        'last_quote_seen':v.get('last_quote_seen')} for tf,v in snapshot['markets'].items() if tf in TIMEFRAMES}}

def publish(db,current,quotes,now,destination):
    from viewer_data import read_snapshot
    from call_journal import journal_for
    snapshot=read_snapshot(db,now)
    for tf in TIMEFRAMES:
        m=current.get(tf);v=snapshot['markets'][tf]
        if m and m.get('start',now+1)<=now<m.get('end',0):
            v['round']=m
            c=journal_for(db,m['slug'])
            if c:c['is_current']=True;v['call']=c
            q=quotes.get(m['slug'])
            if q:
                bid,ask=q.get('bid'),q.get('ask');at=q.get('fetched_at')
                valid=all(isinstance(x,(int,float)) and math.isfinite(x) for x in (bid,ask,at)) and 0<bid<=ask<1
                fresh=valid and q.get('health') in ('BOOK_OK','BBO_OK','STREAM_OK') and 0<=now-at<=20
                v['quote']={'recorded_at':at,'bid':bid,'ask':ask,'last_trade':q.get('last'),'valid':valid,'fresh':fresh,'age':max(0,now-at) if isinstance(at,(int,float)) else None,'status':'FRESH' if fresh else 'STALE'}
    data=public_payload(snapshot)
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    temp=destination.with_suffix('.tmp')
    temp.write_text(json.dumps(data,allow_nan=False),encoding='utf-8');os.replace(temp,destination)
    return data

def decode(payload,now=None):
    from viewer_data import parsed_round
    now=time.time() if now is None else now
    if not isinstance(payload,dict) or payload.get('schema')!=1 or payload.get('source')!='PERSONAL_DASHBOARD':raise ValueError('Unexpected shared source')
    stamp=payload.get('generated_at')
    if not isinstance(stamp,(int,float)) or not math.isfinite(stamp) or not -3<=now-stamp<=30:raise ValueError('Personal dashboard feed is offline or stale')
    clean=public_payload({**payload,'time':stamp})
    clean['time']=now;clean['source_time']=stamp
    for tf in TIMEFRAMES:
        v=clean['markets'].get(tf)
        if not isinstance(v,dict):raise ValueError('Missing timeframe')
        m=v['round'];c=v['call'];q=v['quote']
        if m:
            expected=parsed_round(m.get('slug'))
            if not expected or expected!=m or m['timeframe']!=tf:raise ValueError('Round identity mismatch')
            if not m['start']<=now<m['end']:
                v['round']=None;v['quote']=None
        if c:
            if c.get('first_side') not in ('UP','DOWN') or c.get('current_side') not in ('UP','DOWN') or c.get('current_tier') not in ('CALLED','LOCKED'):raise ValueError('Invalid call')
            expected=parsed_round(c.get('market_slug'))
            if not expected or expected['timeframe']!=tf or c.get('round_start')!=expected['start'] or c.get('round_end')!=expected['end']:raise ValueError('Call identity mismatch')
            c['is_current']=bool(v['round'] and c['market_slug']==v['round']['slug'])
        if q and v['round']:
            bid,ask,at=q.get('bid'),q.get('ask'),q.get('recorded_at')
            valid=all(isinstance(x,(int,float)) and math.isfinite(x) for x in (bid,ask,at)) and 0<bid<=ask<1
            q['valid']=valid;q['fresh']=bool(valid and q.get('fresh') and 0<=now-at<=20)
            q['age']=max(0,now-at) if isinstance(at,(int,float)) else None
            q['status']='FRESH' if q['fresh'] else 'STALE'
    return clean

def fetch(url,now=None):
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Shared feed requires a public HTTPS URL')
    with urlopen(Request(url,headers={'Accept':'application/json','Cache-Control':'no-cache'}),timeout=5) as response:
        data=response.read(262145)
    if len(data)>262144:raise ValueError('Shared feed exceeds size limit')
    return decode(json.loads(data),now)
