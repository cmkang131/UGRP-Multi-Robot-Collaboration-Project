import json
import math
from pathlib import Path
import sys

import numpy as np

from harness.own_map_navigation import ObservedGrid, OwnMapNavigator, NavigationOptions, Footprint, footprint_clearance
from harness.own_map_navigation_v2 import OwnMapNavigatorV2, footprint_cells, pose_clear, segment_clear

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-explore/code'))
from navigation_actor_v2 import ActorV2, OPTIONS_V2
from grid_world import GridWorld
from run_grid import STARTS, motion_profiles


def rectangle_grid():
    g = ObservedGrid('r1')
    g.observe(robot_id='r1',frame_id=1,pose=(0.,0.,0.),floor_xy=[(x*.1+.05,y*.1+.05) for x in range(-10,21) for y in range(-10,11)])
    return g


def test_v1_pre_change_golden_bytes_and_default_off():
    nav = OwnMapNavigator('r1',NavigationOptions(exploration='own_frontier_v1',door_detection='own_gap_v1',partial_planning='own_astar_v1'))
    g = rectangle_grid()
    raw = json.dumps([nav.update(None,grid=g) for _ in range(3)],sort_keys=True,separators=(',',':'))+'\n'
    assert raw.encode()==(ROOT/'tests/fixtures/floor_goal/navigation_v1.json').read_bytes()
    legacy = (ROOT/'tests/fixtures/floor_goal/pre_goal_snapshot.json').read_bytes()
    assert OwnMapNavigatorV2('r1').update(legacy) is legacy


def test_ros_current_footprint_only_unknown_stays_unknown_and_no_camera_evidence():
    g = ObservedGrid('r1')
    nav = OwnMapNavigatorV2('r1',NavigationOptions(**OPTIONS_V2))
    view = nav.prepare_grid(g,(0.,0.,0.))
    assert view.support == footprint_cells(g,(0.,0.,0.))
    assert not g.support and not g.floor_frames and not g.odds
    assert view.state(g.cell([.35,0.]))==0
    assert pose_clear(view,(0.,0.,0.))
    _,clear,_,lo = footprint_clearance(view,Footprint(),.02,yaw=0.)
    x,y = np.array(view.cell([0.,0.]))-lo
    assert clear[y,x]
    assert not segment_clear(view,(0.,0.,0.),(.3,0.,0.))


def test_current_hit_overrides_static_prior_until_observed_floor_clears():
    g = rectangle_grid()
    cell = g.cell([.65,.05])
    g.odds[cell] = -4.
    g.observe(robot_id='r1',frame_id=2,pose=(0.,0.,0.),wall_xy=[[.65,.05]])
    assert g.state(cell)==-1
    nav = OwnMapNavigatorV2('r1',NavigationOptions(**OPTIONS_V2))
    assert nav.prepare_grid(g,(0.,0.,0.)).state(cell)==1
    g.observe(robot_id='r1',frame_id=3,pose=(0.,0.,0.),floor_xy=[[.65,.05]])
    assert nav.prepare_grid(g,(0.,0.,0.)).state(cell)==-1


def test_v2_dispatch_and_pure_rotation_inverse_gain_do_not_create_translation():
    actor = ActorV2('own_frontier')
    actor.grid = rectangle_grid()
    actor.navigator.prepare_grid(actor.grid,actor.odom.pose)
    plan = dict(status='observation_required',path_m=[],heading_rad=math.radians(25),doors=[])
    cmd = actor.command(plan)
    gain = np.asarray(motion_profiles()['motion']['gain'])
    assert np.allclose((gain@np.array([cmd['forward'],cmd['left'],cmd['turn']]))[:2],0.,atol=1e-12)
    actor.odom.command(cmd)
    actor.odom.advance(1.)
    assert np.linalg.norm(actor.odom.pose[:2])<1e-9
    result = OwnMapNavigator('r1',NavigationOptions(**OPTIONS_V2)).update(None,grid=rectangle_grid())
    assert result['free_policy']=='padded_footprint_polygon_v2'


def test_v2_one_camera_frame_connects_observed_floor_to_body_without_unknown_fill():
    from diagnose_environment import OracleWorld
    world = OracleWorld(1,STARTS['A'],1701,'development')
    actor = ActorV2('own_frontier')
    obs,patches,_ = world.observe(0)
    actor.t = 2.
    actor.receive(obs,patches)
    plan = actor.plan()
    assert plan['status']=='frontier'
    assert all(actor.navigator.last_grid.state(actor.grid.cell(p))==-1 for p in plan['path_m'])
