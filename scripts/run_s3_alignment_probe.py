"""Serial, <=60 SIM-second S3 alignment stage probes, never full E2E.

Restore only the saved scene's evaluation-side setup. Controllers are new and
receive own RGB/commands; missing full checkpoints are explicitly disclosed.
"""
import argparse,copy,hashlib,json,math,os,shutil,subprocess,time,traceback
from pathlib import Path
from harness import zone_s3_recovery_contract as parent
from scripts.run_final_environment_checks import write,check_source
from scripts.run_s3_host import artifact_manifest,environment_record

BUNDLE_ID='zone-s3-alignment-probe-v153'
ROOT=parent.ROOT
RAW=Path('/Users/changmin/projects/ugrp/outputs/s3-recovery-981baa95-s14201-v152')
ROBOTS=('r1','r2','r3')
CAP=60.

def nearest(path,t,key='t'):
    best=None
    with path.open() as stream:
        for line in stream:
            r=json.loads(line)
            if best is None or abs(r[key]-t)<abs(best[key]-t):best=r
            if r[key]>t:break
    return best

def setup_record(raw,case):
    t=532.1
    data=dict(source=str(raw),source_t=t,checkpoint=False,classification='reconstructed stationary stage setup, not exact resume',
        truth=nearest(raw/'eval_only/referee_truth.jsonl',t),robots={})
    for rid in ROBOTS:
        data['robots'][rid]=dict(pose=nearest(raw/f'eval_only/{rid}/trajectory.jsonl',t),
            frame=nearest(raw/f'robots/{rid}/frames.jsonl',t,'sim_time'))
    if case=='cyan':
        # r3 never aligned in v152. Explicit SYNTHETIC stage entrance, using
        # saved cargo only in the setup owner. No pose is returned to control.
        box=data['truth']['items']['cyan_1'];p=data['robots']['r3']['pose']
        p['robot_xyz_m'][:2]=[box['x']-.35,box['y']]
        p['robot_yaw_rad']=0.
        from harness.owncam_pair_beam_v2 import pose_of
        data['robots']['r3']['frame']['commanded_servo']={1:2000,**pose_of('search')}
        data['classification']='synthetic r3 approach end in saved v152 scene; v152 had no r3 align entry'
    return data

