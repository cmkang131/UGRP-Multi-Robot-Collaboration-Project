"""v7 roller collider approximation: profile, mesh-vs-sphere6 equivalence and speed.

Fixed commands only; no policy, no model calls, no ground-truth feedback. Reuses the
v7 step diagnostic (scripts.probe_masterpi_drive_friction) and the paired-beam probe.
Acceptance limits are declared in ACCEPT before any run and recorded in the README.
Run only through the managed workflow `masterpi-v7-roller-approx-probe`.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = Path('/Users/changmin/projects/ugrp/outputs')
BRANCH = 'claude/v7-roller-approx'
PROFILE = 'masterpi_drive_friction_v7'
VARIANTS = {'mesh': {'roller_collision': 'mesh'},
            'sphere6_v1': {'roller_collision': 'sphere6_v1'},
            'mesh_freeze': {'roller_collision': 'mesh', 'idle_robot_contacts': 'freeze_v1'},
            'sphere6_freeze': {'roller_collision': 'sphere6_v1', 'idle_robot_contacts': 'freeze_v1'}}
BASE = 'mesh'   # every other variant is compared with this one

# (tag, case, loaded, wheel_input, drive_s, long_lane): same set-ups as the recorded v7 steps.
EQUIVALENCE = (
    ('empty-f020', 'forward', False, 20, 5., True), ('empty-f030', 'forward', False, 30, 5., True),
    ('empty-f035', 'forward', False, 35, 5., True), ('empty-f050', 'forward', False, 50, 5., True),
    ('empty-f100', 'forward', False, 100, 5., True),
    ('cyan-f035', 'forward', True, 35, 5., True), ('cyan-f100', 'forward', True, 100, 5., True),
    ('empty-left035', 'left', False, 35, 1.5, False),
)
PROFILE_CASES = (('rest', 'rest', False, 35, 1.5, False), ('empty-f050', 'forward', False, 50, 1.5, False),
                 ('cyan-f050', 'forward', True, 50, 1.5, False))

# Declared before the runs. Never changed after seeing results.
ACCEPT = {
    'stationary_peak_com_xy_m': .001,      # 20/30: both variants stay within 1 mm (v7 gate)
    'sustained_tail_min_mps': .001,        # 35/50/100: both variants all-samples forward > 1 mm/s
    'forward_speed_rel': .05,              # |v_sphere6 / v_mesh - 1| of last-0.5 s mean forward speed
    'left_speed_rel': .05,                 # same for lateral speed of the left diagnostic
    'left_yaw_diff_deg': .5,               # |yaw_sphere6 - yaw_mesh| of total yaw change
    'beam_shift_rel': .10,                 # beam world-y shift relative to mesh
    'beam_yaw_diff_deg': .5,               # |beam yaw change difference|
    'beam_progress_difference_rel': .10,   # r1-r2 world-y progress difference relative to mesh
    'speed_gain_min': 1.2,                 # mesh/sphere6 physics-only wall per SIM, forward u50 repeats
}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def _rel(a, b):
    return abs(a/b-1.) if b else float('inf')


def _item(name, passed, detail):
    return {'check': name, 'passed': bool(passed), 'detail': detail}


def compare_forward(tag, wheel_input, mesh, s6):
    """Equivalence of one forward step pair; pure function of the two result dicts."""
    if mesh['status'] != 'MEASURED_DEV' or s6['status'] != 'MEASURED_DEV':
        return _item(tag, False, {'status': [mesh['status'], s6['status']]})
    if wheel_input <= 30:
        a, b = mesh['peak_command_com_xy_m'], s6['peak_command_com_xy_m']
        limit = ACCEPT['stationary_peak_com_xy_m']
        return _item(tag, a <= limit and b <= limit, {'rule': 'both stay <=1 mm',
                     'base_peak_com_xy_m': a, 'variant_peak_com_xy_m': b})
    vm, vs = mesh['steady_velocity'][0], s6['steady_velocity'][0]
    lm, ls = mesh['tail_forward_min_mps'], s6['tail_forward_min_mps']
    ok = (lm > ACCEPT['sustained_tail_min_mps'] and ls > ACCEPT['sustained_tail_min_mps']
          and _rel(vs, vm) <= ACCEPT['forward_speed_rel'])
    return _item(tag, ok, {'rule': 'both sustained and speed within 5%', 'base_mps': vm, 'variant_mps': vs,
                 'relative_difference': vs/vm-1. if vm else None, 'base_tail_min': lm, 'variant_tail_min': ls})


def compare_left(tag, mesh, s6):
    import math
    if mesh['status'] != 'MEASURED_DEV' or s6['status'] != 'MEASURED_DEV':
        return _item(tag, False, {'status': [mesh['status'], s6['status']]})
    ym, ys = math.degrees(mesh['yaw_change_rad']), math.degrees(s6['yaw_change_rad'])
    vm, vs = mesh['steady_velocity'][1], s6['steady_velocity'][1]
    moving = mesh['tail_lateral_min_mps'] > ACCEPT['sustained_tail_min_mps'] and s6['tail_lateral_min_mps'] > ACCEPT['sustained_tail_min_mps']
    ok = moving and abs(ys-ym) <= ACCEPT['left_yaw_diff_deg'] and _rel(vs, vm) <= ACCEPT['left_speed_rel']
    return _item(tag, ok, {'rule': 'both move left, yaw difference <=0.5 deg, lateral speed within 5%',
                 'base_yaw_deg': ym, 'variant_yaw_deg': ys, 'yaw_difference_deg': ys-ym,
                 'base_lateral_mps': vm, 'variant_lateral_mps': vs, 'relative_difference': vs/vm-1. if vm else None})


def compare_beam(mesh, s6):
    if mesh['status'] != 'MEASURED_DEV' or s6['status'] != 'MEASURED_DEV':
        return _item('pair-beam', False, {'status': [mesh['status'], s6['status']],
                     'stop_reason': [mesh.get('stop_reason'), s6.get('stop_reason')]})
    fm, fs = mesh['final'], s6['final']
    ym, ys = fm['beam_delta_m'][1], fs['beam_delta_m'][1]
    pm, ps = fm['progress_difference_m'], fs['progress_difference_m']
    yaw = fs['beam_yaw_change_deg']-fm['beam_yaw_change_deg']
    ok = (_rel(ys, ym) <= ACCEPT['beam_shift_rel'] and abs(yaw) <= ACCEPT['beam_yaw_diff_deg']
          and _rel(ps, pm) <= ACCEPT['beam_progress_difference_rel'])
    return _item('pair-beam', ok, {'rule': 'no physical failure; beam y shift within 10%, yaw within 0.5 deg, '
                 'r1-r2 progress difference within 10%',
                 'base_beam_y_m': ym, 'variant_beam_y_m': ys, 'beam_y_relative_difference': ys/ym-1. if ym else None,
                 'base_beam_yaw_deg': fm['beam_yaw_change_deg'], 'variant_beam_yaw_deg': fs['beam_yaw_change_deg'],
                 'yaw_difference_deg': yaw, 'base_progress_difference_m': pm, 'variant_progress_difference_m': ps,
                 'progress_difference_relative': ps/pm-1. if pm else None})


def physics_only_wall_per_sim(result):
    step = result.get('profile', {}).get('step_total_s')
    return step/result['sim_s'] if step and result.get('sim_s') else None


def speed_summary(runs):
    """runs: variant -> list of result dicts of the same case (profile timers on)."""
    out = {'variants': {}}
    for variant, results in runs.items():
        phys = [physics_only_wall_per_sim(r) for r in results]
        diag = [r['wall_per_sim'] for r in results]
        out['variants'][variant] = {'physics_only_wall_per_sim': phys, 'diagnostic_wall_per_sim': diag,
                                    'physics_only_mean': sum(phys)/len(phys), 'diagnostic_mean': sum(diag)/len(diag)}
    if BASE in out['variants']:
        base = out['variants'][BASE]
        for variant, row in out['variants'].items():
            row['gain_physics_only'] = base['physics_only_mean']/row['physics_only_mean']
            row['gain_diagnostic'] = base['diagnostic_mean']/row['diagnostic_mean']
    if 'sphere6_v1' in out['variants']:
        out['gain_required'] = ACCEPT['speed_gain_min']
        out['gain_physics_only'] = out['variants']['sphere6_v1']['gain_physics_only']
        out['passed'] = bool(out['gain_physics_only'] >= ACCEPT['speed_gain_min'])
    return out


def run_render_probe(variant, output, frames=40):
    """Per-frame cost of the production robot camera JPEG path (render share estimate)."""
    import numpy as np
    from sim.masterpi_drive_friction_v7 import build_world
    from sim.zone_final_v3_scene import FinalV3Scene
    from harness.zone_pair_highpose import HIGH
    output.mkdir()
    scene = FinalV3Scene.from_spec({'map': 'zone_wide_two_doors_final_v3', 'seed': 1601,
        'goal': {'B': {'cyan': 1}}, 'extra_boxes': {}, 'team_cargo': []}, 'local_contact_fine')
    scene.config['setup_only']['spawns']['r1'] = [3., -1., .0325, 0.]
    world = build_world(scene, drive_profile=PROFILE, seed=1601, render=True, warehouse_layout=scene.engine_layout,
                        use_calibration_manifest=False, **VARIANTS[variant])
    try:
        scene.setup(world)
        c = world.robot('r1')
        c.set_servo_pulses({**HIGH, 1: 2000}, forward_only=True)
        for _ in range(round(.2/float(world.model.opt.timestep))):
            world._physics_step_for(c, np.zeros(4))
        times = {}
        for camera in ('robot_cam',):
            ms = []
            for i in range(frames+5):
                t = time.perf_counter()
                jpeg = world.render_jpeg(robot_id='r1', camera=camera)
                ms.append(1e3*(time.perf_counter()-t))
            times[camera] = {'ms_per_frame_mean': float(np.mean(ms[5:])), 'ms_per_frame_min': float(min(ms[5:])),
                             'jpeg_bytes': len(jpeg), 'frames': frames, 'warmup_frames_dropped': 5}
        result = {'variant': variant, 'status': 'MEASURED_DEV', 'render': times,
                  'size': [world.width, world.height] if hasattr(world, 'width') else None}
    finally:
        world.close()
    write(output/'result.json', result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--phase', choices=('profile', 'equivalence', 'speed', 'render'), required=True)
    p.add_argument('--variants', nargs='+', choices=tuple(VARIANTS), default=['mesh', 'sphere6_v1'])
    p.add_argument('--repeats', type=int, default=3, help='speed phase: runs per variant (ABBA-style alternation)')
    p.add_argument('--expected-minutes', type=float, default=6.)
    args = p.parse_args()
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to(RAW_ROOT):
        p.error('raw output must be absolute below primary outputs/')
    if args.phase == 'equivalence' and BASE not in args.variants:
        p.error(f'--variants must include {BASE}')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if source != args.expected_source_sha or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        p.error('expected clean committed source required')
    if os.environ.get('UGRP_SIM_MANAGED_CHILD') != '1':
        p.error('use sim_cli workflow run masterpi-v7-roller-approx-probe')
    from scripts import agent_lock
    if agent_lock.status(agent_lock.DEFAULT_ROOT) is not None:
        p.error('physics lock occupied; no simulation started')
    lock = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='claude', branch=BRANCH,
        purpose=f'v7 roller approximation {args.phase}', pid=os.getpid(),
        expected_minutes=args.expected_minutes, timing_sensitive=True)
    try:
        args.output.mkdir(parents=True, exist_ok=False)
        write(args.output/'manifest.json', {'source_sha': source, 'python': platform.python_version(),
            'phase': args.phase, 'accept': ACCEPT, 'command': vars(args) | {'output': str(args.output)},
            'lock': lock, 'loadavg_start': os.getloadavg(), 'model_calls': 0})
        from scripts.probe_masterpi_drive_friction import run_case
        rows, order = [], list(args.variants)
        if args.phase == 'render':
            for variant in order:
                result = run_render_probe(variant, args.output/f'{variant}-render')
                rows.append(result)
                print(json.dumps({'variant': variant, 'render': result['render']}), flush=True)
        elif args.phase in ('profile', 'equivalence'):
            cases = PROFILE_CASES if args.phase == 'profile' else EQUIVALENCE
            for index, (tag, case, loaded, level, drive_s, lane) in enumerate(cases):
                for variant in (order if index % 2 == 0 else order[::-1]):
                    folder = args.output/variant
                    folder.mkdir(exist_ok=True)
                    result = run_case(PROFILE, case, loaded, folder/tag, level, drive_s, False, lane, False,
                                      world_options=VARIANTS[variant], profile_timers=True)
                    result.update(variant=variant, tag=tag)
                    rows.append(result)
                    write(args.output/'results.json', rows)
                    print(json.dumps({k: result.get(k) for k in ('variant', 'tag', 'status', 'wall_per_sim', 'steady_velocity')}), flush=True)
            if args.phase == 'equivalence':
                from scripts.probe_drive_pair_beam import run_pair_case
                for variant in order[::-1]:
                    folder = args.output/variant
                    folder.mkdir(exist_ok=True)
                    result = run_pair_case(PROFILE, folder/'pair-beam', world_options=VARIANTS[variant])
                    result.update(variant=variant, tag='pair-beam')
                    rows.append(result)
                    write(args.output/'results.json', rows)
                    print(json.dumps({k: result.get(k) for k in ('variant', 'status', 'stop_reason', 'wall_per_sim', 'final')}), flush=True)
        else:
            runs = {v: [] for v in order}
            sequence = [v for k in range(args.repeats) for v in (order if k % 2 == 0 else order[::-1])]
            for k, variant in enumerate(sequence):
                folder = args.output/variant
                folder.mkdir(exist_ok=True)
                result = run_case(PROFILE, 'forward', False, folder/f'empty-f050-r{k}', 50, 5., False, True, False,
                                  world_options=VARIANTS[variant], profile_timers=True)
                result.update(variant=variant, tag=f'empty-f050-r{k}')
                rows.append(result)
                write(args.output/'results.json', rows)
                runs[variant].append(result)
                print(json.dumps({k2: result.get(k2) for k2 in ('variant', 'tag', 'status', 'wall_per_sim')}), flush=True)
            write(args.output/'speed-summary.json', speed_summary(runs))
        write(args.output/'results.json', rows)
        if args.phase == 'equivalence':
            by = {(r['variant'], r['tag']): r for r in rows}
            report = {'accept': ACCEPT, 'base': BASE, 'variants': {}}
            for variant in order:
                if variant == BASE:
                    continue
                checks = []
                for tag, case, loaded, level, drive_s, lane in EQUIVALENCE:
                    a, b = by[(BASE, tag)], by[(variant, tag)]
                    checks.append(compare_left(tag, a, b) if case == 'left' else compare_forward(tag, level, a, b))
                checks.append(compare_beam(by[(BASE, 'pair-beam')], by[(variant, 'pair-beam')]))
                report['variants'][variant] = {'checks': checks, 'all_passed': all(c['passed'] for c in checks)}
            write(args.output/'equivalence.json', report)
            print(json.dumps({v: {'all_passed': r['all_passed'], 'failed': [c['check'] for c in r['checks'] if not c['passed']]}
                              for v, r in report['variants'].items()}), flush=True)
    finally:
        held = agent_lock.status(agent_lock.DEFAULT_ROOT)
        if held and held['pid'] == os.getpid() and held['branch'] == BRANCH:
            agent_lock.release(agent_lock.DEFAULT_ROOT, owner='claude')


if __name__ == '__main__':
    main()
