"""Offline single-robot cargo teacher plan; does not construct or step a simulator.

One robot (r1) starts 0.6-1.1 m west of one cargo (box colour / can / tile) of a
v4 study scenario, facing it within +-25 deg. The cargo stays where the scenario
puts it. Kinds are mixed by a fixed per-kind quota; the held-out map scenario
(s4) is never used. Seeds come from configs/grasp_act_seed_splits.json
(solo_diagnostic / solo_gate). The frozen ``handoff_pose_error`` is the map
code's own-pose estimate error used to initialise the set-down look-around.
"""
import argparse, hashlib, json, math, random
from collections import Counter
from pathlib import Path
from harness.zone_final_environment import resolve
from harness.static_keepouts import keepout_rects, rect_distance, inside_rect
from harness.grasp_act_seed_splits import check_range
from sim.grasp_act_solo_teacher import cargo

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ('s1_normal_mixed_v4', 's2_unmapped_blockage_v4', 's3_late_rendezvous_v4', 's5_moved_dropped_item_v4',
             's6_novel_relation_v4', 's7_trio_rendezvous_v4', 's8_mixed_tiers_v4')   # not s4: held-out map
KINDS = ('cyan', 'red', 'green', 'yellow', 'can', 'tile')
GATE_QUOTA = {'cyan': 7, 'red': 5, 'green': 5, 'yellow': 3, 'can': 10, 'tile': 10}     # 40
DIAGNOSTIC_KINDS = ('cyan', 'can', 'tile')
BASE_Z = .032355118817659255
POSE_ERROR = (.05, math.radians(2.))
START_RANGE_M = (.6, 1.1)
FACING_JITTER = math.radians(25.)
FREE_ROBOT_M = .18


def line_of_sight(start, cargo_xy, rects, others, *, step=.02, clear_m=.05):
    """True when no map obstacle or other cargo stands on the start-to-cargo segment.

    The search is pan and in-place rotation only, so a start whose target is hidden
    behind a wall or another item could never see it. Scene-owner geometry, used only
    to draw the start state (never by the teacher).
    """
    n = max(2, int(math.dist(start, cargo_xy)/step))
    for i in range(n):
        p = (start[0]+(cargo_xy[0]-start[0])*i/n, start[1]+(cargo_xy[1]-start[1])*i/n)
        if any(inside_rect(p, rect) for rect in rects):
            return False
        if any(math.dist(p, q['pose_m'][:2]) < clear_m for q in others):
            return False
    return True


def candidates(kind):
    out = []
    for sid in SCENARIOS:
        path = ROOT/'configs/zone_study_scenarios_v4'/f'{sid}.json'
        scenario = json.loads(path.read_text())
        for placement in scenario['eval']['setup']['placements']:
            if placement['kind'] == kind:
                out.append((sid, path, scenario, placement))
    return out


