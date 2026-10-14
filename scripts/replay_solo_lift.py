"""Rejudge saved own RGB + issued commands; never starts a simulator."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import cv2

from sim.grasp_act_solo_rgb import SoloLiftObserver
from sim.rgb_lift_evidence import confirm_parts_v2, confirm_parts_v3


def replay(manifest):
    manifest = Path(manifest)
    data = json.loads(manifest.read_text())
    rows = []
    verified = 0
    for run in data['runs']:
        frames = {}
        for tag, sample in run['samples'].items():
            path = manifest.parent/sample['path']
            if hashlib.sha256(path.read_bytes()).hexdigest() != sample['sha256']:
                raise ValueError(f'file hash mismatch: {path}')
            frame = cv2.imread(str(path))
            if frame is None or hashlib.sha256(frame.tobytes()).hexdigest() != sample['pixel_sha256']:
                raise ValueError(f'pixel hash mismatch: {path}')
            frames[tag] = frame
            verified += 1
        before, after, hold = (frames[tag] for tag in ('before_lift', 'lift_complete', 'settled_hold'))
        masks = SoloLiftObserver(run['kind'])._masks
        kwargs = dict(commands=run['commands'], masks=masks, names=(run['kind'],))
        old = confirm_parts_v2(before, after, settled=hold, rule='solo_rgb_lift_v2', **kwargs)
        new = confirm_parts_v3(before, after, settled=hold, rule='solo_rgb_lift_v3', **kwargs)
        control = confirm_parts_v3(before, before, settled=before, rule='solo_rgb_lift_v3', **kwargs)
        rows.append({'run': run['run'], 'kind': run['kind'], 'samples': run['samples'],
                     'v2': old, 'v3': new, 'same_image_control': control})
    failed = [r for r in rows if r['v2']['verdict'] != 'confirmed']
    passed = [r for r in rows if r['v2']['verdict'] == 'confirmed']
    totals = {'N': len(rows), 'verified_images': verified,
              'recovered': sum(r['v3']['verdict'] == 'confirmed' for r in failed), 'failed_N': len(failed),
              'preserved': sum(r['v3']['verdict'] == 'confirmed' for r in passed), 'passed_N': len(passed),
              'same_image_false_positive': sum(r['same_image_control']['verdict'] == 'confirmed' for r in rows),
              'v3_confirmed': sum(r['v3']['verdict'] == 'confirmed' for r in rows),
              'v3_not_confirmed': sum(r['v3']['verdict'] == 'not_confirmed' for r in rows),
              'v3_undetermined': sum(r['v3']['verdict'] == 'undetermined' for r in rows)}
    ready = (totals['N'] == 6 and totals['failed_N'] == totals['recovered'] == 4 and
             totals['passed_N'] == totals['preserved'] == 2 and totals['same_image_false_positive'] == 0)
    root = Path(__file__).resolve().parents[1]
    return {'schema': 'solo4_offline_replay_v1', 'source_sha': data['source_sha'],
            'reference_sha': 'b033e5f914a0d3e221eb77db455d84288104b004',
            'ready': ready, 'scope': 'saved-frame development replay; not new physical success',
            'manifest': str(manifest), 'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'code_sha256': {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in
                            ('sim/rgb_lift_evidence.py', 'sim/grasp_act_solo_rgb.py', 'scripts/replay_solo_lift.py')},
            'totals': totals, 'runs': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('tests/fixtures/solo_rgb_lift_v3/manifest.json'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--require-ready', action='store_true')
    args = parser.parse_args()
    result = replay(args.manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'ready': result['ready'], **result['totals']}))
    return 1 if args.require_ready and not result['ready'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
