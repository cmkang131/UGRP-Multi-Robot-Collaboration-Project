"""Local saved-ledger/static audit only: never create a world or render a frame."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

from harness.servo_camera_fk import axis_rotation
from harness.visual_arm_v3 import forward_grip, solve_grip_site_ik, tool_pose
from harness.zone_own_perception_v3 import _pixel_rays, _ray_box
from sim.grasp_act_solo_lookback import object_transform, plan_lookback, regions, transforms
from sim.grasp_act_solo_lookback_margin import MODE as MARGIN_MODE, plan_with_margin
from sim.grasp_act_solo_teacher import BOX_KINDS, cargo


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decoded(path):
    return subprocess.check_output(['zstd', '-dc', str(path)], text=True)


def held_overlap(kind, low, view, roi, *, shift=(0., 0., 0.), tilt_deg=0.):
    obj = object_transform(kind, low, view)
    _, camera = transforms(view)
    rays = _pixel_rays(640, 480) @ camera[:3, :3].T
    rotation = axis_rotation([0, 1, 0], np.deg2rad(tilt_deg)) @ obj[:3, :3]
    entry, exit_ = _ray_box(camera[:3, 3], rays, obj[:3, 3]+shift,
                            np.array(cargo(kind).dims_m)/2+.001, rotation)
    mask = (np.isfinite(entry) & (exit_ >= np.maximum(entry, 0.)) & (exit_ > 0.)).reshape(480, 640)
    return int((roi & mask).sum())


def audit(raw, gate_report):
    manifest = json.loads((raw/'manifest.json').read_text())
    names = ('result.json.zst', 'teacher-commands.jsonl.zst', 'eval-only.jsonl.zst', 'plan.json')
    for name in names:
        if sha(raw/name) != manifest[name]['sha256']:
            raise ValueError('raw manifest mismatch: '+name)
    report = json.loads(decoded(raw/'result.json.zst'))
    trace = [json.loads(s) for s in decoded(raw/'teacher-commands.jsonl.zst').splitlines()]
    evaluation = [json.loads(s) for s in decoded(raw/'eval-only.jsonl.zst').splitlines()]
    low = next(r['command']['pwm'] for r in trace if r['phase'] == 'close')
    first = next(r for r in trace if r['phase'] == 'lookback')
    complete = next(r for r in trace if r['rgb_confirmation'].get('after'))
    last = trace[-1]
    at = lambda t: min(evaluation, key=lambda r: abs(r['t']-t))
    a, b = at(first['t']), at(complete['t'])
    commanded = report['teacher']['lookback_commanded_backoff_m']
    observed = float(np.linalg.norm(np.array(b['base_xyz'])[:2]-np.array(a['base_xyz'])[:2]))
    view = complete['command']['pwm']
    obj = object_transform('tile', low, view)
    actual_radius = float(np.linalg.norm(np.array(b['cargo_xyz'])[:2]-np.array(b['base_xyz'])[:2]))
    predicted_radius = float(np.linalg.norm(obj[:2, 3]))
    site_radius = float(np.linalg.norm(np.array(evaluation[0]['cargo_xyz'])[:2]-np.array(b['base_xyz'])[:2]))
    sample = report['lift_lookback_v1']['last']
    gp = forward_grip({int(k): v for k, v in low.items()})
    # Sensitivity only: replace issued retreat by measured retreat magnitude,
    # retaining commanded orientation. Actual robot yaw/camera pose is absent
    # from this ledger; this is explicitly NOT an actual frame registration.
    tile_sensitivity = regions('tile', low, view, site=(gp[0]+observed, gp[1], 0.))[2]
    rows = []
    for kind in BOX_KINDS:
        for x in (.1962, .2002, .2042):
            for y in (-.004, 0., .004):
                lo = {1: 1500, **solve_grip_site_ik((x, y, .024), preferred_pitch_deg=-66,
                                                  calibrated_grasp_only=False)}
                hi = {1: 1500, **solve_grip_site_ik((x, y, .095), preferred_pitch_deg=tool_pose(lo).pitch_deg,
                                                  calibrated_grasp_only=False)}
                plan = plan_lookback(kind, lo, hi)
                gx, gy, _ = forward_grip(lo)
                nominal, _, normal = regions(kind, lo, plan['pwm'], site=(gx+plan['backoff_m'], gy, 0.))
                short, _, sensitivity = regions(kind, lo, plan['pwm'], site=(gx+plan['backoff_m']-(commanded-observed), gy, 0.))
                shifts = [(0., 0., 0.), (.005, 0., 0.), (-.005, 0., 0.),
                          (0., .005, 0.), (0., -.005, 0.), (0., 0., .001), (0., 0., -.001)]
                overlap = max(held_overlap(kind, lo, plan['pwm'], short, shift=s, tilt_deg=t)
                              for s in shifts for t in (-1., 0., 1.))
                margin = plan_with_margin(kind, lo, hi)
                margin_roi, _, margin_info = regions(kind, lo, margin['pwm'],
                    site=(gx+margin['backoff_m']-.045, gy, 0.))
                margin_overlap = max(held_overlap(kind, lo, margin['pwm'], margin_roi, shift=s, tilt_deg=t)
                                     for s in shifts for t in (-1., 0., 1.))
                rows.append({'kind': kind, 'aligned_xyz_m': [x, y, .024],
                             'backoff_m': plan['backoff_m'], 'nominal': normal,
                             'short_retreat_sensitivity': sensitivity,
                             'short_retreat_plus_shift_tilt_max_overlap_px': overlap,
                             'margin_backoff_m': margin['backoff_m'], 'margin_short_retreat_geometry': margin_info,
                             'margin_short_retreat_plus_shift_tilt_max_overlap_px': margin_overlap})
    gate = json.loads(gate_report.read_text())
    boxes = [r for r in gate['rows'] if r['kind'] in BOX_KINDS]
    return {'schema': 'solo7_saved_and_static_v1', 'source_sha': report['source_sha'],
            'scope': 'saved evaluator/issued-command ledger and static geometry only; no new execution',
            'historical_gate': {'all': f"{gate['n_success']}/{gate['N']}",
                                'boxes': f"{sum(r['ok'] for r in boxes)}/{len(boxes)}",
                                'box_subset_is_final_gate': False, 'per_kind': gate['per_kind'],
                                'raw_report': str(gate_report), 'sha256': sha(gate_report)},
            'failure_79505': {'raw': str(raw), 'sha256': {n: sha(raw/n) for n in names},
                'times_absolute_sim_s': {'retreat_start': first['t'], 'first_verdict': complete['t'], 'last_verdict': last['t']},
                'commanded_retreat_m': commanded, 'observed_base_retreat_m': observed,
                'retreat_shortfall_m': commanded-observed,
                'predicted_held_planar_radius_m': predicted_radius, 'evaluated_body_planar_radius_m': actual_radius,
                'radius_mismatch_m': actual_radius-predicted_radius, 'padding_m': .001,
                'evaluated_original_site_planar_radius_m': site_radius,
                'predicted_site_planar_radius_m': float(np.linalg.norm(sample['geometry']['site_from_issued_grip_m'][:2])),
                'last_verdict': sample['answer'], 'last_geometry': sample['geometry'], 'last_colour': sample['after'],
                'first_colour': complete['rgb_confirmation']['after'],
                'held_overlap_with_observed_retreat_magnitude_assumption': tile_sensitivity,
                'interpretation': 'Issued retreat overestimates actual retreat; nominal held body differs by more than 1 mm. Zero predicted overlap is not a measured occlusion guarantee.',
                'frame_review_this_task': 0,
                'prior_coordinator_review': gate['frames_viewed'],
                'frames_missing_locally': [s['path'] for s in report['lift_lookback_v1']['samples'].values()
                                           if not (raw/s['path']).exists()],
                'not_verified': ['actual camera pose, robot yaw and held-body rotation are absent from eval ledger',
                                 'new independent frame review (images not retrieved locally; remote access prohibited)']},
            'box_static_cases': rows,
            'box_static_totals': {'N': len(rows), 'nominal_qualified': sum(r['nominal']['qualified'] for r in rows),
                                 'nominal_overlap_max_px': max(r['nominal']['held_occlusion_pixels'] for r in rows),
                                 'short_retreat_overlap_max_px': max(r['short_retreat_sensitivity']['held_occlusion_pixels'] for r in rows),
                                 'shift_tilt_overlap_max_px': max(r['short_retreat_plus_shift_tilt_max_overlap_px'] for r in rows),
                                 'margin_shift_tilt_overlap_max_px': max(r['margin_short_retreat_plus_shift_tilt_max_overlap_px'] for r in rows)},
            'geometry_fix_toggle': {'name': MARGIN_MODE, 'default': 'off', 'new_queue': 'on',
                                    'change': '150 mm issued retreat; RGB judge unchanged'},
            'limitations': ['Static box clearance does not establish physical RGB accuracy, loaded pose or return accuracy.',
                            'Four box colours share catalogue geometry; colour verdicts require fresh diagnostics.',
                            '5 mm translations and +/-1 degree tilt are sensitivity cases, not proven uncertainty bounds.'],
            'new_physics_runs': 0, 'new_render_runs': 0, 'remote_connections': 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--gate-report', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = audit(a.raw, a.gate_report)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'historical_gate': result['historical_gate'], 'boxes': result['box_static_totals'],
                      'retreat_shortfall_mm': result['failure_79505']['retreat_shortfall_m']*1000}))


if __name__ == '__main__':
    main()
