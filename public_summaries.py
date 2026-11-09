"""Strict allowlists for read-only public research summaries. No local account access."""
import math

PAPER_FIELDS=('updated_at','enabled','cash_cents','available_cents','suggested_cents','realized_cents',
              'wins','losses','closed','open_positions','max_drawdown_cents','scored_rounds','original_correct','revised_correct')
TRAIN_FIELDS=('rounds_with_features','status','holdout_brier','market_brier','updated_utc','validated')


def finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def sanitize_extras(value):
    out={};paper=value.get('paper_summary')
    if isinstance(paper,dict) and paper.get('kind')=='SIMULATED_ONLY':
        clean={'kind':'SIMULATED_ONLY'}
        for k in PAPER_FIELDS:
            v=paper.get(k)
            if k=='enabled' and isinstance(v,bool):clean[k]=v
            elif finite(v):clean[k]=v
        out['paper_summary']=clean
    training=value.get('training_summary')
    if isinstance(training,dict):
        out['training_summary']={}
        for tf in ('5m','15m','1h'):
            row=training.get(tf)
            if not isinstance(row,dict):continue
            clean={}
            for k in TRAIN_FIELDS:
                v=row.get(k)
                if finite(v) or k=='validated' and isinstance(v,bool):clean[k]=v
                elif k in ('status','updated_utc') and isinstance(v,str):clean[k]=v[:80]
            out['training_summary'][tf]=clean
    results=value.get('verified_results')
    if isinstance(results,dict):
        out['verified_results']={}
        for key in ('5m','15m','1h','ai5m'):
            clean=[]
            for row in results.get(key,[])[:20] if isinstance(results.get(key),list) else []:
                if (isinstance(row,dict) and row.get('pick') in ('UP','DOWN') and row.get('outcome') in ('UP','DOWN')
                    and finite(row.get('round_end')) and isinstance(row.get('slug'),str)):
                    clean.append(dict(slug=row['slug'][:100],pick=row['pick'],outcome=row['outcome'],
                        correct=row['pick']==row['outcome'],round_end=row['round_end']))
            out['verified_results'][key]=clean
    return out
