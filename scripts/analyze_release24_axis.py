"""gcp1 saved-evidence axis audit. Truth stays in this offline evaluator only."""
from __future__ import annotations
import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np


def read(p):
    if not p.exists(): p=p.with_suffix(p.suffix+'.zst')
    data=p.read_bytes()
    raw=subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else data
    return raw,dict(path=str(p),sha256=hashlib.sha256(data).hexdigest())


def wrap(a): return (a+math.pi/2)%math.pi-math.pi/2


def distribution(v):
    a=np.asarray(v,float)
    if not len(a):return dict(N=0)
    return dict(N=len(a),mean=float(a.mean()),sd=float(a.std()),
        quantiles={str(q):float(np.quantile(a,q,method='higher')) for q in (0,.05,.5,.9,.95,.99,1)})


def analyze(out,runs=Path('/home/ugrp/ugrp-sim/runs')):
    from harness.zone_final_environment import resolve
    samples=[];sources=[];episodes=[];rejections=Counter();missing=[]
    roots=sorted([*runs.glob('r21ag-*-46afd8b0'),*runs.glob('r21bg-*-46afd8b0'),
                  *runs.glob('r23d*-*-4a1809e2'),*runs.glob('r23d*-*-f4f2994d'),*runs.glob('r23d3-*-8d24a525')])
    for root in roots:
        cohort='release21' if root.name.startswith('r21') else 'release23-'+root.name.split('-')[0]
        try:
            raw,src=read(root/'raw/result.json');d=json.loads(raw);sources.append(src)
            raw,src=read(root/'raw/plan.json');p=json.loads(raw);sources.append(src)
            static,_,_=resolve(p['map_id']);half=static['regions'][p['destination_region']]['half_extents_m'];axis=int(half[1]>=half[0])
            raw,src=read(root/'raw/eval-only.jsonl');truth=[json.loads(x) for x in raw.splitlines()];sources.append(src)
            ts=[x['t'] for x in truth]
            traces={}
            for rid in ('r1','r2'):
                raw,src=read(root/f'raw/teacher-{rid}.jsonl');sources.append(src)
                traces[rid]=[json.loads(x) for x in raw.splitlines()]
            # One sample per newly posted synchronized report, not every 0.1s
            # repetition in the command ledger. Include stopped DEV traces.
            pairs={}
            for tr in traces['r1']:
                r=tr.get('report') or {}
                if r.get('phase')=='observe' and 'axis_error_rad' in r:
                    key=(r.get('observation_epoch'),r.get('observed_at')) if 'observed_at' in r else json.dumps(r,sort_keys=True)
                    pairs.setdefault(key,tr)
            t2=[x['t'] for x in traces['r2']]
            for tr in pairs.values():
                t=tr['t'];j=bisect_right(t2,t+1e-7)-1
                if j<0:continue
                rows=[tr.get('report') or {},traces['r2'][j].get('report') or {}]
                if any('axis_error_rad' not in r for r in rows):continue
                if any('observed_at' in r for r in rows) and rows[0].get('observed_at')!=rows[1].get('observed_at'):continue
                ev=truth[max(0,bisect_right(ts,t+1e-7)-1)]
                actual=wrap(ev['beam']['pose'][2]-(math.pi/2 if axis else 0))
                angles=[r['axis_error_rad'] for r in rows]
                errors=[math.degrees(wrap(a-actual)) for a in angles]
                triggered=any(abs(a)>math.radians(10) for a in angles)
                samples.append(dict(run=root.name,cohort=cohort,seed=p['seed'],t=t,
                    angles_deg=list(map(math.degrees,angles)),truth_deg=math.degrees(actual),
                    errors_deg=errors,difference_deg=math.degrees(wrap(angles[0]-angles[1])),
                    sigma_xy_m=[r.get('pose_sigma_m') for r in rows],
                    triggered=triggered,unnecessary=triggered and abs(actual)<=math.radians(10),
                    reports=rows))
            completed=d.get('status')=='complete'
            category='success' if d.get('release_success') else ('cap_end' if d.get('release_outcome') in ('release_timeout','cap_end') else d.get('release_outcome') or 'supervisor_stop_or_HOST_ERROR')
            episodes.append(dict(run=root.name,cohort=cohort,seed=p['seed'],completed=completed,category=category))
            if category!='success':rejections[category]+=1
        except (FileNotFoundError,KeyError,IndexError) as e:missing.append(dict(run=root.name,reason=str(e)))
    tables={}
    for cohort in sorted({s['cohort'] for s in samples}):
        a=[s for s in samples if s['cohort']==cohort];trigger=[s for s in a if s['triggered']]
        tables[cohort]=dict(pairs=len(a),r1_error_deg=distribution([s['errors_deg'][0] for s in a]),
            r2_error_deg=distribution([s['errors_deg'][1] for s in a]),
            signed_difference_deg=distribution([s['difference_deg'] for s in a]),
            abs_difference_deg=distribution([abs(s['difference_deg']) for s in a]),
            gate_trigger_N=len(trigger),truth_unnecessary_n=sum(s['unnecessary'] for s in trigger),
            unnecessary_fraction=sum(s['unnecessary'] for s in trigger)/len(trigger) if trigger else None)
    base=[s for s in samples if s['cohort']=='release21']
    # Empirical second moments retain bias in uncertainty, unlike variance.
    calibration=dict(source_cohort='release21 only; DEV is diagnostic, not calibration',
        mse_deg2=[float(np.mean([s['errors_deg'][i]**2 for s in base])) for i in (0,1)],
        disagreement_p95_deg=float(np.quantile([abs(s['difference_deg']) for s in base],.95,method='higher')),
        error_correlation=float(np.corrcoef(np.array([s['errors_deg'] for s in base]).T)[0,1]))
    summary=dict(schema='ugrp.release24.axis-audit.v1',scope='offline correlated observations; cohorts separate',
        tables=tables,calibration=calibration,episodes=episodes,missing=missing,
        rejection_reason_table=[dict(category=k,count=v,blocking_object='episode budget' if k=='cap_end' else 'release controller',minimum_gap=None,gap_unknown_reason='legacy summary omits gap') for k,v in rejections.most_common()],
        episode_funnel=[dict(gate='discovered',cumulative_passed=len(roots),rejected=0),dict(gate='readable_saved_evidence',cumulative_passed=len(episodes),rejected=len(missing)),dict(gate='complete',cumulative_passed=sum(e['completed'] for e in episodes),rejected=sum(not e['completed'] for e in episodes)),dict(gate='success',cumulative_passed=sum(e['category']=='success' for e in episodes),rejected=sum(e['completed'] and e['category']!='success' for e in episodes))],
        observation_funnel=[dict(gate='same_round_axis_pair',cumulative_passed=len(samples),rejected=0),dict(gate='legacy_10deg_pass',cumulative_passed=sum(not s['triggered'] for s in samples),rejected=sum(s['triggered'] for s in samples))],
        raw_sources=sources,reproduce="cd /home/ugrp/ugrp-sim/src/8d24a525fc3e2d480050dc08788befd8f3d4fde4 && PYTHONPATH=. .venv-sim/bin/python /home/ugrp/ugrp-sim/ops-reviews/release24/analyze_release24_axis.py --out /home/ugrp/ugrp-sim/ops-reviews/release24")
    out.mkdir(parents=True,exist_ok=True)
    (out/'rejection_table.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'axis-samples.json').write_text(json.dumps(samples,indent=2)+'\n')
    print(json.dumps(dict(tables=tables,calibration=calibration,episode_count=len(episodes),missing=missing,rejections=dict(rejections))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);analyze(p.parse_args().out)
