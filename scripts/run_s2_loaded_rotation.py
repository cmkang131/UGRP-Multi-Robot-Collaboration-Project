"""Clock-only, 60s loaded look-ahead rotation diagnostic; default preview.

Schedule from PR405/762a952f; free-base normal-contact staging from s2v36.
Evaluation can abort physical failure, never choose or correct a command.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import time

import numpy as np

from scripts.diagnose_s2_load_wall import arm_action, measurement
from scripts.run_final_environment_checks import check_source, write

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT/'experiments/2026-10-06-s2-realism/loaded-rotation-criteria.json'
IDENTIFIER = 's2-loaded-rotation-v1'


def schedule():
    # Byte-equivalent pulse vocabulary/timing to egomap32 schedule().
    tick = 40; blocks = []; commands = {}
    for rep in range(1, 6):
        cells = [('single', 1, 1), ('single', -1, 1),
                 ('continuous', 1, 10), ('continuous', -1, 10)]
        if rep % 2 == 0: cells.reverse()
        for mode, sign, pulses in cells:
            blocks.append(dict(repeat=rep, mode=mode, sign=sign, pulses=pulses,
                               start_tick=tick, end_tick=tick+4*pulses,
                               split='fit' if rep<=3 else 'check'))
            for j in range(pulses):
                commands[tick+4*j] = dict(kind='mecanum',forward=0.,left=0.,
                                         turn=sign*.35,duration_s=.10)
            tick += 4*pulses+36
    return blocks, commands, tick


def run(out, source):
    import mujoco
    from PIL import Image
    from sim.s2_realism import make_scene, PhysicalStop
    from sim.s2_realism_camera_binding import bound_world
    from sim.s2_servo_stiffness import transform_xml
    from sim.s2_align_pulse import FinePulsePort
    from sim.masterpi_drive_friction_v7 import PROFILE
    from harness.zone_pair_highpose import HIGH
    from harness.zone_solo_cyan_real_carry import LOOK_AHEAD, transition

    plan = json.loads(PLAN.read_text()); blocks, commands, ticks = schedule()
    parent = Path(plan['parent_bundle']['path'])
    assert hashlib.sha256(parent.read_bytes()).hexdigest()==plan['parent_bundle']['sha256']
    bundle = json.loads(parent.read_text())
    out.mkdir(parents=True,exist_ok=False); (out/'rgb').mkdir()
    write(out/'configuration.json',dict(execution_bundle_id=IDENTIFIER,source_sha=source,
        plan=plan,plan_sha256=hashlib.sha256(PLAN.read_bytes()).hexdigest(),
        options=plan['options'],parent_bundle=bundle,task_controller=False,model_calls=0))
    write(out/'schedule.json',dict(blocks=blocks,commands=commands,ticks=ticks))
    started=time.monotonic(); world=None; frames=[]; issued=[]; evaluation=[]; staging=[]
    result=dict(status='HOST_ERROR',source_sha=source,execution_bundle_id=IDENTIFIER,
        task_run=False,physics_runs=1,model_calls=0,loadavg_start=list(os.getloadavg()),options=plan['options'])
    try:
        scene=make_scene(bundle,plan['setup_seed']);xyz=plan['initial_xyz_m']
        scene.config['setup_only']['spawns']['r3']=[*xyz,0.]
        item=next(iter(scene.config['setup_only']['objects'].values()));item['position_m']=[.5,-.5,.016]
        transform=scene.robot_transform
        scene.robot_transform=lambda xml,**kw:transform_xml(transform(xml,**kw),servo_stiffness='real_v1')
        world=bound_world(scene,drive_profile=PROFILE,idle_robot_contacts='freeze_v1',seed=plan['setup_seed'],
            width=640,height=480,render=True,warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None)
        scene.setup(world);robot=world.robot('r3');m,d=world.model,world.data;dt=float(m.opt.timestep)
        assert abs(.05/dt-round(.05/dt))<1e-7
        (out/'scene.xml').write_text(world.scene_xml)
        # One-time, surveyed setup only. No reset/clamp/qpos correction after this.
        robot.set_servo_pulses({1:2000,**HIGH},forward_only=True)
        robot.set_base_pose_for_test(xyz,0.)
        cargo=m.body(item['body_name']).id;q=int(m.jnt_qposadr[m.body_jntadr[cargo]])
        d.qpos[q:q+3]=robot.site_xyz('grip_site');d.qpos[q+3:q+7]=d.xquat[robot.gripper_bid]
        for jid in robot.gripper_joint:d.qpos[int(m.jnt_qposadr[jid])]=(.0467-.040)/2
        robot.set_servo_pulses({1:1500});mujoco.mj_forward(m,d)
        port=FinePulsePort(world,'r3',allow_reverse=True,allow_mecanum=True,
                           min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
        lost=None

        def sample(monitor=True):
            nonlocal lost
            row=measurement(world,robot,cargo)
            joints=m.actuator_trnid[robot.wheel_act,0]
            row['wheel_qvel_rad_s']=d.qvel[m.jnt_dofadr[joints]].tolist()
            result['last_eval']=row  # retain the aborting sample, too
            if row['active_welds']:raise PhysicalStop('WELD_FORBIDDEN')
            if max(abs(v) for v in row['rpy'][:2])>math.radians(15):raise PhysicalStop('ROBOT_TILT_LIMIT')
            if monitor:
                if row['cargo_xyz'][2]<.06:raise PhysicalStop('LOAD_DROP')
                if not row['bilateral']:
                    if lost is None:lost=row['t']
                    if row['t']-lost>=.3-1e-8:raise PhysicalStop('GRIP_LOSS')
                else:lost=None
                if any(c['category'].startswith('wall_') and c['force_contact_frame'][0]>0 for c in row['contacts']):
                    raise PhysicalStop('NONFREE_WALL_CONTACT')
            return row

        def advance(seconds,monitor=True):
            for i in range(round(seconds/dt)):
                port.tick(float(d.time));world._physics_step_for(robot)
                if i%round(.05/dt)==0:staging.append(sample(monitor))

        advance(.8,False)
        if not sample(False)['bilateral']:raise PhysicalStop('STAGING_GRIP_ABSENT')
        for pose,duration,settle in transition({1:1500,**HIGH},LOOK_AHEAD):
            for sid,pulse in pose.items():
                action=arm_action(sid,pulse);port.apply(action,float(d.time));issued.append(dict(t=float(d.time),**action))
            advance(duration+settle)
        advance(2.)
        t0=float(d.time);result.update(start_sim_s=t0,box_mass_kg=float(m.body_mass[cargo]),
            robot_mass_kg=float(robot.robot_mass_kg),initial=sample(),pose_command=LOOK_AHEAD)
        for tick in range(ticks+1):
            now=float(d.time);row=sample();row['relative_t']=tick/20;evaluation.append(row)
            if tick%4==0:
                rgb=world.render_rgb(robot_id='r3',camera='robot_cam');path=out/'rgb'/f'{len(frames):05d}.jpg'
                Image.fromarray(rgb).save(path,quality=95)
                frames.append(dict(t=now,path=str(path.relative_to(out)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            if tick in commands:
                action=commands[tick];port.apply(action,now);issued.append(dict(t=now,relative_t=tick/20,**action))
            if tick%100==0:print('loaded rotation SIM',tick/20,flush=True)
            if tick<ticks:
                for _ in range(round(.05/dt)):
                    port.tick(float(d.time));world._physics_step_for(robot)
        result.update(status='RECORDED',measurement_sim_s=ticks/20,total_sim_s=float(d.time),
            samples=len(evaluation),frames=len(frames),blocks=len(blocks),pulses=len(commands),
            bilateral_fraction=float(np.mean([r['bilateral'] for r in evaluation])),final=evaluation[-1])
    except Exception as exc:
        result.update(status='PHYSICAL_FAILURE' if isinstance(exc,PhysicalStop) else 'HOST_ERROR',
            failure=dict(type=type(exc).__name__,message=str(exc)),enospc=getattr(exc,'errno',None)==28)
        import traceback
        traceback.print_exc()
    finally:
        if world is not None:world.close()
        write(out/'commands.json',issued);write(out/'frames.json',frames)
        for name,data in [('eval-only.jsonl',evaluation),('staging-eval-only.jsonl',staging)]:
            (out/name).write_text(''.join(json.dumps(row)+'\n' for row in data))
        result.update(wall_s=time.monotonic()-started,loadavg_end=list(os.getloadavg()))
        write(out/'result.json',result)
        write(out/'artifacts.sha256.json',{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifacts.sha256.json'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not a.execute:
        print(json.dumps(dict(execution_started=False,identifier=IDENTIFIER,blocks=len(schedule()[0]),pulses=len(schedule()[1]),sim_s=schedule()[2]/20)));return
    check_source(a.expected_source_sha)
    if not a.output.is_absolute() or not a.output.resolve().is_relative_to('/Users/changmin/projects/ugrp/outputs') or a.output.exists():
        raise ValueError('new primary output required')
    from scripts import agent_lock
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',
        purpose='s2v42 supervised loaded look-ahead rotation measurement',pid=os.getpid(),expected_minutes=15,timing_sensitive=True)
    def timeout(*_):raise TimeoutError('HOST_BUDGET_15_MINUTES')
    signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,900)
    try:result=run(a.output,a.expected_source_sha)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        if a.output.exists():write(a.output/'lock.json',dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))
    print(json.dumps({k:result.get(k) for k in ('status','measurement_sim_s','bilateral_fraction','wall_s','failure')}),flush=True)
    if result['status']!='RECORDED':raise SystemExit(1)


if __name__=='__main__':main()
