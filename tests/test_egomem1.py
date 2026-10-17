import numpy as np
import pytest
from harness.egocentric_landmark_memory import LandmarkMemory, OPTION, relative, observation_model, language_context


def obs(xy, name='blue', ident='o'):
    return dict(id=ident, kind='zone_corner', signature=name, relative_xy_m=xy, covariance_m2=(np.eye(2)*.04).tolist())


def test_inverse_translation_turn_and_shared_covariance():
    m = LandmarkMemory(option=OPTION)
    m.step(0., [0,0,0], np.zeros((3,3)), [obs([2,1]), obs([-1,2], 'red')])
    before = m.x.copy()
    m.step(1., [.1,.2,.3], np.diag([.01,.02,.03]))
    assert np.allclose(m.x.reshape(-1,2), [relative(x,[.1,.2,.3]) for x in before.reshape(-1,2)])
    assert np.linalg.norm(m.p[:2,2:]) > 0  # common motion noise cannot be dropped
    assert np.linalg.eigvalsh(m.p).min() >= 0


def test_jacobian_against_finite_difference():
    x = np.array([2.,1.,-1.,2.,.1,.2,.3]); _, h = observation_model(x,0)
    numerical = np.column_stack([(observation_model(x+np.eye(len(x))[j]*1e-6,0)[0]-observation_model(x-np.eye(len(x))[j]*1e-6,0)[0])/2e-6 for j in range(len(x))])
    assert np.allclose(numerical,h,atol=1e-8)


def test_reobserve_reduces_error_and_covariance_without_world_pose():
    m = LandmarkMemory(option=OPTION)
    m.step(0., [0,0,0], np.zeros((3,3)), [obs([2,0])])
    predicted = m.step(1., [.4,0,0], np.diag([.1,.1,.01]))
    old_error = abs(predicted['memories'][0]['relative_xy_m'][0]-1.8)
    p = m.p.copy()
    result = m.step(2., [0,0,0], np.zeros((3,3)), [obs([1.8,0])])
    assert abs(m.x[0]-1.8) < old_error
    assert np.trace(m.p) < np.trace(p)
    assert result['memories'][0]['observations'] == 2
    assert result['self_pose'] == [0,0,0]


def test_ambiguity_duplicate_and_off_fail_closed():
    m = LandmarkMemory(option=OPTION)
    m.step(0., [0,0,0], np.zeros((3,3)), [obs([2,0]), obs([2.1,0],ident='p')])
    r = m.step(1., [0,0,0], np.zeros((3,3)), [obs([2,0])])
    assert any(e['reason']=='association_ambiguous' for e in r['events'])
    assert LandmarkMemory().step(0.,[0,0,0],np.zeros((3,3)),[obs([1,0])])['memories'] == []
    with pytest.raises(ValueError): m.step(1., [0,0,0], np.zeros((3,3)))
    with pytest.raises(ValueError): LandmarkMemory(option=OPTION).step(0., [0,0,0], -np.eye(3))


def test_llm_prefix_stable_and_unknown_goal_search_only():
    a = language_context([],goal_signature='blue')
    m = LandmarkMemory(option=OPTION)
    r = m.step(0.,[0,0,0],np.zeros((3,3)),[obs([2,1])])
    b = language_context(r['memories'],goal_signature='blue')
    assert a['fixed_prefix'] == b['fixed_prefix']
    assert a['candidates'][0]['action'] == 'look_left'
    assert b['candidates'][0]['arrival_verified'] is False
