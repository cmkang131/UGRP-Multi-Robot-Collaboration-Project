"""e2e1 setup-only first RGB audit, x86 persistent disk only; no controller/model."""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = {'base':[3.9,-1.4,.032355118817659255,-.7853981633974483],
              'A':[3.65,-1.15,.032355118817659255,-.7853981633974483],
              'B':[4.05,-1.25,.032355118817659255,-1.0471975511965976]}


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def run(out, candidate, sha):
    from sim.zone_scenario_scene import load_scenario, ScenarioFinalV3Scene
    from sim.masterpi_drive_friction_v7 import build_world, PROFILE
    from sim.camera_robot_port import CameraRobotPort
    from PIL import Image
    import mujoco
    import numpy as np
    start = time.monotonic(); world = None
    result = dict(schema='ugrp.e2e1.first_frame.v1',status='HOST_ERROR',candidate=candidate,source_sha=sha,
        seed=61001,controller_runs=0,model_calls=0,scope='setup_only_first_RGB',
        loadavg_start=list(os.getloadavg()),camera_changed=False,weld='off',motion_expected=False)
    out.mkdir(parents=True,exist_ok=False)
    try:
        scenario=load_scenario('e2e_one_beam_ownmap')
        scenario['eval']['setup']['robot_spawns']['r1']=copy.deepcopy(CANDIDATES[candidate])
        scene=ScenarioFinalV3Scene.from_scenario(scenario,61001)
        world=build_world(scene,drive_profile=PROFILE,seed=61001,width=640,height=480,render=True,
            warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None)
        scene.setup(world)  # one standard initialization; never restore a stage
        write(out/'scenario.json',scenario);write(out/'scene.json',scene.manifest)
        (out/'scene.xml').write_text(world.scene_xml)
        assert not world.data.eq_active.any()
        frames={}; masks={}
        for rid in ('r1','r2','r3'):
            port=CameraRobotPort(world,rid,allow_reverse=True,allow_mecanum=True)
            obs=port.capture(); data=base64.b64decode(obs.pop('image'))
            (out/f'{rid}-first.jpg').write_bytes(data)
            write(out/f'{rid}-first.json',obs)
            # Referee-only pixel attribution. Never returned to an input builder.
            def segment():
                robot=world.robot(rid)
                with world.physics_lock,world.render_lock:
                    robot._sync_real_camera_mount()
                    world.renderer.enable_segmentation_rendering()
                    try:
                        world.renderer.update_scene(world.data,camera=robot._n('robot_cam'),
                            scene_option=robot._robot_sensor_scene_option)
                        seg=world.renderer.render().copy()
                    finally:world.renderer.disable_segmentation_rendering()
                    mask=((seg[:,:,0]==world.model.geom('zone_zone_B').id)&(seg[:,:,1]==int(mujoco.mjtObj.mjOBJ_GEOM))).astype('uint8')
                    if robot._robot_fisheye_map is not None:
                        import cv2
                        mx,my=robot._robot_fisheye_map
                        mask=cv2.remap(mask,mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT)
                    return mask
            mask=world._render_executor.submit(segment).result(timeout=30)
            masks[rid]=int(mask.sum())
            (out/'eval_only').mkdir(exist_ok=True)
            Image.fromarray(mask*255).save(out/f'eval_only/{rid}-B-mask.png')
            frames[rid]=dict(frame_id=obs['frame_id'],sim_s=obs['sim_time'],sha256=obs['sha256'])
        matched=masks['r1']>=100 and masks['r2']==0
        result.update(status='PASS' if matched else 'INFORMATION_GAP_FAIL',B_visible_pixels=masks,
            first_frames=frames,sim_s=float(world.data.time),initial_check=dict(
                exception_free=True,first_frames_written=3,stationary_setup_only=True,
                controller_command_check='not_applicable_no_controller',information_gap=matched),
            B_floor_size_m=[.8,1.4],past_success_inherited=False)
        write(out/'eval_only/setup.json',scene.config['setup_only'])
    except Exception:
        result['failure']=traceback.format_exc()
        result['initial_check']=dict(exception_free=False,exit_recorded=True)
    finally:
        if world is not None:world.close()
        result.update(wall_s=time.monotonic()-start,loadavg_end=list(os.getloadavg()))
        write(out/'result.json',result)
        write(out/'artifacts.sha256.json',{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.rglob('*')) if p.is_file()})
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--candidate',choices=CANDIDATES,default='base')
    p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:print(json.dumps(dict(execution_started=False,scope='e2e1_first_frame')));return 0
    if platform.system()!='Linux' or platform.machine()!='x86_64' or os.environ.get('MUJOCO_GL')!='osmesa':
        raise ValueError('ORACLE_X86_OSMESA_ONLY')
    out=a.output.resolve();persistent=(Path.home()/'ugrp-sim/runs').resolve()
    if not out.is_relative_to(persistent) or out.exists():raise ValueError('NEW_PERSISTENT_RUN_PATH_REQUIRED')
    if ROOT.name!=a.expected_source_sha or len(a.expected_source_sha)!=40:raise ValueError('COMMITTED_ARCHIVE_REQUIRED')
    if os.getloadavg()[0]>=51:raise RuntimeError('LOAD_ADMISSION_REJECTED')
    available=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
    if available<6*1024**3 or shutil.disk_usage(persistent).free<10*1024**3:raise OSError('MEMORY_OR_DISK_ADMISSION_REJECTED')
    result=run(out,a.candidate,a.expected_source_sha);print(json.dumps(result));return int(result['status']=='HOST_ERROR')

if __name__=='__main__':raise SystemExit(main())
