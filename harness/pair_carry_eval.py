"""Evaluation-only judge for the P2 pair carry (GT; never a policy input).

Success (pre-registered in experiments/2026-10-21-pairact-p2/DESIGN.md §5):

    placed_in_zone_B  AND  drop_events == 0  AND  robot_robot_contacts == 0

Wall contacts are RECORDED (count, first time, which body) but are not a
failure term. The evaluator reads only eval-only truth rows (the same
``snapshot()`` rows the frozen runner writes to eval-only.jsonl) plus the
teacher's lower-start time as the boundary between "carry" (any descent is a
drop) and "set-down" (commanded descent). It never reads teacher internals
otherwise, and it does not trust the teacher's own outcome.

Contacts: the default source is a GT geometry proxy (robot discs / beam
rectangle vs walls and vs each other). Native MuJoCo/MJWarp contact rows are
the preferred source but are not wired on the Warp mirror yet
(``native_contacts`` -> NotImplementedError, see TODO list in DESIGN.md §8).
"""
from __future__ import annotations

import math

from harness.pair_carry_teacher_warp import (BEAM_HALF, ROBOT_RADIUS_M, HOLD_MIN_Z_M, HOLD_MIN_FORCE,
                                             beam_corners, rect_distance, wall_rects, zone_of, door_of,
                                             wrap)

SCHEMA = 'ugrp.pairact.carry_eval.v1'


class Criteria:
    # carry window (handover .. lower start): drop if the load is not held
    drop_min_z_m = HOLD_MIN_Z_M      # same 0.012 m as the joint-hold gate
    drop_dwell_s = .3                # min_z below threshold this long -> drop
    drop_tilt_deg = 30.              # any time before rest: gross tilt -> drop
    drop_fall_mps = .25              # any time: beam-centre descent faster than this -> drop
    # placement at the end
    rest_max_z_m = .006              # beam lowest point within 6 mm of the floor
    rest_max_tilt_deg = 5.
    rest_still_s = 1.                # pose change below rest_still_m over this window
    rest_still_m = .005
    released_max_force = HOLD_MIN_FORCE   # both jaws below this at the end
    zone_margin_m = 0.               # beam footprint fully inside zone B
    # contact proxies
    robot_radius_m = ROBOT_RADIUS_M
    robot_contact_gap_m = 0.         # discs overlapping
    wall_contact_gap_m = 0.
    # funnel
    carried_min_m = 1.
    door_clear_m = .2                # bases and beam centre this far past the door plane


def native_contacts(world):  # pragma: no cover - needs the simulator
    """TODO(P2-warp): read robot-robot / robot-wall / beam-wall contact pairs from
    the MJWarp batch (``hooks`` contact arrays, cf. WarpTransport.forces). The CPU
    perception mirror is not guaranteed to hold contact rows under Warp."""
    raise NotImplementedError('native contact rows on the MJWarp mirror are not wired (P2 TODO)')


def _beam_center_z(row):
    pos = row['beam'].get('xyz')
    return None if pos is None else float(pos[2])


def contact_proxy(row, rects, roles, crit=Criteria):
    """Geometry proxy contacts for one GT row."""
    robots = {rid: row['robots'][rid]['pose'] for rid in roles}
    out = {'robot_robot': False, 'robot_wall': [], 'beam_wall': False}
    rids = list(robots)
    for a in range(len(rids)):
        for b in range(a + 1, len(rids)):
            if math.dist(robots[rids[a]][:2], robots[rids[b]][:2]) < 2*crit.robot_radius_m - crit.robot_contact_gap_m:
                out['robot_robot'] = True
    for rid, p in robots.items():
        if min((rect_distance(p[:2], w) for w in rects), default=math.inf) < crit.robot_radius_m - crit.wall_contact_gap_m:
            out['robot_wall'].append(rid)
    corners = beam_corners(tuple(row['beam']['pose']), BEAM_HALF)
    # beam rectangle vs wall rectangles: corner-in-wall or wall-corner-in-beam
    for c in corners:
        if min((rect_distance(c, w) for w in rects), default=math.inf) <= crit.wall_contact_gap_m:
            out['beam_wall'] = True
    beam_rect = (*row['beam']['pose'][:2], *BEAM_HALF, row['beam']['pose'][2])
    for cx, cy, hx, hy, yaw in rects:
        if out['beam_wall']:
            break
        for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            wc = (cx + math.cos(yaw)*sx*hx - math.sin(yaw)*sy*hy, cy + math.sin(yaw)*sx*hx + math.cos(yaw)*sy*hy)
            if rect_distance(wc, beam_rect) <= crit.wall_contact_gap_m:
                out['beam_wall'] = True
                break
    return out


def beam_inside(pose, zone, margin=0.):
    return all(abs(x - zone['cx']) <= zone['hx'] - margin + 1e-9 and abs(y - zone['cy']) <= zone['hy'] - margin + 1e-9
               for x, y in beam_corners(tuple(pose), BEAM_HALF))


