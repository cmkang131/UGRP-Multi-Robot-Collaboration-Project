"""Read-only, hash-checked v186 pose diagnosis from fetch-lite text evidence."""
import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import subprocess


def content(path):
    return path.read_bytes() if path.exists() else subprocess.check_output(['zstd', '-dc', str(path)+'.zst'])


def audit(raw):
    manifest_bytes = content(raw/'artifacts.sha256.json')
    manifest = json.loads(manifest_bytes)
    inputs = {}
    def read(name, lines=False):
        data = content(raw/name)
        digest = hashlib.sha256(data).hexdigest()
        if manifest.get(name) != digest:
            raise ValueError('raw hash mismatch: '+name)
        inputs[name] = digest
        return [json.loads(x) for x in data.splitlines()] if lines else json.loads(data)
    bundle = read('bundle.json')
    static = read('inputs/static_map.json')
    setup = read('eval_only/stage-setup.json')
    states = read('stage-states.json')
    records = read('student_record.json')['localizers']
    poses = read('eval_only/continuous-poses.jsonl', True)
    trajectory = {r: {row['t']: row for row in read(f'eval_only/{r}/trajectory.jsonl', True)}
        for r in ('r1', 'r2')}
    times = [x['t'] for x in states if all(y['state'] == 'carry' for y in x['robots'].values())]
    first = next(x for x in poses if x['t'] >= min(times))
    x0, x1, y0, y1 = static['bounds_m']
    center = [(x0+x1)/2, (y0+y1)/2]
    output = dict(name=raw.parent.name, raw=str(raw), seed=bundle['seed'],
        distance_m=bundle['continuous_distance']['target_m'], physical_source_sha=bundle['source_sha'],
        raw_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        frame=static['frame'], map_center_m=center, stage_origin=setup['stage_origin_receipt'],
        carry_entry_t=first['t'], robots={})
    for rid in ('r1', 'r2'):
        logs = records[rid]['poses']
        stamps = [r['t'] for r in logs]
        p = first['robots'][rid]
        # eval_sample precedes on_frames at this clock instant. Compare both
        # adjacent released reports; never resample or alter the stored PF.
        telemetry_match, truth_match = [], []
        for row in poses:
            estimate = row['robots'][rid]['estimated_xy_m']
            if estimate is None:
                continue
            i = bisect.bisect_right(stamps, row['t']+1e-8)-1
            choices = logs[max(0, i-1):i+1]
            finite = [[x['x'], x['y']] for x in choices if x['x'] is not None and x['y'] is not None]
            telemetry_match.append(min(math.dist(estimate, xy) for xy in finite))
            truth_match.append(math.dist(row['robots'][rid]['actual_xy_m'], trajectory[rid][row['t']]['robot_xyz_m'][:2]))
        report = min(logs, key=lambda r: abs(r['t']-first['t']))
        earliest = next(r for r in logs if r['x'] is not None and r['y'] is not None)
        updates = records[rid]['amcl_update']['rows']
        delta = [a-b for a, b in zip(p['estimated_xy_m'], p['actual_xy_m'])]
        peer = 'r2' if rid == 'r1' else 'r1'
        origin_delta = setup['stage_origin_receipt']['rigid_translation_xy_m']
        output['robots'][rid] = dict(actual_xy_m=p['actual_xy_m'], estimated_xy_m=p['estimated_xy_m'],
            error_vector_m=delta, error_m=math.hypot(*delta), std_xy_m=p['std_xy_m'],
            map_center_predicted_error_m=math.dist(center, p['actual_xy_m']),
            estimate_distance_from_map_center_m=math.dist(center, p['estimated_xy_m']),
            initial_report=dict(t=earliest['t'], xy_m=[earliest['x'], earliest['y']],
                distance_from_center_m=math.dist(center, [earliest['x'], earliest['y']]),
                std_xy_m=earliest['std_xy_m'], last_fix_t=earliest['last_fix_t']),
            certificate=report.get('convergence_certificate'),
            first_visual_update=updates[0] if updates else None,
            updates_before_carry=sum(r['t'] <= first['t'] for r in updates),
            particle_handoff=records[rid]['particle_sampling']['handoff'],
            telemetry_vs_own_released_report_max_m=max(telemetry_match),
            telemetry_vs_same_robot_truth_max_m=max(truth_match),
            id_swapped_error_m=math.dist(p['estimated_xy_m'], first['robots'][peer]['actual_xy_m']),
            add_stage_translation_error_m=math.dist([x+d for x,d in zip(p['estimated_xy_m'], origin_delta)],p['actual_xy_m']),
            subtract_stage_translation_error_m=math.dist([x-d for x,d in zip(p['estimated_xy_m'], origin_delta)],p['actual_xy_m']))
    a, b = first['robots']['r1'], first['robots']['r2']
    actual_separation = math.dist(a['actual_xy_m'], b['actual_xy_m'])
    estimate_separation = math.dist(a['estimated_xy_m'], b['estimated_xy_m'])
    output['rigid_transform_test'] = dict(actual_robot_separation_m=actual_separation,
        estimated_robot_separation_m=estimate_separation,
        best_possible_max_error_lower_bound_m=abs(actual_separation-estimate_separation)/2,
        reason='Translation, axis swap, rotation, reflection and ID swap preserve inter-robot distance.')
    output['verified_inputs_sha256'] = inputs
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    runs = [audit(raw) for raw in sorted(a.cohort.glob('*/raw'))]
    summary = dict(schema='ugrp.s3_pose_origin_audit.v1', n=len(runs),
        classification='unconverged map-uniform posterior in synthetic alignment-entry diagnostic',
        evaluator_coordinate_bug=False, estimator_coordinate_bug=False,
        correction_applied=False, control_inputs_changed=False, runs=runs,
        mechanism=['stage runner sets boot_finished_at and directly enters pair alignment; skips global startup scan',
            'new no-prior localizers sample static free-space in world metres and full yaw',
            'first base command downsamples global particles to2000 before a useful localization scan',
            'large connected global mode still reports a near-map-centre mean; existing convergence certificate is false',
            'DEV light continues with this explicitly uncertain estimate; distance targets share the same startup prefix'],
        scope='Diagnosis of archived evidence, not new localization accuracy or mission completion. Do not fit an offset using evaluation truth.')
    a.output.write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(n=len(runs), classification=summary['classification'],
        max_truth_match_m=max(v['telemetry_vs_same_robot_truth_max_m'] for r in runs for v in r['robots'].values()),
        max_report_match_m=max(v['telemetry_vs_own_released_report_max_m'] for r in runs for v in r['robots'].values()))))


if __name__ == '__main__':
    main()
