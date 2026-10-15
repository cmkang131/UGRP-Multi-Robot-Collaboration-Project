"""Saved-image gcp2 audit of the exact selfmap boundary/LK inputs, no renderer.

Admission comparisons have zero slack: user asked for no floor regressions and
v1 median/p10 column preservation. Quantile levels are reporting coordinates,
not fitted acceptance thresholds. No detector constants are changed here.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import platform
import sys
import cv2
import numpy as np
from PIL import Image, ImageDraw
from scripts.summarize_scene_tex3 import read, write, sha, dist
from scripts.probe_scene_tex2 import pose_pwm_mode, mask_score

ENCODINGS = ('png', 'jpeg90', 'pil82')
BASE = ('floor_light_textured_v1', 'native')


def distribution(values):
    values = list(values)
    out = dist(values)
    valid = [float(x) for x in values if x is not None]
    out['p10'] = float(np.percentile(valid, 10)) if valid else None
    return out


def colour_partition(bgr):
    # Exact authored channel order: v1 floor R=G=B, new cool wall B>R.
    # S20 and V60/225 are existing all-hue paint/dark/white exclusions, not
    # values fitted to evaluation masks. Applied identically to all arms.
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    eligible = (hsv[..., 1] < 20) & (hsv[..., 2] > 60) & (hsv[..., 2] < 225)
    cool = bgr[..., 0] > bgr[..., 2]
    return {'wall': eligible & cool, 'floor': eligible & ~cool}


def selfmap_metrics(before, after, pwm, masks):
    from harness.e2e_rgb_vo import ground_pair
    from harness.active_wall_vision import modules
    from harness.active_camera import transform
    mp, hfw, _ = modules()
    try:
        origin, rotation = transform(pwm)
    except ValueError as exc:
        return {'qualified': False, 'status': str(exc), 'columns': None, 'residuals_px': [],
                'false_columns': None, 'LK_tracks': None, 'LK_inliers': None}
    cm = mp.ColumnModel(tuple(sorted(pwm.items())), 0., mp.column_positions(96, 2), camera_transform=(origin, rotation))
    params = dict(floor_patch_max_m=.81, run_step_window=3, top_edge_px=4)
    und = mp.undistort(before)
    scan = hfw.detect(und, cm, params=params, loaded=False)
    und_masks = {k: cv2.remap(v.astype(np.uint8), mp._UNDISTORT[0], mp._UNDISTORT[1],
                 cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT) > 0 for k, v in masks.items()}
    residuals, false_columns, truth_columns = [], 0, 0
    for j, u in enumerate(cm.columns):
        boundaries = np.flatnonzero(und_masks['wall'][:-1, u] & und_masks['floor'][1:, u]) + .5
        truth_columns += bool(len(boundaries))
        value = scan['vb'][j, 0]
        if np.isfinite(value):
            if len(boundaries): residuals.append(float(np.min(abs(value-boundaries))))
            else: false_columns += 1
    cv2.setRNGSeed(0)
    flow = ground_pair(cv2.cvtColor(before, cv2.COLOR_BGR2RGB), cv2.cvtColor(after, cv2.COLOR_BGR2RGB),
                       pwm, vo_floor_mask='homography_v1')
    return {'qualified': True, 'status': flow['status'], 'columns': int(np.isfinite(scan['vb'][:, 0]).sum()),
            'residuals_px': residuals, 'false_columns': false_columns, 'visible_boundary_columns': truth_columns,
            'LK_tracks': int(flow.get('tracks', 0)), 'LK_inliers': int(flow.get('inliers', 0)),
            'segments': len(hfw.link_segments(scan, params))}


def image_path(root, row, enc):
    return root/row['encodings'][enc]['file']


def boundary_ok(rows, reference, enc):
    rr = [r['signal'][enc] for r in rows if r['signal'][enc]['qualified']]
    bb = [reference[r['case']]['signal'][enc] for r in rows if r['signal'][enc]['qualified']]
    a, b = [r['columns'] for r in rr], [r['columns'] for r in bb]
    ae = [v for r in rr for v in r['residuals_px']]
    be = [v for r in bb for v in r['residuals_px']]
    # An empty/short boundary error sample cannot win by failing to detect.
    errors_ok = bool(ae and be) and len(ae) >= len(be) and bool(np.all(
        np.percentile(ae, np.arange(101)) <= np.percentile(be, np.arange(101))))
    cols_ok = bool(a and b) and all(np.percentile(a, q) >= np.percentile(b, q) for q in (10, 50))
    false_ok = sum(r['false_columns'] for r in rr) <= sum(r['false_columns'] for r in bb)
    return {'pass': bool(cols_ok and errors_ok and false_ok), 'columns_pass': bool(cols_ok),
            'error_distribution_pass': bool(errors_ok), 'false_columns_pass': bool(false_ok),
            'columns': distribution(a), 'v1_columns': distribution(b),
            'errors_px': distribution(ae), 'v1_errors_px': distribution(be),
            'false_columns': sum(r['false_columns'] for r in rr),
            'v1_false_columns': sum(r['false_columns'] for r in bb)}


def score(inputs, output):
    from harness.zone_pair_highpose import HIGH
    from scripts.zone_teacher import FOLDED
    output.mkdir(parents=True, exist_ok=False)
    allrows, sources, modelrows = [], [], []
    seen = set()
    for root in inputs:
        meta = read(root/'summary.json')
        if meta['status'] != 'MEASURED': raise ValueError('INCOMPLETE_SOURCE:'+str(root))
        hashes = read(root/'SHA256SUMS.json')
        bad = [f for f, h in hashes.items() if not (root/f).is_file() or sha(root/f) != h]
        if bad: raise ValueError('RAW_HASH_MISMATCH:'+str(bad[:3]))
        sources.append({'path': str(root), 'source_sha': meta['source_sha'], 'verified_files': len(hashes),
                        'summary_sha256': sha(root/'summary.json')})
        modelrows.extend(read(root/'models.json'))
        for item in read(root/'index.json'):
            key = (item['case'], item['material'], item['quality'])
            if key in seen: continue
            # Keep original v1 and v3, not unrelated v2 from prior rounds.
            if not item['material'].startswith('walls_floor_contrast_v4_') and (item['material'], item['quality']) not in (
                    BASE, ('walls_floor_textured_v3', 'native'), ('walls_floor_textured_v3', 'wall_no_mip_v1')):
                continue
            seen.add(key)
            row = read(root/item['record'])
            row['raw_root'] = str(root)
            stem = row['case']+'--'+row['material']+'--'+row['quality']
            masks = {s: cv2.imread(str(root/(stem+'--mask-'+s+'.png')), 0)>0 for s in ('floor', 'wall')}
            after = cv2.imread(str(root/(stem+'--next.png')))
            pwm = FOLDED if pose_pwm_mode(row['pose']) == 'FOLDED' else {**HIGH, 1: 1500}
            row['signal'], row['colour_iou'], row['colour_separation'] = {}, {}, {}
            for enc in ENCODINGS:
                before = cv2.imread(str(image_path(root, row, enc)))
                prediction = colour_partition(before)
                row['colour_iou'][enc] = {s: mask_score(prediction[s], masks[s]) for s in masks}
                if masks['floor'].any() and masks['wall'].any():
                    lab = cv2.cvtColor(before, cv2.COLOR_BGR2LAB).astype(float)
                    centres = [np.median(lab[masks[s]], axis=0) for s in ('wall', 'floor')]
                    row['colour_separation'][enc] = {'delta_L': float(abs(centres[0][0]-centres[1][0])),
                        'delta_E76_opencv8': float(np.linalg.norm(centres[0]-centres[1]))}
                else: row['colour_separation'][enc] = None
                if enc == 'pil82': continue
                from scripts.probe_scene_tex3 import jpeg
                next_image = after if enc == 'png' else jpeg(after, 90)[0]
                row['signal'][enc] = selfmap_metrics(before, next_image, pwm, masks)
            allrows.append(row)
        print('scored', str(root), len(allrows), flush=True)
    reference = {r['case']: r for r in allrows if (r['material'], r['quality']) == BASE}
    if len(reference) != 88: raise ValueError('BASELINE_88_MISSING')
    modelref = {r['map']: r for r in modelrows if (r['material'], r['quality']) == BASE}
    grouped = defaultdict(list)
    for r in allrows: grouped[(r['material'], r['quality'])].append(r)
    reports, rejection = [], []
    for (material, quality), rows in grouped.items():
        if len(rows) != 88 or set(r['case'] for r in rows) != set(reference): raise ValueError('POSE_SET_MISMATCH')
        if any(r['qpos_sha256'] != reference[r['case']]['qpos_sha256'] for r in rows): raise ValueError('QPOS_MISMATCH')
        models = [m for m in modelrows if (m['material'], m['quality']) == (material, quality)]
        parity = bool(models) and all((m['physics_sha256'], m['camera_sha256']) ==
                    (modelref[m['map']]['physics_sha256'], modelref[m['map']]['camera_sha256']) for m in models)
        bycase = []
        for r in rows:
            b = reference[r['case']]
            detector = all(r['encodings'][e]['semantic']['box_counts'] == b['encodings'][e]['semantic']['box_counts']
                and r['encodings'][e]['semantic']['detectors']['beam_legacy_dark_band_v2'] ==
                    b['encodings'][e]['semantic']['detectors']['beam_legacy_dark_band_v2'] for e in ENCODINGS)
            intrusions, support, floor_features, floor_matches, lk = [], [], [], [], []
            for e in ENCODINGS:
                aenc, benc = r['encodings'][e], b['encodings'][e]
                for label, surfaces in aenc['intrusions'].items():
                    for surface, n in surfaces.items():
                        old = benc['intrusions'].get(label, {}).get(surface, 0)
                        if n > old: intrusions.append([e, label, surface, old, n])
                for label, targets in benc['target_support'].items():
                    for target, n in targets.items():
                        new = aenc['target_support'].get(label, {}).get(target, 0)
                        if new < n: support.append([e, label, target, n, new])
                for f in ('orb20', 'orb7', 'interior20', 'interior7'):
                    a, v = aenc['surfaces']['floor'][f], benc['surfaces']['floor'][f]
                    if a < v: floor_features.append([e, f, v, a])
                for f in ('floor20', 'floor7'):
                    a, v = r['matches'][e][f]['mutual_ratio_matches'], b['matches'][e][f]['mutual_ratio_matches']
                    if a < v: floor_matches.append([e, f, v, a])
            for e in ('png', 'jpeg90'):
                for f in ('LK_tracks', 'LK_inliers'):
                    a, v = r['signal'][e][f], b['signal'][e][f]
                    if v is not None and (a is None or a < v): lk.append([e, f, v, a])
            bycase.append({'case': r['case'], 'detector': detector, 'intrusions': intrusions, 'support': support,
                           'floor_features': floor_features, 'floor_matches': floor_matches, 'LK': lk})
        boundary = {e: boundary_ok(rows, reference, e) for e in ('png', 'jpeg90')}
        stages, alive = [], list(bycase)
        tests = [('same_88_pose_physics_camera', lambda r: parity),
                 ('existing_detectors_png_jpeg_pil', lambda r: r['detector']),
                 ('colour_no_new_intrusion_or_support_loss', lambda r: not r['intrusions'] and not r['support']),
                 ('selfmap_columns_and_error_distribution', lambda r: all(v['pass'] for v in boundary.values())),
                 ('floor_features_every_pose', lambda r: not r['floor_features']),
                 ('floor_matching_and_LK_every_pose', lambda r: not r['floor_matches'] and not r['LK'])]
        for name, check in tests:
            failed = [r for r in alive if not check(r)]
            stages.append({'stage': name, 'input_n': len(alive), 'cumulative_pass_n': len(alive)-len(failed),
                           'rejected_n': len(failed), 'rejections': [{'case': r['case'], 'category': name.upper(),
                           'blocking_object': 'wall/floor visual material; existing colour/selfmap input',
                           'minimum_gap_m': None, 'minimum_gap_reason': 'static RGB audit; not a collision clearance gate',
                           'reason': 'paired v1 zero-regression requirement; details in case-metrics'} for r in failed]})
            alive = [r for r in alive if check(r)]
        report = {'material': material, 'quality': quality, 'frames': len(rows), 'encoded_frames': 264,
            'ready': len(alive) == 88, 'physics_camera_parity': parity, 'boundary': boundary,
            'detector_equal': {e: sum(r['encodings'][e]['semantic']['box_counts'] == reference[r['case']]['encodings'][e]['semantic']['box_counts'] for r in rows) for e in ENCODINGS},
            'regression_frames': {k: sum(bool(r[k]) for r in bycase) for k in ('intrusions', 'support', 'floor_features', 'floor_matches', 'LK')},
            'floor_features': {e: {f: distribution(r['encodings'][e]['surfaces']['floor'][f] for r in rows) for f in ('orb20', 'orb7', 'interior20', 'interior7')} for e in ENCODINGS},
            'drive_floor_orb20': {e: distribution(r['encodings'][e]['surfaces']['floor']['orb20'] for r in rows if r['pose'] == 'drive') for e in ENCODINGS},
            'floor_matching': {e: {f: distribution(r['matches'][e][f]['mutual_ratio_matches'] for r in rows) for f in ('floor20', 'floor7')} for e in ENCODINGS},
            'wall_orb_record_only': {e: distribution(r['encodings'][e]['surfaces']['wall']['orb20'] for r in rows) for e in ENCODINGS},
            'wall_occluded_scene_limit': {'n': sum(r['pose']=='high_beam_peer_occluded' for r in rows),
                 'wall_visible_n': sum(r['pose']=='high_beam_peer_occluded' and r['encodings']['png']['surfaces']['wall']['pixels']>0 for r in rows)},
            'colour_iou': {e: {s: distribution(r['colour_iou'][e][s]['iou'] for r in rows) for s in ('wall', 'floor')} for e in ENCODINGS},
            'colour_separation': {e: {f: distribution(r['colour_separation'][e][f] if r['colour_separation'][e] else None for r in rows) for f in ('delta_L', 'delta_E76_opencv8')} for e in ENCODINGS}}
        name = material+'--'+quality
        write(output/(name+'-cases.json'), bycase)
        write(output/(name+'-signals.json'), [{'case': r['case'], 'signal': r['signal'], 'iou': r['colour_iou']} for r in rows])
        write(output/(name+'.json'), report)
        reports.append(report)
        rejection.append({'material': material, 'quality': quality, 'stages': stages,
                          'independent_failures': report['regression_frames'], 'details': name+'-cases.json'})
    write(output/'rejection-table.json', {'arms': rejection, 'sources': sources,
          'reproduction_command': [sys.executable, '-m', 'scripts.score_scene_tex4', *sys.argv[1:]],
          'threshold_basis': 'user 2026-10-16: v1 zero floor regression; columns median/p10 >= v1; error distribution <= v1; no new slack',
          'boundary_exclusions': 'HIGH/unknown-load guard retained; no camera calibration override'})
    write(output/'summary.json', {'schema': 'ugrp.scenetex4.static.v1', 'status': 'MEASURED', 'sources': sources,
          'frames': len(allrows), 'encoded_frames': len(allrows)*3, 'reports': reports,
          'physics_steps': 0, 'model_calls': 0, 'scope': 'static SIM0 fixtures plus one-pixel-angle yaw pairs; no localization/task/physical success',
          'analysis_sha256': sha(Path(__file__)), 'classifier': 'colour_partition: identical channel-order rule for all arms; not a controller',
          'decision': 'READY' if any(r['ready'] for r in reports if r['material'].startswith('walls_floor_contrast_v4_')) else 'NOT_READY'})
    # Same poses in every column; generated on gcp2, fetched as image files only.
    select = [r for r in allrows if (r['material'], r['quality']) == BASE and r['robot']=='r1' and r['view']==0
              and r['pose'] in ('drive', 'box_palette', 'high_beam_peer_occluded')][:6]
    keys = list(grouped)
    sheet = Image.new('RGB', (320*len(keys), 270*len(select)), 'white')
    draw = ImageDraw.Draw(sheet)
    for y, base in enumerate(select):
        for x, key in enumerate(keys):
            row = next(r for r in grouped[key] if r['case']==base['case'])
            picture = Image.open(image_path(Path(row['raw_root']), row, 'png')).convert('RGB')
            picture.thumbnail((320, 240))
            sheet.paste(picture, (320*x, 270*y+30))
            draw.text((320*x+3, 270*y+2), key[0].replace('walls_floor_', '')+' / '+key[1], fill='black')
            draw.text((320*x+3, 270*y+15), row['map'].split('_final')[0]+'/'+row['pose'], fill='black')
    sheet.save(output/'comparison.jpg', quality=87)
    write(output/'SHA256SUMS.json', {p.name: sha(p) for p in output.iterdir() if p.is_file()})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', nargs='+', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not platform.node().startswith('ugrp-sim-gcp2'): p.error('gcp2 saved-image analysis only')
    score(a.inputs, a.output)
