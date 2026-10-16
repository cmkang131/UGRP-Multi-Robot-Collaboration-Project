"""Host-side stopped-run receipt and actual learning curves; no model selection.

Run after all ACT16w leases have drained. Originals stay on GCP2; only the
small JSON/PNG delivery directory needs to be retrieved. No fabricated curve
is produced when training did not run.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from act16w_runtime import frozen_source, require_gcp2

B = Path('/home/ugrp/ugrp-sim')


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def receipt(path):
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    host = require_gcp2()
    source = frozen_source(ROOT)
    if not args.out.resolve().is_relative_to(B / 'runs'):
        raise ValueError('delivery stays inside GCP2 runs root')
    leases = sorted((B / 'leases').glob('act16w*.json'))
    if leases:
        raise ValueError('ACT16w has not drained: ' + ', '.join(p.name for p in leases))
    subprocess.run([sys.executable, str(Path(__file__).with_name('summarize_records.py'))],
                   check=True, capture_output=True, text=True)
    progress_path = B / 'runs/act16w-resume2-admission/progress-latest.json'
    progress = read(progress_path)
    if progress['counts'].get('running') or progress['counts'].get('pending'):
        raise ValueError('stopped-run receipt cannot finalize running/pending records')
    pointer = read(B / 'runs/act16w-active-training.json') or {}
    training = Path(pointer.get('root', str(B / 'runs/act16w-resume2-training')))
    arms, curves, hashes = {}, {}, [receipt(progress_path)]
    for arm in ('A', 'B', 'C', 'D1'):
        stages, points = {}, []
        for stage in ('smoke', 'main'):
            folder = training / f'{arm}-{stage}'
            summary_path = folder / 'summary.json'
            summary = read(summary_path)
            if summary is None:
                continue
            if summary['status'] == 'running':
                # A hard resource stop may leave an immutable stale summary.
                # Distinguish that from an orphan that is still training.
                launch = read(training / f'{stage}-{arm}-launch.json') or {}
                command = Path(f'/proc/{launch.get("pid", -1)}/cmdline')
                argv = command.read_bytes().decode().strip('\0').split('\0') if command.exists() else []
                if '--output' in argv and argv[argv.index('--output') + 1] == str(folder):
                    raise ValueError('owned training process still live: ' + str(summary_path))
                summary = dict(summary, status='HOST_ERROR_abrupt_end', raw_summary_status='running',
                               complete=False, readback_verified=False,
                               actual_step_count_exact=False)
            stages[stage] = summary
            hashes.append(receipt(summary_path))
            log = folder / 'progress.jsonl'
            if log.exists():
                points += [dict(stage=stage, **json.loads(line))
                           for line in log.read_text().splitlines() if line.strip()]
                hashes.append(receipt(log))
        if stages:
            latest = stages.get('main', stages.get('smoke'))
            # Main resumes smoke. A failed main can still report0 before its
            # first log; retain the already verified smoke steps as a bound.
            known_steps = max(value['steps_completed'] for value in stages.values())
            exact = (latest['status'] in ('complete', 'RESOURCE_CAP', 'SUPERVISOR_STOP')
                     and latest['readback_verified'] is True)
            arms[arm] = dict(steps=known_steps, actual_step_count_exact=exact,
                             status=latest['status'], complete=latest['complete'],
                             readback_verified=latest['readback_verified'],
                             last_checkpoint=latest.get('last_checkpoint'), stages=stages)
            curves[arm] = points
    for row in progress['rows']:
        raw = Path(row['raw'])
        for path in (raw / 'capture/summary.json', raw / 'controller/summary.json',
                     raw / 'controller/rejection_table.json', raw / 'launch.json',
                     raw / 'runner-args.json', raw / 'dataset-audit.json',
                     raw / 'strict-native-audit-r1.json',
                     raw / 'controller' / f'world-{row["world"]:03d}' / 'result.json'):
            actual = path if path.exists() else Path(str(path) + '.zst')
            if actual.exists() and str(actual) not in {h['path'] for h in hashes}:
                hashes.append(receipt(actual))
    args.out.mkdir(parents=True, exist_ok=False)

    def write(name, value):
        (args.out / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

    steps = sum(a['steps'] for a in arms.values())
    steps_exact = all(a['actual_step_count_exact'] for a in arms.values())
    write('learning-curves.json', dict(status='recorded' if any(curves.values()) else 'not_run' if steps_exact and not steps else 'no_logged_updates',
          optimizer_steps_by_arm={k: v['steps'] for k, v in arms.items()},
          points=curves, raw_log_receipts=[h for h in hashes if h['path'].endswith('progress.jsonl')],
          scope='actual logged optimization only; no synthetic probe or unrun points'))
    if any(curves.values()):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        figure, axes = plt.subplots(2, 2, figsize=(10, 7))
        for axis, key in zip(axes.flat, ('loss', 'movement_l1_loss', 'done_bce_loss', 'kld_loss')):
            for arm, points in curves.items():
                valid = [point for point in points if key in point]
                if valid:
                    axis.plot([point['step'] for point in valid],
                              [point[key] for point in valid], label=arm, linewidth=.8)
            axis.set(xlabel='Optimizer step', ylabel=key)
            axis.grid(alpha=.2)
            if axis.lines:
                axis.legend()
        figure.suptitle('ACT16w: actual training logs (no smoothing)')
        figure.tight_layout()
        figure.savefig(args.out / 'learning-curves.png', dpi=150)
        plt.close(figure)
    write('rejection_table.json', dict(funnel=progress['funnel'],
          rejections=progress['rejections'], rows=progress['rows'],
          upstream_event_funnels=[h for h in hashes if h['path'].endswith('/controller/rejection_table.json')],
          run_configuration_receipts=[h for h in hashes if h['path'].endswith(('/launch.json', '/runner-args.json'))],
          raw=progress['raw'], reproduce=progress['reproduce']))
    write('raw-receipts.json', dict(source_sha=source, files=hashes))
    # Keep finite warm/capped probes, pre-physics HOST_ERROR and synthetic
    # checks visible without adding them to the fresh40 teacher denominator.
    diagnostics = []
    for name in ('warm-receipts.json', 'sap-diagnostic.json',
                 'bulk-host-schema-host-error.json', 'cuda-preflight.json',
                 'oracle-interface-probe.json', 'native-policy-interface-probe.json',
                 'converter-canary.json', 'first30-own-rgb-preview-r1-rejected.json'):
        path = Path(__file__).with_name(name)
        diagnostics.append(dict(name=name, **receipt(path)) if path.exists()
                           else dict(name=name, status='unavailable', path=str(path)))
    write('diagnostic-receipts.json', dict(separate_from_fresh40=True,
          scope='original proof files retain failures/cap_end and raw paths; synthetic checks are not research training',
          records=diagnostics))
    first = datetime.fromisoformat('2026-10-16T05:47:00.019842+00:00')
    now = datetime.now(timezone.utc)
    conservative_hours = max(0, (now - first).total_seconds() / 3600)
    write('summary.json', dict(source_sha=source, host=host, observed_utc=now.isoformat(),
          status='stopped; subsequent study stages require verified evidence',
          requested_records=40, counts=progress['counts'],
          provisional_teacher_n=progress['provisional_success_n'],
          native_audited_teacher_n=progress['confirmed_native_success_n'],
          recording_gate_passed=progress['independent_recording_gate_passed'],
          training_arms=arms, total_actual_optimizer_steps=steps if steps_exact else None,
          verified_optimizer_steps_lower_bound=steps, actual_step_count_exact=steps_exact,
          separate_diagnostic_records='diagnostic-receipts.json',
          student_final_evaluation='see separately verified evaluation receipt; not inferred from training',
          budget=dict(task_first_gpu_utc=first.isoformat(), wall_cap=None,
                      conservative_shared_L4_window_h=conservative_hours,
                      configured_rate_USD_per_h=1.096,
                      configured_shared_window_estimate_USD=conservative_hours * 1.096,
                      scope='configured-rate upper window estimate, not current billing or additive task cost'),
          verification_scope='teacher recording, tensor/input audit and actual optimization are separate; model Release and student task success require their own evidence',
          foreign_leases=[p.name for p in sorted((B / 'leases').glob('*.json'))],
          vm_stop_attempted=False, original_data_preserved=True))
    write('delivery-sha256.json', {p.name: receipt(p) for p in sorted(args.out.iterdir()) if p.is_file()})
    print(json.dumps(dict(out=str(args.out), actual_optimizer_steps=steps if steps_exact else None,
                          verified_optimizer_steps_lower_bound=steps,
                          counts=progress['counts'], original_data_preserved=True)))


if __name__ == '__main__':
    main()
