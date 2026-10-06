"""Pure 2D evaluator counterexamples, no physics or provider calls."""
from pathlib import Path
import json
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


def test_corrected_evaluator_uses_orientation_and_preserves_real_contacts():
    from grid_world_v2 import RectangleWorld, RectangleOracleWorld
    for cls in (RectangleWorld, RectangleOracleWorld):
        world = cls(1,STARTS['B'],2701,'confirmation')
        world.rects = [dict(id='wall',center=[0.,.20],half=[1.,.05],yaw=0.)]
        world.pose[:] = [0.,0.,0.]
        assert not world.collision([0.,0.])
        assert world.collision([0.,.06])
        world.pose[2] = np.pi/2
        assert world.collision([0.,.04])
        assert world.collision([-1.1,0.])


def test_report_temporal_funnel_emits_native_json_counts(tmp_path):
    from scripts.report_mapfree_environment import funnel
    p = tmp_path/'s1-A-1701-own_frontier'
    p.mkdir()
    logs = [dict(t=3.*i,pose_odom=[.1*i,0.,0.],patches=[dict(track_id=1)],plan=dict(path_m=[])) for i in range(3)]
    truth = [dict(B_component_truth=[True]) for _ in logs]
    (p/'actor.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in logs))
    (p/'eval_only.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in truth))
    row = dict(scenario='s1',start='A',seed=1701,condition='own_frontier',status='budget',
               sensor_draws=dict(B_positive_frames=3,B_detections=3))
    result = funnel(tmp_path,[row])
    assert result[0]['true_tracks_3views_translation']==1
    assert json.loads(json.dumps(result,allow_nan=False))==result


def test_rejected_path_is_not_issued_door_attempt():
    from scripts.score_mapfree_passage_commands import score_commands
    from grid_world_v2 import RectangleWorld
    world = RectangleWorld(1,[2.,.05,0.],1701,'development')
    plan = dict(path_m=[[0.,0.],[.12,0.]],doors=[])
    rows = [dict(frame=i,t=2.+4*i,pose_odom=[0.,0.,0.],plan=plan,
        command=dict(forward=forward,left=0.,turn=0.,duration_s=1.)) for i,forward in enumerate([0.,.08])]
    truth = [dict(frame=r['frame'],t=r['t'],pose_world=[2.,.05,0.]) for r in rows]
    result = score_commands(world,rows,truth)
    assert result['suppressed_nonmoving_path_frames']==1
    assert result['door_attempts']==1
    assert result['wrong_door_attempts']==0
