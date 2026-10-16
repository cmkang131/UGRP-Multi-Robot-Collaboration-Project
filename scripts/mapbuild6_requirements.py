"""Pre-score requirements from saved teacher ledgers and authored map geometry.

Run on gcp5. No simulator, image, new trajectory or estimator result is read.
Teacher coverage is a task envelope, never proof of student robustness.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('GCP5_ONLY')
    import numpy as np
    rows=[]
    for plan in sorted(a.ledgers.glob('*/plan.json')):
        result=plan.with_name('result.json.zst')
        d=json.loads(plan.read_text()); d=d['episodes'][0] if 'episodes' in d else d
        outcome=json.loads(subprocess.check_output(['zstd','-dc',str(result)]))
        if not (outcome['physical_success'] and outcome['lift_success'] and outcome['release_success']):
            raise ValueError('REFERENCE_SUCCESS_REQUIRED')
        x,y,z,yaw=d['spawns']['r1']; cx,cy,_=d['cargo_pose_m']
        bearing=math.atan2(cy-y,cx-x)
        rows.append(dict(seed=d['seed'],relative_xy=[x-cx,y-cy],
            facing_error_rad=math.atan2(math.sin(yaw-bearing),math.cos(yaw-bearing)),
            handoff_pose_error=d['handoff_pose_error'],plan=str(plan),plan_sha256=sha(plan),
            result=str(result),result_sha256=sha(result),kind=d['kind']))
    if len(rows)!=40:
        raise ValueError('EXACT_EXISTING_40_LEDGER_REQUIRED')
    xy=np.array([r['relative_xy'] for r in rows]); nominal=np.median(xy,axis=0)
    residual=np.linalg.norm(xy-nominal,axis=1)
    yaw=np.abs([r['facing_error_rad'] for r in rows])
    injected=np.array([r['handoff_pose_error'] for r in rows])
    static=json.loads(a.static.read_text())
    # The slot half-extent is the declared landing area, not the 0.4m
    # nearest-slot classification limit. Report both instead of conflating.
    slots=static['zone_slots']; slot=min(v for ss in slots.values() for r in ss for v in r['half_extents_m'])
    spacing=min(math.dist(x['center_m'],y['center_m']) for ss in slots.values()
                for i,x in enumerate(ss) for y in ss[i+1:])
    region=min(min(r['half_extents_m']) for k,r in static['regions'].items() if k.startswith('zone_'))
    box_half=a.box_half
    result=dict(schema='ugrp.mapbuild6.requirements.v1',frozen_before_recording=True,
        source_teacher=dict(cohort='solo_truth_free_gate_v1 79800-79839; historical CPU teacher only',
            host='gcp1 archived Mac copies; VM never accessed',source_sha='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8',
            native87420_87459='not locally retrieved; fallback existing teacher ledgers authorized by user',
            scope='separate requirement evidence, not pooled performance, not native/student success'),
        handoff=dict(n=40,nominal_relative_xy_m=nominal.tolist(),
            position_error_m=float(np.percentile(residual,95)),yaw_error_rad=float(np.percentile(yaw,95)),
            position_quantiles_m={str(q):float(np.percentile(residual,q)) for q in (5,50,95,100)},
            facing_quantiles_deg={str(q):float(np.degrees(np.percentile(yaw,q))) for q in (5,50,95,100)},
            definition='P95 norm of successful authored handoff-start XY minus median relative XY; P95 absolute yaw minus target bearing',
            limitation='marginal empirical teacher support only; joint support/student acceptance unverified',
            release_injected_pose_p95_m=float(np.percentile(np.linalg.norm(injected[:,:2],axis=1),95)),
            release_injected_yaw_p95_rad=float(np.percentile(abs(injected[:,2]),95))),
        arrival=dict(slot_center_error_m=slot,nearest_slot_identity_error_m=spacing/2,
            cargo_inside_zone_center_error_m=region-box_half,box_half_m=box_half,
            yaw_error_rad=None,yaw_status='square box/zone has no separate yaw requirement; evaluate rotated footprint geometrically'),
        passage=dict(definition='abs(lateral SE2 error) + a*abs(sin(yaw error))+b*abs(cos(yaw error)) <= width/2',
            robot_half_length_m=None,robot_half_width_m=None,
            footprint_status='must derive original folded collision footprint at setup; no guessed robot radius',
            passages=static['passages']),
        static=dict(path=str(a.static),sha256=sha(a.static)),teacher_rows=rows,
        decision=['both meet every applicable task requirement and complete route: LK default, RBPF off',
            'LK fails and RBPF meets every requirement and completes route: RBPF',
            'both fail: reason distribution then proposal only; no tuning this round',
            'missing required route/event/loaded evidence: NOT_READY, no default adoption'],
        scoring=dict(reference='chassis centre SE(2)',alignment='one initial SE2 only; scale=1',
            metrics=['handoff/arrival/door XY+yaw','path-normalized drift percent','return/lookaround before-after','maximum'],
            camera_center='reference column only'),round_limit=3)
    dump(a.output,result)
    print(json.dumps({k:result[k] for k in ('handoff','arrival','decision')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('ledgers','static','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--box-half',type=float,required=True,help='original sim.zone_arena.BOX_HALF geometry, not fitted')
    main(p.parse_args())
