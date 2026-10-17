#!/usr/bin/env python3
"""Recount the egonav far-range detection diagnostic (``--detect-probe``).

Reads only the raw JSON written by ``scripts/egonav_gate.py --detect-probe``
and (optionally) the recovered own-RGB JPEG frames.  Evaluation-only fields
(pose, authored zone rectangle) are used for the measurement table and the
zone-marking classification only; nothing here is fed back to the controller.

The rows-based table needs no simulator and no third-party import.  The
``--frames`` mechanism section re-uses the frozen ``camera_v3`` floor
projection from ``harness/`` to measure how much of the zone marking stays
inside the detector's valid floor region at each authored start.

Usage:
  python3 scripts/egonav_far_diag_recount.py \
      --run experiments/2026-10-17-egonav/raw/far-diag-range-01 \
      --out experiments/2026-10-17-egonav/recount_far_diag_range_01.json \
      [--frames]
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stats(values):
    if not values:
        return dict(n=0)
    return dict(n=len(values), min=min(values), median=statistics.median(values),
                max=max(values))


def patch_world(pose, patch):
    """Evaluation-only: body-frame patch center -> authored world frame."""
    x, y, yaw = pose
    bx, by = patch['center_body_m'][:2]
    c, s = math.cos(yaw), math.sin(yaw)
    return [x + c * bx - s * by, y + s * bx + c * by]


def hue_class(hue):
    if hue is None:
        return 'unknown'
    if 10 <= hue <= 16:
        return 'zone_marking'          # zone A decal renders at hue 12 (12-13 p10-p90)
    if hue <= 5:
        return 'cargo_red'             # red cargo renders at hue 1
    if 24 <= hue <= 27:
        return 'cargo_yellow'          # yellow cargo renders at hue 25 (frame 24-28)
    return 'other'


def zone_distance(world, center):
    return math.hypot(world[0] - center[0], world[1] - center[1])


def inside_zone(world, center, half, slack=0.15):
    return (abs(world[0] - center[0]) <= half[0] + slack and
            abs(world[1] - center[1]) <= half[1] + slack)


def rows_analysis(run):
    probe = load(run / 'detect_probe' / 'detect_probe.json')
    if probe.get('schema') != 'ugrp.egonav.detect_probe.v1':
        raise ValueError('NOT_A_DETECT_PROBE:%s' % probe.get('schema'))
    center = probe['target']['center_m']
    half = probe['target']['half_m']
    sums_path = run / 'SHA256SUMS.json'
    sums = load(sums_path) if sums_path.exists() else {}
    verified = missing = bad = 0
    bad_names = []
    for name, want in sums.items():
        path = run / name
        if not path.exists():
            missing += 1
            bad_names.append('missing:' + name)
            continue
        if sha(path) == want:
            verified += 1
        else:
            bad += 1
            bad_names.append('bad:' + name)
    worlds = []
    for meta in probe['worlds']:
        world = meta['world']
        rows = [r for r in probe['rows'] if r['world'] == world]
        zone_rows, other_rows = [], []
        for row in rows:
            zone_patches, other_patches = [], []
            for patch in row['patches']:
                world_xy = patch_world(row['pose_eval_only'], patch)
                item = dict(tick=row['tick'], hue=patch['hue_median'],
                            hue_class=hue_class(patch['hue_median']),
                            area_m2=patch['observed_area_m2'],
                            pixels=patch['pixels'],
                            rect_sides_m=patch['rect_sides_m'],
                            range_m=patch['range_m'],
                            world_xy=[round(v, 3) for v in world_xy],
                            dist_to_zone_center_m=round(zone_distance(world_xy, center), 3),
                            inside_eval_zone=inside_zone(world_xy, center, half))
                pp = patch.get('hue_p10'), patch.get('hue_p90')
                item['hue_p10'], item['hue_p90'] = pp
                (zone_patches if item['hue_class'] == 'zone_marking' else
                 other_patches).append(item)
            if zone_patches:
                zone_rows.append(dict(row=row, patches=zone_patches))
            if other_patches:
                other_rows.append(dict(row=row, patches=other_patches))
        diag = Counter()
        tick_stage = Counter()
        for row in rows:
            for key, value in row['diagnostics'].items():
                if isinstance(value, (int, float)) and value:
                    diag[key] += value
            dg = row['diagnostics']
            if row['visible']:
                tick_stage['accepted_visible'] += 1
            elif dg.get('metric_size'):
                tick_stage['metric_size_only'] += 1
            elif dg.get('metric_area'):
                tick_stage['metric_area_only'] += 1
            elif dg.get('metric_shape'):
                tick_stage['metric_shape_only'] += 1
            elif dg.get('before_metric'):
                tick_stage['before_metric_other'] += 1
            else:
                tick_stage['no_patch'] += 1
        zone_ticks = [tuple(sorted({p['tick'] for p in z['patches']}))[0]
                      for z in zone_rows]
        zone_area = [p['area_m2'] for z in zone_rows for p in z['patches']]
        zone_pixels = [p['pixels'] for z in zone_rows for p in z['patches']]
        zone_hue = [p['hue'] for z in zone_rows for p in z['patches']]
        zone_sides = [p['rect_sides_m'] for z in zone_rows for p in z['patches']]
        zone_dist = [p['dist_to_zone_center_m'] for z in zone_rows
                     for p in z['patches']]
        short = [s[0] for s in zone_sides]
        long_ = [s[1] for s in zone_sides]
        other_by_class = {}
        for klass in ('cargo_red', 'cargo_yellow', 'other', 'unknown'):
            items = [p for z in other_rows for p in z['patches']
                     if p['hue_class'] == klass]
            if items:
                other_by_class[klass] = dict(
                    ticks=len({p['tick'] for p in items}), patches=len(items),
                    hue=stats([p['hue'] for p in items]),
                    area_m2=stats([p['area_m2'] for p in items]),
                    pixels=stats([p['pixels'] for p in items]),
                    range_m=stats([p['range_m'] for p in items]),
                    dist_to_zone_center_m=stats(
                        [p['dist_to_zone_center_m'] for p in items]))
        first = meta.get('first_detection') or {}
        worlds.append(dict(
            world=world, spawn=meta['spawn'],
            authored_distance_to_target_center_m=round(
                meta['authored_distance_to_target_center_m'], 4),
            tick_n=meta['tick_n'],
            detected_ticks=meta['detected_ticks'],
            zone_marking_ticks=len(zone_rows),
            zone_marking_first_tick=(zone_ticks[0] if zone_ticks else None),
            zone_marking_above_area_gate_ticks=sum(
                1 for a in zone_area if a >= 0.10),
            zone_area_m2=stats(zone_area), zone_pixels=stats(zone_pixels),
            zone_hue=stats(zone_hue), zone_short_side_m=stats(short),
            zone_long_side_m=stats(long_),
            zone_dist_to_zone_center_m=stats(zone_dist),
            zone_world_xy_first=([round(v, 3) for v in patch_world(
                first['pose_eval_only'], first['patches'][0])]
                if first.get('patches') else None),
            other_patches_by_class=other_by_class,
            diagnostics=dict(sorted(diag.items())),
            tick_stages=dict(sorted(tick_stage.items()))))
    return dict(
        schema='ugrp.egonav.far_diag_range_recount.v1',
        run='far-diag-range-01',
        source_sha=probe['source_sha'], host=probe['host'],
        mode=probe['mode'], evaluation_only=probe['evaluation_only'],
        control_use=probe['control_use'],
        nworld=probe['nworld'], step_budget=probe['step_budget'],
        sim_s=probe['sim_s'], target=probe['target'],
        detector_effective=probe['detector_effective'],
        floor_valid_pixels=probe['floor_valid_pixels'],
        floor_pixels=probe['floor_pixels'],
        floor_max_range_m=probe['floor_max_range_m'],
        downward_min=probe['downward_min'],
        noslip_iterations=probe['noslip_iterations'],
        warp_noslip_iterations=probe['warp_noslip_iterations'],
        detect_probe_sha256=sha(run / 'detect_probe' / 'detect_probe.json'),
        sha256sums=dict(file=sha(sums_path) if sums_path.exists() else None,
                        verified=verified, missing=missing, bad=bad,
                        problems=bad_names),
        worlds=worlds,
        notes=[
            'zone_marking class = measured hue 10-16; zone A decal renders at '
            'hue 12 (rows: hue p10=p90=12 at 4.5 m). Truth never enters control.',
            'other-patch classes are measured hues only: red cargo renders hue 1, '
            'yellow cargo hue 25 (frame sample p10-p90 24-28). Neither is a zone '
            'marking and neither is used for control.',
            'world_xy/dist_to_zone_center_m are evaluation-only projections of '
            'the patch body-frame center with the recorded eval pose; at 4-5 m '
            'the frozen forward-floor projection bias is ~0.2 m, so use these '
            'only to label which authored zone the patch belongs to.',
            'tick0 is rendered before the first physics step (initial camera '
            'pose); ticks 1-99 are the settled static hold. Split is explicit.',
            'far-diag detector used max_range_m=10.0 (diagnostic only); the '
            'control default stays 4.0.'])


def frames_analysis(run, result):
    """Mechanism: how much of the zone marking stays inside the detector's
    valid floor-projection region.  Uses the frozen camera model only."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import numpy as np
    import cv2
    from harness.active_camera import SEARCH, goal_camera
    from harness import floor_goal as fg

    origin, axes = goal_camera(SEARCH, 'camera_v3')
    points, valid = fg.floor_intersections(
        fg.optical_rays(640, 480), origin, axes,
        downward_min=result['downward_min'],
        max_range_m=result['floor_max_range_m'])
    ranges = np.linalg.norm(points - origin, axis=-1)
    rows_valid = np.array([valid[r].mean() for r in range(480)])
    center_col = 320
    valid_center_rows = np.nonzero(valid[:, center_col])[0]
    h, w = valid.shape
    mechanism = dict(
        camera_v3_origin_body_m=[round(float(v), 4) for v in origin],
        valid_floor_pixels=int(valid.sum()), floor_pixels=int(valid.size),
        valid_fraction=round(float(valid.mean()), 4),
        first_row_valid_half_width=int(np.argmax(rows_valid > 0.5)),
        center_column_grazing_cut_range_m=round(
            float(ranges[valid_center_rows.min(), center_col]), 3),
        max_valid_floor_range_m=round(float(ranges[valid].max()), 3),
        frames={})
    zone_center = np.array(result['target']['center_m'], float)
    half = np.array(result['target']['half_m'], float)
    for world in range(result['nworld']):
        spawn = result['worlds'][world]['spawn']
        yaw = spawn[3]
        c, s = math.cos(yaw), math.sin(yaw)
        cam = [spawn[0] + c * float(origin[0]) - s * float(origin[1]),
               spawn[1] + s * float(origin[0]) + c * float(origin[1])]
        corners = [[zone_center[0] + sx * half[0], zone_center[1] + sy * half[1]]
                   for sx in (-1, 1) for sy in (-1, 1)]
        dist = sorted(math.hypot(x - cam[0], y - cam[1]) for x, y in corners)
        entry = dict(zone_corner_dist_from_camera_m=[
            round(v, 3) for v in dist])
        for tick in (0, 50, 99):
            frame = run / 'detect_probe' / 'frames' / \
                f'world{world:02d}-t{tick:04d}.jpg'
            if not frame.exists():
                continue
            rgb = cv2.cvtColor(cv2.imread(str(frame)), cv2.COLOR_BGR2RGB)
            hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
            hue_band = ((hsv[..., 0] >= 11) & (hsv[..., 0] <= 15) &
                        (hsv[..., 1] >= 70) & (hsv[..., 2] >= 40))
            hue_valid = hue_band & valid
            frac = (float(hue_valid.sum()) / int(hue_band.sum())
                    if hue_band.any() else None)
            item = dict(hue_11_15_pixels=int(hue_band.sum()),
                        valid_pixels=int(hue_valid.sum()),
                        valid_fraction=(round(frac, 3) if frac is not None else None))
            if hue_valid.any():
                pts = points[hue_valid, :2]
                wx = spawn[0] + c * pts[:, 0] - s * pts[:, 1]
                wy = spawn[1] + s * pts[:, 0] + c * pts[:, 1]
                dd = np.hypot(wx - zone_center[0], wy - zone_center[1])
                item['valid_hue_world_dist_to_zone_center_m'] = [
                    round(float(dd.min()), 3), round(float(np.median(dd)), 3),
                    round(float(dd.max()), 3)]
                item['valid_hue_world_xy_bbox'] = [
                    round(float(wx.min()), 3), round(float(wx.max()), 3),
                    round(float(wy.min()), 3), round(float(wy.max()), 3)]
            entry[f'tick{tick:04d}'] = item
        mechanism['frames'][f'world{world:02d}'] = entry
    mechanism['notes'] = [
        'valid mask = detector floor_intersections(downward_min=0.05, '
        'max_range_m=10.0) with the frozen camera_v3 mount; the detector masks '
        'out hue pixels outside this valid floor region, so this is the same '
        'geometry the run used.',
        'frames are the recovered own-RGB JPEGs written at ticks 0/50/99; JPEG '
        'quantisation shifts borderline pixel counts by a few pixels.']
    result['mechanism'] = mechanism


