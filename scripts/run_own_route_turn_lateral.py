"""egomap70 fixed 24-run checkpoint batch, independent calibration artifact."""
import argparse
import copy
import hashlib
import json
import math
import signal
import sys
from pathlib import Path
from types import MethodType,SimpleNamespace
import cv2
import numpy as np
from harness.active_camera import bind,SEARCH
from harness.own_route_reference import Options,install as route_install
from harness.turn_lateral_calibration import OPTION,install as motion_install,ARTIFACT
from harness.own_route_zone_arrival import ARRIVAL,COLOR,install as zone_install,observed_inside
from scripts import run_own_route_traversed as previous

ref=previous.ref
ROOT=ref.ROOT
PLAN=ROOT/'experiments/2026-10-11-own-route-turn-lateral/prereg.json'
CONDITIONS=dict(baseline=Options(),calib=Options(),calib_traversed=Options(return_own_free_astar=True),
    calib_traversed_zone=Options(return_own_free_astar=True))

def registration():return json.loads(PLAN.read_text())


def bundle(seed,source,condition,mode):
    b=ref.previous.bundle(seed,source,'baseline',mode)
    b['execution_bundle_id']=f'egomap70-{mode}-{condition}-{seed}-v1'
    b['options'].update(motion_model_turn_lateral_v2='off' if condition=='baseline' else OPTION,
        traversed_free='footprint_history_v1' if CONDITIONS[condition].return_own_free_astar else 'off',
        arrival_zone=ARRIVAL if condition=='calib_traversed_zone' else 'off',
        B_color_confirmation=COLOR if condition=='calib_traversed_zone' else 'off')
    b['host_alarm_s']=registration()['host_alarm_s']
    b['turn_calibration_sha256']=hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() if condition!='baseline' else None
    b['admission']='egomap70 same6 DEV checkpoints; prefix unchanged; new future turn-Y only'
    return b


def own_prefix_rgb(c,path):
    root=path.parents[1];target=c.entities['B']['frame_sha256']
    row=next(r for r in ref.rows(root/'robots/r3/frames.jsonl') if r['sha256']==target)
    data=(root/row['path']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=target:raise ValueError('PREFIX_RGB_HASH')
    return cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)


