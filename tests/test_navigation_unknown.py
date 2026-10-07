"""Upstream policy boundary and persistent own-footprint semantics, no new cohort."""
import copy
from pathlib import Path
import sys
import numpy as np
import pytest
from harness.own_map_navigation import ObservedGrid
from harness.public_navigation_unknown import (UnknownCore,UnknownCostmap,UnknownActor,
    clear_current_footprint,footprint_cells,navigation_output_v7)
from harness.public_navigation.native import PublicCore
from harness.public_navigation_raytrace import receive_rays
from test_navigation_raytrace import observation


def test_allow_unknown_native_default_and_known_lethal_remain_distinct():
    raw = np.zeros((30,30),np.uint8)
    raw[:,14:16] = 255
    legacy,new = PublicCore(),UnknownCore()
    before = legacy.plan(raw,(5,15),(24,15)).tobytes()
    assert before == b''
    assert len(new.plan(raw,(5,15),(24,15))) > 0
    assert legacy.plan(raw,(5,15),(24,15)).tobytes() == before
    raw[:,14:16] = 254
    assert not len(new.plan(raw,(5,15),(24,15)))


def test_unknown_footprint_allowed_but_known_wall_and_map_bounds_rejected():
    raw = np.full((30,30),255,np.uint8)
    cm = UnknownCostmap(raw,[-.75,-.75],.05)
    assert cm.pose_clear([0,0,0])
    cm.raw[cm.world_to_map([.14,0])[1],cm.world_to_map([.14,0])[0]] = 254
    cm.costs = cm.inflate()
    assert not cm.pose_clear([0,0,0])
    assert not cm.pose_clear([-.74,0,0])
    assert cm.raw[0,0] == 255  # permitting traversal is not clearing it


def test_footprint_persists_without_rgb_credit_future_clear_or_static_erasure():
    grid,latest = ObservedGrid('r1',.05),{}
    fixed = grid.cell((.025,.025))
    grid.odds[fixed] = 4.
    first = clear_current_footprint(grid,latest,{fixed},[0,0,0])
    assert first == footprint_cells(grid,[0,0,0])-{fixed}
    assert grid.odds[fixed] == 4. and not grid.floor_frames
    assert grid.state(grid.cell((.575,.025))) == 0
    clear_current_footprint(grid,latest,{fixed},[.3,0,0])
    assert all(grid.state(c)==-1 for c in first)
    # A later hit can reoccupy the OLD footprint. Only current pose is re-cleared.
    old = grid.cell((-.075,.025))
    receive_rays(grid,latest,{fixed},observation(wall=[(-.075,.025)]),[0,0,0])
    clear_current_footprint(grid,latest,{fixed},[.3,0,0])
    assert grid.state(old)==1


def test_actor_initially_no_authored_map_and_control_ticks_clear_only_current():
    actor = UnknownActor('own_frontier',navigation='public_ros_v7')
    assert not actor.grid.odds and not actor.static_hits and actor.static_goal is None
    actor.receive(observation(),[])
    original = set(actor.grid.odds)
    actor.odom.correct([.25,0,0],np.zeros((3,3)))
    actor.make_costmap()
    assert original <= set(actor.grid.odds)
    assert actor.grid.state(actor.grid.cell((.325,.025))) == -1
    assert not actor.grid.floor_frames
    assert actor.grid.state(actor.grid.cell((.675,.025))) == 0


def test_off_is_lazy_identity_and_old_frozen_bytes_preserved():
    legacy = b'{"unchanged":true}\n'
    class Poison:
        def update(self,**kwargs):raise AssertionError('off input evaluated')
    assert navigation_output_v7(legacy,navigator=Poison(),hidden=object()) is legacy
    with pytest.raises(ValueError,match='V7_REQUIRED'):UnknownActor('own_frontier')
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'experiments/2026-10-07-mapfree-unknown-footprint/code'))
    import unknown_common as common
    assert common.v6.prior.verify_frozen() == common.read(common.v6.prior.v5.EXP/'freeze.json')['hashes']
    assert common.CRITERIA == common.v6.prior.CRITERIA
    assert 'mujoco' not in sys.modules
