"""pairact P0: setup-only certified-stance check, run BEFORE the MJWarp gate (CPU, no physics).

beampair9 method (experiments/2026-10-16-beampair9/operations/static_census.py) applied to the
beamact5 wide-start cases: for every case and both beam ends, take the existing 91-pose
certified family (sim.grasp_act_search24.reachability_map, +/-15 deg x 13 distances), place the
real 185x160 mm chassis (sim.grasp_act_search18.body_clearance) and measure the gap to the
authored static obstacles and cargo rectangles, exactly the inputs of
scripts/warp_flow_admission.certify (root 05046e9d) as replicated in wide_start.build_admission.

Three thresholds are reported, none is tuned here:
  overlap   gap > 0 (overlap/touch = 0.0)  (beampair9 "all certified poses overlap the box")
  admission gap >= FRESH_MARGIN_M (5 mm)   (current placement_graspable_filter_v1; all 40 pass)
  floor     gap >= FRESH_MARGIN_M + K*0.002 = 11.07 mm  (runtime margin at the 2 mm sigma floor)
A case is "flagged" under a rule when either end has zero certified poses meeting it.
Which rule excludes worlds is decided in the pre-registration BEFORE this runs (see
WORLD37_STATIC_PREREG_DRAFT.json); this script only computes.

Usage (gcp6 or any host with the r13 teacher tree; CPU only, seconds):
  cd <teacher tree fe6858ec> && <python> static_stance_check.py \
     --cases /home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json \
     --scenario <adapter tree>/experiments/2026-10-15-beampair1/scenario-v7.json \
     --out /home/ugrp/ugrp-sim/runs/pairact-p0/static-stance-<UTC>.json
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

SIGMA_FLOOR_M = .002  # existing 2 mm observation floor (sim/grasp_act_search22.measurement_uncertainty)


def thresholds():
    from sim.grasp_act_search21 import FRESH_MARGIN_M
    from sim.grasp_act_search22 import K
    return {'overlap': 0., 'admission': FRESH_MARGIN_M, 'floor': FRESH_MARGIN_M + K * SIGMA_FLOOR_M}


def end_census(beam_pose, end, offset, family, rects, clearance, limits):
    """Pure: per-end certified-pose gaps. ``rects`` = [(name, (x, y, hx, hy, yaw))]."""
    d = -offset if end == 'teal' else offset
    x, y = beam_pose[0] + d * math.cos(beam_pose[2]), beam_pose[1] + d * math.sin(beam_pose[2])
    poses = []
    for angle, distance, *_ in family:
        yaw = beam_pose[2] + (math.pi if end == 'blue' else 0.) + angle
        goal = (x - distance * math.cos(yaw), y - distance * math.sin(yaw), yaw)
        gaps = [(name, clearance(goal, [], [rect])) for name, rect in rects]
        name, gap = min(gaps, key=lambda v: v[1]) if gaps else ('none', math.inf)
        poses.append({'offset_deg': round(math.degrees(angle), 3), 'distance_m': distance,
                      'blocked_object': name, 'min_gap_m': gap})
    best = max(poses, key=lambda p: p['min_gap_m']) if poses else None
    # body_clearance returns 0.0 (not negative) for overlapping/touching rectangles, so the
    # overlap rule is strict: a pose is overlap-free only when gap > 0.
    free = {k: sum((p['min_gap_m'] > v) if k == 'overlap' else (p['min_gap_m'] >= v) for p in poses)
            for k, v in limits.items()}
    return {'N': len(poses), 'free_N': free,
            'best': best}


def case_census(beam_pose, rects, family, offset, clearance, limits):
    ends = {e: end_census(beam_pose, e, offset, family, rects, clearance, limits) for e in ('teal', 'blue')}
    flagged = {k: [e for e, v in ends.items() if v['free_N'][k] == 0] for k in limits}
    return {'ends': ends, 'flagged_ends': flagged}


def scene_rects(static, scenario):
    """Same rectangle list as wide_start.build_admission (static obstacles + cargo, beam excluded)."""
    from sim.zone_arena import BOX_HALF, COLORS
    from sim.zone_cargo import kind
    rects = [(o['id'], (*o['center_m'], *o['half_extents_m'], o.get('yaw_rad', 0.))) for o in static['obstacles']]
    for p in scenario['eval']['setup']['placements']:
        if p['item_id'] == 'beam_1':
            continue
        half = BOX_HALF[:2] if p['kind'] in COLORS else kind(p['kind']).landing_half_extents_m
        rects.append((p['item_id'], (*p['pose_m'][:2], *half, p['pose_m'][2])))
    return rects


def plan_of(case):
    plan = case.get('plan', case) if isinstance(case, dict) else None
    if not isinstance(plan, dict) or 'beam_pose' not in plan:
        raise ValueError('case without plan.beam_pose; cases schema differs [확인 필요]')
    return plan


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--scenario', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--indices', help='default: all cases')
    p.add_argument('--teacher-root', type=Path, default=Path.cwd(),
                   help='teacher source tree (r13: fe6858ec) providing sim/ and harness/')
    a = p.parse_args()
    import sys
    sys.path.insert(0, str(a.teacher_root.resolve()))
    if a.out.exists():
        raise SystemExit('new output path required')
    from harness.zone_final_environment import resolve
    from sim.grasp_act_search18 import body_clearance
    from sim.grasp_act_search24 import reachability_map
    from sim.zone_cargo import kind
    cases = json.loads(a.cases.read_text())
    if isinstance(cases, dict):
        cases = cases.get('cases') or cases.get('episodes')
    scenario = json.loads(a.scenario.read_text())
    beam = kind('long_beam')
    family = reachability_map(beam.grasps[0].grip_xyz[2])
    offset = abs(beam.grasps[0].grip_xyz[0])
    limits = thresholds()
    idx = range(len(cases)) if not a.indices else [int(i) for i in a.indices.split(',')]
    rows = []
    for i in idx:
        plan = plan_of(cases[i])
        static, _, _ = resolve(plan.get('map_id', scenario['map_id']))
        rects = scene_rects(static, scenario)
        r = case_census(plan['beam_pose'], rects, family, offset, body_clearance, limits)
        rows.append({'index': i, 'seed': plan.get('seed'), **r})
    report = {
        'schema': 'ugrp.pairact.p0.static_stance_check.v1', 'setup_only': True, 'physics': False,
        'cases': str(a.cases), 'cases_sha256': hashlib.sha256(a.cases.read_bytes()).hexdigest(),
        'scenario_sha256': hashlib.sha256(a.scenario.read_bytes()).hexdigest(),
        'family_N': len(family), 'offset_m': offset, 'thresholds_m': limits,
        'flagged': {k: [r['index'] for r in rows if r['flagged_ends'][k]] for k in limits},
        'rows': rows,
        'note': 'authored setup poses only; runtime cargo observation (r2 world 37 best 4.87 mm) can differ'}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps({'flagged': report['flagged'], 'thresholds_m': limits}))


if __name__ == '__main__':
    main()
