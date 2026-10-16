"""New seed and compositional sentences, after the r4 parser was frozen.

No model-generated outcomes or former confirmation sentences are consulted.
This is synthetic wording generalization, not independent physical collection.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

SEED=2026101405
PHRASES={
 'next':{
  'cyan_claimed':['Red is still free; I am handling cyan.','The cyan order is mine; nobody has taken red yet.','I have claimed cyan. The red order remains free.'],
  'red_claimed':['Cyan is still free; I am handling red.','The red order is mine; nobody has taken cyan yet.','I have claimed red. The cyan order remains free.']},
 'pair':{
  'available':["I'm available for beam_1; my gripper is empty.",'At the beam, I can be your second carrier; I am not tied up.',"I can join the beam team: I'm available."],
  'unavailable':["I'm unavailable for beam_1: I am carrying my solo load.",'My gripper is occupied; I cannot be your second carrier.',"I cannot join the beam team: I'm tied up."]},
 'help':{
  'needs_help':['For beam_1 I still need help: there is nobody at the other end.','My beam_1 request is still active; please join me.','I need a second carrier at beam_1; the request is still active.'],
  'withdrawn':['The second end is covered now; cancel the request for beam_1.','Another carrier has joined me, so I withdraw my beam_1 request.','For beam_1 I no longer need help; cancel my request.']},
 'wait':{
  'near':['The rendezvous is a short trip away; I am near the beam.','I will not be late for the beam; I am around the corner.','I am almost at the beam. I can join shortly.'],
  'late':['I cannot arrive soon: this delivery has me stuck.','The rendezvous will have to wait. I am delayed far from the beam.','I am still far away from the beam and will not arrive shortly.']},
 'yield':{
  'committed':['Inside corridor_1, my loaded crossing is underway; I am not yielding.','I have entered corridor_1 with my load and am committed to crossing.','I am not yielding at corridor_1: I am already inside.'],
  'yielding':['I have pulled into bay_1 and am giving you the turn at corridor_1.','I am not entering corridor_1; I am yielding in the bay.','Corridor_1 is free for you; I am giving you the turn.']},
 'route':{
  'blocked':['Door_wide is open, but door_narrow is blocked.','There is no way through door_narrow; use caution at that opening.','Door_narrow is not clear at the moment; something is blocking it.'],
  'clear':['Door_narrow is clear at the moment; the opening is passable.','Nothing is obstructing door_narrow; I can see the opening.','Door_narrow is not blocked now; there is a way through.']},
 'correct':{
  'initial':['At the initial order-sheet slot I can see the target; it has not moved.','The target is where the original order sheet says, at the initial slot.','I see the target: it is still at its initial slot.'],
  'new':['At P1-3 I can see the target; the initial slot is empty.','The target is now in P1-3; its original slot is vacant.','I found the target at P1-3. It is not at its initial slot anymore.'],
  'dropped':['The target is down on the pickup floor; my gripper is empty.','Near pickup I dropped the target; it is not delivered.','The target fell onto the pickup floor from my gripper.']},
 'relation':{
  'beam_blocks':['Across the west approach to can_1 lies beam_1; the beam needs turning.','The beam needs turning before can_1 pickup; beam_1 spans its west approach.','Beam_1 lies across the only usable can_1 approach; my robot is not the obstruction.'],
  'robot_blocks':['My robot still blocks can_1 west approach; the beam is out of the way.','It is my robot in the can approach, so turning the beam will not help.','The robot is in the can approach; I need to retreat before you fetch can_1.'],
  'clear':['No obstruction remains at can_1 west approach; I have backed away.','Neither the beam nor my robot blocks can_1 now; the approach is open.','The can approach is open after the beam rotation; I have backed away.']}}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.out.exists():raise SystemExit('new output required')
    a.out.mkdir(parents=True)
    spec=importlib.util.spec_from_file_location('frozen_task_generator',a.source/'benchmark.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ROOT=a.out.resolve();module.REPO=Path(__file__).resolve().parents[1]
    module.SEED=SEED;module.PHRASES=PHRASES;module.generate()
    (a.out/'generation_r4.json').write_text(json.dumps(dict(seed=SEED,
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        parser_sha256=hashlib.sha256((module.REPO/'harness/task_planner_cost_rules.py').read_bytes()).hexdigest(),
        scope='new compositional wording and cost seed; same public algebra and latent-state cycle'),indent=2)+'\n')