def episode(i, kind, seed, split):
    rng = random.Random(seed)
    pool = candidates(kind)
    rejects = Counter()
    for attempt in range(400):
        sid, path, scenario, placement = pool[(i+attempt) % len(pool)]
        static, _, _ = resolve(scenario['map_id'])
        bounds, rects = static['bounds_m'], keepout_rects(static, perimeter=True)
        others = [p for p in scenario['eval']['setup']['placements'] if p['item_id'] != placement['item_id']]
        cx, cy = placement['pose_m'][:2]
        spec = cargo(kind)
        role = 'any' if kind == 'can' else 'west'
        station = spec.station_m or .2002

        def free(p, r=FREE_ROBOT_M):
            return (bounds[0]+r <= p[0] <= bounds[1]-r and bounds[2]+r <= p[1] <= bounds[3]-r
                    and all(rect_distance(p, rect) >= r for rect in rects))

        final = (cx-station, cy)
        if not free(final) or any(math.dist(final, q['pose_m'][:2]) < .25 for q in others):
            rejects['station_blocked'] += 1
            continue
        r = rng.uniform(*START_RANGE_M)
        phi = rng.uniform(-math.radians(55), math.radians(55))
        start = (cx-r*math.cos(phi), cy+r*math.sin(phi))
        if not free(start) or any(math.dist(start, q['pose_m'][:2]) < .35 for q in others):
            rejects['start_blocked'] += 1
            continue
        if not line_of_sight(start, (cx, cy), rects, others):
            rejects['target_hidden_from_start'] += 1
            continue
        yaw = math.atan2(cy-start[1], cx-start[0])+rng.uniform(-FACING_JITTER, FACING_JITTER)
        parking = []
        for _ in range(2):
            for _try in range(2000):
                p = (rng.uniform(bounds[0]+.2, bounds[1]-.2), rng.uniform(bounds[2]+.2, bounds[3]-.2))
                if free(p) and all(math.dist(p, q) > .7 for q in [start, final, (cx, cy), *parking]) \
                        and all(math.dist(p, q['pose_m'][:2]) > .35 for q in others):
                    parking.append(p)
                    break
        if len(parking) < 2:
            rejects['no_parking'] += 1
            continue
        err = [rng.gauss(0, POSE_ERROR[0]), rng.gauss(0, POSE_ERROR[0]), rng.gauss(0, POSE_ERROR[1])]
        return {'episode_id': f'{split}-{seed}', 'batch': f'solo-teacher-{split}-{seed}', 'seed': seed, 'split': split,
                'scenario_id': sid, 'scenario_source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'map_id': scenario['map_id'], 'kind': kind, 'item_id': placement['item_id'], 'role': role,
                'robot_id': 'r1', 'cargo_pose_m': [cx, cy, placement['pose_m'][2]],
                'spawns': {'r1': [*start, BASE_Z, yaw], 'r2': [*parking[0], BASE_Z, 0.], 'r3': [*parking[1], BASE_Z, 0.]},
                'handoff_pose_error': err, 'start_to_cargo_m': r, 'proposal_attempts': attempt+1,
                'rejects': dict(rejects)}
    raise ValueError(f'no admissible start for {kind} index {i}: {dict(rejects)}')


def prepare(*, split, fresh_diagnostics=False):
    if fresh_diagnostics and split != 'solo_diagnostic':
        raise ValueError('fresh diagnostics must stay outside the gate')
    if split == 'solo_diagnostic':
        kinds, seed0 = list(DIAGNOSTIC_KINDS)*(2 if fresh_diagnostics else 1), 76900
    elif split == 'solo_gate':
        left, kinds = dict(GATE_QUOTA), []
        while any(left.values()):                     # round robin: a stopped run keeps a mixed prefix
            for k in KINDS:
                if left[k]:
                    kinds.append(k)
                    left[k] -= 1
        seed0 = 78000
    check_range(split, seed0, len(kinds))
    per_kind = Counter()
    episodes = []
    for n, kind in enumerate(kinds):
        episodes.append(episode(per_kind[kind], kind, seed0+n, split))
        per_kind[kind] += 1
    return {'schema': 'ugrp.grasp_act.solo_plan.v1', 'episodes': episodes,
            'distribution': {'kinds': dict(Counter(kinds)), 'scenarios': list(SCENARIOS), 'excluded': 's4 (held-out map)',
                             'start': 'west of the cargo 0.6-1.1 m, facing within 25 deg',
                             'handoff_pose_error_sigma': {'xy_m': POSE_ERROR[0], 'yaw_rad': POSE_ERROR[1]},
                             'fixed': ['floor_light_v1', 'camera review v3 runtime binding', 'native v7', 'weld off']},
            'criteria': {'teacher_target_rate': .95, 'minimum_episodes': 40,
                         'success': 'lift (clearance >= 12 mm, tilt <= 10 deg, both fingers >= 0.5 N, 3 s) then set-down '
                                    '(5 mm, 2 s still, tilt <= 3 deg, open) and command-complete with the look-around '
                                    'done; per-kind n/N reported, no kind is qualified by fewer than its own samples'},
            'student_evaluation': False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--split', choices=('solo_diagnostic', 'solo_gate'), required=True)
    p.add_argument('--fresh-diagnostics', action='store_true', help='append cyan/can/tile seeds 76903-76905')
    a = p.parse_args()
    plan = prepare(split=a.split, fresh_diagnostics=a.fresh_diagnostics)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(plan, indent=2)+'\n')
    print(json.dumps({'episodes': len(plan['episodes']), 'kinds': plan['distribution']['kinds']}))


if __name__ == '__main__':
    main()
