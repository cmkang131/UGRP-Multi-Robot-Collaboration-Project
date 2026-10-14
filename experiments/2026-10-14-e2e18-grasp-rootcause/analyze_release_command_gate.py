"""Read-only evaluation of retrieved cdace35e logs; no simulator/controller imports.

Truth stays in this offline report. No fitted parameter or pose is exported to
the teacher. Run from the repository root with python3 and zstd available.
"""
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import statistics
import subprocess

ROOT = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
OUT = Path(__file__).with_name('release-command-gate-diagnosis.json')


def read(path):
    if not path.exists() and path.suffix == '.zst':
        path = path.with_suffix('')
    raw = path.read_bytes()
    text = subprocess.check_output(['zstd', '-dc', str(path)]).decode() if path.suffix == '.zst' else raw.decode()
    digest = hashlib.sha256(raw).hexdigest()
    manifest = path.parent.parent / 'SHA256SUMS'
    expected = {line.split(maxsplit=1)[1]: line.split(maxsplit=1)[0]
                for line in manifest.read_text().splitlines() if line.strip()}
    remote = '/home/ugrp/ugrp-sim/runs/' + str(path.relative_to(ROOT))
    if expected.get(remote) != digest:
        raise ValueError(f'retrieved hash does not match source manifest: {path}')
    return text, {'path': str(path), 'sha256': digest, 'bytes': len(raw), 'source_manifest_verified': True}


def stats(xs):
    return {'n': len(xs), 'min': min(xs), 'median': statistics.median(xs), 'max': max(xs)} if xs else {'n': 0}


