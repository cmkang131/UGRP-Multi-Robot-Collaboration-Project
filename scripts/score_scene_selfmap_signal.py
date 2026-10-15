"""Score actual wall-column/LK inputs on saved static pairs; NO new render."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import platform
import cv2
import numpy as np

from scripts.summarize_scene_tex3 import read, write, dist, sha
from scripts.probe_scene_tex2 import pose_pwm_mode


def score(root, output):
    from harness.e2e_rgb_vo import ground_pair
    from harness.active_wall_vision import modules
    from harness.active_camera import transform
    from harness.zone_pair_highpose import HIGH
    from scripts.zone_teacher import FOLDED
    mp, hfw, _ = modules()
    rows = []
    for entry in read(root/'index.json'):
        r = read(root/entry['record'])
        pwm = FOLDED if pose_pwm_mode(r['pose']) == 'FOLDED' else {**HIGH, 1: 1500}
        stem = r['case']+'--'+r['material']+'--'+r['quality']
        after = cv2.imread(str(root/(stem+'--next.png')))
        try:
            origin, rotation = transform(pwm)
        except ValueError as exc:
            # Preserve the existing loaded/unknown-load calibration guard.
            # A static HIGH fixture must not silently become an unloaded FK.
            for enc in ('png', 'jpeg90'):
                rows.append({'case': r['case'], 'pose': r['pose'], 'material': r['material'], 'quality': r['quality'],
                    'encoding': enc, 'wall_contact_columns': None, 'linked_wall_segments': None,
                    'LK_status': 'UNQUALIFIED_CAMERA:'+str(exc), 'LK_tracks': None,
                    'LK_homography_inliers': None, 'LK_rigid_inliers': None})
            continue
        cm = mp.ColumnModel(tuple(sorted(pwm.items())), 0., mp.column_positions(96, 2), camera_transform=(origin, rotation))
        params = dict(floor_patch_max_m=.81, run_step_window=3, top_edge_px=4)
        for enc in ('png', 'jpeg90'):
            before = cv2.imread(str(root/r['encodings'][enc]['file']))
            next_image = after
            if enc == 'jpeg90':
                next_image = cv2.imdecode(cv2.imencode('.jpg', after, [cv2.IMWRITE_JPEG_QUALITY, 90])[1], cv2.IMREAD_COLOR)
            cv2.setRNGSeed(0)  # reproducible offline estimator randomness, not an admission threshold
            flow = ground_pair(cv2.cvtColor(before, cv2.COLOR_BGR2RGB), cv2.cvtColor(next_image, cv2.COLOR_BGR2RGB),
                               pwm, vo_floor_mask='homography_v1')
            scan = hfw.detect(mp.undistort(before), cm, params=params, loaded=False)
            segments = hfw.link_segments(scan, params)
            rows.append({'case': r['case'], 'pose': r['pose'], 'material': r['material'], 'quality': r['quality'], 'encoding': enc,
                'wall_contact_columns': int(np.isfinite(scan['vb'][:, 0]).sum()), 'linked_wall_segments': len(segments),
                'LK_status': flow['status'], 'LK_tracks': int(flow.get('tracks', 0)),
                'LK_homography_inliers': int(flow.get('homography_inliers', 0)), 'LK_rigid_inliers': int(flow.get('inliers', 0))})
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r['material'], r['quality'], r['encoding'])].append(r)
    summary = []
    for (material, quality, enc), rr in grouped.items():
        summary.append({'material': material, 'quality': quality, 'encoding': enc,
            'statuses': dict(Counter(r['LK_status'] for r in rr)),
            **{k: dist(r[k] for r in rr) for k in ('wall_contact_columns', 'linked_wall_segments', 'LK_tracks', 'LK_homography_inliers', 'LK_rigid_inliers')}})
    output.mkdir(parents=True, exist_ok=False)
    detail = write(output/'frames.json', rows)
    write(output/'summary.json', {'scope': 'same wall-column/LK signal as selfmap4 observe/PlaneFlow; no pose accuracy or dynamic success claim',
        'input': str(root), 'frames': len(rows)//2, 'detail_file': detail.name,
        'camera_qualification': 'legacy own-command camera geometry; v3 metric calibration unverified',
        'source_sha256': {str(p): sha(p) for p in [Path(__file__), Path('harness/active_camera.py'), Path('harness/active_wall_vision.py'), Path('harness/e2e_rgb_vo.py')]},
        'results': summary})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not platform.node().startswith('ugrp-sim-gcp2'):
        p.error('gcp2 analysis only')
    score(a.input, a.output)
