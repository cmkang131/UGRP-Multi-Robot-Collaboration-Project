"""Frozen same-seed A/B/C queue; all authorization flags false, no submission."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.prepare_reloc8_carry_queue import prepare8, FLAGS
from scripts.make_solo_carry_plan import ROOT, queue

PLAN = 'experiments/2026-10-15-reloc9/diagnostic-plan.json'
CANDIDATES = ('rotation', 'rotation_wall', 'rotation_wall_search')


def prepare9():
    old = prepare8(); episodes = []
    for i, source in enumerate(old['episodes']):
        for candidate in CANDIDATES:
            e = copy.deepcopy(source)
            e.update(batch='solo-carry-reloc9',reloc9_candidate=candidate,
                reloc9_rotation_calibration_v1=True,
                reloc9_wall_height_guard_v1=candidate != 'rotation',
                reloc9_reacquisition_v1=candidate == 'rotation_wall_search')
            episodes.append(e)
    return dict(schema='ugrp.solo_carry_plan.reloc9',episodes=episodes,research_result=False,
        training_rgb=False,gate_eligible=False,training_eligible=False,previous_results_combinable=False,
        candidates=list(CANDIDATES), gate_promotion_authorized_if_all_conditions_pass=False)


def make_queue(plan,sha):
    q = queue({**plan,'schema':'ugrp.solo_carry_plan.v5'},sha,505,plan_path=PLAN)
    for i, (run, episode) in enumerate(zip(q['runs'],plan['episodes'])):
        name = f'solo-carry-{episode["seed"]}-{episode["reloc9_candidate"]}-{sha[:8]}'
        oldname = run['name'];run['name'] = name
        run['command'] = [part.replace(oldname,name) for part in run['command']]
        run.update(candidate=episode['reloc9_candidate'],stage='reproductions' if i < 9 else 'fresh_eight')
    name = f'solo-carry-rotation-check-{sha[:8]}'
    preflight = dict(name=name,source_sha=sha,stage='rotation_check',requires_coordinator_approval=True,
        command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','505',
            '--per-run-mb','256',str(ROOT),name,'--','.venv-sim/bin/python','-m','scripts.run_reloc9_rotation_check',
            '--plan',PLAN,'--expected-source-sha',sha,'--execution-host','gcp1','--out',
            f'/home/ugrp/ugrp-sim/runs/{name}/raw'],
        execution_argument_after_approval='--execute',targets_deg=[90,-180])
    q['runs'].insert(0,preflight)
    for i,run in enumerate(q['runs']):
        run['depends_on'] = q['runs'][i-1]['name'] if i else None
    q.update(schema='ugrp.solo_carry_queue.reloc9',source_sha=sha,run_count=len(q['runs']),max_parallel=1,
        candidates=list(CANDIDATES),automatic_promotion=False,previous_results_combinable=False,
        supersedes_blocked_queue='20261015-solo-carry-0459c03c.json',
        execution_stages=[dict(name='rotation_check',indices=[0],requires='90L/180R each actual/estimate 0.9-1.1 and saved ledger review'),
            dict(name='reproductions',indices=list(range(1,10)),requires='rotation check passed; first30 and final review per candidate'),
            dict(name='fresh_eight',indices=list(range(10,34)),requires='3 reproductions x3 candidates reviewed; no worsened accepted correction; explicit approval')],
        seed_reservation=dict(split='solo_carry_diagnostic_v1',reproduction=[93261,93262,93266],fresh=[93290,93297],
                              remote_unused_verified=False),storage_budget_mib=dict(per_run=256,total=34*256,measured=False))
    q['preconditions'] += [
        'All approval/execution flags are false. Serial: rotation check, then 3 exact reproduction layouts x3 candidates, then 8 new layouts x3 candidates.',
        'Reuse identical layout/seed for rotation / rotation+wall / rotation+wall+search. Do not pool candidates or old versions.',
        'Review first30 raw for each candidate; compare 5deg/10cm absolute risk AND before/after normalized error and separate axis worsening counts.',
        'Offline holdout has outliers; new rotation gate is mandatory, never automatically approve.',
        'PR511 unmerged texture is opinion-only and no dependency; no selfmap queue created; coordinator waits for93571.',
        'Native 640x480 recovery captures and manifests required; preview wall audit showed limited checker removal.']
    for obj in [q,q['coordinator_approval'],*q['runs'],*q['execution_stages']]:
        obj.update({k:False for k in FLAGS})
    return q


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');p.add_argument('--queue-out',type=Path)
    a=p.parse_args()
    if a.plan:
        path=ROOT/PLAN;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x') as f:json.dump(prepare9(),f,separators=(',',':'));f.write('\n')
    if a.queue_out:
        sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        value=make_queue(json.loads((ROOT/PLAN).read_bytes()),sha)
        with a.queue_out.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
        print(json.dumps(dict(path=str(a.queue_out),sha=sha,sha256=hashlib.sha256(a.queue_out.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
