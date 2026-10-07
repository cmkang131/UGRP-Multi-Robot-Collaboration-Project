"""Strict staged pure-2D evaluator. Never imports or starts MuJoCo or a model client."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-explore/code'))
import numpy as np
from run_grid import STARTS,static_inputs,write,source_hashes
from grid_world_v2 import RectangleWorld,RectangleOracleWorld
from harness.public_navigation.actor import PublicActor
from harness.self_odom_grid import transform,motion_profiles
from harness.public_navigation.native import build

FRESH_STARTS = {'G':[-.45,-2.30,math.pi/6], 'H':[1.20,.65,-math.pi/3]}
SETTINGS = dict(navigation='public_ros_v1',resolution_m=.1,control_dt=.1,speed_m_s=.12,
    lookahead_m=.20,position_tolerance_m=.05,rotate_speed_rad_s=.5,rotate_threshold_rad=math.pi/4,
    footprint_half_m=[.12,.10],padding_m=.02,inflation_radius_m=.5,inflation_scaling=10.,
    progress_timeout_s=30.,frontier_potential=1.,frontier_gain=1.,frontier_min_m=.1,
    observation_time_s=2.,action_time_s=1.,budget_s=600.,budget_m=40.,budget_frames=300)


def hashes():
    result = source_hashes()  # unchanged legacy environment/sensor files
    paths = list((ROOT/'harness/public_navigation').rglob('*.py'))
    paths += list((ROOT/'harness/public_navigation').rglob('*.cpp'))
    paths += list((ROOT/'harness/public_navigation').rglob('*.h'))
    paths += [p for p in (ROOT/'third_party/mapfree_navigation').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths += [Path(__file__)]
    for p in paths:
        result[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    frozen_b = json.loads((ROOT/'experiments/2026-10-07-mapfree-goal-floor/v3-selection.json').read_text())['code_hashes']
    for name,expected in frozen_b.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('FROZEN_B_V3_CHANGED')
        result[name] = expected
    return result


def cohort(cohort_name):
    starts,seeds = (['A','C'],[1701]) if cohort_name=='development' else (['G','H'],[4701,4702])
    return [(i,s,seed) for i in range(1,9) for s in starts for seed in seeds]


def verify_gate(folder,stage,current_hashes):
    if folder is None:
        raise ValueError('ORACLE_STATIC_GATE_REQUIRED')
    source = json.loads((folder/'source.json').read_text())
    rows = json.loads((folder/'results.json').read_text())
    expected = {(f's{i}',s,seed) for i,s,seed in cohort('confirmation')}
    keys = {(r['scenario'],r['start'],r['seed']) for r in rows}
    if source['stage']!=stage or source['cohort']!='confirmation' or source['hashes']!=current_hashes:
        raise ValueError('GATE_SOURCE_OR_COHORT_MISMATCH')
    if len(rows)!=32 or keys!=expected:
        raise ValueError('GATE_INCOMPLETE_COHORT')
    # Check original episode results, not an editable aggregate pass flag.
    for r in rows:
        name = f"{r['scenario']}-{r['start']}-{r['seed']}-{r['condition']}"
        if json.loads((folder/name/'result.json').read_text())!=r:
            raise ValueError('GATE_RAW_RESULT_MISMATCH')
    if stage=='a' and (sum(r['status']=='B_confirmed' for r in rows)<30 or any(r['status']=='B_false_confirmed' for r in rows)):
        raise ValueError('ORACLE_STATIC_GATE_FAILED_STOP_B_C')


def issued_passage(world,command,plan,pose,t):
    gain = np.asarray(motion_profiles()['motion']['gain'])
    twist = gain@np.array([command['forward'],command['left'],command['turn']])
    if np.linalg.norm(twist[:2])<=1e-9:
        return
    target = transform([twist[:2]*command['duration_s']],pose)[0].tolist()
    world.passage_intent({**plan,'path_m':[list(pose[:2]),target]},pose,t)


def episode(index,start_id,seed,split,condition,sensing,out):
    world = (RectangleOracleWorld if sensing=='oracle' else RectangleWorld)(index,{**STARTS,**FRESH_STARTS}[start_id],seed,split)
    actor = PublicActor(condition,*(static_inputs(world) if condition=='static_map' else (None,None)),navigation='public_ros_v1')
    logs,truth_logs,commands = [],[],[]
    track_truth = {}
    first = None
    status = 'budget'
    if world.collision(world.pose[:2]):
        status = 'HOST_SETUP_ERROR'
    else:
        for frame in range(300):
            if actor.t>=600-1e-8 or world.distance>=40 or world.collision_latched:
                status = 'collision' if world.collision_latched else 'budget'
                break
            hold = dict(t=actor.t,kind='stop')
            actor.odom.command(hold)
            world.advance(hold,actor.t+2.)
            actor.odom.advance(actor.t+2.)
            actor.t = actor.odom.t
            if world.collision_latched:
                status = 'collision'
                break
            observation,patches,truth = world.observe(frame)
            actor.steps = frame
            accepted = actor.receive(observation,patches)
            for patch,true in zip(accepted,truth):
                evidence = track_truth.setdefault(patch['track_id'],[])
                evidence.append(bool(true))
                if patch['confirmed_t'] is not None:
                    correct = sum(evidence)>=2 and sum(evidence)>len(evidence)/2
                    first = dict(time_s=actor.t,distance_m=world.distance,true=correct,
                                 true_views=sum(evidence),total_views=len(evidence))
                    status = 'B_confirmed' if correct else 'B_false_confirmed'
                    break
            plan = actor.plan()
            logs.append(dict(frame=frame,t=actor.t,pose_odom=list(actor.odom.pose),
                             observation=observation,patches=accepted,plan=plan))
            truth_logs.append(dict(frame=frame,t=actor.t,pose_world=world.pose.tolist(),
                coverage=world.coverage(),B_component_truth=truth,distance_m=world.distance))
            if first:
                break
            # Public path tracker operates at 10 Hz during the same one-second motion interval.
            for tick in range(10):
                command = actor.command(plan)
                commands.append(dict(frame=frame,tick=tick,t=actor.t,pose_odom=list(actor.odom.pose),command=command))
                issued_passage(world,command,plan,actor.odom.pose,actor.t)
                actor.odom.command(command)
                end = actor.t+.1
                world.advance(command,end)
                actor.odom.advance(end)
                actor.t = actor.odom.t
                if world.collision_latched:
                    status = 'collision'
                    break
            if world.collision_latched:
                break
    result = dict(scenario=f's{index}',start=start_id,seed=seed,split=split,condition=condition,sensing=sensing,
        status=status,first_B=first,time_s=actor.t,distance_m=world.distance,coverage=world.coverage(),
        collisions=world.collisions,door_attempts=world.door_attempts,wrong_door_attempts=world.wrong_doors,
        candidate_passage_attempts=world.candidate_attempts,false_candidate_passage_attempts=world.false_candidate_attempts,
        plans=actor.counts,navigation_events=dict(Counter(e['reason'] for e in actor.navigator.events)),
        observations=len(logs),sensor_draws=world.sensor_counters,
        end_position_error_m=float(np.linalg.norm(transform([actor.odom.pose[:2]],world.start)[0]-world.pose[:2])),
        sources=world.sources,options=SETTINGS,passage_scoring='issued_translation_public_v1')
    out.mkdir(parents=True,exist_ok=False)
    for name,rows in [('actor',logs),('eval_only',truth_logs),('commands',commands),('navigation_events',actor.navigator.events)]:
        (out/(name+'.jsonl')).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
    write(out/'result.json',result)
    write(out/'eval_path.json',world.path)
    write(out/'own_grid.json',dict(resolution_m=.1,cells=[[*c,v] for c,v in sorted(actor.grid.odds.items())]))
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--navigation',default='off',choices=['off','public_ros_v1'])
    p.add_argument('--cohort',required=True,choices=['development','confirmation'])
    p.add_argument('--stage',required=True,choices=['a','b','c'])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--freeze',type=Path)
    p.add_argument('--gate-a',type=Path)
    p.add_argument('--gate-b',type=Path)
    p.add_argument('--smoke',action='store_true')
    a = p.parse_args()
    if a.navigation=='off':
        p.error('Default off: use the preserved legacy runner, or explicitly opt in.')
    current = hashes()
    if a.smoke and a.cohort!='development':
        p.error('Smoke is only allowed for already seen development data')
    if a.cohort=='confirmation':
        freeze = json.loads(a.freeze.read_text()) if a.freeze else {}
        if freeze.get('hashes')!=current or freeze.get('settings')!=SETTINGS or freeze.get('starts')!=FRESH_STARTS:
            raise ValueError('CONFIRMATION_REQUIRES_FROZEN_SOURCE_AND_SETTINGS')
    if a.stage in ('b','c'):
        verify_gate(a.gate_a,'a',current)
        if a.stage=='c':
            verify_gate(a.gate_b,'b',current)
    if a.cohort=='development' and a.stage!='a':
        p.error('Only static oracle development was preregistered')
    native = build()
    a.output.mkdir(parents=True,exist_ok=False)
    write(a.output/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        hashes=current,settings=SETTINGS,starts=FRESH_STARTS,cohort=a.cohort,stage=a.stage,smoke=a.smoke,
        native_path=str(native),native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
        python=sys.version,environment='rect_footprint_v2'))
    rows=[]
    for i,start,seed in (cohort(a.cohort)[:1] if a.smoke else cohort(a.cohort)):
        for mode in (['static_map','own_frontier'] if a.stage=='c' else ['static_map' if a.stage=='a' else 'own_frontier']):
            name=f's{i}-{start}-{seed}-{mode}'
            row=episode(i,start,seed,a.cohort,mode,'noisy' if a.stage=='c' else 'oracle',a.output/name)
            rows.append(row)
            write(a.output/'results.json',rows)
            print(name,row['status'],round(row['coverage'],3),row['navigation_events'],flush=True)
    if a.stage=='a' and a.cohort=='confirmation':
        passed=len(rows)==32 and sum(r['status']=='B_confirmed' for r in rows)>=30 and not any(r['status']=='B_false_confirmed' for r in rows)
        write(a.output/'gate.json',dict(passed=passed,required_true=30,total=32,
            true=sum(r['status']=='B_confirmed' for r in rows),false=sum(r['status']=='B_false_confirmed' for r in rows),
            next_stages='allowed' if passed else 'BLOCKED_DO_NOT_RUN'))
        print('ORACLE_STATIC_GATE', 'PASS' if passed else 'FAIL_STOP',flush=True)


if __name__=='__main__':
    main()
