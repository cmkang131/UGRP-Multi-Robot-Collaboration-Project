"""Write a reviewable local queue after push; never connect to a VM."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

EXP = Path(__file__).resolve().parent
ROOT = EXP.parents[1]
ADMIN = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin')
OLD = ADMIN/'vm3-queue/20261015-crate-bf31840f.json'
STAGES = [('diagnostic', 'diag_plan_crate10_77980.json', 10),
          ('reproduction', 'repro_plan_crate10.json', 3),
          ('gate', 'gate_plan_crate10_77400.json', 40)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(sha, summary):
    old = json.loads(OLD.read_text())
    q = {k: deepcopy(old[k]) for k in ('branch', 'pr', 'host', 'machine_type', 'azure_allowed',
        'submission_owner', 'source_worktree', 'runner_cwd', 'runner_note', 'stop_rule', 'admission', 'speed_limit')}
    q.update(owner='codex-crate10', sha=sha, remote_verified_sha=sha,
        created_utc=datetime.now(timezone.utc).isoformat(), status='ready', ready=True, runs_enabled=True,
        previous_completed_queue={'path': str(OLD), 'sha256': digest(OLD), 'never_resubmit': True,
            'file_status_observed': old['status'], 'operational_result': 'completed diagnostic 8/10; file preserved verbatim'},
        run_count=53, stage_counts={stage: n for stage, _, n in STAGES},
        stage_order=['diagnostic + reproduction', 'coordinator approval of this SHA and evidence', 'gate'],
        max_combined_concurrency=40, max_parallel_per_stage=10,
        stage_max_parallel={stage: 10 for stage, _, _ in STAGES},
        cargo_scene_version='crate_mass_025_v1', crate_lift_pose='crate_antipodal_grasp_v1',
        crate_approach_recovery='crate_approach_recovery_v1',
        gate_promotion_authorized_if_all_conditions_pass=False,
        coordinator_approval={'approved': False, 'sha': sha, 'required_after': ['diagnostic', 'reproduction'],
                              'required_before': 'gate', 'prior_approval_inherited': False},
        purpose='Diagnostic10 fresh + exact failure reproductions3; independent new gate40 only after coordinator approval.',
        profile=old['profile']+' / crate_approach_recovery_v1 / approach_recovery_v1 / approach_progress_v1',
        criteria={**old['criteria'], 'diagnostic_required': 10, 'diagnostic_N': 10,
            'reproduction_required': 3, 'reproduction_N': 3,
            'diagnostic_success_required': '10/10 fresh AND 3/3 reproductions physically successful; handoff/timeout/HOST_ERROR are failures',
            'gate_N': 40, 'gate_minimum_physical_success': 38,
            'denominators': 'fresh diagnostic N=10 and reproduction N=3 separately; gate N=40 including all failures/HOST_ERROR; no pooling'},
        storage_budget_mib={'diagnostic': 1280, 'reproduction': 384, 'gate': 5120,
            'total_new_raw_upper_estimate': 6784, 'copies_budgeted_separately': True},
        plan_sha256={name: digest(EXP/name) for _, name, _ in STAGES},
        candidate_record={'record': str(EXP/'crate10.md'), 'summary': str(EXP/'crate10-summary.json'),
            'local_tests': summary['local_tests'], 'new_remote_runs': 0},
        seed_reservation={'fresh_diagnostic': list(range(77980, 77990)),
            'reproductions': [77969, 77978, 77979], 'fresh_gate': list(range(77400, 77440)),
            'never_train': True, 'local_unused_verified': True, 'remote_unused_verified': False},
        preconditions=[
            'Operations only: verify credit stop, GCP project ugrp-act-train-1014, 8h cap, 20min idle, disk and remote seed reservations.',
            'Freeze this clean pushed SHA and plan hashes; keep mass0.25kg, colors, weldOFF, cameras, servo/physics and all success criteria unchanged.',
            'Reserve under shared admission lock: combined active+reserved<=40, crate<=10. No independent check-then-launch.',
            'Measure first30 at actual planned load on this machine; median wall/SIM<=3.5. Existing 10-concurrency timing is not qualification for40.',
            'Inspect first30 and failure frames/ledgers, both audit counters0. Confirmed shared physical/control defect: stop same-defect running/pending jobs immediately.',
            'Static unreachable handoff is an explicit failure, never success. No forced grasp or hidden/held object coordinates for escape.',
            'Retrieve/hash/review all13 diagnostic/reproduction results, including failure/HOST_ERROR. Require10/10+3/3 physical success and no unresolved defects.',
            'Gate stays disabled even if all conditions pass: coordinator approval for THIS SHA/13-result evidence is mandatory before enabling gate40.',
            'No training capture before same-profile gate>=38/40; no automatic promotion or alternate host.'],
        remaining_unverified=summary['remaining_unverified'])
    q['runs'] = []
    for stage, filename, count in STAGES:
        episodes = json.loads((EXP/filename).read_text())['episodes']; assert len(episodes) == count
        for i, ep in enumerate(episodes):
            name = f"crate-{'diag' if stage == 'diagnostic' else stage}-{ep['seed']}-{sha[:8]}"
            enabled = stage != 'gate'
            payload = deepcopy(old['runs'][0]['payload'])
            for flag, value in [('--plan', f'experiments/2026-10-14-crate-teacher/{filename}'),
                                ('--episode', str(i)), ('--out', f'/home/ugrp/ugrp-sim/runs/{name}/raw')]:
                payload[payload.index(flag)+1] = value
            payload += ['--crate-approach-recovery', 'crate_approach_recovery_v1']
            q['runs'].append({'stage': stage, 'seed': ep['seed'], 'scenario_id': ep['scenario_id'],
                'name': name, 'ready': enabled, 'runs_enabled': enabled,
                'status': 'ready' if enabled else 'awaiting_coordinator_approval',
                'max_parallel': 10, 'max_other_running': 30, 'max_combined_concurrency': 40,
                'maximum_sim_s_per_episode': 170, 'payload': payload,
                'command': ['python3', 'scripts/remote_run.py', '--host', 'gcp1', '--detach', '--class', 'dev',
                            '--pr', '500', '--per-run-mb', '128', str(ROOT), name, '--', *payload]})
    return q


def main():
    def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    assert git('branch', '--show-current') == 'claude/act-crate-teacher'
    assert not git('status', '--porcelain')
    assert git('remote', 'get-url', 'origin') == 'https://github.com/kcm0127-dotcom/ugrp.git'
    sha = git('rev-parse', 'HEAD')
    assert git('ls-remote', 'origin', 'refs/heads/claude/act-crate-teacher').split()[0] == sha
    summary = json.loads((EXP/'crate10-summary.json').read_text())
    assert summary['local_tests']['failed'] == 0 and summary['local_tests']['passed'] > 0
    for ref in summary['artifacts'].values():
        assert digest(Path(ref['path'])) == ref['sha256']
    assert json.loads(OLD.read_text())['sha'] == 'bf31840fe16cd2d37631d8a8e50ff077e3d42575'
    before = OLD.read_bytes(); q = build(sha, summary)
    dest = OLD.with_name(f'20261015-crate-{sha[:8]}.json'); assert not dest.exists()
    assert len(q['runs']) == 53 and sum(r['runs_enabled'] for r in q['runs']) == 13
    assert not q['gate_promotion_authorized_if_all_conditions_pass'] and q['ready']
    dest.write_text(json.dumps(q, ensure_ascii=False, indent=2)+'\n')
    assert json.loads(dest.read_text()) == q and OLD.read_bytes() == before
    delivery = {'sha': sha, 'queue': str(dest), 'queue_sha256': digest(dest), 'ready': True,
                'gate_enabled': False, 'previous_queue_unchanged_sha256': digest(OLD), 'new_remote_runs': 0}
    (ADMIN/'crate10-delivery.json').write_text(json.dumps(delivery, indent=2)+'\n')
    print(json.dumps(delivery))


if __name__ == '__main__':
    main()
