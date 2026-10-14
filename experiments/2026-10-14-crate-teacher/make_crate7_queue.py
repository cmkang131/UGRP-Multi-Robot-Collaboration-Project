"""Publish only the authorized fresh diagnostic queue, after clean commit/push.

No remote host access/submission, no gate40, no simulation or model calls.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
ADMIN = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin')
OLD_NAME = '20261014-crate-8c2395d0.json'
PLAN = 'diag_plan_crate7_77940.json'


def build_queue(old, sha, plan, summary):
    q = deepcopy(old)
    short = sha[:8]
    for key in ('blocked_reasons', 'superseded_reason', 'superseded_by', 'superseded_utc'):
        q.pop(key, None)
    q.update(owner='codex-crate7', sha=sha, remote_verified_sha=sha,
             created_utc=datetime.now(timezone.utc).isoformat(), status='ready', ready=True,
             runs_enabled=True, supersedes=[OLD_NAME], run_count=10,
             cargo_scene_version='crate_mass_025_v1', crate_lift_pose='crate_lift_pose_margin_v1',
             stage_counts={'diagnostic': 10}, stage_max_parallel={'diagnostic': 10},
             purpose='Authorized 0.25 kg command-margin diagnostic only; no success/gate claim',
             order='Run fresh diagnostic10 only. No gate stage is authorized; coordinator approval is separate.',
             profile=old['profile'].replace('crate_mass_030_v1', 'crate_mass_025_v1')+' / crate_lift_pose_margin_v1',
             storage_budget_mib={'diagnostic': 640, 'total_new_raw_upper_estimate': 640,
                                 'scope': '64 MiB/run; source/archive duplication also budgeted'},
             pooling='Never pool with crate6 or earlier masses, sources, profiles or machine types.',
             worktree_hold='Operations must verify the clean worktree HEAD and remote SHA equal this queue before snapshotting.',
             remaining_unverified=summary['remaining_unverified'],
             seed_reservation={'fresh_diagnostic_inclusive': [77940, 77949], 'split': 'crate_diagnostic',
                               'never_train': True, 'status': 'reserved_local',
                               'freshness': 'no local queue/run evidence at preparation; remote inventory not accessed; operations must verify unused'},
             candidate_record={'record': str(EXP/'crate7.md'), 'summary': str(EXP/'crate7-summary.json'),
                               'local_tests': summary['local_tests'], 'new_remote_runs': 0,
                               'runtime_audit': 'unverified', 'weight_changed': True, 'pose_selector_toggle_added': True},
             offline_preflight={'status': 'passed_for_diagnostic_only', 'summary': str(EXP/'crate7-summary.json'),
                                'summary_sha256': hashlib.sha256((EXP/'crate7-summary.json').read_bytes()).hexdigest(),
                                'exact_old_replay_verified': False, 'torque_margin_witness': True,
                                'all_targets_have_candidate': False, 'remote_seed_freshness_verified': False},
             preconditions=[
                 'Before execution operations verifies GCP credit stop, 8h cap, 20min idle guard, disk budget, global concurrency <=16 and fresh unused seeds.',
                 'Freeze clean worktree HEAD/remote at the queue SHA; keep all profiles, normal contacts and weld OFF.',
                 'No candidate is a stop outcome; do not restore the legacy high-torque lift or alter radius/pitch/contact constraints to continue.',
                 'Inspect first30 raw including issued pose, selected-prefix torque, held_world_reads=0 and invisible_measurements=0; static statics are not actual loads.',
                 'Review both robots and at least six evenly spaced video frames before diagnosing failures; stop same-defect pending/running jobs immediately.',
                 'Both own RGB confirmations are still required. Shorter lift visibility, unequal sharing, actual clearance and collisions are unverified.',
                 'Retrieve all runs including failures/HOST_ERROR with raw hashes. Gate40 requires separate coordinator approval; no automatic promotion.'])
    q['criteria'] = {k: v for k, v in old['criteria'].items() if k not in ('required', 'N', 'denominators', 'start_los')}
    q['criteria'].update(denominators='diagnostic full N=10, including failure/HOST_ERROR; no gate in this queue',
                         start_los={'toggle': 'start_assigned_los_v1', 'diagnostic_both_pass': '10/10 static only'},
                         static_elbow_threshold_nm=.15886773, no_candidate='stop and record none')
    q['plan_sha256'] = {PLAN: hashlib.sha256((EXP/PLAN).read_bytes()).hexdigest()}
    q['speed_limit'].update(basis='New 0.25 kg/profile: inspect diagnostic first30; old speed is reference only, no gate qualification')
    q['runs'] = []
    for index, episode in enumerate(plan['episodes']):
        seed = episode['seed']
        name = f'crate-diag-{seed}-{short}'
        payload = ['.venv-sim/bin/python', '-m', 'scripts.run_crate_teacher', '--plan', f'experiments/2026-10-14-crate-teacher/{PLAN}',
                   '--episode', str(index), '--grasp-cap-s', '80', '--cap-s', '90', '--observe-mode', 'backoff_v3',
                   '--zone-slots', 'zone', '--reach-mode', 'pad_window_v2', '--own-pose-source', 'commands',
                   '--held-object', 'hidden_v1', '--setdown-lookaround', 'off', '--crate-scene', 'crate_mass_025_v1',
                   '--crate-lift-pose', 'crate_lift_pose_margin_v1', '--rgb-lift', 'crate_rgb_lift_v3',
                   '--teacher-stability', 'align_relook_v1', '--teacher-search', 'search_reacquire_v1',
                   '--approach-goal-set', 'approach_goal_set_v1', '--execution-host', 'gcp1', '--pr', '500',
                   '--out', f'/home/ugrp/ugrp-sim/runs/{name}/raw']
        q['runs'].append({'stage': 'diagnostic', 'seed': seed, 'scenario_id': episode['scenario_id'], 'name': name,
                          'ready': True, 'status': 'ready', 'runs_enabled': True, 'max_parallel': 10, 'max_other_running': 6,
                          'cargo_scene_version': q['cargo_scene_version'], 'crate_lift_pose': q['crate_lift_pose'],
                          'maximum_sim_s_per_episode': 170, 'payload': payload,
                          'condition': 'diagnostic only; operations preconditions; no candidate -> stop',
                          'command': ['python3', 'scripts/remote_run.py', '--host', 'gcp1', '--detach', '--class', 'dev',
                                      '--pr', '500', '--per-run-mb', '64', str(ROOT), name, '--', *payload]})
    assert [r['seed'] for r in q['runs']] == list(range(77940, 77950))
    assert set(r['stage'] for r in q['runs']) == {'diagnostic'}
    return q


def main():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    sha = git('rev-parse', 'HEAD')
    branch = git('branch', '--show-current')
    assert branch == 'claude/act-crate-teacher' and not git('status', '--porcelain')
    assert git('remote', 'get-url', 'origin') == 'https://github.com/kcm0127-dotcom/ugrp.git'
    remote = git('ls-remote', 'origin', 'refs/heads/'+branch).split()[0]
    assert remote == sha
    summary = json.loads((EXP/'crate7-summary.json').read_text())
    assert summary['local_tests']['failed'] == 0 and summary['local_tests']['passed'] > 0
    for ref in summary['artifacts'].values():
        assert hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest() == ref['sha256']
    oldpath = ADMIN/'vm3-queue'/OLD_NAME
    old = json.loads(oldpath.read_text())
    assert old['sha'] == '8c2395d07f2e7426dc7b101c4869a021a00255b2'
    plan = json.loads((EXP/PLAN).read_text())
    q = build_queue(old, sha, plan, summary)
    dest = oldpath.with_name(f'20261014-crate-{sha[:8]}.json')
    assert not dest.exists()
    dest.write_text(json.dumps(q, ensure_ascii=False, indent=2)+'\n')
    old.update(status='superseded', ready=False, runs_enabled=False, superseded_by=dest.name,
               superseded_utc=q['created_utc'], superseded_reason='2026-10-14 user selected 0.25 kg; fresh command-margin diagnostic only')
    for row in old['runs']:
        row.update(ready=False, status='superseded', runs_enabled=False)
    oldpath.write_text(json.dumps(old, ensure_ascii=False, indent=2)+'\n')
    saved = json.loads(dest.read_text())
    assert saved['sha'] == remote and saved['ready'] and len(saved['runs']) == 10
    delivery = {'sha': sha, 'remote_verified_sha': remote, 'queue': str(dest),
                'queue_sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'superseded': str(oldpath),
                'record': str(EXP/'crate7.md'), 'ready': True, 'stages': ['diagnostic'], 'remote_runs_submitted': 0}
    (ADMIN/'crate7-delivery.json').write_text(json.dumps(delivery, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(delivery, ensure_ascii=False))


if __name__ == '__main__':
    main()
