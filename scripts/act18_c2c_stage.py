"""C2c nine-run v7-clock evaluation driver (gcp2 only, default off).

Runs {B0,C2c} x {HO4,TRAIN4} x 3 repetitions in the preregistered cross order.
Each run has the two registered 2-world groups in parallel. No training, no
checkpoint writes, new run root only.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2, frozen_source, sha256
from act17_data import read

ROOT = Path(__file__).resolve().parents[1]
B = Path('/home/ugrp/ugrp-sim')
Q = B / 'src/f0db6b1abb842ea65b71c433738210254f300a7c'
STACK = {
    'physics_backend': 'mjwarp_batch_v1', 'contact_profile': 'warp_native_contact_v1',
    'noslip_iterations': 0, 'scene_profile': 'walls_floor_contrast_v5_indigo110_s80',
    'end_color_scene': 'grasp_act_teal_blue_v1', 'cargo_version': 'v6', 'scenario_version': 'v7',
    'heavy_crate': False, 'held_object_hidden_v1': True, 'held_world_reads': 0,
    'nearfield_executor': 'ACT', 'weld': False, 'top_camera_control': False, 'heading_mode': 'on',
    'ultrasonic_front': 'off', 'wall_cap': None, 'speed_gate': 'record_only',
    'speed_metric': 'wall_s/(sim_s*nworld)', 'gcp_host': 'ugrp-act-l4-gcp2',
    'gcp_project': 'ugrp-sim-b-1014', 'gcp_account': 'changmin5781@gmail.com',
    'gcp_guards': {'idle_minutes': 20, 'budget_stop': True, 'credentials_on_vm': False},
    'no_pooling': True, 'rejection_ledger': ['reason_category', 'blocked_object', 'minimum_gap_m'],
    'cap_end_label': 'cap_end', 'teacher_visibility': 'visible_only', 'invisible_measurements': 0,
    'setdown_lookaround_v1': True, 'planning_cap_basis': 'compute_or_sim', 'static_map_use': 'none',
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--prereg', type=Path, required=True)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--native-gate', type=Path, required=True)
    p.add_argument('--physics-python', type=Path, required=True)
    p.add_argument('--qualified-source', type=Path, required=True)
    p.add_argument('--teacher-source', type=Path, required=True)
    p.add_argument('--qualification', type=Path, required=True)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--record-references', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    a = p.parse_args()
    if not a.enabled:
        p.error('C2c stage is default OFF')
    host = require_gcp2(training=True); source = frozen_source(ROOT)
    prereg = read(a.prereg)
    if prereg.get('schema') != 'ugrp.act18.c2c_prereg.v1':
        raise ValueError('registered C2c prereg required')
    if prereg.get('r3', {}).get('retraining') != 'no-go':
        raise ValueError('C2c authorizes no R3 retraining')
    checkpoint_sha = sha256(a.checkpoint / 'model.safetensors')
    if checkpoint_sha != prereg['checkpoint']['model_sha256']:
        raise ValueError('preregistered R8 checkpoint hash required')
    plans = {row['seed']: row for row in read(a.record_references / 'plans.json')['episodes']}
    a.run_root.mkdir(parents=True, exist_ok=False)
    runs = []
    for name in prereg['cross_order']:
        arm, queue, rep = name.split('-')
        rep = int(rep.replace('rep', ''))
        stage = 'diag' if queue == 'ho4' else 'train'
        deadband = prereg['arms'][arm]['issued_clock_deadband']
        folder = a.run_root / name; folder.mkdir()
        stage_dir = folder / f'R8-{stage}'; stage_dir.mkdir()
        group_defs = (prereg['holdout']['groups'] if stage == 'diag'
                      else prereg['queues']['TRAIN4']['groups'])
        run_seeds = []
        commands = []
        for group in (0, 1):
            definition = group_defs[f'group-{group:03d}']
            seeds = definition['seeds'];run_seeds.extend(seeds)
            case = definition['compiled_reference_case']
            group_dir = stage_dir / f'group-{group:03d}'; group_dir.mkdir()
            plans_path = group_dir / 'plans.json'
            plans_path.write_text(json.dumps(dict(episodes=[plans[seed] for seed in seeds]), indent=2) + '\n')
            out = group_dir / 'evaluation'
            if out.exists():
                raise ValueError('new evaluation leaf required')
            cmd = [sys.executable, '-u', str(ROOT / 'scripts/act18_evaluate.py'),
                   '--act18-reference-v1', '--stage', stage, '--enabled', '--full-evaluation',
                   '--physics-python', str(a.physics_python), '--qualified-source', str(a.qualified_source),
                   '--teacher-source', str(a.teacher_source), '--qualification', str(a.qualification),
                   '--references', str(a.references),
                   '--compiled-reference', str(a.record_references / case / 'compiled-312.json'),
                   '--compiled-geometry', str(a.record_references / case / 'compiled-geometry312.npz'),
                   '--plans', str(plans_path), '--actor-source', str(B / 'src' / '3f99d58c5ada0862e669ef4065c0ba957f1b4547'),
                   '--checkpoint', str(a.checkpoint), '--out', str(out), '--protocol', str(a.protocol),
                   '--split', 'validation', '--issued-clock-deadband', str(deadband),
                   '--record-done-prob', str(stage_dir / f'done-prob-group-{group:03d}.jsonl')]
            if stage == 'diag':
                cmd += ['--diag-prereg', str(a.prereg)]
            commands.append(cmd)
        queue_path = folder / 'queue.json'
        queue_path.write_text(json.dumps(dict(flow='act_eval', source_sha=source, host=host, stage=stage,
            checkpoint_sha256=checkpoint_sha, candidate='R8', stack_values=STACK,
            rejection_table=str(folder / 'rejection_table.json'), requested_seeds=run_seeds,
            wall_cap=None, max_worlds=4, teacher_fallback=False, policy_privileged_inputs=0), indent=2) + '\n')
        subprocess.run([sys.executable, str(ROOT / 'scripts/check_current_stack.py'), str(queue_path),
                        '--flow', 'act_eval', '--output', str(folder / 'current-stack-check.json')], check=True)
        launch = dict(schema='ugrp.act18.c2c_launch.v1', run=name, arm=arm, queue=queue, rep=rep,
                      stage=stage, argv=commands, cwd=str(Q), host=host, source_sha=source, git_sha=source,
                      checkpoint_sha256=checkpoint_sha, checkpoint_path=str(a.checkpoint),
                      clock=dict(mode='deadband' if deadband else 'v6', deadband=deadband,
                                 flag=f'--issued-clock-deadband {deadband}'),
                      diag_prereg=(dict(path=str(a.prereg), sha256=sha256(a.prereg)) if stage == 'diag' else None),
                      env=dict(UGRP_ACT16W_NATIVE_GATE=str(a.native_gate), MUJOCO_GL='osmesa',
                               LP_NUM_THREADS='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                               PYTHONDONTWRITEBYTECODE='1'),
                      run_root=str(a.run_root), no_pooling=True, r3_retraining='no-go',
                      started_utc=datetime.now(timezone.utc).isoformat())
        (folder / 'launch.json').write_text(json.dumps(launch, indent=2) + '\n')
        started = time.monotonic(); processes = []
        for group, cmd in enumerate(commands):
            log = (stage_dir / f'group-{group:03d}' / 'run.log').open('x')
            env = {**os.environ, **launch['env']}
            processes.append((group, subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                                      cwd=str(Q), env=env), log))
        codes = []
        for group, process, log in processes:
            rc = process.wait(); log.close(); codes.append((group, rc))
        wall = time.monotonic() - started
        after = sha256(a.checkpoint / 'model.safetensors')
        if after != checkpoint_sha:
            raise ValueError('checkpoint changed during evaluation')
        status = 'DONE' if all(rc == 0 for _, rc in codes) else 'HOST_ERROR'
        row = dict(run=name, arm=arm, queue=queue, rep=rep, stage=stage, deadband=deadband,
                   status=status, group_exit=dict(codes), wall_s=round(wall, 1),
                   checkpoint_sha256_after=after, finished_utc=datetime.now(timezone.utc).isoformat())
        runs.append(row)
        (folder / 'run.json').write_text(json.dumps(row, indent=2) + '\n')
        print(json.dumps(row), flush=True)
        if status != 'DONE':
            raise RuntimeError(f'{name}: evaluation child HOST_ERROR {codes}')
    summary = dict(schema='ugrp.act18.c2c_runs.v1', source_sha=source, run_root=str(a.run_root),
                   prereg=dict(path=str(a.prereg), sha256=sha256(a.prereg)), host=host,
                   checkpoint_sha256_before=checkpoint_sha,
                   checkpoint_sha256_after=sha256(a.checkpoint / 'model.safetensors'),
                   runs=runs, no_pooling=True, r3_retraining='no-go')
    (a.run_root / 'runs.json').write_text(json.dumps(summary, indent=2) + '\n')
    subprocess.run([sys.executable, str(ROOT / 'scripts/act18_c2c_analyze.py'), '--enabled',
                    '--run-root', str(a.run_root), '--prereg', str(a.prereg)], check=True)


if __name__ == '__main__':
    main()
