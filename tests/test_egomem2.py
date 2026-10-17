"""Object persistence and direct upstream 1:1 association; no sim/render."""
import math
import numpy as np
import pytest

from harness.egocentric_landmark_memory import LandmarkMemory, MemoryOptions, OPTION
from harness.egomem_object_association import PROFILE, assign
from scripts.build_egomem_rovio_statistics import build


@pytest.fixture(scope='module')
def library(tmp_path_factory):
    path=tmp_path_factory.mktemp('egomem2')/'rovio.so';build(path);return str(path)


def obs(x, name='blue', ident='o'):
    return dict(id=ident,kind='zone_corner',signature=name,relative_xy_m=x,
                covariance_m2=(np.eye(2)*.04).tolist())


def mem(library, **kw):
    return LandmarkMemory(option=OPTION,options=MemoryOptions(
        implementation=PROFILE,statistics_library=library,**kw))


def test_upstream_gnn_joint_assignment_avoids_greedy_collision():
    # Greedy detection0 -> memory0 would force memory1 -> cost8; global is3.
    assert assign([[1,2],[1,8]],[[0,0],[1,1]],[np.eye(2)]*2,0.,9.21)=={1:0,0:1}


def test_out_of_view_persists_native_stats_still_age(library):
    m=mem(library);m.step(0.,[0,0,0],np.zeros((3,3)),[obs([2,0])])
    for t in range(1,120):
        result=m.step(float(t),[0,0,.01],np.diag([.001,.001,.001]))
    assert len(m.items)==1 and m.items[0]['id']=='m1'
    assert result['memories'][0]['tracking_statistics']['local_visibility']<.9
    assert not any(e['reason'].endswith('_removed') for e in result['events'])
    assert result['self_pose']==[0.,0.,0.]


def test_same_frame_duplicate_does_not_create_or_double_update(library):
    m=mem(library)
    result=m.step(0.,[0,0,0],np.zeros((3,3)),[obs([2,0]),obs([2.01,0],ident='p')])
    assert len(m.items)==1
    assert result['events'][-1]['reason']=='same_frame_birth_suppressed'
    result=m.step(1.,[0,0,0],np.zeros((3,3)),[obs([2,0]),obs([2.01,0],ident='p')])
    assert len(m.items)==1 and m.items[0]['observations']==2
    assert sum(e['reason']=='reobserved' for e in result['events'])==1


def test_distinct_same_color_landmarks_and_resource_cap(library):
    m=mem(library,max_landmarks=2)
    m.step(0.,[0,0,0],np.zeros((3,3)),[obs([1,0]),obs([4,0],ident='far')])
    result=m.step(1.,[0,0,0],np.zeros((3,3)),[obs([1.01,0]),obs([4.01,0],ident='far')])
    assert len(m.items)==2 and sum(e['reason']=='reobserved' for e in result['events'])==2
    result=m.step(2.,[0,0,0],np.zeros((3,3)),[obs([-4,0],'red')])
    assert len(m.items)==2 and any(e['reason']=='memory_slot_evicted' for e in result['events'])


def test_wrapped_line_angle_and_forbidden_fields(library):
    o=dict(id='line',kind='zone_boundary',signature='blue',representation='oriented_line',
           measurement_state=[1.,math.pi-.01],covariance_m2=np.diag([.04,.01]).tolist())
    m=mem(library);m.step(0.,[0,0,0],np.zeros((3,3)),[o])
    result=m.step(1.,[0,0,0],np.zeros((3,3)),[{**o,'measurement_state':[1.,-math.pi+.01]}])
    assert len(m.items)==1 and any(e['reason']=='reobserved' for e in result['events'])
    with pytest.raises(ValueError,match='UNEXPECTED_OBSERVATION'):
        m.step(2.,[0,0,0],np.zeros((3,3)),[{**o,'spawn':[1,2]}])


def test_return_cannot_finish_by_only_turning_toward_color():
    from harness.egomem_navigation import MemoryReturn
    c=MemoryReturn(sweep_steps=100,footprint_diameter_m=.4,horizontal_half_fov_rad=.5,
                   strict_return=True,translated_return=True)
    m=dict(id='m',kind='zone_boundary',signature='blue',age_s=0.,range_m=.6,
           bearing_rad=math.pi,measurement_state=[-.6,0.],appearance_hue=107.)
    c.step(0.,[0,0,2*math.pi],[m],[],colour_pixels=1000)
    m['measurement_state'][1]=math.pi
    c.step(1.,[0,0,0],[m],[],colour_pixels=0)
    c.step(2.,[1.,0,0],[m],[],colour_pixels=0)
    m['bearing_rad']=0.
    o=[dict(kind='zone_boundary',signature='blue')]
    c.step(3.,[0,0,0],[m],o,colour_pixels=1000)
    assert not c.done and c.return_moving
    c.step(4.,[.4,0,0],[m],o,colour_pixels=1000)
    assert c.done and c.events[-1]['own_return_path_m']==pytest.approx(.4)


def test_full_denominator_quantile_includes_missing_mass():
    from scripts.egomem2_compare import stats
    r=stats([.1,.2],10)
    assert r['coverage']==.2 and r['full_denominator_p95_m'] is None


def test_observed_patch_hint_transports_separately_from_infinite_line(library):
    from harness.egocentric_landmark_memory import relative
    o=dict(id='line',kind='zone_boundary',signature='blue',representation='oriented_line',
           measurement_state=[1.,math.pi/2],covariance_m2=np.diag([.01,.01]).tolist(),
           observed_endpoints_m=[[1.,1.],[2.,1.]])
    m=mem(library);first=m.step(0.,[0,0,0],np.zeros((3,3)),[o])['memories'][0]
    assert np.allclose(first['navigation_hint_relative_xy_m'],[1.5,1.])
    assert not np.allclose(first['relative_xy_m'],first['navigation_hint_relative_xy_m'])
    delta=np.array([.2,0,.3]);last=m.step(1.,delta,np.zeros((3,3)),observation_tick=False)['memories'][0]
    assert np.allclose(last['navigation_hint_relative_xy_m'],relative([1.5,1.],delta))
    assert last['navigation_hint_status'].endswith('uncertainty_unqualified')


def test_observed_goal_does_not_turn_back_when_line_foot_flips():
    from harness.egomem_navigation import MemoryReturn
    c=MemoryReturn(sweep_steps=100,footprint_diameter_m=.4,horizontal_half_fov_rad=.5,
                   strict_return=True,translated_return=True,observed_segment_aim=True)
    m=dict(id='m',kind='zone_boundary',signature='blue',age_s=0.,range_m=.6,
           bearing_rad=0.,measurement_state=[-.6,math.pi],appearance_hue=107.,
           navigation_hint_relative_xy_m=[2.,0.])
    c.step(0.,[0,0,2*math.pi],[m],[],colour_pixels=1000)
    c.step(1.,[1.,0,0],[m],[],colour_pixels=0)
    # A line foot jumps behind at rho=0. The measured patch remains ahead.
    m['bearing_rad']=math.pi;m['measurement_state'][0]=.4
    o=[dict(kind='zone_boundary',signature='blue')]
    action=c.step(2.,[.1,0,0],[m],o,colour_pixels=1000)
    assert action==[.35,0.,0.] and not c.done
    c.step(3.,[.3,0,0],[m],o,colour_pixels=1000)
    assert c.done and c.return_path==pytest.approx(.4)
