"""Post-seal wall geometry audit on gcp5; no estimator/admission changes.

Separate the saved RGB->body scan projection from the additional pose/map
placement error. Ground truth is read only here, after verifying predictions.
Nearest authored wall distance is descriptive, not correspondence correctness.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('GCP5_ONLY')
    sys.path.insert(0, str(a.source))
    import numpy as np
    from harness.e2e_rgb_vo import compose, between
    from harness.mapbuild_static_registration import wall_segments
    from harness.self_map_csm import sample_segments
    from harness.self_odom_grid import transform

    def read(p): return json.loads(p.read_text())
    def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
    seal = read(a.prediction/'prediction-seal.json')
    for name, h in seal['prediction_sha256'].items():
        if sha(a.prediction/name) != h:
            raise ValueError('PREDICTION_SEAL_CHANGED')
    rows = read(a.input/'online-trajectory.json')
    scans = read(a.input/'scans.json')
    gt = read(a.input/'eval-only.json')['frames']
    ref = np.asarray(wall_segments(read(a.input/'static-map.json')))
    start = compose(gt[0]['pose'], between(rows[0]['corrected_pose'], np.zeros(3)))

    def distances(points):
        u, v = ref[:, 0], ref[:, 1]-ref[:, 0]
        q = np.clip(np.einsum('nsi,si->ns', points[:, None]-u, v) /
                    np.sum(v*v, axis=1), 0, 1)
        feet = u+q[..., None]*v
        return np.linalg.norm(points[:, None]-feet, axis=-1).min(1)

    def stats(x):
        return dict(n=len(x), median_m=float(np.median(x)),
                    p95_m=float(np.percentile(x, 95)), rms_m=float(np.sqrt(np.mean(x*x))))

    records = []
    for row, scan, truth in zip(rows, scans, gt):
        e = row['map_event']
        if not e['attempted']:
            continue
        points = sample_segments(scan['segments'])
        poses = dict(true_body=truth['pose'],
                     prior_body=compose(start, e['prior_pose']),
                     inserted_body=compose(start, row['corrected_pose']))
        match = e['self_match']
        rank = len(match.get('observable_axes_scaled', [])) if match else None
        records.append(dict(t=row['t'], accepted=e['accepted'], reason=e['reason'],
                            observable_rank=rank,
                            wall_distance={k: stats(distances(transform(points, p))) for k, p in poses.items()}))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(raw=str(a.input), records=records, truth_to_control=0,
                  threshold_fitting=0, note='true_body isolates nominal scan projection; prior/inserted also include pose error; nearest distances do not prove a correct wall identity',
                  source_sha256={str(p): sha(p) for p in [Path(__file__), a.prediction/'prediction-seal.json', a.input/'eval-only.json', a.input/'static-map.json']},
                  reproduction=sys.argv)
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps([r for r in records if r['accepted'] and 25 <= r['t'] <= 29]))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'prediction', 'source', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    main(p.parse_args())
