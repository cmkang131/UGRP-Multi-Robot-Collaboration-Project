"""Behavior and input boundaries for the default-off ROS v3 port; no simulator."""
import ast
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from harness.public_navigation.native import ROOT
from harness.public_navigation.costmap import Costmap
from harness.public_navigation_persistent import (
    PersistentActor, PersistentNavigator, ProgressChecker, navigation_output_v3, raytrace_cells)
from harness.own_map_navigation import ObservedGrid

CODE = ROOT/'experiments/2026-10-07-mapfree-navigation-persistence/code'
sys.path.insert(0, str(CODE))
from run_persistent import development_pass, verify_development, cohort, hashes
from contact_world import ContactWorld


def actor():
    return PersistentActor('own_frontier', navigation='public_ros_v3')


def observation(frame, free=(), hits=()):
    return dict(robot_id='r1', frame_id=frame, floor_xy=free, wall_xy=hits, floor_source='floor_visible')


def test_default_off_golden_and_legacy_source_bytes():
    for p in (ROOT/'tests/fixtures/floor_goal').glob('*.json'):
        raw = p.read_bytes()
        assert navigation_output_v3(raw) is raw
    with pytest.raises(ValueError):
        PersistentActor('own_frontier')
    with pytest.raises(ValueError):
        navigation_output_v3(None, navigation='public_ros_v2')
    import subprocess
    files = ['harness/public_navigation_recovery.py', 'harness/public_navigation/stack.py',
             'harness/public_navigation/actor.py', 'harness/public_navigation/costmap.py',
             'experiments/2026-10-07-mapfree-navigation-recovery/cohort.json']
    for name in files:
        original = subprocess.check_output(['git','show','6ae4c5a7:'+name], cwd=ROOT)
        assert (ROOT/name).read_bytes() == original


def test_progress_checker_rotation_jitter_active_clock_and_reset():
    p = ProgressChecker()
    assert p.check([0,0,0], 0)
    assert p.check([.49,0,3], 10)
    assert not p.check([.49,0,-3], 10.1)
    assert p.check([.501,0,0], 10.2)
    assert p.check([.501,0,0], 20.2)
    assert not p.check([.501,0,0], 20.21)
    p.reset()
    assert p.check([0,0,0], 100)
    nav = PersistentNavigator()
    nav.checker.check([0,0,0], nav.active_t)
    nav.advance_phase([0,0,0], 600.)  # camera hold is not FollowPath execution
    assert nav.active_t == 0.


def test_recovery_success_only_retry_failure_next_child_and_pinned_finite_rr():
    nav = PersistentNavigator()
    nav.static_mode = True
    nav.failure(0, 'controller_no_progress')
    assert nav.phase == 'context_clear' and nav.retry == 0
    nav.phase_result(1, True)
    nav.failure(2, 'controller_no_progress')
    assert nav.phase == 'clear' and nav.retry == 0
    nav.phase_result(3, True)
    assert nav.retry == 1 and nav.round_index == 1
    nav.failure(4, 'controller_no_progress')
    nav.phase_result(5, True)
    nav.failure(6, 'controller_no_progress')
    assert nav.phase == 'spin'
    nav.phase_result(7, False)
    assert nav.phase == 'wait' and nav.retry == 1
    nav.phase_result(12, True)
    assert nav.retry == 2
    nav.failure(13, 'controller_no_progress')
    nav.phase_result(14, True)
    nav.failure(15, 'controller_no_progress')
    assert nav.phase == 'backup'
    nav.phase_result(17, True)
    # Exact pinned RoundRobin.cpp early break, even final-child SUCCESS.
    assert nav.failed and nav.retry == 2
    assert nav.events[-1]['cause'] == 'round_robin_exhausted'


def test_aborted_frontier_blacklisted_next_goal_not_permanent_failed():
    nav = PersistentNavigator()
    cm = Costmap(np.zeros((60,60),np.uint8), [-3,-3])
    nav.frontier, nav.target = np.array([1.,0]), np.array([.8,0])
    nav.action_failed(10, 'recovery_exhausted')
    assert not nav.failed and nav.blocked([1.,0], .1)
    nav.core = SimpleNamespace(frontiers=lambda *_: np.array([[1,0,1,0,1,3,0],[-1,0,-1,0,1,3,1]]))
    nav.plan_to = lambda _cm,p,t: [list(p[:2]),list(t)]
    nav.update(cm, np.zeros(3), 11)
    assert np.allclose(nav.frontier, [-1,0])
    static = PersistentNavigator()
    static.static_mode = True
    static.target = np.array([1.,0])
    static.action_failed(10, 'recovery_exhausted')
    assert static.failed and not static.blacklist


def test_frontier_min_distance_timeout_blacklist_and_immediate_next():
    nav = PersistentNavigator()
    nav.frontier = np.array([1.,0])
    nav.target = np.array([.8,0])
    nav.best_distance, nav.last_progress = 1., 0.
    nav.core = SimpleNamespace(frontiers=lambda *_: np.array([[1,0,1,0,1,3,0],[-1,0,-1,0,2,3,1]]))
    nav.plan_to = lambda _cm,p,t: [list(p[:2]),list(t)]
    cm = Costmap(np.zeros((60,60),np.uint8), [-3,-3])
    nav.update(cm, np.zeros(3), 31)
    assert nav.blocked([1,0],.1) and np.allclose(nav.frontier,[-1,0])
    assert any(e['reason']=='progress_timeout_blacklist' for e in nav.events)