def main():
    runs, origins, inputs = [], [], []
    for index in range(40):
        base = ROOT / f'release-command-gate-{index:02d}-cdace35e' / 'raw'
        values = {}
        for name in ('plan.json', 'result.json.zst', 'eval-only.jsonl.zst', 'teacher-r1.jsonl.zst', 'teacher-r2.jsonl.zst'):
            text, meta = read(base / name)
            inputs.append(meta)
            values[name] = [json.loads(line) for line in text.splitlines()] if 'jsonl' in name else json.loads(text)
        result, plan = values['result.json.zst'], values['plan.json']
        robots = {}
        for rid, item in result['lookaround_result'].items():
            loc, ev = item['localizer'], item['evaluation']
            views = loc['views']
            # before/after are overwritten by each sweep in the source runner.
            # Preserve the last recorded pair and every independently recorded view.
            robots[rid] = {
                'last_sweep_t0': ev.get('t0'), 'last_sweep_sim_s': ev.get('sim_s'),
                'before': ev.get('before'), 'after': ev.get('after'),
                'last_decision': ev.get('decision'),
                'map_pose_known': loc['map_pose_known'], 'pose_frame': loc['pose_frame'],
                'view_count': len(views),
                'detection_sample_totals': {k: sum(v.get(k, 0) for v in views) for k in ('wall_points', 'floor_lines', 'doors')},
                'views_with_detections': sum(bool(sum(v.get(k, 0) for k in ('wall_points', 'floor_lines', 'doors'))) for v in views),
                'associated_map_groups': sorted(set(g for v in views for g in v.get('seen_groups', []))),
                'update_skipped': dict(Counter(v.get('update_skipped', 'not_recorded') for v in views)),
                'views': ev['views'],
            }
            origins += ev['views']
        positions = result['evaluation_position_error']
        decisions = result['code_decisions']
        shifts = [d for d in decisions if d['action'] == 'shift']
        truth_rows = [v for v in values['eval-only.jsonl.zst'] if 'beam' in v]
        phase_groups = []
        for row in truth_rows:
            if not phase_groups or phase_groups[-1]['phase'] != row['phase']:
                phase_groups.append({'phase': row['phase'], 'start_t': row['t'], 'end_t': row['t'], 'start_beam': row['beam']['pose'], 'end_beam': row['beam']['pose']})
            phase_groups[-1].update(end_t=row['t'], end_beam=row['beam']['pose'])
        shift_observed = []
        for group in phase_groups:
            if group['phase'] == 'shift':
                group = dict(group)
                group['beam_delta_xy_m'] = [b-a for a,b in zip(group['start_beam'][:2], group['end_beam'][:2])]
                shift_observed.append(group)
        observed_reports = {}
        for rid in ('r1', 'r2'):
            seen = []
            for row in values[f'teacher-{rid}.jsonl.zst']:
                report = row.get('report')
                if report and report.get('phase') == 'observe' and (not seen or seen[-1]['report'] != report):
                    seen.append({'t': row['t'], 'report': report})
            observed_reports[rid] = seen
        runs.append({
            'index': index, 'seed': plan['seed'], 'scenario': plan['scenario_id'],
            'zone': plan['destination_region'], 'long_axis': positions['zone_long_axis'],
            'stratum': plan['stratum'], 'beam_start_yaw_deg': math.degrees(plan['beam_pose'][2]),
            'success': result['release_success'], 'prefix_held': result['prefix_held'],
            'outcome': result['release_outcome'], 'reasons': result['release_failure_reasons'],
            'initial_center_distance_m': result['release_start']['beam_to_zone_center_m'],
            'position': positions, 'lookaround': robots,
            'first_decision': decisions[0], 'shift_decisions': shifts,
            'shift_phases_eval': shift_observed, 'observe_reports': observed_reports,
            'reported_shift_steps': result['shift_steps'],
            'input_audit': {k: result['input_audit'][k] for k in ('held_world_reads', 'invisible_measurements')},
        })
    groups = {}
    for key in ('scenario', 'zone', 'long_axis', 'side', 'teal_south', 'axial_outside_m'):
        grouped = defaultdict(list)
        for run in runs:
            value = run[key] if key in run else run['stratum'][key]
            grouped[str(value)].append(run)
        groups[key] = {k: {'n': len(v), 'success': sum(x['success'] for x in v), 'failed_indices': [x['index'] for x in v if not x['success']]} for k,v in grouped.items()}
    robots = [robot for run in runs for robot in run['lookaround'].values()]
    summary = {
        'source_sha': 'cdace35e0c5bd94d0c1d348e17cd470a773cb270',
        'scope': 'offline evaluation only; no physics/rendering/model calls; frames not yet retrieved or reviewed',
        'success': sum(r['success'] for r in runs), 'n': len(runs),
        'prefix_held': sum(r['prefix_held'] for r in runs),
        'center_distance_m': {key: stats([r['position']['center_distance_m'] for r in runs if key == 'all' or r['success'] == (key == 'success')]) for key in ('all', 'success', 'failure')},
        'center_y_offset_m': stats([r['position']['center_offset_m'][1] for r in runs]),
        'last_sweep_error_before_m': stats([r['before']['error_xy_m'] for r in robots]),
        'last_sweep_error_after_m': stats([r['after']['error_xy_m'] for r in robots if r['after']]),
        'error_scope': 'arbitrary command origin, aligned using evaluation-only spawn; map-frame error is undefined, not zero',
        'before_after_limit': 'only last sweep before/after retained per robot; every view retained; timeout may leave last sweep incomplete',
        'accepted_last_sweeps': sum(bool(r['last_decision'] and r['last_decision']['accepted']) for r in robots),
        'last_sweep_reasons': dict(Counter((r['last_decision'] or {}).get('reason', 'missing') for r in robots)),
        'detection_totals_not_unique_landmarks': {k: sum(r['detection_sample_totals'][k] for r in robots) for k in ('wall_points','floor_lines','doors')},
        'view_count': sum(r['view_count'] for r in robots),
        'views_with_detections': sum(r['views_with_detections'] for r in robots),
        'associated_map_group_count': sum(len(r['associated_map_groups']) for r in robots),
        'camera_fk_origin_error_m': stats([r['camera_fk_origin_error_m'] for r in origins]),
        'camera_fk_axis_error_deg': stats([r['camera_fk_axis_error_deg'] for r in origins]),
        'first_lower_without_evidence': sum(r['first_decision']['action'] == 'lower' and r['first_decision']['evidence'] == ['none','none'] for r in runs),
        'input_audit_totals': {k: sum(r['input_audit'][k] for r in runs) for k in ('held_world_reads','invisible_measurements')},
        'groups': groups,
    }
    detail = OUT.with_name('release-command-gate-diagnosis-detail.json.zst')
    payload = (json.dumps({'runs': runs, 'inputs': inputs}, ensure_ascii=False, indent=2) + '\n').encode()
    compressed = subprocess.check_output(['zstd', '-q', '-c'], input=payload)
    detail.write_bytes(compressed)
    summary['detail'] = {'path': detail.name, 'sha256': hashlib.sha256(compressed).hexdigest(), 'bytes': len(compressed)}
    summary['input_files_verified_against_source_manifest'] = len(inputs)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
