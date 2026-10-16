import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from harness.active_wall_mapping import active_output,ActiveMapper,pulse_command,compose,inverse
from harness.active_camera import servo_output,SEARCH,LOOK_AHEAD,pitch,goal_camera,goal_detector
from harness.self_pulse_odom import PulseOdometry,profile_key,model
from harness.self_wall_memory_robust import SelfWallMemory
from harness.active_information_gain import forecast,sample_path,pose_entropy,cast
from harness.self_odom_grid import OdomGrid

ROOT=Path(__file__).resolve().parents[1]


def test_off_is_exact_passthrough_and_source_copies_are_frozen():
    value=b'legacy\r\n\x00'
    assert active_output(value) is value
    assert servo_output(value) is value
    record=json.loads((ROOT/'experiments/2026-10-07-active-wall-map/navigation-source.json').read_text())
    for name,digest in record['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name


def test_camera_uses_commands_and_same_optical_axis():
    assert -10<pitch(LOOK_AHEAD)<-5
    assert abs(pitch(SEARCH)+18.08)<1e-9
    assert servo_output(SEARCH,camera_pose='look_ahead_v1')==LOOK_AHEAD
    origin,axes=goal_camera(LOOK_AHEAD,'camera_v3')
    from harness.active_camera import transform
    o,R=transform(LOOK_AHEAD)
    np.testing.assert_array_equal(origin,o)
    np.testing.assert_array_equal(axes,R.T)
    # New camera injection never edits the v3 original function globals.
    from harness.floor_goal_v3 import detect_floor_v3
    assert goal_detector().__code__ is detect_floor_v3.__code__
    assert goal_detector().__globals__['commanded_camera'] is not detect_floor_v3.__globals__['commanded_camera']


def test_pulse_requests_are_calibrated_include_stop_and_preserve_se2():
    for twist in ([.12,0,0],[0,0,.5],[0,0,-.5],[-.12,0,0],[0,.1,0]):
        cmd,diagnostic=pulse_command(twist,0.)
        if cmd['kind']=='mecanum':
            assert profile_key(cmd,False) in model()['profiles']
            odom=PulseOdometry()
            odom.command(cmd)
            np.testing.assert_allclose(odom.advance(.2),diagnostic['predicted_delta'],atol=1e-12)
    cmd,_=pulse_command([0,0,0],0.)
    assert cmd['kind']=='hold'
    p=np.array([1.,-2.,.8])
    np.testing.assert_allclose(compose(p,inverse(p)),0,atol=1e-12)


def test_finite_pulse_collision_stops_and_does_not_invent_gain():
    class Closed:
        def pose_clear(self,p):return False
    cmd,_=pulse_command([.12,0,0],0,costmap=Closed(),pose=[0,0,0])
    assert cmd['kind']=='hold'
    cloud=np.array([[0.,0.,0.],[.2,0,.1]])
    assert pose_entropy(cloud,np.array([.5,.5]))>pose_entropy(cloud*.1,np.array([.5,.5]))
    path=sample_path([[0,0],[.1,0],[.2,0],[1,0]],0)
    np.testing.assert_allclose(path[:,0],[0,.5,1])


def test_forecast_copy_does_not_mutate_real_filter_or_rng():
    memory=SelfWallMemory('r3',self_map='odom_grid_v1',pose_correction='own_map_rbpf_v1',
                          pose_correction_options={'particles':30},motion_model='s2_pulse_v122')
    grid=memory.self_map
    before=json.dumps(grid.export(),sort_keys=True)
    rng=json.dumps(grid.rng.bit_generator.state,sort_keys=True)
    result=forecast(grid,[[0,0],[.5,0]],seed=1)
    assert np.isfinite(result['utility']) and result['unknown_cells']>0
    assert before==json.dumps(grid.export(),sort_keys=True)
    assert rng==json.dumps(grid.rng.bit_generator.state,sort_keys=True)


def test_empty_camera_abstains_from_free_space_and_rejects_peer():
    from harness.active_wall_vision import observe
    rgb=np.zeros((480,640,3),np.uint8)
    detection=observe(rgb,LOOK_AHEAD)
    assert not detection['segments'] and not detection['floor_xy']
    actor=ActiveMapper('r3',0.,LOOK_AHEAD,active_mapping='frontier_rbpf_v1')
    with pytest.raises(ValueError,match='PEER'):
        actor.receive(robot_id='r2',t=1.,frame_id=1,rgb=rgb,servo=LOOK_AHEAD,observation=detection)
    command,trace=actor.receive(robot_id='r3',t=2.,frame_id=1,rgb=rgb,servo=LOOK_AHEAD,observation=detection)
    assert trace['map_cells']>0 and trace['wall_segments']==0
    assert command['kind'] in ('mecanum','hold')
    assert not actor.grid.floor_frames # footprint support isn't observed coverage


def test_original_navfn_reaches_observed_frontier_on_connected_free_rays():
    from harness.public_navigation_monitor import MonitorNavigator
    from harness.public_navigation_unknown import from_observed_grid,clear_current_footprint
    from harness.public_navigation_raytrace import receive_rays
    from harness.own_map_navigation import ObservedGrid
    grid=ObservedGrid('r3')
    latest={}
    floor=np.array([[x,y] for x in np.arange(.2,2.,.1) for y in np.arange(-.8,.8,.1)])
    receive_rays(grid,latest,set(),dict(robot_id='r3',frame_id=0,floor_xy=floor,wall_xy=[],
      floor_origins_xy=np.tile([.12,0],(len(floor),1)),wall_origins_xy=[]),[0,0,0])
    clear_current_footprint(grid,latest,set(),[0,0,0])
    cost=from_observed_grid(grid,[0,0,0],latest,set())
    nav=MonitorNavigator()
    result=nav.update(cost,np.zeros(3),0.)
    assert result['path_m'] and result['status']=='public_frontier'
