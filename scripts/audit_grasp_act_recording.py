"""Offline strict student-field, native RGB and camera audit of one raw run."""
import argparse
from pathlib import Path

from PIL import Image

from harness.grasp_act_contract import validate_observation
from harness.grasp_act_data import audit_camera, read_json, read_rows, safe_path, sha256, write_json


def existing(root, name):
    for suffix in ('', '.zst'):
        p = root / (name + suffix)
        if p.is_file():
            return p
    raise FileNotFoundError(root / name)


def audit(root):
    root = Path(root)
    result = read_json(existing(root, 'result.json'))
    if (result.get('training_rgb') is not True or result.get('recording_mode') != 'training'
            or result.get('student_execution') is not False):
        raise ValueError('training recording required')
    camera = read_json(root / 'student-camera.json')
    audit_camera(camera)
    observations = read_rows(existing(root, 'student-r1.jsonl'))
    if not observations:
        raise ValueError('empty recording')
    frames = {}
    times = []
    for row in observations:
        validate_observation(row)  # exact root AND nested allowlists
        times.append(row['t'])
        for ref in row['rgb']:
            if ref['path'] in frames:
                if frames[ref['path']]['sha256'] != ref['sha256']:
                    raise ValueError('conflicting RGB references')
                continue
            path = safe_path(root, ref['path'])
            if sha256(path) != ref['sha256']:
                raise ValueError('RGB hash mismatch')
            with Image.open(path) as im:
                if im.size != (640, 480) or im.format != 'JPEG':
                    raise ValueError('native RGB mismatch')
                im.verify()
            frames[ref['path']] = ref
    periods = [b-a for a, b in zip(times, times[1:])]
    if not periods or any(abs(x - .1) > .002 for x in periods):
        raise ValueError('recording clock mismatch')
    actual = {str(p.relative_to(root)) for p in (root/'rgb').rglob('*.jpg')}
    if actual != set(frames) or len(frames) != len(observations):
        raise ValueError('unreferenced or missing training frames')
    boundary = result.get('input_audit') or {}
    if any(boundary.get(k) != 0 for k in ('invisible_measurements', 'held_world_reads')):
        raise ValueError('missing or failed teacher input audit')
    if list((root/'review-top').glob('*')):
        raise ValueError('top review output forbidden')
    return {
        'schema': 'ugrp.act12.recording_audit.v1', 'passed': True,
        'raw': str(root), 'result_sha256': sha256(existing(root, 'result.json')),
        'status': result['status'], 'physical_success': result.get('physical_success'),
        'student_rows': len(observations), 'training_frames': len(frames),
        'width': 640, 'height': 480, 'period_s': .1,
        'measured_period_min_s': min(periods), 'measured_period_max_s': max(periods),
        'camera': camera, 'student_fields': sorted(observations[0]),
        'student_privileged_fields': 0, 'input_audit': boundary,
        'rgb_bytes': sum((root/p).stat().st_size for p in frames),
        'run_logical_bytes': sum(p.stat().st_size for p in root.parent.rglob('*') if p.is_file()),
        'evaluation_fields': 'teacher labels and evaluation directories remain separate; not read as observations',
        'training_include': False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = audit(a.raw)
    write_json(a.output, report)
    print(f"PASS {report['student_rows']} rows / {report['training_frames']} native frames")


if __name__ == '__main__':
    main()
