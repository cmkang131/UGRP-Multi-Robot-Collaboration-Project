#!/usr/bin/env python3
"""Score saved own RGB frames only: no simulator, renderer, network or learned model.

Manual image polygons are evaluation labels only, never observer arguments.
Example: python scripts/diagnose_owncam_robot_mask.py --output /new/absolute/dir
"""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import opencv_wall_observation as ow  # noqa: E402
from harness import own_image_gates, vision_loc_protocol as vp  # noqa: E402
from harness.vision_pose_source_final import measured_column_model  # noqa: E402

FIXTURE = ROOT / 'tests/fixtures/owncam_robot_mask/manifest.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def obs_bytes(obs):
    return b''.join(getattr(obs, k).tobytes() for k in ('columns',) + vp.OBS_KEYS)


def peer_hits(obs, polygons):
    """Count columns with at least one accepted edge on a visible peer silhouette."""
    hits = []
    for j, u in enumerate(obs.columns):
        for kind, row in ((obs.b_kind[j], obs.b_lo[j]), (obs.t_kind[j], obs.t_lo[j])):
            if kind and any(cv2.pointPolygonTest(np.asarray(p, np.float32),
                                                 (float(u), float(row)), False) >= 0 for p in polygons):
                hits.append(j)
                break
    return hits


def evaluate(manifest=FIXTURE, output=None):
    manifest = Path(manifest)
    raw = manifest.read_bytes()
    doc = json.loads(raw)
    vl, _ = vp.load_vis3()
    gates = own_image_gates.load()
    result = {'schema': 'ugrp.owncam_robot_mask_offline.v1', 'scope': 'exploratory saved RGB, not PF/physical validation',
              'manifest_sha256': digest(raw), 'legacy_function_sha256': digest(inspect.getsource(ow.observations).encode()),
              'gates': gates, 'mask': ow.ROBOT_MASK_CONFIG, 'opencv_version': cv2.__version__,
              'numpy_version': np.__version__, 'model_calls': 0, 'simulation_calls': 0,
              'source_files_sha256': {p: digest((ROOT/p).read_bytes()) for p in
                  ('harness/opencv_wall_observation.py', 'scripts/diagnose_owncam_robot_mask.py')}, 'frames': []}
    if output is not None:
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
    for f in doc['frames']:
        data = (manifest.parent/f['file']).read_bytes()
        if digest(data) != f['sha256']:
            raise ValueError(f"frame hash mismatch: {f['file']}")
        bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        vp.check_frame(bgr)
        camera = measured_column_model(vl.mp, f['camera_record'], vl.mp.column_positions(96, 2))
        before = ow.observations(vl, bgr, camera, gates['values'])
        off = ow.masked_observations(vl, bgr, camera, gates['values'], robot_mask=None)
        after = ow.masked_observations(vl, bgr, camera, gates['values'], robot_mask=ow.ROBOT_MASK)
        # Only now read the manual labels: they cannot influence either observer.
        polygons = f['peer_polygons_undistorted']
        bad_before, bad_after = peer_hits(before, polygons), peer_hits(after, polygons)
        removed = np.flatnonzero(before.informative & ~after.informative).tolist()
        result['frames'].append({'id': f['id'], 'file': f['file'], 'peer_visible': f['peer_visible'],
            'sha256': f['sha256'], 'off_byte_identical': obs_bytes(before) == obs_bytes(off),
            'before_sha256': digest(obs_bytes(before)), 'off_sha256': digest(obs_bytes(off)),
            'after_sha256': digest(obs_bytes(after)), 'before_columns': int(before.informative.sum()),
            'after_columns': int(after.informative.sum()), 'peer_false_before': len(bad_before),
            'peer_false_after': len(bad_after), 'removed_columns': len(removed),
            'removed_not_labelled_peer': len(set(removed)-set(bad_before)),
            'false_edges_before': [[int(before.columns[j]), float(before.b_lo[j])] for j in bad_before]})
        if output is not None:
            img = vl.mp.undistort(bgr)
            excluded = ow.robot_occluded_columns(img)
            img[:, excluded] = (.6*img[:, excluded] + .4*np.array([180, 0, 0])).astype(np.uint8)
            for polygon in polygons:
                cv2.polylines(img, [np.asarray(polygon, np.int32)], True, (255, 255, 255), 1)
            for j, u in enumerate(before.columns):
                if before.b_kind[j]:
                    color = (0, 220, 0) if after.b_kind[j] else (0, 0, 255)
                    cv2.circle(img, (int(u), int(round(before.b_lo[j]))), 3, color, -1)
            cv2.imwrite(str(output/f"frame_{f['id']:02d}.png"), img)
    result['groups'] = {}
    for name, visible in (('peer_visible', True), ('no_peer_visible', False)):
        rows = [r for r in result['frames'] if r['peer_visible'] is visible]
        result['groups'][name] = {'frames': len(rows), 'detector_columns': 96*len(rows),
            'frames_with_false_before': sum(r['peer_false_before'] > 0 for r in rows),
            'frames_with_false_after': sum(r['peer_false_after'] > 0 for r in rows),
            **{k: sum(r[k] for r in rows) for k in ('before_columns', 'after_columns', 'peer_false_before',
                'peer_false_after', 'removed_columns', 'removed_not_labelled_peer')}}
    result['all_off_byte_identical'] = all(r['off_byte_identical'] for r in result['frames'])
    if output is not None:
        (output/'result.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=FIXTURE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.manifest, args.output)
    print(json.dumps({'groups': result['groups'], 'all_off_byte_identical': result['all_off_byte_identical']}, indent=2))
