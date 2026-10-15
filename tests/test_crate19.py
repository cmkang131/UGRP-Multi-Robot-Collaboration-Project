"""Retained-error fixture, OFF parity, visibility reset; no physics/render."""
import pytest
from sim.crate_settle_v19 import RetainedErrorSettler, settlers, compensated_pulse, WINDOW
from sim.crate_settle_v18 import DELTA, INNER18, pulse
from test_crate18 import make
from test_crate15 import empty, hold


def test_rebound_fixture_accepts_after_six_issued_pulses_only():
    s=settlers()[0]
    # Error rebounds between commands despite temporarily entering the band.
    for i in range(WINDOW):
        q=s.observe(.002392,DELTA[0])
        assert not q['settled']
        s.issued(.002392)
        assert s.observe(.00075,DELTA[0])['settled']
    state=s.observe(.002392,DELTA[0])
    assert state['settled'] and state['reason']=='same_sign_retained_error'
    assert state['tolerance']>=.6*DELTA[0] and state['acceptance_band']<=2*state['tolerance']
    assert not s.observe(.005,DELTA[0])['settled']


def test_passive_samples_and_progress_never_trigger_compensation():
    for s in (settlers()[0],settlers()[0]):
        for _ in range(100): assert not s.observe(.01,DELTA[0])['settled']
        assert s.boost==s.pulses==0
    s=settlers()[0]
    for i in range(WINDOW):
        e=.02-i*.001;s.observe(e,DELTA[0]);s.issued(e)
    assert s.boost==0 and not s.stagnant


def test_large_stagnation_boosts_with_bounded_pulse_and_sign_flip_resets():
    s=settlers()[0]
    for _ in range(30):s.observe(.01,DELTA[0]);s.issued(.01)
    assert s.band is None and s.boost==3
    c=compensated_pulse(hold(),0,.01,s)
    assert .025<max(c['duration_s'])<=.1
    s.issued(-.01);assert s.boost==0


def test_common_three_reversals_unchanged():
    s=settlers()[2]
    for e in (.018,-.018,.018):
        assert not s.observe(e,DELTA[2])['settled'];s.issued(e)
    assert s.observe(-.018,DELTA[2])['reason']=='consecutive_reversals'


def test_geometry_guard_and_missing_view_clear_compensation():
    t=make();t.crate19='crate19_v1';t._reset_alignment();w=empty()
    for _ in range(WINDOW):t.settlers18[0].issued(.002392)
    assert t.settlers18[0].band is not None
    w['beam']['ends']['teal'][2]=-.5
    assert not t.ready_geometry(w)
    w['beam']=None;w['visibility']['r1']['visible_probes']=0
    t._observe_stable(w,1.)
    assert all(s.band is None and s.boost==0 for s in t.settlers18)


def test_off_is_identical_to_crate18_pulse():
    t=make()
    for axis in range(3):
        t.phase='align';t.crate15_errors=[.01]*3
        v=[0]*3;v[axis]=1
        assert t._continuous(1.,*v)==pulse(t._hold(1.),axis,.01)


def test_requires_crate18():
    from scripts.run_crate_teacher import make_grasp_teacher
    with pytest.raises(ValueError,match='requires crate18'):
        make_grasp_teacher('r1','teal',{},crate19='crate19_v1')
