"""Verify fresh GCP recording receipts, then compare five estimates offline.

Every preregistered run/robot remains in the denominator, including absent,
failed, truncated, mistimed or corrupted recordings. No physics imports.
"""
import argparse
import json
from pathlib import Path
import numpy as np

from scripts.e2e_stage_pose_eval import read
from harness.e2e_result_writer import write
from scripts.extract_e2e_pose_features import packets, sha256, source_sha256
from scripts.record_map_amcl import SPEC, load_spec, run_name
from scripts.replay_map_amcl import main as replay_main


def cohort_for(raw_root, spec, source_sha, spec_sha):
    intervals, receipts, maps = [], {}, set()
    for seed in spec['seeds']:
        run = run_name(seed)
        raw = raw_root/run/'raw'
        problem, origin = None, None
        try:
            result = read(raw/'result.json')
            if (result['status'] != 'RECORDED' or not result['finalization_complete'] or
                    result['finalization_errors'] or result['source_sha'] != source_sha or
                    result['host'] != spec['host'] or result['machine_type'] != spec['machine_type'] or
                    result['project'] != spec['project'] or result['spec_sha256'] != spec_sha or
                    result['seed'] != seed or result['frames_per_robot'] != spec['frames_per_robot'] or
                    result['top_camera_input'] is not False or result['candidate_in_control'] is not False):
                raise ValueError('RECORDING_PROVENANCE_OR_COMPLETION_MISMATCH')
            origin = result['origin_s']
            audit = result.get('input_audit', {})
            if (audit.get('status') != 'MEASURED_CONTROLLER_BOUNDARY' or
                    any(audit.get(k) != 0 for k in ('top_camera_inputs', 'truth_reads', 'held_world_reads', 'rejected_inputs')) or
                    audit.get('own_rgb_inputs') != spec['frames_per_robot']*len(spec['robots']) or
                    audit.get('controller_calls') != audit.get('own_rgb_inputs') or
                    read(raw/'input-audit.json') != audit):
                raise ValueError('MEASURED_INPUT_AUDIT_REQUIRED')
            hashes = read(raw/'artifacts.sha256.json')
            # Verify all mandatory raw files, including original JPEG bytes;
            # no evaluator file is opened for its values until replay estimates
            # have been produced. A digest is not a control observation.
            required = ['result.json', 'bundle.json', 'scene.json', 'scene.xml', 'inputs/static_map.json',
                        'input-audit.json']
            for rid in spec['robots']:
                required += [f'robots/{rid}/{n}.jsonl' for n in ('frames', 'commands', 'ownmap')]
                required += [f'eval_only/{rid}/trajectory.jsonl']
                frames = read(raw/f'robots/{rid}/frames.jsonl', True)
                rows = packets(raw, rid)
                if len(frames) != spec['frames_per_robot'] or len(rows) != spec['frames_per_robot']:
                    raise ValueError('ALL_10HZ_FRAMES_REQUIRED')
                times = np.arange(spec['frames_per_robot'])*spec['period_s']
                if (not np.allclose([r['t'] for r in rows], times, atol=1e-6, rtol=0) or
                        not np.allclose([r['physical_t'] for r in rows], times+origin, atol=1e-6, rtol=0)):
                    raise ValueError('10HZ_FRAME_CLOCK_MISMATCH')
                for row in rows:
                    image = Path(row['image_path'])
                    name = str(image.relative_to(raw.resolve()))
                    if sha256(image) != row['sha256']:
                        raise ValueError('RGB_SHA_MISMATCH')
                    required.append(name)
            for name in required:
                if hashes.get(name) != source_sha256(raw/name):
                    raise ValueError('RECORDING_HASH_MISMATCH:'+name)
            map_hash = source_sha256(raw/'inputs/static_map.json')
            maps.add(map_hash)
            receipts[run] = dict(result_sha256=source_sha256(raw/'result.json'),
                manifest_sha256=source_sha256(raw/'artifacts.sha256.json'), static_map_sha256=map_hash)
        except (OSError, KeyError, ValueError, TypeError) as error:
            problem = type(error).__name__+':'+str(error)
        for rid in spec['robots']:
            intervals.append(dict(run=run, robot=rid, N=spec['frames_per_robot'], cutoff_s=0.,
                physics_start_s=origin, condition='gcp1_fresh_drive_10hz', unavailable_reason=problem))
    if len(maps) > 1:
        for interval in intervals:
            interval['unavailable_reason'] = 'MIXED_STATIC_MAPS'
    return dict(schema='map-amcl-paired-cohort/1', paired_recording=True,
        expected_N=len(spec['seeds'])*len(spec['robots']), intervals=intervals,
        recording_spec_sha256=spec_sha, recording_source_sha=source_sha, receipts=receipts,
        scope='Fresh GCP own-camera [0,60]s drive; full interval including convergence; rigid SE2 and absolute map errors; GT evaluation only',
        caveat='DEV localization only; failures remain in N; not grasp/E2E success; never pool historical Azure observations')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-root', type=Path, required=True)
    p.add_argument('--recording-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    spec = load_spec()
    a.output.mkdir(parents=True, exist_ok=False)
    cohort = cohort_for(a.raw_root, spec, a.recording_source_sha, sha256(SPEC))
    write(a.output/'cohort.json', cohort)
    summary = replay_main(['--raw-root', str(a.raw_root), '--cohort', str(a.output/'cohort.json'),
        '--feature-root', str(a.output/'features'), '--extract-saved-rgb', '--map-amcl', 'amcl_v1',
        '--output', str(a.output/'replay')])
    write(a.output/'summary.json', dict(schema='map-amcl-recorded-comparison/1',
        comparison_complete=summary['comparison_complete'], expected_intervals=spec['expected_intervals'],
        paired_aggregates=summary['paired_aggregates'],
        source_sha=summary['source_sha'], recording_source_sha=a.recording_source_sha,
        raw_root=str(a.raw_root), replay_summary_sha256=sha256(a.output/'replay/summary.json'),
        cohort_sha256=sha256(a.output/'cohort.json'), automatic_promotion=False))
    return 0 if summary['comparison_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
