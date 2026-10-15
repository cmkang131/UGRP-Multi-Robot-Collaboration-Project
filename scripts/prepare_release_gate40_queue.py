"""Offline gate manifests with pinned controller SHA and external episode inputs.

Never submits commands. --commands only expands JSON argv for the coordinator,
who must supply a clean source checkout at each candidate's exact SHA.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[1]
BASE = 'a3bbc90e07d3d731278cb6c83185687a190e3c6b'
RECORD = 'experiments/2026-10-14-e2e18-grasp-rootcause'
PLAN = RECORD + '/release18-gate40-plan.json'
QUEUE_ROOT = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
FLAGS = ('approved', 'enabled', 'ready', 'submitted', 'scheduled', 'executed')
GUARD = """import subprocess,sys
source,expected=sys.argv[1:3]
if subprocess.check_output(['git','-C',source,'rev-parse','HEAD'],text=True).strip()!=expected: raise SystemExit('source SHA mismatch')
if subprocess.check_output(['git','-C',source,'status','--porcelain']): raise SystemExit('source dirty')
raise SystemExit(subprocess.call(sys.argv[3:]))
"""
# Input is shipped inside argv: the old controller needs no new plan file or
# modified source. run() writes its normal raw/plan.json and manifest.
ENTRY = """import base64,hashlib,json,sys,zlib
from pathlib import Path
from scripts.run_grasp_act_release import run
raw=zlib.decompress(base64.b64decode(sys.argv[1]))
if hashlib.sha256(raw).hexdigest()!=sys.argv[2]: raise SystemExit('plan hash mismatch')
plan=json.loads(raw)
print(json.dumps(run(plan['episodes'][int(sys.argv[3])],Path(sys.argv[4]),cap_s=180,**json.loads(sys.argv[5]))))
"""


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def build(candidate_sha=None):
    raw = (ROOT/PLAN).read_bytes()
    plan = json.loads(raw)
    profile = dict(plan['execution_profile'])
    candidates = [dict(id='A', source_sha=BASE, execution_profile=profile)]
    if candidate_sha:
        candidates.append(dict(id='B', source_sha=candidate_sha,
                               execution_profile={**profile, 'release_profile':'release19_v1'}))
    runs = []
    for c in candidates:
        for i, ep in enumerate(plan['episodes']):
            runs.append(dict(candidate=c['id'], source_sha=c['source_sha'], episode=i, seed=ep['seed'],
                             name=f"r{'18' if c['id']=='A' else '19'}g-{i:02d}-{c['source_sha'][:8]}",
                             **{f:False for f in FLAGS}))
    return dict(schema='ugrp.release_gate40.queue.v1', owner='codex-release19', pr=491, host='gcp1',
                branch='claude/grasp-act-probes', created_utc=datetime.now(timezone.utc).isoformat(),
                sha=candidate_sha or BASE, source_worktree=str(ROOT),
                runner_cwd='/Users/changmin/projects/ugrp-wt/gcp-sim-host',
                source_checkout_policy='Coordinator supplies clean pinned source per candidate; never reset the active worktree. Use --commands --source-worktree PATH --candidate A|B to expand argv.',
                status='PREPARED_NOT_APPROVED', **{f:False for f in FLAGS},
                stage_ready=dict(gate=False), coordinator_approval=dict(approved=False),
                gate_promotion_authorized_if_all_conditions_pass=False, training_rgb=False,
                remote_host_contacted=False, authorized_run_count=0, run_count=len(runs),
                max_combined_concurrency=16, storage_budget_mib=dict(per_run=96,total=96*len(runs)),
                criteria={**plan['criteria'], 'required':38,'N':40,
                          'handoff_failure':'failure; no replacement', 'HOST_ERROR':'failure; no replacement',
                          'timeout':'failure', 'cap_s':180, 'invisible_measurements':0,'held_world_reads':0},
                pooling='Forbidden across candidates, diagnostics, prefixes, earlier releases or hosts; report A and B independently as n/40.',
                candidates=candidates, plan_path=PLAN, plan_sha256=hashlib.sha256(raw).hexdigest(),
                plan_zlib_base64=base64.b64encode(zlib.compress(raw,9)).decode(),
                command_template=['python3','-c',GUARD,'{source}','{sha}','python3','scripts/remote_run.py',
                    '--host','gcp1','--detach','--class','dev','--pr','491','--per-run-mb','96','{source}','{name}',
                    '--','.venv-sim/bin/python','-c',ENTRY,'{plan}','{plan_sha}','{episode}',
                    '/home/ugrp/ugrp-sim/runs/{name}/raw','{profile}'],
                stop_rule='Confirmed physical/control defect: stop owned same-defect running/pending jobs, preserve raw; fix and restart without pooling.',
                runs=runs)


def commands(q, source, candidate):
    c = next(c for c in q['candidates'] if c['id']==candidate)
    for r in q['runs']:
        if r['candidate'] != candidate:
            continue
        values=dict(source=str(source),sha=c['source_sha'],name=r['name'],plan=q['plan_zlib_base64'],
                    plan_sha=q['plan_sha256'],episode=str(r['episode']),profile=compact(c['execution_profile']).decode())
        yield [v.format(**values) if v not in (GUARD,ENTRY) else v for v in q['command_template']]


def verify(q):
    raw=zlib.decompress(base64.b64decode(q['plan_zlib_base64']))
    assert hashlib.sha256(raw).hexdigest()==q['plan_sha256']
    plan=json.loads(raw)
    assert len(plan['episodes'])==40 and len({e['seed'] for e in plan['episodes']})==40
    assert q['criteria']['required']==38 and q['criteria']['N']==40
    assert q['criteria']['cap_s']==180 and q['criteria']['handoff_failure'].startswith('failure')
    for item in [q,*q['runs']]:
        assert all(item[f] is False for f in FLAGS)
    assert q['authorized_run_count']==0 and not q['stage_ready']['gate']
    assert q['coordinator_approval']['approved'] is False
    assert not q['gate_promotion_authorized_if_all_conditions_pass'] and not q['training_rgb']
    assert q['run_count']==40*len(q['candidates'])==len(q['runs'])
    for c in q['candidates']:
        assert len(c['source_sha'])==40 and all(v in '0123456789abcdef' for v in c['source_sha'])
        assert c['execution_profile']['held_object']=='hidden_v1'
        runs=[r for r in q['runs'] if r['candidate']==c['id']]
        assert [r['seed'] for r in runs]==[e['seed'] for e in plan['episodes']]
        assert all(r['source_sha']==c['source_sha'] for r in runs)
        expanded=list(commands(q,Path('/pinned-source'),c['id']))
        assert len(expanded)==40 and all(ENTRY in cmd for cmd in expanded)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--candidate-sha')
    p.add_argument('--verify',type=Path)
    p.add_argument('--commands',type=Path)
    p.add_argument('--source-worktree',type=Path)
    p.add_argument('--candidate',choices=('A','B'),default='A')
    p.add_argument('--queue-root',type=Path,default=QUEUE_ROOT)
    a=p.parse_args()
    if a.verify or a.commands:
        q=json.loads((a.verify or a.commands).read_text());verify(q)
        if a.commands:
            if not a.source_worktree:p.error('--commands requires --source-worktree')
            for cmd in commands(q,a.source_worktree,a.candidate):print(json.dumps(cmd))
        else:print(f"verified: {q['run_count']} runs, all approval/execution flags false")
        return
    q=build(a.candidate_sha);verify(q)
    path=a.queue_root/f"20261015-release-gate40-{q['sha'][:8]}.json"
    with path.open('x') as f:f.write(json.dumps(q,ensure_ascii=False,separators=(',',':'))+'\n')
    assert path.stat().st_size<65536
    print(path)

if __name__=='__main__':main()
