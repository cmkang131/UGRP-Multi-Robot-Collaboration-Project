"""gcp2 saved-input route/corridor analysis; never advances physics."""
import collections
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np

R=Path('/home/ugrp/ugrp-sim/runs')
SOURCE=R.parent/'src/cb8b37c2994f5c77bcfaea469341bf987c7d3779'
sys.path.insert(0,str(SOURCE))
from harness.reloc20_motion import LoadedRoute
from sim.solo_carry_obstacles import RGBObstacleMemory
from sim.grasp_act_visible_route import waypoint


def read(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'])
def obj(p):return json.loads(read(p))
def dist(x):return dict(N=len(x),min=min(x),p50=float(np.percentile(x,50)),p95=float(np.percentile(x,95)),max=max(x)) if x else dict(N=0)


def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    reports=[]
    for task in obj(R/'reloc20-round3/queue.json')['runs']:
        if task['kind']!='carry' or task['condition']!='candidate':continue
        raw=Path(task['raw']);d=obj(raw/'result.json');carry=d['teacher']['carry'];goal=carry['stand_off_xy']
        c=[json.loads(x) for x in read(raw/'teacher-commands.jsonl').splitlines()]
        travel=[x for x in c if x.get('phase_before',x['phase'])=='carry_to_zone']
        low={int(k):v for k,v in next(x['command']['pwm'] for x in c if x['phase']=='close').items()}
        static=obj(raw/'carry-static-map.json');plan=obj(raw/'plan.json');route=LoadedRoute(static);records=[]
        selected=travel[-601::50]
        for x in selected:
            p=x['map_pose']['pose_estimate'];route.update_load(True,plan['kind'],low,{int(k):v for k,v in x['command']['pwm'].items()})
            memory=RGBObstacleMemory();memory.tracks=x['carry_obstacles']['tracks'];discs=memory.discs(x['t'])
            route.disc_names=[f"own_rgb_{v['kind']}_track_{v.get('id',i)}" for i,v in enumerate(memory.tracks)]
            path=route.plan(p[:2],goal,static['bounds_m'],discs)
            target=waypoint(p[:2],path,discs,tuple(v for _,v in route.rects),route.radius) if path else None
            contexts=[route.segment(a,b,discs)[1] for a,b in zip(path or [],(path or [])[1:])]
            # Homotopy descriptor: side of each authored divider at its
            # closest path point. Exact path vertices were NOT saved live.
            signature=tuple((o['id'],1 if min(path,key=lambda q:abs(q[0]-o['center_m'][0]))[1]>=o['center_m'][1] else -1) for o in static['obstacles'] if path and 'divider' in o['id'])
            records.append(dict(t=x['t'],estimate=p,path_found=bool(path),homotopy=signature,
                remaining_route_m=sum(math.dist(a,b) for a,b in zip(path or [],(path or [])[1:])),
                remaining_direct_m=math.dist(p[:2],goal),target=target,
                target_distance_m=math.dist(p[:2],target) if target else None,
                minimum_gap_m=min((q['minimum_gap_m'] for q in contexts),default=None),
                blocked_object=min(contexts,key=lambda q:q['minimum_gap_m'])['blocked_object'] if contexts else route.last.get('blocked_object','unknown'),
                category='offline_route_replay',reason='strict_route_found' if path else route.last.get('reason','no_route')))
        repeated=[]
        for i in range(2,len(records)):
            a,b,z=records[i-2:i+1]
            if a['homotopy']==b['homotopy']==z['homotopy']:
                repeated.append(dict(start=a['t'],end=z['t'],same_route_class=True,progress_m=a['remaining_route_m']-z['remaining_route_m'],
                    below_existing_arrival_tolerance=a['remaining_route_m']-z['remaining_route_m']<.025))
        live=carry['reloc20_motion']['footprint']
        reports.append(dict(run=task['name'],raw=str(raw),source_sha=task['source_sha'],
            source_commands_sha256=hashlib.sha256(read(raw/'teacher-commands.jsonl')).hexdigest(),
            observed_live_funnel=live['plan_funnel'],observed_live_rejections=live['rejections'],
            replay_cumulative=dict(states=len(records),path_found=sum(x['path_found'] for x in records)),
            minimum_clearance_m=dist([x['minimum_gap_m'] for x in records if x['minimum_gap_m'] is not None]),
            short_target_distance_m=dist([x['target_distance_m'] for x in records if x['target_distance_m'] is not None]),
            same_route_triples=repeated,records=records))
    audit=obj(R/'reloc20-round3/full-plan-audit.json')['runs'];all_gaps=[v['context']['minimum_gap_m'] for x in audit for v in x['records']]
    result=dict(analysis_host=platform.node(),reproduce=f'{sys.executable} {__file__}',
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='saved permitted-input replay; same homotopy is not byte-identical live path; gap is enclosure geometry not measured physical passage',
        full_plan_cumulative=dict(slot_candidates=sum(len(x['records']) for x in audit),complete_plan_clear=sum(v['accepted'] for x in audit for v in x['records'])),
        full_plan_minimum_gap_m=dist(all_gaps),runs=reports)
    out=R/'reloc21-prior/route-replay.json';out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='runs'}))
    for x in reports:print(json.dumps({k:v for k,v in x.items() if k not in ('records','observed_live_rejections','same_route_triples')}), 'no_progress_triples',sum(v['below_existing_arrival_tolerance'] for v in x['same_route_triples']))


if __name__=='__main__':main()
