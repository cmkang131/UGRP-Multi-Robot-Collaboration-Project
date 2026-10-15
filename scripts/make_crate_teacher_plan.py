"""Offline episode plan for the heavy-crate teacher (grasp, lift barrier, set-down).

Does not construct or step a simulator. Each episode starts with the crate beside the
destination zone B (map-code handoff within 0.8 m of the zone centre, as the beam release
plan) and two robots 0.5-2.0 m away in random bearings, so the chain approach -> align ->
grasp -> GO/ACK lift -> set-down is exercised in one run. Scenarios s2 and s8 (v4) are the
only ones with a heavy crate.

Lug assignment (who takes the west/east lug):
- ``nearest`` (default, the gate): the assignment with the smaller total straight-line
  distance from the two starts to the two lug stations. Two different lugs by
  construction; no robot crosses to the far side when avoidable. This is the demonstration
  supervisor's rule (GT positions are allowed for the demo assignment), not a student input.
- ``alternating``: r1 west/east alternating by index regardless of position (the beam plan's
  rule); includes crossing cases for training diversity. Not used by the gate.

``start_assigned_los_v1`` conditions the existing joint proposal distribution on
both assigned lugs having >=5/15 probes available during a static rotation scan.
Original admissible starts/rejection rates remain in the plan. This privilege
belongs solely to demonstration setup; runtime teachers do not receive it.
"""
from __future__ import annotations
import argparse, hashlib, json, math, random
from collections import Counter
from pathlib import Path
from harness.zone_final_environment import resolve
from harness.static_keepouts import keepout_rects, pose_clear, rect_distance
from harness.grasp_act_seed_splits import check_range
from scripts.make_grasp_act_plan import BASE_Z
from sim.cargo_teacher_profile import CRATE, station_xy

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_SETS = {'v4': ('s2_unmapped_blockage_v4', 's8_mixed_tiers_v4'),
                 'v5': ('s2_unmapped_blockage_v5', 's8_mixed_tiers_v5')}
SCENARIOS = SCENARIO_SETS['v4']      # default (old behaviour); v5 = PR #498 set without tri_frame
HANDOFF_MAX_M = .8
POSE_ERROR = (.05, math.radians(2.))
STRATA = ((-.30, -.02), (0., .10), (.10, .20), (.20, .30))
PEERS = ('other_end', 'approaching', 'near_own', 'absent')
FOOTPRINT = [(-.12, -.05), (.12, -.05), (.12, .05), (-.12, .05)]
CROSS_OFFSET_M = .08
LOUD = ('nearest', 'alternating', 'fixed_rgb_lugs_v1')


def assign(own, other, crate, p=CRATE):
    """Return (r1_end, r2_end) minimising total start-to-station distance (ties: r1 teal)."""
    st = {e: station_xy(p, e, *crate)[:2] for e in ('teal', 'blue')}
    d = lambda a, e: math.dist(a, st[e])
    straight = d(own, 'teal')+d(other, 'blue')
    crossed = d(own, 'blue')+d(other, 'teal')
    return ('teal', 'blue') if straight <= crossed else ('blue', 'teal')


