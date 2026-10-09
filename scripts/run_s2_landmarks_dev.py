"""s2v39 one start then conditional full, own RGB and commands only."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from harness import zone_s2_landmarks_contract as c
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_landmarks import runtime_class as landmarks_runtime
from harness.zone_solo_cyan_best_cluster import runtime_class as best_runtime
from harness.zone_solo_cyan_amcl_sensor import runtime_class as sensor_runtime
from scripts import run_s2_realism_v117 as loop
from scripts.run_final_environment_checks import check_source,write


def moving(action):
    return action['kind'] in ('mecanum','drive') and any(action.get(k,0) for k in ('forward','left','turn'))


def start_only_class(previous):
    class StartOnly(previous):
        start_done=False
        def step(self,now):
            actions=super().step(now)
            if any(moving(a) for _,a in actions) or self.state not in ('init','scan','search_move'):
                # Finite diagnostic boundary: do not execute first navigation
                # pulse. Scan, last SEARCH observation and pose inference are
                # ordinary own-RGB controller operations; no truth gate.
                self.start_done=True
                return [(self.robot_id,dict(kind='hold'))]
            return actions
    return StartOnly


def runtime_factory(b):
    from harness.zone_solo_cyan_look_ahead import Runtime as Carry
    from harness.zone_solo_cyan_kld_start import Runtime as Start
    from harness.s2_stiff_camera_calibration import runtime_class as stiff_runtime
    base=stiff_runtime(Start) if b['mode']=='start' else Carry
    Runtime=landmarks_runtime(sensor_runtime(best_runtime(base)))
    if b['mode']=='start':Runtime=start_only_class(Runtime)
    omit=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
    options={k:v for k,v in b['options'].items() if k not in omit}
    keys=['motion_model','pulse_calibration','extrinsic_calibration','floor_appearance','stiff_camera_table']
    if b['mode']=='full':keys.append('look_ahead_calibration')
    return lambda *a,**kw:Runtime(*a,**kw,**options,**{k:b[k] for k in keys})


def run(b,out):
    from sim import s2_realism
    from sim.s2_servo_stiffness import transform_xml
    from sim.s2_pulse_cal import backend_class
    from sim.s2_eval_wall_contacts import backend_class as wall_backend
    c.require_execution(b)
    Base=backend_class()
    class Backend(wall_backend(Base)):
        def __init__(self,*a,**kw):
            original=s2_realism.make_scene
            def scene_factory(*args,**kwargs):
                scene=original(*args,**kwargs);transform=scene.robot_transform
                scene.robot_transform=lambda xml,**k:transform_xml(transform(xml,**k),servo_stiffness=b['options']['servo_stiffness'])
                return scene
            try:s2_realism.make_scene=scene_factory;super().__init__(*a,**kw)
            finally:s2_realism.make_scene=original
    record={}
    def writer(path,value):
        if path.name=='student_record.json':record.update(value)
        if path.name=='result.json':
            value.update(mode=b['mode'],pool_with_previous_s2=False,dev_light=True,run_limit=1,
                conservative_stops=record.get('dev_light_would_stop',{}),transport='solo',research_result=False)
            if b['mode']=='start' and record.get('poses'):
                import numpy as np
                truth=[json.loads(row) for row in (out/'eval_only/trajectory.jsonl').read_text().splitlines()]
                p=record['poses'][-1];t=[q['t'] for q in truth]
                gt=[np.interp(p['t_est'],t,[q['robot_xyz_m'][j] for q in truth]) for j in (0,1)]
                error=float(np.linalg.norm(np.array([p['x'],p['y']])-gt))
                value.update(start_error_m=error,start_within_25cm=error<=.25,
                    start_pose=p,transport_attempted=False,gt_use='posthoc scoring only',
                    visual_updates=record['amcl_update']['updates'])
            elif b['mode']=='full' and record:
                from scripts.evaluate_s2_real_carry import metrics
                try:
                    value['posthoc_evaluation']=metrics(out,record,b)
                    write(out/'eval_only/metrics.json',value['posthoc_evaluation'])
                except Exception as exc:value['posthoc_evaluation_error']=str(exc)
        write(path,value)
    reached=(lambda r,s:r.start_done) if b['mode']=='start' else loop.stage_reached
    return bind(loop.run,contract=SimpleNamespace(BUNDLE_ID=b['execution_bundle_id']),write=writer,
        stage_reached=reached)(b,out,stage=b['stage_probe'],runtime_factory=runtime_factory(b),backend_factory=Backend)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--mode',choices=('start','full'),required=True)
    p.add_argument('--sensor-landmarks',choices=('off','floor_zones_doors_v1'),default='off')
    p.add_argument('--output',type=Path);p.add_argument('--start-proof',type=Path)
    a=p.parse_args();proof=None
    if a.start_proof:proof=dict(path=str(a.start_proof.resolve()),sha256=c.old.hp.base.sha(a.start_proof))
    b=c.bundle(a.expected_source_sha,a.mode,sensor_landmarks=a.sensor_landmarks,start_proof=proof)
    if not a.execute:print(json.dumps(dict(execution_started=False,bundle=b['execution_bundle_id'],options=b['options'])));return
    check_source(a.expected_source_sha);c.require_execution(b)
    root=Path('/Users/changmin/projects/ugrp/outputs').resolve()
    if not a.output or not a.output.is_absolute() or a.output.exists() or not a.output.resolve().is_relative_to(root):raise ValueError('new primary output required')
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',
        purpose='s2v39 one '+a.mode+' DEV landmark admission',pid=os.getpid(),expected_minutes=30,timing_sensitive=True)
    undo=None
    try:
        _,undo=install('v98-exact-v6');result=run(b,a.output)
        print(json.dumps({k:result.get(k) for k in ('status','start_error_m','start_within_25cm','evaluation','wall_per_sim')}),flush=True)
    finally:
        if undo is not None:undo()
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        write(a.output/'lock.json',dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))

if __name__=='__main__':main()
