#!/usr/bin/env python3
"""Short MuJoCo probe of the hidden-event hooks on the REAL study host (PR #257 review P1-G/H/I).

DIAGNOSTIC ONLY, not a study result: no model call, no study layer, no robot
decision. Two ``StudyTeamHost`` worlds of the integration prereg's first episode
are stepped identically; only one has hidden events. In both, a ground-truth
teacher (evaluation-side, AGENTS.md teacher exception) places one cyan box in
front of r1 and grasps it with ``scripts/zone_teacher``'s own arm sequence and
grip IK (normal contact physics, weld OFF), and r2 is sent the same drive
commands. Then, in the event world only:

* ``item_dropped`` (gripper servo fault): does the held box really fall, while
  the control world keeps it?
* ``robot_hold`` (wheels blocked at the actuator): does r2 really stand still,
  while the control world drives on?
* ``passage_blocked``: the parked obstacle is in the scene and moves up.

Both worlds must show each robot the SAME issued-command rows and the SAME
``actuator_state`` in every own-camera capture (the fault never reaches the
robot's own command record), and the event world's scene XML must equal the
control world's apart from the hidden obstacle body. Raw output goes to the
primary checkout's ``outputs/`` and is never overwritten.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import zone_study_referee as zr  # noqa: E402
from harness.visual_arm import solve_grip_ik, tool_pose  # noqa: E402
from scripts import run_zone_study_integration as runner  # noqa: E402
from scripts.zone_teacher import CLOSED, GRASP_RADIUS_M, GRASP_Z_M, HOVER_Z_M, OPEN, ArmSequence  # noqa: E402
from sim import zone_hidden_events as zhe  # noqa: E402
from sim.zone_arena import BOX_HALF  # noqa: E402

PREREG = ROOT / 'experiments/2026-09-26-zone-study-integration/prereg.json'
CONTROL_S = .02
T_START, T_GRASP_CHECK, T_EVENT, T_HOLD_S, T_END = .6, 6.2, 6.6, 2.0, 9.8
DRIVE = {'kind': 'drive', 'forward': .1, 'turn': 0., 'duration_s': .6}
DRIVE_EVERY_S = .5
OBSTACLE = {'obstacle_id': 'probe_pallet', 'center_m': [2.2, .05], 'half_extents_m': [.15, .22], 'height_m': .12}


def events():
    ev = lambda eid, kind, target: {'event_id': eid, 'kind': kind,  # noqa: E731
                                    'trigger': {'kind': 'sim_time', 'at_sim_s': T_EVENT}, 'target': target}
    return [ev('probe_drop', 'item_dropped', {'item_id': None}),       # item id filled in below
            ev('probe_hold', 'robot_hold', {'robot_id': 'r2', 'duration_s': T_HOLD_S}),
            ev('probe_block', 'passage_blocked', {'passage': 'probe_door', 'obstacle': OBSTACLE})]


class CommandPort:
    """``ArmSequence`` port that goes through the host's own command path (rows + port)."""

    def __init__(self, host, rid):
        self.host, self.rid = host, rid

    def apply(self, action, now):
        self.host._apply(self.rid, action, now)


def tap_captures(host):
    """Record the actuator_state each own-camera capture shows its robot (the robot-visible command state)."""
    seen = {rid: [] for rid in runner.ROBOTS}
    for rid, slot in host.robots.items():
        capture = slot.port.capture

        def tapped(camera='robot_cam', _capture=capture, _rid=rid):
            obs = _capture(camera)
            seen[_rid].append({'t': round(float(obs['sim_time']), 4), 'actuator_state': copy.deepcopy(obs['actuator_state'])})
            return obs
        slot.port.capture = tapped
    return seen


def build(name, out, schedule, provider, spec, student):
    host = runner.StudyTeamHost(spec, student, root=ROOT, provider_spec=provider,
                                frames_dir=out / 'own_frames' / name, hidden=schedule)
    return host, tap_captures(host)


