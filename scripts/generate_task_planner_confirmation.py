"""Frozen new-seed/new-sentence sample, generated without inspecting model output."""
import argparse, copy, hashlib, importlib.util, json
from pathlib import Path

PHRASES={
'next':{'cyan_claimed':'For this round I am handling cyan; red remains unassigned.', 'red_claimed':'For this round I am handling red; cyan remains unassigned.'},
'pair':{'available':'My delivery is finished, so I can join the beam team now.', 'unavailable':'I cannot join you now because my gripper must retain another load.'},
'help':{'needs_help':'I still need someone to grasp the opposite beam end; the request remains open.', 'withdrawn':'Please cancel my beam request: a second carrier has already arrived.'},
'wait':{'near':'I am almost at the beam, with only the last approach remaining.', 'late':'A long job has left me delayed; I am still far away from our meeting point.'},
'yield':{'committed':'I have entered corridor_1 with cargo; my crossing is in progress.', 'yielding':'I am giving you the turn and have stopped in bay_1.'},
'route':{'blocked':'Cargo has left door_narrow blocked, while the wider passage remains usable.', 'clear':'I inspected the opening and found door_narrow clear for passage.'},
'correct':{'initial':'The target remains at its initial location from the order sheet.', 'new':'My current view places the target in P1-3 rather than the old slot.', 'dropped':'The target dropped onto the pickup floor while I was releasing my grip.'},
'relation':{'beam_blocks':'The beam spans the west access to can_1; rotating it needs both carriers.', 'robot_blocks':'My robot still blocks the west access to can_1 although the beam is clear.', 'clear':'The can approach is open now after the beam and robot moved aside.'}}

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('frozen_benchmark',a.source/'benchmark.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.ROOT=a.out;m.SEED=2026101302
    m.PHRASES={d:{w:[t, 'Current update: '+t, 'From my latest view: '+t] for w,t in worlds.items()} for d,worlds in PHRASES.items()}
    m.generate()
    gold=json.loads((a.out/'eval_only.json').read_text())
    rows=[dict(g,model='rules',condition='none') for g in gold]
    (a.out/'results_scored.json').write_text(json.dumps(rows,indent=2)+'\n')
    (a.out/'benchmark.py').write_bytes((a.source/'benchmark.py').read_bytes())
    (a.out/'README.md').write_text('New synthetic confirmation sample: seed 2026101302, new English templates fixed before evaluation. Same public task algebra; no physics. This is a new-phrasing/generalization check, not an independently collected physical study. Generator: scripts/generate_task_planner_confirmation.py.\n')
    (a.out/'generation.json').write_text(json.dumps(dict(seed=m.SEED,generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),phrases=PHRASES,old_source=str(a.source)),indent=2)+'\n')
if __name__=='__main__':main()
