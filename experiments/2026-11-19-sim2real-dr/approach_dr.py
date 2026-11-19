"""Approach + square-up under real-world perturbations (no ACT): where does the handover break?

Runs the evaluated solo approach code (solo_pipeline/harness/approach_survey_v1.py) in the solo
MuJoCo world and measures how far the robot ends from the grasp station at handover. ACT's
taught tolerance is about +-1 cm / 4 deg (docs/sim2real/03_pipeline.md), so the handover pose
decides whether ACT can grasp at all.

Perturbations (each grounded in the real system, see README):
  --gain       wheel displacement scale per pulse (real mm/pulse vs sim)        -> pulse length x gain
  --cmd-delay  laptop->Pi->motor latency (s)                                       -> command starts later
  --cam-delay  camera capture->laptop latency (s)                                  -> older frame is used
  --cam-pitch / --cam-yaw  camera mount angle error (deg)                          -> rotated robot camera
Evaluation values (true poses) are read only after the run, never by the approach code.
"""
from __future__ import annotations
import argparse, collections, json, math, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import importlib.util as ilu
import numpy as np


def load(name, path):
    spec = ilu.spec_from_file_location(name, str(path)); mod = ilu.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def quat_mul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])


def axis_quat(axis, deg):
    h = math.radians(deg) / 2; v = np.array(axis, float) * math.sin(h); return np.array([math.cos(h), *v])


def run(plan, a, c=None, appearance=None, surv=None):
    if c is None:
        from harness import grasp_act_contract as c
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim.render_profile import install
    from sim.final_pair_highpose_nearclip import wrap
    from sim import masterpi_camera_review_v3 as camera
    from sim import s2_realism_camera_binding as binding
    from sim.s2_servo_stiffness import transform_xml as stiffness
    from sim.masterpi_drive_friction_v7 import build_world, PROFILE
    from sim.camera_robot_port import CameraRobotPort
    appearance = appearance or load('solo_appearance_v1', ROOT / 'scripts' / 'solo_appearance_v1.py')
    surv = surv or load('approach_survey_v1', ROOT / 'solo_pipeline' / 'harness' / 'approach_survey_v1.py')

    if a.cam_pitch or a.cam_yaw:
        # Camera-local axes (MuJoCo camera looks along -z, x right, y up): pitch about x, yaw about y.
        q = quat_mul(np.asarray(binding.camera.QUAT_WXYZ, float), quat_mul(axis_quat((1, 0, 0), a.cam_pitch), axis_quat((0, 1, 0), a.cam_yaw)))
        binding.camera.QUAT_WXYZ = tuple(q / np.linalg.norm(q))

    scene = wrap(install(ScenarioFinalV3Scene.from_scenario(plan['scenario_id'], plan['seed']), 'floor_light_v1'))
    scene.config['setup_only']['spawns'] = plan['spawns']
    plan = dict(plan); plan.setdefault('solo_appearance', {'profile': 'solo_green_v1', 'jitter': False})  # evaluated look: green walls, red/blue boxes
    scene = appearance.apply_plan(scene, plan)
    obj = scene.config['setup_only']['objects'][plan['item_id']]
    orig = scene.robot_transform
    def tr(xml, **kw):
        xml = camera.transform_xml(orig(xml, **kw), profile_id=camera.PROFILE_ID)
        for rid in ('r1', 'r2', 'r3'): xml = stiffness(xml, servo_stiffness='real_v1', robot_id=rid)
        return xml
    scene.robot_transform = tr
    world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=640, height=480, render=True,
                        warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None, roller_collision='mesh', idle_robot_contacts='off')
    for ctl in world.controllers.values():
        binding.bind_camera(ctl)
    scene.setup(world)  # places the robots and boxes (same call as the runner)
    rid = plan['robot_id']; port = CameraRobotPort(world, rid); robot = world.robot(rid)
    init = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}
    for s, v in init.items():
        port.apply({'kind': 'look', 'pan_pulse': v} if s == '6' else {'kind': 'arm', 'servo_id': int(s), 'pulse': v}, float(world.data.time))
    end = float(world.data.time) + 1.
    while float(world.data.time) < end - 1e-8:
        port.tick(float(world.data.time)); world._physics_step_for(robot)

    objects = scene.config['setup_only']['objects']
    bodies = {k: world.model.body(v['body_name']).id for k, v in objects.items() if 'body_name' in v}
    def select(entries):  # evaluation-side matching, identical rule to the runner; only the index goes in
        xyz = robot.base_xyz(); yaw = float(robot.base_rpy()[2]); co, si = math.cos(yaw), math.sin(yaw)
        pairs = []
        for i, e in enumerate(entries):
            for k, bid in bodies.items():
                if objects[k]['kind'] != e['kind']: continue
                dx = float(world.data.xpos[bid][0] - xyz[0]); dy = float(world.data.xpos[bid][1] - xyz[1])
                gap = math.hypot(e['x'] - (co*dx + si*dy), e['y'] - (-si*dx + co*dy))
                if gap <= 0.15: pairs.append((gap, i, k))
        ui, uk, chosen = set(), set(), None
        for gap, i, k in sorted(pairs):
            if i not in ui and k not in uk:
                ui.add(i); uk.add(k)
                if k == plan['item_id']: chosen = i
        return chosen
    approach = surv.SurveyApproach(c, select)

    pending = collections.deque()       # (start_time, wheels, durations) after command latency
    active = ([0.]*4, [0.]*4, 0.)       # wheels, deadlines(abs)
    frames = collections.deque()        # (render_time, jpeg) for camera latency
    origin = float(world.data.time); tick = 0; t0 = time.monotonic(); prev_pwm = dict(init)
    while float(world.data.time) - origin < a.cap_s - 1e-8 and not approach.arrived:
        now = float(world.data.time)
        frames.append((now, bytes(base64_decode(port.capture()['image']))))
        while len(frames) > 1 and frames[1][0] <= now - a.cam_delay + 1e-9:
            frames.popleft()
        value = approach.step(frames[0][1], now)
        if value is None: break
        pending.append((now + a.cmd_delay, value))
        tick += 1
        until = origin + tick * c.PERIOD_S
        while float(world.data.time) < until - 1e-8:
            t = float(world.data.time)
            while pending and pending[0][0] <= t + 1e-9:
                start, v = pending.popleft()
                active = (list(v['wheels']), [start + d * a.gain for d in v['duration_s']], start)
                for s in c.SERVOS:  # servos follow the same latency
                    p = v['pwm'][str(s)]
                    if p != prev_pwm[str(s)]:
                        port.apply({'kind': 'look', 'pan_pulse': p} if s == 6 else {'kind': 'arm', 'servo_id': s, 'pulse': p}, t)
                        prev_pwm[str(s)] = p
            port.tick(t)
            port._set_motors(tuple(w if t < dl else 0. for w, dl in zip(active[0], active[1])))
            world._physics_step_for(robot)
    # evaluation only
    bid = bodies[plan['item_id']]
    rot = world.data.xmat[bid].reshape(3, 3); oyaw = math.atan2(rot[1, 0], rot[0, 0])
    base = np.asarray(robot.base_xyz()[:2]); yaw = float(robot.base_rpy()[2]); target = world.data.xpos[bid][:2]
    rel = target - base; d = float(np.linalg.norm(rel)); bearing = math.atan2(rel[1], rel[0]) - yaw
    bearing = math.atan2(math.sin(bearing), math.cos(bearing))
    face = (yaw - oyaw) % (math.pi / 2); face = min(face, math.pi / 2 - face)  # heading vs nearest face normal
    return {'seed': plan['seed'], 'arrived': bool(approach.arrived), 'reason': approach.reason,
            'sim_s': round(float(world.data.time) - origin, 1), 'wall_s': round(time.monotonic() - t0, 1),
            'range_m': round(d, 4), 'lateral_mm': round(1000 * d * math.sin(bearing), 1),
            'bearing_deg': round(math.degrees(bearing), 2), 'face_deg': round(math.degrees(face), 2)}


