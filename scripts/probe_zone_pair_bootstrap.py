#!/usr/bin/env python3
"""Short start-pose bootstrap probe (no full E2E): stationary look -> arm-raise guard.

Builds the v6 pair dev scene (dock map, one long beam, three robots), makes the
two participants request the same first own-camera ``look_around`` the dev
actor requests, and stops as soon as each participant either

- passes: its look sweep reaches the pan stage (the arm-raise transition to
  the look posture was issued under the unchanged SweepGuard), or
- fails: the job ends (``STATIONARY_BOOTSTRAP_NO_FIX``,
  ``SWEEP_TRANSITION_BLOCKED``, ...), or
- the SIM limit (default 25 s) elapses.

Control inputs are the robots' own RGB, own commands and the static map.
No GT reaches control. This script reads GT (``_truth``) only after the loop
for its ``eval_*`` columns; the inherited host still logs GT during the run
into its in-memory ``eval_only`` evaluation record (never a control input).
No model calls, weld OFF, no pair_carry submission, no retries. This is a
diagnostic, not a registered cohort: dock assignment and pose perturbations
are setup-only changes of the spawn, recorded per case.

Grid: ``--seeds`` x ``--docks`` x ``--perturb`` (each case a fresh world).
``--docks seeded`` keeps the seeded robot-to-row assignment; ``rot1``/``rot2``
rotate it; perturbations are ``dx,dy,dyaw`` (m, m, rad) applied to r1 and r2.

usage (one-case smoke):
  python3 scripts/probe_zone_pair_bootstrap.py --output <abs outputs dir> \
      --seeds 911 --docks seeded --perturb 0,0,0 --policy b-boot
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = 'ugrp.zone_pair_bootstrap_probe.v1'
PARTICIPANTS = ('r1', 'r2')
BEAM_XYYAW = [1.0, 0.05, 0.0]          # v6 prereg seeds 911/912 setup (static)
SHEET = {'beam_xyyaw': [1.0, 0.0, 0.0], 'grid': {'xy_m': .1, 'yaw_rad': .174533},
         'source': 'coarse order sheet (setup pose rounded to the sheet grid; static, fixed before the run)'}


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--output', type=Path, required=True, help='new directory (absolute, primary outputs/)')
    p.add_argument('--seeds', type=int, nargs='+', default=[911])
    p.add_argument('--docks', nargs='+', default=['seeded'], choices=('seeded', 'rot1', 'rot2'))
    p.add_argument('--perturb', nargs='+', default=['0,0,0'], help='dx,dy,dyaw applied to r1 and r2 spawns')
    p.add_argument('--policy', default='b-boot', choices=('v5h', 'b-only', 'a+b', 'b-boot', 'a+b-boot'))
    p.add_argument('--max-sim-s', type=float, default=25.)
    p.add_argument('--keep-frames', action='store_true', help='also keep own JPEGs (default keeps them too)')
    return p


def parse_perturb(text):
    vals = [float(v) for v in text.split(',')]
    if len(vals) != 3 or not all(map(math.isfinite, vals)) or abs(vals[0]) > .15 or abs(vals[1]) > .15 \
            or abs(vals[2]) > .35:
        raise ValueError('perturbation must be dx,dy,dyaw within 0.15 m / 0.35 rad')
    return vals


def cases(args):
    for seed in args.seeds:
        for dock in args.docks:
            for pert in args.perturb:
                yield {'seed': seed, 'docks': dock, 'perturb': parse_perturb(pert), 'policy': args.policy}


def spawn_setup(scene, dock, perturb):
    """Setup-only: rotate the seeded row assignment and perturb r1/r2 (never read by control)."""
    spawns = scene.config['setup_only']['spawns']
    order = ('r1', 'r2', 'r3')
    rows = [spawns[r][1] for r in order]
    shift = {'seeded': 0, 'rot1': 1, 'rot2': 2}[dock]
    rows = rows[shift:] + rows[:shift]
    for rid, y in zip(order, rows):
        spawns[rid][1] = y
    for rid in PARTICIPANTS:
        spawns[rid][0] += perturb[0]
        spawns[rid][1] += perturb[1]
        spawns[rid][3] += perturb[2]
    return copy.deepcopy(spawns)


def run_case(case, out):
    from harness.owncam_bootstrap_v6b import bootstrap_state
    from harness.zone_own_team_host import OwnCamTeamHost
    from scripts.run_zone_pair_dev import CALIBRATION, ORDER
    from scripts.zone_pair_dev_runtime import make_scene

    spec = {'map': 'zone_wide_door_tags_v2_dock_v3', 'seed': case['seed'], 'goal': {'B': {'cyan': 1}},
            'pair_policy': case['policy'],
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': BEAM_XYYAW}],
            'pair_order_sheets': {'cargoX': SHEET}, 'order_sheet': copy.deepcopy(ORDER),
            'contact_profile': 'cargo_noslip_v1', 'job_sim_limit_s': 900.}
    student = {'mode': 'm1', 'calibration': str(CALIBRATION.relative_to(ROOT)),
               'skill_module': 'harness.wrist_zone_skill_v9', 'skill_class': 'WristZoneDeliveryV9'}
    scene = make_scene(spec)
    spawns = spawn_setup(scene, case['docks'], case['perturb'])
    status = {r: {'outcome': None} for r in PARTICIPANTS}

    class ProbeHost(OwnCamTeamHost):
        def _decide_raw(self, rid, now):
            if rid in PARTICIPANTS and not getattr(self, '_looked', {}).get(rid):
                self._looked = {**getattr(self, '_looked', {}), rid: True}
                self.call(rid, 'look_around')
            self._observe(rid, now)
            return super()._decide_raw(rid, now)

        def _observe(self, rid, now):
            if rid not in PARTICIPANTS or status[rid]['outcome'] is not None:
                return
            ex = self.robots[rid].executor
            job = ex.job
            if job is not None and job.kind == 'look_around' and (job.sweep or {}).get('stage') in ('pan', 'restore', 'done'):
                rep = ex.pose.report(now)
                status[rid].update(outcome='arm_raise_guard_pass', t=round(now, 3),
                                   std_xy_m=round(rep.std_xy_m, 4), std_yaw_rad=round(rep.std_yaw_rad, 4))
            elif job is None and self._looked.get(rid):
                last = next((e for e in reversed(ex.jobs_done)), None)
                rep = ex.pose.report(now)
                ok = last is not None and last.get('outcome') in ('LOOKED', 'LOOKED_POSE_UNCERTAIN')
                status[rid].update(outcome='arm_raise_guard_pass' if ok else 'fail', t=round(now, 3),
                                   job_outcome=None if last is None else last.get('outcome'),
                                   std_xy_m=round(rep.std_xy_m, 4) if rep.initialized else None,
                                   std_yaw_rad=round(rep.std_yaw_rad, 4) if rep.initialized else None)

        def done(self):
            return all(s['outcome'] is not None for s in status.values())

    frames = out / 'frames'
    host = ProbeHost.__new__(ProbeHost)
    started = time.monotonic()
    load0 = list(os.getloadavg())
    try:
        ProbeHost.__init__(host, spec, student, root=ROOT, study_layer=lambda *a: None, frames_dir=frames,
                           scene=scene)
        t0 = float(host.world.data.time)
        result = host.run(t0 + case['max_sim_s'], done=host.done)
        robots = {}
        for rid in PARTICIPANTS:
            ex = host.robots[rid].executor
            state = bootstrap_state(ex.pose)
            truth = host._truth(rid)                   # evaluation only, after the loop
            rep = ex.pose.report(float(host.world.data.time))
            robots[rid] = {**status[rid], 'time_to_result_s': None if status[rid].get('t') is None
                           else round(status[rid]['t'] - t0, 3),
                           'bootstrap': state, 'provider_source': ex.pose.source,
                           'jobs_done': ex.jobs_done,
                           'commands': [c for c in host.robots[rid].commands if c['kind'] != 'hold'][:80],
                           'eval_only': {'truth_xyyaw_end': [round(v, 4) for v in truth],
                                         'spawn_setup': spawns[rid],
                                         'err_xy_m_end': None if not rep.initialized else
                                         round(math.hypot(rep.x_m - truth[0], rep.y_m - truth[1]), 4)}}
        return {'termination': result['outcome'], 'sim_start_s': t0, 'sim_end_s': result['sim_s'],
                'robots': robots, 'wall_s': round(time.monotonic() - started, 1),
                'loadavg_start_end': [load0, list(os.getloadavg())]}
    finally:
        if hasattr(host, 'world'):
            host.close()


def main(argv=None):
    args = parser().parse_args(argv)
    out = args.output
    if not out.is_absolute() or out.exists():
        raise SystemExit('--output must be a new absolute directory')
    out.mkdir(parents=True)
    rows = []
    for i, case in enumerate(cases(args)):
        case = {**case, 'max_sim_s': args.max_sim_s}
        d = out / f"case{i:03d}-s{case['seed']}-{case['docks']}"
        d.mkdir()
        try:
            record = {'schema': SCHEMA, 'case': case, **run_case(case, d)}
        except Exception as exc:                 # noqa: BLE001 - a host error is a recorded case result
            record = {'schema': SCHEMA, 'case': case, 'host_error': {'type': type(exc).__name__,
                                                                      'message': str(exc)[:500]}}
        (d / 'result.json').write_text(json.dumps(record, indent=1, default=str))
        summary = {'case': case, **{rid: {k: (record.get('robots', {}).get(rid) or {}).get(k)
                                          for k in ('outcome', 'time_to_result_s', 'std_xy_m', 'job_outcome')}
                                    for rid in PARTICIPANTS}, 'host_error': record.get('host_error')}
        rows.append(summary)
        print(json.dumps(summary), flush=True)
    (out / 'summary.json').write_text(json.dumps({'schema': SCHEMA, 'argv': argv or sys.argv[1:], 'cases': rows},
                                                 indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
