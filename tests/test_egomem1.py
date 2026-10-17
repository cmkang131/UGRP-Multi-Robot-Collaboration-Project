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


def test_line_inverse_and_jacobian_no_fake_midpoint():
    x = np.array([2., .4, .1, .2, .3])
    z,h = observation_model(x,0,'oriented_line')
    assert np.allclose(z,[2-np.cos(.4)*.1-np.sin(.4)*.2,.1])
    num = np.column_stack([(observation_model(x+np.eye(5)[j]*1e-6,0,'oriented_line')[0]-observation_model(x-np.eye(5)[j]*1e-6,0,'oriented_line')[0])/2e-6 for j in range(5)])
    assert np.allclose(h,num,atol=1e-8)
    o=dict(id='line',kind='zone_boundary',signature='blue',representation='oriented_line',measurement_state=[2.,.4],covariance_m2=np.diag([.01,.01]).tolist())
    m=LandmarkMemory(option=OPTION);m.step(0.,[0,0,0],np.zeros((3,3)),[o])
    result=m.step(1.,[.1,.2,.3],np.zeros((3,3)))
    assert np.allclose(m.x,z)
    assert result['memories'][0]['extent_unknown']


def test_navigation_reacquisition_requires_departure_and_new_rgb():
    from harness.egomem_navigation import MemoryReturn
    c=MemoryReturn(sweep_steps=100,footprint_diameter_m=.4,horizontal_half_fov_rad=.5)
    m=dict(id='m1',kind='zone_boundary',signature='blue',age_s=0.,range_m=1.,bearing_rad=np.pi)
    c.step(0.,[0,0,2*np.pi],[m],[])
    assert c.stage=='depart'
    assert not c.done
    c.step(1.,[1.,0,0],[m],[])
    assert c.departed and not c.done
    m['bearing_rad']=0.
    c.step(2.,[0,0,0],[m],[dict(kind='zone_boundary',signature='blue')])
    assert c.done and c.events[-1]['reason']=='rgb_signature_reacquired'
    assert c.events[-1]['arrival_verified'] is False


def test_observation_schema_blocks_world_fields_and_search_uses_only_hits():
    m=LandmarkMemory(option=OPTION)
    with pytest.raises(ValueError,match='UNEXPECTED_OBSERVATION'):
        m.step(0.,[0,0,0],np.zeros((3,3)),[{**obs([1,0]),'world_pose':[4,5,6]}])
    context=language_context([],scan=dict(columns=[dict(status='unknown',range_m=None),dict(status='hit',range_m=2.,bearing_rad=.2)]),footprint_radius_m=.2)
    assert len(context['candidates'])==1
    assert context['candidates'][0]['minimum_gap_m']==1.8


def test_strict_return_goes_outside_colored_halfplane_and_needs_color_exit():
    from harness.egomem_navigation import MemoryReturn
    c=MemoryReturn(sweep_steps=100,footprint_diameter_m=.4,horizontal_half_fov_rad=.5,strict_return=True)
    m=dict(id='m',kind='zone_boundary',signature='blue',age_s=0.,range_m=.6,bearing_rad=np.pi,measurement_state=[-.6,0.],appearance_hue=107.)
    action=c.step(0.,[0,0,2*np.pi],[m],[],colour_pixels=1000)
    assert c.goal_range==.8 and action[2]>0  # depart outward -normal, not into colored side
    m['measurement_state'][1]=np.pi;m['bearing_rad']=np.pi
    c.step(1.,[0,0,0],[m],[],colour_pixels=1000)
    c.step(2.,[1.,0,0],[m],[],colour_pixels=1000)
    assert c.stage=='depart' and not c.done  # missing boundary is insufficient
    c.step(3.,[0,0,0],[m],[],colour_pixels=0)
    assert c.stage=='return'
    m['bearing_rad']=0.
    c.step(4.,[0,0,0],[m],[dict(kind='zone_boundary',signature='blue')],colour_pixels=1000)
    assert c.done
