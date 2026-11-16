"""Conditional navigation replay at the recorded failure. No GT/physics.

Own pose/observations remain from egomap28 regardless of alternative commands.
This verifies action lifecycle, not a counterfactual trajectory or map precision.
Information-gain forecasting/RBPF are held as recorded, not resimulated.
"""
import json,sys,hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/rbpf-wide-confirm-v1/new-seed')
OUT=Path('/Users/changmin/projects/ugrp/outputs/active-recovery-v1')
from harness.active_wall_recovery import make_mapper,OPTION
from harness.active_wall_mapping import pulse_command
from harness.active_camera import SEARCH
from harness.public_navigation_unknown import from_observed_grid
from harness.public_navigation_recovery import issued_twist
from scripts.run_active_wall_wide import dump
load=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(l) for l in p.read_text().splitlines()]


def main():
    audits=load(OUT/'diagnostic-off/audits.json');failure=audits[4]
    snapshot=np.load(OUT/'diagnostic-off'/f"{failure['snapshot']}.npz")
    a=make_mapper('r3',1.3,SEARCH,active_mapping='frontier_rbpf_v1',active_recovery=OPTION)
    n=a.navigator
    # Restore known navigation map and own estimate at the first sustained failure.
    lo=np.rint(snapshot['origin']/.1).astype(int)
    yy,xx=np.nonzero(snapshot['raw']!=255)
    for y,x in zip(yy,xx):
        cell=tuple((lo+[x,y]).tolist());hit=snapshot['raw'][y,x]==254
        a.grid.odds[cell]=1. if hit else -1.;a.latest[cell]=bool(hit)
    for k,v in failure['before'].items():
        if k in ('target','frontier'):v=None if v is None else np.array(v)
        elif k=='blacklist':v=[np.asarray(p) for p in v]
        setattr(n,k,v)
    own={round(r['t'],6):r for r in rows(RAW/'frontend-covariances.jsonl')}
    traces=[];observations=rows(RAW/'own-contacts.jsonl')
    own_map_before=json.dumps(a.memory.self_map.export())
    for row in observations:
        if row['t']<44.1:continue
        t=row['t'];p=own[round(t,6)]['pose']
        # Set only recorded OWN estimate. No simulator/GT state is opened here.
        a.memory.self_map.poses[:]=p
        a.frames.append(row);wall=a._rays(row,a.pose)
        if n.clear_requested:a.clear_navigation(t)
        cost=from_observed_grid(a.grid,a.pose,a.latest,set())
        plan=n.update(cost,a.pose,t,static_goal=failure['supplied_goal'])
        # Same .2s controller cadence as ActiveMapper (base command counts .1s).
        if not n.phase and not n.failed and not n.finished:n.active_t+=.1
        command=n.command(cost,a.pose,plan,t)
        cmd,pulse=pulse_command(issued_twist(command),t,costmap=cost,pose=a.pose,core=n.core,points=wall)
        traces.append(dict(t=t,status=plan['status'],phase=n.phase,failed=n.failed,
            target=None if n.target is None else n.target.tolist(),command=cmd,blacklist=len(n.blacklist)))
    from collections import Counter
    summary=dict(input_start=44.1,frames=len(traces),hold=sum(t['command']['kind']=='hold' for t in traces),
        moving_requests=sum(t['command']['kind']!='hold' for t in traces),states=dict(Counter(t['status'] for t in traces)),
        permanent_failed_frames=sum(t['failed'] for t in traces),blacklists=sum(e['reason']=='ABORTED_goal_blacklisted' for e in n.events),
        selected_frontiers=sum(e['reason']=='frontier_selected' for e in n.events),resets=sum(e['reason']=='navigation_layer_reset' for e in n.events),
        first_non_hold=next((t['t'] for t in traces if t['command']['kind']!='hold'),None),
        qualification='Conditional navigation replay: recorded OWN poses/scans and initial requested goal fixed; commands never applied; no physical success or alternative map metrics claimed.')
    dump(OUT/'conditional-navigation.json',dict(summary=summary,trace=traces,events=n.events))
    dump(EXP/'results/conditional-navigation.json',summary)
    print(json.dumps(summary,indent=2),flush=True)
    assert summary['moving_requests']>0 and summary['permanent_failed_frames']==0
    assert summary['blacklists']>0 and summary['selected_frontiers']>0
    assert 'mujoco' not in sys.modules

if __name__=='__main__':main()