def evaluate(rows, static_map, roles, *, lower_start_t=None, handover_t=None, contacts=None,
             crit=Criteria, door_id='door_wide', zone='zone_B'):
    """Judge one episode from GT rows starting at (or before) the handover.

    rows: list of dicts with keys t, beam{pose,min_z,tilt_deg[,xyz]}, robots{rid:{pose}},
          contacts{rid:[f_left,f_right]}.
    lower_start_t: teacher time at which the commanded set-down began (None if never).
    contacts: optional per-row native contact dicts (same shape as contact_proxy output);
              None -> geometry proxy.
    """
    roles = list(roles)
    z, door, rects = zone_of(static_map, zone), door_of(static_map, door_id), wall_rects(static_map)
    if not rows:
        return {'schema': SCHEMA, 'success': False, 'failure': 'no_rows'}
    t0 = handover_t if handover_t is not None else rows[0]['t']
    rows = [r for r in rows if r['t'] >= t0 - 1e-9]
    drops, rr, walls = [], [], []
    low_since = None
    start_xy = rows[0]['beam']['pose'][:2]
    carried = 0.
    door_t = None
    prev = None
    for k, r in enumerate(rows):
        t, beam = r['t'], r['beam']
        in_carry = lower_start_t is None or t < lower_start_t - 1e-9
        if in_carry:
            if beam['min_z'] < crit.drop_min_z_m:
                low_since = t if low_since is None else low_since
                if t - low_since >= crit.drop_dwell_s - 1e-9 and not any(d['kind'] == 'carry_low' for d in drops):
                    drops.append({'t': t, 'kind': 'carry_low', 'min_z': beam['min_z']})
            else:
                low_since = None
        if beam['tilt_deg'] > crit.drop_tilt_deg and not any(d['kind'] == 'tilt' for d in drops):
            drops.append({'t': t, 'kind': 'tilt', 'tilt_deg': beam['tilt_deg']})
        if prev is not None and _beam_center_z(r) is not None and _beam_center_z(prev) is not None:
            dt = t - prev['t']
            if dt > 1e-9 and (_beam_center_z(prev) - _beam_center_z(r))/dt > crit.drop_fall_mps \
                    and not any(d['kind'] == 'fall' for d in drops):
                drops.append({'t': t, 'kind': 'fall', 'vz': (_beam_center_z(r) - _beam_center_z(prev))/dt})
        c = contacts[k] if contacts is not None else contact_proxy(r, rects, roles, crit)
        if c['robot_robot']:
            rr.append(t)
        for rid in c['robot_wall']:
            walls.append({'t': t, 'body': rid})
        if c['beam_wall']:
            walls.append({'t': t, 'body': 'beam'})
        carried = max(carried, math.dist(start_xy, beam['pose'][:2]))
        if door_t is None and all(r['robots'][rid]['pose'][0] >= door['x'] + crit.door_clear_m for rid in roles) \
                and beam['pose'][0] >= door['x'] + crit.door_clear_m:
            door_t = t
        prev = r
    last = rows[-1]
    window = [r for r in rows if r['t'] >= last['t'] - crit.rest_still_s - 1e-9]
    still = (last['t'] - window[0]['t'] >= crit.rest_still_s - 1e-6 and
             max(math.dist(w['beam']['pose'][:2], last['beam']['pose'][:2]) for w in window) <= crit.rest_still_m and
             max(abs(wrap(w['beam']['pose'][2] - last['beam']['pose'][2])) for w in window) <= math.radians(1.))
    resting = last['beam']['min_z'] <= crit.rest_max_z_m and last['beam']['tilt_deg'] <= crit.rest_max_tilt_deg
    released = all(max(last['contacts'][rid]) < crit.released_max_force for rid in roles)
    inside = beam_inside(last['beam']['pose'], z, crit.zone_margin_m)
    placed = bool(inside and resting and still and released)
    funnel = {'handover': True,
              'carried_1m': carried >= crit.carried_min_m,
              'door_passed': door_t is not None,
              'zone_inside_final': inside,
              'lowered_resting': resting,
              'released': released,
              'still_1s': still}
    success = placed and not drops and not rr
    failure = None
    if not success:
        failure = ('drop' if drops else 'robot_robot_contact' if rr else
                   'not_through_door' if door_t is None else 'not_in_zone' if not inside else
                   'not_resting' if not resting else 'not_released' if not released else 'not_still')
    return {'schema': SCHEMA, 'success': success, 'failure': failure, 'placed_in_zone': placed,
            'drop_events': drops, 'robot_robot_contact_ticks': len(rr),
            'robot_robot_first_t': rr[0] if rr else None,
            'wall_contact_ticks': len(walls), 'wall_contact_first': walls[0] if walls else None,
            'wall_contact_bodies': sorted({w['body'] for w in walls}),
            'contact_source': 'native' if contacts is not None else 'gt_geometry_proxy_v1',
            'funnel': funnel, 'carried_max_m': carried, 'door_passed_t': door_t,
            'final_beam_pose': list(last['beam']['pose']), 'final_min_z': last['beam']['min_z'],
            'final_tilt_deg': last['beam']['tilt_deg'], 'handover_t': t0, 'lower_start_t': lower_start_t,
            'end_t': last['t'], 'zone': z['id'], 'door': door['id'],
            'criteria': {k: getattr(crit, k) for k in dir(crit) if not k.startswith('_')}}


def eval_row(truth):
    """Slim the runner's snapshot() row to what the evaluator needs (keeps beam xyz)."""
    beam = truth['beam']
    xyz = beam.get('xyz')
    if xyz is None and beam.get('ends'):
        # snapshot() has no centre z; the mean end height is the same rigid offset
        ends = list(beam['ends'].values())
        xyz = [beam['pose'][0], beam['pose'][1], sum(e[2] for e in ends)/len(ends)]
    return {'t': truth['t'], 'beam': {'pose': list(beam['pose']), 'min_z': beam['min_z'], 'tilt_deg': beam['tilt_deg'],
                                      'xyz': xyz},
            'robots': {rid: {'pose': list(v['pose'])} for rid, v in truth['robots'].items()},
            'contacts': {rid: list(v) for rid, v in truth['contacts'].items()}}