def base64_decode(s):
    import base64; return base64.b64decode(s)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('plan', type=Path)
    p.add_argument('--gain', type=float, default=1.)
    p.add_argument('--cmd-delay', type=float, default=0.)
    p.add_argument('--cam-delay', type=float, default=0.)
    p.add_argument('--cam-pitch', type=float, default=0.)
    p.add_argument('--cam-yaw', type=float, default=0.)
    p.add_argument('--cap-s', type=float, default=150.)
    p.add_argument('--scene-source', type=Path, help='pinned scene/physics worktree (6f057f7e), as in the evaluated runs')
    p.add_argument('--save-frames', type=Path, help='also save every Nth own-camera JPEG here (perception DR input)')
    p.add_argument('--every', type=int, default=15)
    a = p.parse_args()
    # Same import order as solo_pipeline/scripts/run_grasp_act_student.py: contract, appearance and the approach
    # code come from this checkout; sim/harness packages come from the pinned scene source.
    from harness import grasp_act_contract as c
    appearance = load('solo_appearance_v1', ROOT / 'scripts' / 'solo_appearance_v1.py')
    surv = load('approach_survey_v1', ROOT / 'solo_pipeline' / 'harness' / 'approach_survey_v1.py')
    from contextlib import nullcontext
    from scripts.run_grasp_act_recovery import dependency_modules
    with dependency_modules(a.scene_source) if a.scene_source else nullcontext():
        if a.save_frames:
            from sim.camera_robot_port import CameraRobotPort
            a.save_frames.mkdir(parents=True, exist_ok=True)
            orig_capture, seen, seed = CameraRobotPort.capture, [0], json.loads(a.plan.read_text())['seed']
            def capture(self, *args, **kw):
                r = orig_capture(self, *args, **kw); seen[0] += 1
                if seen[0] % a.every == 0:
                    (a.save_frames / f'{seed}_{seen[0]:04d}.jpg').write_bytes(base64_decode(r['image']))
                return r
            CameraRobotPort.capture = capture
        out = run(json.loads(a.plan.read_text()), a, c, appearance, surv)
    out.update(gain=a.gain, cmd_delay=a.cmd_delay, cam_delay=a.cam_delay, cam_pitch=a.cam_pitch, cam_yaw=a.cam_yaw)
    print(json.dumps(out))
