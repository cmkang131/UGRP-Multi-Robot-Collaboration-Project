#!/usr/bin/env python3
"""Independent arithmetic/count validation of exported per-frame diagnostics."""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parent
summary = json.loads((P/'summary.json').read_text())
episodes = json.loads((P/'episodes.json').read_text())
counts = defaultdict(Counter)
mins = {}
conditional = defaultdict(lambda:defaultdict(Counter))
ready_margins = defaultdict(list)
position_fail_bins = defaultdict(Counter)
seen = set()
n = 0
with gzip.open(P/'frame-metrics.csv.gz','rt') as f:
    for r in csv.DictReader(f):
        arm, world, t = r['arm'], int(r['world']), float(r['t'])
        key=(arm,world,t)
        assert key not in seen
        seen.add(key)
        n+=1
        d1,d2=float(r['r1_d_m']),float(r['r2_d_m'])
        y1,y2=float(r['r1_yaw_rad']),float(r['r2_yaw_rad'])
        # Independently form max BEFORE subtracting 1, directly as requested.
        m=max(d1/.03,d2/.03,y1/.06,y2/.06)-1
        assert m==float(r['m'])
        geo=max(d1,d2)<=.03 and max(y1,y2)<=.06
        ready=r['r1_stage']=='ready' and r['r2_stage']=='ready'
        protocol=r['r1_protocol_ready']=='True' and r['r2_protocol_ready']=='True'
        assert geo==(r['joint_geometry']=='True')
        assert ready==(r['joint_policy_ready']=='True')
        c=counts[arm]
        c['frames']+=1
        c['alignment_frames']+=geo
        c['joint_ready_frames']+=ready
        c['joint_protocol_ready_frames']+=protocol
        c['aligned_and_ready_frames']+=geo and ready
        c['aligned_and_protocol_ready_frames']+=geo and protocol
        c['joint_policy_vs_protocol_ready_mismatch_frames']+=ready!=protocol
        if ready:ready_margins[arm].append(dict(world=world,t=t,m=m))
        if (arm,world) not in mins or m<mins[arm,world]['m']:
            mins[arm,world]=dict(m=m,t=t)
        for rid,d,y in [('r1',d1,y1),('r2',d2,y2)]:
            local=d<=.03 and y<=.06
            rdy=r[rid+'_stage']=='ready'
            c['local_aligned_robot_ticks']+=local
            c['ready_robot_ticks']+=rdy
            c['local_geo_and_ready_robot_ticks']+=local and rdy
            c['premature_ready_local_geometry_n']+=rdy and not local
            c['pre_local_geometry_robot_ticks']+=not local
            for key in ['wheel_nonzero','software_hold','permit']:
                cond=conditional[arm][key+'='+r[rid+'_'+key]]
                cond['N']+=1
                cond['READY']+=rdy
for arm,c in counts.items():
    for k,v in c.items(): assert summary['arms'][arm]['counts'][k]==v,(arm,k)
for ep in episodes:
    best=mins[ep['arm'],ep['world']]
    assert best['m']==ep['min_joint_margin_frame']['margin']
    assert best['t']==ep['min_joint_margin_frame']['t']
extras={}
for arm in ['C','S']:
    ee=[e for e in episodes if e['arm']==arm]
    paired=[e for e in ee if all(v['ready_frames']>0 for v in e['robots'].values())]
    ready_runs=[span for e in ee for v in e['robots'].values() for span in v['ready_spans']]
    q=lambda s:dict(n=len(s),min=min(s) if s else None,max=max(s) if s else None)
    extras[arm]=dict(
        both_robots_ready_at_some_time_worlds=[e['world'] for e in paired],
        each_ever_ready_but_not_joint_worlds=[e['world'] for e in paired if e['counts']['joint_ready_frames']==0],
        ready_runs=q([r['samples'] for r in ready_runs]),
        issued_command_conditionals={k:dict(v,rate=v['READY']/v['N']) for k,v in conditional[arm].items()},
        joint_ready_margin_frames=ready_margins[arm],
        nearest_failed_episode_world=min((e for e in ee if e['min_joint_margin_frame']['margin']>0),key=lambda e:e['min_joint_margin_frame']['margin'])['world'])
manifest=json.loads((P/'source-manifest.json').read_text())
for path,v in manifest.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==v['sha256'],path
out=dict(status='PASS',utc=datetime.now(timezone.utc).isoformat(),
    independent_frame_formula_checks=n,independent_episode_minimum_checks=len(episodes),
    all_used_input_hashes_rechecked=len(manifest),aggregate_count_checks=sum(len(c) for c in counts.values()),
    extras=extras,scope='CPU arithmetic only; exported rows independently recomputed; raw geometry was checked against original geometry() and stored flags by analyze.py')
(P/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='extras'}))
