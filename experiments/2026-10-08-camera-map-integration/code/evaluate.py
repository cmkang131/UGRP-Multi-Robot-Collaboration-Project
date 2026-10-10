"""Evaluation-only GT geometry. No geometry is sent to replay.py."""
from collections import Counter
import math
import numpy as np
from scipy.spatial import cKDTree
from replay import *
from harness.self_odom_grid import transform

sys.path.insert(0, str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
import odom_grid_replay as metric
visibility = module('egomap44_visibility', ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')


def geometry():
    truth = rows(EP/'eval_only/trajectory.jsonl')
    origin = [*truth[0]['robot_xyz_m'][:2], truth[0]['robot_yaw_rad']]
    rects = np.array([o['center_m']+o['half_extents_m']
                     for o in load(EP/'inputs/static_map.json')['obstacles'] if o['kind'] == 'wall'])
    return truth, origin, rects, rows(EP/'eval_only/camera.jsonl')


def occupied(grid, origin):
    c = np.array([r for r in grid['cells'] if r[2] > 0]).reshape(-1, 3)
    return transform((c[:, :2]+.5)*grid['resolution_m'], origin)


def face_points(segments):
    parts = [np.linspace(a, b, max(2, int(math.ceil(np.linalg.norm(np.asarray(b)-a)/.05))+1))
             for a, b in segments]
    return np.concatenate(parts) if parts else np.empty((0, 2))


def missing_cause(visible, detected, inserted, placed):
    if not visible: return 'a_not_potentially_visible'
    if not detected: return 'b_no_projected_detection'
    if not inserted: return 'c_detection_not_inserted'
    if not placed: return 'd_inserted_pose_displaced'
    return 'e_free_evidence_or_cell_boundary'


def diagnose():
    if (EXP/'results/missing.json').exists(): raise ValueError('DIAGNOSIS_ALREADY_SEALED')
    truth, origin, rects, cameras = geometry()
    # One representative of the historical 10 cm wall samples per own grid cell.
    samples = metric.wall_samples(rects)
    inv_yaw = -origin[2]
    local = transform(samples-np.array(origin[:2]), [0., 0., inv_yaw])
    _, indices = np.unique(np.floor(local/.1).astype(int), axis=0, return_index=True)
    targets = samples[np.sort(indices)]
    keys = np.floor(transform(targets-np.array(origin[:2]), [0., 0., inv_yaw])/.1).astype(int)
    baseline = load(EP/'grid.json')
    points = occupied(baseline, origin)
    missing = cKDTree(points).query(targets)[0] > .15
    positive_keys = {tuple(r[:2]) for r in baseline['cells'] if r[2] > 0}
    gt = {round(r['t'], 6): r for r in truth}
    cams = {round(r['t'], 6): r for r in cameras}
    contacts = {r['frame_id']: r for r in rows(EP/'own-contacts.jsonl')}
    ledger = {r['frame_id']: r for r in load(EP/'graph.json')['ledger']}
    decisions = {r['frame_id']: r for r in load(EP/'decisions.json')}
    witnesses = [dict(visible=[], detected=[], inserted=[], placed=[], withheld_reasons={}) for _ in targets]
    for frame in rows(EP/'robots/r3/frames.jsonl'):
        t = round(frame['sim_time'], 6)
        if t not in cams: continue
        vis = visibility.in_view(targets, [cams[t]], rects)
        fid = frame['frame_id']
        for i in np.flatnonzero(vis): witnesses[i]['visible'].append(fid)
        if fid not in contacts: continue
        r = contacts[fid]
        near = [s for s in r['segments'] if np.linalg.norm(np.array(s)-r['camera'], axis=1).max() < 4.]
        pts = face_points(near)
        if not len(pts): continue
        body_pose = [*gt[t]['robot_xyz_m'][:2], gt[t]['robot_yaw_rad']]
        detection = (cKDTree(transform(pts, body_pose)).query(targets)[0] <= .15) & vis
        for i in np.flatnonzero(detection):
            w = witnesses[i]; w['detected'].append(fid)
            if fid in ledger:
                w['inserted'].append(fid)
                actual_insert = occupied_face = transform(face_points(ledger[fid]['segments']), ledger[fid]['pose'])
                actual_insert = transform(occupied_face, origin)
                if len(actual_insert) and np.linalg.norm(actual_insert-targets[i], axis=1).min() <= .15:
                    w['placed'].append(fid)
            else:
                reason = decisions.get(fid, {}).get('reason', 'empty_or_unrecorded')
                w['withheld_reasons'][reason] = w['withheld_reasons'].get(reason, 0)+1
    detail = []
    for i, (target, w) in enumerate(zip(targets, witnesses)):
        detail.append(dict(cell=keys[i].tolist(), world_xy=target.tolist(), missing=bool(missing[i]),
            exact_cell_occupied=tuple(keys[i]) in positive_keys,
            category=missing_cause(*(bool(w[k]) for k in ('visible', 'detected', 'inserted', 'placed'))) if missing[i] else 'covered',
            **w))
    counts = Counter(r['category'] for r in detail if r['missing'])
    report = dict(total_wall_cells=len(targets), original_samples=len(samples), missing_cells=int(missing.sum()),
        covered_cells=int((~missing).sum()), exact_cell_missing=sum(not r['exact_cell_occupied'] for r in detail),
        causes={k: dict(cells=counts[k], fraction_missing=counts[k]/int(missing.sum()),
                       fraction_all=counts[k]/len(targets)) for k in sorted(counts)},
        frame_reasons=dict(Counter(r['reason'] for r in decisions.values())),
        rgb_frames=len(cameras), detector_frames=len(contacts), nonempty_frames=sum(bool(r['segments']) for r in contacts.values()),
        inserted_frames=len(ledger), potential_visible_wall_cells=sum(bool(w['visible']) for w in witnesses),
        visibility_scope='true camera and wall-only occlusion; object/self silhouettes unavailable, potential visibility',
        detection_scope='projected face within .15 m at GT chassis pose; includes projection failure in b',
        evaluation_inputs={str(EP/n): sha(EP/n) for n in ['eval_only/camera.jsonl','eval_only/trajectory.jsonl','inputs/static_map.json']})
    dump(RAW/'missing-wall-cells.json', detail)
    dump(EXP/'results/missing.json', report)
    print(json.dumps(report, indent=2), flush=True)


def map_score():
    truth, origin, rects, cams = geometry()
    samples = metric.wall_samples(rects)
    visible = visibility.in_view(samples, cams, rects)
    reports = {}
    for label, path in [('egomap34', RAW/'off-grid.json'), ('sparse_online_control', RAW/'sparse-online-grid.json'),
                        ('camera_every_frame_v1', RAW/'on-grid.json')]:
        g = load(path); xy = occupied(g, origin)
        quality, covered = metric.quality(xy, rects, samples)
        region = visibility.in_view(xy, cams, rects)
        correct = metric.boundary_dist(xy, rects) <= .15
        reports[label] = dict(quality, region_precision=float(correct[region].mean()),
            region_precision_correct=int(correct[region].sum()), region_precision_cells=int(region.sum()),
            region_recall=float(covered[visible].mean()), region_recalled=int(covered[visible].sum()),
            visible_samples=int(visible.sum()), whole_samples=len(samples), covered_samples=int(covered.sum()),
            inserted_frames=g['frames'], observed_cells=len(g['cells']),
            observed_area_m2=len(g['cells'])*.01, free_cells=sum(r[2] < 0 for r in g['cells']))
    p = load(RAW/'prepared.json')
    on = reports['camera_every_frame_v1']
    unchanged = all(sha(Path(n)) == digest for n, digest in p['input_hashes'].items())
    gates = dict(insertion_increased=on['inserted_frames'] > 64,
        region_precision_no_less=on['region_precision'] >= 103/162,
        region_recall_no_less=on['region_recall'] >= 111/146,
        whole_coverage_increased=on['wall_coverage'] > 213/329,
        wall_rmse_no_more=on['wall_error_rmse_m'] <= .5204,
        estimator_records_unchanged=unchanged)
    result = dict(maps=reports, gates=gates, passed=all(gates.values()), independent_recordings=1,
        physics=0, retuning=0, source_sha=head(), prepared_sha256=sha(RAW/'prepared.json'))
    dump(EXP/'results/maps.json', result)
    print(json.dumps(result, indent=2), flush=True)


def utility_score():
    adapted = configure_old()
    sys.modules['replay'] = adapted
    scorer = module('egomap44_unchanged_utility_score', ROOT/'experiments/2026-10-08-own-map-causal-landmarks/code/score.py')
    scorer.evaluate('on')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['diagnose', 'maps', 'utility'])
    a = p.parse_args()
    {'diagnose': diagnose, 'maps': map_score, 'utility': utility_score}[a.stage]()
