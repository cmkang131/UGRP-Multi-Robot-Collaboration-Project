"""Three fixed REAL-style pulses on native v7. Eval-only measurements, no mission controller."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time
from harness import s2_real_output_diagnostic as contract
from harness.zone_solo_cyan_real_output import primitive
from scripts.run_final_environment_checks import check_source,write


def run_case(row,bundle,out):
    import numpy as np
    from sim.s2_realism import make_scene
    from sim.s2_realism_camera_binding import bound_world
    from sim.s2_real_output import RealPrimitivePort
    from harness.owncam_pair_beam_v2 import pose_of
    out.mkdir()
    task_bundle={**bundle,'task':dict(seed=row['seed'],robot_id='r3',pickup_slot='P1-2',destination='B')}
    scene=make_scene(task_bundle,row['seed'])
    scene.config['setup_only']['spawns']['r3']=[3.,-1.,.0325,0.]
    world=None;started=time.monotonic();trace=[]
    result=dict(seed=row['seed'],case=row['axis'],status='HOST_ERROR',model_calls=0,
                source_sha=bundle['source_sha'],execution_bundle_id=contract.BUNDLE_ID,
                scope='unloaded setup-only exploration; no mission/hardware claim',loadavg_start=os.getloadavg())
    try:
        world=bound_world(scene,drive_profile='masterpi_drive_friction_v7',seed=row['seed'],render=False,
                          warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None)
        scene.setup(world)
        robot=world.robot('r3');robot.set_servo_pulses({**pose_of('search'),1:2000},forward_only=True)
        dt=float(world.model.opt.timestep)
        for _ in range(round(1./dt)):world._physics_step_for(robot)
        p=RealPrimitivePort(world,'r3',allow_reverse=True,allow_mecanum=True,min_wheel_cmd=bundle['options']['min_wheel_cmd'])
        request=dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=.1)
        request[row['axis']]=.1
        command=primitive(request,bundle['options']['min_wheel_cmd'])
        start=float(world.data.time);end=command['duration_s']+4.
        p.apply(command,start)
        for step in range(round(end/dt)+1):
            now=float(world.data.time)-start
            if step % round(.01/dt)==0:
                body=world.data.body('r3__robot')
                tilt=math.degrees(math.acos(float(np.clip(body.xmat[8],-1,1))))
                trace.append(dict(t=now,xyz=body.xpos.tolist(),yaw=math.atan2(body.xmat[3],body.xmat[0]),
                    wheel_command=robot.motor_command.tolist(),relay=world.drive_input_state.get('r3',np.zeros(4,dtype=int)).tolist(),
                    tilt_deg=tilt,base_external_force=world.data.xfrc_applied[body.id].tolist()))
                if tilt>=10:raise RuntimeError('ROBOT_TILT_LIMIT')
            if step==round(end/dt):break
            p.tick(float(world.data.time));world._physics_step_for(robot)
        p.stop()
        delta=np.asarray(trace[-1]['xyz'][:2])-trace[0]['xyz'][:2]
        yaw0=trace[0]['yaw'];c,s=math.cos(yaw0),math.sin(yaw0)
        dbody=[c*delta[0]+s*delta[1],-s*delta[0]+c*delta[1],math.atan2(math.sin(trace[-1]['yaw']-yaw0),math.cos(trace[-1]['yaw']-yaw0))]
        cal=contract.parent.old.hp.base.read(contract.ROOT/contract.parent.old.CALIBRATION)
        predicted=(np.asarray(cal['params']['motion']['gain'])@np.array([command[k] for k in ('forward','left','turn')])*command['duration_s']).tolist()
        errors=(np.asarray(dbody)-predicted).tolist()
        i=('forward','left','turn').index(row['axis'])
        relative=abs(errors[i])/max(abs(dbody[i]),1e-5)
        result.update(status='MEASURED_DEV',command=command,request=request,sim_s=end,
                      observed_delta_body=dbody,inherited_prediction=predicted,error=errors,relative_main_axis_error=relative,
                      refit_required=relative>.25 or math.hypot(*errors[:2])>.01 or abs(errors[2])>math.radians(2),
                      max_tilt_deg=max(r['tilt_deg'] for r in trace),applied_drive_profile=world.drive_profile_record)
    except Exception as exc:
        result['failure']=str(exc)
        if str(exc)=='ROBOT_TILT_LIMIT':result['status']='PHYSICAL_FAILURE'
    finally:
        if world is not None:world.close()
        result.update(wall_s=time.monotonic()-started,loadavg_end=os.getloadavg())
        write(out/'result.json',result)
        (out/'trajectory.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in trace))
        write(out/'artifacts.sha256.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--min-wheel-cmd',choices=('off','real_v1'),default='off');p.add_argument('--execute',action='store_true')
    args=p.parse_args();b=contract.bundle(args.expected_source_sha,min_wheel_cmd=args.min_wheel_cmd)
    if not args.execute:print(json.dumps(b));return
    check_source(args.expected_source_sha)
    from scripts.agent_lock import DEFAULT_ROOT,status
    lock=status(DEFAULT_ROOT)
    if not lock or not lock['pid_alive'] or lock['owner']!='codex' or lock['branch']!='codex/s2-realism':
        raise ValueError('owned active agent lock required')
    if not args.output.is_absolute() or not args.output.is_relative_to('/Users/changmin/projects/ugrp/outputs'):
        raise ValueError('primary output path required')
    args.output.mkdir(exist_ok=False);write(args.output/'bundle.json',b)
    results=[]
    for row in b['task']['runs']:
        result=run_case(row,b,args.output/f"s{row['seed']}-{row['axis']}");results.append(result)
        if result['status']!='MEASURED_DEV':break
    write(args.output/'result.json',dict(source_sha=args.expected_source_sha,execution_bundle_id=contract.BUNDLE_ID,
          status='COMPLETED_DIAGNOSTIC' if len(results)==3 and all(r['status']=='MEASURED_DEV' for r in results) else 'DIAGNOSTIC_FAILED',
          model_calls=0,runs=results))
    return 0 if len(results)==3 and all(r['status']=='MEASURED_DEV' for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
