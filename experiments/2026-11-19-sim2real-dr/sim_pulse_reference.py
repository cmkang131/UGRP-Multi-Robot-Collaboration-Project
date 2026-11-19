"""Sim reference: body displacement of one wheel pulse per sim value (solo world, no ACT, no rendering). Used by scripts/fit_real_robot_calibration.py."""
import json, math, sys, time
sys.path.insert(0, '.')
import importlib.util as ilu
import numpy as np
from sim.zone_scenario_scene import ScenarioFinalV3Scene
from sim.render_profile import install
from sim.final_pair_highpose_nearclip import wrap
from sim import masterpi_camera_review_v3 as camera
from sim.s2_servo_stiffness import transform_xml as stiffness
from sim.masterpi_drive_friction_v7 import build_world, PROFILE
from sim.camera_robot_port import CameraRobotPort
spec = ilu.spec_from_file_location('app', 'solo_pipeline/scripts/solo_appearance_v1.py')
plan = json.load(open(sys.argv[1]))
scene = wrap(install(ScenarioFinalV3Scene.from_scenario(plan['scenario_id'], plan['seed']), 'floor_light_v1'))
scene.config['setup_only']['spawns'] = plan['spawns']
orig = scene.robot_transform
def tr(xml, **kw):
    xml = camera.transform_xml(orig(xml, **kw), profile_id=camera.PROFILE_ID)
    for rid in ('r1','r2','r3'): xml = stiffness(xml, servo_stiffness='real_v1', robot_id=rid)
    return xml
scene.robot_transform = tr
t0=time.time()
world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=640, height=480, render=False,
    warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None, roller_collision='mesh', idle_robot_contacts='off')
print('build', round(time.time()-t0,1), file=sys.stderr)
rid = plan['robot_id']; port = CameraRobotPort(world, rid); robot = world.robot(rid)
PAT = {'forward': (1,1,1,1), 'left': (-1,1,1,-1), 'yaw_left': (-1,1,-1,1)}
init = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}
for s,v in init.items():
    port.apply({'kind':'look','pan_pulse':v} if s=='6' else {'kind':'arm','servo_id':int(s),'pulse':v}, float(world.data.time))
def settle(sec):
    end=float(world.data.time)+sec
    while float(world.data.time)<end-1e-8:
        port.tick(float(world.data.time)); port._set_motors((0.,)*4); world._physics_step_for(robot)
settle(1.0)
def pose():
    x,y,_=robot.base_xyz(); return np.array([x,y]), float(robot.base_rpy()[2])
rows=[]
for direction, pat in PAT.items():
    for val in (0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38, 0.39, 0.40):
        for dur, rep in [(d, r) for d in (0.05, 0.10, 0.15) for r in range(3)]:
            p0,y0=pose(); start=float(world.data.time)
            while float(world.data.time) < start+dur-1e-8:
                port._set_motors(tuple(val*s for s in pat)); world._physics_step_for(robot)
            settle(0.6)
            p1,y1=pose(); d=p1-p0
            fwd = d[0]*math.cos(y0)+d[1]*math.sin(y0); lat=-d[0]*math.sin(y0)+d[1]*math.cos(y0)
            dyaw=math.atan2(math.sin(y1-y0),math.cos(y1-y0))
            rows.append(dict(seed=plan['seed'],rep=rep,direction=direction,value=val,pulse_s=dur,forward_mm=round(fwd*1000,2),lateral_mm=round(lat*1000,2),dyaw_rad=round(dyaw,4)))
            print(json.dumps(rows[-1]), flush=True)
print('total', round(time.time()-t0,1), file=sys.stderr)
