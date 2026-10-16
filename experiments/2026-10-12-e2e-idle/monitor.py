#!/usr/bin/env python3
"""Read-only E2E monitor; stdout is one JSON object. No controller imports.

Health: run/log.txt, emitted by scripts/run_e2e_ownmap_live.py:health/run.
Actual robot positions: raw/progress.jsonl[.zst], emitted by
sim/s3_setdown.py:PhysicsBackend.progress (robots.r1/r2.base_xyz_m).
These referee positions are report-only and never fed to a controller.
Command distribution samples health rows, not every issued command.
"""
import argparse
from collections import Counter, deque
from contextlib import contextmanager
import datetime
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

WINDOW = 120.0
LINE_LIMIT = 2 * 1024 * 1024
SMALL_LIMIT = 4 * 1024 * 1024
HEALTH_FIELDS = ('sim_s', 'wall_s', 'phase', 'frames', 'first_model_response',
                 'own_map_B_generated', 'own_B_boundary_remembered',
                 'own_route_generated', 'model_attempts', 'setdowns')
RESULT_FIELDS = ('status', 'source_sha', 'seed', 'LLM_operated',
                 'own_map_completed', 'start_to_finish_transport', 'E2E_success',
                 'model_calls', 'frames', 'wall_s', 'sim_s',
                 'finalization_complete', 'shutdown_signals', 'failure_type')


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def point(value, size=2):
    return isinstance(value, list) and len(value) >= size and all(finite(x) for x in value[:size])


def code(value):
    """Never echo arbitrary exception text, URLs, request bodies or credentials."""
    if not isinstance(value, str):
        return None
    return value if re.fullmatch(r'[A-Z][A-Z0-9_:.-]{0,100}', value) else 'details_retained_in_raw'


def selected(value, fields):
    return {k: value[k] for k in fields if k in value}


def existing(path):
    return path if path.is_file() else path.with_name(path.name + '.zst')


