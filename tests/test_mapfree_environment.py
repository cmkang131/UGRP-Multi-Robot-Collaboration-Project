"""Pure 2D evaluator counterexamples, no physics or provider calls."""
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-explore/code'))
from diagnose_environment import OracleWorld, rectangle_contacts
from grid_world import GridWorld
from run_grid import Actor, STARTS


def test_oracle_preserves_camera_gate_and_frozen_temporal_translation():
    world = OracleWorld(1,[4.,-2.1,0.],2701,'confirmation')
    actor = Actor('own_frontier')
    for frame in range(4):
        obs,patches,truth = world.observe(frame)
        assert truth == [True]
        actor.t = 2.+3*frame
        actor.steps = frame
        accepted = actor.receive(obs,patches)
        assert all(p['confirmed_t'] is None for p in accepted)
    world.pose[2] = np.pi
    assert not world.goal_patches()[0]


def test_oracle_motion_exactly_matches_command_dr_without_truth_feedback():
    world = OracleWorld(1,STARTS['B'],2701,'confirmation')
    cmd = dict(t=0.,kind='mecanum',forward=.1,left=0.,turn=.1,duration_s=1.)
    actor = Actor('own_frontier')
    actor.odom.command(cmd)
    actor.odom.advance(1.)
    world.advance(cmd,1.)
    assert np.allclose(world.pose,np.array(STARTS['B'])+actor.odom.pose)


def test_circle_contact_is_not_rectangle_collision_and_yaw_matters():
    bounds = [-5,5,-5,5]
    rects = [dict(id='wall',center=[0.,.20],half=[1.,.05],yaw=0.)]
    assert rectangle_contacts([0.,.0,0.],rects,bounds)==[]
    assert rectangle_contacts([0.,.06,0.],rects,bounds)==['wall']
    assert rectangle_contacts([0.,.04,np.pi/2],rects,bounds)==['wall']
    w = GridWorld(1,STARTS['B'],2701,'confirmation')
    w.rects = rects
    assert w.collision([0.,0.])  # the frozen evaluator's circumscribed-circle false positive
