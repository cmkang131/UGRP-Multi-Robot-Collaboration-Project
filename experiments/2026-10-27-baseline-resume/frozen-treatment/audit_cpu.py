"""Small CPU-only pilot/termination decisions; no model/simulator imports."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess

# Same registered r2 cap and original comparison tolerance, not fitted values.
STUDENT_CAP_S = 180.
CAP_TOLERANCE = 1e-8

# C-03: r2 eval-only XY excursions, 20 worlds x 2 robots, empirical P100.
# Source VM CPU recount: conditions-fix-20261026/motion-reference.json,
# SHA256 fc40c2e79df8a173801644ac4de4572980696b55c32535e558c65963b7392515.
# Strictly exceed the entire observed blocked-run envelope; this is a pilot
# translation diagnostic, not a success/distance-to-goal or control threshold.
# Active only in the opt-in Arm C pilot; default treatment mode remains none.
TRANSLATION_THRESHOLD_M = 0.03082987502070276
# Frozen grasp_act_contract.PERIOD_S / original evaluation sampling = 10 Hz.
EVAL_PERIOD_S = 0.1
MOTION_SCHEMA = 'ugrp.baseline-treatment.eval-motion.v1'


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def physical_motion(rows, robots=('r1', 'r2')):
    """Evaluation-only XY excursion/path and yaw, never controller input."""
    first, previous, metrics = {}, {}, {}
    times = []
    for row in rows:
        now = row['t']
        if not finite_number(now) or (times and
                (now <= times[-1] or now - times[-1] > EVAL_PERIOD_S + CAP_TOLERANCE)):
            raise ValueError('nonfinite_nonmonotonic_or_gapped_eval_time')
        times.append(now)
        for rid in robots:
            pose = row['robots'][rid]['pose']
            if len(pose) != 3 or not all(finite_number(v) for v in pose):
                raise ValueError('invalid_eval_robot_pose:' + rid)
            if rid not in first:
                first[rid] = previous[rid] = pose
                metrics[rid] = dict(max_xy_excursion_m=0., net_xy_displacement_m=0.,
                                    xy_path_m=0., yaw_path_rad=0.)
            metric = metrics[rid]
            metric['max_xy_excursion_m'] = max(metric['max_xy_excursion_m'], math.dist(first[rid][:2], pose[:2]))
            metric['net_xy_displacement_m'] = math.dist(first[rid][:2], pose[:2])
            metric['xy_path_m'] += math.dist(previous[rid][:2], pose[:2])
            delta = pose[2] - previous[rid][2]
            metric['yaw_path_rad'] += abs(math.atan2(math.sin(delta), math.cos(delta)))
            previous[rid] = pose
    if len(times) < 2:
        raise ValueError('fewer_than_two_eval_samples')
    return dict(schema=MOTION_SCHEMA, status='MEASURED', samples=len(times),
                first_t=times[0], last_t=times[-1], robots=metrics)


def read_physical_motion(raw_dir, raw):
    """Read closed raw logs after lane completion; preserve all raw bytes."""
    record = dict(schema=MOTION_SCHEMA, status='UNMEASURED', robots={})
    try:
        paths = [p for p in (Path(raw_dir) / 'eval-only.jsonl',
                            Path(raw_dir) / 'eval-only.jsonl.zst') if p.is_file()]
        if len(paths) != 1:
            raise ValueError('missing_or_ambiguous_eval_only_log')
        path = paths[0]
        packed = path.read_bytes()
        decoded = subprocess.check_output(['zstd', '-qdc'], input=packed) if path.suffix == '.zst' else packed
        record.update(raw_path=str(path.resolve()), bytes=len(packed),
                      sha256=hashlib.sha256(packed).hexdigest(),
                      decoded_sha256=hashlib.sha256(decoded).hexdigest())
        measured = physical_motion(json.loads(line) for line in decoded.splitlines() if line.strip())
        origin = ((raw.get('student_eval') or {}).get('treatment') or {}).get('episode_origin_t')
        sim = raw.get('sim_s')
        if not finite_number(origin) or not finite_number(sim) or sim <= 0:
            raise ValueError('missing_episode_clock_for_eval_motion')
        if (abs(measured['first_t'] - origin) > CAP_TOLERANCE or
                measured['last_t'] < origin + sim - EVAL_PERIOD_S - CAP_TOLERANCE or
                measured['last_t'] > origin + sim + CAP_TOLERANCE):
            raise ValueError('eval_motion_does_not_cover_episode')
        record.update(measured)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        record.update(status='UNMEASURED', reason=str(error), robots={})
    return record


def termination(raw, batch_cap_end=None):
    sim = raw.get('sim_s')
    cap = raw.get('cap_end')
    finished = (raw.get('student_eval') or {}).get('finished_t')
    origin = ((raw.get('student_eval') or {}).get('treatment') or {}).get('episode_origin_t')
    finished_elapsed = finished - origin if finished is not None and origin is not None else None
    status = raw.get('status')
    issues = []
    if status != 'complete':
        label = 'HOST_ERROR' if status == 'HOST_ERROR' else 'INCOMPLETE'
    elif not isinstance(sim, (int, float)) or type(cap) is not bool:
        label = 'UNCLASSIFIED'
        issues.append('missing_raw_cap_end_or_sim_s')
    elif cap != (sim >= STUDENT_CAP_S - CAP_TOLERANCE):
        label = 'UNCLASSIFIED'
        issues.append('raw_cap_end_vs_180_SIM_conflict')
    elif cap:
        label = 'cap_end'
    elif finished is not None:
        label = 'learned_finished_early'
    else:
        label = 'other_terminal_unverified'
    if finished is not None and origin is None:
        issues.append('missing_episode_origin_for_absolute_finished_t')
        label = 'UNCLASSIFIED'
    if finished_elapsed is not None and isinstance(sim, (int, float)) and (finished_elapsed < -CAP_TOLERANCE or finished_elapsed > sim + CAP_TOLERANCE):
        issues.append('finished_t_after_sim_s')
        label = 'UNCLASSIFIED'
    return dict(termination=label, raw_cap_end=cap, sim_s=sim, finished_t=finished,
        episode_origin_t=origin, finished_elapsed_s=finished_elapsed,
        batch_cap_end=batch_cap_end,
        batch_raw_cap_end_disagreement=batch_cap_end is not None and batch_cap_end != cap,
        audit_issues=issues, denominator_included=status == 'complete')


def pilot_gate(completions, physical_motion_records=None):
    if len(completions) != 4:
        raise ValueError('pilot gate requires exactly four completed episodes')
    rejections, stages = Counter(), Counter()
    moved = host_errors = 0
    hold_issues = []
    terminations = []
    motions, motion_issues, translated = [], [], []
    for world, raw in completions:
        student = raw.get('student_eval') or {}
        treatment = student.get('treatment') or {}
        motion = (physical_motion_records or {}).get(world) or {}
        motions.append(dict(world=world, **motion))
        if motion.get('schema') != MOTION_SCHEMA or motion.get('status') != 'MEASURED':
            motion_issues.append(dict(world=world, issue='missing_or_invalid_physical_motion',
                                      reason=motion.get('reason', 'not measured')))
        else:
            observed = motion.get('robots') or {}
            if set(observed) != {'r1', 'r2'}:
                motion_issues.append(dict(world=world, issue='missing_two_robot_physical_motion'))
            for rid, values in observed.items():
                excursion = values.get('max_xy_excursion_m')
                if not finite_number(excursion) or excursion < 0:
                    motion_issues.append(dict(world=world, robot_id=rid, issue='invalid_xy_excursion'))
                elif excursion > TRANSLATION_THRESHOLD_M:
                    translated.append(dict(world=world, robot_id=rid, max_xy_excursion_m=excursion))
        if treatment.get('mode') != 'arm_c':
            hold_issues.append(dict(world=world, issue='missing_arm_c_metadata'))
        host_errors += int(raw.get('status') != 'complete' or bool(raw.get('HOST_ERROR')))
        for events in student.get('barrier_events', {}).values():
            for event in events:
                if event.get('event') == 'proposal_rejected':
                    rejections[event.get('reason_category') or 'INVALID_EMPTY_REASON'] += 1
        metrics = treatment.get('metrics') or {}
        if len(metrics) != 2:
            hold_issues.append(dict(world=world, issue='missing_two_robot_metrics'))
        for rid, metric in metrics.items():
            ticks = metric.get('ticks', 0)
            counts = metric.get('stage_counts', {})
            stages.update(counts)
            moved += metric.get('nonzero_wheel_ticks', 0)
            if not (ticks > 0 and metric.get('inference_calls') == ticks and
                    metric.get('discard_calls') == ticks and metric.get('issued_ticks') == ticks and
                    sum(counts.values()) == ticks and metric.get('skill_counts') == {'grasp': ticks} and
                    metric.get('state225_nonzero') == 0):
                hold_issues.append(dict(world=world, robot_id=rid, issue='G9_G10_or_stage_sample_mismatch'))
        term = termination(raw)
        terminations.append(dict(world=world, **term))
        if term['audit_issues']:
            hold_issues.append(dict(world=world, issue='termination_audit_failed'))
    checks = dict(close_gate_count_zero=rejections['close_before_learned_ready'] == 0,
        zero_rejections_nonzero_wheels_and_translation=(sum(rejections.values()) == 0 and
            moved > 0 and bool(translated) and not motion_issues),
        stage_record_and_HOLD_valid=not hold_issues,
        HOST_ERROR_zero=host_errors == 0)
    return dict(schema='ugrp.baseline-treatment.pilot-gate.v2', completed_worlds=[i for i, _ in completions],
        checks=checks, pass_gate=all(checks.values()), rejections=dict(rejections),
        nonzero_wheel_robot_ticks=moved, stages=dict(stages),
        all_approach=bool(stages) and set(stages) == {'approach'},
        all_approach_rule='CONTINUE if all four integrity checks pass; never outcome-tune',
        hold_issues=hold_issues, terminations=terminations,
        physical_motion=motions, motion_issues=motion_issues, translated_robot_worlds=translated,
        physical_motion_column='max_xy_excursion_m', translation_threshold_m=TRANSLATION_THRESHOLD_M,
        translation_rule='all four worlds measured for both robots; at least one robot-world strictly exceeds r2 P100 XY excursion',
        cost_note='20 concurrent lanes already run; no 0.34 GPU-h stopping-cost guarantee')
