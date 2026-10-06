"""Stationary S2 calibration jig: known fixture, RGB targets, separate GT audit.

The jig fixes the chassis at a surveyed level pose (hardware: clamp to a level
stand). Normal arm, finger and cargo contacts remain; there are no cargo welds.
This setup is calibration only and can never count as a transport trial.
"""
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from harness import s2_extrinsic_targets as target


def board_xml(xml):
    root=ET.fromstring(xml)
    asset=root.find('asset')
    for name, colour in [('white','1 1 1 1'),('black','0 0 0 1')]:
        ET.SubElement(asset,'material',name='cal_'+name,rgba=colour,emission='1',specular='0',reflectance='0')
    body=ET.SubElement(root.find('worldbody'),'body',name='cal_board',pos='0 0 3')
    ET.SubElement(body,'geom',name='cal_border',type='box',size='1 1 .00001',pos='0 0 .00003',
                  material='cal_white',contype='0',conaffinity='0',group='2')
    for y in range(6):
        for x in range(9):
            ET.SubElement(body,'geom',name=f'cal_{x}_{y}',type='box',size='1 1 .00001',
                pos='0 0 .00001',material='cal_'+('black' if (x+y)%2==0 else 'white'),
                contype='0',conaffinity='0',group='2')
    return ET.tostring(root,encoding='unicode')


