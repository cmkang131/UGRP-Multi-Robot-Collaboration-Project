"""Eval-only L1-lite success and auxiliary metrics (no controller, no run).

Main metric (plan §3 item 4), one boolean per run and one row per robot:

    success = both robots' GT base xy inside their own chosen slot zone
              and own-input ARRIVED claim 2/2
              and the two chosen slots are different
              and each robot's private constraint is respected
              and robot-robot contact is 0

Every component is reported separately, so a run that fails one component is
never summarised as a success.  Unmeasured is not zero: a missing GT, an
unavailable contact channel, a missing constraint map or a missing allocation
record all keep ``success`` false and say so.

Auxiliary metrics: completion SIM time, minimum base-centre distance, a
conservative minimum body-gap lower bound, LLM calls/tokens/cost, utterance
count, hallucinated slot/constraint mentions, and the 60 SIM s deadlock check.

Nothing in this module is a controller input.  ``evaluate_run`` reads only raw
run artifacts (``slot-decisions.json``, ``world-00/eval-geometry.json``,
``evaluation-state.npz``, ``nav-events.json``, ``contact-ledger.json``,
``llm_ledger.json``, ``messages.json``, ``result.json``) and writes no run
state; a caller writes the returned report to a separate evaluation file.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

from harness.e2ewarp_l1lite import (DEADLOCK_SIM_S, PLANNER_PRICE_USD_PER_MILLION,
                                    ROBOTS, SLOTS, VERSION)

SCHEMA = 'ugrp.e2ewarp.l1lite_evaluation.v1'
#: Authored zone B rectangle from ``maps/zones_final_v3/zone_wide_two_doors_final_v3.json``
#: (``regions.zone_B``: centre [4.6, -2.1], half extents [0.3, 0.7]).  The run's
#: eval-only ``world-00/eval-geometry.json`` is preferred; this constant is the
#: declared fallback used only when a synthetic fixture supplies no geometry.
ZONE_B = dict(map_id='zone_wide_two_doors_final_v3', region='zone_B',
              center_m=[4.6, -2.1], half_extents_m=[0.3, 0.7])
_SLOT_WORDS = {'left', 'right'}


def slot_zone(zone, slot):
    """The left/north or right/south half of the zone rectangle.

    Facing +x (east), robot-left is +y (north): the ``left`` slot is the north
    half, the ``right`` slot the south half.  This is the same derivation as the
    authored lane/slot mapping (r1 north lane -> left, r2 south lane -> right).
    """
    center = [float(v) for v in zone['center_m']]
    half = [float(v) for v in zone['half_extents_m']]
    if slot not in SLOTS:
        raise ValueError('unknown slot: ' + str(slot))
    if slot == 'left':
        return dict(center_m=[center[0], center[1] + half[1] / 2.0],
                    half_extents_m=[half[0], half[1] / 2.0])
    return dict(center_m=[center[0], center[1] - half[1] / 2.0],
                half_extents_m=[half[0], half[1] / 2.0])


def in_rect(xy, rect):
    if xy is None or rect is None:
        return False
    return bool(abs(float(xy[0]) - float(rect['center_m'][0])) <= float(rect['half_extents_m'][0])
                and abs(float(xy[1]) - float(rect['center_m'][1])) <= float(rect['half_extents_m'][1]))


def estimate_cost_usd(usage_rows):
    """USD from recorded usage rows at the pinned CoreWeave fp4 prices.

    The price is per 1M tokens (``configs/model_endpoints.json``, recorded
    2026-10-16).  A row without a usage mapping contributes 0 tokens; the
    report keeps ``usage_missing`` so absent usage is never reported as free.
    """
    prompt = completion = 0
    missing = 0
    for row in usage_rows or ():
        usage = (row or {}).get('usage') or {}
        if not usage:
            missing += 1
        prompt += int(usage.get('prompt_tokens') or 0)
        completion += int(usage.get('completion_tokens') or 0)
    cost = (prompt * PLANNER_PRICE_USD_PER_MILLION['prompt']
            + completion * PLANNER_PRICE_USD_PER_MILLION['completion']) / 1_000_000.0
    return dict(calls=len(usage_rows or ()), prompt_tokens=prompt,
                completion_tokens=completion, total_tokens=prompt + completion,
                cost_usd=round(cost, 12), usage_missing=missing)


def hallucination_report(messages, constraints):
    """Deterministic hallucinations: false private-constraint claims, bad slots.

    Only *transport-valid* messages are scanned (the channel rejects malformed
    ones).  Structured ``my_constraint`` claims are compared with the sender's
    true private constraint; free prose references to a slot that does not
    exist (``B-center``, ``slot middle``, ``B2``...) are counted.  This is a
    conservative lexical check, not a semantic judge.
    """
    items = []
    for row in messages or ():
        sender = str((row or {}).get('sender'))
        body = (row or {}).get('body')
        if not isinstance(body, dict):
            continue
        sim_s = (row or {}).get('sim_s')
        if body.get('act') == 'my_constraint':
            true_slot = (constraints or {}).get(sender)
            if true_slot is None or body.get('slot') != true_slot:
                items.append(dict(kind='false_constraint_claim', robot=sender,
                                  sim_s=sim_s, claimed=body.get('slot'),
                                  true_constraint=true_slot))
            continue
        text = body.get('text')
        if not isinstance(text, str):
            continue
        for match in re.finditer(r'\bB[-\s_]?([A-Za-z0-9_]+)', text):
            token = match.group(1).lower()
            if token not in _SLOT_WORDS:
                items.append(dict(kind='unknown_slot_mention', robot=sender,
                                  sim_s=sim_s, evidence=match.group(0)))
        for match in re.finditer(r'\b(?:slot|zone)[\s_-]+([A-Za-z0-9_-]+)', text,
                                  re.IGNORECASE):
            token = match.group(1).lower()
            if token not in _SLOT_WORDS and token not in ('b', 'zone_b'):
                items.append(dict(kind='unknown_slot_mention', robot=sender,
                                  sim_s=sim_s, evidence=match.group(0)))
    return dict(count=len(items), items=items[:50])


def _robot_rows(slots, constraints, final_gt, claims, zone):
    rows = {}
    for robot in ROBOTS:
        slot = (slots or {}).get(robot)
        valid = slot in SLOTS
        rect = slot_zone(zone, slot) if valid else None
        gt = (final_gt or {}).get(robot)
        inside = bool(valid and gt is not None and in_rect(gt, rect))
        constraint = (constraints or {}).get(robot)
        constraint_ok = (None if robot not in (constraints or {})
                         else (constraint is None or (valid and slot == constraint)))
        rows[robot] = dict(
            chosen_slot=slot, constraint=constraint,
            slot_zone=rect, gt_xy=(None if gt is None else [round(float(v), 4) for v in gt]),
            inside_chosen_slot_gt=inside,
            own_arrival_claim=bool((claims or {}).get(robot) is True),
            constraint_ok=constraint_ok)
    return rows


def evaluate(*, slots, constraints, final_gt, claims, zone,
             contacts_available, robot_robot_contacts,
             claim_sim_s=None, sim_s=None, allocation=None, usage=None,
             utterances=None, min_center_distance_m=None,
             min_body_gap_m=None, messages=None):
    """One L1-lite run's main metric and auxiliary metrics (pure function).

    ``allocation`` is the ``slot-decisions.json`` record (or an equivalent
    mapping).  ``None`` means "no allocation record" and keeps ``success``
    false.  ``contacts_available is True and robot_robot_contacts == 0`` is the
    only passing contact state; an unavailable channel is not zero contact.
    """
    rows = _robot_rows(slots, constraints, final_gt, claims, zone)
    allocation = allocation or {}
    allocation_errors = [str(e) for e in (allocation.get('errors') or ())]
    allocation_ok = bool(allocation) and allocation.get('fatal') is not True \
        and allocation.get('success_eligible') is True
    slots_measured = isinstance(slots, dict) and set(slots) == set(ROBOTS)
    constraints_measured = isinstance(constraints, dict) and set(constraints) == set(ROBOTS)
    gt_measured = isinstance(final_gt, dict) and all(
        final_gt.get(r) is not None for r in ROBOTS)
    claims_measured = isinstance(claims, dict) and all(r in claims for r in ROBOTS)
    distinct = bool(slots_measured and len(set(slots.values())) == 2
                    and set(slots.values()) == set(SLOTS))
    claims_ok = bool(claims_measured and all(claims.get(r) is True for r in ROBOTS))
    constraint_ok = bool(constraints_measured
                         and all(rows[r]['constraint_ok'] is True for r in ROBOTS))
    contact_ok = bool(contacts_available is True and int(robot_robot_contacts) == 0)
    arrival_ok = bool(gt_measured and all(rows[r]['inside_chosen_slot_gt'] for r in ROBOTS))
    success = bool(allocation_ok and slots_measured and distinct and arrival_ok
                   and claims_ok and constraint_ok and contact_ok)
    constraint_violations = [r for r in ROBOTS if rows[r]['constraint_ok'] is False]
    completion = None
    if claim_sim_s and claims_ok:
        completion = round(max(float(claim_sim_s.get(r, 0.0)) for r in ROBOTS), 3)
    elif claims_ok and sim_s is not None:
        completion = round(float(sim_s), 3)
    deadlock = bool(allocation.get('deadlock') is True
                    or (sim_s is not None and float(sim_s) >= DEADLOCK_SIM_S
                        and not claims_ok))
    llm = estimate_cost_usd(usage)
    hallucination = hallucination_report(messages if messages is not None
                                         else allocation.get('messages'), constraints)
    components = dict(
        allocation_ok=allocation_ok, allocation_errors=allocation_errors,
        slots_measured=slots_measured, distinct_slots=distinct,
        constraints_measured=constraints_measured, constraint_ok=constraint_ok,
        gt_measured=gt_measured, arrival_in_chosen_slot=arrival_ok,
        claims_measured=claims_measured, claims_2_of_2=claims_ok,
        contacts_available=contacts_available is True,
        robot_robot_contacts=int(robot_robot_contacts),
        robot_contact_zero=contact_ok,
    )
    return dict(
        schema=SCHEMA, version=VERSION, eval_only=True, no_pooling=True,
        research_result=False, success=success,
        success_components=components,
        robots=rows,
        constraint_violations=constraint_violations,
        aux=dict(
            completion_sim_s=completion, sim_s=None if sim_s is None else round(float(sim_s), 3),
            min_center_distance_m=(None if min_center_distance_m is None
                                   else round(float(min_center_distance_m), 4)),
            min_body_gap_m=(None if min_body_gap_m is None
                            else round(float(min_body_gap_m), 4)),
            body_gap_method=('rotated-base-box support-radius lower bound'
                             if min_body_gap_m is not None else 'not_measured'),
            utterances=(int(utterances) if utterances is not None
                        else int(allocation.get('utterances') or 0)),
            deadlock_60s=deadlock,
            hallucination=hallucination,
            llm=llm,
        ),
        scope=('eval-only L1-lite (move+allocation, picking/placing excluded); '
               'own-input ARRIVED claim is not physical success'),
    )


def _tracks(qpos, geometry):
    """Per-robot xy tracks and yaw from raw qpos (eval-only)."""
    import numpy as np
    adr = {str(r): int(v) for r, v in (geometry.get('robot_qpos_adr') or {}).items()}
    if not adr:
        raise ValueError('eval-geometry has no robot_qpos_adr')
    tracks = {}
    for robot, start in adr.items():
        track = np.asarray(qpos)[:, 0, start:start + 7]
        if track.ndim != 2 or track.shape[1] < 7:
            raise ValueError('evaluation-state qpos does not hold robot poses')
        xy = track[:, :2]
        qw, qx, qy, qz = track[:, 3], track[:, 4], track[:, 5], track[:, 6]
        yaw = np.arctan2(2.0 * (qw * qz + qx * qy),
                         1.0 - 2.0 * (qy * qy + qz * qz))
        tracks[robot] = dict(xy=xy, yaw=yaw)
    return tracks


def _distances(tracks, base_boxes=None):
    import numpy as np
    if set(tracks) != set(ROBOTS):
        return None, None
    a, b = ROBOTS
    if not len(tracks[a]['xy']) or len(tracks[a]['xy']) != len(tracks[b]['xy']):
        return None, None
    delta = tracks[a]['xy'] - tracks[b]['xy']
    centers = np.linalg.norm(delta, axis=1)
    min_center = float(centers.min())
    min_gap = None
    boxes = (base_boxes or {})
    if all(r in boxes and boxes[r] for r in ROBOTS):
        gaps = []
        for robot in ROBOTS:
            size = [float(v) for v in (boxes[robot].get('size') or ())]
            local = [float(v) for v in (boxes[robot].get('local_pos') or (0.0, 0.0, 0.0))]
            if len(size) < 2:
                return min_center, None
            yaw = tracks[robot]['yaw']
            c, s = np.cos(yaw), np.sin(yaw)
            wx = tracks[robot]['xy'][:, 0] + c * local[0] - s * local[1]
            wy = tracks[robot]['xy'][:, 1] + s * local[0] + c * local[1]
            radius = np.abs(c) * size[0] + np.abs(s) * size[1]
            tracks[robot]['_wx'], tracks[robot]['_wy'] = wx, wy
            tracks[robot]['_r'] = radius
        dx = tracks[a]['_wx'] - tracks[b]['_wx']
        dy = tracks[a]['_wy'] - tracks[b]['_wy']
        gap = np.hypot(dx, dy) - tracks[a]['_r'] - tracks[b]['_r']
        min_gap = float(gap.min())
    return min_center, min_gap


def evaluate_run(run_dir, *, zone=None):
    """Recount one raw L1-lite run directory (writes nothing, returns a report)."""
    run = Path(run_dir)
    result = json.loads((run / 'result.json').read_text()) if (run / 'result.json').is_file() else {}
    record = json.loads((run / 'slot-decisions.json').read_text()) \
        if (run / 'slot-decisions.json').is_file() else {}
    geometry = {}
    geometry_path = run / 'world-00' / 'eval-geometry.json'
    if geometry_path.is_file():
        geometry = json.loads(geometry_path.read_text())
    destination = (zone or geometry.get('destination') or copy.deepcopy(ZONE_B))
    if 'center_m' not in destination:
        destination = copy.deepcopy(ZONE_B)
    claims, claim_sim_s = {}, {}
    events_path = run / 'nav-events.json'
    if events_path.is_file():
        events = json.loads(events_path.read_text())
        for robot in ROBOTS:
            rows = events.get(f'0:{robot}') or []
            hit = next((row for row in rows if row.get('after') == 'ARRIVED'), None)
            claims[robot] = hit is not None
            if hit is not None:
                claim_sim_s[robot] = hit.get('sim_s')
    contacts_available, robot_contacts = False, 0
    ledger_path = run / 'contact-ledger.json'
    base_boxes = {}
    if ledger_path.is_file():
        ledger = json.loads(ledger_path.read_text())
        contacts_available = ledger.get('contacts_available') is True
        robot_contacts = int(ledger.get('contact_pairs_total') or 0)
        base_boxes = ledger.get('base_boxes') or {}
    usage = []
    ledger_rows = run / 'llm_ledger.json'
    if ledger_rows.is_file():
        usage = json.loads(ledger_rows.read_text())
    messages = []
    messages_path = run / 'messages.json'
    if messages_path.is_file():
        for world in json.loads(messages_path.read_text()):
            messages.extend(world.get('events') or [])
    final_gt, min_center, min_gap = {}, None, None
    state_path = run / 'evaluation-state.npz'
    if state_path.is_file() and geometry:
        import numpy as np
        state = np.load(state_path)
        tracks = _tracks(np.asarray(state['qpos']), geometry)
        final_gt = {r: [float(v) for v in tracks[r]['xy'][-1]] for r in tracks}
        min_center, min_gap = _distances(tracks, base_boxes)
    report = evaluate(
        slots=record.get('decisions') or {}, constraints=record.get('constraints') or {},
        final_gt=final_gt, claims=claims, zone=destination,
        contacts_available=contacts_available, robot_robot_contacts=robot_contacts,
        claim_sim_s=claim_sim_s, sim_s=result.get('sim_s'), allocation=record,
        usage=usage, min_center_distance_m=min_center, min_body_gap_m=min_gap,
        messages=messages)
    inputs = {}
    for name in ('result.json', 'slot-decisions.json', 'nav-events.json',
                 'contact-ledger.json', 'llm_ledger.json', 'messages.json',
                 'evaluation-state.npz', 'world-00/eval-geometry.json'):
        path = run / name
        inputs[name] = (hashlib.sha256(path.read_bytes()).hexdigest()
                        if path.is_file() else None)
    report.update(run=str(run.resolve()), source_sha=result.get('source_sha'),
                  status=result.get('status'), inputs=inputs,
                  note=('recount works from raw state only; it never re-enters the run '
                        'and is not an E2E or physical-success claim'))
    return report
