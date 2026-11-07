"""Hosted public-data collection. No account, order API, keys or local PC calls."""
import json,sqlite3,threading,time,shutil
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from us_monitor import init_db,unpack_book,date_ts,DURATIONS
from call_journal import init_journal,observe
from direction_signals import evaluate_direction
from blossom_contracts import verified_standard_series
from blossom_grade_sync import reconcile

ROOT=Path(__file__).resolve().parent
API='https://gateway.polymarket.us'

def get(path):
    request=Request(API+path,headers={'User-Agent':'BlossomPublicViewer/1.0','Accept':'application/json'})
    with urlopen(request,timeout=8) as response:return json.load(response)

def prepare(root=ROOT):
    folder=root/'us_data';folder.mkdir(exist_ok=True)
    db=folder/'quotes.sqlite3'
    if not db.exists():shutil.copy2(root/'seed/public.sqlite3',db)
    models=folder/'models';models.mkdir(exist_ok=True)
    if not (models/'training_status.json').exists():shutil.copy2(root/'seed/training_status.json',models/'training_status.json')
    init_db(db);init_journal(db)
    return db

def collect(db,known,now=None,fetch=get):
    now=time.time() if now is None else now
    for tf,seconds in DURATIONS.items():
        start=int(now//seconds)*seconds
        slug='cpc-btc-updown-'+tf+'-'+datetime.fromtimestamp(start,timezone.utc).strftime('%Y-%m-%d-%H%M')+'z'
        if not verified_standard_series(slug,tf,start,start+seconds):continue
        if known.get(tf)!=slug:
            market=fetch('/v1/market/slug/'+slug)['market']
            desc=str(market.get('description','')).lower()
            if market.get('slug')!=slug or market.get('active') is not True or market.get('closed') is not False:
                continue
            if not all(word in desc for word in ('settle to up','settle to down','brti')):continue
            known[tf]=slug
        payload=fetch('/v1/markets/'+slug+'/book')
        md=payload.get('marketData') or {}
        if md.get('marketSlug')!=slug:raise ValueError('Public quote market mismatch')
        book=unpack_book(payload,expected_slug=slug)
        received=time.time() if now>1e9 else now
        stamp=date_ts(book['exchange_time'])
        good=stamp is not None and -1<=received-stamp<=20 and book['state']=='MARKET_STATE_OPEN'
        good=good and book['bid'] is not None and book['ask'] is not None and 0<book['bid']<=book['ask']<1
        if not good:continue
        quote=dict(bid=book['bid'],ask=book['ask'],last=book['last'],health='BOOK_OK',fetched_at=received)
        market=dict(slug=slug,timeframe=tf,start=start,end=start+seconds,active=True)
        if received>=market['end']:continue
        with closing(sqlite3.connect(db,timeout=5)) as c:
            c.execute('INSERT INTO quotes(recorded_at,market_slug,bid,ask,last_trade) VALUES(?,?,?,?,?)',(received,slug,quote['bid'],quote['ask'],quote['last']));c.commit()
        observe(db,market,quote,evaluate_direction(market,quote,received,mapping_verified=True),received)
        time.sleep(1)

class CloudFeed:
    def __init__(self,db):self.db=db;self.thread=None
    def run(self):
        known={};retry={}
        while True:
            try:
                collect(self.db,known)
                now=time.time()
                with closing(sqlite3.connect(self.db,timeout=5)) as c:
                    pending=c.execute('SELECT j.market_slug,j.timeframe,j.round_end FROM price_call_journal j LEFT JOIN official_outcomes o USING(market_slug) WHERE o.market_slug IS NULL AND j.round_end<? ORDER BY j.round_end',(now-30,)).fetchall()
                pending=[r for r in pending if retry.get(r[0],0)<=now][:2]
                for slug,tf,end in pending:
                    retry[slug]=now+180
                    try:
                        result=get('/v1/markets/'+slug+'/settlement');value=result.get('settlement')
                        if result.get('slug')!=slug:raise ValueError('Public settlement identity mismatch')
                        if type(value) not in (int,float) or value not in (0,1):continue
                        with closing(sqlite3.connect(self.db,timeout=5)) as c:
                            c.execute('INSERT OR IGNORE INTO official_outcomes VALUES(?,?,?,?,?)',(slug,tf,end,value,time.time()));c.commit()
                    except HTTPError as exc:
                        if exc.code!=404:raise
                reconcile(self.db)
                time.sleep(35)
            except Exception as exc:
                # Never use missing data as a price/outcome or spam failing endpoints.
                time.sleep(120 if isinstance(exc,HTTPError) and exc.code==429 else 60)
    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
        return self