def test_nav2_raytrace_tie_and_endpoint():
    assert list(raytrace_cells((0,0),(4,2))) == [(0,0),(1,1),(2,1),(3,2),(4,2)]
    assert list(raytrace_cells((0,0),(0,0))) == [(0,0)]
    assert list(raytrace_cells((0,0),(-2,-4))) == [(0,0),(-1,-1),(-1,-2),(-2,-3),(-2,-4)]


def test_obstacle_out_of_view_clear_ray_hit_precedence_and_footprint():
    a = actor()
    a.receive(observation(0, hits=[[.75,.05],[.05,.05]]), [])
    distant, inside = (7,0), (0,0)
    a.t = 1.
    a.receive(observation(1, free=[[0,1]]), [])
    a.clear_obstacles()
    a.plan()
    assert a.latest[distant] and a.latest[inside]
    cell = a.costmap.world_to_map([.05,.05])
    assert a.costmap.raw[cell[1],cell[0]] == 0  # derived footprint only
    assert a.grid.odds[inside] > 0  # memory retained
    a.t = 2.
    a.receive(observation(2, free=[[.75,.05]], hits=[[.75,.05]]), [])
    assert a.latest[distant]
    a.t = 3.
    a.receive(observation(3, free=[[.75,.05]]), [])
    assert not a.latest[distant]
    a.t = 4.
    a.receive(observation(4, hits=[[.95,.05]]), [])
    # Wall endpoints alone are NOT floor evidence along the ray.
    assert (8,0) not in a.latest
    with pytest.raises(ValueError, match='DUPLICATE'):
        a.receive(observation(4), [])


def test_static_layer_preserved_after_clear():
    grid = ObservedGrid('r1')
    grid.odds[(0,0)] = 4.
    a = PersistentActor('static_map',grid,[1,1],navigation='public_ros_v3')
    a.clear_obstacles()
    a.plan()
    ij = a.costmap.world_to_map([.05,.05])
    assert a.costmap.raw[ij[1],ij[0]] == 254


def test_binary_contact_only_no_pose_correction_and_bounded_backup():
    a = actor()
    before = np.array(a.odom.pose)
    with pytest.raises(ValueError,match='BINARY_CONTACT_ONLY'):
        a.receive_contact(dict(t=0.,pressed=True,object_xy=[1,2]))
    assert a.receive_contact(dict(t=0.,pressed=True))
    assert np.array_equal(a.odom.pose,before)
    assert a.navigator.phase == 'contact_backup'
    assert not a.receive_contact(dict(t=0.,pressed=True))
    cm = Costmap(np.zeros((60,60),np.uint8), [-3,-3])
    cmd = a.navigator.command(cm,before,a.navigator.idle(before,'x'),0.)
    from harness.public_navigation_recovery import issued_twist
    assert issued_twist(cmd)[0] < 0
    a.navigator.advance_phase([-.30,0,0], 2.)
    assert a.navigator.phase is None
    assert any(e['reason']=='contact_replan' for e in a.navigator.events)


def test_contact_world_stops_before_penetration_counts_contact_releases_away():
    w = object.__new__(ContactWorld)
    w.pose = np.zeros(3)
    w.motion_rng = np.random.default_rng(1)
    w.motion = SimpleNamespace(t=0.)
    w.rects = [dict(id='unseen',center=[.25,0],half=[.05,.05],yaw=0.)]
    w.static = dict(bounds_m=[-3,3,-3,3])
    w.bumper_pressed = False
    w.collisions = 0
    w.contact_events = []
    w.distance = 0.
    w.path = []
    w._motion_step(np.array([.1,0,0]), np.zeros(3))
    assert w.collisions == 1 and np.allclose(w.pose,0)
    assert w.contact_sample(1) == dict(t=1.,pressed=True)
    w._motion_step(np.zeros(3),np.zeros(3))
    assert w.contact_sample(2)['pressed']
    w._motion_step(np.array([-.1,0,0]),np.zeros(3))
    assert w.collisions == 1 and not w.contact_sample(3)['pressed']
    assert w.pose[0] == -.1


def test_development_gate_cannot_open_32_on_six_valid_failures(tmp_path):
    rows=[]
    for i,s,seed in cohort('diagnostic'):
        setup = (i,s) in {(1,'H'),(4,'H')}
        rows.append(dict(scenario=f's{i}',start=s,seed=seed,status='HOST_SETUP_ERROR' if setup else 'B_confirmed',
                         first_B=None if setup else dict(true=True),collisions=0,navigation_events={}))
    assert development_pass(rows)
    rows[-1]['status']='recovery_exhausted'
    assert not development_pass(rows)
    assert not development_pass(rows[:-1])
    with pytest.raises(ValueError,match='DEVELOPMENT_GATE_REQUIRED'):
        verify_development(None,{})


def test_pinned_sources_actor_boundary_and_hashes():
    for row in json.loads((ROOT/'third_party/mapfree_navigation_persistence/SOURCES.json').read_text())['files']:
        assert hashlib.sha256((ROOT/row['file']).read_bytes()).hexdigest()==row['sha256']
    source = (ROOT/'harness/public_navigation_persistent.py').read_text()
    tree = ast.parse(source)
    names=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    names += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert not any(any(x in n for x in ('mujoco','grid_world','contact_world','cohort','run_grid','openai','genai')) for n in names)
    h = hashes()
    assert 'harness/public_navigation_persistent.py' in h
    assert 'experiments/2026-10-07-mapfree-navigation-persistence/code/contact_world.py' in h
