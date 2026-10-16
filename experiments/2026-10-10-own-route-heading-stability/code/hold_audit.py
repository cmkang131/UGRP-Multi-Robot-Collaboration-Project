"""Count saved commands only; no controller replay or simulation."""
from pathlib import Path
from collections import Counter
import json,sys

def audit(rows,start):
    reasons=Counter();counts=Counter();turns=flips=0;last=None
    for r in rows:
        if r['t']<start:continue
        c=r['command'];kind='turn' if c.get('turn',0) else 'forward' if c.get('forward',0)>0 else 'backward' if c.get('forward',0)<0 else 'lateral' if c.get('left',0) else 'hold'
        counts[kind]+=1
        if kind=='hold':reasons[r.get('pulse',{}).get('reason','unlogged')]+=1
        if kind=='turn':
            sign=1 if c['turn']>0 else -1
            flips+=last is not None and sign!=last;last=sign;turns+=1
    return dict(commands=dict(counts),hold_reasons=dict(reasons),turn_sign_reversals=flips,reversals_per_turn=flips/turns if turns else None)

def main(root):
    reports=[]
    for batch in ('egomap65-batch','egomap65-input-recovery'):
        for p in sorted((root/batch/'data').glob('egomap65-*')):
            if not p.is_dir() or not (p/'result.json').exists():continue
            result=json.loads((p/'result.json').read_text())
            with (p/'own-controller.jsonl').open() as f:r=audit((json.loads(x) for x in f),result['start_sim_s'])
            r.update(name=p.name,raw=str(p),wall_s=result['wall_s'],sim_s=result['total_sim_s']-result['start_sim_s'])
            r['wall_per_sim']=r['wall_s']/r['sim_s'];reports.append(r)
    assert len(reports)==24
    out=root/'egomap65-batch/data/hold-audit.json';out.write_text(json.dumps(reports,indent=2)+'\n')
    for pop in ('baseline','a'):
        for suffix in ('off','filtered_hysteresis_v1'):
            rows=[r for r in reports if r['name'].endswith(f'-{pop}-{suffix}')]
            c=Counter();h=Counter()
            for r in rows:c.update(r['commands']);h.update(r['hold_reasons'])
            print(pop,suffix,dict(c),dict(h),'flips/turn',sum(r['turn_sign_reversals'] for r in rows)/c['turn'])
    print('wall/SIM range',min(r['wall_per_sim'] for r in reports),max(r['wall_per_sim'] for r in reports),'maxwall',max(r['wall_s'] for r in reports))
if __name__=='__main__':main(Path(sys.argv[1]))
