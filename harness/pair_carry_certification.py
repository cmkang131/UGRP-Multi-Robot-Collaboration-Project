"""Opt-in transport evidence precheck; legacy verdicts remain untouched.

Version 1 never certifies transport: ground-frame, release-duration and physical
continuity criteria are unregistered. It distinguishes contradicted evidence
from unknown evidence instead of promoting the existing strict diagnostic.
"""
import copy
import hashlib
import json
import math

SCHEMA = 'ugrp.transport_evidence.v1'
KINDS = {'SYNTHETIC_COUNTEREXAMPLE_NOT_REAL_RUN', 'ORIGINAL_MUTATION', 'REAL_ORIGINAL'}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def certify(rows, static_map, roles, *, evaluator, geometry, handover_t=None,
            lower_start_t=None, registration=None, parent_ids=None,
            input_kind=None, stored_result=None, opt_in=False):
    """Return a separate evidence report, or an unchanged copy of stored_result.

    evaluator/geometry must be the caller's explicitly selected source modules.
    This API evaluates recorded GT only; it is never a policy input or gate.
    Source selection and parent labels do not authenticate a physical run.
    """
    if type(opt_in) is not bool:
        raise ValueError('opt_in must be a boolean')
    if not opt_in:
        return copy.deepcopy(stored_result if stored_result is not None else {})
    axes = {k: {'status': 'unknown', 'reason': 'evidence not established'} for k in 'ABCDEFG'}
    out = {'schema': SCHEMA, 'verdict': 'unknown', 'axes': axes,
           'input_kind': input_kind, 'registration': copy.deepcopy(registration),
           'parent_ids': copy.deepcopy(parent_ids), 'legacy_result': copy.deepcopy(stored_result),
           'student_success_count': None, 'environment_applied': 'unknown',
           'transmission_acknowledged': 'unknown', 'motion_observed': 'unknown'}

    def set_axis(k, status, reason, **evidence):
        axes[k] = {'status': status, 'reason': reason, **evidence}

    try:
        rows, static_map, roles = copy.deepcopy((list(rows), static_map, list(roles)))
        if not roles or len(set(roles)) != len(roles) or 'beam' in roles:
            raise ValueError('unique robot roles are required')
        if input_kind not in KINDS:
            raise ValueError('explicit input_kind required')
        last = None
        for row in rows:
            t = row['t']
            if not _finite(t) or (last is not None and t <= last):
                raise ValueError('finite strictly increasing timestamps required')
            last = t
            for pose in [row['beam']['pose']] + [row['robots'][r]['pose'] for r in roles]:
                if len(pose) < 3 or not all(_finite(v) for v in pose):
                    raise ValueError('finite poses required')
            if not _finite(row['beam']['min_z']) or not _finite(row['beam']['tilt_deg']):
                raise ValueError('finite height and tilt required')
            for r in roles:
                force = row['contacts'][r]
                if len(force) != 2 or not all(_finite(v) for v in force):
                    raise ValueError('two finite jaw forces per robot required')
        if handover_t is not None and not _finite(handover_t):
            raise ValueError('finite handover boundary required')
        if lower_start_t is not None and not _finite(lower_start_t):
            raise ValueError('finite lower boundary required')
        out['raw_rows_sha256'] = _hash(rows)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        set_axis('C', 'refused', str(exc))
        out['verdict'] = 'refused'
        return out
    registered = (isinstance(registration, dict) and all(
        isinstance(registration.get(k), str) and registration[k].strip() for k in ('cohort_id', 'version')))
    parents = isinstance(parent_ids, list) and bool(parent_ids) and all(
        isinstance(x, str) and x.strip() for x in parent_ids)
    set_axis('C', 'supported' if registered and parents and handover_t is not None else 'unknown',
             'window is t > handover_t; parent ids are labels, not authentication',
             window_rule='t > handover_t', registration_complete=registered, parents_complete=parents)
    # No implicit boundary is substituted when the saved runner rule is absent.
    window = [r for r in rows if r['t'] > handover_t] if handover_t is not None else []
    carry = [r for r in window if lower_start_t is None or r['t'] < lower_start_t]
    if len(carry) >= 2:
        try:
            door = geometry.door_of(static_map)
            if not all(_finite(door[k]) for k in ('x', 'cy', 'half_y')) or door['half_y'] <= 0:
                raise ValueError('finite door plane and positive aperture required')
        except (KeyError, StopIteration, NotImplementedError, TypeError, ValueError) as exc:
            set_axis('A', 'refused', 'door geometry unavailable: ' + str(exc))
            out['verdict'] = 'refused'
            return out
        crossing = {}
        for entity in ['beam'] + roles:
            def pose(row):
                return row['beam']['pose'] if entity == 'beam' else row['robots'][entity]['pose']
            events = []
            for a, b in zip(carry, carry[1:]):
                pa, pb = pose(a), pose(b)
                if pa[0] < door['x'] <= pb[0]:
                    f = (door['x'] - pa[0]) / (pb[0] - pa[0])
                    y = pa[1] + f * (pb[1] - pa[1])
                    events.append({'before': a['t'], 'after': b['t'],
                                   'in_aperture': abs(y - door['cy']) <= door['half_y']})
            crossing[entity] = {'starts_west': pose(carry[0])[0] < door['x'], 'events': events}
        crossed = all(v['starts_west'] and v['events'] and all(e['in_aperture'] for e in v['events'])
                      for v in crossing.values())
        set_axis('A', 'supported' if crossed else 'refused', 'sampled forward crossings', entities=crossing)
        force_counts = {r: sum(min(row['contacts'][r]) >= geometry.HOLD_MIN_FORCE for row in carry) for r in roles}
        held = all(n == len(carry) for n in force_counts.values())
        set_axis('B', 'supported' if held else 'refused', 'bilateral force over entire sampled carry window',
                 force_rows=force_counts, carry_rows=len(carry))
    if window:
        distances = [math.dist(window[0]['beam']['pose'][:2], r['beam']['pose'][:2]) for r in window]
        moving_intervals = sum(a['beam']['pose'][:2] != b['beam']['pose'][:2] for a, b in zip(window, window[1:]))
        enough = max(distances) >= evaluator.Criteria.carried_min_m and moving_intervals >= 2
        set_axis('D', 'unknown' if enough else 'refused', 'physical continuity bound unregistered' if enough else 'insufficient or single-interval movement',
                 carried_max_m=max(distances), moving_intervals=moving_intervals)
        try:
            recomputed = evaluator.evaluate(copy.deepcopy(window), static_map, roles,
                                             lower_start_t=lower_start_t, handover_t=handover_t)
        except (KeyError, StopIteration, NotImplementedError, TypeError, ValueError) as exc:
            set_axis('E', 'refused', 'legacy recomputation unavailable: ' + str(exc))
            out['verdict'] = 'refused'
            return out
        out['recomputed_legacy_result'] = recomputed
        boundary_mismatch = isinstance(stored_result, dict) and any(
            key in stored_result and stored_result[key] != expected
            for key, expected in (('handover_t', handover_t), ('lower_start_t', lower_start_t)))
        internal_contradiction = isinstance(stored_result, dict) and stored_result.get('success') is True and (
            stored_result.get('placed_in_zone') is False or bool(stored_result.get('drop_events'))
            or bool(stored_result.get('robot_robot_contact_ticks'))
            or any(value is False for value in (stored_result.get('funnel') or {}).values()))
        contradiction = internal_contradiction
        if stored_result is not None and not boundary_mismatch:
            for key in ('success', 'placed_in_zone', 'drop_events', 'robot_robot_contact_ticks', 'funnel'):
                if key in stored_result and stored_result[key] != recomputed.get(key):
                    contradiction = True
        set_axis('E', 'refused' if contradiction or (not boundary_mismatch and not recomputed.get('success')) else 'unknown',
                 'saved result contradicts raw-row recomputation' if contradiction else
                 'saved result uses different window boundaries; cross-report comparison deferred' if boundary_mismatch else
                 'legacy result recomputed; wall policy unregistered', boundary_mismatch=boundary_mismatch)
    set_axis('F', 'unknown', 'ground reference and negative-height interpretation unregistered')
    set_axis('G', 'unknown', 'release duration unregistered; no invented time threshold')
    out['verdict'] = 'refused' if any(v['status'] == 'refused' for v in axes.values()) else 'unknown'
    return out
