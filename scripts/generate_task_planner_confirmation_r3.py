"""Frozen new-seed/new-sentence sample, generated without inspecting model output."""
import argparse, copy, hashlib, importlib.util, json
from pathlib import Path

PHRASES={
'next':{'cyan_claimed':'Cyan is claimed by me for the upcoming trip; you may take red.', 'red_claimed':'Red is claimed by me for the upcoming trip; you may take cyan.'},
'pair':{'available':'I am available now to share the beam carry after unloading my cargo.', 'unavailable':'I am unavailable for the beam carry until I finish my current cargo trip.'},
'help':{'needs_help':'The beam task still needs help from you at the opposite end.', 'withdrawn':'Help is no longer needed for my beam task; another carrier has taken the position.'},
'wait':{'near':'I am near the meeting point and should arrive in a short time.', 'late':'I am delayed and cannot arrive soon; a long detour remains.'},
'yield':{'committed':'My crossing of corridor_1 is committed; I am already inside with a load.', 'yielding':'I am yielding at bay_1 until your load passes corridor_1.'},
'route':{'blocked':'Door_narrow is blocked by cargo at the entrance; use the wide passage if needed.', 'clear':'Door_narrow is clear and currently passable at the entrance.'},
'correct':{'initial':'The ordered item is still at the initial location; I see no move to another slot.', 'new':'The ordered item moved to P1-3; inspect that new location.', 'dropped':'The ordered item was dropped at pickup; recovery from the floor is needed.'},
'relation':{'beam_blocks':'The beam blocks the can_1 approach from the west and needs a paired rotation.', 'robot_blocks':'My robot blocks can_1 access from the west; the beam does not cover it.', 'clear':'Access to can_1 is clear because both robot and beam have moved away.'}}

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('frozen_benchmark',a.source/'benchmark.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.ROOT=a.out;m.SEED=2026101303
    m.PHRASES={d:{w:[t, 'Current update: '+t, 'From my latest view: '+t] for w,t in worlds.items()} for d,worlds in PHRASES.items()}
    m.generate()
    gold=json.loads((a.out/'eval_only.json').read_text())
    rows=[dict(g,model='rules',condition='none') for g in gold]
    (a.out/'results_scored.json').write_text(json.dumps(rows,indent=2)+'\n')
    (a.out/'benchmark.py').write_bytes((a.source/'benchmark.py').read_bytes())
    (a.out/'README.md').write_text('New synthetic confirmation sample: seed 2026101303, new English templates fixed before evaluation. Same public task algebra; no physics. This is a new-phrasing/generalization check, not an independently collected physical study. Generator: scripts/generate_task_planner_confirmation_r3.py.\n')
    (a.out/'generation.json').write_text(json.dumps(dict(seed=m.SEED,generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),phrases=PHRASES,old_source=str(a.source)),indent=2)+'\n')
if __name__=='__main__':main()
