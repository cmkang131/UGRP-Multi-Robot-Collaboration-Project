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


def rep(t, *, fix_t, sxy, syaw_deg, initialized=True):
    return SimpleNamespace(t_est=t, initialized=initialized, last_fix_t=fix_t, std_xy_m=sxy,
                           std_yaw_rad=math.radians(syaw_deg), x_m=1.2, y_m=.03, yaw_rad=.01)


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
    assert dc.decide(rep(11.3, fix_t=None, sxy=.01, syaw_deg=.5), 11.3, 10., 10., MIN) == ('wait', None)
    assert dc.decide(rep(11.3, fix_t=2., sxy=.01, syaw_deg=.5, initialized=False), 11.3, 10., 10., MIN) == ('wait', None)


def run_dr(ctls, *, until, sxy, syaw_deg, only=None):
    """Real tick() + arm ticks; from each checkpoint stop on, the own report is DR only (last fix before the stop)."""
    for i in range(int(round(until/.1))+1):
        now = round(i*.1, 8)
        for c in ctls:
            if getattr(c, 'checkpoint_fix_after', None) is not None and (only is None or c.rid in only):
                c.port.own.last_report = rep(now, fix_t=c.checkpoint_fix_after-30., sxy=sxy[c.rid],
                                             syaw_deg=syaw_deg[c.rid])
            if c.state not in ('failed', 'released', 'done'):
                c.tick(now)
        for c in ctls:
            if c.state != 'failed':
                c.arm.tick(now)
    return ctls


def test_dr_receipt_resumes_at_high_without_lowering_or_a_reobserve_event():
    _, ctls = pair(segments=(.1, .1))
    run_dr(ctls, until=60., sxy={'r1': .0424, 'r2': .0423}, syaw_deg={'r1': 1.38, 'r2': 1.22})
    for c in ctls:
        assert c.failure is None and c.state == 'released'
        stop = next(e['t'] for e in c.events if e['event'] == 'checkpoint_high_stop')
        got = [e for e in c.events if e['event'] == dc.DR_EVENT]
        assert len(got) == 1 and got[0]['seg'] == 1 and got[0]['t']-stop >= MIN-1e-8
        assert got[0]['std_xy_m'] <= dc.BUDGET_XY_M and got[0]['fix_age_s'] > 30.
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


def test_record_names_the_unchanged_thresholds():
    r = dc.record()
    assert r['budget_xy_m'] == .05 and math.isclose(r['budget_yaw_rad'], math.radians(3.))
    assert r['events'] == [dc.FIX_EVENT, dc.DR_EVENT, dc.OVER_EVENT]
