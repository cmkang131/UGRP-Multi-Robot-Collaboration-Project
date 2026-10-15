"""Fresh carry7 3+8 plan/disabled queue. No remote access or submission."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.make_solo_carry_plan import ROOT, prepare, queue

PLAN = 'experiments/2026-10-15-map-carry-zone/diagnostic-plan-v7.json'


def prepare7():
    old = json.loads((ROOT/'experiments/2026-10-15-map-carry-zone/diagnostic-plan-v6.json').read_text())
    repro = [copy.deepcopy(next(e for e in old['episodes'] if e['seed'] == s)) for s in (93261,93262,93266)]
    fresh = prepare(carry5=True,seed0=93280,count=8)['episodes']
    for i,e in enumerate([*repro,*fresh]):
        e.update(batch='solo-carry-zone-v7',carry5_rank_aware_views_v1=True,
                 carry5_trim_yaw_calibration_v1=False,carry7_robust_recovery_v1=True,
                 carry7_role='reproduction' if i < 3 else 'fresh_seed',merge_with_previous_results=False)
        if i < 3: e['reproduction_source_sha'] = 'd9e0073f5db51cde78f571aeb1ce91ad44d23eaa'
    return dict(schema='ugrp.solo_carry_plan.v7',episodes=[*repro,*fresh],research_result=False,
                training_rgb=False,gate_eligible=False,training_eligible=False,
                previous_results_combinable=False,gate_promotion_authorized_if_all_conditions_pass=False,
                seed_policy='exact 93261/93262/93266 layouts + fresh93280-93287; no pooling')


def queue7(plan,sha):
    value = queue({**plan,'schema':'ugrp.solo_carry_plan.v5'},sha,505,plan_path=PLAN)
    value.update(schema='ugrp.solo_carry_queue.v7',enabled=False,approved=False,ready=False,
                 stage_ready=False,execute=False,submitted=False,run_count=11,
                 supersedes_blocked_queue='20261015-solo-carry-d9e0073f.json',
                 previous_results_combinable=False,carry7_robust_recovery_v1=True,
                 seed_reservation=dict(split='solo_carry_diagnostic_v1',reproduction=[93261,93262,93266],
                    fresh=[93280,93287],remote_unused_verified=False),
                 storage_budget_mib=dict(per_run=256,total=2816,measured=False),
                 execution_stages=[dict(name='reproduce_first',indices=[0]),
                    dict(name='reproduce_remaining',indices=[1,2],requires='first run raw review and explicit approval'),
                    dict(name='fresh_eight',indices=list(range(3,11)),requires='three reproductions raw review and explicit approval')])
    value['preconditions'] = [x.replace('all8','all11') for x in value['preconditions']]
    value['preconditions'] += [
        'Carry7 is default-off, independent of carry6; new raw wall endpoints and sensor-mode receipts required.',
        'Offline old proposals lack wall endpoints/modes: fail closed, not a completed trajectory replay.',
        'Reproduce three layouts exactly; confirm no accepted wrong mode, scan completion and fresh cargo visibility before fresh8.',
        'No per-run limit relaxations or previous-result pooling; first30 speed and model supply checks still apply.']
    for i,r in enumerate(value['runs']):
        r['stage'] = 'reproduce_first' if i == 0 else ('reproduce_remaining' if i < 3 else 'fresh_eight')
    for obj in [value['coordinator_approval'],*value['runs'],*value['execution_stages']]:
        obj.update(approved=False,enabled=False,ready=False,stage_ready=False,execute=False,submitted=False)
    return value


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');p.add_argument('--queue-out',type=Path)
    a=p.parse_args()
    if a.plan:
        with (ROOT/PLAN).open('x') as f: json.dump(prepare7(),f,separators=(',',':'));f.write('\n')
    if a.queue_out:
        sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        value=queue7(json.loads((ROOT/PLAN).read_text()),sha)
        with a.queue_out.open('x') as f: json.dump(value,f,indent=2);f.write('\n')
        print(json.dumps(dict(path=str(a.queue_out),sha=sha,sha256=hashlib.sha256(a.queue_out.read_bytes()).hexdigest())))

if __name__=='__main__': main()
