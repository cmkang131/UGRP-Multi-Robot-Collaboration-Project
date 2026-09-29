"""Chain probe for the own-camera pair-carry controller (issue #221): grasp+lift done -> carry legs 0..7 -> destination set-down
in ONE controller run, with no teacher re-staging between the legs (opt-in stage ``chain`` of the stage probe).

Why: the stage probe (``harness.pair_stage_probe``) starts every carry leg from a fresh teacher staging, so it never sees the
error that one leg leaves for the next (open-loop odometry, beam pose after each lower/open/re-grasp, the localizer and its fix
clock). Here the teacher stages ONCE (the same teacher-lifted beam as the ``carry`` stage, leg 0) and then the registered
controller runs the whole route by itself: carry -> lower -> open -> checkpoint relocalization -> re-grasp -> lift -> next leg
... -> set-down. The probe only RECORDS, per robot and per controller tick: the state timeline, the own PoseReport at each leg
boundary and (eval only) the ground-truth beam / robot pose at the leg boundaries.

Boundary (AGENTS.md): this module imports no simulator. Ground truth is read by the eval-only observer of the runner and lands only
in the records written here; the controller never receives it. Nothing here writes to or steers the controller: the tick
wrapper is a pass-through that returns the original tick's result unchanged.

A chain result is a stage-probe result (development map, teacher-staged first lift, tags may give the first fix), not an E2E
success and not a student success.
"""
from __future__ import annotations

import math
from collections import Counter

CHAIN_PROBE_VERSION = '0.1.0'
CARRY_STATES = ('wait_carry', 'carry')                                   # a leg is being carried (or about to be)
HANDOVER_STATES = ('wait_lower', 'lower', 'wait_open', 'cp_open', 'released', 'done')   # after a leg / the set-down
LEG_START_STATES = CARRY_STATES
LEG_END_STATE = 'wait_lower'     # the controller finished the carry schedule (robots held, beam still up) -> leg end