def place_box(host, rid, item):
    """Teacher setup: the box on the floor GRASP_RADIUS_M in front of ``rid``, aligned with it."""
    import mujoco
    robot = host.world.robot(rid)
    x, y, yaw = float(robot.base_xyz()[0]), float(robot.base_xyz()[1]), float(robot.base_rpy()[2])
    m, d = host.world.model, host.world.data
    body = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, host.objects[item]['body_name'])
    jid = int(m.body_jntadr[body])
    q, v = int(m.jnt_qposadr[jid]), int(m.jnt_dofadr[jid])
    bx, by = x + GRASP_RADIUS_M * math.cos(yaw), y + GRASP_RADIUS_M * math.sin(yaw)
    d.qpos[q:q + 7] = [bx, by, BOX_HALF[2], math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
    d.qvel[v:v + 6] = 0
    mujoco.mj_forward(m, d)
    return [round(bx, 4), round(by, 4)]


def grasp_targets(host, rid, item):
    """``scripts/zone_teacher.TeacherRobot._grasp_targets`` for this robot and box (teacher truth)."""
    robot = host.world.robot(rid)
    x, y, yaw = float(robot.base_xyz()[0]), float(robot.base_xyz()[1]), float(robot.base_rpy()[2])
    box = host.world.data.body(host.objects[item]['body_name']).xpos
    dx, dy = float(box[0]) - x, float(box[1]) - y
    bx, by = math.cos(yaw) * dx + math.sin(yaw) * dy, -math.sin(yaw) * dx + math.cos(yaw) * dy
    grasp = solve_grip_ik(bx, by, GRASP_Z_M, -90)
    pitch = tool_pose(grasp).pitch_deg
    hover = solve_grip_ik(bx, by, HOVER_Z_M, pitch)
    path = [solve_grip_ik(bx, by, float(z), pitch) for z in np.linspace(HOVER_Z_M, GRASP_Z_M, 8)[1:]]
    return hover, path


def run_world(host, seen, item, *, log):
    """Identical teacher/drive timeline in both worlds; returns per-time measurements (eval only)."""
    world = host.world
    t = host.settle(T_START)
    box_z = lambda: float(world.data.body(host.objects[item]['body_name']).xpos[2])  # noqa: E731
    placed = place_box(host, 'r1', item)
    arm = ArmSequence(CommandPort(host, 'r1'), {int(k): int(v) for k, v in world.robot('r1').servo_command_pulses.items()})
    hover, path = grasp_targets(host, 'r1', item)
    arm.queue({**hover, 1: OPEN}, t)
    for pose in path:
        arm.queue(pose, t, duration=.12, settle=0.)
    arm.queue({1: CLOSED}, t, duration=.5, settle=.4)
    lifted = False
    samples, next_drive = [], T_GRASP_CHECK - .2
    while t < T_END - 1e-9:
        now = float(world.data.time)
        host.hidden_tick(now)
        done = arm.tick(now)
        if done and not lifted:
            arm.queue({**hover, 1: CLOSED}, now, duration=.8, settle=.6)
            lifted = True
        if now + 1e-9 >= next_drive:
            host._apply('r2', DRIVE, now)
            next_drive += DRIVE_EVERY_S
        t = round(t + CONTROL_S, 6)
        host._physics_until(t)
        r2 = world.robot('r2').base_xyz()
        samples.append({'t': round(float(world.data.time), 4), 'box_z': round(box_z(), 4),
                        'holders': zhe.finger_holders(world.data, host._box_geom[item], host._fingers),
                        'r2_xy': [round(float(r2[0]), 5), round(float(r2[1]), 5)]})
    log(f'{len(samples)} samples, last {samples[-1]}')
    return {'placed_box_xy': placed, 'samples': samples,
            'commands': {rid: copy.deepcopy(s.commands) for rid, s in host.robots.items()},
            'captures': seen, 'servo_command_pulses': {rid: dict(world.robot(rid).servo_command_pulses)
                                                       for rid in runner.ROBOTS}}


def at(samples, t):
    return min(samples, key=lambda s: abs(s['t'] - t))


def canonical(xml, *, drop_hidden):
    root = ET.fromstring(xml)
    for body in list(root.find('worldbody')):
        if drop_hidden and body.get('name', '').startswith(zhe.HIDDEN_BODY_PREFIX):
            root.find('worldbody').remove(body)
    return ET.canonicalize(ET.tostring(root, encoding='unicode'))


def verdict(control, fault, scene_same, event_log):
    c, f = control['samples'], fault['samples']
    grasped = {name: at(r['samples'], T_GRASP_CHECK) for name, r in (('control', control), ('fault', fault))}
    held_ok = all(s['box_z'] > .045 and s['holders'] == ['r1'] for s in grasped.values())
    end_c, end_f = at(c, T_END), at(f, T_END)
    hold_end = T_EVENT + T_HOLD_S
    d = lambda rows, a, b: math.dist(at(rows, a)['r2_xy'], at(rows, b)['r2_xy'])  # noqa: E731
    checks = {
        'grasp_setup_held_in_both_worlds': held_ok,
        'fault_world_box_on_floor_at_end': end_f['box_z'] < .03 and not end_f['holders'],
        'control_world_box_still_held_at_end': end_c['box_z'] > .045 and end_c['holders'] == ['r1'],
        'r2_still_while_held': d(f, T_EVENT + .3, hold_end) < .005,
        'r2_drives_in_control_meanwhile': d(c, T_EVENT + .3, hold_end) > .02,
        'r2_drives_again_after_hold': d(f, hold_end + .1, T_END) > .005,
        'robot_command_rows_identical': control['commands'] == fault['commands'],
        'robot_visible_actuator_state_identical': control['captures'] == fault['captures'],
        'servo_command_pulses_identical': control['servo_command_pulses'] == fault['servo_command_pulses'],
        'scene_xml_identical_apart_from_hidden_obstacle': scene_same,
        'events_logged': [r['effect'] for r in event_log] == [
            'gripper_fault_open', 'wheels_held', 'obstacle_moved', 'gripper_fault_cleared', 'wheels_released'],
    }
    return {'checks': checks, 'pass': all(checks.values()), 'grasp_check': grasped,
            'end': {'control': end_c, 'fault': end_f},
            'r2_displacement_m': {'control_hold_window': round(d(c, T_EVENT + .3, hold_end), 5),
                                  'fault_hold_window': round(d(f, T_EVENT + .3, hold_end), 5),
                                  'fault_after_hold': round(d(f, hold_end + .1, T_END), 5)},
            'box_z_min_after_event': {'control': min(s['box_z'] for s in c if s['t'] >= T_EVENT),
                                      'fault': min(s['box_z'] for s in f if s['t'] >= T_EVENT)}}


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--output', required=True, help='new directory under the primary checkout outputs/')
    args = p.parse_args(argv)
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)                  # never overwrite a result
    started, load0 = time.time(), os.getloadavg()
    record = {'schema': 'ugrp.zone_hidden_events_probe.v1', 'diagnostic_only': True,
              'note_ko': '진단 전용. 연구 결과·모델 호출·로봇 판단이 아니다. 교사(정답)가 상자를 잡게 한 뒤 숨은 사건 물리만 확인한다.',
              'code': {'sha': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain', '--', 'sim', 'harness',
                                                                         'scripts'))},
              'env': {'python': platform.python_version(), 'platform': platform.platform(),
                      'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                                                                 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')}},
              'load_average': {'start': [round(v, 2) for v in load0]}, 'timeline': {
                  'start': T_START, 'grasp_check': T_GRASP_CHECK, 'event': T_EVENT, 'hold_s': T_HOLD_S, 'end': T_END,
                  'drive': DRIVE, 'drive_every_s': DRIVE_EVERY_S, 'gripper_fault_s': zhe.GRIPPER_FAULT_S},
              'failure': None}
    hosts = []
    lines = []
    log = lambda msg: (lines.append(msg), print(msg, file=sys.stderr, flush=True))  # noqa: E731
    try:
        import mujoco
        record['env']['mujoco'] = mujoco.__version__
        pre = runner.load_prereg(PREREG)
        episode = pre['episodes'][0]
        _, scenario, map_bundle, provider = runner.run_bundle(pre, episode)
        spec = runner.host_spec(scenario, episode, map_bundle)
        record['episode'] = {'episode_id': episode['episode_id'], 'map': spec['map'], 'seed': spec['seed'],
                             'contact_profile': spec['contact_profile']}
        control, seen_c = build('control', out, None, provider, spec, pre['student'])
        hosts.append(control)
        item = sorted(i for i, o in control.objects.items() if o['kind'] == 'cyan')[0]
        rows = events()
        rows[0]['target']['item_id'] = item
        fault, seen_f = build('fault', out, zr.HiddenEventSchedule({'eval': {'hidden_events': rows}}),
                              provider, spec, pre['student'])
        hosts.append(fault)
        record['item'] = item
        record['hidden_events'] = rows
        scene_same = canonical(fault.world.scene_xml, drop_hidden=True) == canonical(control.world.scene_xml,
                                                                                   drop_hidden=False)
        log(f'scene identical apart from hidden obstacle: {scene_same}')
        results = {}
        for name, host, seen in (('control', control, seen_c), ('fault', fault, seen_f)):
            t0 = time.time()
            results[name] = run_world(host, seen, item, log=log)
            results[name]['wall_s'] = round(time.time() - t0, 1)
            log(f'{name}: {results[name]["wall_s"]} s wall')
        event_log = list(fault.hidden_log)
        record['event_log'] = event_log
        record['fault_steps'] = dict(fault.hidden_physics.faults.fault_steps)
        record['obstacle_pos_m'] = [round(float(v), 4) for v in
                                    fault.world.data.body(zhe.HIDDEN_BODY_PREFIX + OBSTACLE['obstacle_id']).xpos]
        record['verdict'] = verdict(results['control'], results['fault'], scene_same, event_log)
        for name, r in results.items():
            (out / f'{name}_samples.json').write_text(json.dumps(r, indent=1) + '\n')
        runner.jsonl(out / 'eval_only' / 'hidden_events.jsonl', event_log)
        log(json.dumps(record['verdict']['checks']))
    except BaseException as exc:                              # noqa: BLE001 - recorded, then re-raised
        record['failure'] = {'type': type(exc).__name__, 'message': str(exc)[:2000],
                             'traceback': traceback.format_exc()[-6000:]}
        raise
    finally:
        for host in hosts:
            try:
                host.close()
            except Exception as exc:                          # noqa: BLE001
                lines.append(f'close failed: {exc!r}')
        record['load_average']['end'] = [round(v, 2) for v in os.getloadavg()]
        record['wall_s'] = round(time.time() - started, 1)
        record['log'] = lines
        (out / 'probe.json').write_text(json.dumps(record, indent=1, ensure_ascii=False, default=str) + '\n')
    return 0 if record.get('verdict', {}).get('pass') else 1


if __name__ == '__main__':
    sys.exit(main())
