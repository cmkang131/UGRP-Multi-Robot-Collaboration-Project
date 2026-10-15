"""PNG numerical stress audit of non-colour own-image consumers; no MuJoCo.

Analytic pinhole plane sampling is an approximation, not a camera render or a
textured-profile calibration. No runtime detector, gate or calibration is edited.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image

from harness import own_image_gates, opencv_wall_observation as ow
from harness import vision_loc_protocol as vp
from harness.zone_pair_highpose_frame_gate import FrameGate
from sim.natural_scene_texture import ASSETS

ROOT = Path(__file__).resolve().parents[1]
SERVO = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


def read_assets(directory):
    raw = (Path(directory)/'manifest.json').read_bytes()
    record = json.loads(raw)
    for entry in record['images'].values():
        if hashlib.sha256((Path(directory)/entry['file']).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('audit input asset hash mismatch')
    return record, hashlib.sha256(raw).hexdigest()


def wall_windows(directory, record):
    """All interior 40x7 windows, raw pixels AND horizontal strip-mean std.

    The latter follows detect_boundaries' variance convention; the former is
    conservative and comparable to the reviewer's rough PNG calculation.
    """
    out = {k: {'accepted': 0, 'N': 0, 'std_max': 0.} for k in ('raw_40x7', 'detector_strip_40x7')}
    for key, entry in record['images'].items():
        if key == 'floor':
            continue
        gray = np.asarray(Image.open(Path(directory)/entry['file']))[..., 0].astype(float)
        strip = cv2.boxFilter(gray, -1, (7, 1), normalize=True)
        for name, value, square, kernel in (
                ('raw_40x7', gray, gray*gray, (7, 40)),
                ('detector_strip_40x7', strip, strip*strip, (1, 40))):
            mean = cv2.boxFilter(value, -1, kernel, normalize=True)[20:-20, 3:-3]
            var = cv2.boxFilter(square, -1, kernel, normalize=True)[20:-20, 3:-3] - mean*mean
            std = np.sqrt(np.maximum(var, 0))
            row = out[name]
            row['accepted'] += int((std <= 3).sum())
            row['N'] += int(std.size)
            row['std_max'] = max(row['std_max'], float(std.max()))
    for row in out.values():
        row['fraction'] = row['accepted']/row['N']
    return out


def sample(rgb, u, v):
    return cv2.remap(rgb, (np.clip(u, 0, 1)*(rgb.shape[1]-1)).astype(np.float32),
                     (np.clip(v, 0, 1)*(rgb.shape[0]-1)).astype(np.float32), cv2.INTER_LINEAR)


def approximate_view(mp, camera, floor, wall, distance, gain, gradient, *, baseline=False):
    """Undistorted analytic floor + 0.4m wall; legacy probe camera geometry.

    A wall face spans 6.5m horizontally. No robot/cargo/paint, fisheye lens,
    shadows, material BRDF, real light model, cube orientation or occlusion.
    """
    y, x = np.indices((480, 640), dtype=float)
    rays = np.stack([x, y, np.ones_like(x)], -1) @ mp.K_INV.T @ camera._rot.T
    origin = camera.origin
    with np.errstate(divide='ignore', invalid='ignore'):
        tf = np.where(rays[..., 2] < 0, -origin[2]/rays[..., 2], np.inf)
        tw = np.where(rays[..., 0] > 0, distance/rays[..., 0], np.inf)
    # Finite sampling coordinates even for rays which do not meet a plane.
    pf = origin + np.where(np.isfinite(tf), tf, 0)[..., None]*rays
    pw = origin + np.where(np.isfinite(tw), tw, 0)[..., None]*rays
    wall_mask = np.isfinite(tw) & (pw[..., 2] >= 0) & (pw[..., 2] <= .4) & (tw < tf)
    floor_mask = np.isfinite(tf) & ~wall_mask & (np.abs(pf[..., 0]) < 8) & (np.abs(pf[..., 1]) < 8)
    rgb = np.full((480, 640, 3), 190, np.uint8)
    if baseline:
        # floor_light_v1 authored RGB endpoints, approximate checker placement.
        checker = ((np.floor(pf[..., 0]*2)+np.floor(pf[..., 1]*2)) % 2).astype(bool)
        floor_pixels = np.where(checker[..., None], [158, 156, 150], [92, 89, 87]).astype(np.uint8)
        wall_pixels = np.full_like(rgb, [59, 71, 84])  # authored .23 .28 .33
    else:
        floor_pixels = sample(floor, (pf[..., 0]+8)/16, 1-(pf[..., 1]+8)/16)
        wall_pixels = sample(wall, .5+pw[..., 1]/6.5, 1-pw[..., 2]/.4)
    rgb[floor_mask] = floor_pixels[floor_mask]
    rgb[wall_mask] = wall_pixels[wall_mask]
    rgb = np.clip(np.rint(rgb*gain*(1+gradient*(y/479-.5))[..., None]), 0, 255).astype(np.uint8)
    expected = np.full(len(camera.columns), np.nan)
    for j, u in enumerate(camera.columns):
        rows = np.flatnonzero(wall_mask[:, u])
        if len(rows) >= 12 and rows[-1] < 470:
            expected[j] = rows[-1]+.5
    return rgb[..., ::-1].copy(), expected


def column_score(bottom, expected):
    found = np.isfinite(bottom)
    visible = np.isfinite(expected)
    correct = found & visible & (np.abs(bottom-expected) < 4)
    return {'accepted': int(found.sum()), 'N': len(expected),
            'correct': int(correct.sum()), 'visible_N': int(visible.sum()),
            'false': int((found & ~correct).sum())}


def frame_score(jpeg, gate):
    obs = {'camera': 'robot_cam', 'robot_id': 'r1', 'frame_id': 1, 'sim_time': 9.95,
           'image': base64.b64encode(jpeg).decode(), 'sha256': hashlib.sha256(jpeg).hexdigest()}
    verdict, measures = gate.assess(obs, 'r1', 10., ob=True)
    return {'valid_frame': gate.valid_frame(obs, 'r1', 10.), 'valid_frame_ob': verdict == 'valid',
            'measures': measures, 'jpeg_sha256': obs['sha256']}


def audit(reference_assets, output):
    current, digest = read_assets(ASSETS)
    original, old_digest = read_assets(reference_assets)
    vl, _ = vp.load_vis3()
    mp = vl.mp
    camera = mp.column_model(SERVO, -.02, mp.column_positions(96))
    # Analytic inputs are already undistorted: call the real detector/observer,
    # adapting only the image coordinate convention, not their decisions.
    adapter = SimpleNamespace(mp=SimpleNamespace(undistort=lambda bgr: bgr,
                              detect_boundaries=mp.detect_boundaries), EDGE=vl.EDGE, ColumnObs=vl.ColumnObs)
    gates = own_image_gates.load()
    gate = FrameGate.from_values(gates['values'])
    floor = np.asarray(Image.open(ASSETS/'floor.png').convert('RGB'))
    keys = [k for k in current['images'] if k.endswith('_fileup')][:3]
    rows = []
    output = Path(output)
    raw_dir = output.with_name(output.stem+'-inputs')
    raw_dir.mkdir(exist_ok=True)
    for key in keys:
        for distance in (.75, 1.5):
            for light, gain, gradient in (('dim', .75, 0.), ('nominal', 1., 0.), ('bright_gradient', 1.25, .06)):
                case = f'{key}-{distance}-{light}'
                for arm, directory in (('floor_light_v1_approx', None), ('original_texture', reference_assets),
                                       ('revised_texture', ASSETS), ('flat_texture_control', None)):
                    wall = np.full((512, 512, 3), current['wall_mean_value'], np.uint8) if directory is None else np.asarray(
                        Image.open(Path(directory)/current['images'][key]['file']).convert('RGB'))
                    bgr, expected = approximate_view(mp, camera, floor, wall, distance, gain, gradient,
                                                   baseline=arm == 'floor_light_v1_approx')
                    jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
                    scores = {}
                    for encoding, image in (('raw_png', bgr), ('jpeg_q90', cv2.imdecode(
                            np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR))):
                        scan = mp.detect_boundaries(image, camera, ow.DETECTOR)
                        # GT chooses a candidate for scoring only; it is never
                        # passed to the observer's actual single-candidate filter.
                        diff = np.abs(scan.vb-expected[:, None])
                        candidates = np.isfinite(scan.vb)
                        chosen = np.argmin(np.where(candidates & np.isfinite(diff), diff, np.inf), axis=1)
                        bottom = scan.vb[np.arange(len(expected)), chosen]
                        observed = ow.observations(adapter, image, camera, gates['values'])
                        scores[encoding] = {'detect_boundaries': column_score(bottom, expected),
                                            'opencv_wall_observation': column_score(observed.b_lo, expected)}
                    image_path = raw_dir/f'{case}-{arm}.png'
                    Image.fromarray(bgr[..., ::-1]).save(image_path)
                    image_path.with_suffix('.jpg').write_bytes(jpeg)
                    rows.append({'case': case, 'arm': arm, 'png_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
                                 'encodings': scores, 'own_image_gates': frame_score(jpeg, gate)})
    summary = {}
    for arm in sorted({r['arm'] for r in rows}):
        group = [r for r in rows if r['arm'] == arm]
        summary[arm] = {'frames': len(group), 'encodings': {encoding: {consumer: {
            k: sum(r['encodings'][encoding][consumer][k] for r in group)
            for k in ('accepted', 'N', 'correct', 'visible_N', 'false')}
            for consumer in ('detect_boundaries', 'opencv_wall_observation')}
            for encoding in ('raw_png', 'jpeg_q90')},
            'own_image_gates': {name: sum(r['own_image_gates'][name] for r in group)
                               for name in ('valid_frame', 'valid_frame_ob')}}
    paths = ['scripts/audit_scene_texture_own_image.py', 'harness/opencv_wall_observation.py',
             'harness/own_image_gates.py', 'harness/zone_pair_highpose_frame_gate.py',
             'configs/calibration/own_image_gates_floor_light_v1.json',
             'experiments/2026-09-26-vision-loc/vision_loc.py',
             'experiments/2026-09-26-vision-loc/calibration_train.json',
             'experiments/2026-09-26-markerless-probe/markerless_probe.py']
    result = {'schema': 'ugrp.scene_texture_own_image_audit.v1', 'scope': __doc__,
              'environment': {'python': sys.version.split()[0], 'opencv': cv2.__version__, 'numpy': np.__version__},
              'camera_verified': False, 'calibration_transferred': False, 'ready_for_execution': False,
              'current_manifest_sha256': digest, 'original_manifest_sha256': old_digest,
              'original_assets': str(reference_assets), 'raw_inputs': str(raw_dir),
              'source_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
              'approximation': approximate_view.__doc__, 'issued_servo': SERVO, 'elevation_bias_rad': -.02,
              'wall_height_m': .4, 'jpeg_quality': 90, 'jpeg_scope': 'numerical stress approximation; exact runtime codec remains a GCP gate',
              'sampled_wall_faces': keys, 'detector_scoring': 'any correct candidate per column; observer uses actual single-candidate rule',
              'detector_defaults': mp.DEFAULT_DETECTOR,
              'observer_detector': ow.DETECTOR, 'gates': gates,
              'wall_windows': {'original': wall_windows(reference_assets, original), 'revised': wall_windows(ASSETS, current)},
              'controls': {str(v): frame_score(cv2.imencode('.jpg', np.full((480, 640, 3), v, np.uint8),
                  [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes(), gate) for v in (0, 128)},
              'summary': summary, 'frames': rows,
              'unverified_consumers': ['harness/wall_floor_lorigo.py', 'harness/wall_floor_ulrich.py', 'vendor/lu_vp'],
              'remaining': 'GCP paired raw own PNG/runtime JPEG, correct/false columns and gate pass n/N; actual optics/materials/occluders; texture-specific calibration if required'}
    frame_path = output.with_name(output.stem+'-frames.json')
    frame_path.write_text(json.dumps(result.pop('frames'), separators=(',', ':'))+'\n')
    result['frames'] = {'path': str(frame_path), 'sha256': hashlib.sha256(frame_path.read_bytes()).hexdigest()}
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'summary': summary, 'wall_windows': result['wall_windows'], 'bytes': output.stat().st_size}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.reference_assets, args.output)
