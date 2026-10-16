"""Compute-budget boundaries and geometry; no physics/render/provider."""
from types import SimpleNamespace

import numpy as np
import pytest

from harness.e2e_speed4 import OFF, Options, current, processing_due, using


def test_options_default_off_and_scoped():
    assert not OFF.enabled
    with using(Options(floor_ray_stride=2)):
        assert current().floor_ray_stride == 2
    assert current() == OFF
    for opts in ({'rbpf_particles': 1}, {'floor_ray_stride': True}, {'render_half': 1}):
        with pytest.raises(ValueError):
            Options(**opts)


@pytest.mark.parametrize('servo', [
    {1:2000,3:740,4:2320,5:1320,6:1500},
    {1:2000,3:1100,4:2000,5:1400,6:1100},
    {1:1800,3:1400,4:1800,5:1100,6:1900}])
def test_vector_envelope_preserves_projected_masks(servo):
    from harness.floor_goal_self_mask import body_envelopes, _project_envelopes
    from harness.active_camera import goal_camera
    origin, axes = goal_camera(servo, 'camera_v3')
    geometry = list(body_envelopes(servo, 'camera_v3'))
    a = _project_envelopes(geometry, origin, axes, 640, 480)
    with using(Options(vector_envelopes=True)):
        b = _project_envelopes(geometry, origin, axes, 640, 480)
    np.testing.assert_array_equal(a, b)


def test_observation_cadence_keeps_turn_stop_servo_and_transport_fresh():
    r = SimpleNamespace(speed4=Options(moving_observation_stride=2),
                        last_obs={'sim_time':1.}, packet=None,
                        nav_command=dict(kind='mecanum',forward=.35,left=0.,turn=0.))
    assert processing_due(r, 1.2, 'mapping')  # suggested motion is not an issued command
    r._speed4_last_motion = dict(r.nav_command)
    assert not processing_due(r, 1.2, 'mapping')
    assert processing_due(r, 1.4, 'mapping')
    assert processing_due(r, 1.2, 'carrying')
    r._speed4_servo_changed = True
    assert processing_due(r, 1.2, 'mapping')
    r.nav_command['turn'] = .1
    assert processing_due(r, 1.2, 'mapping')
    r.goal = SimpleNamespace(e2e_vo=object())
    r.nav_command['turn'] = 0.
    assert processing_due(r, 1.2, 'mapping')
    r.nav_command = {'kind':'hold'}
    assert processing_due(r, 1.2, 'mapping')


def test_pixel_budget_adapter_does_not_change_camera_or_physics():
    from sim.e2e_speed4 import dimensions, install
    calls = []
    native = np.zeros((240,320,3),np.uint8)
    world = SimpleNamespace(_render_rgb_direct=lambda robot, camera: calls.append((robot,camera)) or native)
    assert dimensions({}) == (640,480)
    b = {'speed4':{'render_half':True}}
    assert dimensions(b) == (320,240)
    install(world,b)
    assert world._render_rgb_direct('r1','robot_cam').shape == (480,640,3)
    assert calls == [('r1','robot_cam')]
    assert world._render_rgb_direct('r1','nav_cam') is native


def test_particle_budget_and_wall_endpoints_are_independent(monkeypatch):
    from harness import active_wall_mapping as m
    from harness.self_map_rbpf import RBPFOptions
    with pytest.raises(ValueError, match='30_OR_100'):
        RBPFOptions(particles=50)
    with using(Options(rbpf_particles=50)):
        assert RBPFOptions(particles=50).particles == 50
    with pytest.raises(ValueError, match='30_OR_100'):
        RBPFOptions(particles=50)
    captured = []
    monkeypatch.setattr(m, 'receive_rays', lambda *a: captured.append(a[3]))
    monkeypatch.setattr(m, 'clear_current_footprint', lambda *a: None)
    mapper = SimpleNamespace(robot_id='r1',grid=None,latest={})
    row = dict(segments=[[[.2,0],[.2,1]]], floor_xy=[[i*.01,.1] for i in range(20)],
               camera=[0.,0.],frame_id=1)
    m.ActiveMapper._rays(mapper,row,[0,0,0])
    with using(Options(floor_ray_stride=2)):
        m.ActiveMapper._rays(mapper,row,[0,0,0])
    np.testing.assert_array_equal(captured[0]['wall_xy'], captured[1]['wall_xy'])
    assert len(captured[1]['floor_xy']) == 10


def test_new_robot_gets_particle_budget_without_global_mutation(monkeypatch):
    pytest.importorskip('mujoco', exc_type=ModuleNotFoundError)
    pytest.importorskip('matplotlib', exc_type=ModuleNotFoundError)
    from scripts.replay_e2e_receive_speed import build_robots
    from harness import e2e_live_mapping as mapping
    original = mapping.Robot
    monkeypatch.setattr(mapping, 'Robot', lambda *a, **kw: original(*a, **kw, speed4=Options(rbpf_particles=50)))
    robots, _ = build_robots({})
    assert all(len(r.goal.explorer.memory.self_map.poses) == 50 for r in robots.values())
    from harness.active_wall_mapping import OPTIONS
    assert OPTIONS['pose_correction_options']['particles'] == 100


def test_door_pair_filter_keeps_scalar_candidates_and_order():
    import math
    from harness.e2e_speed4 import door_pair_indices
    rng = np.random.default_rng(104)
    starts = rng.integers(-50,50,(150,2))
    delta = rng.integers(-10,10,(150,2))
    delta[np.all(delta==0,axis=1)] = [1,0]
    lines = np.stack((starts,starts+delta),axis=1)
    for i,a in enumerate(lines):
        va = a[1]-a[0];va=va/np.linalg.norm(va)
        normal=np.array([-va[1],va[0]]);expected=[]
        for j in range(i+1,len(lines)):
            b=lines[j];vb=b[1]-b[0];vb=vb/np.linalg.norm(vb)
            if abs(np.dot(va,vb)) < math.cos(math.radians(10)):continue
            if max(abs((b-a[0])@normal))*.05 > .15:continue
            expected.append(j)
        assert door_pair_indices(lines,i,.05).tolist()==expected


def test_vector_door_updates_preserve_real_grid_outputs(monkeypatch):
    import cv2
    from harness.own_map_navigation import ObservedGrid, DoorMemory
    grid=ObservedGrid('r1',.05)
    grid.initial_support()
    lines=np.array([[[2,2],[2,8]],[[2,16],[2,25]],[[6,2],[6,8]],[[6,16],[6,25]],[[20,20],[30,20]]])
    monkeypatch.setattr(cv2,'HoughLinesP',lambda *a,**kw:lines[:,None].reshape(-1,1,4))
    a=DoorMemory('r1');expected=a.update(grid,[0,0,0])
    b=DoorMemory('r1')
    with using(Options(vector_door_pairs=True)):
        got=b.update(grid,[0,0,0])
    assert got==expected and b.tracks==a.tracks