@contextmanager
def stream(path):
    path = existing(path)
    process = None
    if path.suffix == '.zst':
        process = subprocess.Popen(['zstd', '-qdc', '--', str(path)],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        handle = process.stdout
    else:
        handle = path.open('rb')
    try:
        yield handle
    finally:
        handle.close()
        if process is not None:
            if process.poll() is None:
                process.terminate()
            process.wait()


def lines(path, stats):
    """Bound memory even for malformed/oversized lines; ignore a partial tail."""
    path = existing(path)
    if not path.is_file():
        return
    size = path.stat().st_size if path.suffix != '.zst' else None
    consumed = 0
    with stream(path) as handle:
        while size is None or consumed < size:
            limit = LINE_LIMIT if size is None else min(LINE_LIMIT, size - consumed)
            line = handle.readline(limit)
            if not line:
                break
            consumed += len(line)
            if not line.endswith(b'\n'):
                if len(line) == LINE_LIMIT:
                    stats['oversized_lines'] = stats.get('oversized_lines', 0) + 1
                    while line and not line.endswith(b'\n'):
                        line = handle.readline(LINE_LIMIT)
                        consumed += len(line)
                    continue
                stats['incomplete_tail_ignored'] = True
                break
            yield line
    stats['complete_prefix_bytes_read'] = consumed


def small(path, warnings):
    path = existing(path)
    if not path.is_file():
        return {}
    try:
        with stream(path) as handle:
            data = handle.read(SMALL_LIMIT + 1)
        if len(data) > SMALL_LIMIT:
            warnings.append('small_record_size_limit:' + path.name)
            return {}
        result = json.loads(data)
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        warnings.append('record_unreadable:' + path.name)
        return {}


def raw_directory(run):
    if (run / 'raw').is_dir():
        return run / 'raw'
    candidates = sorted(run.glob('*/raw'))
    return candidates[0] if len(candidates) == 1 else run / 'raw'


def command_kind(command):
    if not isinstance(command, dict) or command.get('kind') != 'mecanum':
        return 'hold' if isinstance(command, dict) and command.get('kind') == 'hold' else 'other'
    if command.get('forward', 0) or command.get('left', 0):
        return 'forward' if command.get('forward', 0) > 0 else 'translation_other'
    return 'turn' if command.get('turn', 0) else 'hold'


def process_alive(run, warnings):
    record = small(run / 'PROCESS.json', warnings)
    pid = record.get('pid')
    if not isinstance(pid, int) or not Path('/proc').is_dir():
        return None
    try:
        if record.get('boot_id') and record['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
            return False
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] != 'Z' and (record.get('start') is None or str(record['start']) == fields[19])
    except (OSError, ValueError):
        return False


def ground_truth(raw, warnings, initial_cutoff_sim_s=None):
    path = raw / 'progress.jsonl'
    recent, stationary = {}, {}
    result = dict(source=str(existing(path)), schema='sim.s3_setdown.PhysicsBackend.progress',
                  evaluation_only=True, feedback_to_controller=False, rows=0, robots={})
    for line in lines(path, result):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not finite(row.get('t')):
            continue
        result['rows'] += 1
        result.setdefault('first_backend_time_s', row['t'])
        result['last_backend_time_s'] = row['t']
        result.setdefault('first_frame_count', row.get('frame_count'))
        result['last_frame_count'] = row.get('frame_count')
        for rid in ('r1', 'r2'):
            pose = (row.get('robots', {}).get(rid) or {}).get('base_xyz_m')
            if not point(pose, 3):
                continue
            stats = result['robots'].setdefault(rid, dict(first_base_xyz_m=pose,
                         last_base_xyz_m=pose, max_xy_displacement_from_start_m=0.,
                         initial_window_max_xy_displacement_m=0., xy_path_length_m=0., samples=0))
            stats['xy_path_length_m'] += math.dist(stats['last_base_xyz_m'][:2], pose[:2])
            stats['last_base_xyz_m'] = pose
            stats['max_xy_displacement_from_start_m'] = max(stats['max_xy_displacement_from_start_m'],
                                                    math.dist(stats['first_base_xyz_m'][:2], pose[:2]))
            stats['net_xy_displacement_m'] = math.dist(stats['first_base_xyz_m'][:2], pose[:2])
            # Translation only: body yaw is deliberately absent from this
            # referee diagnostic, so spinning against a wall cannot reset it.
            anchor = stationary.setdefault(rid, dict(xy=pose[:2], since=row['t']))
            if math.dist(anchor['xy'], pose[:2]) > .01:
                anchor.update(xy=pose[:2], since=row['t'])
            stats['xy_stationary_sim_s'] = row['t'] - anchor['since']
            stats['xy_stationary_tolerance_m'] = .01
            window = recent.setdefault(rid, deque())
            window.append((row['t'], pose[:2]))
            while len(window) > 2 and window[1][0] <= row['t'] - WINDOW:
                window.popleft()
            if len(window) > 4096:
                window.popleft()
                warnings.append('GT_window_truncated:' + rid)
            if initial_cutoff_sim_s is not None and row['t'] - result['first_backend_time_s'] <= initial_cutoff_sim_s:
                stats['initial_window_max_xy_displacement_m'] = max(stats['initial_window_max_xy_displacement_m'],
                                                    stats['net_xy_displacement_m'])
            stats['samples'] += 1
    for rid, window in recent.items():
        first_t, first_xy = window[0]
        last_t, last_xy = window[-1]
        previous = first_xy
        path_m = maximum = 0.
        for _, xy in window:
            path_m += math.dist(previous, xy)
            maximum = max(maximum, math.dist(first_xy, xy))
            previous = xy
        result['robots'][rid]['recent_120_sim_s'] = dict(
            start_backend_time_s=first_t, end_backend_time_s=last_t,
            observed_span_sim_s=last_t-first_t, window_complete=last_t-first_t >= WINDOW,
            samples=len(window), xy_path_length_m=path_m,
            net_xy_displacement_m=math.dist(first_xy, last_xy),
            max_xy_displacement_from_window_start_m=maximum)
    result['available'] = bool(result['robots'])
    return result


def monitor(run):
    warnings, alerts = [], []
    raw = raw_directory(run)
    recent, poses, totals = deque(), {}, {'r1': Counter(), 'r2': Counter()}
    stats = dict(rows=0, malformed_json_lines=0, tracebacks=0)
    first = last = initial_last = None
    initial_mapping_seen = False
    first_response_wall = first_forward_wall = None
    signalled_log = False
    for line in lines(run / 'log.txt', stats):
        if line.startswith(b'Traceback (most recent call last):'):
            stats['tracebacks'] += 1
        if b'KeyboardInterrupt: SIGNAL_SIGINT' in line or b'KeyboardInterrupt: SIGNAL_SIGTERM' in line:
            signalled_log = True
        if not line.startswith(b'{'):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            stats['malformed_json_lines'] += 1
            continue
        if not isinstance(row, dict) or not finite(row.get('sim_s')) or not isinstance(row.get('robots'), dict):
            continue
        if last and row['sim_s'] < last['sim_s']:
            alerts.append('SIM_TIME_REGRESSION')
            continue
        stats['rows'] += 1
        if first is None:
            first = row
        last = row
        if finite(row.get('wall_s')) and row['wall_s'] <= 300:
            initial_last = row
            initial_mapping_seen |= row.get('phase') == 'mapping'
        recent.append(row)
        while len(recent) > 2 and recent[1]['sim_s'] <= row['sim_s'] - WINDOW:
            recent.popleft()
        if len(recent) > 4096:
            recent.popleft()
            warnings.append('health_window_truncated')
        if row.get('first_model_response') and first_response_wall is None:
            first_response_wall = row.get('wall_s')
        for rid in ('r1', 'r2'):
            robot = row['robots'].get(rid) or {}
            kind = command_kind(robot.get('command'))
            totals[rid][kind] += 1
            if kind == 'forward' and first_forward_wall is None:
                first_forward_wall = row.get('wall_s')
            pose = robot.get('pose_own_m')
            if point(pose, 3):
                p = poses.setdefault(rid, dict(anchor=pose, since=row['sim_s']))
                yaw = abs((pose[2] - p['anchor'][2] + math.pi) % (2 * math.pi) - math.pi)
                if math.dist(pose[:2], p['anchor'][:2]) > .01 or yaw > math.radians(1):
                    p.update(anchor=pose, since=row['sim_s'])
    result = small(raw / 'result.json', warnings)
    initial = small(raw / 'initial-check.json', warnings)
    milestones = small(raw / 'stage-milestones.json', warnings)
    meta = small(run / 'RUN_META.json', warnings)
    alive = process_alive(run, warnings)
    exit_code = None
    if (run / 'EXIT').is_file():
        try:
            exit_code = int((run / 'EXIT').read_text()[:20].strip())
        except (OSError, ValueError):
            warnings.append('EXIT_unreadable')
    normal_signal = result.get('failure_type') == 'KeyboardInterrupt' and result.get('failure') in ('SIGNAL_SIGINT', 'SIGNAL_SIGTERM')
    normal_signal = normal_signal or signalled_log
    # The Finalizer creates an initial HOST_ERROR placeholder before any work.
    finalizing = result.get('finalization_complete') is False and 'wall_s' in result
    finished = exit_code is not None
    real_error = bool(result.get('finalization_errors')) or bool(result.get('failure_type') and not normal_signal)
    real_error |= bool(stats['tracebacks'] and not normal_signal)
    real_error |= exit_code not in (None, 0) and not (normal_signal and exit_code in (130, 143, -2, -15))
    if alive is False and not finished and not finalizing and not result.get('finalization_complete'):
        real_error = True
        alerts.append('PROCESS_EXIT_WITHOUT_FINAL_RESULT')
    outcome = 'error' if real_error else 'finished' if finished else 'finalizing' if finalizing or result.get('finalization_complete') else 'live'
    if real_error:
        alerts.append('EXECUTION_EXCEPTION_OR_NONZERO_EXIT')
    gt = ground_truth(raw, warnings, initial_last['sim_s'] if initial_last else None)
    now = time.time()
    elapsed = now - meta['submitted_unix'] if finite(meta.get('submitted_unix')) else (last or {}).get('wall_s')
    health = selected(last or {}, HEALTH_FIELDS)
    robots = {}
    for rid in ('r1', 'r2'):
        robot = ((last or {}).get('robots') or {}).get(rid) or {}
        earlier = ((recent[0] if recent else {}).get('robots') or {}).get(rid) or {}
        start = recent[0]['sim_s'] if recent else None
        span = last['sim_s'] - start if last is not None else 0.
        cur, old = robot.get('translation_commands'), earlier.get('translation_commands')
        delta = cur - old if finite(cur) and finite(old) else None
        distribution = Counter(command_kind((r['robots'].get(rid) or {}).get('command')) for r in recent if last['sim_s'] - WINDOW <= r['sim_s'])
        p = poses.get(rid)
        idle = last['sim_s'] - p['since'] if p and last else None
        robots[rid] = dict(stage=robot.get('stage'), own_estimated_pose_m=robot.get('pose_own_m'),
            own_pose_stationary_sim_s=idle, own_pose_tolerance_m=.01, own_yaw_tolerance_deg=1.,
            translation_commands=cur, translation_delta_last_120_sim_s=delta,
            window_observed_sim_s=span, window_complete=span >= WINDOW,
            health_command_samples_last_120_sim_s=dict(distribution),
            health_command_samples_all=dict(totals[rid]), map_frames=robot.get('map_frames'))
        if span >= WINDOW and delta == 0:
            alerts.append(rid + ':NO_TRANSLATION_120_SIM_S')
        if idle is not None and idle >= WINDOW:
            alerts.append(rid + ':OWN_ESTIMATE_STATIONARY_120_SIM_S')
        if span >= WINDOW and len(distribution) == 1 and (next(iter(distribution)) in ('hold', 'turn') or (idle is not None and idle >= WINDOW)):
            alerts.append(rid + ':SAME_COMMAND_KIND_120_SIM_S:' + next(iter(distribution)))
        if span >= 10 and finite(robot.get('map_frames')) and robot['map_frames'] == earlier.get('map_frames'):
            alerts.append(rid + ':SENSOR_MAP_FRAMES_NOT_INCREASING')
        actual = gt['robots'].get(rid, {})
        if actual.get('xy_stationary_sim_s', 0) >= WINDOW:
            alerts.append(rid + ':ACTUAL_XY_STATIONARY_120_SIM_S')
            if delta is not None and delta > 0 and distribution.get('forward', 0) > 0:
                alerts.append(rid + ':FORWARD_COMMANDS_WITH_ACTUAL_XY_STATIONARY_120_SIM_S')
    frames_growing = bool(first and initial_last and finite(first.get('frames')) and finite(initial_last.get('frames')) and initial_last['frames'] > first['frames'] and initial_last['sim_s'] > first['sim_s'])
    gt_moved = gt['available'] and all(gt['robots'].get(r, {}).get('initial_window_max_xy_displacement_m', 0) > .01 for r in ('r1', 'r2'))
    initial_checks = dict(first_model_response=bool((initial_last or {}).get('first_model_response')),
        forward_command=finite(first_forward_wall) and first_forward_wall <= 300, frames_and_sim_increasing=frames_growing,
        actual_r1_r2_moved_over_1cm=gt_moved, mapping_entered=initial_mapping_seen,
        no_execution_exception=not real_error)
    if finite(elapsed) and elapsed >= 300 and not all(initial_checks.values()):
        alerts.extend('INITIAL_5MIN:' + k for k, passed in initial_checks.items() if not passed)
    if last and finite(elapsed) and finite(last.get('wall_s')) and elapsed - last['wall_s'] > 180 and outcome == 'live':
        alerts.append('HEALTH_LOG_STALE_WALL_180S')
    if not last and finite(elapsed) and elapsed > 300:
        alerts.append('NO_HEALTH_ROWS_AFTER_5MIN')
    if last and last['sim_s'] >= WINDOW and not last.get('own_B_boundary_remembered'):
        alerts.append('B_BOUNDARY_NOT_YET_CONFIRMED_AFTER_120_SIM_S')
    if last and last.get('own_B_boundary_remembered') and not last.get('own_route_generated'):
        alerts.append('B_BOUNDARY_PRESENT_ROUTE_PENDING')
    return dict(run=run.name,run_dir=str(run),raw_dir=str(raw),outcome=outcome,exit_code=exit_code,
        supervisor_alive=alive,normal_SIGINT_or_SIGTERM=normal_signal,elapsed_since_submit_wall_s=elapsed,
        health=health,robots=robots,evaluation_only_actual_motion=gt,
        initial_5min=dict(deadline_wall_s=300,checks=initial_checks,passed=all(initial_checks.values()),
            first_model_response_logged_wall_s=first_response_wall,first_forward_logged_wall_s=first_forward_wall,
            last_health_wall_s_in_window=(initial_last or {}).get('wall_s'),
            assessment='recorded_first_300_wall_seconds'),
        initial_check=selected(initial,HEALTH_FIELDS + ('passed','would_stop','stop')),
        stage_milestones={k:selected(v,('sim_s','wall_s')) for k,v in milestones.items() if isinstance(v,dict)},
        result={**selected(result,RESULT_FIELDS),'failure_code':code(result.get('failure')),
            'finalization_error_count':len(result.get('finalization_errors') or [])},
        latest_route_wait_code=code((last or {}).get('latest_route_wait')),
        log_statistics=stats,alerts=sorted(set(alerts)),warnings=sorted(set(warnings)),
        feedback_to_controller=False,read_only=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dirs', nargs='+', type=Path)
    args = parser.parse_args()
    results = []
    for run in args.run_dirs:
        try:
            results.append(monitor(run))
        except Exception as exc:
            results.append(dict(run=run.name,outcome='error',alerts=['MONITOR_READ_ERROR'],
                                error_type=type(exc).__name__,read_only=True,feedback_to_controller=False))
    print(json.dumps(dict(schema='ugrp.e2e-monitor.v1',captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                          runs=results),ensure_ascii=False,allow_nan=False))


if __name__ == '__main__':
    main()
