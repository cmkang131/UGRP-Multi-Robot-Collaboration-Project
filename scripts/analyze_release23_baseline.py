"""Run on gcp1: saved-evidence calibration only, no simulator or control input.

Usage: .venv-sim/bin/python scripts/analyze_release23_baseline.py --out DIR
Truth is read solely here, for offline residuals and labels, never by release23.
"""
from __future__ import annotations
import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess


def read(p):
    if not p.exists(): p = p.with_suffix(p.suffix+'.zst')
    raw = subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
    return raw, dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                     decoded_sha256=hashlib.sha256(raw).hexdigest())


def analyze(out, runs=Path('/home/ugrp/ugrp-sim/runs')):
    from harness.zone_final_environment import resolve
    samples=[]; costs=[]; tails=[]; sources=[]; shas=set(); rejection=Counter(); episode=Counter(); line=Counter()
    for root in sorted([*runs.glob('r21ag-*-46afd8b0'), *runs.glob('r21bg-*-46afd8b0'),
                        runs/'rel22rec-record-88639-f4763385']):
        raw, src = read(root/'raw/result.json'); d=json.loads(raw); sources.append(src); shas.add(d['source_sha'])
        episode['attempted']+=1
        episode['audit_zero']+=int(all(d['input_audit'][k]==0 for k in ('invisible_measurements','held_world_reads','control_top_camera_reads')))
        episode['success']+=int(d['release_success'])
        if not d['release_success']:
            rejection['cap_end' if d['release_outcome']=='release_timeout' else d['release_outcome']]+=1
        for check in d.get('line_rechecks',[]):
            line['candidate']+=1;line['done']+=int(check['state']=='done')
            for ev in check['events']:
                line['events']+=1
                if 'blocked' in ev['event']: rejection[ev['event']]+=1
        plan=json.loads(read(root/'raw/plan.json')[0]);static,_,_=resolve(plan['map_id'])
        zone=static['regions'][plan['destination_region']]; center=zone['center_m'];half=zone['half_extents_m']; axis=int(half[1]>=half[0])
        traces={}
        for rid in ('r1','r2'):
            raw,src=read(root/f'raw/teacher-{rid}.jsonl');sources.append(src)
            traces[rid]=[r for v in raw.splitlines() if 't' in (r:=json.loads(v))]
        raw,src=read(root/'raw/eval-only.jsonl');sources.append(src)
        truth=[json.loads(v) for v in raw.splitlines()]; times=[v['t'] for v in truth]
        decisions=[c for c in d['code_decisions'] if c.get('reason')]
        for i,c in enumerate(decisions):
            if c['action'] in ('shift','axis_correct') and i+1<len(decisions):
                costs.append(dict(run=root.name, start=c['t'], seconds=decisions[i+1]['t']-c['t']))
            if i==len(decisions)-1 and c['action']=='lower':
                tails.append(d['sim_s']-(c['t']-truth[0]['t']+d['prefix']['held_sim_s']))
            rows=[]
            # rel22 recorder has clean commands but no scalar report in this
            # student trace; use it for failure/cycle counts, never impute data.
            if not all(traces.values()): continue
            for rid in ('r1','r2'):
                tr=traces[rid]; idx=bisect_right([v['t'] for v in tr],c['t']+1e-7)-1
                rows.append(tr[idx].get('report') or {})
            if not all(r.get('kind')=='localized_margin' for r in rows):continue
            m=[r['margin_m'] for r in rows]
            theta=[r['axis_error_rad'] for r in rows]
            slack=2*half[axis]-.60*sum(abs(math.cos(v)) for v in theta)/2
            residual=sum(m)-slack; bias=residual/2
            ev=truth[max(0,bisect_right(times,c['t']+1e-7)-1)]
            x,y,a=ev['beam']['pose']; direction=(math.cos(a),math.sin(a))
            actual=[]
            for rid in ('r1','r2'):
                sign=-1 if plan['roles'][rid]=='teal' else 1
                p=(x,y)[axis]+sign*.30*direction[axis]
                outward=sign*direction[axis]
                actual.append(half[axis]-math.copysign(1,outward)*(p-center[axis]))
            corrected=[v-max(-.10,min(0,bias)) for v in m]
            samples.append(dict(run=root.name,t=c['t'],raw_m=m,truth_m=actual,
                corrected_m=corrected, residual_m=residual,
                differential_error_m=[v-w for v,w in zip(corrected,actual)],
                eligible=-.15<=residual<=0, action=c['action']))
    import numpy as np
    valid=[r for r in samples if r['eligible']]
    errors=[abs(v) for r in valid for v in r['differential_error_m']]
    bound=max(errors)
    cost=float(np.quantile([c['seconds'] for c in costs],.95,method='higher'))
    # Additional .10m axial travel at the existing .129m/s command rate.
    cost30=cost+.10/.129
    summary=dict(schema='ugrp.release23.calibration.v1', scope='offline saved evidence; correlated A/B, not independent trials',
        source_shas=sorted(shas),
        samples_N=len(samples), eligible_N=len(valid), error_bound_m=bound,
        error_bound_policy='maximum absolute corrected-minus-true end-center residual on eligible saved same-round observations; empirical, no distribution-free guarantee',
        differential_error_abs_quantiles_m={str(q):float(np.quantile(errors,q,method='higher')) for q in (.5,.95,.99,1)},
        leg_cost_p95_s=cost, leg_cost30_p95_s=cost30,
        tail_max_s=max(tails), cycle_N=len(costs),
        rejection_reason_table=[dict(category=k,count=v,blocking_object='episode SIM cap' if k=='cap_end' else 'cumulative issued yaw budget 18deg' if k=='release17_motion_cap' else 'own camera FOV boundary',minimum_gap=-.0008407346410206351 if k=='release17_motion_cap' else None,unit='rad' if k=='release17_motion_cap' else 'SIM s' if k=='cap_end' else 'pixel',unknown_reason='legacy event omits numeric gap' if k!='release17_motion_cap' else None) for k,v in rejection.most_common()],
        episode_funnel=[dict(gate=k,cumulative_passed=episode[k],rejected=episode['attempted']-episode[k]) for k in ('attempted','audit_zero','success')],
        observation_funnel=[dict(gate='same_round_localized_pair',cumulative_passed=len(samples),rejected=0),dict(gate='common_mode_residual_domain',cumulative_passed=len(valid),rejected=len(samples)-len(valid))],
        event_funnel=dict(line), raw_sources=sources,
        reproduce="ssh gcp1 'cd /home/ugrp/ugrp-sim/src/46afd8b095e74954439f98b28f2aa52af3eaea01 && PYTHONPATH=. .venv-sim/bin/python /home/ugrp/ugrp-sim/ops-reviews/release23/analyze_baseline.py --out /home/ugrp/ugrp-sim/ops-reviews/release23'")
    summary['false_accepts_after_bound']=sum(min(v-bound for v in r['corrected_m'])>=.04 and min(r['truth_m'])<.04 for r in valid)
    out.mkdir(parents=True,exist_ok=True)
    for name,value in [('calibration.json',summary),('samples.json',samples),('cycle-costs.json',costs)]:
        (out/name).write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('raw_sources',)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    analyze(p.parse_args().out)
