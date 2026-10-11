"""Read-only, post-run/early-health evidence. Never supplies control observations."""
import json
import math
from pathlib import Path


def rows(path):
    if not path.exists():return []
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def jumps(poses):
    distances=[math.dist(a[:2],b[:2]) for a,b in zip(poses,poses[1:])]
    return dict(intervals=len(distances),over_5cm=sum(d>.05 for d in distances),
        over_20cm=sum(d>.20 for d in distances),max_m=max(distances,default=None))


def inspect(raw):
    raw=Path(raw);progress=raw/'e2e-progress.json'
    p=json.loads(progress.read_text()) if progress.exists() else {}
    own={r:rows(raw/f'robots/{r}/ownmap.jsonl') for r in ('r1','r2','r3')}
    actual={}
    for rid in own:
        positions=[row['robot_xyz_m'][:2] for row in rows(raw/f'eval_only/{rid}/trajectory.jsonl')]
        actual[rid]=max((math.dist(x,positions[0]) for x in positions),default=None)
    responses=[]
    from harness.llm_completion import assess_completion,normal_completion
    for path in sorted((raw/'wire').glob('*response.json')):
        response=json.loads(path.read_text());assessment=assess_completion(response,study_json=True)
        responses.append(dict(provider=response.get('provider'),normal=normal_completion(assessment),
            fence_removed=assessment['json_fence_removed'],jev=response.get('ugrp_jev')))
    resultpath=raw/'result.json'
    result=json.loads(resultpath.read_text()) if resultpath.exists() else {}
    moving=all(actual[r] is not None and actual[r]>.005 for r in ('r1','r2'))
    checks=dict(no_exceptions=not result.get('failure'),frames_increased=p.get('frames',0)>1,
        sim_time_increased=p.get('sim_s',0)>0,actual_translation=moving,
        deepinfra_normal=any(r['normal'] and r['provider']=='DeepInfra' for r in responses),
        ownmap_trace=all(len(own[r])>1 for r in ('r1','r2')),
        mapping_phase_entered=p.get('phase') not in (None,'boot'))
    return dict(progress=p,checks=checks,passed=all(checks.values()),actual_displacement_m=actual,
        command_kinds={r:sorted({x['command']['kind'] for x in own[r]}) for r in own},
        own_pose_frame_jumps={r:jumps([x['pose_own_m'] for x in own[r]]) for r in own},responses=responses,
        evaluation_only=True,feedback_to_controller=False)
