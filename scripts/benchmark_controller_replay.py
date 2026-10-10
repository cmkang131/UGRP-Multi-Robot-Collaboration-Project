"""Finite, serial ABBA replay; acquire the shared timing slot after S3 returns it.

This measures saved-input controller work, including serialization and writes.
It is not an online physics/mission performance test. Originals are read-only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

from harness.lossless_recording import logical_equal, logical_open
from scripts.profile_controller_replay import ROOT, acquire_slot, sha, source_check, write

ORDER = ('A', 'B', 'B', 'A')
S3_FILES = ('commands.json', 'state.json', 'record.json')
EGO_FILES = tuple(name+'.json' for name in (
    'commands','traces','state','route-map','frontend-grid','frontend-ledger','decisions',
    'graphs','navigation','heading-decisions','utility-events','own-inputs',
    'return-navigation','frontend-poses','active-events','all-particle-maps')) + (
    'own-controller.jsonl','own-contacts.jsonl','frontend-covariances.jsonl','online-maps.jsonl')


def priority_check(receipt, expected_run=None):
    data = json.loads(receipt.read_text())
    result = Path(data['result_path'])
    if expected_run is not None and result != Path(expected_run)/'result.json':
        raise ValueError('CURRENT_S3_RUN_REQUIRED')
    if data.get('released_for_speedctrl') is not True or not data.get('coordination_url','').startswith('https://github.com/'):
        raise ValueError('EXPLICIT_S3_RETURN_REQUIRED')
    if not result.is_file() or sha(result) != data['result_sha256']:
        raise ValueError('S3_COMPLETION_HASH_REQUIRED')
    if not isinstance(json.loads(result.read_text()), dict):
        raise ValueError('S3_RESULT_REQUIRED')
    return data


def compare_runs(paths, kind):
    files = S3_FILES if kind == 's3' else EGO_FILES
    checked = []
    for name in files:
        matches = [logical_equal(paths[0]/name, p/name) for p in paths[1:]]
        checked.append(dict(name=name, equal=all(matches), comparisons=matches))
    results = [json.loads((p/'result.json').read_text()) for p in paths]
    inputs_equal = all(r['input_sha256'] == results[0]['input_sha256'] for r in results)
    complete = all(r['failure'] is None and r['frames'] == r['available_frames'] for r in results)
    return dict(verified=all(x['equal'] for x in checked) and inputs_equal and complete,
                files=checked, input_hashes_equal=inputs_equal, completed_callbacks=complete,
                scope='direct decoded behavior bytes; per-frame particle-array hashes and full RNG state; final maps',
                excluded=('timing, load, profile, implementation/adapter/storage provenance',))


def load_assessment(paths, *, absolute=.5, relative=.25):
    means = []
    for path in paths:
        samples = json.loads((path/'trend.json').read_text())
        means.append(statistics.fmean(row['loadavg'][0] for row in samples))
    a = statistics.fmean(means[i] for i in (0,3))
    b = statistics.fmean(means[i] for i in (1,2))
    tolerance = max(absolute, relative*min(a,b))
    # Reject transient mismatch between adjacent crossover arms as well.
    adjacent = [abs(means[i]-means[j]) <= max(absolute,relative*min(means[i],means[j]))
                for i,j in ((0,1),(2,3))]
    return dict(mean_1min=means, A=a, B=b, tolerance=tolerance,
                comparable=abs(a-b)<=tolerance and all(adjacent),
                rule='both crossover pairs and aggregate: |A-B| <= max(0.5, 0.25*min(A,B))',
                limitation='load average is a host-load proxy, not identical scheduling or cache state')


def components(paths):
    result = []
    for index,path in enumerate(paths):
        r = json.loads((path/'result.json').read_text())
        duration = r['end']-r['start']
        result.append(dict(order=index+1,arm=ORDER[index],frames=r['frames'],sim_s=duration,
            wall_per_input_sim=r['wall_per_input_sim'],wall_s=r['wall_s'],
            exclusive={k:v['exclusive_s']/duration for k,v in r['timers'].items()},
            calls={k:v['calls'] for k,v in r['timers'].items()},
            cache=r['speedups'], storage=json.loads((path/'record-storage.json').read_text())))
    return result


def estimated_trajectory(path, *, frame='frontend'):
    """Saved frontend, or its actual held online map->odom transform.

    Graph transforms are applied only from their recorded timestamp onward;
    no interpolation or final correction of earlier online states is invented.
    """
    if frame not in ('frontend','online_map'):raise ValueError('UNKNOWN_TRAJECTORY_FRAME')
    with logical_open(path/'frontend-poses.json') as stream:poses=json.load(stream)
    if frame=='frontend':return poses
    with logical_open(path/'graphs.json') as stream:graphs=json.load(stream)
    if any(b['t']<a['t'] for a,b in zip(graphs,graphs[1:])):raise ValueError('UNORDERED_GRAPH_TRANSFORMS')
    transform=[0.,0.,0.];index=0
    for row in poses:
        while index<len(graphs) and graphs[index]['t']<=row['t']:
            transform=graphs[index]['map_to_odom'];index+=1
        if len(transform)!=3 or not all(math.isfinite(v) for v in transform):
            raise ValueError('INVALID_MAP_TRANSFORM')
        x,y,yaw=row['pose'];tx,ty,angle=transform;c,s=math.cos(angle),math.sin(angle)
        row['pose']=[tx+c*x-s*y,ty+s*x+c*y,math.atan2(math.sin(angle+yaw),math.cos(angle+yaw))]
    return poses


def pose_difference(baseline, candidate, *, frame='frontend'):
    """Estimated frontend trajectory deltas; no truth is provided to the runner."""
    old,new=estimated_trajectory(baseline,frame=frame),estimated_trajectory(candidate,frame=frame)
    if len(old) != len(new) or [x['t'] for x in old] != [x['t'] for x in new]:
        return dict(comparable=False, reason='estimated_trajectory_stamps_differ')
    import numpy as np
    delta = np.asarray([x['pose'] for x in new])-np.asarray([x['pose'] for x in old])
    if not len(delta):
        return dict(comparable=False,reason='empty_trajectory')
    yaw = np.arctan2(np.sin(delta[:,2]),np.cos(delta[:,2]))
    with logical_open(baseline/'commands.json') as a, logical_open(candidate/'commands.json') as b:
        commands_a,commands_b = json.load(a),json.load(b)
    return dict(comparable=True, samples=len(delta), xy_rmse_delta_m=float(np.sqrt(np.mean(np.sum(delta[:,:2]**2,axis=1)))),
        xy_max_delta_m=float(np.linalg.norm(delta[:,:2],axis=1).max()),yaw_rmse_delta_rad=float(np.sqrt(np.mean(yaw*yaw))),
        generated_commands_equal=commands_a==commands_b,
        trajectory_frame=frame,
        scope='same archived inputs and issued commands; estimated trajectory delta, not absolute accuracy or closed-loop success')


def trajectory_accuracy(path, raw, *, frame='frontend'):
    """Evaluation after replay only; simulator truth never enters the controller."""
    import numpy as np
    source=raw/'eval_only/trajectory.jsonl'
    setup=raw/'eval_only/setup.json'
    manifest=json.loads((raw/'artifacts.sha256.json').read_text());manifest=manifest.get('files',manifest)
    if any(manifest.get(str(p.relative_to(raw)))!=sha(p) for p in (source,setup)):
        raise ValueError('EVAL_INPUT_HASH')
    truth={round(r['t'],9):r for r in (json.loads(line) for line in source.read_text().splitlines())}
    spawn=json.loads(setup.read_text())['spawns']['r3']
    origin=np.array(spawn[:2]);yaw=spawn[3]
    world_to_own=np.array([[math.cos(yaw),math.sin(yaw)],[-math.sin(yaw),math.cos(yaw)]])
    estimates=estimated_trajectory(path,frame=frame)
    errors=[]
    for estimate in estimates:
        value=truth.get(round(estimate['t'],9))
        if value is None:
            raise ValueError('EVAL_TIMESTAMP_MISSING: no invented truth/interpolation')
        expected=np.r_[world_to_own@(np.asarray(value['robot_xyz_m'][:2])-origin),value['robot_yaw_rad']-yaw]
        delta=np.asarray(estimate['pose'])-expected
        delta[2]=math.atan2(math.sin(delta[2]),math.cos(delta[2]))
        errors.append(delta)
    if not errors:
        return dict(available=False,reason='no estimated trajectory')
    error=np.asarray(errors)
    return dict(available=True,samples=len(error),xy_rmse_m=float(np.sqrt(np.mean(np.sum(error[:,:2]**2,axis=1)))),
        yaw_rmse_rad=float(np.sqrt(np.mean(error[:,2]**2))),xy_max_m=float(np.linalg.norm(error[:,:2],axis=1).max()),
        trajectory_frame=frame,gt_use='posthoc evaluation only; immutable saved spawn defines own odom frame',
        source_hashes={str(source):sha(source),str(setup):sha(setup)})


def referee_abba(raw, output, args):
    """Replay finalized evaluator events only; never deliver truth to control."""
    from harness import controller_exact_speedups as acceleration
    from harness.zone_study_referee import Referee
    source=raw/'eval_only/referee.json'
    manifest=json.loads((raw/'artifacts.sha256.json').read_text())
    manifest=manifest.get('files',manifest)
    digest=sha(source)
    if manifest['eval_only/referee.json']!=digest:
        raise ValueError('REFEREE_INPUT_HASH')
    archived=json.loads(source.read_text());events=archived['events'];first=events[0]
    assert first['event']=='orders' and all(r['event']=='sample' for r in events[1:])
    output.mkdir(exist_ok=False)
    runs=[];paths=[]
    old_env={name:os.environ.get(name) for name in (acceleration.REFEREE_ENV,acceleration.SCAN_ENV)}
    try:
        for index,arm in enumerate(ORDER,1):
            source_check(args.expected_source_sha)
            if time.monotonic()>=args.deadline:raise TimeoutError('FINITE_ABBA_BUDGET')
            out=output/(str(index)+'-'+arm);out.mkdir(exist_ok=False);paths.append(out)
            os.environ[acceleration.REFEREE_ENV]='off' if arm=='A' else 'owned-v1'
            os.environ[acceleration.SCAN_ENV]='off'
            installed=acceleration.install('exact-v1')
            loads=[];started=time.perf_counter()
            try:
                judge=Referee(first['orders'],first['static_map'],evidence_key=first['evidence_key'])
                for j,row in enumerate(events[1:]):
                    judge.observe(row['sim_s'],row['items'])
                    if j%1000==0:loads.append(os.getloadavg())
                record=judge.record()
                receipts=[]
                write(out/'record.json',record,ensure_ascii=False,
                      storage='off' if arm=='A' else 'gzip-v1',receipts=receipts)
                wall=time.perf_counter()-started
                runs.append(dict(order=index,arm=arm,wall_s=wall,samples=len(events)-1,
                    source_sha=args.expected_source_sha,source_run_sha=json.loads((raw/'bundle.json').read_text())['source_sha'],
                    input_sim_s=events[-1]['sim_s']-events[1]['sim_s'],loadavg_samples=loads,
                    speedups=installed.snapshot(),storage=receipts))
            finally:installed.close()
            write(out/'result.json',runs[-1])
    finally:
        for name,value in old_env.items():
            if value is None:os.environ.pop(name,None)
            else:os.environ[name]=value
    means=[statistics.fmean(x[0] for x in r['loadavg_samples']) for r in runs]
    a,b=(statistics.fmean(means[i] for i in group) for group in ((0,3),(1,2)))
    comparable=abs(a-b)<=max(.5,.25*min(a,b)) and all(
        abs(means[i]-means[j])<=max(.5,.25*min(means[i],means[j])) for i,j in ((0,1),(2,3)))
    proof=all(logical_equal(paths[0]/'record.json',p/'record.json') for p in paths[1:])
    result=dict(runs=runs,bytes_identical=proof,load_comparable=comparable,mean_1min=means,
        original=dict(path=str(source),sha256=digest),physics_runs=0,controller_feedback=False,
        scope='separate finalized S3 v151 evaluator-event replay; not v148 controller timing or online mission')
    write(output/'comparison.json',result)
    if not proof:raise RuntimeError('REFEREE_BEHAVIOR_BYTES_DIFFER')
    return result


def invoke(case, output, args, *, scan, storage, local=0.):
    source_check(args.expected_source_sha)
    if shutil.disk_usage(output.parent).free < 10*2**30:
        raise RuntimeError('HOST_ERROR: disk below 10 GiB; originals preserved')
    budget = args.deadline-time.monotonic()
    if budget <= 0:
        raise TimeoutError('FINITE_ABBA_BUDGET')
    command = [sys.executable,'-m','scripts.sim_cli','workflow','run','controller-replay-profile',
        '--record',str(output.parent/(output.name+'-managed')),'--timeout',str(min(5400.,budget)), '--',
        '--kind',case['kind'],'--raw',case['raw'],'--adapter',case['adapter'],
        '--output',str(output),'--expected-source-sha',args.expected_source_sha,
        '--lock-owner-pid',str(os.getpid()),'--execute','--speedups','exact-v1',
        '--scan-speedups',scan,'--record-storage',storage,'--local-submap-m',str(local),
        '--referee-speedups','off' if scan=='off' else 'owned-v1',
        '--visibility-speedups','off' if scan=='off' else 'shared-v1',
        '--detail-timers']
    if args.profile:
        command += ['--profile']
    with (output.parent/(output.name+'.log')).open('xb') as log:
        subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--priority-receipt',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--budget-s',type=float,default=21600.)
    p.add_argument('--profile',action='store_true')
    p.add_argument('--diagnostic-profile',action='store_true',help='separate profiled B replay after unprofiled ABBA')
    p.add_argument('--referee-abba',action='store_true',help='separate evaluator-event ABBA from finalized priority run')
    p.add_argument('--local-submap-m',type=float,default=0.)
    p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    if not math.isfinite(args.budget_s) or not 0<args.budget_s<=21600:
        p.error('budget must be finite and <=21600 seconds')
    if not math.isfinite(args.local_submap_m) or not 0<=args.local_submap_m<=6:
        p.error('local radius must be finite and in [0,6]')
    plan=json.loads(args.plan.read_text())
    if not args.execute:
        print(json.dumps(dict(execution_started=False,order=ORDER,cases=plan['cases'],physics_runs=0)))
        return
    source_check(args.expected_source_sha)
    assert int(subprocess.check_output(['ps','-o','ni=','-p',str(os.getpid())]))==0
    priority=priority_check(args.priority_receipt,plan['priority_run'])
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'plan.json',dict(plan=plan,plan_sha256=sha(args.plan),source=args.expected_source_sha,
        order=ORDER,priority=priority,profile=args.profile,local_submap_m=args.local_submap_m))
    args.deadline=time.monotonic()+args.budget_s
    held,owned=acquire_slot(args.expected_source_sha,'speedctrl2 serial ABBA saved inputs; physics0',
        wait_s=min(7200,args.budget_s),expected_minutes=math.ceil(args.budget_s/60))
    report=dict(schema='ugrp.controller_abba.v1',source=args.expected_source_sha,cases=[],complete=False)
    try:
        for case in plan['cases']:
            paths=[]
            for index,arm in enumerate(ORDER):
                output=args.output/(case['id']+'-'+str(index+1)+'-'+arm)
                print(f"ABBA {case['id']} {index+1}/4 {arm}",flush=True)
                invoke(case,output,args,scan='off' if arm=='A' else 'exact-v2',storage='off' if arm=='A' else 'gzip-v1')
                paths.append(output)
            proof=compare_runs(paths,case['kind'])
            rows=components(paths)
            load=load_assessment(paths)
            a=statistics.fmean(rows[i]['wall_per_input_sim'] for i in (0,3))
            b=statistics.fmean(rows[i]['wall_per_input_sim'] for i in (1,2))
            entry=dict(id=case['id'],measurement_source=args.expected_source_sha,paths=[str(p) for p in paths],
                proof=proof,components=rows,load=load,A_wall_per_input_sim=a,
                B_wall_per_input_sim=b,percent_saved=(100*(a-b)/a if proof['verified'] and load['comparable'] else None))
            report['cases'].append(entry)
            write(args.output/(case['id']+'-comparison.json'),entry)
            if not proof['verified']:
                raise RuntimeError('BEHAVIOR_BYTES_DIFFER: default-on adoption refused')
        if args.diagnostic_profile:
            profile_args=argparse.Namespace(**{**vars(args),'profile':True})
            for case in plan['cases']:
                output=args.output/(case['id']+'-profile')
                invoke(case,output,profile_args,scan='exact-v2',storage='gzip-v1')
                entry=next(c for c in report['cases'] if c['id']==case['id'])
                reference=args.output/(case['id']+'-2-B')
                entry['diagnostic_profile']=dict(result=json.loads((output/'result.json').read_text()),
                    proof=compare_runs([reference,output],case['kind']))
                if not entry['diagnostic_profile']['proof']['verified']:
                    raise RuntimeError('PROFILE_BEHAVIOR_BYTES_DIFFER')
        if args.local_submap_m:
            for case in plan['cases']:
                if case['kind']!='egomap':continue
                output=args.output/(case['id']+'-local')
                invoke(case,output,args,scan='exact-v2',storage='gzip-v1',local=args.local_submap_m)
                entry=next(c for c in report['cases'] if c['id']==case['id'])
                reference=args.output/(case['id']+'-2-B')
                entry['local_option']=dict(radius_m=args.local_submap_m,default_on=False,
                    result=json.loads((output/'result.json').read_text()),
                    delta=pose_difference(reference,output),
                    online_map_delta=pose_difference(reference,output,frame='online_map'),
                    baseline_accuracy=trajectory_accuracy(reference,Path(case['raw'])),
                    local_accuracy=trajectory_accuracy(output,Path(case['raw'])),
                    baseline_map_accuracy=trajectory_accuracy(reference,Path(case['raw']),frame='online_map'),
                    local_map_accuracy=trajectory_accuracy(output,Path(case['raw']),frame='online_map'))
        if args.referee_abba:
            report['referee_abba']=referee_abba(Path(plan['priority_run']),args.output/'referee-abba',args)
        report['complete']=True
    except BaseException as exc:
        report['failure']=dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        from scripts import agent_lock
        try:
            write(args.output/'abba.json',report)
        finally:
            released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex') if owned else None
        write(args.output/'lock.json',dict(acquired=held,released=released))


if __name__=='__main__':
    main()
