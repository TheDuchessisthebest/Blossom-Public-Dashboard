"""One conservative match-status policy shared by worker and both viewers."""
import math
import re

STATUS_MAX_AGE=120
METADATA_MAX_AGE=90
TERMINAL=('RET','WO','W/O','ABD','CANC','DEF','FT','FINAL','FINISHED','ENDED')


def fresh(at,now,limit):
    return isinstance(at,(int,float)) and not isinstance(at,bool) and math.isfinite(at) and -1<=now-at<=limit


def classify(m,now,call=None):
    """An open market, scheduled start or old live flag never proves play."""
    period=str(m.get('period') or '').upper().strip()
    special=str(m.get('special_status') or '').upper()
    terminal=period in TERMINAL or any(v in special+' '+period for v in ('CANCEL','ABANDON','RETIR','WALKOVER','DEFAULT','FINISHED'))
    if (call or {}).get('settlement') is not None or m.get('ended') is True or terminal:
        return 'COMPLETED','Official settlement available' if (call or {}).get('settlement') is not None else 'Special match / finished status; official settlement may be pending'
    if not m.get('active') or m.get('closed') or m.get('tradable') is False:
        return 'UNCONFIRMED','Market unavailable; not evidence of a running match'
    if not fresh(m.get('received_at'),now,METADATA_MAX_AGE):return 'UNCONFIRMED','Match metadata stale'
    if not m.get('status_confirmed'):return 'UNCONFIRMED','Reliable tennis match-status identity unavailable'
    if any(v in special+' '+period for v in ('SUSP','DELAY','POSTPON','INTERRUPT','PAUSE')):
        return 'UNCONFIRMED','Play suspended or delayed'
    if m.get('live') is True:
        if not fresh(m.get('score_at'),now,STATUS_MAX_AGE):return 'UNCONFIRMED','Live score stale or match-status timestamp missing'
        if not re.fullmatch(r'S[1-5]|SET[ _]?[1-5]|IN_PROGRESS|INPLAY',period):
            return 'UNCONFIRMED','Active set / in-play status is not confirmed'
        return 'LIVE','Fresh official US tennis state confirms active play'
    start=m.get('start')
    if isinstance(start,(int,float)) and math.isfinite(start) and start>now and period in ('NS','NOT_STARTED','SCHEDULED',''):
        return 'UPCOMING','Scheduled to begin later; no active play inferred'
    return 'UNCONFIRMED','Start time has passed without fresh confirmation of active play'


def groups(cards,now,healthy=True):
    result={k:[] for k in ('LIVE','UPCOMING','COMPLETED','UNCONFIRMED')}
    for card in cards:
        group,reason=classify(card['match'],now,card.get('call'))
        if not healthy and group=='LIVE':group,reason='UNCONFIRMED','Worker heartbeat stale; live status withdrawn'
        result[group].append((card,reason))
    return result
