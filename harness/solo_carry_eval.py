"""Evaluation-only gates for the single-robot carry (pure functions over recorded rows).

DERIVED / UNVERIFIED (solo-e2e/20261024): not yet run against any physics output.
Nothing here is ever a teacher or student input; it reads only eval-only truth
rows. No simulator, teacher or student imports.

Row shape = the rows ``scripts/run_grasp_act_teacher.snapshot`` writes to
``eval-only.jsonl`` (also what ``harness.pair_carry_eval.eval_row`` keeps):

    {'t': s, 'beam': {'pose': [x, y, yaw], 'min_z': m, 'tilt_deg': deg},
     'robots': {rid: {'pose': [...]}}, 'contacts': {rid: [left_N, right_N]}}

The key ``'beam'`` is the pair runner's name for the carried object; in a solo
episode it holds the CAN. ``min_z`` is the lowest point of the cargo above the
floor.

Gates (all must pass; ``failure`` names the first one that does not, in this order):

  lift         grasp + stable lift: min_z >= 0.012 m, tilt <= 10 deg, each finger
               >= 0.5 N, continuously for 3 s (``LiftScore`` criteria)
  no_drop      from the start of that stable lift until the commanded set-down
               begins (``lower_start_t``), min_z never falls below 0.012 m
  slot         the final cargo disc lies fully inside the designated zone-B slot rectangle
  rest         over the last ``rest_still_s``: on the floor (min_z <= 6 mm), tilt <= 5 deg,
               moved <= 5 mm, finger load < 0.1 N
  release      gentle: first row after ``lower_start_t`` with both fingers < 0.1 N has the
               cargo within [-5, 6] mm of the floor; afterwards cargo speed <= 0.02 m/s
               and tilt <= 10 deg
  completion   release + rest window finished within ``cap_s`` of ``t0``

An unobserved quantity (missing / None / non-finite / negative contact or height)
FAILS the gate that needs it; it is never treated as zero force or as passing.

Provenance of the numbers (see docs/solo-e2e-20261024.md "open numeric pins"):
  * lift criteria      harness/grasp_act_rollout.LiftScore.CRITERIA, on dsh/pairact-r1-dryrun
                       (not in the pinned tree); same 0.012 / 0.5 N as
                       harness/pair_carry_teacher_warp.HOLD_MIN_Z_M / HOLD_MIN_FORCE (in tree)
  * release criteria   harness/grasp_act_rollout.SoloScore.RELEASE_CRITERIA, same branch
                       (clearance [-0.005, 0.006], finger_max 0.1 N, linear speed 0.02 m/s)
  * rest criteria      harness/pair_carry_eval.Criteria (in tree)
  * cap_s              NOT pinned here: a required argument.
"""
from __future__ import annotations

import math

SCHEMA = 'ugrp.solo.carry_eval.v1'
STATUS = 'derived_unverified_no_physics_run'
GATES = ('lift', 'no_drop', 'slot', 'rest', 'release', 'completion')


class Criteria:
    # lift
    lift_min_z_m = .012
    lift_max_tilt_deg = 10.
    lift_finger_each_n = .5
    lift_hold_s = 3.
    max_row_gap_s = .15
    # no drop: strict (any row below the threshold) -- the spec says "never returns to below"
    drop_dwell_s = 0.
    # release (SoloScore.RELEASE_CRITERIA)
    release_finger_max_n = .1
    release_clearance_m = (-.005, .006)
    release_speed_max_mps = .02
    release_tilt_max_deg = 10.
    # rest (pair_carry_eval.Criteria)
    rest_max_z_m = .006
    rest_max_tilt_deg = 5.
    rest_still_s = 1.
    rest_still_m = .005
    # slot
    cargo_radius_m = .019            # sim/zone_cargo.py CATALOGUE['can'] landing_half_extents_m
    slot_margin_m = 0.


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def forces(row, rid):
    """(left_N, right_N) or None when the contact reading is unobserved."""
    contacts = row.get('contacts')
    pair = contacts.get(rid) if isinstance(contacts, dict) else None
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return None
    values = tuple(_num(v) for v in pair)
    return None if any(v is None or v < 0 for v in values) else values


