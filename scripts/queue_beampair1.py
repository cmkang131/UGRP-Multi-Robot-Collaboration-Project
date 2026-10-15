"""Prepare, never submit, a source-bound long_beam gate40 operator queue."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from harness.beampair_teacher import DEPENDENCY_SHA,MODE

ROOT=Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/2026-10-15-beampair1'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_evidence(report,table,source,*,expected_bursts=None):
    if not table.is_absolute() or not table.is_file():raise ValueError('existing absolute rejection_table required')
    funnel=json.loads(table.read_text())
    if funnel.get('source_sha')!=source:raise ValueError('rejection_table source mismatch')
    if (report['source_sha']!=source or report['N']!=6 or report['n']<4
            or report['incomplete_N'] or report['held_world_reads'] or report['invisible_measurements']
            or report['missing_rejection_audit_N']):
        raise ValueError('short6 acceptance/integrity/input audit incomplete')
    lengths=[]
    for r in report['runs']:
        if not r['held_object_hidden_v1'] or not r['hidden_measurement_ticks']:
            raise ValueError('held-cargo audit is missing or vacuous')
        if r['probe_executed_ticks']['r1']!=r['probe_burst_ticks']['r1']:
            raise ValueError('truncated r1 recovery burst')
        lengths.append(r['probe_executed_ticks']['r1'])
    expected=[1,3,5,8,10,12] if expected_bursts is None else sorted(expected_bursts)
    if sorted(lengths)!=expected:raise ValueError('frozen burst envelope not physically exercised')


def build(source,worktree,evidence,table):
    report=json.loads(evidence.read_text());validate_evidence(report,table,source)
    if subprocess.check_output(['git','-C',str(worktree),'rev-parse','HEAD'],text=True).strip()!=source:
        raise ValueError('pinned worktree SHA mismatch')
    if subprocess.check_output(['git','-C',str(worktree),'status','--porcelain']):
        raise ValueError('pinned worktree must be clean')
    plan_path='experiments/2026-10-15-beampair1/gate-plan.json'
    frozen=subprocess.check_output(['git','-C',str(worktree),'show',source+':'+plan_path])
    if hashlib.sha256(frozen).hexdigest()!=sha(ROOT/plan_path):raise ValueError('gate plan differs from tested source')
    plan=json.loads(frozen);episodes=plan['episodes']
    if len(episodes)!=40 or len({e['seed'] for e in episodes})!=40:raise ValueError('40 distinct frozen trials required')
    hashes={p:hashlib.sha256(subprocess.check_output(['git','-C',str(worktree),'show',source+':'+p])).hexdigest()
        for p in ('scripts/run_beampair1.py','harness/beampair_teacher.py','harness/grasp_act_perturb.py',
                  'experiments/2026-10-15-beampair1/scenario-v7.json',plan_path)}
    runs=[]
    for i,e in enumerate(episodes):
        name=f'beampair1-gate-{e["seed"]}-{source[:8]}'
        remote='/home/ugrp/ugrp-sim/runs/'+name
        command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','522',
            '--per-run-mb','128',str(worktree),name,'--','.venv-sim/bin/python','-m','scripts.run_beampair1',
            '--plan',plan_path,'--episode',str(i),'--dependency-root','/home/ugrp/ugrp-sim/src/'+DEPENDENCY_SHA,
            '--out',remote+'/raw','--mode',MODE,'--candidate','baseline','--cap-s','60']
        runs.append(dict(name=name,seed=e['seed'],episode=i,source_sha=source,command=command,
            training_rgb=False,approved=False,submitted=False,burst_ticks=e['burst_ticks'],roles=e['roles']))
    return dict(schema='ugrp.beampair1.gate40_queue.v1',owner='beampair1',branch='claude/beam-pair-teacher',pr=522,
        status='PREPARED_NOT_SUBMITTED',ready=True,approved=False,submitted=False,
        source_sha=source,sha=source,source_worktree=str(worktree),pinned_worktree=str(worktree),
        remote_pinned_worktree='/home/ugrp/ugrp-sim/src/'+source,dependency_sha=DEPENDENCY_SHA,
        dependency_root='/home/ugrp/ugrp-sim/src/'+DEPENDENCY_SHA,source_hashes=hashes,
        host='gcp1',project_id='ugrp-act-train-1014',machine_type='n4-highcpu-64',planned_N=40,
        max_parallel=16,host_total_concurrency_limit=40,training_rgb=False,
        scene='cargo_v7 / grasp_act_teal_blue_v1',weld='off',held_object_hidden_v1=True,
        minimum_success=38,qualification_denominator=40,gate_measured_N=0,
        criteria=dict(whole_beam_min_z_m=.012,max_tilt_deg=10,bilateral_finger_min_N=.5,hold_sim_s=3),
        rejection_table=str(table),rejection_table_sha256=sha(table),
        setup_funnel=str((EXP/'setup-funnel.json').resolve()),setup_funnel_sha256=sha(EXP/'setup-funnel.json'),
        exploration_evidence=str(evidence),exploration_evidence_sha256=sha(evidence),
        first_two_seeds=[e['seed'] for e in episodes[:2]],first30_review_before_fill=True,
        required_before_start=[
            'Verify source/dependency SHA and clean pinned worktrees, all source hashes, and rejection_table existence/hash.',
            'Operator activation is required. This queue has not submitted any gate trials.',
            'Recheck global capacity <=40, own maximum16, memory>=6GiB, disk>=8GiB, budget-stop, idle20min and max8h guards.',
            'Current candidate speed was measured only at6 concurrent runs; planned16 first30 speed must be verified before filling.',
            'Review first two whole trajectories and first30 own-camera/protocol/input ledgers before filling the queue.',
            'Stop owned same-defect running/waiting trials immediately on confirmed control/physics failure; preserve originals.',
            'Record cap_end separately, every rejection reason/object/gap, and actual disturbance lengths; never pool R1/R2/R3.',
            'No training RGB/data collection before this source independently reaches >=38/40 and recording admission is checked.'],
        runs=runs)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True)
    p.add_argument('--worktree',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--rejection-table',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();q=build(a.source,a.worktree.resolve(),a.evidence.resolve(),a.rejection_table.resolve())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:f.write(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(path=str(a.output.resolve()),source_sha=q['source_sha'],planned_N=40,submitted=False)))
