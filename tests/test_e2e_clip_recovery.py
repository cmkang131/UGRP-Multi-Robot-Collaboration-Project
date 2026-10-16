import copy
from types import SimpleNamespace

import pytest
from harness import e2e_clip_recovery as m
from harness.e2e_carrier_approach import advance
from tests.test_e2e_fine_entry import recorded


def clipped(mode='back3_v1'):
    tr, r = recorded('off')
    tr.approach_commit = 'memory60_view_v1'
    advance(tr, 'r2', 2.)
    tr.clip_recovery = mode
    r.beam = None
    r.last_obs = dict(frame_id=1538, sim_time=3.)
    # r48 v264 s61007 r1 f1538, accepted inspect image (SHA in experiment).
    r.beam_observation = dict(rgb=dict(frame_id=1538, t_sim=3., sha256='a'*64), result=dict(
        visible=True, end_visible=False, reason='BAND_CLIPPED',
        near_end_base_m=[.2081415748, .00955605482], axis_heading_rad=.3529226583,
        band=dict(length_m=.0332, touches_invalid_border=True)))
    return tr, r


def test_recorded_clip_reverses_then_requires_new_settled_rgb_without_ready():
    tr, r = clipped()
    fine, actions = advance(tr, 'r2', 3.)
    assert not fine and not tr.aligned
    assert actions == [dict(kind='mecanum', forward=-.35, left=0., turn=0., duration_s=.1)]
    assert r.carrier_approach['status'] == 'clip_recovery_backup'
    r.last_obs.update(frame_id=1539, sim_time=3.2)
    r.beam_observation['rgb'].update(frame_id=1539, t_sim=3.2)
    assert advance(tr, 'r2', 3.2) == (False, [dict(kind='hold')])
    r.last_obs.update(frame_id=1540, sim_time=3.6)
    r.beam_observation['rgb'].update(frame_id=1540, t_sim=3.6)
    assert advance(tr, 'r2', 3.6)[1][0]['forward'] == -.35
    assert not tr.aligned


@pytest.mark.parametrize('mode,count', [('back3_v1', 3), ('back6_v1', 6)])
def test_episode_bound_and_full_band_clears_attempt(mode, count):
    tr, r = clipped(mode)
    state = tr.approach['r2'];diag = dict(distance_m=.06)
    for i in range(count+1):
        t = 3.+i*.6
        r.last_obs.update(frame_id=1538+i, sim_time=t)
        r.beam_observation['rgb'].update(frame_id=1538+i, t_sim=t)
        result = m.step(tr, 'r2', t, state, diag)
        assert (result is None) == (i == count)
    assert state['clip_recovery_attempt']['count'] == count
    assert state['clip_recovery_attempt']['exhausted']
    r.beam_observation['result']['end_visible'] = True
    assert m.step(tr, 'r2', t, state, diag) is None
    assert 'clip_recovery_attempt' not in state and not tr.aligned


@pytest.mark.parametrize('change', ['off', 'stale', 'closed', 'distant', 'wrong_posture', 'not_clipped', 'wrong_geometry'])
def test_no_recovery_without_fresh_near_open_gripper_clip(change):
    tr, r = clipped();diag = dict(distance_m=.06)
    if change == 'off':tr.clip_recovery = 'off'
    if change == 'stale':r.beam_observation['rgb']['t_sim'] = 2.
    if change == 'closed':r.servo[1] = 1500
    if change == 'distant':diag['distance_m'] = .26
    if change == 'wrong_posture':r.servo[3] = 700
    if change == 'not_clipped':r.beam_observation['result']['reason'] = 'NO_BEAM'
    if change == 'wrong_geometry':r.beam_observation['result']['near_end_base_m'][0] = .5
    assert m.step(tr, 'r2', 3., tr.approach['r2'], diag) is None
    assert not tr.aligned


def test_projection_guard_preserved_and_dev_records_would_stop(monkeypatch):
    import harness.public_navigation.follower as follower
    monkeypatch.setattr(follower, 'projected_clear', lambda *a: False)
    tr, r = clipped();tr.dev_light = False
    assert m.step(tr, 'r2', 3., tr.approach['r2'], dict(distance_m=.06)) == (False, [dict(kind='hold')])
    assert tr.approach['r2']['clip_recovery_attempt']['count'] == 0
    tr.dev_light = True
    assert m.step(tr, 'r2', 3., tr.approach['r2'], dict(distance_m=.06))[1][0]['forward'] < 0
    assert any(e['event'] == 'would_stop_clip_recovery_collision_guard' for e in tr.events)


def test_default_off_and_parent_binding():
    assert m.step(object(), 'r1', 0., {}, {}) is None
    for (mode, parent), version in m.PARENTS.items():
        b=dict(execution_bundle_id=parent, e2e_options={});original=copy.deepcopy(b)
        assert m.compose(b, 'off') == () and b == original
        m.compose(b, mode)
        assert b['execution_bundle_id'] == f'e2e18-v{version}'
        with pytest.raises(ValueError):m.compose(b, mode)
