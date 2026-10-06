"""Post-hoc evaluation correction: a rejected plan is not an issued motion attempt.

Reads immutable actor/evaluation logs. No controller rerun, parameter change, or
ground-truth feedback. Original pre-command plan counters remain in raw results.
"""
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-explore/code'))
from run_grid import STARTS
from run_revision import NEW_STARTS
from grid_world import GridWorld
from grid_world_v2 import RectangleWorld
from harness.self_odom_grid import motion_profiles, transform

PASSAGE_KEYS = ('door_attempts','wrong_door_attempts','candidate_passage_attempts','false_candidate_passage_attempts')


def score_commands(world, actor, evaluation):
    gain = np.asarray(motion_profiles()['motion']['gain'])
    suppressed = 0
    assert len(actor)==len(evaluation)
    for row,truth in zip(actor,evaluation):
        assert row['frame']==truth['frame'] and row['t']==truth['t']
        path = row['plan'].get('path_m',[])
        if len(path)<2 or 'command' not in row:
            continue
        command = row['command']
        body = gain@np.array([command['forward'],command['left'],command['turn']])
        if np.linalg.norm(body[:2])<=1e-9:
            suppressed += 1
            continue
        world.pose = np.array(truth['pose_world'],float)
        world.events(row['t'])
        pose = row['pose_odom']
        # Evaluate the short translation requested by the command, in the own frame.
        target = transform([body[:2]*command['duration_s']],pose)[0].tolist()
        issued = {**row['plan'],'path_m':[pose[:2],target]}
        world.passage_intent(issued,pose,row['t'])
    return dict(door_attempts=world.door_attempts,wrong_door_attempts=world.wrong_doors,
        candidate_passage_attempts=world.candidate_attempts,false_candidate_passage_attempts=world.false_candidate_attempts,
        suppressed_nonmoving_path_frames=suppressed)


def rescore(folder, row):
    name = f"{row['scenario']}-{row['start']}-{row['seed']}-{row['condition']}"
    p = folder/name
    actor = [json.loads(s) for s in (p/'actor.jsonl').read_text().splitlines()]
    evaluation = [json.loads(s) for s in (p/'eval_only.jsonl').read_text().splitlines()]
    world_type = RectangleWorld if row.get('environment')=='rect_footprint_v2' else GridWorld
    start = {**STARTS,**NEW_STARTS}[row['start']]
    world = world_type(int(row['scenario'][1:]),start,row['seed'],row['split'])
    scored = score_commands(world,actor,evaluation)
    return {**row,'pre_command_plan_counters':{k:row[k] for k in PASSAGE_KEYS},
            'passage_scoring':'issued_translation_v2',**scored}
