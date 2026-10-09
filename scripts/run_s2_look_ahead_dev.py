"""Standard S2 full loop with explicit measured look-ahead option; default preview."""
import argparse,os
from pathlib import Path
from harness import zone_s2_realism_contract_v131 as contract
from harness.zone_solo_cyan_look_ahead import Runtime
from harness.zone_final_pair_binding import bind
from scripts import run_s2_realism_v117 as loop
from scripts.run_final_environment_checks import check_source,write


def runtime_factory(bundle):
    excluded=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
    options={k:v for k,v in bundle['options'].items() if k not in excluded}
    extra={k:bundle[k] for k in ('motion_model','pulse_calibration','extrinsic_calibration','floor_appearance','look_ahead_calibration','stiff_camera_table')}
    return lambda *a,**kw:Runtime(*a,**kw,**options,**extra)


def run(bundle,out):
    from sim import s2_realism
    from sim.s2_servo_stiffness import transform_xml
    from sim.s2_pulse_cal import backend_class
    contract.require_execution(bundle)
    from sim.s2_eval_wall_contacts import backend_class as wall_backend
    Base=backend_class()
    class Backend(wall_backend(Base)):
        def __init__(self,*a,**kw):
            original=s2_realism.make_scene
            def scene_factory(*args,**kwargs):
                scene=original(*args,**kwargs);tr=scene.robot_transform
                scene.robot_transform=lambda xml,**k:transform_xml(tr(xml,**k),servo_stiffness=bundle['options']['servo_stiffness'])
                return scene
            try:s2_realism.make_scene=scene_factory;super().__init__(*a,**kw)
            finally:s2_realism.make_scene=original
    record={}
    def writer(path,value):
        if path.name=='student_record.json':record.update(value)
        if path.name=='result.json':
            value.update(pool_with_previous_s2=False,comparison_metrics=['wall_per_sim'],dev_light=True,
                conservative_stops=record.get('dev_light_would_stop',{}),run_limit=1,transport='solo',research_result=False)
            if record and (out/'eval_only/trajectory.jsonl').exists():
                from scripts.evaluate_s2_real_carry import metrics
                try:
                    score=metrics(out,record,bundle);value['posthoc_evaluation']=score;write(out/'eval_only/metrics.json',score)
                except Exception as exc:value['posthoc_evaluation_error']=str(exc)
        write(path,value)
    return bind(loop.run,contract=contract,write=writer)(bundle,out,stage='place',runtime_factory=runtime_factory(bundle),backend_factory=Backend)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path)
    p.add_argument('--carry-pose',choices=('off','look_ahead_v1'),default='off');p.add_argument('--servo-stiffness',choices=('off','real_v1'),default='off');p.add_argument('--camera-pitch',choices=('off','stiff_target_v1'),default='off')
    p.add_argument('--pregrasp-policy',choices=('off','log_only_v1'),default='off')
    a=p.parse_args();b=contract.bundle(a.expected_source_sha,carry_pose=a.carry_pose,servo_stiffness=a.servo_stiffness,camera_pitch=a.camera_pitch,pregrasp_policy=a.pregrasp_policy)
    if not a.execute:print(dict(execution_started=False,bundle=b['execution_bundle_id'],options=b['options']));return
    check_source(a.expected_source_sha);contract.require_execution(b)
    if not a.output or not a.output.is_absolute() or a.output.exists():raise ValueError('new absolute output required')
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',purpose='s2v36 authorized seed1051 look-ahead pregrasp log-only rerun',pid=os.getpid(),expected_minutes=40,timing_sensitive=True)
    _,undo=install('v98-exact-v6')
    try:run(b,a.output)
    finally:
        undo();released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex');write(a.output/'lock.json',dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))
if __name__=='__main__':main()
