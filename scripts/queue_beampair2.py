"""Prepare a new gate40 from verified beampair2 exploration, never submit."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.queue_beampair1 import validate_evidence,sha

ROOT=Path(__file__).resolve().parents[1]


def build(source,evidence,table):
    if len(source)!=40 or any(c not in '0123456789abcdef' for c in source):
        raise ValueError('full source SHA required')
    report=json.loads(evidence.read_text());validate_evidence(report,table,source)
    if report['n']!=6 or report.get('cap_end_N'):
        raise ValueError('all six probes including failed-seed regression must pass')
    if not report['runs'][0]['strict_success']:raise ValueError('first failed-seed probe must pass')
    base=ROOT/'experiments/2026-10-15-beampair1'
    q=deepcopy(json.loads((base/'gate40-queue.json').read_text()))
    plan_path='experiments/2026-10-15-beampair1/gate-plan.json'
    frozen=subprocess.check_output(['git','show',source+':'+plan_path],cwd=ROOT)
    episodes=json.loads(frozen)['episodes']
    if len(episodes)!=40 or len({e['seed'] for e in episodes})!=40:raise ValueError('distinct frozen40 required')
    first=next(i for i,e in enumerate(episodes) if e['seed']==8318604)
    pinned=f'/Users/changmin/projects/ugrp-wt/beam-pair-gate-{source[:8]}'
    paths=list(q['source_hashes'])+['harness/grasp_act_peer_rendezvous.py']
    hashes={p:hashlib.sha256(subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)).hexdigest() for p in paths}
    runs=[]
    for i in [first,*[i for i in range(40) if i!=first]]:
        e=episodes[i];name=f'beampair2-gate-{e["seed"]}-{source[:8]}'
        command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','522',
            '--per-run-mb','128',pinned,name,'--','timeout','--signal=INT','8h',
            '.venv-sim/bin/python','-m','scripts.run_beampair1','--plan',plan_path,'--episode',str(i),
            '--dependency-root',q['dependency_root'],'--out','/home/ugrp/ugrp-sim/runs/'+name+'/raw',
            '--mode','beampair1_v1','--candidate','baseline','--rendezvous','peer_rendezvous_v1','--cap-s','60']
        runs.append(dict(name=name,seed=e['seed'],episode=i,source_sha=source,command=command,
            training_rgb=False,approved=False,submitted=False,burst_ticks=e['burst_ticks'],roles=e['roles']))
    q.update(schema='ugrp.beampair2.gate40_queue.v1',owner='beampair2',source_sha=source,sha=source,
        status='PREPARED_NEEDS_COORDINATOR_PIN',ready=False,approved=False,submitted=False,
        source_worktree=pinned,pinned_worktree=pinned,pinned_worktree_created=False,
        pinned_worktree_owner='coordinator',remote_pinned_worktree='/home/ugrp/ugrp-sim/src/'+source,
        source_hashes=hashes,rejection_table=str(table),rejection_table_sha256=sha(table),
        exploration_evidence=str(evidence),exploration_evidence_sha256=sha(evidence),
        first_two_seeds=[r['seed'] for r in runs[:2]],peer_rendezvous='peer_rendezvous_v1',runs=runs,
        gate_measured_N=0,prior_gate_results_pooled=False,
        cohort_scope='restart all40; 8318604 regression sentinel first; same frozen setups, no d79 outcomes inherited',
        required_before_start=[
            'Coordinator creates a clean detached pinned worktree at the full source SHA; verify all source hashes.',
            'The existing absolute rejection_table and its SHA256 are mandatory; do not activate without them.',
            'Start at 8318604, remeasure all40 from zero, never pool d79f04a3 or exploration results.',
            'Recheck budget-stop, idle guard, storage, available memory and global admission lock; host total <=40.',
            'Existing VM scheduling was24h during DEV; coordinator must check/resolve the required8h VM cap before gate activation. Own commands also have8h limits.',
            'Planned16-concurrent first30 speed/own-camera/protocol review is unverified; check before filling.',
            'Stop owned same-defect siblings immediately; preserve every failure/interruption and classify cap_end separately.',
            'No training RGB/data/student runs before >=38/40 and separate recording admission.'])
    return q


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--rejection-table',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();q=build(a.source,a.evidence.resolve(),a.rejection_table.resolve())
    with a.output.open('x') as f:f.write(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:q[k] for k in ('source_sha','status','rejection_table','first_two_seeds','gate_measured_N')}))