# GT criteria (eval only). Same development hypotheses as the single-leg ``carry`` / ``setdown`` stages, applied to every
# leg end (so the end-point criterion is CUMULATIVE against the planned route point). Recorded with every result.
CRITERIA = {'min_lift_m': .03, 'max_tilt_deg': 10., 'both_jaws_contact': True, 'max_end_error_m': .10, 'max_leg_error_m': .10,
            'setdown': {'max_rest_height_m': .005, 'max_tilt_deg': 3., 'no_jaw_contact': True, 'max_shift_m': .05},
            'note': ('every leg end: beam lifted >= 3 cm, tilt <= 10 deg, both jaws of both robots touch; beam end point within '
                     '10 cm of the planned route point (cumulative, includes cross-track) and beam travel within 10 cm of '
                     'the planned leg (incremental); final set-down: on the floor, level, released, not dragged (<= 5 cm '
                     'from where leg 7 ended)')}


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# ------------------------------------------------------------------ static geometry
def legs_of(route):
    """The planned legs of a static route (controller ``make_plan`` route): leg k goes route[k] -> route[k + 1]."""
    out = []
    for k, (a, b) in enumerate(zip(route, route[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        out.append({'leg': k, 'p0': [float(a[0]), float(a[1])], 'p1': [float(b[0]), float(b[1])], 'length_m': math.hypot(dx, dy),
                    'axis': 'lateral' if abs(dy) > 1e-6 else 'axial'})
    return out


def phase_of(seg, state, n_legs):
    """(phase, leg) of a controller (segment, state) pair.

    ``carry``: leg ``seg`` is being carried. ``handover``: after leg ``seg`` ended, lower/open/checkpoint (the segment counter
    is incremented at the end of ``cp_open``). ``regrasp``: relocalize / align / grasp / lift for leg ``seg`` (the counter
    already moved on). ``setdown``: the last leg's lower/open/back-off. ``other``: anything not in the known state lists.
    """
    last = n_legs - 1
    if state in CARRY_STATES:
        return 'carry', int(seg)
    if state in HANDOVER_STATES:
        return ('setdown', int(seg)) if int(seg) >= last else ('handover', int(seg))
    if int(seg) >= 1:
        return 'regrasp', int(seg)
    return 'other', int(seg)


def phase_at(timeline, t, n_legs):
    """(phase, leg) of a robot at sim time ``t`` from its transition timeline [(t, seg, state), ...]; None if before it."""
    cur = None
    for row in timeline:
        if row[0] <= t + 1e-9:
            cur = row
        else:
            break
    return None if cur is None else phase_of(cur[1], cur[2], n_legs)


def brief_report(rep):
    """The robot's OWN PoseReport reduced to the fields the chain curves use (data the controller already had)."""
    if not rep:
        return None
    return {'t': rep.get('t_est'), 'xyyaw': list(rep.get('xyyaw') or [rep.get('x_m'), rep.get('y_m'), rep.get('yaw_rad')]),
            'std_xy_m': rep.get('std_xy_m'), 'std_yaw_rad': rep.get('std_yaw_rad'), 'fix_age_s': rep.get('fix_age_s'),
            'fix_source': rep.get('fix_source')}


# ------------------------------------------------------------------ per-robot recorder (pass-through hook)
class ChainRecorder:
    """Records one robot's state timeline and its leg-boundary snapshots. Pure bookkeeping, no control input.

    ``observe(now, seg, state, own_fn, gt_fn)``: called after every controller tick. ``own_fn()`` / ``gt_fn()`` are lazy and are
    called only at a boundary (first tick of a leg in a carry state = leg start; first tick in ``wait_lower`` = leg end;
    first tick in ``done``), so a tick that is not a boundary costs nothing.
    """
    def __init__(self, rid):
        self.rid = rid
        self.timeline = []           # [t, seg, state] at every (seg, state) change
        self.leg_start = {}          # seg -> {'sim_s', 'own', 'gt'}
        self.leg_end = {}            # seg -> {'sim_s', 'own', 'gt'}
        self.done = None             # {'sim_s', 'own', 'gt'}
        self.tick_count = 0

    def observe(self, now, seg, state, own_fn, gt_fn):
        self.tick_count += 1
        key = (int(seg), state)
        if not self.timeline or (self.timeline[-1][1], self.timeline[-1][2]) != key:
            self.timeline.append([float(now), int(seg), state])
        snap = None
        if state in LEG_START_STATES and int(seg) not in self.leg_start:
            snap = self.leg_start[int(seg)] = {'sim_s': float(now), 'own': own_fn(), 'gt': gt_fn()}
        elif state == LEG_END_STATE and int(seg) not in self.leg_end:
            snap = self.leg_end[int(seg)] = {'sim_s': float(now), 'own': own_fn(), 'gt': gt_fn()}
        elif state == 'done' and self.done is None:
            snap = self.done = {'sim_s': float(now), 'own': own_fn(), 'gt': gt_fn()}
        return snap

    def raw(self):
        return {'timeline': self.timeline, 'leg_start': self.leg_start, 'leg_end': self.leg_end, 'done': self.done,
                'ticks': self.tick_count}


def install_recorder(ctl, rid, probe, execution):
    """Wrap ONE controller's ``tick`` with a pass-through recorder (called from ``install_stage`` for stage ``chain`` only).

    The wrapped tick returns exactly what the original returns and runs it first; the recorder reads ``ctl.seg`` / ``ctl.state``
    afterwards. The recorder never sets a controller attribute and never re-stages: entry is the single teacher staging.
    """
    chain = probe.__dict__.setdefault('chain', {})
    rec = chain.setdefault(rid, ChainRecorder(rid))
    original = ctl.tick

    def own_fn():
        last = execution.own.last_report
        return brief_report(None if last is None else last.as_dict())

    def gt_fn():
        return None if probe.host is None else probe.host.gt_snapshot(rid)   # eval only, never returned to control

    def tick(now):
        out = original(now)
        rec.observe(now, getattr(ctl, 'seg', 0), ctl.state, own_fn, gt_fn)
        return out

    ctl.tick = tick
    return ctl


def raw_of(probe):
    """The probe's recorders as plain data (written to result.json ``chain_raw``)."""
    return {rid: rec.raw() for rid, rec in probe.__dict__.get('chain', {}).items()}


# ------------------------------------------------------------------ metrics (pure)
def leg_line_metrics(p0, p1, end_xy):
    """Beam end vs the planned leg line: distance to the route point, signed along error, absolute cross-track."""
    length = math.dist(p0, p1)
    ux, uy = (p1[0] - p0[0]) / length, (p1[1] - p0[1]) / length
    dx, dy = end_xy[0] - p0[0], end_xy[1] - p0[1]
    return {'end_error_m': math.dist(end_xy, p1), 'along_error_m': dx * ux + dy * uy - length,
            'cross_track_m': abs(-dx * uy + dy * ux)}


def _later(records):
    """The later of the robots' records (the beam is judged when the last robot reaches the boundary, as the carry stage does)."""
    got = [r for r in records if r is not None]
    return max(got, key=lambda r: r['sim_s']) if got else None


def _std_max(records, key):
    """Largest value of an own-report field across the robots' records (None when no robot reported it)."""
    vals = [r['own'][key] for r in records if r and r.get('own') and r['own'].get(key) is not None]
    return max(vals) if vals else None


def _est_err(records):
    """Own estimate vs GT pose per robot at a boundary (eval only): worst xy [m] and yaw [rad] error across robots."""
    xy, yaw = [], []
    for rid, r in records.items():
        if not r or not r.get('own') or not r.get('gt'):
            continue
        est, gt = r['own']['xyyaw'], r['gt']['robots'][rid]
        xy.append(math.dist(est[:2], gt[:2]))
        yaw.append(abs(wrap(est[2] - gt[2])))
    return (max(xy) if xy else None), (max(yaw) if yaw else None)


def chain_legs(route, raw, n_legs=None):
    """Per-leg records from the two robots' raw recorders (``raw_of``). A leg without both robots' start/end is marked
    ``recorded: False`` and carries no metrics (the run never got there)."""
    n_legs = n_legs if n_legs is not None else len(route) - 1
    planned = legs_of(route)
    robots = sorted(raw)
    chain_start = None
    legs = []
    prev_end = None
    for k in range(n_legs):
        starts = {r: raw[r]['leg_start'].get(k) or raw[r]['leg_start'].get(str(k)) for r in robots}
        ends = {r: raw[r]['leg_end'].get(k) or raw[r]['leg_end'].get(str(k)) for r in robots}
        st, en = (_later(starts.values()) if starts else None), (_later(ends.values()) if ends else None)
        row = {'leg': k, 'axis': planned[k]['axis'], 'planned_length_m': planned[k]['length_m'], 'recorded': False,
               'start_sim_s': None if st is None else st['sim_s'], 'end_sim_s': None if en is None else en['sim_s']}
        complete = (st is not None and en is not None and len(robots) and all(starts[r] and ends[r] for r in robots)
                    and st['gt'] is not None and en['gt'] is not None)
        if complete:
            if chain_start is None:
                chain_start = st['gt']
            s, e = st['gt'], en['gt']
            p0, p1 = planned[k]['p0'], planned[k]['p1']
            travel = math.dist(s['beam_xyz'][:2], e['beam_xyz'][:2])
            step_target = [s['beam_xyz'][0] + p1[0] - p0[0], s['beam_xyz'][1] + p1[1] - p0[1]]
            est_xy, est_yaw = _est_err(ends)
            row.update(
                recorded=True, **leg_line_metrics(p0, p1, e['beam_xyz'][:2]),
                travel_m=travel, leg_error_m=abs(travel - planned[k]['length_m']),
                step_error_m=math.dist(e['beam_xyz'][:2], step_target),
                yaw_drift_deg=math.degrees(wrap(e['beam_yaw'] - chain_start['beam_yaw'])),
                yaw_step_deg=math.degrees(wrap(e['beam_yaw'] - s['beam_yaw'])),
                lift_m=e['lift_m'], tilt_deg=e['tilt_deg'], jaws=e['jaws'],
                sigma_xy_start_m=_std_max(starts.values(), 'std_xy_m'), sigma_yaw_start_rad=_std_max(starts.values(), 'std_yaw_rad'),
                sigma_xy_end_m=_std_max(ends.values(), 'std_xy_m'), sigma_yaw_end_rad=_std_max(ends.values(), 'std_yaw_rad'),
                fix_age_end_s=_std_max(ends.values(), 'fix_age_s'),
                est_err_xy_end_m=est_xy, est_err_yaw_end_rad=est_yaw,
                handover_from_prev_end_s=None if prev_end is None else st['sim_s'] - prev_end['sim_s'])
            prev_end = en
        legs.append(row)
    return legs


def setdown_record(raw, legs, gt_at_end, final_states, criteria=CRITERIA):
    """The destination set-down at the end of the chain (eval only): rest height, tilt, release, shift from the leg-7 end."""
    crit = criteria['setdown']
    last = legs[-1] if legs else None
    out = {'reached': bool(gt_at_end is not None and final_states and all(s == 'done' for s in final_states.values()))}
    if gt_at_end is None:
        return out
    out.update(lift_m=gt_at_end['lift_m'], tilt_deg=gt_at_end['tilt_deg'], jaws=gt_at_end['jaws'])
    if last and last['recorded']:
        chain_end = None
        for r in raw.values():
            e = r['leg_end'].get(len(legs) - 1) or r['leg_end'].get(str(len(legs) - 1))
            chain_end = _later([chain_end, e])
        if chain_end and chain_end.get('gt'):
            out['shift_m'] = math.dist(chain_end['gt']['beam_xyz'][:2], gt_at_end['beam_xyz'][:2])
    out['checks'] = {'rest': gt_at_end['lift_m'] <= crit['max_rest_height_m'], 'tilt': gt_at_end['tilt_deg'] <= crit['max_tilt_deg'],
                     'released': not any(any(gt_at_end['jaws'][r]) for r in gt_at_end['jaws']),
                     'shift': (out.get('shift_m') if out.get('shift_m') is not None else 0.) <= crit['max_shift_m']}
    return out


def leg_checks(leg, crit=CRITERIA):
    """Pass/fail of one recorded leg against the criteria (a not-recorded leg has no checks)."""
    if not leg.get('recorded'):
        return {}
    return {'lift': leg['lift_m'] >= crit['min_lift_m'], 'tilt': leg['tilt_deg'] <= crit['max_tilt_deg'],
            'both_jaws_both_robots': all(all(v) for v in leg['jaws'].values()),
            'end_error': leg['end_error_m'] <= crit['max_end_error_m'], 'leg_error': leg['leg_error_m'] <= crit['max_leg_error_m']}


def chain_checks(chain, crit=CRITERIA):
    """Aggregated checks for ``pair_stage_probe.evaluate('chain', ...)``: same names as the carry / setdown stages, every leg
    must pass (``legs_recorded`` = all planned legs reached their end)."""
    legs = chain['legs']
    checks = {'legs_recorded': all(l['recorded'] for l in legs) and bool(legs)}
    per_leg = [leg_checks(l, crit) for l in legs]
    for name in ('lift', 'tilt', 'both_jaws_both_robots', 'end_error', 'leg_error'):
        checks[name] = all(c.get(name, False) for c in per_leg) if per_leg else False
    sd = chain.get('setdown') or {}
    for name in ('rest', 'released', 'shift'):
        checks[name] = bool((sd.get('checks') or {}).get(name, False))
    checks['tilt'] = checks['tilt'] and bool((sd.get('checks') or {}).get('tilt', False))
    return checks


def curves(legs):
    """Cumulative curves over legs 0..n (None where a leg was not reached): the input of the accumulation plots/tables."""
    keys = ('end_error_m', 'cross_track_m', 'along_error_m', 'yaw_drift_deg', 'step_error_m', 'leg_error_m',
            'sigma_xy_end_m', 'sigma_yaw_end_rad', 'est_err_xy_end_m', 'est_err_yaw_end_rad')
    return {k: [l.get(k) if l.get('recorded') else None for l in legs] for k in keys}


def first_failure(chain, record, own_at_failure=None, crit=CRITERIA):
    """The first thing that went wrong in chronological order: a controller failure (job_failed) or a leg whose GT criteria fail.

    Returns None when neither happened. ``code`` reuses the stage probe's cause vocabulary. Deterministic and labelled, not a
    proof of cause.
    """
    from harness import pair_stage_probe as sp
    n_legs = len(chain['legs'])
    cands = []
    ff = record.get('first_failure')
    if ff and ff.get('reason') != 'HOST_ERROR':
        timeline = (chain.get('timelines') or {}).get(ff.get('robot_id')) or []
        where = phase_at(timeline, ff['sim_s'], n_legs) if ff.get('sim_s') is not None else None
        code = sp.FAILURE_TO_CAUSE.get(ff['reason']) or ('PARTNER_ABORT' if str(ff['reason']).startswith('PARTNER') else 'UNCLASSIFIED')
        sub = sp.pose_uncertainty_sub((own_at_failure or {}).get(ff.get('robot_id'))) if code == 'SELF_POSE_UNCERTAIN' else None
        cands.append({'source': 'controller', 'sim_s': ff['sim_s'], 'reason': ff['reason'], 'robot_id': ff.get('robot_id'),
                      'phase': None if where is None else where[0], 'leg': None if where is None else where[1],
                      'code': code, 'sub': sub})
    for leg in chain['legs']:
        bad = [k for k, v in leg_checks(leg, crit).items() if not v]
        if bad:
            order = ['lift', 'both_jaws_both_robots', 'end_error', 'leg_error', 'tilt']
            bad.sort(key=lambda k: order.index(k) if k in order else len(order))
            cands.append({'source': 'gt_criterion', 'sim_s': leg['end_sim_s'], 'reason': ','.join(bad), 'robot_id': None,
                          'phase': 'carry', 'leg': leg['leg'], 'code': sp.CHECK_TO_CAUSE.get(bad[0], 'UNCLASSIFIED'), 'sub': ','.join(bad)})
            break
    sd = chain.get('setdown') or {}
    bad = [k for k, v in (sd.get('checks') or {}).items() if not v]
    if bad and sd.get('reached'):
        cands.append({'source': 'gt_criterion', 'sim_s': None, 'reason': ','.join(bad), 'robot_id': None, 'phase': 'setdown',
                      'leg': n_legs - 1, 'code': sp.CHECK_TO_CAUSE.get(bad[0], 'UNCLASSIFIED'), 'sub': ','.join(bad)})
    if not cands:
        return None
    return min(cands, key=lambda c: (float('inf') if c['sim_s'] is None else c['sim_s']))


def chain_record(case, raw, gt_at_end, final_states, localizer_log=None):
    """The whole chain result from the raw recorders (called by the runner's ``finish_result`` for stage ``chain``)."""
    route = case['route']
    legs = chain_legs(route, raw)
    sd = setdown_record(raw, legs, gt_at_end, final_states)
    out = {'version': CHAIN_PROBE_VERSION, 'n_legs': len(legs), 'legs': legs, 'setdown': sd,
           'timelines': {rid: r['timeline'] for rid, r in raw.items()},
           'restaging_between_legs': False,
           'staging_note': 'one teacher staging (leg 0 lift); the controller state (PF, command history, own fix clock) '
                           'runs on across legs; nothing here re-stages'}
    out['legs_recorded'] = sum(l['recorded'] for l in legs)
    # legs passed = consecutive legs from 0 whose own checks all pass
    passed = 0
    for l in legs:
        if l['recorded'] and all(leg_checks(l).values()):
            passed += 1
        else:
            break
    out['legs_passed_prefix'] = passed
    out['curves'] = curves(legs)
    log = localizer_log or []
    out['localizer_replaced_events'] = [{'t': x['t'], 'robot_id': x['robot_id']} for x in log if x.get('event') == 'localizer_object_replaced']
    return out


def chain_metrics(chain):
    """Compact metrics for ``evaluate`` (kept small: the full per-leg table lives in the row's ``chain`` block)."""
    return {'legs_recorded': chain['legs_recorded'], 'legs_passed_prefix': chain['legs_passed_prefix'],
            'end_error_m_by_leg': chain['curves']['end_error_m'], 'yaw_drift_deg_by_leg': chain['curves']['yaw_drift_deg'],
            'sigma_yaw_end_rad_by_leg': chain['curves']['sigma_yaw_end_rad']}


def summarize_chain(rows):
    """Aggregate over chain rows: legs reached / passed histogram, first-failure histogram, per-leg curve medians and maxima."""
    chains = [r['chain'] for r in rows if r.get('chain')]
    if not chains:
        return {'cases': 0}
    n = max(c['n_legs'] for c in chains)
    per_leg = {}
    for k in range(n):
        vals = {key: sorted(c['curves'][key][k] for c in chains if len(c['curves'][key]) > k and c['curves'][key][k] is not None)
                for key in ('end_error_m', 'cross_track_m', 'yaw_drift_deg', 'sigma_yaw_end_rad', 'sigma_xy_end_m')}
        per_leg[str(k)] = {'reached': sum(1 for c in chains if c['legs'][k]['recorded']),
                           **{f'{key}_median': (v[len(v) // 2] if v else None) for key, v in vals.items()},
                           **{f'{key}_max': (v[-1] if v else None) for key, v in vals.items()}}
    first = Counter((c['first_failure']['phase'], c['first_failure']['leg'], c['first_failure']['code'])
                    for c in chains if c.get('first_failure'))
    return {'cases': len(chains), 'legs_recorded': dict(Counter(c['legs_recorded'] for c in chains)),
            'legs_passed_prefix': dict(Counter(c['legs_passed_prefix'] for c in chains)), 'per_leg': per_leg,
            'first_failure': [{'phase': p, 'leg': leg, 'code': code, 'count': cnt} for (p, leg, code), cnt in first.most_common()]}
