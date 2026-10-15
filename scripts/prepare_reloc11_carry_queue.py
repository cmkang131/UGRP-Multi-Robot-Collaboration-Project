"""Prepare a blocked carry texture handoff without touching its active checkout."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FLAGS=('approved','enabled','ready','stage_ready','execute','submitted')


def prepare(existing, sha):
    q=copy.deepcopy(existing)
    def scrub(obj):
        if isinstance(obj,dict):
            for key in list(obj):
                if key.startswith('operator') or key.startswith('tested_') or key == 'runtime_git_tree_fingerprint_sha256':
                    obj.pop(key)
                else:scrub(obj[key])
        elif isinstance(obj,list):
            for value in obj:scrub(value)
    scrub(q)
    q['runs_enabled']=False
    plan=ROOT/'experiments/2026-10-15-reloc11/carry-texture-plan.json'
    q.update(schema='ugrp.solo_carry_queue.reloc11_texture',status='BLOCKED',
             source_sha=sha,sha=sha,scene_version='floor_light_textured_v1',
             plan_sha256=hashlib.sha256(plan.read_bytes()).hexdigest(),
             candidates=['rotation','rotation_wall_search'],previous_results_combinable=False,
             supersedes_blocked_queue=None,existing_smooth_queue_untouched=True,
             texture_api_connected=False,source_pin_requires_regeneration=True,
             blocker='CARRY_PATH_AUTHORIZATION_AND_ORIGIN_MAIN_MERGE_THEN_PATCH_REQUIRED',
             required_patch=str(ROOT/'experiments/2026-10-15-reloc11/carry-texture-api.patch'),
             required_merge='origin/main including PR511 official texture/nearclip APIs',
             plan_path='experiments/2026-10-15-reloc11/carry-texture-plan.json',
             max_parallel=16,automatic_promotion=False)
    for r in q['runs']:
        old=r['name'];r['name']=old.replace('solo-carry-','solo-carry-tex-',1)
        r['scene_version']='floor_light_textured_v1'
        r['command']=[s.replace(old,r['name']) for s in r['command'] if s!='--execute']
        if '--plan' in r['command']:r['command'][r['command'].index('--plan')+1]=q['plan_path']
        if r.get('depends_on'):r['depends_on']=r['depends_on'].replace('solo-carry-','solo-carry-tex-',1)
    for obj in [q,q.get('coordinator_approval',{}),*q['runs'],*q.get('execution_stages',[])]:obj.update({k:False for k in FLAGS})
    q['preconditions']=[
        'BLOCKED handoff: source SHA names the untouched carry checkout, not a validated texture implementation. Regenerate against a new carry commit after path authorization, official origin/main merge and patch tests.',
        'Do not alter 987d033f running smooth jobs or their existing queue. This file never submits.',
        'Texture is primary; no extra smooth comparison runs. Keep scene/source/host/candidate results separate.',
        'Rotation gate then reproduction3 x2 candidates then fresh8 x2 candidates; all flags false.',
        'gcp1 only, project ugrp-act-train-1014, aggregate<=40; budget-stop, 8h STOP, idle20m preserved.',
        'No TOP capture/control, held truth reads0, invisible measurements0. Truth evaluator only.']
    return q


def main():
    p=argparse.ArgumentParser();p.add_argument('--existing',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source=json.loads(a.existing.read_bytes());sha=source['source_sha'];q=prepare(source,sha)
    with a.output.open('x') as f:json.dump(q,f,indent=2,ensure_ascii=False);f.write('\n')
    print(json.dumps(dict(path=str(a.output),sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),status=q['status'])))


if __name__=='__main__':main()