def passive_metrics(c,rows):
    original=c._arrival;old_streak=0;zone_streak=0;legacy_at=None;zone_at=None
    def arrival(self,t,frame_id,pose,box_visible):
        nonlocal old_streak,zone_streak,legacy_at,zone_at
        if self.active=='B':
            near=math.dist(pose[:2],self.entities['B']['center_m'])<=.20
            fresh=any(p.get('confirmed_t') is not None for p in self.current_patches)
            lower=0 if self.labels is None else int(np.count_nonzero(self.labels[2*self.labels.shape[0]//3:]))
            old_streak=old_streak+1 if near and fresh and lower>=self.explorer.goal.options.min_pixels else 0
            inside,n=observed_inside(self,pose);zone_streak=zone_streak+1 if inside else 0
            if old_streak>=5 and legacy_at is None:legacy_at=t
            if zone_streak>=5 and zone_at is None:zone_at=t
            rows.append(dict(t=t,frame_id=frame_id,pose=list(map(float,pose)),legacy_streak=old_streak,
                zone_streak=zone_streak,legacy_at=legacy_at,zone_at=zone_at,observed_cells=n))
        return original(t,frame_id,pose,box_visible)
    c._arrival=MethodType(arrival,c)


def run(a):
    a.stage_schedule=ref.SCHEDULE;a.profile='baseline'
    b=bundle(a.seed,ROOT.name,a.condition,a.mode);audit=[];dual=[];controllers=[]
    def load(path,out):
        backend,c,start,tick,cp=ref.old.checkpoint_load(path,out)
        route_install(c,CONDITIONS[a.condition],traversed_free=b['options']['traversed_free'])
        motion_install(c,motion_model_turn_lateral_v2=b['options']['motion_model_turn_lateral_v2'])
        rgb=own_prefix_rgb(c,path) if b['options']['B_color_confirmation']!='off' else None
        zone_install(c,arrival_zone=b['options']['arrival_zone'],B_color_confirmation=b['options']['B_color_confirmation'],
                     prefix_rgb=rgb,prefix_servo=SEARCH)
        passive_metrics(c,dual);controllers.append(c);ref.arrival_audit(c,audit)
        def emit(row):
            row['turn_lateral']=getattr(c,'_turn_lateral_record',None)
            row['turn_profiles_applied']=(c.heading_host.profiles is c.explorer.memory.self_map.odom.driver.profiles) if a.condition!='baseline' else None
            row['zone_calls']=getattr(c,'_zone_calls',None)
            row['valid']=row['valid'] and (a.condition=='baseline' or (row['turn_lateral'] is not None and row['turn_profiles_applied']))
            if a.condition=='calib_traversed_zone':row['valid']=row['valid'] and row['zone_calls']==row['call']
            with (out/'execution-path.jsonl').open('a') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
            if not row['valid']:raise RuntimeError('EGOMAP70_TOGGLE_NOT_EXECUTED')
        previous.execution_audit(c,CONDITIONS[a.condition],emit)
        return backend,c,start,tick,cp
    def alarm(n):return signal.alarm(b['host_alarm_s'] if n else 0)
    r=bind(ref.old.run,bundle=lambda *args:b,checkpoint_load=load,server_slot=ref.server_slot,
        install=ref.previous.previous.install,signal=SimpleNamespace(**{**vars(signal),'alarm':alarm}))(a)
    ref.old.dump(a.output/'arrival-gates.json',audit)
    ref.old.dump(a.output/'dual-arrival.json',dual)
    ref.old.dump(a.output/'B-color-confirmation.json',getattr(controllers[0],'_color_rows',[]) if controllers else [])
    return r


def jobs(out):
    return [dict(name=f'egomap70-{cp["seed"]}-{condition}',seed=cp['seed'],condition=condition,profile='baseline',status='QUEUED',
        checkpoint=cp['path'],checkpoint_sha256=cp['sha256'],output=str(Path(out)/f'egomap70-{cp["seed"]}-{condition}'),
        command=[sys.executable,'-m','scripts.run_own_route_turn_lateral','--mode','stage','--seed',str(cp['seed']),
                 '--condition',condition,'--output',str(Path(out)/f'egomap70-{cp["seed"]}-{condition}')])
        for cp in registration()['checkpoints'] for condition in CONDITIONS]


def score_batch(plan,out):
    reports=bind(ref.score_batch,aggregate=bind(ref.aggregate,CONDITIONS=CONDITIONS))(plan,out,round_name='egomap70')
    from scripts.score_own_route_full_budget import load_old,boundary_distance
    m=load_old()
    for r in reports:
        p=Path(r['raw']);result=json.loads((p/'result.json').read_text()) if (p/'result.json').exists() else {}
        if not r.get('samples'):continue
        start=result['start_sim_s'];tr=ref.rows(p/'eval_only/trajectory.jsonl');tb={round(x['t'],6):x for x in tr}
        origin=[*tr[0]['robot_xyz_m'][:2],tr[0]['robot_yaw_rad']]
        own=[x for x in ref.rows(p/'own-controller.jsonl') if x['t']>=start and round(x['t'],6) in tb]
        actual=np.array([tb[round(x['t'],6)]['robot_xyz_m'][:2] for x in own])
        err=np.linalg.norm(m.transform([x['local_pose'][:2] for x in own],origin)-actual,axis=1)
        B=json.loads((p/'inputs/static_map.json').read_text())['regions']['zone_B']
        dual=json.loads((p/'dual-arrival.json').read_text()) if (p/'dual-arrival.json').exists() else []
        r['position_rmse_m']=float(np.sqrt(np.mean(err**2)))
        for kind in ('legacy','zone'):
            stamp=next((x[kind+'_at'] for x in dual if x[kind+'_at'] is not None),None)
            gt=tb.get(round(stamp,6)) if stamp is not None else None
            r[kind+'_B']=dict(declared_t=stamp,actual_inside=boundary_distance(gt['robot_xyz_m'][:2],B)==0 if gt else None)
        colors=json.loads((p/'B-color-confirmation.json').read_text()) if (p/'B-color-confirmation.json').exists() else []
        r['color_confirmation']=dict(attempts=len(colors),accepted=sum(x['accepted'] for x in colors),prefix=[x for x in colors if x.get('scope')=='prefix'])
    ref.old.dump(out/'scores.json',reports)
    aggregate=bind(ref.aggregate,CONDITIONS=CONDITIONS)(reports)
    for key in CONDITIONS:
        group=[r for r in reports if r['condition']==key and r.get('samples')]
        aggregate[key]['position_rmse_median']=float(np.median([r['position_rmse_m'] for r in group])) if group else None
        aggregate[key]['dual_B']={kind:dict(declared=sum(r[kind+'_B']['declared_t'] is not None for r in group),
            true=sum(r[kind+'_B']['actual_inside'] is True for r in group)) for kind in ('legacy','zone')}
    ref.old.dump(out/'summary.json',dict(round='egomap70',host='oracle-x86',source_sha=ROOT.name,registered=24,
        conditions=aggregate,runs=reports,thresholds_changed=False,raw_root=str(out),
        calibration_sha256=hashlib.sha256(ARTIFACT.read_bytes()).hexdigest(),
        scores_sha256=hashlib.sha256((out/'scores.json').read_bytes()).hexdigest()))


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('stage','smoke','batch'),required=True)
    p.add_argument('--condition',choices=tuple(CONDITIONS),default='baseline');p.add_argument('--seed',type=int,default=63001)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='batch':return bind(ref.batch,jobs=jobs,registration=registration,early_check=previous.early_check,
        score_batch=score_batch)(a,required_free_gib=20)
    a.checkpoint=Path(next(cp['path'] for cp in registration()['checkpoints'] if cp['seed']==a.seed))
    if a.mode=='smoke':a.mode='smoke_resume'
    r=run(a);print(json.dumps(r),flush=True);return 0 if r['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
