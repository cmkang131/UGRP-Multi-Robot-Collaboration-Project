"""Pure saved-input / command replay. No physics, renderer, remote or truth feedback."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import subprocess

from harness.zone_final_environment import resolve
from scripts.zone_teacher import plan_path, proportional_drive, PeerDisc
from sim.solo_carry_pose import task_start
from sim.solo_carry_to_zone import CarryToZone
from sim.grasp_act_port import duty_wheels
from sim.grasp_act_visible_route import waypoint

PROFILE = 'carry5_active_localization_v1'
PLAN = Path('experiments/2026-10-15-map-carry-zone/diagnostic-plan-v4.json')


def issue(carry, drive):
    w, d = duty_wheels([3*drive[0], 3*drive[1], .65*drive[2]])
    carry.issue({'t': carry.loc.now, 'wheels': w, 'duration_s': d,
                 'pwm': {str(k): 1500 for k in (1, 3, 4, 5, 6)}}, .1)


def map_controller(episode, enabled):
    static = resolve(episode['map_id'])[0]
    return CarryToZone(static, episode['destination_zone'], start=task_start(static),
                       recovery_profile=PROFILE if enabled else 'off')


def replay(episode, *, enabled=True, approach=True):
    m = map_controller(episode, enabled)
    station = [episode['cargo_pose_m'][0]-.2002, episode['cargo_pose_m'][1]]
    # Plan/setup coordinates only define this offline nominal route experiment;
    # no measured/evaluation pose, obstacles or successful fix are injected.
    path = plan_path(m.loc.pose[:2], station, m.static['bounds_m'], [], rects=m.rects, radius=.26)
    length = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
    first = None
    if approach:
        for _ in range(3000):
            if math.dist(m.loc.pose[:2], station) <= .025:
                break
            if enabled and m.needs_recovery(m.loc.now):
                first = {'phase': 'approach', 'reason': m.recovery_reason, 't': m.loc.now}
                break
            point = waypoint(m.loc.pose[:2], path, [], m.rects, .26)
            if point is None:
                raise AssertionError('nominal v4 approach has no path')
            if enabled:
                drive = m.heading_drive(m.loc.pose, point, 0.)
            else:
                cmd = proportional_drive(m.loc.pose, station, point, 0.)
                drive = (max(-.05, min(.08, cmd['forward'])), max(-.06, min(.06, cmd['left'])), max(-.1, min(.1, cmd['turn'])))
            issue(m, drive)
        else:
            raise AssertionError('nominal approach exceeded finite command cap')
    else:
        # Explicit reviewer counterfactual: carry starts at the nominal station
        # with the original prior covariance and zero accumulated command budget.
        m.loc.own.x[:2] = station
    if first is None:
        m.start(m.loc.now, (.2002, 0.))
        for _ in range(3000):
            drive, arrived, failure = m.step(m.loc.now)
            if failure or m.recovery_reason or arrived:
                first = {'phase': 'carry', 'reason': failure or m.recovery_reason or 'arrived', 't': m.loc.now}
                break
            issue(m, drive)
        else:
            raise AssertionError('nominal carry exceeded finite command cap')
    row = {'seed': episode['seed'], 'kind': episode['kind'], 'zone': episode['destination_zone'],
           'approach_included': approach, 'approach_path_m': length, **first,
           'pose_at_branch': m.loc.pose,
           'distance_since_fix_m': m.loc.distance_since_fix, 'turn_since_fix_deg': math.degrees(m.loc.turn_since_fix),
           'sigma_m_m_deg': [*m.loc.sigmas()[:2], math.degrees(m.loc.sigmas()[2])],
           'hard_guard_open': m.loc.ready(m.loc.now), 'physical_effect_verified': False}
    if enabled:
        from sim.grasp_act_solo_lookaround import SoloLookaround
        from sim.grasp_act_solo_teacher import primitives
        look = SoloLookaround(m.static, ops=primitives(), truth_free_v1=True, command_pose=m.loc, carry5=True)
        look.arm(); look.start(m.loc.now, 1500)
        row['planned_landmark_views'] = len(look.loc.plan['views'])
        row['planned_landmark_groups'] = look.loc.plan['expected_landmarks']
        row['accepted_rgb_fixes'] = m.loc.fixes
        row['no_fix_outcome'] = 'carry_relocalization_unconfirmed' if not m.finish_recovery(m.loc.now, m.loc.fixes) else 'unexpected'
    return row


def saved(raw):
    p = raw/'teacher-commands.jsonl.zst'
    text = subprocess.check_output(['zstd', '-dc', str(p)], text=True)
    rows = [json.loads(x) for x in text.splitlines()]
    episode = json.loads((raw/'plan.json').read_text())
    m = map_controller(episode, True)
    m.loc.now = m.loc.started = rows[0]['t']
    trigger = None
    out = []
    for i, row in enumerate(rows):
        if i:
            m.issue(rows[i-1]['command'], row['t']-rows[i-1]['t'])
        if trigger is None and m.needs_recovery(m.loc.now):
            trigger = {'sim_s': row['t']-rows[0]['t'], 'reason': m.recovery_reason,
                       'sigma': m.loc.sigmas(), 'hard_guard_open': m.loc.ready(m.loc.now)}
        sim_t = row['t']-rows[0]['t']
        if any(abs(sim_t-t)<.01 for t in (21., 30., 53.6)):
            # Reproduce original saved map/visible body input A*: no evaluation fields.
            x, y, a = row['map_pose']['pose_estimate']; c, s = math.cos(a), math.sin(a)
            target = row['visible_target']; tx, ty = target['xyz'][:2]; yaw = target['yaw']
            goal = (tx-.2002*math.cos(yaw), ty-.2002*math.sin(yaw), yaw)
            rects = [(c*(ox-x)+s*(oy-y), -s*(ox-x)+c*(oy-y), hx, hy, angle-a)
                     for ox, oy, hx, hy, angle in m.rects]
            discs = []
            for ob in row['carry_obstacles']['tracks']:
                ox, oy = ob['xy']; q = (c*(ox-x)+s*(oy-y), -s*(ox-x)+c*(oy-y))
                if math.dist(q, (tx, ty)) > .12:
                    r = ob['radius']+ob['range_error_m']+(min(.20, .01*max(0., row['t']-ob['seen_t'])) if ob['kind']=='robot' else 0.)
                    discs.append(PeerDisc((*q, r)))
            paths = {name: bool(plan_path((0., 0.), goal[:2], (-2., 2., -2., 2.), dd, rects=rr, radius=.17))
                     for name, dd, rr in [('static_only', [], rects), ('rgb_only', discs, []), ('full', discs, rects)]}
            # Snapshot adapter from saved issued belief; this does not submit commands.
            snapshot = map_controller(episode, True)
            snapshot.loc.own.x[:] = row['map_pose']['pose_estimate']
            snapshot.loc.now = row['t']
            snapshot.loc.distance_since_fix = row['map_pose']['issued_distance_since_fix_m']
            snapshot.loc.turn_since_fix = row['map_pose']['issued_turn_since_fix_rad']
            drive = snapshot.pickup_route(goal, (tx, ty), episode['kind'], row['t'])
            out.append({'sim_s': sim_t, 'paths': paths, 'carry5_drive': drive,
                        'carry5_branch': snapshot.recovery_reason})
    return {'source': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
            'rows': len(rows), 'first_recovery_if_enabled': trigger, 'snapshots': out,
            'after_first_trigger': 'continued archived commands only, not a closed-loop rollout'}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--raw', type=Path); args = p.parse_args()
    episodes = json.loads(PLAN.read_text())['episodes']
    result = {'scope': 'command-only replay; no physics/render; RGB fix acceptance rate unmeasured',
              'plan_sha256': hashlib.sha256(PLAN.read_bytes()).hexdigest(),
              'v4': [replay(e, enabled=False) for e in episodes],
              'carry5': [replay(e) for e in episodes],
              'carry5_zero_budget_at_station_counterfactual': [replay(e, approach=False) for e in episodes]}
    if args.raw:
        result['saved_93220'] = saved(args.raw)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')


if __name__ == '__main__':
    main()
