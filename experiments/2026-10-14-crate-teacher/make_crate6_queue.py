"""Publish a BLOCKED operations queue after a clean commit/push; no submissions."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
ADMIN = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin')


def main():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    sha = git('rev-parse', 'HEAD')
    branch = git('branch', '--show-current')
    assert branch == 'claude/act-crate-teacher' and not git('status', '--porcelain')
    remote = git('ls-remote', 'origin', 'refs/heads/'+branch).split()[0]
    assert remote == sha
    subprocess.run(['git', 'merge-base', '--is-ancestor', '77ee0ab7', sha], cwd=ROOT, check=True)
    summary_path = EXP/'crate6-summary.json'
    summary = json.loads(summary_path.read_text())
    assert summary['status'] == 'blocked' and summary['ready'] is False
    for ref in summary['artifacts'].values():
        assert hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest() == ref['sha256']
    assert not json.loads((EXP/'crate6-torque.json').read_text())['all_lifted_heights_scan']['qualified']
    oldpath = ADMIN/'vm3-queue/20261014-crate-b033e5f9.json'
    old = json.loads(oldpath.read_text())
    assert old['sha'] == 'b033e5f914a0d3e221eb77db455d84288104b004'
    q = deepcopy(old)
    now = datetime.now(timezone.utc).isoformat()
    dest = oldpath.with_name(f'20261014-crate-{sha[:8]}.json')
    q.update(owner='codex-crate6', sha=sha, remote_verified_sha=remote, created_utc=now,
        status='blocked', ready=False, runs_enabled=False, supersedes=[oldpath.name],
        purpose='Preserve diagnostic10 + provisional gate40; no run before torque/replay/freshness blockers are resolved',
        order='BLOCKED: no diagnostic or gate submissions. After a user/coordinator decision, revised code must restart diagnostic10 before gate40.',
        blocked_reasons=summary['blocked_reasons'],
        merged_search_sha=summary['merged_sha'],
        offline_preflight={'status':'blocked', 'summary':str(summary_path),
            'summary_sha256':hashlib.sha256(summary_path.read_bytes()).hexdigest(),
            'exact_replay_verified':False, 'torque_margin_passed':False,
            'visual_review':'87/87 retrieved, hashed and viewed', 'start_los':'40/40 static only',
            'remote_seed_freshness_verified':False},
        candidate_record={'record':str(EXP/'crate6.md'),'local_tests':summary['local_tests'],
            'new_gcp_runs':0,'runtime_audit':'unverified','weight_changed':False,'pose_selector_toggle_added':False},
        preconditions=[*summary['blocked_reasons'],
            'Do not override ready=false; obtain a new reviewed code/queue after the user/coordinator mass or scope decision.',
            'Before any future enablement, verify GCP credit stop/8h cap/20min idle guard, clean frozen SHA, disk budget and global concurrency <=16.',
            'Gate needs all diagnostic10 successes; stop immediately on confirmed defects; no pooling with older sources or hosts.'],
        worktree_hold='Blocked queue is not an execution lease. Operations must not snapshot/submit this source for physical runs.',
        max_combined_concurrency=16, max_parallel_per_stage=16,
        stage_max_parallel={'diagnostic':10,'gate':16},
        pooling='This candidate has no physical results. Historical b033/6f312 results remain separate.')
    q['seed_reservation'].update(status='provisional_blocked',
        freshness='no local evidence; remote inventory failed; operations must verify 77300-77339 unused before enabling')
    q['criteria']['start_los'].update(gate_both_pass='40/40 statically rechecked',
        original_rejected='14/40 in frozen v7 proposal distribution')
    for key in ('superseded_reason','superseded_by','superseded_utc'):
        q.pop(key,None)
    for row in q['runs']:
        row.update(ready=False, status='blocked', runs_enabled=False,
                   condition='BLOCKED: see top-level blocked_reasons; do not submit')
        row['name'] = row['name'].replace('b033e5f9',sha[:8])
        for key in ('payload','command'):
            row[key] = [str(v).replace('b033e5f9',sha[:8]) for v in row[key]]
    assert len(q['runs']) == 50
    assert [r['seed'] for r in q['runs'] if r['stage']=='gate'] == list(range(77300,77340))
    assert sorted(r['seed'] for r in q['runs'] if r['stage']=='diagnostic') == [77204,77208,77212,77231,77920,77921,77922,77930,77931,77932]
    for name, digest in q['plan_sha256'].items():
        assert hashlib.sha256((EXP/name).read_bytes()).hexdigest() == digest
    dest.write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    old.update(status='superseded',ready=False,runs_enabled=False,superseded_by=dest.name,
               superseded_utc=now,superseded_reason='77ee0ab7 merged; crate6 torque/replay audit blocks further execution')
    for row in old['runs']:
        row.update(ready=False,runs_enabled=False,status='superseded')
    oldpath.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    saved = json.loads(dest.read_text())
    assert saved['sha']==remote and saved['status']=='blocked' and not any(r['ready'] for r in saved['runs'])
    print(json.dumps({'queue':str(dest),'sha':sha,'status':'blocked','ready':False,'runs':50,'superseded':str(oldpath)}))


if __name__ == '__main__':
    main()
