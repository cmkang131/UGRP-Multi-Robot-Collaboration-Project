"""v98 HIGH intermediate checkpoint: own dead-reckoning budget receipt (simulator-free).

Sigma values are the offline model prediction for the registered route (v98 provider at af2f7c2a, recorded
6727751b ``align_to_carry`` own frames/commands up to the carry GO, then the planned carry commands):
end of leg 0 (before_door stop) std_xy 42.4/42.3 mm, std_yaw 1.38/1.22 deg (r1/r2); end of leg 1 (door)
59.1/59.9 mm. Ground truth is not used by the rule or by these tests.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_dr_checkpoint as dc
from harness.zone_pair_highpose_timing import CHECKPOINT_REOBSERVE_S
from scripts import run_pair_highpose as runner
from tests.test_highpose_transit import pair, opened, short_route  # noqa: F401  (autouse fixture)

MIN = CHECKPOINT_REOBSERVE_S


def rep(t, *, fix_t, sxy, syaw_deg, initialized=True, cov='diag'):
    """Fake own report. ``cov='diag'``: the 3x3 covariance implied by the sigmas; ``None``: no ``cov`` attribute."""
    syaw = math.radians(syaw_deg)
    if cov == 'diag':
        cov = ((sxy**2/2, 0., 0.), (0., sxy**2/2, 0.), (0., 0., syaw**2))
    report = SimpleNamespace(t_est=t, initialized=initialized, last_fix_t=fix_t, std_xy_m=sxy,
                             std_yaw_rad=syaw, x_m=1.2, y_m=.03, yaw_rad=.01)
    if cov is not None:
        report.cov = cov
    return report


def test_decide_waits_for_the_unchanged_minimum_stop():
    kind, detail = dc.decide(rep(10.5, fix_t=2., sxy=.042, syaw_deg=1.4), 10.5, 10., 10., MIN)
    assert kind == 'wait' and detail['stop_s'] == .5


def test_decide_accepts_own_dr_within_the_same_budget():
    kind, detail = dc.decide(rep(11.3, fix_t=2., sxy=.0424, syaw_deg=1.38), 11.3, 10., 10., MIN)
    assert kind == 'dr' and math.isclose(detail['fix_age_s'], 9.3)
    assert dc.BUDGET_XY_M == .05 and math.isclose(dc.BUDGET_YAW_RAD, math.radians(3.))   # nothing widened


def test_decide_over_budget_aborts_instead_of_waiting():
    assert dc.decide(rep(11.3, fix_t=2., sxy=.0591, syaw_deg=1.63), 11.3, 10., 10., MIN)[0] == 'over'
    assert dc.decide(rep(11.3, fix_t=2., sxy=.03, syaw_deg=3.1), 11.3, 10., 10., MIN)[0] == 'over'
    assert dc.decide(rep(11.3, fix_t=2., sxy=float('nan'), syaw_deg=1.), 11.3, 10., 10., MIN)[0] == 'over'


def test_decide_keeps_the_fresh_fix_receipt():
    assert dc.decide(rep(11.3, fix_t=10.6, sxy=.01, syaw_deg=.5), 11.3, 10., 10., MIN)[0] == 'fix'
    # a fresh fix that is still wide waits for a better one (old behaviour, bounded by the 8 s timeout)
    assert dc.decide(rep(11.3, fix_t=10.6, sxy=.08, syaw_deg=.5), 11.3, 10., 10., MIN)[0] == 'wait'


def test_decide_without_a_usable_report_waits():
    assert dc.decide(None, 11.3, 10., 10., MIN) == ('wait', None)
    assert dc.decide(rep(10.0, fix_t=2., sxy=.01, syaw_deg=.5), 11.3, 10., 10., MIN) == ('wait', None)  # stale
    assert dc.decide(rep(11.3, fix_t=2., sxy=.01, syaw_deg=.5, initialized=False), 11.3, 10., 10., MIN) == ('wait', None)


def test_decide_treats_a_voided_receipt_as_dr_not_wait():
    # vision_pose_source_p03.begin_relocalization (called at checkpoint_high_stop) keeps the belief and sigma
    # but sets last_scan_t -> last_fix_t to None. Before this rule decide() waited 8 s and timed out
    # (1f7fb800 align_to_carry r1: sigma 36 mm / 1.15 deg, HIGH_CHECKPOINT_REOBSERVE_TIMEOUT at +8.1 s).
    kind, detail = dc.decide(rep(11.3, fix_t=None, sxy=.0364, syaw_deg=1.15), 11.3, 10., 10., MIN)
    assert kind == 'dr' and detail['fix_receipt_voided'] and detail['fix_t'] is None
    assert dc.decide(rep(11.3, fix_t=None, sxy=.0591, syaw_deg=1.), 11.3, 10., 10., MIN)[0] == 'over'
    assert dc.decide(rep(10.5, fix_t=None, sxy=.01, syaw_deg=.5), 10.5, 10., 10., MIN)[0] == 'wait'


def test_real_provider_reset_voids_last_fix_t():
    # The real p03 provider path the v98 HighPoseSource inherits: begin_relocalization sets last_scan_t None.
    import inspect
    from harness import vision_pose_source_p03 as p03
    from harness.vision_pose_source_highpose import HighPoseSource
    assert issubclass(HighPoseSource, p03.VisionPoseSource)
    src = inspect.getsource(p03.VisionPoseSource.begin_relocalization)
    assert 'self.loc._pf.last_scan_t = None' in src


def run_dr(ctls, *, until, sxy, syaw_deg, only=None, voided=False, fresh_fix=False):
    """Real tick() + arm ticks; from each checkpoint stop on, the own report is DR only (last fix before the stop)."""
    for i in range(int(round(until/.1))+1):
        now = round(i*.1, 8)
        for c in ctls:
            if getattr(c, 'checkpoint_fix_after', None) is not None and (only is None or c.rid in only):
                fix_t = now if fresh_fix else None if voided else c.checkpoint_fix_after-30.
                c.port.own.last_report = rep(now, fix_t=fix_t, sxy=sxy[c.rid], syaw_deg=syaw_deg[c.rid])
            if c.state not in ('failed', 'released', 'done'):
                c.tick(now)
        for c in ctls:
            if c.state != 'failed':
                c.arm.tick(now)
    return ctls


import pytest


@pytest.mark.parametrize('voided', [False, True])
def test_dr_receipt_resumes_at_high_without_lowering_or_a_reobserve_event(voided):
    _, ctls = pair(segments=(.1, .1))
    run_dr(ctls, until=60., sxy={'r1': .0424, 'r2': .0423}, syaw_deg={'r1': 1.38, 'r2': 1.22}, voided=voided)
    for c in ctls:
        assert c.failure is None and c.state == 'released'
        stop = next(e['t'] for e in c.events if e['event'] == 'checkpoint_high_stop')
        got = [e for e in c.events if e['event'] == dc.DR_EVENT]
        assert len(got) == 1 and got[0]['seg'] == 1 and got[0]['t']-stop >= MIN-1e-8
        assert got[0]['std_xy_m'] <= dc.BUDGET_XY_M
        assert (got[0]['fix_age_s'] is None and got[0]['fix_receipt_voided']) if voided else got[0]['fix_age_s'] > 30.
        assert not [e for e in c.events if e['event'] == dc.FIX_EVENT]      # never labelled as a re-observation
        assert not [a for t, a in c.issued_log if stop <= t <= got[0]['t'] and a['kind'] == 'arm']
        assert any(e['event'] == 'barrier_go' and e['barrier'] == 'carry' and e['t'] > got[0]['t'] for e in c.events)
        assert opened(c)                                                     # only after the final lowering


def test_over_budget_aborts_at_the_minimum_stop_and_partner_stops():
    _, ctls = pair(segments=(.1, .1))
    run_dr(ctls, until=60., sxy={'r1': .0424, 'r2': .0599}, syaw_deg={'r1': 1.38, 'r2': 1.46})
    r1, r2 = ctls
    assert r2.failure == dc.OVER_REASON
    stop = next(e['t'] for e in r2.events if e['event'] == 'checkpoint_high_stop')
    over = next(e for e in r2.events if e['event'] == dc.OVER_EVENT)
    assert over['t']-stop < MIN+.2 and over['std_xy_m'] > dc.BUDGET_XY_M     # not the 8 s timeout
    assert r1.failure == 'PARTNER_ABORT'
    for c in ctls:
        assert not opened(c) and pose.at_high(c.port.own.servo)


def test_no_report_still_times_out():
    _, ctls = pair(segments=(.1, .1))
    run_dr(ctls, until=60., sxy={'r1': .0424, 'r2': .0424}, syaw_deg={'r1': 1.38, 'r2': 1.38}, only=('r1',))
    assert ctls[1].failure == 'HIGH_CHECKPOINT_REOBSERVE_TIMEOUT'


def test_p03_receipt_keeps_the_receipt_kind():
    def session(event):
        robots = {rid: {'events': [{'event': 'state', 'state': 'carry', 'seg': 0},
                                   {'event': 'checkpoint_high_stop', 'seg': 1, 't': 20.},
                                   {'event': event, 'seg': 1, 't': 21.3}]} for rid in ('r1', 'r2')}
        return {'pair': [{'plan': {'checkpoint_segments': {'before_door': 1}}, 'robots': robots}]}
    for event, kind in ((dc.DR_EVENT, 'dr_budget'), (dc.FIX_EVENT, 'fix')):
        out = runner.checkpoint_record(session(event), 'before_door')
        assert out['status'] == 'SEQUENCE_OBSERVED_UNQUALIFIED'
        assert all(r['high_reobserved'][0]['receipt'] == kind for r in out['robots'].values())
    assert runner.checkpoint_record(session(dc.OVER_EVENT), 'before_door')['status'] == 'NOT_REACHED'


def test_decide_logs_the_own_mean_and_covariance_for_every_receipt_kind():
    # 2026-10-05 (independent review P1-3): the sigma-budget receipt must also record WHAT the filter believed, so an
    # evaluation-only scorer can compute the NEES after the run. Log only: the kind never depends on these fields.
    cov = ((4e-4, 1e-5, 2e-6), (1e-5, 5e-4, -3e-6), (2e-6, -3e-6, 3e-4))
    for fix_t, sxy, kind in ((2., .03, 'dr'), (None, .03, 'dr'), (10.6, .01, 'fix'), (2., .06, 'over')):
        report = rep(11.3, fix_t=fix_t, sxy=sxy, syaw_deg=1., cov=cov)
        got, detail = dc.decide(report, 11.3, 10., 10., MIN)
        assert got == kind
        assert (detail['x_m'], detail['y_m'], detail['yaw_rad']) == (1.2, .03, .01)
        assert detail['cov'] == [list(row) for row in cov] and isinstance(detail['cov'][0], list)
    # not-yet-receipt reports (wait with detail) log them too; a missing report still has no detail
    assert dc.decide(rep(10.5, fix_t=2., sxy=.03, syaw_deg=1., cov=cov), 10.5, 10., 10., MIN)[1]['cov'] is not None
    assert dc.decide(None, 11.3, 10., 10., MIN) == ('wait', None)


BAD_COVS = (None, (), ((1., 2.),), ((1., 0., 0.), (0., 1.), (0., 0., 1.)), 'abc', 7,
            ((float('nan'), 0., 0.), (0., 1., 0.), (0., 0., 1.)), ((float('inf'), 0., 0.), (0., 1., 0.), (0., 0., 1.)),
            (('a', 0., 0.), (0., 1., 0.), (0., 0., 1.)))


@pytest.mark.parametrize('bad', BAD_COVS, ids=range(len(BAD_COVS)))
def test_logging_the_estimate_never_changes_the_decision(bad):
    # Same (report time, fix time, sigmas, clock) with a good cov, a missing cov and a malformed one: same kind, same
    # old detail keys, and a bad cov is logged as None (never raised, never NaN: the runner writes strict JSON).
    cases = ((11.3, 2., .0424, 1.38, 11.3), (11.3, None, .0424, 1.38, 11.3), (11.3, 10.6, .01, .5, 11.3),
             (11.3, 10.6, .08, .5, 11.3), (11.3, 2., .0591, 1.63, 11.3), (11.3, 2., .03, 3.1, 11.3),
             (11.3, 2., float('nan'), 1., 11.3), (10.5, 2., .042, 1.4, 10.5), (10.0, 2., .01, .5, 11.3))
    old_keys = {'std_xy_m', 'std_yaw_rad', 'fix_t', 'fix_age_s', 'fix_receipt_voided', 'report_t_est', 'stop_s'}
    for t, fix_t, sxy, syaw, now in cases:
        good = dc.decide(rep(t, fix_t=fix_t, sxy=sxy, syaw_deg=syaw), now, 10., 10., MIN)
        other = dc.decide(rep(t, fix_t=fix_t, sxy=sxy, syaw_deg=syaw, cov=bad), now, 10., 10., MIN)
        assert good[0] == other[0]
        if good[1] is None:
            assert other[1] is None
            continue
        keep = lambda d: repr(sorted((k, v) for k, v in d.items() if k in old_keys))     # repr: nan-safe equality
        assert keep(good[1]) == keep(other[1])
        assert set(other[1]) == old_keys | {'x_m', 'y_m', 'yaw_rad', 'cov'}
        assert other[1]['cov'] is None


def test_decide_estimate_fields_are_none_when_the_mean_is_not_finite():
    report = rep(11.3, fix_t=2., sxy=.03, syaw_deg=1.)
    report.x_m = float('nan')
    kind, detail = dc.decide(report, 11.3, 10., 10., MIN)
    assert kind == 'dr' and detail['x_m'] is None and detail['y_m'] == .03 and detail['cov'] is not None


@pytest.mark.parametrize('mode', ['fix', 'dr', 'voided'])
def test_every_receipt_event_in_the_controller_log_carries_the_own_estimate(mode):
    # Real controller path: FIX_EVENT used to log only fix_t; DR/OVER already spread the decide() detail.
    _, ctls = pair(segments=(.1, .1))
    run_dr(ctls, until=60., sxy={'r1': .0424, 'r2': .0423}, syaw_deg={'r1': 1.38, 'r2': 1.22},
           voided=mode == 'voided', fresh_fix=mode == 'fix')
    for c in ctls:
        assert c.failure is None
        event = dc.FIX_EVENT if mode == 'fix' else dc.DR_EVENT
        got = [e for e in c.events if e['event'] == event]
        assert len(got) == 1
        e = got[0]
        sxy = {'r1': .0424, 'r2': .0423}[c.rid]
        assert (e['x_m'], e['y_m'], e['yaw_rad']) == (1.2, .03, .01)
        assert e['cov'][0][0] == sxy**2/2 and e['cov'][1][1] == sxy**2/2 and len(e['cov']) == 3
        assert e['report_t_est'] <= e['t'] and e['seg'] == 1
        if mode == 'fix':
            assert e['fix_t'] == e['report_t_est'] and not e['fix_receipt_voided']


def test_over_event_carries_the_own_estimate():
    _, ctls = pair(segments=(.1, .1))
    run_dr(ctls, until=60., sxy={'r1': .0424, 'r2': .0599}, syaw_deg={'r1': 1.38, 'r2': 1.46})
    over = next(e for e in ctls[1].events if e['event'] == dc.OVER_EVENT)
    assert over['cov'] is not None and (over['x_m'], over['y_m'], over['yaw_rad']) == (1.2, .03, .01)


def test_record_names_the_unchanged_thresholds():
    r = dc.record()
    assert r['budget_xy_m'] == .05 and math.isclose(r['budget_yaw_rad'], math.radians(3.))
    assert r['events'] == [dc.FIX_EVENT, dc.DR_EVENT, dc.OVER_EVENT]


# ---- record-derived (2026-10-04 coordinator practice: feed new rules values from a real recorded run) ----
import json
from pathlib import Path

RECORD = Path(__file__).with_name('fixtures')/'v98_dr_checkpoint_align_to_carry_1f7fb800.json'


def _recorded():
    return json.loads(RECORD.read_text())


def test_recorded_checkpoint_reset_voids_the_receipt_and_keeps_the_belief():
    rec = _recorded()
    assert rec['source']['sha256'].startswith('a609368e')
    for rid, r in rec['robots'].items():
        lc = r['begin_relocalization']
        assert lc['before']['last_scan_t'] == lc['previous_fix_t'] is not None      # a fix existed (before HIGH)
        assert lc['after']['last_scan_t'] is None                                    # receipt voided by the reset
        assert lc['belief_preserved'] and lc['before']['particles_sha256'] == lc['after']['particles_sha256']
        assert lc['previous_fix_t'] < 64.8 < r['checkpoint_high_stop']['sim_s']    # no fix at HIGH before the stop


def test_recorded_checkpoint_values_give_dr_with_the_proposal_and_wait_with_the_old_rule():
    rec = _recorded()
    for rid, r in rec['robots'].items():
        cov = r['begin_relocalization']['before']['std']
        sxy = math.sqrt(cov[0][0]+cov[1][1])                                        # owncam std_xy_m (trace)
        syaw_deg = math.degrees(math.sqrt(cov[2][2]))
        stop = r['checkpoint_high_stop']['sim_s']
        now = stop+MIN
        report = rep(now-.16, fix_t=None, sxy=sxy, syaw_deg=syaw_deg)              # 0.16 s pose delay, fresh
        kind, detail = dc.decide(report, now, stop, stop, MIN)
        assert kind == 'dr' and detail['fix_receipt_voided'], (rid, sxy, syaw_deg)
        # the old rule treated last_fix_t None as "no usable report": the recorded run timed out / partner abort
        assert r['job_failed']['detail']['reason'] in ('HIGH_CHECKPOINT_REOBSERVE_TIMEOUT', 'PARTNER_ABORT')
    assert rec['robots']['r1']['job_failed']['detail']['reason'] == 'HIGH_CHECKPOINT_REOBSERVE_TIMEOUT'


def test_real_provider_reset_feeds_decide_a_voided_dr_report(tmp_path, monkeypatch):
    from tests.test_zone_final_pair_highpose import synthetic, MAPS, c
    from tests.test_highpose_pf_consistency import _scan
    from harness.vision_pose_source_highpose import HighPoseSource
    path, _ = synthetic(tmp_path, monkeypatch)
    servo = {1: 2000, **pose.grasp_postures()[1][-1]}
    src = HighPoseSource(c.resolve(MAPS[0])[0], path, c.base.sha(path))
    src.init_prior((1., 0., 0.), (.01, .01, .01), source='synthetic public dock')
    pf = src.loc._pf
    pf.apply_scan(1., _scan(src, servo), servo)
    before = src.report(2.)
    src.begin_relocalization(2., servo)
    after = src.report(2.)
    assert after.initialized and after.last_fix_t is None
    assert math.isclose(after.std_xy_m, before.std_xy_m) and math.isclose(after.std_yaw_rad, before.std_yaw_rad)
    kind, detail = dc.decide(after, 2., 2.-MIN, 2.-MIN, MIN)
    assert kind in ('dr', 'over') and detail['fix_receipt_voided']
    assert kind == ('dr' if after.std_xy_m <= dc.BUDGET_XY_M and after.std_yaw_rad <= dc.BUDGET_YAW_RAD else 'over')
