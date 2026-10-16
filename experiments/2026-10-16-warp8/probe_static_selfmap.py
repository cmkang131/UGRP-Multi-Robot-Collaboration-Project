"""gcp3 saved-view CSM diagnostic; prediction and scoring are separate processes."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys


def read(p):
    return json.loads(p.read_text() if p.exists() else
                      subprocess.check_output(['zstd', '-qdc', str(p)+'.zst']))


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p, x): p.write_text(json.dumps(x, indent=2, allow_nan=False)+'\n')


def setup(a):
    sys.path[:0] = [str(a.owner), str(a.owner/'scripts'), str(a.adapter/'scripts')]
    os.chdir(a.owner)


def robot_job(job):
    a, w, rid, frames = job
    setup(a)
    import cv2
    import numpy as np
    from harness.e2e_rgb_vo import between
    from release_reloc_static_selfmap import StaticReleaseSelfmap, OPTION
    cv2.setNumThreads(1)
    static = read(a.input/w['static'])
    loc = StaticReleaseSelfmap(static, read(a.owner/'experiments/2026-10-16-reloc16/colour-calibration.json'),
                              method='lk', registration=OPTION)
    previous_command = frames[0]['command_pose']
    folder = a.output/f"world-{w['world']:03d}-{rid}"
    folder.mkdir()
    rows, results = [], {}
    # Before = end of the existing first three-pan panorama (-60/0/+60),
    # after = end of all recorded repeat/recovery views. This reporting
    # checkpoint is the original script length, not an acceptance threshold.
    before_n = a.checkpoints['initial_panorama_view_count']
    for i, f in enumerate(frames):
        p = a.input/f['rgb']
        if sha(p) != f['rgb_sha256'] or f['rgb_sha256'] != f['recorded_rgb_sha256']:
            raise ValueError('OWN_RGB_CHANGED')
        servo = {int(k): int(v) for k, v in f['servo'].items()}
        if servo[1] <= 1600:
            raise ValueError('SPARSE_OPEN_VIEW_EXPECTED')
        rgb = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
        delta = between(previous_command, f['command_pose'])
        # All captures are emitted after the original own-issued .8s/1s
        # view wait, exceeding the owner's open-camera .25s settle interval.
        # This is no synthetic frame and makes no carry-camera claim.
        rows.append(loc.observe(f['t'], rgb, servo, command_delta=delta, settled=True))
        previous_command = f['command_pose']
        if i+1 == before_n:
            results['before'] = loc.register()
            dump(folder/'before.json', results['before'])
            print('registered before', w['world'], rid,
                  results['before']['registration']['reason'], flush=True)
    if 'before' not in results:
        raise ValueError('RECOVERY_BOUNDARY_MISSING')
    results['after'] = loc.register()
    dump(folder/'after.json', results['after'])
    dump(folder/'trajectory.json', rows)
    dump(folder/'own-walls.json', dict(segments=loc.segments, camera_origins=loc.origins))
    result = dict(world=w['world'], seed=w['seed'], rid=rid, views=len(rows),
                  before_n=before_n, results=results,
                  wall_views=sum(r['wall_hit_columns']>0 for r in rows),
                  wall_columns=sum(r['wall_hit_columns'] for r in rows),
                  motion_status=dict(Counter(r['lk']['status'] for r in rows)))
    dump(folder/'summary.json', result)
    print('registered after', w['world'], rid,
          results['after']['registration']['reason'], flush=True)
    return result


def predict(a):
    if not a.enabled: raise ValueError('EXPLICIT_OPTIONS_REQUIRED')
    if not Path(read(a.queue)['rejection_table']).is_file():
        raise ValueError('PRIOR_REJECTION_TABLE_REQUIRED')
    manifest = read(a.owner/'OWNER_BYTES.json')
    for n, r in manifest['files'].items():
        if sha(a.owner/n) != r['sha256']: raise ValueError('OWNER_BYTES_CHANGED:'+n)
    a.output.mkdir(parents=True, exist_ok=False)
    inputs = read(a.input/'own-inputs.json')
    a.checkpoints = read(a.checkpoint_file)
    jobs = [(a,w,r,frames) for w in inputs['worlds'] for r,frames in w['robots'].items()]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        results = list(pool.map(robot_job, jobs))
    dump(a.output/'predictions.json', dict(rows=results, truth_inputs=0, top_inputs=0,
        held_world_reads=0, physics_steps=0, scale=1, spawn_fallback=False,
        raw=str(a.input),owner_sha=manifest['mapbuild_sha'],
        scope='sparse open-gripper component; carry LK/loaded qualification/physical release unmeasured'))
    dump(a.output/'prediction-seal.json', dict(
        files={str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*.json')},
        inputs_sha256=sha(a.input/'own-inputs.json') if (a.input/'own-inputs.json').exists() else
            hashlib.sha256(subprocess.check_output(['zstd','-qdc',str(a.input/'own-inputs.json')+'.zst'])).hexdigest(),
        checkpoints_sha256=sha(a.checkpoint_file), owner_manifest_sha256=sha(a.owner/'OWNER_BYTES.json'),
        adapter_sha256=sha(a.adapter/'scripts/release_reloc_static_selfmap.py'),
        truth_inputs=0, physics_steps=0, reproduction=sys.argv))


def score(a):
    for n,h in read(a.output/'prediction-seal.json')['files'].items():
        if sha(a.output/n)!=h:raise ValueError('PREDICTION_CHANGED')
    d = read(a.output/'predictions.json'); truth = read(a.input/'eval-only.json')['rows']
    req = read(a.requirements)
    rows, reasons = [], Counter()
    def compose(a,b):
        c,s=math.cos(a[2]),math.sin(a[2])
        return [a[0]+c*b[0]-s*b[1],a[1]+s*b[0]+c*b[1],a[2]+b[2]]
    def error(pose,target):
        return dict(xy_m=math.dist(pose[:2],target[:2]),
            yaw_deg=math.degrees(abs(math.atan2(math.sin(pose[2]-target[2]),math.cos(pose[2]-target[2])))))
    for r in d['rows']:
        ev = [e for e in truth if e['world']==r['world'] and e['rid']==r['rid']]
        item = dict(world=r['world'], rid=r['rid'], seed=r['seed'], scores={})
        for phase,n in [('before',r['before_n']),('after',r['views'])]:
            pred = r['results'][phase]; reason=pred['registration']['reason'];reasons[reason]+=1
            target=ev[n-1]['truth_pose'];pose=pred['map_pose']
            xy=yaw=joint=None;passed=False
            if pose is not None:
                xy=math.dist(pose[:2], target[:2])
                yaw=abs(math.atan2(math.sin(pose[2]-target[2]),math.cos(pose[2]-target[2])))
                h=req['handoff'];joint=yaw+math.atan2(xy,h['nominal_target_range_m']-xy)
                passed=xy<=h['position_error_m'] and joint<=h['yaw_error_rad']
            item['scores'][phase]=dict(accepted=pose is not None,reason=reason,
                error_xy_m=xy,error_yaw_deg=None if yaw is None else math.degrees(yaw),
                joint_error_deg=None if joint is None else math.degrees(joint),
                requirement_pass=passed,wrong_acceptance=pose is not None and not passed,
                error_status='measured' if pose is not None else 'unregistered_no_world_pose')
            proposal=pred['registration'].get('best_candidate')
            item['scores'][phase]['proposal_error_evaluation_only']=(None if proposal is None else
                error(compose(proposal,pred['own_pose']),target))
            # Initial SE2 is used here only to score relative drift. It is
            # never returned to the estimator or counted as map acquisition.
            item['scores'][phase]['initial_SE2_relative_drift_evaluation_only']=error(
                compose(ev[0]['truth_pose'],pred['own_pose']),target)
        rows.append(item)
    counts={phase:dict(attempts=len(rows),accepted=sum(r['scores'][phase]['accepted'] for r in rows),
        ambiguous_none=sum(r['scores'][phase]['reason']=='ambiguous_modes' for r in rows),
        rejected_none=sum(not r['scores'][phase]['accepted'] for r in rows),
        wrong_acceptances=sum(r['scores'][phase]['wrong_acceptance'] for r in rows),
        requirement_pass=sum(r['scores'][phase]['requirement_pass'] for r in rows))
        for phase in ('before','after')}
    world_pass=sum(all(r['scores']['after']['requirement_pass'] for r in rows if r['world']==w) for w in range(14))
    summary=dict(schema='ugrp.warp8f.static_selfmap.v1',host='gcp3',world_n=14,robot_n=28,
        views=sum(r['views'] for r in d['rows']),counts=counts,reason_counts=dict(reasons),
        world_pass_n=world_pass,offline_error_gate_pass=world_pass==14,
        physical_release_ready=False,release_A40_submitted=False,release_B40_submitted=False,
        requirements_sha256=sha(a.requirements),handoff_requirements=req['handoff'],
        truth_scope='scorer only after prediction seal; no alignment/fallback supplied to estimator',
        loaded_camera_qualified=False,carry_LK_qualified=False,owner_actual_route_ready=False,
        physics_steps=0,model_calls=0,legacy_floor_line_calls=0,
        raw=str(a.output),reproduction=sys.argv)
    dump(a.output/'error-table.json',dict(rows=rows))
    dump(a.output/'summary.json',summary)
    stages=[]
    # Robot-level cumulative funnel; input/feature counts are parallel diagnostics.
    prev=28
    for name,n in [('saved_robot_streams',28),('CSM_attempted',28),
                   ('CSM_accepted',counts['after']['accepted']),
                   ('handoff_error_requirement',counts['after']['requirement_pass'])]:
        stages.append(dict(stage=name,cumulative_pass_n=n,rejected_n=prev-n));prev=n
    dump(a.output/'rejection_table.json',dict(stages=stages,counts=counts,
        reasons=[dict(category='static_wall_registration',reason=k,count=v,
            blocking_object='authored_wall_geometry',minimum_gap_m=None,gap_status='not_measured') for k,v in reasons.items()],
        raw=str(a.output),reproduction=sys.argv,requirements_sha256=sha(a.requirements),
        attempts_unit='before+after robot registrations; 56 total',world_pass_n=world_pass))
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['predict','score'],required=True)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--workers',type=int,default=4)
    for k in ('owner','adapter','input','output','queue','checkpoint-file','requirements'):
        p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    if socket.gethostname().split('.')[0]!='ugrp-act-l4-gcp3':raise ValueError('GCP3_ONLY')
    os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    (predict if a.stage=='predict' else score)(a)
