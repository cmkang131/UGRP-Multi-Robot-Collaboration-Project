"""Offline v6 carry diagnostic plan / disabled coordinator queue; no submission."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.make_solo_teacher_plan import episode
from sim.grasp_act_solo_teacher import BOX_KINDS
from harness.grasp_act_seed_splits import check_range
from harness.zone_environment_registry import load_scenario
from harness.zone_final_environment import resolve, digest

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'experiments/2026-10-15-map-carry-zone/diagnostic-plan.json'
SCENARIOS = ('s1_normal_mixed_v6', 's2_unmapped_blockage_v6', 's3_late_rendezvous_v6',
             's5_moved_dropped_item_v6', 's6_novel_relation_v6', 's7_pair_with_solo_v6', 's8_mixed_tiers_v6')


def prepare():
    check_range('solo_carry_diagnostic_v1', 93200, 8)
    episodes = []
    for i, kind in enumerate(BOX_KINDS*2):
        p = episode(i//4, kind, 93200+i, 'solo_carry_diagnostic_v1', scenarios=SCENARIOS)
        scenario = load_scenario(p['scenario_id'])
        placement = next(x for x in scenario['eval']['setup']['placements'] if x['item_id'] == p['item_id'])
        order = next(x for x in scenario['orders'] if x['order_id'] == placement['order_id'])
        static, _, _ = resolve(p['map_id'])
        p.pop('handoff_pose_error')  # no fabricated self pose anywhere in this profile
        p.update(solo_carry_to_zone_v1=True, destination_zone=order['destination_zone'],
                 static_map_sha256=digest(static), negative_probe=False, gate_eligible=False,
                 training_eligible=False, batch='solo-carry-zone-v1', training_rgb=False)
        episodes.append(p)
    return {'schema': 'ugrp.solo_carry_plan.v1', 'episodes': episodes,
            'distribution': dict(Counter(e['kind'] for e in episodes)),
            'research_result': False, 'training_rgb': False, 'gate_eligible': False,
            'gate_promotion_authorized_if_all_conditions_pass': False}


def queue(plan, sha, pr):
    runs = []
    for i, p in enumerate(plan['episodes']):
        name = f"solo-carry-{p['seed']}-{sha[:8]}"
        runs.append({'name': name, 'seed': p['seed'], 'kind': p['kind'], 'enabled': False,
            'source_sha': sha, 'requires_coordinator_approval': True, 'stage': 'diagnostic',
            'command': ['python3', 'scripts/remote_run.py', '--host', 'gcp1', '--detach',
                '--class', 'dev', '--pr', str(pr), '--per-run-mb', '256', str(ROOT), name, '--',
                '.venv-sim/bin/python', '-m', 'scripts.run_solo_grasp_act_teacher',
                '--execution-host', 'gcp1', '--teacher-profile', 'solo_visible_only_v1',
                '--held-object-hidden-v1', '--setdown-lookaround-v1', '--teacher-stability',
                'align_relook_v1', '--reach-mode', 'pad_window_v2', '--rgb-lift-mode',
                'solo_lift_lookback_v1', '--solo-lift-lookback-margin-v1',
                '--solo-truth-free-lookaround-v1', '--solo-carry-to-zone-v1',
                '--plan', PLAN, '--episode', str(i), '--cap-s', '300',
                '--out', f'/home/ugrp/ugrp-sim/runs/{name}/raw']})
    return {'schema': 'ugrp.solo_carry_queue.v1', 'branch': 'claude/map-carry-zone', 'pr': pr,
        'sha': sha, 'host': 'gcp1', 'machine_type': 'n4-highcpu-64', 'project': 'ugrp-act-train-1014',
        'source_worktree': str(ROOT), 'runner_cwd': '/Users/changmin/projects/ugrp',
        'status': 'prepared_not_submitted', 'ready': False, 'runs_enabled': False,
        'coordinator_approval': {'approved': False, 'source_sha': sha, 'review': None},
        'gate_promotion_authorized_if_all_conditions_pass': False, 'gate_eligible': False,
        'training_rgb': False, 'run_count': 8, 'runs': runs, 'max_parallel': 1,
        'plan_sha256': hashlib.sha256((ROOT/PLAN).read_bytes()).hexdigest(),
        'seed_reservation': {'split': 'solo_carry_diagnostic_v1', 'range': [93200, 93207],
                             'remote_unused_verified': False},
        'storage_budget_mib': {'per_run': 256, 'total': 2048, 'measured': False},
        'preconditions': [
            'Explicit coordinator approval of exact pushed source SHA and hashed plan before any run.',
            'Use primary standard GCP remote_run.py with frozen source worktree; no Mac/other-host execution.',
            'Check live unused seeds, model endpoint alerts, project budget-stop and cost admission.',
            'Keep 8h STOP + idle20min guards; storage_budget.py --all-hosts includes other reserved writes.',
            'Measure same-machine first30 speed at concurrency1 before further diagnostic admission; no inherited speed claim.',
            'Inspect first30 and at least6 evenly spaced own/top frames (also >=1 per60 SIM s), including carry and new-zone release.',
            'Check RGB motion association identity/yaw and loaded motion, no stale self pose or held truth reads; stop common defects immediately.',
            'Report all8 including failure/HOST_ERROR; compare whole-footprint zone release, no-drop and SIM time separately.',
            'Preserve raw frames/commands/evaluation, retrieve manifest hashes, verify VM stopped; no automatic gate/training promotion.']}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--plan-out', type=Path)
    p.add_argument('--queue-out', type=Path)
    p.add_argument('--pr', type=int)
    a = p.parse_args()
    if a.plan_out:
        plan = prepare()
        a.plan_out.parent.mkdir(parents=True, exist_ok=True)
        with a.plan_out.open('x') as f:
            json.dump(plan, f, indent=2); f.write('\n')
    if a.queue_out:
        if not a.pr:
            p.error('--pr required for queue')
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        plan = json.loads((ROOT/PLAN).read_text())
        with a.queue_out.open('x') as f:
            json.dump(queue(plan, sha, a.pr), f, indent=2); f.write('\n')


if __name__ == '__main__':
    main()
