"""One authorized seed1052 start-localization diagnostic; never pick/carry."""
import argparse,copy,hashlib,json,os,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=Path('/Users/changmin/projects/ugrp/outputs/s2-stiff-cal-20261007/start/setup_bundle.json')
PLAN=ROOT/'experiments/2026-10-06-s2-realism/active-markov-criteria.json'


def episode(backend,runtime):
    """Only own RGB/issued commands cross the controller boundary."""
    from harness.zone_solo_cyan_active_markov import PARAMS
    backend.reset(5.);start=backend.now;backend.set_deadline(start+PARAMS['sim_cap_s'])
    runtime.initial_commands(start,{'r3':backend.commands['r3']})
    for i in range(round(PARAMS['sim_cap_s']/.05)+1):
        backend.advance_to(round(start+i*.05,8));backend.eval_sample()
        runtime.on_frames(backend.now,backend.capture())
        for rid,action in runtime.step(backend.now):
            backend.issue(rid,action);runtime.on_command(rid,backend.now,action)
        if i%100==0:print(json.dumps(dict(sim_s=backend.now-start,state=runtime.state)),flush=True)
        if runtime.terminal:break
    backend.issue('r3',dict(kind='hold'))
    return backend.now-start


def run(out,source):
    import numpy as np
    from scripts.run_final_environment_checks import write
    from harness import zone_solo_cyan_contract_v106 as c
    from harness.zone_solo_cyan_active_markov import Runtime,OPTION,PARAMS
    from harness.s2_stiff_camera_calibration import runtime_class
    from harness.zone_pair_highpose_exact_speedups import install
    from sim import s2_realism
    from sim.s2_pulse_cal import backend_class
    from sim.s2_servo_stiffness import transform_xml
    plant=json.loads(TEMPLATE.read_text());criteria=json.loads(PLAN.read_text())
    out.mkdir(parents=True,exist_ok=False)
    write(out/'setup_bundle.json',plant) # immutable scene/plant template, not the new run identity
    options={**plant['options'],**criteria['options']}
    configuration=dict(schema='ugrp.s2.active_markov_start.config.v1',workflow_id='s2-active-markov-start-v1',
        source_sha=source,seed=1052,options=options,start_only=True,full_dev=False,
        template_sha256=hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
        criteria_sha256=hashlib.sha256(PLAN.read_bytes()).hexdigest(),parameters=PARAMS,
        camera_table_sha256=hashlib.sha256((ROOT/'configs/calibration/s2_camera_stiff_target_v1.json').read_bytes()).hexdigest())
    configuration['configuration_sha256']=c.hp.base.digest(configuration)
    write(out/'run-configuration.json',configuration)
    original=s2_realism.make_scene;backend=runtime=None;wall=time.monotonic();_,undo=install('v98-exact-v6')
    def scene_factory(*args,**kwargs):
        scene=original(*args,**kwargs);transform=scene.robot_transform
        scene.robot_transform=lambda xml,**kw:transform_xml(transform(xml,**kw),servo_stiffness='real_v1')
        scene.manifest['s2_active_start']=configuration
        return scene
    result=dict(schema='ugrp.s2.active_markov_start.result.v1',**configuration,
        status='HOST_ERROR',physical_success=None,model_calls=0,full_dev=False,transport_attempted=False)
    try:
        omit=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace','servo_stiffness','camera_pitch')
        kw={k:v for k,v in options.items() if k not in omit}
        kw.update(motion_model=plant['motion_model'],pulse_calibration=plant['pulse_calibration'],
            extrinsic_calibration=plant['extrinsic_calibration'],floor_appearance=plant['floor_appearance'],
            camera_pitch='stiff_target_v1',servo_stiffness='real_v1',
            stiff_camera_table=json.loads((ROOT/'configs/calibration/s2_camera_stiff_target_v1.json').read_text()))
        runtime=runtime_class(Runtime)(c.hp.resolve(c.MAP_ID)[0],ROOT/c.CALIBRATION,c.CALIBRATION_SHA,seed=1052,**kw)
        try:
            s2_realism.make_scene=scene_factory;backend=backend_class()(plant,out,seed=1052)
        finally:s2_realism.make_scene=original
        sim_s=episode(backend,runtime)
        # The controller has stopped. GT is read only for the final score below.
        record=runtime.record();write(out/'student_record.json',record)
        estimate=record['poses'][-1];truth=backend.eval_rows[-1]
        error=float(np.linalg.norm(np.array([estimate['x'],estimate['y']])-truth['robot_xyz_m'][:2]))
        actions=record['active_markov']['decisions']
        result.update(status='COMPLETED',sim_s=sim_s,final_error_m=error,
            within_25cm=error<=.25,reason=record['active_markov']['reason'],
            final_estimate=estimate,actions=len(actions),completed_actions=sum(a['completed'] for a in actions),
            wheel_pulses=sum(a['issued_pulses'] for a in actions),
            updates=record['amcl_update']['updates'] if 'amcl_update' in record else runtime.amcl_audit['updates'],
            selected_actions=[a['selected'] for a in actions],would_stop=runtime.soft_counts,
            gt_evaluation_only=True,controller_gt_inputs=False,known_own_dock=False)
    except Exception as exc:
        result.update(status='PHYSICAL_FAILURE' if isinstance(exc,s2_realism.PhysicalStop) else 'HOST_ERROR',failure=f'{type(exc).__name__}: {exc}')
        if runtime is not None:write(out/'student_record.json',runtime.record())
        raise
    finally:
        result['wall_s']=time.monotonic()-wall
        if backend is not None:backend.close()
        if runtime is not None:runtime.close()
        undo();write(out/'result.json',result)
    print(json.dumps({k:result[k] for k in ('status','sim_s','final_error_m','actions','wheel_pulses','wall_s')}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true');p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path);p.add_argument('--seed',type=int,choices=[1052],default=1052)
    p.add_argument('--start-localization',choices=['off','active_markov_v1'],default='off')
    a=p.parse_args()
    if not a.execute:
        print(json.dumps(dict(execution_started=False,seed=a.seed,start_localization=a.start_localization,sim_cap_s=30.,transport=False)));return
    if a.start_localization!='active_markov_v1':raise ValueError('explicit active start opt-in required')
    if a.output is None or not a.output.is_absolute() or a.output.exists():raise ValueError('absolute new output required')
    from scripts.run_final_environment_checks import check_source,write
    from scripts import agent_lock
    check_source(a.expected_source_sha)
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',
        purpose='s2v34 one seed1052 active localization; no transport',pid=os.getpid(),expected_minutes=15,timing_sensitive=True)
    try:run(a.output,a.expected_source_sha)
    finally:
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        write(a.output/'lock.json',dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))


if __name__=='__main__':main()
