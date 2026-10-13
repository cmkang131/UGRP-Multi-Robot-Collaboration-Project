from pathlib import Path
import json,subprocess,math,sys,statistics,hashlib
from collections import Counter
root=Path.home()/'ugrp-sim';source=root/'src/e654ae01dc07014b960acf0b9c5de292f9f0436f';sys.path.insert(0,str(source))
from harness.e2e_route_stage_probe import evaluate
from harness.self_odom_grid import transform
from harness.pair_stage_probe import digest

def read(p,lines=False):
 if not p.exists():p=Path(str(p)+'.zst')
 b=subprocess.check_output(['zstd','-qdc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
 return [json.loads(x) for x in b.splitlines()] if lines else json.loads(b)
run=root/'runs/route1-stage-replay-b1';data=read(run/'raw/results.json');cache={};out=[]
for row in data['rows']:
 if not row.get('generated'):continue
 path=Path(row['snapshot']);record=read(path);state=record['snapshot'];raw=path.parent.parent
 if str(raw) not in cache:cache[str(raw)]=read(raw/'eval_only/r1/trajectory.jsonl',True)
 t=state['t_sim']-30.+1.3;traj=cache[str(raw)];obs=min(traj,key=lambda x:abs(x['t']-t));assert abs(obs['t']-t)<.051
 own=state['local_pose'];yaw=obs['robot_yaw_rad']-own[2];c=math.cos(yaw);s=math.sin(yaw);tf=[obs['robot_xyz_m'][0]-c*own[0]+s*own[1],obs['robot_xyz_m'][1]-s*own[0]-c*own[1],yaw]
 assert math.dist(transform([own[:2]],tf)[0],obs['robot_xyz_m'][:2])<1e-9
 label=read(run/'eval_only'/(digest(state)+'.json'));initial=label['own_to_world'];label['own_to_world']=tf
 trial=evaluate(row,state,label)
 out.append(dict(option=row['option'],snapshot_sha256=row['snapshot_file_sha256'],case_id=row['case_id'],initial_registration_collision_free=row['evaluation']['collision_free'],current_robot_registration_collision_free=trial['collision_free'],current_reason=trial.get('reason'),robot_registration_drift_m=math.dist(transform([own[:2]],initial)[0],obs['robot_xyz_m'][:2]),own_B_world_initial=transform([state['entities']['B']['center_m']],initial)[0].tolist(),own_B_world_current=transform([state['entities']['B']['center_m']],tf)[0].tolist()))
print(json.dumps(dict(scope='evaluation only; compare fixed initial registration and instantaneous own-robot rigid registration. Neither corrects nonrigid map errors; dynamic obstacles and physical passage untested',results_source_sha256=hashlib.sha256((run/'raw/results.json.zst').read_bytes()).hexdigest(),generated_N=len(out),initial_collision_free_n=sum(r['initial_registration_collision_free'] for r in out),current_collision_free_n=sum(r['current_robot_registration_collision_free'] for r in out),current_failure_reasons=dict(Counter(r['current_reason'] for r in out)),robot_registration_drift_m_median=statistics.median(r['robot_registration_drift_m'] for r in out),robot_registration_drift_m_max=max(r['robot_registration_drift_m'] for r in out),rows=out)))
