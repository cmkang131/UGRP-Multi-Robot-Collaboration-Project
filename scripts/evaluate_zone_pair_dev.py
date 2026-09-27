#!/usr/bin/env python3
"""Offline, fail-closed physical scoring. Never imported by a robot controller.

All derived truth, including result.json, remains in eval_only/. The run's
outer result only points here so GT is not copied into controller inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.run_zone_pair_dev import EXPECTED, LABELS, sha_file, write_json

PAIR = ('r1', 'r2')
MOTION = {'drive', 'mecanum', 'arm', 'look'}


def sustained(rows, predicate, duration, max_gap):
    start = prev = None
    for row in rows:
        t = row['t']
        if not predicate(row):
            start = prev = None
            continue
        if start is None or prev is None or t - prev > max_gap:
            start = t
        prev = t
        if t - start >= duration - 1e-8:
            return t
    return None


def audit_protocol(status, commands, shutdown, required_go=(), *, require_abort=False, post_s=.5):
    malformed = any(m.get('robot_id') not in PAIR or type(m.get('sent_at_s')) not in (float, int)
                    or not math.isfinite(m['sent_at_s']) for m in status)
    first = {}
    for m in status:
        if '_go_' in m['state']:
            first.setdefault((m['task_id'], m['state']), {}).setdefault(m['robot_id'], m['sent_at_s'])
    go_errors = []
    for (task, state), times in first.items():
        if set(times) != set(PAIR) or max(times.values()) - min(times.values()) > 1e-8:
            go_errors.append({'task_id': task, 'state': state, 'times': times})
    missing = sorted(set(required_go) - {s for _, s in first})
    # Only a single task with paired, simultaneous consumption can authorize a
    # planned set-down interval. Keep these command times separate from GT.
    go_times = {state: times['r1'] for (_, state), times in first.items()
                if set(times) == set(PAIR) and max(times.values()) - min(times.values()) <= 1e-8}
    if malformed or len({task for task, _ in first}) != 1:
        go_times = {}
    abort_times = [m['sent_at_s'] for m in status if m['state'] == 'abort']
    aborted = bool(abort_times)
    invalid_commands = any(type(c.get('after_abort')) is not bool for c in commands)
    after = [c for c in commands if c['kind'] in MOTION and
             (c.get('after_abort') or (aborted and c['t'] > min(abort_times) + 1e-8))]
    abort_rows = [r for r in shutdown if r.get('aborted')]
    queue_fields = ('arm', 'carry', 'port_buffer', 'macro', 'servo_targets', 'motor_nonzero')
    queues_empty = bool(abort_rows) and all(
        set(r['queues']) == set(PAIR) and all(
            all(q.get(k) == 0 for k in queue_fields) and q.get('capture_after') is False
            for q in r['queues'].values()) for r in abort_rows)
    post_observed = bool(abort_rows) and abort_rows[-1]['t'] - abort_rows[0]['t'] >= post_s - 1e-8
    abort_ok = (queues_empty and post_observed and not after) if aborted else not require_abort
    return {'ok': not go_errors and not missing and abort_ok and not invalid_commands and not malformed,
            'go_seen': bool(first), 'go_pairs': len(first), 'go_errors': go_errors, 'missing_go': missing,
            'go_times': go_times,
            'abort_seen': aborted, 'abort_check': 'checked' if aborted else 'not_exercised',
            'abort_queues_empty': queues_empty if aborted else None,
            'post_abort_observation_complete': post_observed if aborted else None,
            'post_abort_motion_count': len(after), 'command_order_metadata_complete': not invalid_commands}


def planned_setdown(row, prereg, protocol):
    """Evaluation-only exemption for an authorized, stationary route checkpoint.

    A state name alone is insufficient: both robots must be in the matching
    segment, within the paired lower-GO -> next carry-GO window and near its
    preregistered static target. Tilt, penetration and forbidden contacts are
    never exempt. The last target is destination placement, not a regrasp.
    """
    c, go = prereg['criteria'], protocol.get('go_times', {})
    targets = prereg['planned_setdown']['route_endpoints_m']
    for i, target in enumerate(targets):
        final = i == len(targets) - 1
        start, end = go.get(f'lower_go_{i}'), go.get(f'carry_go_{i + 1}')
        if start is None or row['t'] < start or (not final and (end is None or row['t'] >= end)):
            continue
        same_segment = {'lower', 'wait_open', 'released', 'done'} if final else {'lower', 'wait_open', 'cp_open'}
        regrasp = {'pregrasp_look', 'grasp', 'wait_lift', 'lift', 'wait_carry'}
        if not all((row['segments'][r] == i and row['states'][r] in same_segment) or
                   (not final and row['segments'][r] == i + 1 and row['states'][r] in regrasp) for r in PAIR):
            continue
        if (math.dist(row['beam_xyz'][:2], target) <= c['planned_setdown_xy_m']
                and row['tilt_deg'] <= c['max_transport_tilt_deg']
                and min(p[2] for p in row['beam_corners']) >= -c['floor_penetration_tolerance_m']):
            return i
    return None


def score(manifest, prereg, rows, contacts, protocol, *, video_review=None):
    """Pure evaluator; missing/NaN/partial evidence cannot become success."""
    c = prereg['criteria']
    checks = {k: False for k in ('applied', 'trace_complete', 'contacts_complete', 'approach', 'joint_grasp', 'lift',
                                'door', 'placement_release', 'no_drop', 'contacts', 'r3', 'weld_off',
                                'protocol', 'video')}
    checks['applied'] = manifest.get('applied') == EXPECTED
    checks['protocol'] = protocol.get('ok') is True and protocol.get('go_seen') is True
    evidence = {}
    errors = []
    try:
        if not rows:
            raise ValueError('missing evaluation trace')
        # JSON recursion rejects nonfinite values even when they are outside selected stages.
        json.dumps([rows, contacts], allow_nan=False)
        times = [r['t'] for r in rows]
        start, end = manifest['simulator_start_s'], manifest['sim_end_s']
        dt, eps = manifest['applied']['timestep_s'], c['coverage_time_tolerance_s']
        if not all(type(v) in (int, float) and math.isfinite(v) for v in (start, end, dt)) or dt <= 0 or end <= start:
            raise ValueError('invalid observation time range/timestep')
        expected_steps = round((end - start) / dt)
        on_grid = lambda t: abs(t - start - round((t - start) / dt) * dt) <= eps
        checks['trace_complete'] = (len(times) > 1 and on_grid(end) and all(on_grid(t) for t in times)
                                    and all(0 < b - a <= c['max_sample_gap_s'] for a, b in zip(times, times[1:]))
                                    and abs(times[0] - start) <= eps and abs(times[-1] - end) <= eps)
        checks['contacts_complete'] = (on_grid(end) and type(contacts['physics_steps']) is int
                                       and contacts['physics_steps'] == expected_steps and expected_steps > 0
                                       and abs(contacts['observation_start_s'] - start) <= eps
                                       and abs(contacts['observation_end_s'] - end) <= eps
                                       and abs(contacts['timestep_s'] - dt) <= eps
                                       and abs(contacts['max_step_gap_s'] - dt) <= eps
                                       and contacts['invalid_step_intervals'] == 0)
        evidence['coverage'] = {'start_s': start, 'end_s': end, 'timestep_s': dt, 'expected_physics_steps': expected_steps,
                                'observed_physics_steps': contacts['physics_steps']}
        for r in rows:
            if (len(r['beam_corners']) != 8 or set(r['robots']) != {'r1', 'r2', 'r3'} or set(r['finger_n']) != set(PAIR)
                    or set(r['segments']) != set(PAIR)):
                raise ValueError('incomplete geometry or fingers')
        setdowns = [planned_setdown(r, prereg, protocol) for r in rows]
        evidence['planned_setdowns'] = [
            {'segment': i, 'kind': 'destination' if i == len(prereg['planned_setdown']['route_endpoints_m']) - 1 else 'checkpoint',
             'first_observed_s': min(r['t'] for r, s in zip(rows, setdowns) if s == i),
             'last_observed_s': max(r['t'] for r, s in zip(rows, setdowns) if s == i),
             'samples': setdowns.count(i)} for i in sorted({s for s in setdowns if s is not None})]
        # GT approach position at each locally consumed approach GO, not the controller's arrival claim alone.
        approach = {}
        for rid in PAIR:
            candidates = [r for r in rows if r['approach_go_s'][rid] is not None
                          and 0 <= r['t'] - r['approach_go_s'][rid] <= c['max_sample_gap_s']]
            if candidates:
                r = candidates[0]
                target, actual = r['prestations'][rid], r['robots'][rid]
                yaw = abs((actual[2] - target[2] + math.pi) % (2 * math.pi) - math.pi)
                approach[rid] = math.dist(actual[:2], target[:2]) <= c['approach_xy_m'] and yaw <= math.radians(c['approach_yaw_deg'])
        checks['approach'] = set(approach) == set(PAIR) and all(approach.values())
        grip = lambda r: all(len(r['finger_n'][rid]) == 2 and min(r['finger_n'][rid]) >= c['grasp_finger_n'] for rid in PAIR)
        bottom = lambda r: min(p[2] for p in r['beam_corners'])
        grasp_at = sustained(rows, grip, c['grasp_dwell_s'], c['max_sample_gap_s'])
        lifted_at = sustained(rows, lambda r: grip(r) and bottom(r) >= c['lift_bottom_m'], c['lift_dwell_s'], c['max_sample_gap_s'])
        checks['joint_grasp'], checks['lift'] = grasp_at is not None, lifted_at is not None
        go_times = [r['approach_go_s'][rid] for r in rows for rid in PAIR if r['approach_go_s'][rid] is not None]
        if not go_times or grasp_at is None or grasp_at < max(go_times):
            checks['joint_grasp'] = False
        west_seen = False
        crossing = []
        door_at = None
        clear_since = None
        for r, setdown in zip(rows, setdowns):
            xs = [p[0] for p in r['beam_corners']]
            ys = [p[1] for p in r['beam_corners']]
            if max(xs) < c['door_west_x_m']:
                west_seen = True
            if min(xs) <= c['door_east_x_m'] and max(xs) >= c['door_west_x_m']:
                crossing.append(min(ys) >= c['door_y_min_m'] and max(ys) <= c['door_y_max_m']
                                and (setdown is not None or (bottom(r) >= c['lift_bottom_m'] and grip(r))))
            carrying_clear = (west_seen and crossing and all(crossing) and min(xs) > c['door_east_x_m']
                              and lifted_at is not None and r['t'] > lifted_at and grip(r)
                              and bottom(r) >= c['lift_bottom_m'] and all(r['states'][rid] == 'carry' for rid in PAIR))
            if carrying_clear:
                if clear_since is None:
                    clear_since = r['t']
                if r['t'] - clear_since >= c['door_clear_dwell_s'] - 1e-8:
                    door_at = r['t']
                    break
            else:
                clear_since = None
        checks['door'] = door_at is not None
        cx, cy = c['destination_center_m']
        hx, hy = c['destination_half_extents_m']
        tol = c['footprint_tolerance_m']
        def placed(r):
            return (door_at is not None and r['t'] > door_at and all(r['states'][rid] == 'done' for rid in PAIR)
                    and all(abs(p[0] - cx) <= hx + tol and abs(p[1] - cy) <= hy + tol for p in r['beam_corners'])
                    and -c['floor_penetration_tolerance_m'] <= bottom(r) <= c['release_bottom_m']
                    and r['tilt_deg'] <= c['release_tilt_deg']
                    and all(max(r['finger_n'][rid]) < c['release_finger_n'] for rid in PAIR))
        # Stable final interval, including low speed, not an earlier transient placement.
        tail = [r for r in rows if r['t'] >= times[-1] - c['release_dwell_s'] - c['max_sample_gap_s']]
        stable = sustained(tail, placed, c['release_dwell_s'], c['max_sample_gap_s'])
        speeds = [math.dist(a['beam_xyz'], b['beam_xyz']) / (b['t'] - a['t']) for a, b in zip(tail, tail[1:])]
        checks['placement_release'] = stable is not None and placed(rows[-1]) and bool(speeds) and max(speeds) <= c['release_speed_m_s']
        drops = [r['t'] for r, setdown in zip(rows, setdowns) if lifted_at is not None and r['t'] >= lifted_at and
                 (r['tilt_deg'] > c['max_transport_tilt_deg'] or bottom(r) < -c['floor_penetration_tolerance_m']
                  or (bottom(r) < c['drop_bottom_m'] and setdown is None))]
        checks['no_drop'] = lifted_at is not None and not drops
        forbidden = ('robot_robot', 'robot_wall', 'beam_wall', 'robot_beam_approach', 'r3_interference')
        checks['contacts'] = checks['contacts_complete'] and all(contacts['counts'][k] == 0 for k in forbidden)
        checks['r3'] = (checks['contacts_complete'] and contacts['counts']['r3_interference'] == 0 and contacts['r3_motion_commands'] == 0
                        and contacts['r3_api_calls'] == 0 and contacts['r3_max_displacement_m'] <= c['r3_max_displacement_m'])
        checks['weld_off'] = checks['contacts_complete'] and contacts['max_eq_active'] == 0
        checks['video'] = bool(video_review and video_review.get('verified') is True)
        evidence.update(grasp_at_s=grasp_at, lifted_at_s=lifted_at, door_at_s=door_at, drop_samples=drops,
                        final_stable_at_s=stable, approach=approach)
    except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError, OverflowError) as exc:
        errors.append(f'{type(exc).__name__}: {exc}')
    nominal = manifest.get('intervention') == 'none'
    complete = (manifest.get('state') == 'completed' and not manifest.get('host_error')
                and manifest.get('source_changed') is False and manifest.get('inputs_changed') is False)
    passed = all(checks.values()) and not errors and nominal and complete
    incomplete = not checks['trace_complete'] or not checks['contacts_complete'] or bool(errors)
    return {'schema': 'ugrp.zone_pair_dev_evaluation.v1', 'labels': LABELS, 'research_result': False,
            'physical_success': passed, 'dev_physical_success': passed,
            'verdict': 'DEV_PASS' if passed else ('HOST_ERROR' if manifest.get('host_error') else
                                                'EVIDENCE_INCOMPLETE' if incomplete else 'DEV_NOT_CONFIRMED'),
            'checks': checks, 'evidence': evidence, 'protocol': protocol, 'errors': errors,
            'sequence_done_is_success': False,
            'video_review': video_review or {'verified': False, 'reason': 'manual review pending'}}


def load_lines(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def evaluate_run(run, review_path=None):
    run = Path(run)
    ev = run / 'eval_only'
    manifest = json.loads((run / 'manifest.json').read_text())
    prereg_bytes = (run / 'prereg.json').read_bytes()
    registration = manifest.get('prereg')
    expected_hash = registration.get('sha256') if isinstance(registration, dict) else None
    if hashlib.sha256(prereg_bytes).hexdigest() != expected_hash:
        raise ValueError('prereg hash mismatch: snapshot does not match the original manifest prereg.sha256')
    prereg = json.loads(prereg_bytes)
    records = json.loads((run / 'pair_records.json').read_text())
    targets = prereg['planned_setdown']['route_endpoints_m']
    if (len(records) != 1 or len(records[0]['plan']['route']) != len(targets) + 1
            or any(math.dist(a, b) > 1e-9 for a, b in zip(records[0]['plan']['route'][1:], targets))):
        raise ValueError('planned route does not match preregistered set-down targets')
    status = load_lines(run / 'status.jsonl')
    required = []
    if manifest['intervention'] == 'none' and len(records) == 1:
        segments = len(records[0]['plan']['route']) - 1
        required = ['approach_go_0'] + [f'{p}_go_{i}' for i in range(segments) for p in ('lift', 'carry', 'lower', 'open')]
    protocol = audit_protocol(status, load_lines(run / 'commands.jsonl'), load_lines(run / 'shutdown.jsonl'), required,
                              require_abort=manifest['intervention'] != 'none', post_s=prereg['criteria']['post_abort_s'])
    review = None
    if review_path:
        raw = json.loads(Path(review_path).read_text())
        videos = sorted(ev.glob('*.mp4'))
        stages = ('approach', 'joint_grasp', 'lift', 'door', 'placement_release', 'drop_contact')
        verified = (bool(videos) and raw.get('reviewer') and raw.get('run_id') == manifest['run_id']
                    and raw.get('trace_sha256') == sha_file(ev / 'trace.jsonl')
                    and all(raw.get('videos', {}).get(p.name) == sha_file(p) for p in videos)
                    and all(raw.get('stages', {}).get(k) is True for k in stages))
        review = {'verified': bool(verified), 'record': raw}
    result = score(manifest, prereg, load_lines(ev / 'trace.jsonl'),
                   json.loads((ev / 'contacts.json').read_text()), protocol, video_review=review)
    injection = json.loads((run / 'intervention.json').read_text()) if (run / 'intervention.json').is_file() else None
    injection_exercised = bool(injection and injection['kind'] == 'abort_after_carry_go'
                              and any(q['arm'] or q['carry'] or q['macro'] or q['servo_targets'] or q['motor_nonzero']
                                      for q in injection['queues_before'].values()))
    result['abort_diagnostic'] = {'intervention_exercised_with_pending_motion': injection_exercised,
                                  'passed': bool(injection_exercised and protocol['ok'] and protocol['go_seen']
                                                 and result['checks']['trace_complete'] and result['checks']['contacts_complete']
                                                 and manifest['state'] == 'completed'
                                                 and not manifest.get('intervention_not_reached'))}
    commands = load_lines(run / 'commands.jsonl')
    result.update(run_id=manifest['run_id'], seed=manifest['seed'], condition='tags_temporary_dev_' + manifest['intervention'],
                  source_sha=manifest.get('source', {}).get('source_sha'), wall_s=manifest.get('wall_s'),
                  sim_s=manifest.get('sim_end_s'), commands=sum(c['kind'] in MOTION for c in commands),
                  model_calls=0, model_response_time='not_applicable_no_model_calls',
                  scope='tags_temporary, dev, 연구 결과 아님', clock='synchronous SIM',
                  policy='PairTeam/M2DoorStudent-v3', case=manifest['run_id'], limits=manifest['limits'],
                  config={'contact_profile': 'cargo_noslip_v1'},
                  command_count_scope='issued arm/look/drive/mecanum commands, not successful physical actions')
    result['input_sha256'] = {str(p.relative_to(run)): sha_file(p) for p in
                              [run / 'manifest.json', run / 'prereg.json', run / 'pair_records.json',
                               run / 'status.jsonl', run / 'commands.jsonl', run / 'shutdown.jsonl',
                               ev / 'trace.jsonl', ev / 'contacts.json']}
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--video-review', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    if not a.output.resolve().is_relative_to((a.run / 'eval_only').resolve()) or a.output.exists():
        p.error('use a NEW output path inside run/eval_only/; preserve earlier scoring')
    try:
        result = evaluate_run(a.run, a.video_review)
    except (OSError, ValueError, KeyError) as exc:
        result = {'physical_success': False, 'verdict': 'EVIDENCE_INCOMPLETE', 'error': str(exc), 'labels': LABELS}
    write_json(a.output, result)
    print(json.dumps({'evaluation': str(a.output), 'physical_success': result['physical_success']}))
    return 0 if result['physical_success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
