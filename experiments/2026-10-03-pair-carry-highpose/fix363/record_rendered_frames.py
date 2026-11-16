"""REVIEW_363 round 2: rendered own-RGB frames for a NON-circular relation test.

Same physics, scene, reviewer commands and three conditions as
headless_grip_monitor.py (nominal, partner_delay_2s, raise_grip_loss), but the
world is built with the renderer ON and every 0.5 SIM s each carrier's own
wrist frame is captured through the normal CameraRobotPort.capture (pinhole
render remapped to the measured fisheye, floor_light_v1). No controller runs.

Ground truth is used ONLY to label each frame on the evaluation side
(eval_label: bar height/tilt, own/partner gripper command, phase window).
The labels never enter harness code; tests use them only as expected answers.
"""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE))
import headless_grip_monitor as hg  # noqa: E402
from scripts.run_final_environment_checks import write, check_source  # noqa: E402
from harness import zone_final_pair_contract as c  # noqa: E402

STEP_S = .5
CONDITIONS = [('nominal', 0., False), ('partner_delay_2s', 2., False), ('raise_grip_loss', 0., True)]


def rendered(p):
    class Rendered(p.Headless):
        def __init__(self, bundle, out, *, seed):
            from sim.zone_final_v3_scene import build_world
            from sim.camera_robot_port import CameraRobotPort
            self.out, self.bundle = Path(out), bundle
            self.world, self.ports, self.streams = None, {}, {}
            self.frame, self.deadline, self.commands = 0, None, {}
            self.pose_sample_index, self._last_guard_xy = 0, {}
            self.scene = p.make_scene(bundle, seed)
            try:
                self.world = build_world(self.scene, bundle['contact_profile'], seed=seed,
                    width=640, height=480, render=True,
                    warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
                self.dt = float(self.world.model.opt.timestep)
                for rid in ('r1', 'r2', 'r3'):
                    self.ports[rid] = CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
            except Exception:
                self.close()
                raise
    return Rendered


def window(t, shift):
    for name, (a, b) in hg.WINDOWS.items():
        if a+shift-1e-8 <= t < b+shift-1e-8:
            return name
    return 'floor' if t < 10. else 'other'


def main(out_root, sha, seed=911, only=None):
    check_source(sha)
    p = hg.probe()
    Backend = rendered(p)
    out_root.mkdir(parents=True, exist_ok=False)
    index = []
    for name, delay, slip in [row for row in CONDITIONS if only is None or row[0] in only]:
        out = out_root/name
        (out/'frames').mkdir(parents=True)
        events = copy.deepcopy(p.commands())
        if delay:
            for row in events:
                if row['robot_id'] == 'r2' and 10 < row['t'] < 49:
                    row['t'] = round(row['t']+delay, 8)
        if slip:
            events = [e for e in events if not (e['robot_id'] == 'r2' and e['t'] >= 12. and e['action'].get('servo_id') == 1)]
            events.append({'t': 12., 'robot_id': 'r2', 'action': {'kind': 'arm', 'servo_id': 1, 'pulse': 2000}})
        events.sort(key=lambda row: row['t'])
        write(out/'commands.json', events)
        bundle = c.bundle('zone_wide_two_doors_final_v3', 'calibration-loaded')
        backend = Backend(bundle, out/'raw', seed=seed)
        rows = []
        try:
            backend.reset(5.)
            start = backend.now
            backend.set_deadline(start+52.)
            m, d = backend.world.model, backend.world.data
            j = 0
            for i in range(1041):
                t = round(i*.05, 8)
                backend.eval_sample()
                if i % int(STEP_S/.05) == 0 and t >= 3.5-1e-8:
                    gid = m.geom('cargo_beam__bar').id
                    axis = d.geom_xmat[gid].reshape(3, 3)[:, 0]
                    for rid in hg.CARRIERS:
                        obs = backend.ports[rid].capture()
                        jpeg = base64.b64decode(obs['image'])
                        path = out/'frames'/f'{rid}_{t:05.1f}.jpg'
                        path.write_bytes(jpeg)
                        own = hg.issued_servo(events, rid, t, False)
                        partner = hg.issued_servo(events, 'r2' if rid == 'r1' else 'r1', t, False)
                        rows.append({'condition': name, 'rid': rid, 't': t, 'file': str(path.relative_to(out_root)),
                            'sha256': obs['sha256'], 'issued_servo': own,
                            'actuator_state_servo': obs['actuator_state']['servo_pulses'],
                            'eval_label': {'window': window(t, delay if rid == 'r2' else 0.),
                                'bar_z_m': float(d.geom_xpos[gid][2]),
                                'bar_tilt_deg': float(np.degrees(np.arcsin(abs(axis[2])))),
                                'own_gripper_cmd': own.get(1), 'partner_gripper_cmd': partner.get(1)}})
                if i == 1040:
                    break
                while j < len(events) and events[j]['t'] <= t+1e-8:
                    backend.issue(events[j]['robot_id'], events[j]['action'])
                    j += 1
                backend.advance_to(start+(i+1)*.05)
        finally:
            backend.close()
        write(out/'frames.json', rows)
        index += rows
        print(json.dumps({'condition': name, 'frames': len(rows)}), flush=True)
    write(out_root/'index.json', {'source_sha': sha, 'driver_sha256': c.base.sha(Path(__file__)),
        'step_s': STEP_S, 'seed': seed, 'render': True, 'controller': None, 'model_calls': 0, 'weld': False,
        'loadavg_end': list(os.getloadavg()), 'frames': index})


if __name__ == '__main__':
    out_root, sha = Path(sys.argv[1]), sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 911
    only = set(sys.argv[4].split(',')) if len(sys.argv) > 4 else None
    primary = Path('/Users/changmin/projects/ugrp/outputs')
    if not out_root.is_absolute() or not out_root.resolve().is_relative_to(primary):
        raise SystemExit('raw output must be absolute under primary outputs')
    if shutil.disk_usage(primary).free < 10*1024**3:
        raise SystemExit('HOST_ERROR: ENOSPC (<10 GiB free)')
    main(out_root, sha, seed, only)
