"""GCP-only read-only camera audit, complete distributions and paired gates."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess

import numpy as np
from PIL import Image, ImageDraw


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    if not path.exists():
        path = path.with_name(path.name+'.zst')
    data = subprocess.check_output(['zstd', '-dqc', str(path)]) if path.suffix == '.zst' else path.read_bytes()
    return json.loads(data)


def write(path, data):
    from scripts.probe_scene_tex2 import write as save
    return save(path, data)


def dist(values):
    rows = list(values)
    values = [float(x) for x in rows if x is not None]
    return {'n': len(rows), 'valid_n': len(values), 'zero_n': sum(x == 0 for x in values),
            **dict(zip(('min', 'p05', 'p25', 'median', 'p75', 'p95', 'max'),
                       np.percentile(values, [0, 5, 25, 50, 75, 95, 100]).tolist() if values else [None]*7)),
            'sum': sum(values)}


def summarize(root, output):
    output.mkdir(parents=True, exist_ok=False)
    meta = read(root/'summary.json')
    manifest = read(root/'SHA256SUMS.json')
    bad = [p for p, digest in manifest.items() if not (root/p).is_file() or sha(root/p) != digest]
    if bad:
        raise ValueError('RAW_HASH_MISMATCH:'+repr(bad[:5]))
    rows = [read(root/e['record']) for e in read(root/'index.json')]
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r['material'], r['quality'])].append(r)
    reference = {r['case']: r for r in rows if r['material'] == 'floor_light_textured_v1' and r['quality'] == 'native'}
    bright_reference = {r['case']: r for r in rows if r['material'] == 'floor_light_v1' and r['quality'] == 'native'}
    stats, arms = [], []
    for (material, quality), rr in grouped.items():
        arm = {'material': material, 'quality': quality, 'n': len(rr), 'scopes': {}}
        for scope in ('all', 'drive'):
            sr = [r for r in rr if scope == 'all' or r['pose'] == scope]
            arm['scopes'][scope] = {enc: {
                surface: {field: dist(r['encodings'][enc]['surfaces'][surface][field] for r in sr)
                          for field in ('orb20', 'orb7', 'interior20', 'interior7', 'laplacian_variance', 'pixels')}
                for surface in ('floor', 'wall')} for enc in ('png', 'jpeg90', 'pil82')}
        arm['stages'] = {stage: {surface: {f: dist(r['stages'][stage][surface][f] for r in rr)
            for f in ('orb20', 'orb7', 'interior20', 'laplacian_variance')}
            for surface in ('floor', 'wall')} for stage in ('pinhole', 'fisheye', 'final')}
        arm['matches'] = {enc: {key: dist(r['matches'][enc][key]['mutual_ratio_matches'] for r in rr)
                               for key in ('floor20', 'floor7', 'wall20', 'wall7')}
                          for enc in ('png', 'jpeg90', 'pil82')}
        arm['segmentation'] = {enc: {surface: {
            'per_frame_iou': dist(r['encodings'][enc]['iou'][surface]['iou'] for r in rr),
            'micro_iou': (sum(r['encodings'][enc]['iou'][surface]['tp'] for r in rr) /
                max(1, sum(sum(r['encodings'][enc]['iou'][surface][k] for k in ('tp', 'fp', 'fn')) for r in rr)))}
            for surface in ('floor', 'wall')} for enc in ('png', 'jpeg90', 'pil82')}
        arm['timing'] = {k: dist(x[k] for r in rr for x in r['warm_timing']) for k in ('render_s', 'rgb_s')}
        arm['timing_vs_native'] = {}
        for k in ('render_s', 'rgb_s'):
            native = grouped.get((material, 'native'), [])
            arm['timing_vs_native'][k] = dist(np.median([t[k] for t in r['warm_timing']]) /
                np.median([t[k] for t in next(n for n in native if n['case'] == r['case'])['warm_timing']])
                for r in rr) if native else None
        arm['occluded'] = {'n': sum(r['pose'] == 'high_beam_peer_occluded' for r in rr),
                           'wall_visible_n': sum(r['pose'] == 'high_beam_peer_occluded' and
                                  r['encodings']['png']['surfaces']['wall']['pixels'] > 0 for r in rr)}
        arm['paired'] = {}
        failures = []
        for enc in ('png', 'jpeg90', 'pil82'):
            pairs = [(r, reference[r['case']]) for r in rr if r['case'] in reference]
            if not pairs:
                continue
            pair = {'n': len(pairs),
                    'box_equal_v1': sum(r['encodings'][enc]['semantic']['box_counts'] == b['encodings'][enc]['semantic']['box_counts'] for r, b in pairs),
                    'box_equal_bright': sum(r['case'] in bright_reference and r['encodings'][enc]['semantic']['box_counts'] ==
                         bright_reference[r['case']]['encodings'][enc]['semantic']['box_counts'] for r, b in pairs)}
            for surface in ('floor', 'wall'):
                pair[surface] = {f: {'lower_n': sum(r['encodings'][enc]['surfaces'][surface][f] < b['encodings'][enc]['surfaces'][surface][f]
                        for r, b in pairs if b['encodings'][enc]['surfaces'][surface][f] is not None),
                        'difference': dist(None if b['encodings'][enc]['surfaces'][surface][f] is None or
                            r['encodings'][enc]['surfaces'][surface][f] is None else
                            r['encodings'][enc]['surfaces'][surface][f]-b['encodings'][enc]['surfaces'][surface][f] for r, b in pairs)}
                        for f in ('orb20', 'orb7', 'interior20', 'laplacian_variance')}
            pair['matches'] = {key: {'lower_n': sum(r['matches'][enc][key]['mutual_ratio_matches'] < b['matches'][enc][key]['mutual_ratio_matches'] for r, b in pairs),
                   'difference': dist(r['matches'][enc][key]['mutual_ratio_matches']-b['matches'][enc][key]['mutual_ratio_matches'] for r, b in pairs)}
                   for key in ('floor20', 'floor7', 'wall20', 'wall7')}
            arm['paired'][enc] = pair
            for r, b in pairs:
                if r['encodings'][enc]['semantic']['box_counts'] != b['encodings'][enc]['semantic']['box_counts']:
                    failures.append({'case': r['case'], 'encoding': enc, 'category': 'BOX_SEMANTIC_CHANGED',
                         'blocking_object': 'existing color box detector', 'minimum_gap_m': None,
                         'minimum_gap_reason': 'image/component gate, no collision clearance',
                         'reason': 'kind counts differ from native v1',
                         'candidate': r['encodings'][enc]['semantic']['box_counts'], 'v1': b['encodings'][enc]['semantic']['box_counts']})
        arm['colour_intrusion'] = {enc: {surface: {
            'per_frame_range_sum': dist(sum(x[surface] for x in r['encodings'][enc]['intrusions'].values()) for r in rr),
            'note': 'overlapping ranges, not unique pixels or final false detections'}
            for surface in ('wall', 'floor')} for enc in ('png', 'jpeg90', 'pil82')}
        # Strict paired v1 preservation; no ungrounded numerical count threshold.
        stages = []
        alive = list(rr)
        checks = [
            ('complete_88', lambda r: len(rr) == 88),
            ('box_png_and_jpeg90_equal_v1', lambda r: r['case'] in reference and all(
                r['encodings'][e]['semantic']['box_counts'] == reference[r['case']]['encodings'][e]['semantic']['box_counts']
                for e in ('png', 'jpeg90'))),
            ('camera_features_at_least_v1', lambda r: r['case'] in reference and all(
                r['encodings'][e]['surfaces'][s]['orb20'] >= reference[r['case']]['encodings'][e]['surfaces'][s]['orb20']
                for e in ('png', 'jpeg90') for s in ('floor', 'wall'))),
            ('consecutive_matches_at_least_v1', lambda r: r['case'] in reference and all(
                r['matches'][e][s]['mutual_ratio_matches'] >= reference[r['case']]['matches'][e][s]['mutual_ratio_matches']
                for e in ('png', 'jpeg90') for s in ('floor20', 'wall20'))),
        ]
        for stage, check in checks:
            passed = [r for r in alive if check(r)]
            stages.append({'stage': stage, 'input_n': len(alive), 'cumulative_pass_n': len(passed), 'rejected_n': len(alive)-len(passed)})
            alive = passed
        table = {'material': material, 'quality': quality, 'stages': stages, 'box_changes': failures,
                 'remaining_issues': [{'category': 'REAL_FRAME_UNAVAILABLE', 'blocking_object': 'archived physical RGB missing at recorded paths',
                      'minimum_gap_m': None, 'minimum_gap_reason': 'image availability, no clearance', 'reason': 'physical feature/sharpness comparison unverified'}],
                 'ready': False, 'raw_path': str(root), 'reproduction_command': meta['reproduction_command']}
        filename = material+'--'+quality
        write(output/(filename+'-rejection.json'), table)
        path = write(output/(filename+'.json'), arm)
        stats.append({'material': material, 'quality': quality, 'file': path.name,
                      'box_png_jpeg90': {e: arm['paired'].get(e, {}).get('box_equal_v1') for e in ('png', 'jpeg90', 'pil82')},
                      'floor_orb20_median': arm['scopes']['drive']['png']['floor']['orb20']['median'],
                      'wall_orb20_median': arm['scopes']['drive']['png']['wall']['orb20']['median'],
                      'floor_interior20_sum': arm['scopes']['all']['png']['floor']['interior20']['sum'],
                      'rgb_cost_ratio': (arm['timing_vs_native']['rgb_s'] or {}).get('median')})
        arms.append(arm)
    # Inspect exact old JPEG counterexample + drive + occlusion, same poses.
    selected = ['zone_wide_two_doors_final_v3--view0--box_palette--r1',
                'zone_hardmaps1_h2_final_v3--view1--drive--r1',
                'zone_wide_two_doors_final_v3--view0--high_beam_peer_occluded--r1']
    if len(grouped) <= 6:
        columns = list(grouped)
    else:
        columns = [(m, q) for m, q in grouped if q in ('native', 'ss2_area_v1', 'no_mip_v1') and m != 'floor_light_v1']
    columns = columns[:6]
    sheet = Image.new('RGB', (480*len(columns), 390*len(selected)), 'white')
    draw = ImageDraw.Draw(sheet)
    for j, case in enumerate(selected):
        for i, key in enumerate(columns):
            r = next((r for r in grouped[key] if r['case'] == case), None)
            if r is None:
                continue
            im = Image.open(root/r['encodings']['png']['file']).convert('RGB')
            sheet.paste(im.resize((480, 360)), (480*i, 390*j+30))
            draw.text((480*i+3, 390*j+2), key[0]+' / '+key[1], fill='black')
            draw.text((480*i+3, 390*j+15), case.split('--', 1)[1], fill='black')
    sheet.save(output/'comparison.jpg', quality=87)
    write(output/'summary.json', {'status': meta['status'], 'source_sha': meta['source_sha'], 'frames': len(rows),
           'input': str(root), 'verified_files': len(manifest), 'bad_hashes': bad, 'arms': stats,
           'script_sha256': sha(Path(__file__)), 'rejection_table': str(output/'rejection-table.json')})
    write(output/'rejection-table.json', {'arms': [dict(material=a['material'], quality=a['quality'],
          file=a['material']+'--'+a['quality']+'-rejection.json') for a in arms],
          'ready': False, 'raw_path': str(root), 'reproduction_command': meta['reproduction_command']})
    write(output/'SHA256SUMS.json', {p.name: sha(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps({'frames': len(rows), 'verified_files': len(manifest), 'arms': stats}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if platform.system() != 'Linux' or not platform.node().startswith('ugrp-sim-gcp2'):
        p.error('gcp2 analysis only')
    summarize(a.input, a.output)