def capture(out, source_sha):
    import cv2
    import mujoco
    from PIL import Image
    from sim.s2_realism import make_scene
    from sim.s2_realism_camera_binding import bound_world
    from sim.masterpi_drive_friction_v7 import PROFILE
    from sim.s2_eval_camera_trace import camera_row
    from harness.python_source_closure import source_closure
    from scripts.run_final_environment_checks import write
    c=target.contract
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    bundle=c.bundle(source_sha,seed=1047,**c.NEW_OPTIONS)  # setup design only, no task/control/seed claim
    scene=make_scene(bundle,0)
    transform=scene.transform
    scene.transform=lambda xml:board_xml(transform(xml))
    scene.config['setup_only']['spawns']['r3']=[*target.FIXTURE,0.]
    item=next(iter(scene.config['setup_only']['objects'].values()))
    item['position_m']=[.5,-1.,.016]
    world=None;rows=[];audit=[]
    try:
        world=bound_world(scene,drive_profile=PROFILE,idle_robot_contacts='freeze_v1',seed=0,
            width=640,height=480,render=True,warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None)
        robot=world.robot('r3');original=world._physics_step_for
        def jig_step(*args,**kwargs):
            if world.data.time>360.:raise RuntimeError('CALIBRATION_SIM_CAP')
            value=original(*args,**kwargs)
            # Known fixture boundary, never a measured pose passed to fitting.
            world.data.qpos[robot.base_qadr:robot.base_qadr+7]=[*target.FIXTURE,1,0,0,0]
            world.data.qvel[robot.base_dadr:robot.base_dadr+6]=0
            mujoco.mj_forward(world.model,world.data)
            return value
        world._physics_step_for=jig_step
        scene.setup(world)
        write(out/'scene.json',scene.record())
        (out/'scene.xml').write_text(world.scene_xml)
        write(out/'fixture.json',dict(chassis_pose=[*target.FIXTURE,1,0,0,0],calibration_only=True,
            hardware_procedure='Level chassis clamp at surveyed floor height; surveyed board corners; identical commanded pose/load; wait 8 s',
            cargo_weld=False,load='cyan 30 g, fingers only',intrinsics_K=target.K.tolist(),fisheye_D=target.D.tolist()))
        loaded=False
        for state,pose in target.poses():
            if state=='loaded' and not loaded:
                # Manual placement in a fixed grasp station, then pre-authored
                # ordinary descent/close. No success/GT steers these commands.
                hover,path=target.grasp_postures()
                world._team_joint_move_servos({'r3':{1:2000,**hover}},1.2,settle_s=2.8)
                joint=world.model.joint(item['joint_name']);q=int(joint.qposadr[0]);v=int(joint.dofadr[0])
                from harness.zone_final_pair_vision import GRASP_RADIUS_M
                radius=GRASP_RADIUS_M
                world.data.qpos[q:q+7]=[target.FIXTURE[0]+radius,target.FIXTURE[1],.016,1,0,0,0]
                world.data.qvel[v:v+6]=0;mujoco.mj_forward(world.model,world.data)
                for p in path:world._team_joint_move_servos({'r3':p},.12)
                world._team_joint_move_servos({'r3':{1:1500}},.6,settle_s=1.)
                loaded=True
            world._team_joint_move_servos({'r3':{1:1500 if loaded else 2000,**pose}},1.2,settle_s=8.)
            for board in target.boards(pose):
                axes=np.asarray(board['rotation']);p=np.asarray(board['origin_m'])+[target.FIXTURE[0],target.FIXTURE[1],0]
                body=world.model.body('cal_board');body.pos[:]=p
                quat=np.zeros(4);mujoco.mju_mat2Quat(quat,axes.ravel());body.quat[:]=quat
                s=board['square_m'];border=world.model.geom('cal_border');border.size[:2]=[5.5*s,4*s]
                for y in range(6):
                    for x in range(9):
                        geom=world.model.geom(f'cal_{x}_{y}')
                        geom.pos[:2]=[(x-4)*s,(y-2.5)*s];geom.size[:2]=s/2
                mujoco.mj_forward(world.model,world.data)
                rgb=world.render_rgb(robot_id='r3',camera='robot_cam')
                filename=f'{state}-{target.key(pose)}-{board["index"]}.png'
                Image.fromarray(rgb).save(out/filename)
                row=dict(state=state,servo=pose,pose_key=target.key(pose),path=filename,
                    sha256=c.old.hp.base.sha(out/filename),sim_time=float(world.data.time),**board)
                try:row['corners_px']=target.detect(rgb).tolist();row['status']='detected'
                except ValueError as exc:row['status']=str(exc)
                rows.append(row);write(out/'observations.json',rows)
                # Evaluation-only sidecar, not read by the PnP assembler.
                cam=camera_row(world,'r3',float(world.data.time));cargo=world.data.body(item['body_name'])
                contacts=[]
                fingerids={world.model.geom('r3__'+side+'_finger').id for side in ('left','right')}
                for contact in world.data.contact[:world.data.ncon]:
                    a,b=int(contact.geom1),int(contact.geom2)
                    if a in fingerids and world.model.geom_bodyid[b]==cargo.id:contacts.append(a)
                    if b in fingerids and world.model.geom_bodyid[a]==cargo.id:contacts.append(b)
                audit.append(dict(path=filename,pose_key=row['pose_key'],state=state,camera=cam,
                    cargo_xyz_m=cargo.xpos.tolist(),bilateral_contacts=len(set(contacts))==2,
                    active_weld_count=sum(int(world.data.eq_active[i]) for i in range(world.model.neq)
                        if world.model.eq_type[i]==mujoco.mjtEq.mjEQ_WELD)))
                write(out/'eval_only.json',audit)
            print(state,target.key(pose),[r['status'] for r in rows[-3:]],flush=True)
        write(out/'result.json',dict(status='CAPTURE_COMPLETED',classification='S2_DEV_calibration_not_transport',
            source_sha=source_sha,observations=len(rows),detected=sum(r['status']=='detected' for r in rows),
            wall_s=time.monotonic()-start,sim_s=float(world.data.time),options=dict(idle_robot_contacts='freeze_v1'),
            fixture=True,model_calls=0,source_sha256={p:c.old.hp.base.sha(c.ROOT/p) for p in source_closure(c.ROOT,
                ['scripts/capture_s2_extrinsics.py','sim/s2_extrinsic_capture.py'])}))
    finally:
        if world is not None:world.close()
