"""Offline v6 carry diagnostic plan / disabled coordinator queue; no submission."""
import argparse
from collections import Counter
import hashlib
import json
import math
import random
from pathlib import Path
import subprocess

from scripts.make_solo_teacher_plan import episode, BASE_Z
from sim.solo_carry_pose import task_start
from sim.grasp_act_solo_teacher import BOX_KINDS
from harness.grasp_act_seed_splits import check_range
from harness.zone_environment_registry import load_scenario
from harness.zone_final_environment import resolve, digest

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'experiments/2026-10-15-map-carry-zone/diagnostic-plan-v4.json'
SCENARIOS = ('s1_normal_mixed_v6', 's2_unmapped_blockage_v6', 's3_late_rendezvous_v6',
             's5_moved_dropped_item_v6', 's6_novel_relation_v6', 's7_pair_with_solo_v6', 's8_mixed_tiers_v6')


def prepare_legacy_v2():
    check_range('solo_carry_diagnostic_v1', 93200, 8)
    episodes = []
    for i, kind in enumerate(BOX_KINDS*2):
        p = episode(i//4, kind, 93200+i, 'solo_carry_diagnostic_v1', scenarios=SCENARIOS)
        scenario = load_scenario(p['scenario_id'])
        placement = next(x for x in scenario['eval']['setup']['placements'] if x['item_id'] == p['item_id'])
        order = next(x for x in scenario['orders'] if x['order_id'] == placement['order_id'])
        static, _, _ = resolve(p['map_id'])
        p.pop('handoff_pose_error')
        start = task_start(static)
        # Scene owner constructs the declared task condition, never the reverse.
        # Setup perturbations stay out of the controller prior.
        rng = random.Random(193200+i)
        x, y, yaw = start['pose_m_rad']
        p['spawns']['r1'] = [x+rng.uniform(-.02, .02), y+rng.uniform(-.02, .02),
                             BASE_Z, yaw+rng.uniform(-math.radians(2.), math.radians(2.))]
        p['start_to_cargo_m'] = math.dist(p['spawns']['r1'][:2], p['cargo_pose_m'][:2])
        p.update(task_start=start, carry_pose_profile='own_command_v2', amcl_option='off',
                 start_setup_profile='task_start_jitter_2cm_2deg_v2')
        p.update(solo_carry_to_zone_v1=True, destination_zone=order['destination_zone'],
                 static_map_sha256=digest(static), negative_probe=False, gate_eligible=False,
                 training_eligible=False, batch='solo-carry-zone-v2', training_rgb=False)
        episodes.append(p)
    return {'schema': 'ugrp.solo_carry_plan.v2', 'episodes': episodes,
            'distribution': dict(Counter(e['kind'] for e in episodes)),
            'research_result': False, 'training_rgb': False, 'gate_eligible': False,
            'gate_promotion_authorized_if_all_conditions_pass': False}


def prepare(*, carry5=False, seed0=None, count=8, kind_offset=0):
    """Fresh layout generated against the actual task start and static corridors."""
    from sim.solo_pickup_search import PROFILE
    seed0 = (93240 if carry5 else 93220) if seed0 is None else seed0
    check_range('solo_carry_diagnostic_v1', seed0, count)
    episodes = []
    for i, kind in enumerate((BOX_KINDS*3)[kind_offset:kind_offset+count]):
        p = episode(i//4, kind, seed0+i, 'solo_carry_diagnostic_v1',
                    scenarios=SCENARIOS, carry_layout=True, carry5=carry5)
        scenario = load_scenario(p['scenario_id'])
        placement = next(x for x in scenario['eval']['setup']['placements'] if x['item_id'] == p['item_id'])
        order = next(x for x in scenario['orders'] if x['order_id'] == placement['order_id'])
        static = resolve(p['map_id'])[0]
        p.pop('handoff_pose_error')
        p.update(task_start=task_start(static), carry_pose_profile='own_command_v2', amcl_option='off',
                 start_setup_profile='task_start_jitter_2cm_2deg_v2', pickup_search_profile=PROFILE,
                 solo_carry_to_zone_v1=True, destination_zone=order['destination_zone'],
                 static_map_sha256=digest(static), negative_probe=False, gate_eligible=False,
                 training_eligible=False, batch='solo-carry-zone-v4', training_rgb=False)
        if carry5:
            p.update(carry5_profile='carry5_active_localization_v1', batch='solo-carry-zone-v5',
                     drive_model_dependency='claude/drive-model-deadband',
                     drive_model_required='drive_model_deadband_v1', drive_model_deadband_v1=True)
        episodes.append(p)
    return {'schema': 'ugrp.solo_carry_plan.v5' if carry5 else 'ugrp.solo_carry_plan.v4', 'episodes': episodes,
            'distribution': dict(Counter(e['kind'] for e in episodes)),
            'prior_seeds_used_or_reserved': [*range(93200, 93208), *range(93210, 93218),
                                             *(range(93220, 93228) if carry5 else ())],
            'research_result': False, 'training_rgb': False, 'gate_eligible': False,
            'gate_promotion_authorized_if_all_conditions_pass': False}


def queue(plan, sha, pr, *, plan_path=PLAN):
    carry5 = plan['schema'] == 'ugrp.solo_carry_plan.v5'
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
                '--plan', str(plan_path), '--episode', str(i), '--cap-s', '300',
                '--out', f'/home/ugrp/ugrp-sim/runs/{name}/raw']})
    result = {'schema': 'ugrp.solo_carry_queue.v5' if carry5 else 'ugrp.solo_carry_queue.v4', 'branch': 'claude/map-carry-zone', 'pr': pr,
        'sha': sha, 'host': 'gcp1', 'machine_type': 'n4-highcpu-64', 'project': 'ugrp-act-train-1014',
        'source_worktree': str(ROOT), 'runner_cwd': '/Users/changmin/projects/ugrp',
        'status': 'prepared_not_submitted', 'ready': False, 'runs_enabled': False,
        'coordinator_approval': {'approved': False, 'source_sha': sha, 'review': None},
        'gate_promotion_authorized_if_all_conditions_pass': False, 'gate_eligible': False,
        'training_rgb': False, 'top_rgb_control_allowed': False, 'amcl_option': 'off',
        'supersedes_blocked_queue': '20261015-solo-carry-de8c2412.json', 'run_count': 8, 'runs': runs, 'max_parallel': 1,
        'plan_sha256': hashlib.sha256((ROOT/plan_path).read_bytes()).hexdigest(),
        'seed_reservation': {'split': 'solo_carry_diagnostic_v1', 'range': [93240, 93247] if carry5 else [93220, 93227],
                             'remote_unused_verified': False},
        'storage_budget_mib': {'per_run': 256, 'total': 2048, 'measured': False},
        'preconditions': [
            'Explicit coordinator approval of exact pushed source SHA and hashed plan before any run.',
            'Use primary standard GCP remote_run.py with frozen source worktree; no Mac/other-host execution.',
            'Check live unused seeds, model endpoint alerts, project budget-stop and cost admission.',
            'Keep 8h STOP + idle20min guards; storage_budget.py --all-hosts includes other reserved writes.',
            'Record first30 wall/SIM in the first diagnostic; warn above3.5, block above6.0 or incomplete/HOST_ERROR, per coordinator 2026-10-15 policy.',
            'Inspect first30 and at least6 evenly spaced review frames (also >=1 per60 SIM s), including carry and new-zone release; top frames are evaluation only.',
            'Check declared task start versus setup in evaluation only, own-command drift/uncertainty, destination own RGB and post-release landmarks; no top RGB control or held truth reads.',
            'Report all8 including failure/HOST_ERROR; compare whole-footprint zone release, no-drop and SIM time separately.',
            'Preserve raw frames/commands/evaluation, retrieve manifest hashes, verify VM stopped; no automatic gate/training promotion.']}

    if carry5:
        result.update(supersedes_blocked_queue='20261015-solo-carry-870c0c59.json',
            carry5_profile='carry5_active_localization_v1', approved=False,
            dependency={'branch': 'claude/drive-model-deadband', 'required_toggle': 'drive_model_deadband_v1',
                        'integrated': True, 'commit': '01703ed2790dadad666e53d1b276b97f2b510bda',
                        'enabled_in_carry5': True, 'reason': 'merged shared implementation; physical effect unverified'},
            execution_stages=[{'name': 'first_one', 'indices': [0], 'enabled': False},
                              {'name': 'remaining_seven', 'indices': list(range(1,8)), 'enabled': False,
                               'requires': 'first run retrieval, first30 and video review plus explicit approval'}])
        for i, run in enumerate(result['runs']):
            run.update(ready=False, approved=False,
                       stage='first_one' if i == 0 else 'remaining_seven')
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--plan-out', type=Path)
    p.add_argument('--queue-out', type=Path)
    p.add_argument('--pr', type=int)
    p.add_argument('--carry5', action='store_true')
    a = p.parse_args()
    if a.plan_out:
        plan = prepare(carry5=a.carry5)
        a.plan_out.parent.mkdir(parents=True, exist_ok=True)
        with a.plan_out.open('x') as f:
            # Compact static corridor arrays keep the frozen plan below 64 KiB.
            json.dump(plan, f, separators=(',', ':')); f.write('\n')
    if a.queue_out:
        if not a.pr:
            p.error('--pr required for queue')
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        plan_path = 'experiments/2026-10-15-map-carry-zone/diagnostic-plan-v5.json' if a.carry5 else PLAN
        plan = json.loads((ROOT/plan_path).read_text())
        with a.queue_out.open('x') as f:
            json.dump(queue(plan, sha, a.pr, plan_path=plan_path), f, indent=2); f.write('\n')


if __name__ == '__main__':
    main()
