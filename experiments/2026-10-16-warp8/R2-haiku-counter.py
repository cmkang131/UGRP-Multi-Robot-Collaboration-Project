#!/usr/bin/env python3
import json
import subprocess
import sys
import os

def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    if os.path.exists(path + '.zst'):
        data = subprocess.check_output(['zstd', '-qdc', path + '.zst'])
        return json.loads(data)
    return None

def load_jsonl(path):
    if os.path.exists(path):
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
    if os.path.exists(path + '.zst'):
        data = subprocess.check_output(['zstd', '-qdc', path + '.zst']).decode('utf-8')
        return [json.loads(line) for line in data.split('\n') if line.strip()]
    return None

ROOT = '/home/ugrp/ugrp-sim/runs/warp8/beam40-r2'
status_histogram = {}
completed_N = 0
successes_recounted = 0
original_success_count = 0
per_completed = {}
physical_agree = []
physical_disagree = []
source_shas = set()
audit_zero_count = 0
audit_by_scope = {}
errors = []

summary = load_json(os.path.join(ROOT, 'summary.json'))
if summary:
    for key in summary:
        if 'sha' in key.lower() and isinstance(summary[key], str):
            source_shas.add(summary[key])

cmd_path1 = os.path.join(ROOT, 'beam40-r2.command.json')
cmd_path2 = ROOT + '.command.json'
cmd_file = None
if os.path.exists(cmd_path1):
    cmd_file = load_json(cmd_path1)
    cmd_source_path = cmd_path1
elif os.path.exists(cmd_path2):
    cmd_file = load_json(cmd_path2)
    cmd_source_path = cmd_path2
else:
    errors.append({'error': 'command.json not found at expected paths'})

if cmd_file:
    for key in cmd_file:
        if 'sha' in key.lower() and isinstance(cmd_file[key], str):
            source_shas.add(cmd_file[key])

for i in range(40):
    world = f'world-{i:03d}'
    world_path = os.path.join(ROOT, world)

    try:
        raw = load_json(os.path.join(world_path, 'raw', 'result.json'))
        if raw is None:
            errors.append({'world': world, 'error': 'result.json not found'})
            continue

        assert isinstance(raw.get('input_audit'), dict) and all(k in raw['input_audit'] for k in ('held_world_reads','invisible_measurements')), 'audit fields missing'
        status = raw.get('status')
        if status is None:
            errors.append({'world': world, 'error': 'status key missing'})
            continue

        if status not in status_histogram:
            status_histogram[status] = 0
        status_histogram[status] += 1

        if 'source_sha' in raw:
            source_shas.add(raw['source_sha'])

        if status != 'complete':
            ia = raw.get('input_audit')
            if ia:
                if ia.get('held_world_reads') == 0 and ia.get('invisible_measurements') == 0:
                    scope = 'saved-prefix' if status == 'HOST_ERROR' else 'other'
                    if scope not in audit_by_scope:
                        audit_by_scope[scope] = 0
                    audit_by_scope[scope] += 1
                    audit_zero_count += 1
            continue

        completed_N += 1

        ia = raw.get('input_audit')
        if ia:
            if ia.get('held_world_reads') == 0 and ia.get('invisible_measurements') == 0:
                if 'whole-run' not in audit_by_scope:
                    audit_by_scope['whole-run'] = 0
                audit_by_scope['whole-run'] += 1
                audit_zero_count += 1

        rows = load_jsonl(os.path.join(world_path, 'raw', 'eval-only.jsonl'))
        if rows is None or len(rows) == 0:
            errors.append({'world': world, 'error': 'eval-only.jsonl empty or not found'})
            per_completed[world] = {
                'error': 'no eval data',
                'recomputed_success': False,
                'original_physical_success': raw.get('physical_success', False)
            }
            if raw.get('physical_success'):
                original_success_count += 1
            continue

        first_good = None
        last_t = None
        components_min = {'r1_0': float('inf'), 'r1_1': float('inf'), 'r2_0': float('inf'), 'r2_1': float('inf'), 'min_z': float('inf')}
        tilt_max = float('-inf')
        densegrid_ok = True

        for idx, row in enumerate(rows):
            t = row.get('t', 0.0)
            last_t = t
            contacts = row.get('contacts', {})
            beam = row.get('beam', {})

            r1 = contacts.get('r1', [0, 0])
            r2 = contacts.get('r2', [0, 0])
            min_z = beam.get('min_z', 0.0)
            tilt = beam.get('tilt_deg', 0.0)

            components_min['r1_0'] = min(components_min['r1_0'], r1[0])
            components_min['r1_1'] = min(components_min['r1_1'], r1[1])
            components_min['r2_0'] = min(components_min['r2_0'], r2[0])
            components_min['r2_1'] = min(components_min['r2_1'], r2[1])
            components_min['min_z'] = min(components_min['min_z'], min_z)
            tilt_max = max(tilt_max, tilt)

            if idx > 0:
                prev_t = rows[idx - 1].get('t', 0.0)
                if abs((t - prev_t) - 0.1) >= 1e-8:
                    densegrid_ok = False

            is_good = (r1[0] >= 0.5 and r1[1] >= 0.5 and r2[0] >= 0.5 and r2[1] >= 0.5
                      and min_z >= 0.012 and tilt <= 10.0)

            if is_good:
                if first_good is None:
                    first_good = t
            else:
                first_good = None

        terminal_hold = 0.0
        if first_good is not None and last_t is not None:
            terminal_hold = last_t - first_good

        teacher_N = raw.get('teacher_N')
        teachers_ok = False
        teacher_outcomes = {}

        if teacher_N == 2 and 'teachers' in raw:
            teachers = raw.get('teachers', {})
            r1_outcome = teachers.get('r1', {}).get('outcome')
            r2_outcome = teachers.get('r2', {}).get('outcome')
            teacher_outcomes = {'r1': r1_outcome, 'r2': r2_outcome}
            if r1_outcome == 'success' and r2_outcome == 'success':
                teachers_ok = True
        elif teacher_N != 2:
            teacher_outcomes = {'error': f'teacher_N={teacher_N}, expected 2'}
        else:
            teacher_outcomes = {'error': 'teachers key missing'}

        recomputed_success = (terminal_hold >= 3.0) and teachers_ok and densegrid_ok
        original_success = raw.get('physical_success', False)

        if original_success:
            original_success_count += 1
        if recomputed_success:
            successes_recounted += 1

        if original_success == recomputed_success:
            physical_agree.append(world)
        else:
            physical_disagree.append(world)

        per_completed[world] = {
            'evaluatorN': len(rows),
            'lastgoodstart': first_good if first_good is not None else None,
            'end': last_t,
            'terminalhold': terminal_hold,
            'everycomponentminimum': components_min if components_min['r1_0'] != float('inf') else {},
            'densegrid': densegrid_ok,
            'teacheroutcomes': teacher_outcomes,
            'recomputed_success': recomputed_success,
            'original_physical_success': original_success
        }

    except Exception as e:
        errors.append({'world': world, 'error': str(e)})

out = {
    'audit': {
        'zero_count': audit_zero_count,
        'by_scope': audit_by_scope
    },
    'completed_N': completed_N,
    'errors': errors,
    'original_physical_success_count': original_success_count,
    'per_completed': per_completed,
    'physical_source_agreement': {
        'agree_count': len(physical_agree),
        'disagree_count': len(physical_disagree),
        'disagree_worlds': physical_disagree
    },
    'source_provenance': sorted(list(source_shas)),
    'status_histogram': status_histogram,
    'successes_recounted': successes_recounted
}

print(json.dumps(out, separators=(',', ':'), sort_keys=True))