def prepare(*, count=40, seed=77000, split='crate_gate', destination='B', assignment='nearest', indices=None,
            scenario_set='v4', start_assigned_los='off'):
    if assignment not in LOUD:
        raise ValueError(assignment)
    if start_assigned_los not in ('off', 'start_assigned_los_v1'):
        raise ValueError(start_assigned_los)
    checker = None
    if start_assigned_los != 'off':
        from scripts.audit_crate_start_los import CrateStartLOS, PITCHES, summarize
        checker = CrateStartLOS()
    check_range(split, seed, count)
    scenarios = SCENARIO_SETS[scenario_set]
    episodes = []
    rejects = Counter()
    original_starts = []
    accepted_starts = []
    for i in range(count):
        rng = random.Random(seed+i)
        scenario_id = scenarios[i % len(scenarios)]
        path = ROOT/f'configs/zone_study_scenarios_{scenario_set}'/f'{scenario_id}.json'
        scenario = json.loads(path.read_text())
        static, _, _ = resolve(scenario['map_id'])
        bounds = static['bounds_m']
        rects = keepout_rects(static, perimeter=True)
        zone = static['regions']['zone_'+destination]
        (cx, cy), (hx, hy) = zone['center_m'], zone['half_extents_m']
        others = [q for q in scenario['eval']['setup']['placements'] if q['item_id'] != CRATE.item_id]
        peer = PEERS[i % len(PEERS)]
        axis_y = (i//2) % 2 == 0                       # crate axis along the zone's long (y) side or across it (x)
        lo, hi = STRATA[(i//4) % len(STRATA)]
        side_sign = 1 if (i//8) % 2 == 0 else -1
        original_start = None
        los_proposals = 0

        def free(q, r):
            return (bounds[0]+r <= q[0] <= bounds[1]-r and bounds[2]+r <= q[1] <= bounds[3]-r
                    and all(rect_distance(q, rect) >= r for rect in rects))
        for attempt in range(5000):
            yaw = (math.pi/2 if axis_y else 0.)+rng.uniform(-math.radians(8), math.radians(8))
            if rng.random() < .5:
                yaw += math.pi                          # lugs are identical; both facings occur
            c, s = math.cos(yaw), math.sin(yaw)
            ex = CRATE.landing_end_m*abs(c)+.05*abs(s)  # landing extent along x / y, as landing_fits
            ey = CRATE.landing_end_m*abs(s)+.05*abs(c)
            d = rng.uniform(lo, hi)
            if axis_y:
                x = cx+rng.uniform(-CROSS_OFFSET_M, CROSS_OFFSET_M)
                y = cy+side_sign*(hy-ey-.04+d)
            else:
                y = cy+rng.uniform(-.3, .3)
                x = cx+side_sign*(hx-ex-.04+d)
            crate = [x, y, yaw]
            if math.dist(crate[:2], (cx, cy)) > HANDOFF_MAX_M:
                rejects['handoff_distance'] += 1
                continue
            if not pose_clear(crate, FOOTPRINT, rects, bounds=bounds, margin=.005):
                rejects['crate_wall'] += 1
                continue
            if any(math.dist(crate[:2], q['pose_m'][:2]) < .35 for q in others):
                rejects['crate_other_cargo'] += 1
                continue
            r = .5+1.5*(((i+attempt) % 10+rng.random())/10)
            az = yaw+2*math.pi*(((i*7+attempt) % 12+rng.random())/12)
            own = [x+r*math.cos(az), y+r*math.sin(az)]
            facing = math.atan2(y-own[1], x-own[0])
            ownyaw = facing+rng.uniform(-math.pi/3, math.pi/3)
            # peer cases relative to the lug the peer will take; the lug choice needs both starts,
            # so the peer start is drawn first in crate-axis terms and assigned afterwards.
            other_end = rng.choice(('teal', 'blue'))
            ox, oy, oh = station_xy(CRATE, other_end, *crate)
            if peer == 'other_end':
                other = [ox, oy]
            elif peer == 'near_own':
                other = [own[0]+rng.uniform(-.45, .45), own[1]+rng.uniform(-.45, .45)]
            elif peer == 'approaching':
                pr = rng.uniform(.65, 1.4)
                pa = az+rng.uniform(-1.0, 1.0)
                other = [x+pr*math.cos(pa), y+pr*math.sin(pa)]
            else:
                # 'absent': the gate is a two-robot teacher, so the peer starts far away (2.0-2.6 m)
                pr = rng.uniform(2.0, 2.6)
                pa = az+math.pi+rng.uniform(-.8, .8)
                other = [x+pr*math.cos(pa), y+pr*math.sin(pa)]
            otheryaw = math.atan2(y-other[1], x-other[0])
            if assignment == 'fixed_rgb_lugs_v1':
                # Public role tickets, independent of both GT spawn positions.
                # Runtime confirms the assigned colour in each own RGB frame.
                end1,end2='teal','blue'
            elif assignment == 'nearest':
                end1, end2 = assign(own, other, crate)
            else:
                end1 = 'teal' if i % 2 == 0 else 'blue'
                end2 = 'blue' if end1 == 'teal' else 'teal'
            active = [own, other]
            if any(not free(q, .18) for q in active):
                rejects['robot_wall'] += 1
                continue
            if any(math.dist(q, p['pose_m'][:2]) < .3 for q in active for p in others):
                rejects['robot_other_cargo'] += 1
                continue
            if math.dist(own, other) < .37:
                rejects['robot_overlap'] += 1
                continue
            if any(math.dist(q, crate[:2]) < .29 for q in active):
                rejects['robot_crate'] += 1
                continue
            parking = None
            for _ in range(2000):
                q = [rng.uniform(bounds[0]+.2, bounds[1]-.2), rng.uniform(bounds[2]+.2, bounds[3]-.2)]
                if (free(q, .18) and all(math.dist(q, a) > .7 for a in active+[crate[:2]])
                        and all(math.dist(q, p['pose_m'][:2]) > .3 for p in others)):
                    parking = q
                    break
            if parking is None:
                rejects['no_parking'] += 1
                continue
            roles = {'r1': end1, 'r2': end2}
            if end1 == end2:
                raise ValueError('two robots must take different lugs')
            err = {rid: [rng.gauss(0, POSE_ERROR[0]), rng.gauss(0, POSE_ERROR[0]), rng.gauss(0, POSE_ERROR[1])]
                   for rid in ('r1', 'r2')}
            episode = {
                'episode_id': f'{split}-{seed+i}', 'batch': f'crate-teacher-{split}-{seed}', 'seed': seed+i, 'split': split,
                'scenario_id': scenario_id, 'scenario_source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'map_id': scenario['map_id'], 'cargo_pose': crate,
                'spawns': {'r1': [*own, BASE_Z, ownyaw], 'r2': [*other, BASE_Z, otheryaw], 'r3': [*parking, BASE_Z, 0.]},
                'roles': roles, 'role_tickets': {rid: CRATE.role_of(e) for rid, e in roles.items()},
                'target_item': CRATE.item_id, 'object_kind': 'heavy_crate', 'skill': 'grasp_lift_release',
                'destination_region': 'zone_'+destination, 'lug_color_scene': 'crate_lug_colors_v1',
                'assignment_source': ('fixed_rgb_lugs_v1' if assignment == 'fixed_rgb_lugs_v1' else
                                      'demo_rule_nearest_lug' if assignment == 'nearest' else 'demo_rule_alternating'),
                'initial_pan': {'r1': rng.randint(500, 2500), 'r2': rng.randint(500, 2500)},
                'peer_case': peer, 'stratum': {'axial_outside_m': [lo, hi], 'sampled_outside_m': d,
                                               'axis': 'y' if axis_y else 'x', 'side': side_sign},
                'near_wall': min(rect_distance(crate, rect) for rect in rects) < .45,
                'handoff_pose_error': err, 'crate_to_zone_center_m': math.dist(crate[:2], (cx, cy)),
                'proposal_attempts': attempt+1}
            if checker is not None:
                report = checker.check(episode)
                los_proposals += 1
                if original_start is None:
                    # First geometrically valid proposal is byte-for-byte the
                    # toggle-off start. Keep it even when subsequently rejected.
                    original_start = {'seed': seed+i, 'cargo_pose': crate,
                                      'spawns': episode['spawns'], 'roles': roles,
                                      'initial_pan': episode['initial_pan'], **report}
                if not report['accepted']:
                    rejects['start_assigned_los'] += 1
                    for rid, value in report['robots'].items():
                        if not value['gate5']:
                            rejects['start_assigned_los_'+rid] += 1
                    continue
                episode['start_assigned_los'] = start_assigned_los
                episode['start_los_audit'] = report
                episode['start_los_proposals'] = los_proposals
                original_starts.append(original_start)
                accepted_starts.append(report)
            episodes.append(episode)
            break
        else:
            raise ValueError(f'no admissible crate start for index {i}; {dict(rejects)}')
    if indices is not None:     # keep only these generated indices (the episode seeds stay seed+index)
        episodes = [episodes[j] for j in indices]
        if checker is not None:
            original_starts = [original_starts[j] for j in indices]
            accepted_starts = [accepted_starts[j] for j in indices]
    return {'schema': 'ugrp.crate_teacher.plan.v1', 'episodes': episodes, 'rejected_proposals': dict(rejects),
            **({'start_assigned_los': start_assigned_los,
                'start_los_audit': {
                    'scope': 'demonstration start generation only; never teacher action inputs',
                    'method': 'joint proposal rejection sampling; redraw cargo and robot poses within the existing map/zone/strata and assignment rules',
                    'minimum_visible_probes': 5, 'probe_N': 15,
                    'yaw_step_deg': 1, 'yaw_views_per_pitch': 360,
                    'pitches': [list(p) for p in PITCHES],
                    'original': summarize(original_starts), 'accepted': summarize(accepted_starts),
                    'original_starts': original_starts,
                    'rejected_los_proposals': rejects['start_assigned_los'],
                    'total_los_proposals': sum(e['start_los_proposals'] for e in episodes),
                    'mj_step_calls': 0, 'render_calls': 0}} if checker is not None else {}),
            'distribution': {
                'robot_distance_m': [.5, 2.0], 'peer_cases': list(PEERS), 'scenarios': list(scenarios), 'scenario_set': scenario_set,
                'crate_axis': 'zone long side (y) or across it (x), +-8 deg, both facings',
                'axial_strata_outside_m': STRATA, 'handoff_max_m': HANDOFF_MAX_M,
                'handoff_pose_error_sigma': {'xy_m': POSE_ERROR[0], 'yaw_rad': POSE_ERROR[1]},
                'assignment': assignment, 'lug_color_scene': 'crate_lug_colors_v1',
                'fixed': ['floor_light_v1', 'camera review v3 runtime binding', 'native v7', 'cargo_noslip_v1', 'weld off']},
            'criteria': {
                'teacher_target_rate': .95, 'minimum_episodes': 40,
                'grasp_lift': 'both bilateral >=0.5 N, crate lowest point >= 12 mm, tilt <= 10 deg for >= 3 s',
                'release': 'landing rectangle inside the zone, z < 0.05, no finger contact, speed < 0.01 m/s, tilt < 3 deg, '
                           'both grippers open (>=1900) and grip site >= 4 cm from the crate axis segment, for 2 s',
                'denominators': 'grasp_lift N=40; release counted over held episodes and over all 40'},
            'student_evaluation': False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--count', type=int, default=40)
    p.add_argument('--seed', type=int, default=77000)
    p.add_argument('--split', default='crate_gate')
    p.add_argument('--assignment', choices=LOUD, default='nearest')
    p.add_argument('--scenario-set', choices=tuple(SCENARIO_SETS), default='v4')
    p.add_argument('--start-assigned-los', choices=('off', 'start_assigned_los_v1'), default='off')
    p.add_argument('--indices', default=None, help='comma separated generated indices to keep (diagnostic subset)')
    a = p.parse_args()
    result = prepare(count=a.count, seed=a.seed, split=a.split, assignment=a.assignment,
                     indices=None if a.indices is None else [int(v) for v in a.indices.split(',')],
                     scenario_set=a.scenario_set, start_assigned_los=a.start_assigned_los)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'episodes': len(result['episodes']), 'rejected': result['rejected_proposals']}))


if __name__ == '__main__':
    main()
