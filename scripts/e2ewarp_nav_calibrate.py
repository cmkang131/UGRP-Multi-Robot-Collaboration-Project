#!/usr/bin/env python3
"""Eval-only own-command odometry calibration for the two-robot nav gate.

Issues a fixed open-loop pulse sequence (forward, then turn in place) on the
navigation-gate scene and measures the base displacement from the simulator
state. The simulator state is an *evaluation sink*: it is never read by a
controller and only produces the two constants injected into
``OwnCommandOdometry``.

Output: ``nav-calibration.json`` (schema ``ugrp.e2ewarp.nav_calibration.v1``,
``measured: true``) plus the raw qpos trace and per-step samples. A run without
a finite, positive, cross-robot-consistent measurement exits non-zero and does
not write a calibration artifact.

Linux gcp6 only; --execute is required. No LLM, no relay, no controller.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = 'ugrp-act-l4-gcp6'
PCT = 35.0            # percent amplitude of the calibrated finite-pulse vocabulary
PULSE_S = 0.10        # pulse width used by the navigation controller
SETTLE_TICKS = 5      # let the wheel state settle before measuring
MAX_REL_SPREAD = 0.20  # refuse calibration when the two robots disagree by >20%


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=False) + '\n')


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def head():
    return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()


def stack_values():
    stack = json.loads((ROOT / 'configs/current_stack.json').read_text())
    return {r['id']: r['current'] for r in stack['rules'] if 'e2e_llm' in r['flows']}


def yaw_deg(qpos7):
    w, x, y, z = (float(v) for v in qpos7[3:7])
    return math.degrees(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


def wrap_deg(value):
    return (value + 180.0) % 360.0 - 180.0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seed', type=int, default=601)
    p.add_argument('--forward-pulses', type=int, default=40)
    p.add_argument('--turn-pulses', type=int, default=20)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--host-receipt', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args(argv)
    if not a.execute:
        raise SystemExit('calibration is a physical run: pass --execute')
    if a.forward_pulses < 10 or a.turn_pulses < 5:
        raise SystemExit('need >=10 forward and >=5 turn pulses for a usable measurement')
    if platform.system() != 'Linux' or platform.node().split('.')[0] != INSTANCE:
        raise SystemExit('Linux gcp6 only; no CPU fallback')
    if head() != a.expected_source_sha:
        raise SystemExit('FROZEN_SOURCE_SHA_REQUIRED')
    if subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip():
        raise SystemExit('FROZEN_SOURCE_DIRTY')
    if not Path('/home/ugrp/ugrp-sim/leases/e2ewarp.json').is_file():
        raise SystemExit('OWN_LEASE_REQUIRED')
    if not a.output.resolve().is_relative_to(Path('/home/ugrp/ugrp-sim/runs')):
        raise SystemExit('PERSISTENT_GCP6_RUN_ROOT_REQUIRED')
    if a.output.exists():
        raise SystemExit('output must not exist; never overwrite raw')
    forbidden = [k for k in os.environ if any(s in k.upper() for s in
                                              ('OPENROUTER_API', 'OPENAI_API', 'KAGGLE_KEY',
                                               'GOOGLE_APPLICATION_CREDENTIALS'))]
    if forbidden:
        raise SystemExit('VM_CREDENTIAL_ENV_FORBIDDEN:' + ','.join(forbidden))
    proof = json.loads(a.host_receipt.read_text())
    expected = dict(instance=INSTANCE, project_id='ugrp-sim-f-1016',
                    account='kcm5781kcm5781@gmail.com', idle_minutes=20,
                    budget_stop=True, wall_cap=None, credentials_on_vm=False)
    if any(proof.get(k) != v for k, v in expected.items()):
        raise SystemExit('LIVE_HOST_GUARD_RECEIPT_REQUIRED')

    from harness.active_camera import SEARCH
    from scripts.e2e_warp_physics import build_context, issue, transport
    stack = stack_values()
    out = a.output.resolve()
    started = time.monotonic()
    status, error = 'HOST_ERROR', None
    samples, trace = [], []
    try:
        context = build_context(a.seed, out / 'world-00', stack, nav_scene=True)
        geometry = json.loads((out / 'world-00' / 'eval-geometry.json').read_text())
        robots = sorted(geometry['robot_qpos_adr'])
        adr = {r: int(v) for r, v in geometry['robot_qpos_adr'].items()}
        hooks = transport([context], out, head(), stack)
        hooks.initialize([context])
        pwm = {str(k): int(v) for k, v in SEARCH.items()}
        world = context['world']
        trace.append(world.data.qpos.copy())

        def pose(robot):
            q = world.data.qpos[adr[robot]:adr[robot] + 7]
            return dict(x=float(q[0]), y=float(q[1]), yaw_deg=yaw_deg(q))

        def run_phase(name, wheels, pulses):
            nonlocal samples
            start = {r: pose(r) for r in robots}
            for pulse in range(pulses):
                now = float(world.data.time)
                for robot in robots:
                    issue(context, robot, dict(t=now, wheels=list(wheels),
                                               duration_s=[PULSE_S] * 4, pwm=pwm))
                hooks.step([context], np.ones(1, dtype=bool))
                for robot in robots:
                    samples.append(dict(phase=name, pulse=pulse, sim_s=float(world.data.time),
                                        robot=robot, **pose(robot)))
            end = {r: pose(r) for r in robots}
            return start, end

        # settle: hold wheels for a few ticks without pulses
        for _ in range(SETTLE_TICKS):
            for robot in robots:
                issue(context, robot, dict(t=float(world.data.time), wheels=[0.] * 4,
                                           duration_s=[0.] * 4, pwm=pwm))
            hooks.step([context], np.ones(1, dtype=bool))
        forward_start, forward_end = run_phase('forward', [PCT] * 4, a.forward_pulses)
        turn_start, turn_end = run_phase('turn', [-PCT, PCT, -PCT, PCT], a.turn_pulses)
        for _ in range(SETTLE_TICKS):
            for robot in robots:
                issue(context, robot, dict(t=float(world.data.time), wheels=[0.] * 4,
                                           duration_s=[0.] * 4, pwm=pwm))
            hooks.step([context], np.ones(1, dtype=bool))
        trace.append(world.data.qpos.copy())
        measured = {}
        for robot in robots:
            distance = math.dist((forward_start[robot]['x'], forward_start[robot]['y']),
                                 (forward_end[robot]['x'], forward_end[robot]['y']))
            turn = abs(wrap_deg(turn_end[robot]['yaw_deg'] - turn_start[robot]['yaw_deg']))
            measured[robot] = dict(
                distance_m=distance, turn_deg=turn,
                forward_pulses=a.forward_pulses, turn_pulses=a.turn_pulses,
                forward_m_per_pct_s=distance / (PCT * PULSE_S * a.forward_pulses),
                yaw_deg_per_pct_s=turn / (PCT * PULSE_S * a.turn_pulses))
        forwards = [v['forward_m_per_pct_s'] for v in measured.values()]
        yaws = [v['yaw_deg_per_pct_s'] for v in measured.values()]
        for name, values in (('forward', forwards), ('yaw', yaws)):
            mean = sum(values) / len(values)
            if not math.isfinite(mean) or mean <= 0.0:
                raise ValueError('CALIBRATION_NONPOSITIVE:' + name)
            spread = (max(values) - min(values)) / mean
            if spread > MAX_REL_SPREAD:
                raise ValueError(f'CALIBRATION_INCONSISTENT:{name}:spread={spread:.3f}')
        constants = dict(forward_m_per_pct_s=sum(forwards) / len(forwards),
                         yaw_deg_per_pct_s=sum(yaws) / len(yaws))
        value = dict(schema='ugrp.e2ewarp.nav_calibration.v1', measured=True,
                     measured_n=a.forward_pulses + a.turn_pulses,
                     source_sha=head(), seed=a.seed, scene='s7_pair_with_solo_v7',
                     robots=robots, pulse=dict(percent=PCT, width_s=PULSE_S),
                     per_robot=measured, constants=constants,
                     spread=dict(forward=(max(forwards) - min(forwards)) / constants['forward_m_per_pct_s'],
                                 yaw=(max(yaws) - min(yaws)) / constants['yaw_deg_per_pct_s']),
                     sim_s=float(world.data.time), wall_s=time.monotonic() - started,
                     host=proof, host_receipt_sha256=sha(a.host_receipt),
                     scene_geometry_sha256=sha(out / 'world-00' / 'eval-geometry.json'),
                     eval_only=True, note='measured from simulator base state; never a controller input')
        status = 'CALIBRATED'
        write(out / 'nav-calibration.json', value)
        write(out / 'calibration-samples.json', samples)
        np.savez_compressed(out / 'calibration-trace.npz',
                            qpos=np.asarray(trace), forward_pulses=a.forward_pulses,
                            turn_pulses=a.turn_pulses)
        print(json.dumps(dict(status=status, constants=constants,
                              measured_n=value['measured_n'], sim_s=value['sim_s'])))
    except BaseException as exc:
        import traceback
        error = traceback.format_exc()
        status = 'SUPERVISOR_STOP' if isinstance(exc, KeyboardInterrupt) else 'HOST_ERROR'
    finally:
        if status != 'CALIBRATED':
            out.mkdir(parents=True, exist_ok=True)
            write(out / 'calibration-result.json', dict(schema='ugrp.e2ewarp.nav_calibration.v1',
                  status=status, error=error, source_sha=head(), eval_only=True))
    return 0 if status == 'CALIBRATED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
