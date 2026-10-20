"""Eval-only minimal-E2E success, auxiliary metrics and raw recount.

Pre-registered success (experiments/2026-10-21-e2e-min/PREREG_DRAFT.md §4),
one boolean per run:

    success = allocation ok (L1-lite record success-eligible, distinct slots)
              and GT: each robot's cube final xy inside that robot's assigned
                  slot zone (left = north half, right = south half of zone B)
              and carry drops == 0 (both robots measured, both False)
              and robot-robot contact == 0 (channel available)
              and own arrival claim 2/2

Unmeasured is never zero: a missing GT, an unavailable contact channel, an
unmeasured drop or a missing allocation keeps ``success`` false and says so.

Auxiliary: per-stage reach (allocate/grasp/carry/release/done), stage times,
fail codes, LLM calls/tokens/cost, substitutions and the level label.

Nothing here is a controller input.  ``recount_run`` reads raw artifacts only
and writes nothing.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from harness.e2e_min_handoff import (LEVELS, NAV_CARRY, ROBOTS, SLOTS, STAGE_OF,
                                     substitutions as level_substitutions)
from harness.e2ewarp_l1lite_eval import ZONE_B, estimate_cost_usd, in_rect, slot_zone

SCHEMA = 'ugrp.e2e_min.evaluation.v1'
STAGES = ('allocate', 'grasp', 'carry', 'release', 'done')
#: Drop thresholds (eval-only, frozen by the prereg; values [확인 필요] against
#: a teacher carry trace before E2E-0 is admitted).
DROP_DEFAULTS = dict(floor_clear_m=0.005, detach_m=0.35, min_ticks=5, finger_n=0.1)


def carry_drop(cube_z, cube_xy, base_xy, *, cube_half_m, finger_max_n=None,
               floor_clear_m=DROP_DEFAULTS['floor_clear_m'],
               detach_m=DROP_DEFAULTS['detach_m'], min_ticks=DROP_DEFAULTS['min_ticks'],
               finger_n=DROP_DEFAULTS['finger_n']):
    """Detect a dropped cube during the carry window (GT, eval-only).

    Inputs are the per-tick series *restricted to the NAV_CARRY window*.  A drop
    is any of, held for ``min_ticks`` consecutive ticks:

    * ``floor``: cube bottom clearance (z - half size) <= ``floor_clear_m``
      (the cube rests on the floor instead of being held up);
    * ``detach``: horizontal cube-to-base-centre distance > ``detach_m``
      (the cube is no longer travelling with the robot);
    * ``no_grip`` (only when finger forces are given): max finger force
      < ``finger_n`` (same 0.1 N threshold as grasp_act_rollout.py:134-135).

    Returns ``dropped`` None when the window is empty or series lengths differ.
    """
    n = len(cube_z)
    if n == 0 or len(cube_xy) != n or len(base_xy) != n or (
            finger_max_n is not None and len(finger_max_n) != n):
        return dict(dropped=None, reason='not_measured', first_index=None, ticks=n)
    flags = {'floor': [], 'detach': [], 'no_grip': []}
    for i in range(n):
        clearance = float(cube_z[i]) - float(cube_half_m)
        dx = float(cube_xy[i][0]) - float(base_xy[i][0])
        dy = float(cube_xy[i][1]) - float(base_xy[i][1])
        flags['floor'].append(clearance <= floor_clear_m)
        flags['detach'].append((dx * dx + dy * dy) ** 0.5 > detach_m)
        flags['no_grip'].append(finger_max_n is not None and float(finger_max_n[i]) < finger_n)
    first = None
    for reason in ('floor', 'detach', 'no_grip'):
        run = 0
        for i, hit in enumerate(flags[reason]):
            run = run + 1 if hit else 0
            if run >= min_ticks:
                start = i - min_ticks + 1
                if first is None or start < first[1]:
                    first = (reason, start)
                break
    if first is None:
        return dict(dropped=False, reason=None, first_index=None, ticks=n)
    return dict(dropped=True, reason=first[0], first_index=first[1], ticks=n)


def stage_reach(handoff):
    """Per-robot stage reach from a handoff export (E2EMinEpisode.export())."""
    out = {}
    for robot in ROBOTS:
        row = ((handoff or {}).get('robots') or {}).get(robot) or {}
        reached = {STAGE_OF[p]: t for p, t in (row.get('reach') or {}).items() if p in STAGE_OF}
        out[robot] = dict(reached={s: s in reached for s in STAGES},
                          sim_s={s: reached.get(s) for s in STAGES},
                          final_phase=row.get('phase'), fail_code=row.get('fail_code'))
    return out


def evaluate(*, level, allocation, slots, cube_final_xy, drops, claims, zone=None,
             contacts_available, robot_robot_contacts, handoff=None, usage=None,
             sim_s=None, substitutions=None):
    """One run's pre-registered success and auxiliary metrics (pure function)."""
    if level not in LEVELS:
        raise ValueError('unknown E2E level: ' + str(level))
    zone = copy.deepcopy(zone or ZONE_B)
    alloc = allocation if isinstance(allocation, dict) else {}
    decisions = alloc.get('decisions') or {}
    allocation_ok = bool(alloc) and alloc.get('fatal') is not True \
        and alloc.get('success_eligible') is True
    slots_ok = (isinstance(slots, dict) and set(slots) == set(ROBOTS)
                and sorted(slots.values()) == sorted(SLOTS)
                and all(decisions.get(r) == slots[r] for r in ROBOTS))
    rows = {}
    for robot in ROBOTS:
        slot = (slots or {}).get(robot)
        rect = slot_zone(zone, slot) if slot in SLOTS else None
        xy = (cube_final_xy or {}).get(robot)
        drop = (drops or {}).get(robot)
        rows[robot] = dict(slot=slot, slot_zone=rect,
                           cube_final_xy=None if xy is None else [round(float(v), 4) for v in xy],
                           cube_in_slot_gt=bool(rect is not None and xy is not None and in_rect(xy, rect)),
                           drop_measured=isinstance(drop, bool), dropped=drop,
                           claim=(claims or {}).get(robot) is True)
    gt_measured = all(rows[r]['cube_final_xy'] is not None for r in ROBOTS)
    cubes_ok = gt_measured and all(rows[r]['cube_in_slot_gt'] for r in ROBOTS)
    drops_measured = all(rows[r]['drop_measured'] for r in ROBOTS)
    drops_zero = drops_measured and not any(rows[r]['dropped'] for r in ROBOTS)
    contact_ok = bool(contacts_available is True and int(robot_robot_contacts) == 0)
    claims_ok = all(rows[r]['claim'] for r in ROBOTS)
    success = bool(allocation_ok and slots_ok and cubes_ok and drops_zero and contact_ok
                   and claims_ok)
    expected_subs = level_substitutions(level)
    subs = list(substitutions) if substitutions is not None else expected_subs
    reach = stage_reach(handoff)
    stage_counts = {s: sum(1 for r in ROBOTS if reach[r]['reached'][s]) for s in STAGES}
    return dict(
        schema=SCHEMA, level=level, label=LEVELS[level]['label'], eval_only=True,
        research_result=(level == 'E2E-2'), no_pooling=True, success=success,
        success_components=dict(
            allocation_ok=allocation_ok, slots_match_allocation=slots_ok,
            gt_measured=gt_measured, cubes_in_assigned_slots=cubes_ok,
            drops_measured=drops_measured, drops_zero=drops_zero,
            contacts_available=contacts_available is True,
            robot_robot_contacts=int(robot_robot_contacts), robot_contact_zero=contact_ok,
            claims_2_of_2=claims_ok),
        robots=rows,
        e2e_substitutions=subs,
        substitutions_match_level=(subs == expected_subs),
        aux=dict(stage_reach=reach, stage_reach_counts=stage_counts,
                 sim_s=None if sim_s is None else round(float(sim_s), 3),
                 llm=estimate_cost_usd(usage),
                 constraint_ok=alloc.get('constraint_ok')),
        scope='eval-only minimal E2E; substituted steps listed in e2e_substitutions',
    )


