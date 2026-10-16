import numpy as np
from types import SimpleNamespace
from harness.e2e_arm_clearance import Clearance
from harness.owncam_pair_beam_v2 import pose_of
from harness.own_map_navigation import ObservedGrid
from tests.test_e2e_arm_clearance import setup


def test_correct_front_echo_and_no_current_wall_still_retreat_before_full_arm_queue():
    tr=setup('range_wall_v1',distance=1.9);tr.arm_clearance=Clearance('range_wall_v1','retreat_v1')
    r=tr.robots['r1'];r.servo=pose_of('p45')
    tr._poses('r1',0.,[(pose_of('inspect'),.3,.6)])
    assert not tr.queue and tr.arm_clearance.busy('r1')
    assert tr.events[-1]['command_space_retreat']
    assert tr.arm_clearance.filter(tr,.05,[])[0][1]['forward']<0
    r.goal.explorer.local_pose[0]-=.31;tr.arm_clearance.filter(tr,1.,[])
    r.goal.explorer.local_pose[2]=tr.arm_clearance.pending['r1']['yaw'];tr.arm_clearance.filter(tr,1.1,[])
    tr.arm_clearance.filter(tr,2.,[]);assert tr.queue and not tr.arm_clearance.pending
    tr.queue.clear();r.servo=pose_of('inspect')
    tr._poses('r1',3.,[(pose_of('search'),.3,.6)])
    assert tr.queue and not tr.arm_clearance.pending
    tr.queue.clear();tr._poses('r1',15.,[(pose_of('p45'),.3,.6)])
    assert tr.arm_clearance.pending and not tr.queue


def test_own_persistent_wall_covers_side_sector_and_preserves_map():
    tr=setup('range_wall_v1',distance=1.9);r=tr.robots['r1'];r.robot_id='r1'
    e=r.goal.explorer;e.local_pose=np.zeros(3);e.map_to_odom=np.zeros(3);e.grid=ObservedGrid('r1',.05)
    e.grid.observe(robot_id='r1',frame_id=1,pose=np.zeros(3),wall_xy=[[-.1,.2]])
    e.latest={};before=dict(e.grid.odds);tr.arm_clearance=Clearance('range_wall_v1','map_v1')
    tr._poses('r1',0.,[(pose_of('p45'),.3,.6)])
    assert tr.arm_clearance.pending and not tr.queue and e.grid.odds==before
    assert tr.events[-1]['map_wall_m']<.45


def test_retreat_slot_is_fixed_clock_and_grasp_is_excluded():
    tr=setup('range_wall_v1',distance=1.9);g=Clearance('range_wall_v1','retreat_slots_v1');tr.arm_clearance=g
    assert g.slot('r1',.2) and not g.slot('r2',.2) and g.slot('r2',3.2)
    tr._poses('r1',0.,[(pose_of('p45'),.3,.6),({1:1500},.5,.4)])
    assert tr.queue and not g.pending