def bundle(sha,case,option):
    b=parent.bundle(sha)
    b.update(execution_bundle_id=BUNDLE_ID,schema='ugrp.s3_alignment_probe.v153',source_sha=sha,
        case=case,servo_option=option,case_cap_s=CAP,wall_cap_s=1800.,stage_probe=True,
        source_raw=str(RAW),known_start_information=False,research_result=False)
    from harness.python_source_closure import source_closure
    paths=set(b['source_sha256'])|set(source_closure(ROOT,['scripts/run_s3_alignment_probe.py','harness/zone_s3_visual_pose_servo.py']))
    b['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
    return b

def restore_scene(host,setup):
    """Setup-only before creating any controller; actual state is never returned."""
    import mujoco
    import numpy as np
    m,d=host.world.model,host.world.data
    for rid,row in setup['robots'].items():
        robot=host.world.robot(rid);p=row['pose']
        robot.set_base_pose_for_test(p['robot_xyz_m'],p['robot_yaw_rad'])
        servo={int(k):int(v) for k,v in row['frame']['commanded_servo'].items()}
        robot.set_servo_pulses(servo);host.commands[rid]=servo
        host._append(f'robots/{rid}/commands.jsonl',dict(t=host.now,kind='initial_servo_command',pulses=servo,source='saved issued reset commands'))
    for item,row in setup['truth']['items'].items():
        body=m.body(host.objects[item]['body_name']);j=int(body.jntadr[0]);q=int(m.jnt_qposadr[j]);v=int(m.jnt_dofadr[j]);a=row['yaw']
        # Saved height is inertial/COM; transform local COM offset to body origin.
        quat=np.array([math.cos(a/2),0,0,math.sin(a/2)]);rot=np.empty(9);mujoco.mju_quat2Mat(rot,quat)
        origin=np.array([row['x'],row['y'],row['z']]);origin[2]-=(rot.reshape(3,3)@body.ipos)[2]
        d.qpos[q:q+7]=[*origin,*quat];d.qvel[v:v+6]=0
    mujoco.mj_forward(m,d)
    host.set_deadline(host.now+2.)
    host.advance_to(round(host.now+1.,9))  # issued arm settle only, no controller
    write(host.out/'eval_only/stage-setup.json',setup)
    spec=mujoco.mjtState.mjSTATE_INTEGRATION;state=np.empty(mujoco.mj_stateSize(m,spec));mujoco.mj_getState(m,d,state,spec)
    np.savez(host.out/'eval_only/stage-integration-state.npz',state=state)

def enter_pair(rt,now,option):
    pair=rt.pair.producer
    for rid,other in [('r1','r2'),('r2','r1')]:
        ack=rt.links[rid].submit(rid,'cargoX','B',other,now=now)
        if not ack['accepted']:raise ValueError('stage admission: '+str(ack))
    pair.started=True;pair.submitted.update(('r1','r2'))
    endpoints=pair.team.sessions[0]['endpoints']
    from harness.zone_s3_visual_pose_servo import attach_endpoint
    for ep in endpoints.values():
        ctl=ep.controller;report=ep.own.last_report
        ctl.driver.outcome='arrived'
        ctl.claims['at_prestation']=dict(estimate=[report.x_m,report.y_m,report.yaw_rad],std_xy_m=report.std_xy_m,
            looks=0,sim_time=now,source='stage-only own RGB estimate; not student arrival')
        ctl.set('align_start',now,stage_probe_entry=True)
        attach_endpoint(ep,option)
    return endpoints

def run(b,out):
    from sim.s3_motion_ports import PhysicsBackend
    from harness.zone_s3_recovery_runtime import Runtime
    out.mkdir(parents=True,exist_ok=False);write(out/'bundle.json',b);write(out/'environment.json',environment_record())
    result=dict(status='HOST_ERROR',stage_probe=True,research_result=False,model_calls=0,source_sha=b['source_sha'],
        case=b['case'],servo_option=b['servo_option'],gt_inputs=False,loadavg_start=os.getloadavg())
    started=time.monotonic();host=rt=None;states=[];entry=None;eps={}
    try:
        host=PhysicsBackend(b,out,seed=b['seed']);host.reset(b['reset_cap_s'])
        restore_scene(host,setup_record(RAW,b['case']))
        start=host.now;host.set_deadline(start+CAP)
        static=parent.hp.resolve(b['map_id'])[0]
        rt=Runtime(static,parent.inputs()[2]['orders'],ROOT/b['calibration'],b['calibration_sha256'],seed=b['seed'],config=b['controller_config'])
        rt.initial_commands(start,host.commands)
        if b['case']=='cyan':
            from harness.zone_s3_visual_pose_servo import attach_solo
            attach_solo(rt.localizers['r3'],b['servo_option'])
        # Stage probe skips mission dispatch/approach. New map-uniform own RGB
        # filters are retained; neither saved GT nor Gaussian pose seeds enter.
        rt.boot_finished_at=start
        for i in range(round(CAP/.05)+1):
            now=host.now;host.eval_sample()
            if i==round(CAP/.05):break
            if time.monotonic()-started>b['wall_cap_s']:raise TimeoutError('PROBE_WALL_CAP')
            frames=host.capture();rt.on_frames(now,frames)
            if entry is None and now-start>=.5:
                if b['case']=='pair':eps=enter_pair(rt,now,b['servo_option'])
                else:
                    own=rt.localizers['r3'];fits=own.vision.detect(own.last_obs,own.servo)
                    if len(fits)!=1:raise ValueError('SYNTHETIC_CYAN_STAGE_NOT_UNIQUELY_VISIBLE')
                    own.target=fits[0]['estimated_box_center_base_m'][:2];own.set_state('align',now)
                entry=now
            actions=[]
            if entry is not None:
                if b['case']=='pair':
                    pair=rt.pair.producer
                    actions=pair.step(now)+pair.arm_step(now)
                    current={r:dict(state=ep.controller.state,blind_phase=getattr(ep.controller,'blind_phase',None),failure=ep.controller.failure,servo=dict(ep.own.servo)) for r,ep in eps.items()}
                else:
                    own=rt.localizers['r3'];actions=own.step(now)
                    current={'r3':dict(state=own.state,failure=own.failure,servo=dict(own.servo))}
                states.append(dict(t=now,robots=current))
                for rid,action in actions:
                    host.issue(rid,action);rt.on_command(rid,now,action)
                if any(v['failure'] for v in current.values()):break
                # Stop after actual commanded close and settle; no teacher lift.
                if all(v['servo'].get(1,2000)<=1600 and v['state'] not in ('align','align_start') for v in current.values()):break
            host.advance_to(start+(i+1)*.05)
        result.update(status='DEV_STAGE_FINISHED',check_sim_s=host.now-start,entry_sim_s=entry,
            final={r:dict(state=ep.controller.state,failure=ep.controller.failure) for r,ep in eps.items()} if eps else {'r3':dict(state=rt.localizers['r3'].state,failure=rt.localizers['r3'].failure)})
    except Exception:
        result['failure']=traceback.format_exc()
        if host is not None and 'start' in locals():result['check_sim_s']=host.now-start
    finally:
        write(out/'stage-states.json',states)
        if rt is not None:
            write(out/'student_record.json',rt.record());rt.close()
        if host is not None:host.close()
        result.update(wall_s=time.monotonic()-started,loadavg_end=os.getloadavg())
        write(out/'result.json',result);artifact_manifest(out)
    return result

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',choices=['pair','cyan'],default='pair');p.add_argument('--servo-option',choices=['off','visual_pose_mpc_v1'],default='off');p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:print(json.dumps(dict(execution_started=False,bundle_id=BUNDLE_ID,case=a.case,cap_sim_s=CAP)));return 0
    check_source(a.expected_source_sha)
    if os.getpriority(os.PRIO_PROCESS,0)!=0:raise ValueError('nice zero required')
    from scripts import agent_lock
    primary=agent_lock.DEFAULT_ROOT.parent
    if not a.output.is_absolute() or primary.resolve() not in a.output.resolve().parents or a.output.exists():raise ValueError('new primary output required')
    if shutil.disk_usage(primary).free<11*1024**3:raise OSError('10GiB reserve plus1GiB probe budget required')
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s3-no-prior-smoke',purpose='s3fix8 <=60 SIMs '+a.case+' stage probe',pid=os.getpid(),expected_minutes=30,timing_sensitive=True)
    undo=None
    try:
        b=bundle(a.expected_source_sha,a.case,a.servo_option)
        from harness.zone_pair_highpose_exact_speedups import install
        _,undo=install('v98-exact-v6')
        result=run(b,a.output);print(json.dumps(result));return int(result['status']=='HOST_ERROR')
    finally:
        if undo:undo()
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        if a.output.exists():write(a.output/'lock.json',dict(acquired=held,released=released));artifact_manifest(a.output)
if __name__=='__main__':raise SystemExit(main())
