"""Frozen detector-only evaluation. Extraction writes predictions before GT loading.

No simulator or model execution. Manual annotations are evaluation-only.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT/'experiments/2026-10-07-wall-floor-boundary'
OUT = Path('/Users/changmin/projects/ugrp/outputs/wall-floor-boundary-v1')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code')]
import v3_confidence_replay as old

COLS = old.mp.column_positions(96, 2)
BINS = ((0., 2.), (2., 3.), (3., 4.000001))


def project(uv, origin, rotation, intrinsic):
    """Ray/plane projection, optical z and ray parameter strictly positive."""
    uv = np.asarray(uv, float).reshape(-1, 2)
    rays = np.c_[uv, np.ones(len(uv))] @ np.linalg.inv(intrinsic).T @ np.asarray(rotation).T
    with np.errstate(divide='ignore', invalid='ignore'):
        t = -origin[2]/rays[:, 2]
        xyz = origin + t[:, None]*rays
    depth = ((xyz-origin) @ rotation)[:, 2]
    ranges = np.linalg.norm(xyz[:, :2]-origin[:2], axis=1)
    valid = np.isfinite(xyz).all(axis=1) & (t > 0) & (depth > 0) & (ranges <= 4.)
    return xyz[:, :2], ranges, valid


def annotation_rows(annotation, columns=COLS):
    rows = np.full(len(columns), np.nan)
    ignore = np.zeros(len(columns), bool)
    for line in annotation['polylines']:
        for (x, y), (xx, yy) in zip(line[:-1], line[1:]):
            use = (columns >= x) & (columns <= xx)
            rows[use] = y+(columns[use]-x)*(yy-y)/(xx-x)
    for lo, hi in annotation['ignore']:
        ignore |= (columns >= lo) & (columns <= hi)
    return rows, ignore


def measures(pred, positive, pixel_tp, metric_tp, ranges, label_ranges, errors):
    """Precision is prediction-binned; recall is label-binned, no denominator swap."""
    out = {}
    for key, lo, hi in [('all', 0., 4.000001), *[(f'{a:g}-{min(b,4):g}m', a, b) for a,b in BINS]]:
        p = pred & (ranges >= lo) & (ranges < hi)
        g = positive & (label_ranges >= lo) & (label_ranges < hi)
        out[key] = dict(predicted=int(p.sum()), positive=int(g.sum()),
            pixel_tp_pred=int((pixel_tp & p).sum()), pixel_tp_label=int((pixel_tp & g).sum()),
            metric_tp_pred=int((metric_tp & p).sum()), metric_tp_label=int((metric_tp & g).sum()),
            error_sq_sum=float(np.square(errors[p]).sum()))
    return out


def finalize(counts):
    out = dict(counts)
    p, g = counts['predicted'], counts['positive']
    for name in ('pixel', 'metric'):
        out[name+'_precision'] = counts[name+'_tp_pred']/p if p else None
        out[name+'_recall'] = counts[name+'_tp_label']/g if g else None
    out['rmse_m'] = float(np.sqrt(counts['error_sq_sum']/p)) if p else None
    return out


def extract(case, detector='off'):
    """The only extraction inputs are own RGB, own command and fixed calibration."""
    ep = old.EPISODES[case]
    fs, _ = old.own_inputs(ep, 'r3')
    valid = {e['frame_id'] for e in old.base.read_rows(old.OUT/case/'v3_unloaded_extrinsic_v1/extraction.jsonl')
             if e['reason'] == 'calibrated_unloaded'}
    dest = OUT/detector/case
    dest.mkdir(parents=True, exist_ok=False)
    predictions, reasons = [], Counter()
    for f in fs:
        if f['frame_id'] not in valid:
            continue
        path = ep/f['path']
        assert old.base.sha(path) == f['sha256']
        und = old.mp.undistort(cv2.imread(str(path)))
        servo = {int(k):int(v) for k,v in f['commanded_servo'].items()}
        cm, offset, _ = old.geometry(servo, 'v3_unloaded_extrinsic_v1')
        assert not offset.any()
        if detector == 'off':
            scan = old.hfw.detect(und, cm, params=old.PARAMS, loaded=old.wp.is_loaded(servo))
            uv = np.c_[COLS, scan['vb'][:, 0]]
            xy, ranges, ok = project(uv, cm.origin, cm._rot, old.mp.K)
            ids = np.flatnonzero(ok)
            reason = 'legacy'
        else:
            # This import does not exist until baseline/annotation seal commit.
            from harness.wall_floor_boundary import detect
            result = detect(und, camera_origin=cm.origin, camera_rotation=cm._rot,
                            intrinsic=old.mp.K, columns=COLS)
            uv, xy, ranges = result['uv'], result['xy'], result['ranges']
            ids = result['column_ids']
            reason = result['reason']
            # Normalize the sparse result to the legacy full-column representation.
            full_uv, full_xy = np.full((len(COLS),2), np.nan), np.full((len(COLS),2), np.nan)
            full_ranges = np.full(len(COLS), np.nan)
            full_uv[ids], full_xy[ids], full_ranges[ids] = uv, xy, ranges
            uv, xy, ranges = full_uv, full_xy, full_ranges
        reasons[reason] += 1
        predictions.append(dict(frame_id=f['frame_id'], t=f['sim_time'], reason=reason,
            camera_origin=cm.origin.tolist(), camera_rotation=cm._rot.tolist(),
            points=[dict(column=int(i), u=float(uv[i,0]), v=float(uv[i,1]),
                         xy=xy[i].tolist(), range_m=float(ranges[i])) for i in ids]))
        if len(predictions)%200 == 0:
            print(case, detector, len(predictions), '/', len(valid), flush=True)
    old.rows(dest/'predictions.jsonl', predictions)
    old.base.dump(dest/'prediction-manifest.json', dict(case=case, detector=detector,
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        frames=len(predictions), reasons=dict(reasons), prediction_sha256=old.base.sha(dest/'predictions.jsonl'),
        inputs=[dict(path=str(p),sha256=old.base.sha(p)) for p in [ep/'robots/r3/frames.jsonl', ep/'robots/r3/commands.jsonl']],
        eligibility_source=dict(path=str(old.OUT/case/'v3_unloaded_extrinsic_v1/extraction.jsonl'),
            sha256=old.base.sha(old.OUT/case/'v3_unloaded_extrinsic_v1/extraction.jsonl'))))
    print(case, detector, 'own predictions sealed', dict(reasons), flush=True)


def score(case, detector='off'):
    dest, ep = OUT/detector/case, old.EPISODES[case]
    manifest = old.load(dest/'prediction-manifest.json')
    assert old.base.sha(dest/'predictions.jsonl') == manifest['prediction_sha256']
    predictions = old.base.read_rows(dest/'predictions.jsonl')
    annotations = {r['frame_id']:r for r in old.load(EXP/'annotation-sample.json')['rows'] if r['case']==case}
    # Evaluation-only truth begins after the persisted prediction hash is checked.
    truth = old.current_truth(ep)
    walls = [w for w in old.load(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall']
    rects = np.array([w['center_m']+w['half_extents_m'] for w in walls])
    point_counts, label_counts, frame_scores = {}, {}, []
    ignored = labels_outside = 0
    label_errors = []
    for r in predictions:
        pred = np.zeros(len(COLS), bool)
        ranges, errors, rows = [np.full(len(COLS), np.nan) for _ in range(3)]
        ids = [p['column'] for p in r['points']]
        if ids:
            pred[ids] = True
            ranges[ids] = [p['range_m'] for p in r['points']]
            rows[ids] = [p['v'] for p in r['points']]
            world = old.transform([p['xy'] for p in r['points']], truth[round(r['t'],6)])
            errors[ids] = old.base.boundary_dist(world, rects)
        metric = pred & (errors <= .15)
        all_counts = measures(pred, np.zeros(len(COLS),bool), pred, metric, ranges, ranges, errors)
        for key, values in all_counts.items():
            point_counts.setdefault(key, Counter()).update(values)
        record = dict(frame_id=r['frame_id'], t=r['t'], all_points={k:finalize(v) for k,v in all_counts.items()})
        if r['frame_id'] in annotations:
            a = annotations[r['frame_id']]
            label_rows, ignore = annotation_rows(a)
            xy, lr, valid = project(np.c_[COLS,label_rows], np.array(r['camera_origin']),
                                    np.array(r['camera_rotation']), old.mp.K)
            positive = np.isfinite(label_rows) & valid & ~ignore
            # No true camera pose is present: report nominal calibration's label error separately.
            label_errors.extend(old.base.boundary_dist(old.transform(xy[positive],truth[round(r['t'],6)]),rects).tolist())
            ignored += int(ignore.sum())
            labels_outside += int((np.isfinite(label_rows) & ~valid & ~ignore).sum())
            use = pred & ~ignore
            pixel = use & positive & (abs(rows-label_rows) <= 3.)
            counts = measures(use, positive, pixel, pixel & metric, ranges, lr, errors)
            for key, values in counts.items():
                label_counts.setdefault(key, Counter()).update(values)
            record['annotated'] = {k:finalize(v) for k,v in counts.items()}
        frame_scores.append(record)
    old.rows(dest/'frame-scores.jsonl',frame_scores)
    result = dict(case=case,detector=detector,eligible_frames=len(predictions),annotated_frames=len(annotations),
        all_points={k:finalize(v) for k,v in point_counts.items()},
        annotated={k:finalize(v) for k,v in label_counts.items()},
        ignored_columns=ignored, labels_outside_4m_or_positive_plane=labels_outside,
        annotation_projection_error_m=dict(count=len(label_errors),median=float(np.median(label_errors)) if label_errors else None,
            p90=float(np.quantile(label_errors,.9)) if label_errors else None),
        hashes=dict(predictions=manifest['prediction_sha256'],annotations=old.base.sha(EXP/'annotation-sample.json'),
            static_map=old.base.sha(ep/'inputs/static_map.json'), trajectory=old.base.sha(ep/'eval_only/trajectory.jsonl')))
    old.base.dump(dest/'summary.json',result)
    (EXP/'results'/detector).mkdir(parents=True,exist_ok=True)
    old.base.dump(EXP/'results'/detector/f'{case}.json',result)
    assert old.base.sha(dest/'predictions.jsonl') == manifest['prediction_sha256']
    print(case, detector, 'all P', result['all_points']['all']['metric_precision'], 'annotated', result['annotated']['all'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['extract','score'])
    parser.add_argument('--detector',default='off',choices=['off','floor_boundary_v1'])
    parser.add_argument('--cases',nargs='+',default=list(old.EPISODES),choices=list(old.EPISODES))
    args=parser.parse_args()
    for case in args.cases:
        (extract if args.stage=='extract' else score)(case,args.detector)
