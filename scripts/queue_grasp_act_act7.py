"""Disabled ACT7 gate retry only. Reuse completed census; no remote actions."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from harness.grasp_act_data import sha256
from scripts.grasp_act_training_guard import ROOT, source_sha
from scripts.queue_grasp_act_act6 import RECORD, build_queue as act6_queue


def build_queue(source):
    evidence_path=ROOT/RECORD/'act7-prior-evidence.json'
    evidence=json.loads(evidence_path.read_text())
    previous=act6_queue(source)
    gate=deepcopy(previous['jobs'][0])
    for run in gate['runs']:
        run['name']=run['name'].replace('act6-gate-','act7-gate-')
        run['command']=[s.replace('/act6-gate-','/act7-gate-') for s in run['command']]
    gate['depends_on']=['preflight-receipt','completed-census-reference']
    census=deepcopy(evidence['census'])
    census['receipts']=deepcopy(evidence['receipts'][:4])
    return {**{k:previous[k] for k in ('approved','enabled','ready','stage_ready','submitted',
                'source_sha','branch','pr','project','status','teacher_dependency_sha','teacher_dependency_root')},
        'schema':'ugrp.vm3_queue.act7.v1','record':f'{RECORD}/act7.md',
        'scope':'noise teacher gate40 only; no downstream recording/training submission',
        'gate_promotion_authorized_if_all_conditions_pass':False,'remote_execution_started':False,
        'coordinator_approval':{'approved':False,'ready':False},
        'jobs':[gate],'saved_preflight_jobs':[],
        'gate_plan':{'path':f'{RECORD}/act6-gate-plan.json','sha256':sha256(ROOT/RECORD/'act6-gate-plan.json')},
        'noise':{'path':f'{RECORD}/act6-noise.json','sha256':sha256(ROOT/RECORD/'act6-noise.json')},
        'completed_inputs':{'completed-census-reference':census},
        'seed_reuse':deepcopy(evidence['seed_reuse']),
        'evidence':{'path':f'{RECORD}/act7-prior-evidence.json','sha256':sha256(evidence_path)},
        'prior_queues_untouched':deepcopy(evidence['prior_queues']),
        'machine':previous['machine'],
        'budgets':{k:previous['budgets'][k] for k in ('gate40_wall_s','separate_8h_windows_per_stage',
                 'all_compute_price_and_credit_values','disk_gib','raw_estimate_mib',
                 'reserved_writes_must_include_other_approved_jobs')},
        'required_before_start':[
            'New explicit approval/preflight required; all ready/approval/submission flags remain false.',
            'Verify clean ACT source and pinned teacher checkout. All teacher scripts/sim/harness imports use the dependency only; no ACT fallback.',
            'Use the completed 50/50 census and 100 original hash PASS receipts above; do not rerun the census.',
            '8316600 reuse is based on the preserved pre-world HOST_ERROR; retain that old failure separately. The other 39 were unsubmitted. Recheck live inventory before activation.',
            *[s for s in previous['required_before_start'] if s.startswith(('Check actual','All gcloud','Gate and recording','Stop same-defect'))]],
        'after_each_stage':previous['after_each_stage']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    source=source_sha();q=build_queue(source)
    evidence=json.loads((ROOT/RECORD/'act7-prior-evidence.json').read_text())
    for item in evidence['receipts']+evidence['prior_queues']:
        if sha256(item['path'])!=item['sha256']:raise ValueError(f'prior evidence changed: {item["path"]}')
    a.output_dir.mkdir(parents=True,exist_ok=True)
    path=a.output_dir/f'20261015-act7-{source[:8]}.json'
    # Exclusive creation also protects prior queues from accidental overwrites.
    with path.open('x') as stream:stream.write(json.dumps(q,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'path':str(path),'sha256':sha256(path),'source_sha':source,'approved':False}))


if __name__=='__main__':main()
