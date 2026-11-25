#!/usr/bin/env python3
"""Stand-alone skill tests that run the same robot-side code on the simulator or on a real MasterPi.

  A. pick : look around, approach the nearest box of a colour, square up, ACT grasp and lift
            (real_robot/pick_brain.py = the evaluated solo pick). With --release the fixed set-down
            replay follows (release_code_v1).

    # simulator (same world as the evaluated solo runs)
    python3 scripts/real_skill_test.py pick --side sim --plan experiments/2026-10-15-act-train/act14-plans/91420.json \
        --scene-source <frozen 6f057f7e> --model <actor dir> --actor-python <venv with torch+lerobot> --out runs/sim-91420
    # real robot (Pi runs scripts/masterpi_robot_server.py --board i2c --camera-port 8766)
    python3 scripts/real_skill_test.py pick --side real --host <pi> --kind red \
        --model <actor dir> --actor-python <python> --out runs/real-pick-01

  B. sign : find wall number sign N (ArUco 4x4 id 11-13) with the own camera, drive and stop in front of it
            (real_robot/sign_brain.py = the last part of the evaluated carry, harness/carry_nav_v1.py), arm held.
  C. place: B, then the fixed set-down (release_code_v1). On the simulator (and with --after-pick on the
            robot) a pick (A) comes first so a box is really held; on the robot without it, the operator puts
            the box into the gripper at the hold posture before the start.

    python3 scripts/real_skill_test.py sign  --side sim  --plan <solo plan> --scene-source <...> --sign 12 --out runs/sim-sign12
    python3 scripts/real_skill_test.py sign  --side real --host <pi> --sign 12 --out runs/real-sign12-01
    python3 scripts/real_skill_test.py place --side sim  --plan <solo plan> --scene-source <...> --sign 12 \
        --model <actor dir> --actor-python <python> --out runs/sim-place12
    python3 scripts/real_skill_test.py place --side real --host <pi> --sign 12 --kind red --out runs/real-place12-01

On the simulator B and C use the solo world of the plan with the signs stood on the walls (as the team
runner does with --robot-tags) and r1 placed where a carry stands just after the door: CARRY_PASS_BEYOND_M
(0.6 m) east of the divider wall on the door centre line, facing east. r2 and r3 are parked in the west room.
For C the plan's box red_1 / cyan_1 is moved BOX_AHEAD_M (0.6 m) in front of r1, see there.

Writes into --out: commands.jsonl (every tick: stage, source, command, wall time on the real side),
rgb/NNNNN.jpg (own frames), summary.json (stage reached, approach record, grasp-end rule, ACT latency),
and on the simulator truth.jsonl (evaluation only: base pose and boxes, read after the command).
Success on the real side is what a person writes in operator.json (lifted, held 3 s), see
real_robot/SKILL_TESTS.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from real_robot.pick_brain import PickBrain, Worker  # noqa: E402
from real_robot.sign_brain import SignBrain  # noqa: E402

LIFT_M = 0.03     # evaluation: a box counts as lifted when its centre is this much above where it rested


def sim_lift(truth_rows, hold_s=3.0):
    """Evaluation only: the box that rose most, and whether it stayed >= LIFT_M up for the last hold_s."""
    if not truth_rows:
        return None
    rest = {k: v['xyz'][2] for k, v in truth_rows[0]['boxes'].items()}
    rise = {k: max(r['boxes'][k]['xyz'][2] for r in truth_rows) - rest[k] for k in rest}
    best = max(rise, key=rise.get)
    end_t = truth_rows[-1]['t']
    tail = [r for r in truth_rows if r['t'] >= end_t - hold_s]
    held = bool(tail) and all(r['boxes'][best]['xyz'][2] - rest[best] >= LIFT_M for r in tail) and end_t >= hold_s
    return {'box': best, 'kind': truth_rows[0]['boxes'][best]['kind'], 'max_rise_m': round(rise[best], 4),
            'held_last_s': hold_s, 'lifted_and_held': held}


# B/C start pose on the simulator (see the module text): the door gap of the zone arena runs y -0.2..0.3 in the
# divider at x 2.2 (static_map zone_wide_door_geometry_v3), and a carry stops CARRY_PASS_BEYOND_M = 0.6 beyond it.
DOOR_X, DOOR_Y, PASS_BEYOND_M = 2.2, 0.05, 0.6
SPAWN_Z = 0.032355118817659255          # base height of every solo plan spawn
PARKED = {'r2': [-0.7, 1.1, SPAWN_Z, 0.0], 'r3': [-0.7, 0.6, SPAWN_Z, 0.0]}   # west room, away from boxes and door
# C: box this far east of r1. With 1.0 m (the plan 91421 distance) the grasp left the robot 1.8 m from sign 11,
# where the sign sits on the top edge of the undistorted picture and is never read (sim, 2026-11-19); a box 1.0 m
# north of r1 instead, 0.4 m from the north wall, was not lifted. 0.6 m leaves the robot about 2.2 m from sign 11.
BOX_AHEAD_M = 0.6


def sign_plan(plan, kind=None, box_ahead_m=None):
    """The solo plan with r1 just past the door facing east, r2/r3 parked; for C (kind given) the box of `kind`
    BOX_AHEAD_M east of r1."""
    plan = dict(plan)
    x0 = DOOR_X + PASS_BEYOND_M
    plan['spawns'] = dict(plan['spawns'], r1=[x0, DOOR_Y, SPAWN_Z, 0.0], **PARKED)
    objects = {kind + '_1': [x0 + (BOX_AHEAD_M if box_ahead_m is None else box_ahead_m), DOOR_Y]} if kind else {}
    return plan, objects


def sim_sign(truth_rows, sign, held_box=None):
    """Evaluation only. B: the point CARRY_SETDOWN_M in front of the final base (where the carry sets the box
    down) inside SIGN_AREA[sign]; heading error to the wall normal is reported. C: the held box at rest
    (less than LIFT_M above where it started) inside SIGN_AREA[sign]."""
    import math
    from harness import robot_tags_v1 as tags
    from scripts.run_grasp_act_student import CARRY_SETDOWN_M
    if not truth_rows:
        return None
    x0, x1, y0, y1 = tags.SIGN_AREA[sign]
    inside = lambda x, y: x0 <= x <= x1 and y0 <= y <= y1
    bx, by, yaw = truth_rows[-1]['base']
    face = 0.0 if tags.SIGNS[sign][2] == '-x' else -0.5 * math.pi      # facing the wall the sign is on
    out = {'sign': sign, 'area': tags.SIGN_AREA[sign], 'base': [bx, by, yaw],
           'heading_error_deg': round(math.degrees(math.atan2(math.sin(yaw - face), math.cos(yaw - face))), 1)}
    px, py = bx + CARRY_SETDOWN_M * math.cos(yaw), by + CARRY_SETDOWN_M * math.sin(yaw)
    out.update(setdown_point=[round(px, 3), round(py, 3)], point_in_area=inside(px, py))
    if held_box is not None:
        rest = truth_rows[0]['boxes'][held_box]['xyz'][2]
        bxyz = truth_rows[-1]['boxes'][held_box]['xyz']
        out.update(box=held_box, box_xyz=bxyz, box_at_rest=bxyz[2] - rest < LIFT_M, box_in_area=inside(bxyz[0], bxyz[1]))
        out['placed'] = out['box_at_rest'] and out['box_in_area']
    return out


class PickThenSign:
    """C with a real grasp first: PickBrain until its sequence ends, then SignBrain holding the grasp posture."""

    def __init__(self, pick, sign, kind, zone_close_far=False, log=None):
        # built now, not at the hand-over: on the simulator the step loop runs inside the frozen scene package,
        # whose harness modules differ from the ones the team kit imports
        self.pick, self.log = pick, log
        self.next = SignBrain(sign, held_kind=kind, with_release=True, zone_close_far=zone_close_far)
        self.sign = None

    def start(self):
        return self.pick.start()

    def begin(self, now):
        self.pick.begin(now)

    @property
    def finished(self):
        return self.sign is not None and self.sign.finished

    @property
    def stage(self):
        return self.pick.stage if self.sign is None else self.sign.stage

    def step(self, jpeg, now):
        if self.sign is None and not self.pick.finished:
            return self.pick.step(jpeg, now)
        if self.sign is None:
            self.sign = self.next
            self.sign.hold = self.pick.hold()
            self.sign.begin(now)
            self.sign.previous = dict(self.pick.previous)
        return self.sign.step(jpeg, now)

    def record(self):
        return {'pick': self.pick.record(), 'hold_pwm': self.pick.hold() if self.pick.issued_hist else None,
                'sign': self.sign.record() if self.sign is not None else None}


def _build_adapter(a):
    from real_robot.adapter import Sim2RealAdapter
    from real_robot.calibration import CameraConfig, VisionConfig
    explicit = getattr(a, '_explicit_args', set())
    cal_path = getattr(a, 'calibration', None)
    if cal_path is not None and a.side != 'real':
        raise ValueError('--calibration is only valid with --side real')

    def _override(dest, default_val):
        return dest in explicit or getattr(a, dest, default_val) != default_val

    cam_overrides = {}
    if getattr(a, 'no_sim_camera_warp', False):
        cam_overrides['enabled'] = False
    elif getattr(a, 'sim_camera_warp', False):
        cam_overrides['enabled'] = True
    if _override('camera_f_real', 515.7):
        cam_overrides['f_real'] = float(a.camera_f_real)
    if _override('camera_warp_pitch_deg', 0.0):
        cam_overrides['pitch_offset_deg'] = float(a.camera_warp_pitch_deg)
    if _override('camera_warp_yaw_deg', 0.0):
        cam_overrides['yaw_offset_deg'] = float(a.camera_warp_yaw_deg)
    if _override('camera_warp_roll_deg', 0.0):
        cam_overrides['roll_offset_deg'] = float(a.camera_warp_roll_deg)
    if _override('camera_cx_real', 320.0):
        cam_overrides['cx_real'] = float(a.camera_cx_real)
    if _override('camera_cy_real', 240.0):
        cam_overrides['cy_real'] = float(a.camera_cy_real)

    vis_overrides = {}
    if _override('camera_pitch_offset_deg', 0.0):
        vis_overrides['camera_pitch_offset_deg'] = float(a.camera_pitch_offset_deg)
    if _override('area_scale', 1.0):
        vis_overrides['area_scale'] = float(a.area_scale)
    if _override('red_hue_max', 8):
        vis_overrides['red_hue_max'] = int(a.red_hue_max)
    if _override('red_sat_min', 150):
        vis_overrides['red_sat_min'] = int(a.red_sat_min)

    if cal_path is not None:
        adapter = Sim2RealAdapter.from_file(cal_path, camera_overrides=cam_overrides, vision_overrides=vis_overrides)
    else:
        if cam_overrides.get('enabled', False) and a.side != 'real':
            raise ValueError('--sim-camera-warp is only valid with --side real')
        adapter = Sim2RealAdapter(
            camera=CameraConfig(**cam_overrides),
            vision=VisionConfig(**vis_overrides),
        )
    if adapter.camera.enabled and a.side != 'real':
        raise ValueError('--sim-camera-warp is only valid with --side real')
    return adapter


def run(a):
    pitch_offset = float(getattr(a, 'camera_pitch_offset_deg', 0.0))
    area_scale = float(getattr(a, 'area_scale', 1.0))
    red_hue_max = int(getattr(a, 'red_hue_max', 8))
    red_sat_min = int(getattr(a, 'red_sat_min', 150))
    if not math.isfinite(pitch_offset):
        raise ValueError(f'--camera-pitch-offset-deg must be finite, got {pitch_offset!r}')
    if not math.isfinite(area_scale) or area_scale <= 0.0:
        raise ValueError(f'--area-scale must be finite and > 0, got {area_scale!r}')
    if not 0 <= red_hue_max <= 8:
        raise ValueError(f'--red-hue-max must be an integer in 0..8, got {red_hue_max!r}')
    if not 0 <= red_sat_min <= 255:
        raise ValueError(f'--red-sat-min must be an integer in 0..255, got {red_sat_min!r}')
    adapter = _build_adapter(a)
    with adapter.vision_context():
        _run_with_adapter(a, adapter)


def _run_with_adapter(a, adapter):
    out = Path(a.out)
    (out / 'rgb').mkdir(parents=True, exist_ok=False)
    plan = json.loads(Path(a.plan).read_text()) if a.plan else None
    kind = a.kind or (plan or {}).get('object_kind')
    needs_pick = a.test == 'pick' or (a.test == 'place' and (a.side == 'sim' or a.after_pick))
    if (needs_pick or a.test == 'place') and kind not in ('red', 'cyan'):
        raise SystemExit('--kind red|cyan (or a plan with object_kind)')
    if needs_pick and not (a.model and a.actor_python):
        raise SystemExit('this test grasps with ACT: --model and --actor-python')
    worker = Worker(a.actor_python, a.model, threads=a.actor_threads) if needs_pick else None
    objects = {}
    if a.test == 'pick':
        brain = PickBrain(worker.predict, kind=kind, with_release=a.release)
    elif a.test == 'sign':
        brain = SignBrain(a.sign, zone_close_far=a.zone_close_far)
    elif needs_pick:
        brain = PickThenSign(PickBrain(worker.predict, kind=kind), a.sign, kind, zone_close_far=a.zone_close_far)
    else:
        brain = SignBrain(a.sign, held_kind=kind, with_release=True, zone_close_far=a.zone_close_far)
    if a.side == 'sim' and a.test != 'pick':
        plan, objects = sign_plan(plan, kind if needs_pick else None, getattr(a, 'sim_box_ahead_m', None))
    warper = adapter.frame_transform
    commands = (out / 'commands.jsonl').open('x')
    truth_f = (out / 'truth.jsonl').open('x') if a.side == 'sim' else None
    truth_rows, summary = [], {'test': a.test, 'side': a.side, 'kind': kind, 'sign': getattr(a, 'sign', None),
                               'zone_close_far': getattr(a, 'zone_close_far', False),
                               'release': getattr(a, 'release', None), 'cap_s': a.cap_s, 'plan_seed': plan and plan['seed'],
                               'camera_pitch_offset_deg': adapter.vision.camera_pitch_offset_deg,
                               'area_scale': adapter.vision.area_scale,
                               'red_hue_max': adapter.vision.red_hue_max,
                               'red_sat_min': adapter.vision.red_sat_min,
                               'sim_camera_warp': warper.config() if warper is not None else None,
                               'sim2real_adapter': adapter.summary() if a.side == 'real' else None,
                               'sim_spawn_r1': plan and a.side == 'sim' and plan['spawns']['r1'], 'sim_moved_boxes': objects}
    t0 = time.monotonic()

    def loop(io):
        io.start(brain.start())
        brain.begin(io.now())
        while io.now() - (getattr(io, 'origin', 0.) or 0.) < a.cap_s - 1e-8 and not brain.finished:
            jpeg, now = io.frame(), io.now()
            value, source = brain.step(jpeg, now)
            n = len(truth_rows) if truth_f else getattr(io, 'tick', 0)
            (out / 'rgb' / f'{n:05d}.jpg').write_bytes(jpeg)
            row = {'t': round(now, 3), 'stage': brain.stage, 'source': source, 'command': value}
            io.send(value)
            if a.side == 'real':
                row['wall'] = io.ticks[-1]
            commands.write(json.dumps(row) + '\n')
            if truth_f is not None:
                tr = io.truth(); truth_rows.append(tr); truth_f.write(json.dumps(tr) + '\n')

    try:
        if a.side == 'sim':
            from contextlib import nullcontext
            from scripts.run_grasp_act_recovery import dependency_modules
            with dependency_modules(a.scene_source) if a.scene_source else nullcontext():
                from real_robot.skill_io import SimIO
                io = SimIO(plan, signs_dir=out / 'signs' if a.test != 'pick' else None, objects=objects)
                loop(io)
        else:
            from real_robot.skill_io import RealIO
            io = RealIO(a.host, cmd_port=a.cmd_port, cam_port=a.cam_port, frame_transform=warper)
            try:
                loop(io)
            finally:
                io.close()
    finally:
        if worker is not None:
            worker.close()
        commands.close()
        if truth_f:
            truth_f.close()
        lat = sorted(worker.latencies) if worker is not None else []
        summary.update(brain.record(), finished=brain.finished, wall_s=round(time.monotonic() - t0, 1),
                       act_latency_s={'n': len(lat), 'median': lat[len(lat) // 2] if lat else None,
                                      'max': lat[-1] if lat else None})
        if a.side == 'sim':
            if a.test == 'pick':
                summary['eval_only'] = sim_lift(truth_rows)
            else:
                held = (sim_lift(truth_rows) or {}).get('box') if needs_pick else None
                summary['eval_only'] = sim_sign(truth_rows, a.sign, held)
        (out / 'summary.json').write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: summary.get(k) for k in ('test', 'finished', 'eval_only', 'wall_s')}, default=str))


class _TrackStore(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        explicit = getattr(namespace, '_explicit_args', None)
        if explicit is None:
            explicit = set()
            setattr(namespace, '_explicit_args', explicit)
        explicit.add(self.dest)


class _TrackStoreTrue(argparse.Action):
    def __init__(self, option_strings, dest, default=False, required=False, help=None):
        super().__init__(option_strings=option_strings, dest=dest, nargs=0, const=True,
                         default=default, required=required, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, True)
        explicit = getattr(namespace, '_explicit_args', None)
        if explicit is None:
            explicit = set()
            setattr(namespace, '_explicit_args', explicit)
        explicit.add(self.dest)


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='test', required=True)
    for name in ('pick', 'sign', 'place'):
        k = s.add_parser(name)
        k.add_argument('--side', choices=('sim', 'real'), required=True)
        k.add_argument('--plan', help='sim: solo plan json (scene, seed, spawns)')
        k.add_argument('--scene-source', help='sim: frozen 6f057f7e scene package')
        k.add_argument('--host', help='real: Pi address')
        k.add_argument('--calibration', help='real: per-robot Sim2Real profile JSON (loads camera warp + vision thresholds)')
        k.add_argument('--cmd-port', type=int, default=8765)
        k.add_argument('--cam-port', type=int, default=8766)
        k.add_argument('--kind', choices=('red', 'cyan'))
        k.add_argument('--model')
        k.add_argument('--actor-python')
        k.add_argument('--actor-threads', type=int, default=1, choices=(1, 2, 4, 8, 16))
        k.add_argument('--cap-s', type=float, default=320., help='control seconds (the evaluated runs: <= 320)')
        k.add_argument('--camera-pitch-offset-deg', type=float, default=0.0, action=_TrackStore,
                       help='real: opt-in camera mount pitch offset in degrees (+ = steeper downward than model, default 0.0)')
        k.add_argument('--area-scale', type=float, default=1.0, action=_TrackStore,
                       help='real: opt-in target blob area scale vs sim A_ref_px (default 1.0)')
        k.add_argument('--red-hue-max', type=int, default=8, action=_TrackStore,
                       help='real: opt-in OpenCV low-red hue max 0..8 (default 8; set 0 to ignore orange MasterPi wheels)')
        k.add_argument('--red-sat-min', type=int, default=150, action=_TrackStore,
                       help='real: opt-in OpenCV red HSV saturation min 0..255 (default 150; e.g. 185 ignores human skin)')
        k.add_argument('--sim-camera-warp', action=_TrackStoreTrue, default=False,
                       help='real: opt-in cv2.remap warp from real camera intrinsics/pitch to sim camera (default off)')
        k.add_argument('--no-sim-camera-warp', action=_TrackStoreTrue, default=False,
                       help='real: explicitly disable camera warp even if enabled in --calibration')
        k.add_argument('--camera-f-real', type=float, default=515.7, action=_TrackStore,
                       help='real: focal length (px) for --sim-camera-warp (default 515.7)')
        k.add_argument('--camera-warp-pitch-deg', type=float, default=0.0, action=_TrackStore,
                       help='real: physical mount pitch offset (deg, + = steeper downward) for --sim-camera-warp (default 0.0)')
        k.add_argument('--camera-warp-yaw-deg', type=float, default=0.0, action=_TrackStore,
                       help='real: physical mount yaw offset (deg, + = camera pointed right) for --sim-camera-warp (default 0.0)')
        k.add_argument('--camera-warp-roll-deg', type=float, default=0.0, action=_TrackStore,
                       help='real: physical mount roll offset (deg, + = clockwise) for --sim-camera-warp (default 0.0)')
        k.add_argument('--camera-cx-real', type=float, default=320.0, action=_TrackStore,
                       help='real: principal point x (px) for --sim-camera-warp (default 320.0)')
        k.add_argument('--camera-cy-real', type=float, default=240.0, action=_TrackStore,
                       help='real: principal point y (px) for --sim-camera-warp (default 240.0)')
        k.add_argument('--out', required=True)
        if name == 'pick':
            k.add_argument('--release', action='store_true', help='set the box down again after the lift (release_code_v1)')
        else:
            k.add_argument('--sign', type=int, choices=(11, 12, 13), required=True)
            k.add_argument('--zone-close-far', action='store_true',
                           help='close sign check of the phase-2 runs (2.3 m first close look, read up to 3.3 m); '
                                'needs the phase-2 execution layer laid over the repository (phase2_pipeline/README.md)')
        if name == 'place':
            k.add_argument('--after-pick', action='store_true', help='real: grasp with ACT first (always on the simulator)')
            k.add_argument('--sim-box-ahead-m', type=float, help='sim: box this far east of r1 (default BOX_AHEAD_M)')
    return p


def main(argv=None):
    p = build_parser()
    a = p.parse_args(argv)
    if a.side == 'sim' and not a.plan:
        p.error('--side sim needs --plan')
    if a.side == 'real' and not a.host:
        p.error('--side real needs --host')
    if a.calibration and a.side != 'real':
        p.error('--calibration is only valid with --side real')
    if a.sim_camera_warp and a.no_sim_camera_warp:
        p.error('--sim-camera-warp and --no-sim-camera-warp are mutually exclusive')
    if not math.isfinite(a.camera_pitch_offset_deg):
        p.error('--camera-pitch-offset-deg must be finite')
    if not math.isfinite(a.area_scale) or a.area_scale <= 0.0:
        p.error('--area-scale must be finite and > 0')
    if not 0 <= a.red_hue_max <= 8:
        p.error('--red-hue-max must be an integer in 0..8')
    if not 0 <= a.red_sat_min <= 255:
        p.error('--red-sat-min must be an integer in 0..255')
    if a.sim_camera_warp:
        if a.side != 'real':
            p.error('--sim-camera-warp is only valid with --side real')
        if not math.isfinite(a.camera_f_real) or a.camera_f_real <= 0.0:
            p.error('--camera-f-real must be finite and > 0')
        for flag, val in (
            ('--camera-warp-pitch-deg', a.camera_warp_pitch_deg),
            ('--camera-warp-yaw-deg', a.camera_warp_yaw_deg),
            ('--camera-warp-roll-deg', a.camera_warp_roll_deg),
        ):
            if not math.isfinite(val) or not -60.0 <= val <= 60.0:
                p.error(f'{flag} must be finite in [-60, 60]')
        if not (math.isfinite(a.camera_cx_real) and math.isfinite(a.camera_cy_real)):
            p.error('--camera-cx-real and --camera-cy-real must be finite')
    run(a)


if __name__ == '__main__':
    main()
