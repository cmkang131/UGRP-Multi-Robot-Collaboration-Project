"""Offline issued-PWM gravity estimate from saved scene XML; no simulator calls.

Assumes a level base, commanded angles reached, vertical load at the pad centre.
Equal load sharing is an assumption, not a measured contact-force distribution.
Inertia, horizontal contact forces, servo tracking error and friction are omitted.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
DEST = Path(__file__).with_name('crate6-torque.json')


def read(path):
    source = path if path.exists() else Path(str(path)+'.zst')
    raw = source.read_bytes()
    decoded = raw if source == path else subprocess.check_output(['zstd', '-dc', str(source)])
    return decoded, {'path': str(source), 'sha256': hashlib.sha256(raw).hexdigest()}


def estimate(xml, rid, pwm):
    bodies = {b.get('name'): b for b in xml.iter('body')}
    def joint(body, angle):
        lo, hi = map(float, body.find('joint').get('range').split())
        return max(lo, min(hi, angle))
    p = {int(k): v for k, v in pwm.items()}
    shoulder = joint(bodies[rid+'__shoulder_link'], math.radians(90-(p[5]-89-1500)*.09))
    elbow = joint(bodies[rid+'__elbow_link'], math.radians(-(p[4]-53-1500)*.09))
    wrist = joint(bodies[rid+'__wrist_link'], math.radians((p[3]-54-1500)*.09))
    terms = []
    def rotate(x, z, angle):
        return x*math.cos(angle)-z*math.sin(angle), x*math.sin(angle)+z*math.cos(angle)
    def walk(body, origin, angle):
        inertial = body.find('inertial')
        if inertial is not None:
            x, _, z = map(float, inertial.get('pos').split())
            lever = origin[0]+rotate(x, z, angle)[0]
            mass = float(inertial.get('mass'))
            terms.append({'body': body.get('name'), 'mass_kg': mass,
                          'lever_m': lever, 'torque_nm': mass*9.81*lever})
        for child in body.findall('body'):
            assert child.get('quat') is None and child.get('euler') is None
            x, _, z = map(float, child.get('pos', '0 0 0').split())
            dx, dz = rotate(x, z, angle)
            walk(child, (origin[0]+dx, origin[1]+dz),
                 angle+(wrist if child.get('name') == rid+'__wrist_link' else 0))
    walk(bodies[rid+'__elbow_link'], (0, 0), shoulder+elbow)
    site = next(s for s in xml.iter('site') if s.get('name') == rid+'__grip_site')
    pad_x, _, pad_z = map(float, site.get('pos').split())
    forearm = float(bodies[rid+'__wrist_link'].get('pos').split()[0])
    lever = forearm*math.cos(shoulder+elbow)+rotate(pad_x, pad_z, shoulder+elbow+wrist)[0]
    actuator = next(a for a in xml.find('actuator') if a.get('name') == rid+'__servo_elbow')
    limit = float(actuator.get('forcerange').split()[1])
    own = sum(t['torque_nm'] for t in terms)
    payload = .30/2*9.81*lever
    return {'elbow_to_pad_horizontal_m': lever, 'arm_gravity_nm': own,
            'payload_030kg_equal_share_nm': payload, 'total_equal_share_nm': own+payload,
            'limit_nm': limit, 'margin_nm': limit-abs(own+payload),
            'max_supported_crate_mass_share': (limit-own)/(.30*9.81*lever),
            'terms': terms}


def scan_pad_window(xml, rid='r2', z_tolerance_m=.001, z_bounds=None):
    """Exhaust all integer shoulder/elbow PWM pairs, with analytic wrist pruning.

    This deliberately RELAXES the existing pick schedule: lift pitch can be
    chosen independently, with +/-1 mm height error and no descent/collision
    constraint. Optional z_bounds widens the search to all lifted pad heights.
    Failure here also excludes the narrower fixed-pitch schedule.
    For a fixed shoulder/elbow pair, radius and height increase with pitch in
    [-90,-40] deg, as does torque (dT/dpitch = -B*sin(pitch)+C*cos(pitch)>0).
    Therefore its steepest feasible integer wrist PWM is the torque minimum;
    no feasible wrist command with a better margin is omitted.
    """
    import numpy as np
    from sim.grasp_act_release_teacher import PAD_WINDOW_M
    from sim.masterpi_geometry_v3 import PHYSICAL_V3

    # Bind the closed-form coefficients to the actual saved inertial model.
    expected = {'elbow_link': (.04, (.031, 0., 0.)),
                'wrist_link': (.025, (.035, 0., 0.)),
                'gripper': (.01, (.065, 0., .006)),
                'left_jaw': (.005, (.08185, 0., -.018)),
                'right_jaw': (.005, (.08185, 0., -.018))}
    bodies = {b.get('name'): b for b in xml.iter('body')}
    for suffix, (mass, com) in expected.items():
        inertial = bodies[rid+'__'+suffix].find('inertial')
        assert float(inertial.get('mass')) == mass
        assert tuple(map(float, inertial.get('pos').split())) == com
    assert tuple(map(float, bodies[rid+'__elbow_link'].get('pos').split())) == (.065, 0., 0.)
    assert tuple(map(float, bodies[rid+'__wrist_link'].get('pos').split())) == (.062, 0., 0.)
    site = next(s for s in xml.iter('site') if s.get('name') == rid+'__grip_site')
    assert tuple(map(float, site.get('pos').split())) == (.08685, 0., 0.)
    limit = estimate(xml, rid, {3: 775, 4: 1958, 5: 2139})['limit_nm']
    threshold = .9*limit
    lo, hi = PAD_WINDOW_M
    zlo, zhi = z_bounds if z_bounds is not None else (.095-z_tolerance_m, .095+z_tolerance_m)
    p4 = np.arange(500, 2501)
    elbow = np.deg2rad(-(p4-1553)*.09)
    best = None
    pair_count = feasible = qualified = 0
    max_mass = 0.
    for p5 in range(500, 2501):
        shoulder = math.radians(90-(p5-1589)*.09)
        if not -.15 <= shoulder <= 2.8:
            continue
        forearm = shoulder+elbow
        xb = .065*math.cos(shoulder)+.062*np.cos(forearm)
        zb = PHYSICAL_V3.shoulder_axis_z_floor_m+.065*math.sin(shoulder)+.062*np.sin(forearm)
        needcos, needsin = (lo-xb)/.08685, (zlo-zb)/.08685
        lower = np.maximum.reduce([np.full(len(p4), -math.pi/2),
            -np.arccos(np.clip(needcos, -1, 1)), np.arcsin(np.clip(needsin, -1, 1))])
        p3 = np.maximum(500, np.ceil(1554+np.rad2deg(lower-forearm)/.09-1e-9)).astype(int)
        wrist = np.deg2rad((p3-1554)*.09)
        pitch = forearm+wrist
        radius = xb+.08685*np.cos(pitch)
        z = zb+.08685*np.sin(pitch)
        mask = ((needcos <= 1) & (needsin <= 1) & (p3 <= 2500) & (np.abs(wrist) <= 1.8)
                & (np.abs(elbow) <= 1.8) & (pitch >= -math.pi/2-1e-9)
                & (pitch <= math.radians(-39.865))  # include IK rounding above -40
                & (radius >= lo-1e-9) & (radius <= hi+1e-9)
                & (z >= zlo-1e-9) & (z <= zhi+1e-9))
        own = 9.81*(.00403*np.cos(forearm)+.0023435*np.cos(pitch)+.00012*np.sin(pitch))
        lever = .062*np.cos(forearm)+.08685*np.cos(pitch)
        torque = own+.15*9.81*lever
        pair_count += len(p4)
        feasible += int(mask.sum())
        qualified += int((mask & (torque <= threshold)).sum())
        if not mask.any():
            continue
        max_mass = max(max_mass, float(np.max(2*(threshold-own[mask])/(9.81*lever[mask]))))
        j = int(np.argmin(np.where(mask, torque, np.inf)))
        if best is None or torque[j] < best['total_equal_share_nm']:
            pwm = {3: int(p3[j]), 4: int(p4[j]), 5: p5, 6: 1500}
            detail = estimate(xml, rid, pwm)
            assert abs(detail['total_equal_share_nm']-torque[j]) < 1e-12
            best = {'issued_pwm': pwm, 'arm_axis_radius_m': float(radius[j]),
                    'z_m': float(z[j]), 'pitch_deg': float(np.rad2deg(pitch[j])), **detail}
    return {'scope': scan_pad_window.__doc__, 'pad_window_m': list(PAD_WINDOW_M),
            'z_bounds_m': [zlo, zhi],
            'integer_pwm_range': [500, 2500], 'shoulder_elbow_pairs_checked': pair_count,
            'feasible_pair_minima': feasible, 'at_least_10pct_margin_pair_minima': qualified,
            'required_margin_fraction': .10, 'threshold_nm': threshold,
            'best': best, 'best_margin_fraction': 1-best['total_equal_share_nm']/limit,
            'max_crate_mass_at_10pct_margin_kg': max_mass,
            'qualified': qualified > 0, 'same_height_pair_load_split': '0.15 kg per robot',
            'verdict': ('candidate exists' if qualified else
                '0.30 kg is infeasible WITH the required 10% margin in this pad/lift window; not a universal lifting impossibility')}


def main():
    out = {'scope': __doc__, 'physics_steps': 0, 'render_calls': 0,
           'replay_ready': False, 'reason': 'visible_measurements absent from saved crate evaluation ledger',
           'runs': []}
    for seed in (77208, 77212, 77921):
        for sha in ('b033e5f9', '6f312f74'):
            stage = 'diag' if sha == 'b033e5f9' or seed == 77921 else 'gate'
            folder = ROOT/f'crate-{stage}-{seed}-{sha}'/'raw'
            result, result_ref = read(folder/'result.json')
            evaluation, eval_ref = read(folder/'eval-only.jsonl')
            scene, scene_ref = read(folder/'scene.xml')
            ev = [json.loads(s) for s in evaluation.splitlines()]
            result = json.loads(result)
            row = {'seed': seed, 'sha': sha, 'raw': str(folder),
                   'sources': [result_ref, eval_ref, scene_ref],
                   'prefix_held': result['prefix_held'],
                   'outcomes': result['prefix']['outcomes'],
                   'saved_grasp_inputs': sum('visible_measurements' in e for e in ev if e['stage']=='grasp'),
                   'grasp_rows': sum(e['stage']=='grasp' for e in ev),
                   'observed_load': result['prefix']['servo_load_lift_window'], 'robots': {}}
            xml = ET.fromstring(scene)
            for rid in ('r1', 'r2'):
                data, ref = read(folder/f'teacher-{rid}.jsonl'); row['sources'].append(ref)
                labels = [json.loads(s) for s in data.splitlines()]
                poses = {}
                for label in labels:
                    phase = label['teacher_phase']
                    if label['skill'] == 'grasp' and phase in ('closed', 'complete') and phase not in poses:
                        pwm = label['applied_command']['pwm']
                        poses[phase] = {'t': label['t'], 'issued_pwm': pwm, **estimate(xml, rid, pwm)}
                row['robots'][rid] = poses
            out['runs'].append(row)
    out['pad_window_scan'] = scan_pad_window(xml)
    # For a level crate the lug grasp point starts at 24 mm, and the required
    # bottom clearance is 12 mm. Allow ANY higher pad target, not just 95 mm.
    out['all_lifted_heights_scan'] = scan_pad_window(xml, z_bounds=(.024+.012, 1.))
    out['success_counterexample'] = ('77921/6f312f74 held 3 s despite commanded-pose overload; '
        'issued PWM is not measured pose. This estimate cannot invalidate the observed success '
        'or determine actual load sharing/contact moment/servo tracking. It does show no 10% command-pose margin.')
    DEST.write_text(json.dumps(out, indent=2)+'\n')
    for r in out['runs']:
        print(r['seed'], r['sha'], {rid: {p: round(v['total_equal_share_nm'], 6)
              for p, v in poses.items()} for rid, poses in r['robots'].items()})
    print('pad window:', {k: v for k, v in out['pad_window_scan'].items() if k not in ('scope', 'best')})
    print('all lifted heights:', {k: v for k, v in out['all_lifted_heights_scan'].items() if k not in ('scope', 'best')})


if __name__ == '__main__':
    main()
