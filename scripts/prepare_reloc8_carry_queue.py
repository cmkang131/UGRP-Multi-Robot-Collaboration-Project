"""NEW reloc8 plan/queue only; never connect or submit."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from harness.active_relocalization import OPTION
from scripts.make_solo_carry_plan import ROOT, prepare, queue

PLAN = 'experiments/2026-10-15-map-carry-zone/diagnostic-plan-reloc8.json'
FLAGS = ('approved','enabled','ready','stage_ready','execute','submitted')


def prepare8():
    old=json.loads((ROOT/'experiments/2026-10-15-map-carry-zone/diagnostic-plan-v7.json').read_text())
    repro=[copy.deepcopy(next(e for e in old['episodes'] if e['seed']==s)) for s in (93261,93262,93266)]
    fresh=prepare(carry5=True,seed0=93290,count=8)['episodes']
    for i,e in enumerate([*repro,*fresh]):
        e.update(batch='solo-carry-reloc8', active_relocalization=OPTION,
            carry5_rank_aware_views_v1=True,carry7_robust_recovery_v1=True,
            carry5_trim_yaw_calibration_v1=False,merge_with_previous_results=False,
            reloc8_role='reproduction' if i<3 else 'fresh_seed')
        if i<3:e['reproduction_source_sha']='8c6f219cb39595a877fc0af487b3ea7e9fefb27f'
    return dict(schema='ugrp.solo_carry_plan.reloc8',episodes=[*repro,*fresh],research_result=False,
        training_rgb=False,gate_eligible=False,training_eligible=False,previous_results_combinable=False,
        gate_promotion_authorized_if_all_conditions_pass=False)


def make_queue(plan,sha):
    q=queue({**plan,'schema':'ugrp.solo_carry_plan.v5'},sha,505,plan_path=PLAN)
    q.update(schema='ugrp.solo_carry_queue.reloc8',source_sha=sha,active_relocalization=OPTION,
        run_count=11,previous_results_combinable=False,automatic_promotion=False,
        supersedes_blocked_queue='20261015-solo-carry-8c6f219c.json',
        seed_reservation=dict(split='solo_carry_diagnostic_v1',reproduction=[93261,93262,93266],
            fresh=[93290,93297],remote_unused_verified=False),
        execution_stages=[dict(name='first_reproduction',indices=[0],first30_review_required=True),
            dict(name='remaining_reproductions',indices=[1,2],requires='first run first30 and final raw review; explicit approval'),
            dict(name='fresh_eight',indices=list(range(3,11)),requires='three reproductions reviewed, no dangerous accepted correction; explicit approval')],
        storage_budget_mib=dict(per_run=256,total=2816,measured=False),
        texture_comparison=dict(pr=511,branch='claude/scene-floor-texture',status='WAIT_FOR_MERGE_AND_NEW_SOURCE',
            scene_version='floor_light_textured_v1',code_dependency_connected=False,
            enabled=False,approved=False,execute=False,ready=False,stage_ready=False,submitted=False,
            pool_with_smooth=False,requirement='merge PR511, connect profile API, repin source and generate separate approved comparison queue'))
    for i,r in enumerate(q['runs']):r['stage']='first_reproduction' if i==0 else 'remaining_reproductions' if i<3 else 'fresh_eight'
    for obj in [q,q['coordinator_approval'],*q['runs'],*q['execution_stages']]:obj.update({k:False for k in FLAGS})
    q['preconditions']=[s.replace('all8','all11') for s in q['preconditions']]+[
        'Serial11: 3 exact carry7 layouts + fresh93290-93297; first run first30 raw review before any other run.',
        'Selected offline RGB is incomplete: retrieve >=6 own frames in EACH first/middle/final third plus exact recovery captures.',
        'Compare acceptance/rejection, multi-view/command modes, floor/wall/mark pixels, ORB/line/landmark counts; dangerous accepted corrections must be0.',
        'reloc8 defaults off; changed arm/view directions are physically unverified. Fixed-proposal replay0/28 is not recovery success.',
        'PR511 comparison is a blocked separate scene condition; no pooling or unmerged code dependency.']
    return q


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');p.add_argument('--queue-out',type=Path)
    a=p.parse_args()
    if a.plan:
        with (ROOT/PLAN).open('x') as f:json.dump(prepare8(),f,separators=(',',':'));f.write('\n')
    if a.queue_out:
        sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        q=make_queue(json.loads((ROOT/PLAN).read_text()),sha)
        with a.queue_out.open('x') as f:json.dump(q,f,indent=2,ensure_ascii=False);f.write('\n')
        print(json.dumps(dict(path=str(a.queue_out),sha=sha,sha256=hashlib.sha256(a.queue_out.read_bytes()).hexdigest())))


if __name__=='__main__':main()