def cargo(row):
    """(x, y, min_z, tilt_deg) or None when any of them is unobserved."""
    beam = row.get('beam')
    if not isinstance(beam, dict) or not isinstance(beam.get('pose'), (list, tuple)) or len(beam['pose']) < 2:
        return None
    values = (_num(beam['pose'][0]), _num(beam['pose'][1]), _num(beam.get('min_z')), _num(beam.get('tilt_deg')))
    return None if any(v is None for v in values) else values


def lift_gate(rows, rid, crit=Criteria):
    stable = best = 0.
    stable_start = first_start = None
    prev_t, prev_good = None, False
    unobserved_contact = unobserved_cargo = gaps = observed_contact = 0
    for row in rows:
        t = float(row['t'])
        f, c = forces(row, rid), cargo(row)
        unobserved_contact += f is None
        unobserved_cargo += c is None
        observed_contact += f is not None
        good = (f is not None and c is not None and c[2] >= crit.lift_min_z_m and c[3] <= crit.lift_max_tilt_deg
                and min(f) >= crit.lift_finger_each_n)
        dt = 0. if prev_t is None else t - prev_t
        if dt > crit.max_row_gap_s + 1e-8:
            gaps += 1
            prev_good = False
        if good and prev_good:
            stable += dt
        else:
            stable, stable_start = 0., (t if good else None)
        best = max(best, stable)
        if first_start is None and stable >= crit.lift_hold_s - 1e-8:
            first_start = stable_start      # start of the FIRST run that reached the hold time
        prev_t, prev_good = t, good
    ok = best >= crit.lift_hold_s - 1e-8
    reason = None if ok else ('contact_unobserved' if observed_contact == 0 else 'lift_not_stable')
    return {'pass': ok, 'reason': reason, 'max_stable_lift_s': best, 'stable_start_t': first_start if ok else None,
            'unobserved_contact_rows': unobserved_contact, 'unobserved_cargo_rows': unobserved_cargo,
            'row_gaps': gaps}


def drop_gate(rows, lift, lower_start_t, crit=Criteria):
    if not lift['pass']:
        return {'pass': False, 'reason': 'no_stable_lift'}
    start = lift['stable_start_t']
    below_since, drops, unobserved = None, [], 0
    for row in rows:
        t = float(row['t'])
        if t < start - 1e-9 or (lower_start_t is not None and t >= lower_start_t - 1e-9):
            continue
        c = cargo(row)
        if c is None:
            unobserved += 1
            continue
        if c[2] < crit.lift_min_z_m:
            below_since = t if below_since is None else below_since
            if t - below_since >= crit.drop_dwell_s - 1e-9:
                drops.append(t)
        else:
            below_since = None
    ok = not drops and not unobserved
    return {'pass': ok, 'reason': None if ok else ('cargo_unobserved' if unobserved and not drops else 'dropped_after_lift'),
            'drop_rows': len(drops), 'first_drop_t': drops[0] if drops else None, 'unobserved_rows': unobserved,
            'window': [start, lower_start_t]}


def slot_gate(rows, slot, crit=Criteria):
    from harness.solo_carry_contract import slot_contains
    c = cargo(rows[-1]) if rows else None
    if c is None:
        return {'pass': False, 'reason': 'cargo_unobserved'}
    inside = slot_contains(slot, c[:2], crit.cargo_radius_m, crit.slot_margin_m)
    return {'pass': inside, 'reason': None if inside else 'outside_slot', 'final_xy': [c[0], c[1]]}


def rest_gate(rows, rid, crit=Criteria):
    if not rows or float(rows[-1]['t']) - float(rows[0]['t']) < crit.rest_still_s - 1e-8:
        return {'pass': False, 'reason': 'insufficient_rows_for_rest'}
    end = float(rows[-1]['t'])
    window = [r for r in rows if float(r['t']) >= end - crit.rest_still_s - 1e-9]
    first = None
    worst_move = 0.
    for row in window:
        c, f = cargo(row), forces(row, rid)
        if c is None or f is None:
            return {'pass': False, 'reason': 'unobserved_in_rest_window'}
        first = first or c
        worst_move = max(worst_move, math.dist(c[:2], first[:2]))
        if c[2] > crit.rest_max_z_m or c[3] > crit.rest_max_tilt_deg or max(f) >= crit.release_finger_max_n:
            return {'pass': False, 'reason': 'not_at_rest', 'max_move_m': worst_move}
    ok = worst_move <= crit.rest_still_m
    return {'pass': ok, 'reason': None if ok else 'still_moving', 'max_move_m': worst_move}


