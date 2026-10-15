"""Write a NEW, unapproved GCP selfmap5 queue; never connect or submit jobs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from scripts.run_self_map_diagnostic import bundle, storage_estimate
from harness.selfmap5_revision import OPTION as REVISION
from harness.selfmap5_registration import OPTION as MULTIFRAME

QUEUE = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
WORKTREE = '/Users/changmin/projects/ugrp-wt/map-selfmap'


def make_queue(source):
    if re.fullmatch('[0-9a-f]{40}', source) is None:
        raise ValueError('FULL_SOURCE_SHA_REQUIRED')
    runs = []
    for texture, profile in [('smooth', 'floor_light_v1'), ('textured', 'floor_light_textured_v1')]:
        previous = None
        for stage, seed, cap in [('first30', 93550, 30), ('diagnostic180_1', 93551, 180), ('diagnostic180_2', 93552, 180)]:
            name = f'selfmap5-{texture}-{seed}-{source[:8]}'
            raw = f'/home/ugrp/ugrp-sim/runs/{name}/raw'
            estimate = storage_estimate(cap); reserved = 192 if cap == 30 else 384
            b = bundle(source, seed, cap, bootstrap='command_prior_v1', initial_sweep='required_360_v1',
                recovery_profile='selfmap4_recovery_v1', revision_gate=REVISION,
                multiframe_registration=MULTIFRAME, render_profile=profile)
            command = ['python3', 'scripts/remote_run.py', '--host', 'gcp1', '--detach', '--class', 'dev',
                '--pr', '506', '--per-run-mb', str(reserved), WORKTREE, name, '--', '.venv-sim/bin/python',
                '-m', 'scripts.sim_cli', 'workflow', 'run', 'self-map-diagnostic', '--', '--output', raw,
                '--expected-source-sha', source, '--seed', str(seed), '--cap-s', str(cap),
                '--execution-host', 'gcp1', '--project', 'ugrp-act-train-1014',
                '--self-map-executor', 'frontier_drive_v1', '--bootstrap', 'command_prior_v1',
                '--initial-sweep', 'required_360_v1', '--recovery-profile', 'selfmap4_recovery_v1',
                '--revision-gate', REVISION, '--multiframe-registration', MULTIFRAME,
                '--render-profile', profile, '--execute']
            runs.append(dict(name=name, seed=seed, stage=stage, stage_ready=False, enabled=False,
                execute=False, approved=False, ready=False, source_sha=source,
                requires_coordinator_approval=True, depends_on=previous,
                dependency_pr=511 if texture=='textured' else None,
                dependency_satisfied=False if texture=='textured' else True,
                cap_sim_s=cap, max_wall_s=1800, raw=raw, bundle=b, command=command,
                storage_estimate=estimate, reserved_mib=reserved, scene_version=profile,
                pool_with_previous_results=False))
            previous=name
    return dict(schema='ugrp.coordinator_queue.v1', task='selfmap5-pr506-innovation-multiframe',
        created_at=datetime.now(timezone.utc).isoformat(), branch='claude/map-selfmap', pr=506,
        sha=source, source_sha=source, host='gcp1', machine_type='n4-highcpu-64', machine_type_live_verified=False,
        project='ugrp-act-train-1014', source_worktree=WORKTREE, runner_cwd='/Users/changmin/projects/ugrp',
        status='PREPARED_NOT_APPROVED', approved=False, enabled=False, ready=False, stage_ready=False,
        first30_ready=False, diagnostic_ready=False, cohort_ready=False, runs_enabled=False, execute=False,
        requires_coordinator_approval=True, coordinator_approval=dict(approved=False, source_sha=source),
        gate_promotion_authorized_if_all_conditions_pass=False, automatic_promotion=False, gate_eligible=False,
        physical_execution_authorized=False, rendering_authorized=False, training_authorized=False,
        model_calls_authorized=False, run_count=len(runs), max_parallel=1, runs=runs,
        stages=[dict(name=f'{p}-{s}', approved=False, enabled=False, ready=False, stage_ready=False)
                for p in ('smooth','textured') for s in ('first30','diagnostic180_1','diagnostic180_2')],
        storage_budget_mib=sum(r['reserved_mib'] for r in runs),
        seed_reservation=dict(seeds=[93550,93551,93552], paired_across_scene_versions=True,
            remote_history_checked=False, remote_check_required_before_submission=True),
        guards=dict(vm_max_run_duration='8h', instance_termination_action='STOP', idle_shutdown_minutes=20,
            budget_stop='must remain active; stop and notify; no automatic host failover'),
        coordinator_speed_policy=dict(mode='record_only', statistic='all stage runs, failures included',
            warning_median_above=3.5, block_median_above=6., block_on_incomplete=True,
            block_on_HOST_ERROR=True, passed=False, ready=False),
        dependencies=[dict(pr=511, branch='claude/scene-floor-texture',
            source_sha='6a73c3aab305f250d0ecd9591922b160b9c709ab', satisfied=False,
            requirement='integrate PR511 profile/assets/nearclip API, pin NEW source SHA, regenerate queue before textured submission')],
        record='experiments/2026-10-15-self-map/selfmap5.md',
        recording=dict(own_rgb_hz=10, resolution=[640,480], top_rgb=False,
            retain='all saved own JPEGs, ledger hashes and all failures'),
        preconditions=[
            'This file submits no jobs. Every stage requires explicit approval of the exact pushed source SHA.',
            'Serial per-scene first30 -> manual raw review -> two 180s runs, each reviewed before the next. No automatic promotion.',
            'Texture dependency #511 is OPEN and absent from this source; do not execute textured commands until integrated, repinned and reapproved.',
            'Scene versions, previous selfmap results, machine types and seeds are not pooled.',
            'Check local/remote seed collisions, machine speed, budget-stop, 8h/20min guards, endpoint alerts and disk with --project ugrp-act-train-1014.',
            'First30: verify all RGB hashes/cadence, >=6 frames evenly across time, own RGB/commands/static map only, no peer/top/truth inputs.',
            'Record features/matches/inliers, visual ratio, map_updated, innovation/P+R, rebuild frame IDs/commits, sweep duration, independent axes, raw/calibrated PF covariance and augmented injection.',
            'Record 3 distinct confirming views, anchor consistency, frontier select/arrive, zero-progress intervals and wall/SIM.',
            'Known physical/control defect: stop the owned affected run, preserve raw and fix source before another submission.',
            'S1 recovery allows two bounded sweeps in 80 SIM s; rebuild cooldown is a separate 5 SIM s. Failure is HOST_ERROR, never completion.',
            'Stop and notify if GCP budget guard activates; do not move to another host automatically.',
            'Full ray reraster and S2 full sweep validation are unavailable locally (6/432 saved RGB). PF bias cause and effects remain unverified.'
        ], offline_verdict='OFFLINE_POLICY_VERIFIED_LIVE_EFFECT_UNVERIFIED', pool_with_previous_results=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();q=make_queue(a.source_sha)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:json.dump(q,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    print(json.dumps(dict(path=str(a.output),sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),runs=len(q['runs']),approved=False)))


if __name__=='__main__':
    main()
