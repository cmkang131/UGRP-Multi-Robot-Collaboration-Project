"""gcp2 CPU only: recount terminal warp8 raw results without simulator calls.

Thresholds below are the existing frozen teacher criteria, not new tuning:
26f84d0f/scripts/run_grasp_act_teacher.py:295-300 and
8e81b7d9/scripts/run_grasp_act_release.py:SUCCESS,good,evaluation_checks.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import subprocess

READ_ERRORS = []


def data(path, default=None):
    try:
        raw = path.read_bytes() if path.exists() else subprocess.check_output(
            ['zstd', '-qdc', str(path.with_name(path.name + '.zst'))], stderr=subprocess.DEVNULL)
        return json.loads(raw)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return default


def rows(path):
    def decode(stream):
        for i,line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as error:
                    READ_ERRORS.append(dict(path=str(path), line=i, error=str(error)))
    if path.exists():
        with path.open() as stream:
            yield from decode(stream)
    elif path.with_name(path.name + '.zst').exists():
        child = subprocess.Popen(['zstd', '-qdc', str(path) + '.zst'], stdout=subprocess.PIPE, text=True)
        try:
            yield from decode(child.stdout)
        finally:
            child.stdout.close()
            assert child.wait() == 0


def beam_recount(raw, root):
    since = None
    last_hold = maximum = 0.
    last = first = None
    n = 0
    max_gap = 0.
    errors_before = len(READ_ERRORS)
    for row in rows(root / 'eval-only.jsonl'):
        now = row['t']
        if first is None:
            first = now
        if last is not None:
            max_gap = max(max_gap, now - last)
        last = now
        good = (all(min(v) >= .5 for v in row['contacts'].values())
                and row['beam']['min_z'] >= .012 and row['beam']['tilt_deg'] <= 10.)
        since = (now if since is None else since) if good else None
        last_hold = 0. if since is None else now - since
        maximum = max(maximum, last_hold)
        n += 1
    teacher_n = sum(t.get('outcome') == 'success' for t in raw['teachers'].values())
    dense = n > 0 and max_gap <= .1 + 1e-8 and len(READ_ERRORS) == errors_before
    physical = teacher_n == raw['teacher_N'] and last_hold >= 3.
    return dict(success=physical if dense else None, dense_evaluator_rows=dense,
        evaluator_N=n, first_evaluator_t=first, last_evaluator_t=last,
        max_evaluator_gap_s=max_gap, terminal_hold_s=last_hold,
        max_hold_s=maximum, teacher_success_n=teacher_n,
        source_success=raw['physical_success'], agrees=dense and physical == raw['physical_success'])


def release_recount(raw):
    checks = raw.get('evaluation_checks', [])
    if raw.get('release_outcome') == 'prefix_not_held':
        return dict(success=None, prefix_failed=True, agrees=raw.get('release_success') is None)
    best = streak = 0
    prev = None
    for row in checks:
        speed = 0. if prev is None else math.dist(row['beam_xy_yaw'][:2], prev['beam_xy_yaw'][:2]) / .1
        good = (row['fit'] and row['z'] < .05 and row['tilt_deg'] < 3. and speed < .01
            and all(max(v) < 1e-6 for v in row['contact_n'].values())
            and all(v >= 1900 for v in row['open_pwm'].values()) and min(row['grip_to_beam_m']) >= .04)
        streak = streak + 1 if good else 0
        best = max(best, streak)
        prev = row
    success = best * .1 >= 2. - 1e-6 and raw.get('release_outcome') == 'teacher_done'
    return dict(success=success if checks else None, evaluator_N=len(checks),
        settled_s=best * .1, source_success=raw.get('release_success'),
        agrees=bool(checks) and success == raw.get('release_success'))


def reasons(value):
    if isinstance(value, dict):
        reason = value.get('reason_category') or value.get('reason')
        if isinstance(reason, str) and reason:
            yield (reason, str(value.get('blocked_object') or 'not_recorded'), value.get('min_gap_m'))
        for child in value.values():
            yield from reasons(child)
    elif isinstance(value, list):
        for child in value:
            yield from reasons(child)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    attempts = []
    for path in sorted(a.root.glob('*.command.json')):
        name = path.name.removesuffix('.command.json')
        run = a.root / name
        cmd, receipt, summary = data(path), data(run.with_suffix('.receipt.json')), data(run / 'summary.json', {})
        export = cmd.get('export_only', False)
        terminal = receipt is not None
        results = []
        histogram = Counter()
        minimums = {}
        completed_ids = {w['world'] for w in summary.get('worlds', [])}
        for folder in sorted(run.glob('world-*')):
            if not folder.is_dir():
                continue
            world = int(folder.name.split('-')[1])
            raw = data(folder / 'raw/result.json', {})
            if export or world not in completed_ids or raw.get('status') != 'complete':
                continue
            audit = raw.get('input_audit', {})
            check = beam_recount(raw, folder / 'raw') if summary['flow'] == 'beampair' else release_recount(raw)
            cap = bool(raw.get('cap_end') or raw.get('termination_category') == 'cap_end'
                       or raw.get('release_outcome') in ('cap_end', 'release_timeout'))
            candidates = list(reasons(raw.get('teachers', {})))
            for teacher in folder.glob('raw/teacher-*.jsonl*'):
                if teacher.name.endswith('.zst') and teacher.with_suffix('').exists():
                    continue
                for row in rows(teacher.with_suffix('') if teacher.suffix == '.zst' else teacher):
                    candidates.extend(reasons(row))
            for category, obj, gap in candidates:
                key = (category, obj)
                histogram[key] += 1
                if isinstance(gap, (float, int)) and math.isfinite(gap):
                    minimums[key] = min(minimums.get(key, math.inf), gap)
            results.append(dict(world=world, seed=cmd['case_seeds'][world], sim_s=raw['sim_s'],
                raw=str(folder / 'raw'), success=check['success'], cap_end=cap,
                recount=check, input_audit=dict(held_world_reads=audit.get('held_world_reads'),
                    invisible_measurements=audit.get('invisible_measurements'), scope=audit.get('scope')),
                audit_pass=audit.get('held_world_reads') == 0 and audit.get('invisible_measurements') == 0,
                weld=raw.get('weld', summary.get('weld')), outcome=raw.get('release_outcome') or
                    {r:t.get('outcome') for r,t in raw.get('teachers', {}).items()}))
        sim = sum(w['sim_s'] for w in results)
        first30 = data(run / 'first30-speed.json')
        progress = data(run / 'progress.json', {})
        batch_sim = progress.get('batch_sim_s', max(progress.get('world_sim_s', [0.])))
        if first30 and terminal and len(results) == cmd['planned_world_N']:
            first30 = dict(first30,
                admission_per_world_wall_SIM=first30['loop_wall_s'] / (first30['sim_s']*cmd['planned_world_N']),
                admission_speed_gate_fail=first30['loop_wall_s'] / (first30['sim_s']*cmd['planned_world_N']) > 6.,
                recorded_task_clock_scope='source auxiliary metric preserved; completed teacher episodes and active backend clocks can have different startup origins')
            if summary['flow'] == 'beampair':
                # Reporting only: actual R2 source evidence showed first eval
                # 2.2 vs backend origin1.7. Use each recorded origin, never a
                # new fixed startup constant or acceptance threshold.
                origins = summary['native_initialization_only_sim_s']
                episode_clocks = []
                for world in results:
                    recount = world['recount']
                    start, end = recount['first_evaluator_t'], recount['last_evaluator_t']
                    assert start is not None and end is not None
                    assert math.isclose(end-start, world['sim_s'], abs_tol=1e-8), 'teacher episode clock disagreement'
                    startup = start-origins[world['world']]
                    episode_clocks.append(min(world['sim_s'], max(0., first30['sim_s']-startup)))
                actual = sum(episode_clocks)
                first30.update(teacher_episode_aggregate_SIM=actual,
                    teacher_episode_wall_per_SIM=first30['loop_wall_s']/actual,
                    episode_clock_correction='first evaluator time minus recorded native origin per world; source auxiliary and admission metrics unchanged')
        table = [dict(reason_category=k[0], blocked_object=k[1], min_gap_m=minimums.get(k), count=v,
                      gap_scope='minimum of recorded finite gaps; null means absent/nongeometric')
                 for k,v in histogram.most_common()]
        n = cmd['planned_world_N']
        completed = len(results)
        success = sum(w['success'] is True for w in results)
        setup = summary.get('started_N', 0)
        setup_rejected = int(terminal and setup < n and bool(summary.get('error_type')))
        attempt = dict(name=name, host='gcp3', source_sha=cmd['source_sha'], export_only=export,
            status=('HOST_ERROR' if receipt and receipt['exit_code'] else summary.get('status', 'missing')),
            terminal=terminal, command=cmd['command'], raw=str(run), N=n, completed_N=completed,
            success_N=success, cap_end_N=sum(w['cap_end'] for w in results),
            HOST_ERROR_world_N=n-completed if receipt and receipt['exit_code'] and not export else 0,
            setup_wall_s=summary.get('setup_compile_s'), total_wall_s=summary.get('wall_s'),
            loop_wall_s=summary.get('loop_wall_s'), aggregate_task_sim_s=sim,
            per_world_wall_SIM=summary['loop_wall_s']/(batch_sim*n) if batch_sim and summary.get('loop_wall_s') else None,
            batch_sim_s=batch_sim,
            task_wall_per_SIM=summary['loop_wall_s']/sim if sim and summary.get('loop_wall_s') else None,
            first30=first30, worlds=results, reason_distribution=table,
            funnel=[dict(stage='requested', passed_cumulative_N=n, rejected_N=0),
                dict(stage='setup', passed_cumulative_N=setup, rejected_N=setup_rejected,
                     not_attempted_N=n-setup-setup_rejected if terminal else 0,
                     pending_N=n-setup if not terminal else 0),
                dict(stage='terminal_teacher_trial', passed_cumulative_N=completed,
                     rejected_N=setup-completed if terminal and not export else 0,
                     not_trial_N=setup if export else 0),
                dict(stage='physical_success', passed_cumulative_N=success, rejected_N=completed-success)])
        attempts.append(attempt)
    result = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), simulation_host='gcp3',
        analysis_host='gcp2_CPU', project='ugrp-sim-c-1016', CPU_results_pooled=False,
        attempts=attempts, rejection_table=str(a.out / 'rejection_table.json'),
        collector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        read_errors=READ_ERRORS,
        reason_distribution_scope='record occurrences in diagnostic and teacher trace; not unique candidate IDs',
        scope='terminal raw evaluator recount, not ACT/student success or host root-cause proof')
    (a.out / 'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    (a.out / 'rejection_table.json').write_text(json.dumps(dict(attempts=[
        {k:x[k] for k in ('name','raw','command','funnel','reason_distribution')} for x in attempts]),
        indent=2, allow_nan=False) + '\n')
    print(json.dumps([dict(name=x['name'], status=x['status'], completed=x['completed_N'], success=x['success_N'])
                      for x in attempts]))


if __name__ == '__main__':
    main()
