#!/usr/bin/env python3
"""Finite Linux-only DEV plausibility probes; GT is setup/evaluation only.

Reuses fixed drive commands and the recorded high_held teacher schedule.
No model calls, rendering, policy feedback, weld, or E2E success claim.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))

CASES = ('forward', 'turn', 'grasp_hold', 'pair_lift_hold')
LIMITS = dict(max_penetration_m=.010, max_robot_tilt_deg=20.,
              min_forward_m=.005, max_forward_m=.8, max_lateral_m=.15,
              min_turn_deg=1., max_turn_deg=150., max_grip_slip_m=.030,
              max_static_drift_m=.020)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


class ProbeAbort(RuntimeError):
    pass


class PhysicsAudit:
    """Read-only numeric checks at 50 Hz, after the original stepping path."""
    def __init__(self, world):
        import mujoco
        self.world = world
        self.last_t = -1.
        self.rows = []
        m, d = world.model, world.data
        self.options = dict(timestep_s=float(m.opt.timestep),
                            integrator=mujoco.mjtIntegrator(int(m.opt.integrator)).name,
                            iterations=int(m.opt.iterations))
        self.active_welds = [i for i in range(m.neq)
                            if m.eq_type[i] == mujoco.mjtEq.mjEQ_WELD and d.eq_active[i]]
        if self.active_welds:
            raise ProbeAbort('ACTIVE_WELD')

    def sample(self):
        import numpy as np
        m, d = self.world.model, self.world.data
        if float(d.time)-self.last_t < .02-1e-9:
            return
        self.last_t = float(d.time)
        finite = bool(np.isfinite(d.qpos).all() and np.isfinite(d.qvel).all())
        if not finite:
            raise ProbeAbort('NONFINITE_STATE')
        penetration = max((max(0., -float(d.contact[i].dist)) for i in range(d.ncon)), default=0.)
        tilt = {r: math.degrees(math.acos(float(np.clip(d.body(r+'__robot').xmat[8], -1, 1))))
                for r in self.world.controllers}
        row = dict(t=float(d.time), max_penetration_m=penetration,
                   max_robot_tilt_deg=max(tilt.values()),
                   max_abs_qvel=float(np.max(np.abs(d.qvel))), finite=finite)
        self.rows.append(row)
        if penetration > LIMITS['max_penetration_m']:
            raise ProbeAbort('EXCESS_CONTACT_PENETRATION')
        if row['max_robot_tilt_deg'] > LIMITS['max_robot_tilt_deg']:
            raise ProbeAbort('ROBOT_TILT')

    def record(self):
        return dict(options=self.options, active_welds=self.active_welds,
                    samples=len(self.rows),
                    max_penetration_m=max((r['max_penetration_m'] for r in self.rows), default=None),
                    max_robot_tilt_deg=max((r['max_robot_tilt_deg'] for r in self.rows), default=None),
                    max_abs_qvel=max((r['max_abs_qvel'] for r in self.rows), default=None))


def e2e_scene(scene, profile):
    """Same camera, near clip and stiffness transforms as e2e_ownmap_live."""
    from sim.render_profile import install
    from sim.final_pair_highpose_nearclip import wrap
    from sim import masterpi_camera_review_v3 as camera
    from sim.s2_servo_stiffness import transform_xml
    scene = wrap(install(scene, 'floor_light_v1'))
    original = scene.robot_transform

    def transform(xml, **kwargs):
        xml = camera.transform_xml(original(xml, **kwargs), profile_id=camera.PROFILE_ID)
        for rid in ('r1', 'r2', 'r3'):
            xml = transform_xml(xml, servo_stiffness='real_v1', robot_id=rid)
        if profile != 'off':
            from sim.e2e_speed3_profile import transform_xml as physics_xml
            xml = physics_xml(xml, profile)
        return xml

    scene.robot_transform = transform
    return scene


@contextmanager
def configured_worlds(profile, audits):
    """Scoped factory adapter lets both unchanged diagnostic runners be reused."""
    from sim import masterpi_drive_friction_v7 as drive
    original = drive.build_world

    def build(scene, **kwargs):
        from sim.e2e_speed3_profile import apply_world
        world = original(e2e_scene(scene, profile), **kwargs)
        if profile != 'off':
            apply_world(world, profile)
        audit = PhysicsAudit(world)
        audits.append(audit)
        step = world._physics_step_for

        def checked_step(*args, **kw):
            value = step(*args, **kw)
            audit.sample()
            return value

        world._physics_step_for = checked_step
        return world

    drive.build_world = build
    try:
        yield
    finally:
        drive.build_world = original


def acceptance(case, result, audit):
    measured = lambda key: audit[key] if audit.get(key) is not None else math.inf
    checks = dict(completed=result.get('status') == 'MEASURED_DEV',
                  no_active_weld=not audit.get('active_welds', [True]),
                  numeric_samples=audit.get('samples', 0) > 0,
                  penetration=measured('max_penetration_m') <= LIMITS['max_penetration_m'],
                  tilt=measured('max_robot_tilt_deg') <= LIMITS['max_robot_tilt_deg'],
                  no_mujoco_warning=not result.get('warnings'))
    if case == 'forward':
        delta = result.get('displacement_m', [0., 0., 0.])
        checks.update(forward=LIMITS['min_forward_m'] <= delta[0] <= LIMITS['max_forward_m'],
                      lateral=abs(delta[1]) <= LIMITS['max_lateral_m'])
    elif case == 'turn':
        degrees = math.degrees(result.get('yaw_change_rad', 0.))
        checks['turn'] = LIMITS['min_turn_deg'] <= degrees <= LIMITS['max_turn_deg']
    elif case == 'grasp_hold':
        checks.update(cargo_held=result.get('cargo_min_z_m', 0.) >= .08,
                      static_drift=math.hypot(*result.get('displacement_m', [1., 1.])[:2]) <= LIMITS['max_static_drift_m'])
    elif case == 'pair_lift_hold':
        row = result.get('last_sample') or {}
        plan = result.get('design', {})
        checks.update(lifted=row.get('beam_min_z_m', 0.) > plan.get('lift_clear_m', math.inf),
                      grip_contacts=bool(row.get('finger_n')) and
                      all(min(v) >= plan.get('finger_min_n', math.inf) for v in row.get('finger_n', {}).values()),
                      grip_slip=bool(result.get('max_grip_slip_m')) and
                      max(result.get('max_grip_slip_m', {'none': math.inf}).values()) <= LIMITS['max_grip_slip_m'])
    return dict(passed=all(checks.values()), checks=checks,
                scope='bounded staged plausibility only; not robot policy, delivery, E2E or hardware success')


def run_one(profile, case, output):
    from scripts.probe_masterpi_drive_friction import run_case, HYSTERESIS_PROFILE
    from scripts import probe_drive_pair_beam as pair
    audits = []
    result = {}
    contact_phase = profile == 'adaptive_v1' and case in ('grasp_hold', 'pair_lift_hold')
    # This diagnostic already knows its fixture phase. Actual E2E switching
    # must be tested separately using own issued arm commands, never truth.
    effective_profile = 'off' if contact_phase else profile
    try:
        with configured_worlds(effective_profile, audits):
            if case == 'pair_lift_hold':
                original = pair.design

                def stationary_design():
                    plan = original()
                    plan['command'] = {r: [0., 0., 0., 0.] for r in pair.ROBOTS}
                    plan['qualification'] = 'fixed teacher grasp and lift followed by stationary 1.5 s hold'
                    return plan

                pair.design = stationary_design
                try:
                    result = pair.run_pair_case(HYSTERESIS_PROFILE, output)
                finally:
                    pair.design = original
            else:
                result = run_case(HYSTERESIS_PROFILE, 'rest' if case == 'grasp_hold' else case,
                                  case == 'grasp_hold', output, wheel_input=50,
                                  drive_s=1.5, long_lane=True)
    except Exception as exc:
        if (output/'result.json').exists():
            result = json.loads((output/'result.json').read_text())
        result.update(status='PHYSICS_FAILURE' if isinstance(exc, ProbeAbort) else 'HOST_ERROR',
                      error=dict(type=type(exc).__name__, message=str(exc)))
    output.mkdir(exist_ok=True)
    audit = audits[-1].record() if audits else {}
    if audits:
        write(output/'physics-audit.json', audits[-1].rows)
    result.update(case=case, speed3_profile=profile, physics_audit=audit,
                  camera='masterpi_camera_review_v3', servo_stiffness='real_v1',
                  controller_feedback=False, model_calls=0, renders=0)
    if profile == 'adaptive_v1':
        result['adaptive_probe_scope'] = dict(
            phase_source='known diagnostic fixture, not runtime state',
            contact_resolution_preselected=contact_phase,
            effective_profile=effective_profile,
            runtime_command_switch_verified=False,
            qualification='drive/contact component plausibility; dynamic transition not exercised')
    result['acceptance'] = acceptance(case, result, audit)
    write(output/'result.json', result)
    return result


def compress_and_hash(output):
    """Verify decompressed bytes before replacing this finished probe's JSON."""
    from scripts.compress_json_traces import decompressed_hash
    compressed = []
    for path in sorted(output.rglob('*.json')):
        if path.stat().st_size <= 65536 or path.name == 'RUN_META.json':
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        dest = path.with_suffix(path.suffix+'.zst')
        subprocess.run(['zstd', '-q', '-3', '-T1', '-o', str(dest), '--', str(path)], check=True)
        if decompressed_hash(dest) != digest:
            raise RuntimeError('zstd roundtrip hash mismatch: '+str(path))
        compressed.append(dict(path=str(path.relative_to(output)), sha256=digest,
                               compressed_path=str(dest.relative_to(output)), verified=True))
        write(output/'COMPRESSED.json', compressed)
        path.unlink()
    files = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS.json'}
    write(output/'SHA256SUMS.json', files)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--profiles', nargs='+', choices=('off', 'dt1_v1', 'dt2_v1', 'adaptive_v1'), default=['dt1_v1', 'dt2_v1'])
    p.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    p.add_argument('--pr', type=int)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args(argv)
    if not a.execute:
        p.error('--execute is required for this physical diagnostic')
    if platform.system() != 'Linux':
        p.error('Linux execution host required; no Mac simulation')
    output = a.output.expanduser().resolve()
    if not output.is_relative_to(Path.home()/'ugrp-sim/runs'):
        p.error('raw output must be under ~/ugrp-sim/runs on persistent disk')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if source != a.expected_source_sha:
        p.error('expected-source-sha mismatch')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT).strip():
        p.error('tracked source must be committed before physics')
    subprocess.run(['zstd', '--version'], check=True, stdout=subprocess.DEVNULL)
    output.mkdir(parents=True, exist_ok=False)
    write(output/'RUN_META.json', dict(**{'class': 'dev'}, pr=a.pr,
          branch=subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
          sha=source, batch='e2e-speed3-physics-probe'))
    summary = dict(schema='ugrp.e2e_speed3_physics_probe.v1', source_sha=source,
                   qualification='staged DEV physics only; independent of speed benchmark and E2E cohort',
                   raw_path=str(output), profiles=a.profiles, cases=a.cases,
                   limits=LIMITS, model_calls=0, renders=0, results=[], status='RUNNING',
                   started_at=time.time(), loadavg_start=os.getloadavg())
    write(output/'summary.json', summary)
    try:
        for profile in a.profiles:
            for case in a.cases:
                result = run_one(profile, case, output/(profile+'-'+case))
                row = {k: result.get(k) for k in ('case', 'speed3_profile', 'status', 'acceptance',
                       'physics_audit', 'displacement_m', 'yaw_change_rad', 'cargo_min_z_m',
                       'max_grip_slip_m', 'last_sample', 'error', 'stop_reason', 'wall_per_sim',
                       'adaptive_probe_scope')}
                row['raw_path'] = str(output/(profile+'-'+case))
                summary['results'].append(row)
                summary.update(n=sum(r['acceptance']['passed'] for r in summary['results']),
                               N=len(a.profiles)*len(a.cases), completed=len(summary['results']))
                write(output/'summary.json', summary)
                print(json.dumps(row, ensure_ascii=False), flush=True)
        summary['status'] = 'PASS' if summary['n'] == summary['N'] else 'NOT_READY'
    finally:
        summary.update(finished_at=time.time(), loadavg_end=os.getloadavg())
        if summary['status'] == 'RUNNING':
            summary['status'] = 'HOST_ERROR'
        write(output/'summary.json', summary)
        (output/'EXIT').write_text('0\n' if summary['status'] == 'PASS' else '1\n')
        compress_and_hash(output)
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