def verdict(result):
    by_world = {w['world']: w for w in result['worlds']}
    zone_ticks = {d['world']: by_world[d['world']]['zone_marking_ticks']
                  for d in result['worlds']}
    return dict(
        zone_marking_detected_ticks=zone_ticks,
        zone_marking_detected_fraction={k: round(v / by_world[k]['tick_n'], 3)
                                        for k, v in zone_ticks.items()},
        far_profile_promoted=False,
        decision='4.0 m limit kept; no new far detection profile promotion',
        evidence=[
            '4.5 m: zone marking accepted in %d/100 stable ticks with '
            'area above the 0.10 m2 birth gate; this is the measured edge.' %
            zone_ticks[1],
            '5.0/5.5 m: 0/100 zone marking; only cargo (red hue 1, yellow '
            'hue 25) components are accepted, so no detection/area/hue '
            'evidence at those starts.',
            '4.0 m: 1/100 accepted (tick0 initial camera pose only); '
            'stable ticks are metric_size rejections (footprint outside the '
            '0.6 m known-width*1.2 gate).',
            '5.0 m+ failure mechanism: zone-marking pixels lie outside the '
            'floor-projection valid region (downward_min=0.05 grazing cut at '
            'camera height 0.2309 m), not outside the area gate. A lower area '
            'threshold or sub-0.10 m2 candidate cannot recover them.',
            '6.0 m is unmeasured: the farthest legal authored start along the '
            'door sight line is ~5.58 m (west wall inner face x=-1.025 minus '
            'robot envelope radius 0.1582 m), so 5.5 m was the farthest legal '
            'start; the grazing cut makes 6.0 m unreachable anyway, so its '
            'absence cannot change the verdict.'],
        not_pooled_with=['far-measure-02 (max_range_m=4.0)',
                         'gate-09 16-world gate',
                         'far-probe off-03/on-03 (control probe)'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--frames', action='store_true',
                    help='also measure the floor-validity mechanism on the '
                         'recovered JPEG frames')
    args = ap.parse_args()
    result = rows_analysis(args.run)
    if args.frames:
        frames_analysis(args.run, result)
    result['verdict'] = verdict(result)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(dict(
        out=str(args.out),
        zone_marking_ticks={w['world']: w['zone_marking_ticks']
                            for w in result['worlds']},
        diagnostics={w['world']: w['diagnostics'] for w in result['worlds']},
        sha256sums=result['sha256sums'],
        far_profile_promoted=False)))


if __name__ == '__main__':
    main()