def release_gate(rows, rid, lower_start_t, crit=Criteria):
    if lower_start_t is None:
        return {'pass': False, 'reason': 'lower_start_missing', 'release_t': None}
    after = [r for r in rows if float(r['t']) >= lower_start_t - 1e-9]
    release_t = None
    for k, row in enumerate(after):
        f = forces(row, rid)
        if f is None:
            return {'pass': False, 'reason': 'contact_unobserved', 'release_t': None}
        if max(f) < crit.release_finger_max_n:
            release_t, tail = float(row['t']), after[k:]
            break
    if release_t is None:
        return {'pass': False, 'reason': 'never_released', 'release_t': None}
    c0 = cargo(tail[0])
    if c0 is None:
        return {'pass': False, 'reason': 'cargo_unobserved', 'release_t': release_t}
    lo, hi = crit.release_clearance_m
    max_speed, prev = 0., None
    for row in tail:
        c = cargo(row)
        if c is None:
            return {'pass': False, 'reason': 'cargo_unobserved', 'release_t': release_t}
        if c[3] > crit.release_tilt_max_deg:
            return {'pass': False, 'reason': 'tilted_after_release', 'release_t': release_t}
        if prev is not None and float(row['t']) > prev[0]:
            dt = float(row['t']) - prev[0]
            max_speed = max(max_speed, math.dist((c[0], c[1], c[2]), prev[1])/dt)
        prev = (float(row['t']), (c[0], c[1], c[2]))
    clearance_ok = lo <= c0[2] <= hi
    speed_ok = max_speed <= crit.release_speed_max_mps
    reason = None if clearance_ok and speed_ok else ('released_from_height' if not clearance_ok else 'release_too_fast')
    return {'pass': clearance_ok and speed_ok, 'reason': reason, 'release_t': release_t,
            'clearance_at_release_m': c0[2], 'max_speed_after_release_mps': max_speed}


def completion_gate(release, rest, t0, cap_s, crit=Criteria):
    if not (release['pass'] and rest['pass']):
        return {'pass': False, 'reason': 'not_released_or_not_at_rest', 'completion_t': None}
    completion_t = release['release_t'] + crit.rest_still_s
    elapsed = completion_t - t0
    return {'pass': elapsed <= cap_s + 1e-8, 'reason': None if elapsed <= cap_s + 1e-8 else 'over_cap',
            'completion_t': completion_t, 'elapsed_s': elapsed, 'cap_s': cap_s}


def evaluate(rows, slot, rid, *, lower_start_t, cap_s, t0=None, crit=Criteria):
    """Judge one episode from eval-only rows.

    rows: whole episode (grasp included), time ordered. lower_start_t: sim time at which the
    commanded set-down began (from the carry teacher's phase events; the pair evaluator's boundary
    between "carry" and "set-down" too) or None. cap_s: REQUIRED, no default (open pin).
    """
    rows = sorted(rows, key=lambda r: float(r['t']))
    if not rows:
        return {'schema': SCHEMA, 'status': STATUS, 'success': False, 'failure': 'no_rows', 'gates': {}}
    t0 = float(rows[0]['t']) if t0 is None else float(t0)
    lift = lift_gate(rows, rid, crit)
    no_drop = drop_gate(rows, lift, lower_start_t, crit)
    slot_g = slot_gate(rows, slot, crit)
    rest = rest_gate(rows, rid, crit)
    release = release_gate(rows, rid, lower_start_t, crit)
    completion = completion_gate(release, rest, t0, cap_s, crit)
    gates = {'lift': lift, 'no_drop': no_drop, 'slot': slot_g, 'rest': rest, 'release': release,
             'completion': completion}
    failure = next((g for g in GATES if not gates[g]['pass']), None)
    return {'schema': SCHEMA, 'status': STATUS, 'success': failure is None, 'failure': failure, 'gates': gates,
            'lower_start_t': lower_start_t, 'cap_s': cap_s, 't0': t0,
            'criteria': {k: v for k, v in vars(crit).items() if not k.startswith('_')}}