def _window(transitions, robot):
    enter = leave = None
    for row in transitions or ():
        if row.get('robot') != robot:
            continue
        if row.get('to') == NAV_CARRY and enter is None:
            enter = float(row['sim_s'])
        elif row.get('from') == NAV_CARRY and enter is not None and leave is None:
            leave = float(row['sim_s'])
    return enter, leave


def _read(path, default):
    path = Path(path)
    return json.loads(path.read_text()) if path.is_file() else default


def recount_run(run_dir, *, zone=None, drop_params=None):
    """Raw recount of one E2E run directory (writes nothing).

    Reads ``queue.json`` (e2e markers), ``slot-decisions.json``,
    ``e2e-handoff.json`` (E2EMinEpisode.export()), ``world-00/eval-geometry.json``
    (robot_qpos_adr, cube_qpos_adr, cube_half_m, destination),
    ``evaluation-state.npz`` (10 Hz qpos, tick k at SIM k/10 s),
    ``nav-events.json``, ``contact-ledger.json``, ``llm_ledger.json``.
    """
    import numpy as np
    run = Path(run_dir)
    queue = _read(run / 'queue.json', {})
    level = queue.get('e2e_level')
    allocation = _read(run / 'slot-decisions.json', {})
    handoff = _read(run / 'e2e-handoff.json', {})
    geometry = _read(run / 'world-00' / 'eval-geometry.json', {})
    destination = zone or geometry.get('destination') or ZONE_B
    slots = (handoff.get('slots') if handoff else None) or allocation.get('decisions')
    claims = {}
    events = _read(run / 'nav-events.json', {})
    for robot in ROBOTS:
        claims[robot] = any(r.get('after') == 'ARRIVED' for r in events.get(f'0:{robot}') or ())
    ledger = _read(run / 'contact-ledger.json', {})
    usage = _read(run / 'llm_ledger.json', [])
    cube_final, drops, drop_detail = {}, {}, {}
    state_path = run / 'evaluation-state.npz'
    robot_adr = {str(k): int(v) for k, v in (geometry.get('robot_qpos_adr') or {}).items()}
    cube_adr = {str(k): int(v) for k, v in (geometry.get('cube_qpos_adr') or {}).items()}
    half = geometry.get('cube_half_m')
    if state_path.is_file() and robot_adr and cube_adr and half is not None:
        qpos = np.asarray(np.load(state_path)['qpos'])[:, 0, :]
        transitions = []
        for row in (handoff.get('robots') or {}).values():
            transitions.extend(row.get('transitions') or ())
        for robot in ROBOTS:
            if robot not in cube_adr or robot not in robot_adr:
                continue
            c, b = cube_adr[robot], robot_adr[robot]
            cube_final[robot] = [float(qpos[-1, c]), float(qpos[-1, c + 1])]
            enter, leave = _window(transitions, robot)
            if enter is None:
                drop_detail[robot] = dict(dropped=None, reason='no_carry_window')
                continue
            i0 = int(round(enter * 10))
            i1 = len(qpos) if leave is None else int(round(leave * 10)) + 1
            seg = qpos[i0:i1]
            detail = carry_drop(seg[:, c + 2], seg[:, c:c + 2], seg[:, b:b + 2],
                                cube_half_m=float(half), **(drop_params or {}))
            drop_detail[robot] = detail
            if isinstance(detail['dropped'], bool):
                drops[robot] = detail['dropped']
    report = evaluate(level=level, allocation=allocation, slots=slots,
                      cube_final_xy=cube_final, drops=drops, claims=claims, zone=destination,
                      contacts_available=ledger.get('contacts_available') is True,
                      robot_robot_contacts=int(ledger.get('contact_pairs_total') or 0),
                      handoff=handoff, usage=usage,
                      substitutions=queue.get('e2e_substitutions'))
    report['drop_detail'] = drop_detail
    report['recount_inputs'] = dict(run=str(run), state=state_path.is_file(),
                                    cube_geometry=bool(cube_adr and half is not None))
    return report


def aggregate(reports):
    """n/N per level; never pools across levels."""
    out = {}
    for rep in reports:
        row = out.setdefault(rep['level'], dict(n=0, N=0, fail_codes={}))
        row['N'] += 1
        row['n'] += int(rep['success'] is True)
        for robot in ROBOTS:
            code = rep['aux']['stage_reach'][robot]['fail_code']
            if code:
                row['fail_codes'][code] = row['fail_codes'].get(code, 0) + 1
    return out
