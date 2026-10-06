"""Evaluation only: saved-pose counterfactual maps and geometric visibility.

No estimator calls, new observations, dynamics, integration, rendering or model calls.
GT camera labels/qpos are used ONLY here, never passed into a robot's memory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import odom_grid_replay as base
from harness.self_odom_grid import OdomGrid, ray_cells, transform
from prob_result_report import historical

CONDITIONS = ('off', 'v2', 'prob', 'rbpf100')
CATEGORIES = ('range_projection', 'pose', 'nonwall', 'cell_boundary')
TOL = .15
# Floor contact is 5 mm above the coincident floor/wall edge. Body visibility
# additionally samples a 40 cm wall at 1 cm vertical spacing, including that edge.
HEIGHTS = np.arange(.005, .4, .01)


def relative_pose(world, origin):
    xy = transform([np.asarray(world[:2])-origin[:2]], [0, 0, -origin[2]])[0]
    return np.r_[xy, world[2]-origin[2]]


def sample_frame(row, pose):
    """Exactly the original grid's sampling, with local provenance attached."""
    camera = transform([row['camera']], pose)[0]
    occupied, free = {}, set()
    for local in row['segments']:
        ends = transform(local, pose)
        n = max(2, int(math.ceil(np.linalg.norm(ends[1]-ends[0])/.05))+1)
        for local_p, p in zip(np.linspace(*np.array(local), n), np.linspace(*ends, n)):
            keys = ray_cells(camera, p, .1)
            occupied.setdefault(keys[-1], []).append((local_p, p))
            free.update(keys[:-1])
    return occupied, free-set(occupied)


def update_support(old, new, support, label=None):
    """Allocate only surviving positive log odds; miss/clamp preserve mass."""
    if new <= 0:
        return np.zeros(4)
    if old <= 0:
        return new*np.asarray(label)
    if new < old:
        return support*(new/old)
    return support+(new-old)*np.asarray(label)


def attribution(estimated_distance, gt_distance, wall_fraction):
    """Ordered operational decomposition, not uniquely identified causal labels."""
    if estimated_distance <= TOL:
        return np.array([0., 0., 0., 1.])
    if gt_distance <= TOL:
        return np.array([0., 1., 0., 0.])
    return np.array([wall_fraction, 0., 1.-wall_fraction, 0.])


def in_image(uv, depth):
    # The saved detector uses K-pinhole undistortion of the raw fisheye image.
    # Also require the corresponding raw coordinate to exist.
    import cv2
    import markerless_probe as mp
    from sim.masterpi_camera_profile import CAMERA_FISHEYE_D
    uv = np.asarray(uv).reshape(-1, 2)
    ok = (np.asarray(depth) > 1e-6) & np.isfinite(uv).all(1)
    ok &= (uv[:, 0] >= 0) & (uv[:, 0] < 640) & (uv[:, 1] >= 0) & (uv[:, 1] < 480)
    idx = np.flatnonzero(ok)
    if len(idx):
        normalized = (uv[idx]-[mp.CX, mp.CY])/[mp.FX, mp.FY]
        raw = cv2.fisheye.distortPoints(normalized.reshape(-1, 1, 2), mp.K, np.array(CAMERA_FISHEYE_D)).reshape(-1, 2)
        ok[idx] &= (raw[:, 0] >= 0) & (raw[:, 0] < 640) & (raw[:, 1] >= 0) & (raw[:, 1] < 480)
    return ok


class SavedGeometry:
    """Saved state -> rigid transforms -> first-hit rays. No dynamics pipeline."""
    def __init__(self, xml):
        import mujoco
        self.mj = mujoco
        self.model = mujoco.MjModel.from_xml_path(str(xml))
        self.data = mujoco.MjData(self.model)
        self.mask = np.array([1, 1, 1, 1, 0, 0], np.uint8)
        self.names = [self.model.geom(i).name for i in range(self.model.ngeom)]
        self.wall = np.array([n.startswith('zone_wall_') for n in self.names])
        self.ray_count = 0

    def at(self, qpos):
        self.data.qpos[:] = qpos
        self.mj.mj_kinematics(self.model, self.data)
        assert self.data.time == 0. and np.array_equal(self.data.qpos, qpos)

    def rays(self, origin, directions):
        directions = np.asarray(directions, float).reshape(-1, 3)
        directions = directions/np.linalg.norm(directions, axis=1)[:, None]
        n = len(directions)
        ids, dist = np.empty(n, np.int32), np.empty(n)
        if n:
            self.mj.mj_multiRay(self.model, self.data, np.asarray(origin, float),
                                directions.ravel(), self.mask, True, -1, ids, dist,
                                None, n, 100.)
        self.ray_count += n
        return dist, ids

    def semantics(self, ids):
        labels = []
        for i in ids:
            n = self.names[i] if i >= 0 else 'no_hit'
            if n.startswith('zone_wall_'):
                labels.append('wall')
            elif n == 'floor' or n.startswith('zone_'):
                labels.append('floor')
            elif n.startswith(('r1__', 'r2__', 'r3__')):
                labels.append('robot')
            elif i >= 0:
                labels.append('object')
            else:
                labels.append('unknown')
        return labels


def camera_world(label):
    r = np.asarray(label['base_rotation'])
    return np.array(label['base_position_m'])+r@label['origin_m'], r@label['rotation']


def visible_targets(geometry, origin, rotation, targets):
    import markerless_probe as mp
    rays = targets-origin
    optical = rays@rotation
    with np.errstate(divide='ignore', invalid='ignore'):
        uv = optical[:, :2]/optical[:, 2, None]*[mp.FX, mp.FY]+[mp.CX, mp.CY]
    indices = np.flatnonzero(in_image(uv, optical[:, 2]))
    visible = np.zeros(len(targets), bool)
    if len(indices):
        dist, ids = geometry.rays(origin, rays[indices])
        # Exact first surface must be the target, not the opposite face of the
        # same wall, a robot, an object or the floor in front of it.
        hit_wall = (ids >= 0) & geometry.wall[np.maximum(ids, 0)]
        visible[indices] = hit_wall & (abs(dist-np.linalg.norm(rays[indices], axis=1)) <= .001)
    return visible


class Evidence:
    def __init__(self, geometry, frames, labels, states):
        self.geometry, self.frames, self.labels, self.states = geometry, frames, labels, states
        self.active = None
        self.cache, self.records = {}, []

    def at(self, frame_id):
        if self.active != frame_id:
            self.geometry.at(self.states[round(self.labels[frame_id]['t'], 6)]['qpos'])
            self.active = frame_id

    def fraction(self, frame_id, p):
        import markerless_probe as mp
        import wall_probe as wp
        key = (frame_id, *np.round(p, 10))
        if key in self.cache:
            return self.cache[key]
        self.at(frame_id)
        servo = {int(k): v for k, v in self.frames[frame_id]['commanded_servo'].items()}
        cm = mp.column_model(servo, wp.detector_bias(servo, wp.is_loaded(servo), True), mp.column_positions(96, 2))
        optical = (np.r_[p, 0.]-(cm.origin+[.0482, 0, 0]))@cm._rot
        uv = optical[:2]/optical[2]*[mp.FX, mp.FY]+[mp.CX, mp.CY]
        # Historical detector's above-contact evidence band; do not label the
        # first floor pixel at the contact itself as a floor false detection.
        patch = uv+np.array([(dx, dy) for dy in (-10, -6, -2) for dx in (-2, 0, 2)])
        if not in_image(patch, np.full(len(patch), optical[2])).all():
            raise ValueError('EVIDENCE_OUTSIDE_RECORDED_IMAGE')
        origin, rotation = camera_world(self.labels[frame_id])
        rays = np.column_stack(((patch-[mp.CX, mp.CY])/[mp.FX, mp.FY], np.ones(len(patch))))@rotation.T
        _, ids = self.geometry.rays(origin, rays)
        semantics = self.geometry.semantics(ids)
        if 'unknown' in semantics:
            raise ValueError('UNRESOLVED_EVIDENCE_RAY')
        frac = semantics.count('wall')/len(semantics)
        self.cache[key] = frac
        self.records.append({'frame_id': frame_id, 'local_xy': p.tolist(), 'uv': uv.tolist(),
                             'above_band_semantics': dict(Counter(semantics)), 'wall_fraction': frac})
        return frac


def audited_grid(robot, ledger, truth, origin, rects, evidence):
    grid = OdomGrid(robot)
    support = {}
    mixed_mass = {}
    for row in ledger:
        occupied, free = sample_frame(row, row['pose'])
        gt = truth[round(row['t'], 6)]
        weight = row.get('insertion_weight', 1.)
        for key in free:
            old = grid.cells.get(key, 0.)
            new = max(grid.lo, min(grid.hi, old+grid.miss*weight))
            if old > 0:
                support[key] = update_support(old, new, support[key])
                mixed_mass[key] *= max(0., new)/old
            grid.cells[key] = new
        for key, sources in occupied.items():
            old = grid.cells.get(key, 0.)
            new = max(grid.lo, min(grid.hi, old+grid.hit*weight))
            if new > 0:
                center = transform([(np.array(key)+.5)*.1], origin)
                is_false = base.boundary_dist(center, rects)[0] > TOL
                label, mixed = np.zeros(4), 0.
                # Correct cells also carry bookkeeping mass, but are excluded
                # from the final false-cell attribution denominator.
                if is_false:
                    local = np.array([p[0] for p in sources])
                    estimated = transform(np.array([p[1] for p in sources]), origin)
                    de = base.boundary_dist(estimated, rects)
                    dg = base.boundary_dist(transform(local, gt), rects)
                    for p, a, b in zip(local, de, dg):
                        f = evidence.fraction(row['frame_id'], p) if min(a, b) > TOL else 0.
                        label += attribution(a, b, f)/len(sources)
                        mixed += float(0. < f < 1.)/len(sources)
                else:
                    label[3] = 1.
                support[key] = update_support(old, new, support.get(key, np.zeros(4)), label)
                inc = max(0., new)-max(0., old)
                mixed_mass[key] = mixed_mass.get(key, 0.)+inc*mixed
            grid.cells[key] = new
        grid.frames += 1
    records, counts = [], np.zeros(4)
    for key, value in sorted(grid.cells.items()):
        if value <= 0:
            continue
        xy = transform([(np.array(key)+.5)*.1], origin)[0]
        if base.boundary_dist(xy[None], rects)[0] <= TOL:
            continue
        shares = support[key]/value
        assert abs(shares.sum()-1.) < 1e-10
        counts += shares
        records.append({'cell': [int(k) for k in key], 'world_xy': xy.tolist(), 'log_odds': value,
                        'shares': dict(zip(CATEGORIES, shares.tolist())),
                        'mixed_patch_share': mixed_mass[key]/value})
    return grid, {'false_cells': len(records), 'cell_equivalents': dict(zip(CATEGORIES, counts.tolist())),
                  'fractions': dict(zip(CATEGORIES, (counts/max(1, len(records))).tolist())),
                  'mixed_patch_cell_equivalents': sum(r['mixed_patch_share'] for r in records)}, records


def measure(grid, origin, rects, samples, masks):
    q, cover = base.quality(transform(grid.occupied_points(), origin), rects, samples)
    q['covered_all_count'] = int(cover.sum())
    for name, mask in masks.items():
        q['recall_'+name] = float(cover[mask].mean()) if mask.any() else None
        q['covered_'+name+'_count'] = int(cover[mask].sum())
    return q


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(r, allow_nan=False)+'\n' for r in rows))


def run_case(name, out):
    robot = name[-2:]
    source = base.ROOT/'outputs/self-map-odom-grid-v1-complete'/name
    ref = json.loads((source/'summary.json').read_text())
    episode = Path(ref['episode'])
    frames_list = base.read_rows(episode/f'robots/{robot}/frames.jsonl')
    frames = {f['frame_id']: f for f in frames_list}
    labels = {l['frame_id']: l for l in base.read_rows(episode/f'eval_only/{robot}/camera_labels.jsonl')}
    states = {round(s['t'], 6): s for s in base.read_rows(episode/'eval_only/trajectory.jsonl')}
    times, poses = base.ground_truth(episode, robot)
    truth = dict(zip(np.round(times, 6), poses))
    origin = np.asarray(ref['origin_eval_only'])
    assert np.allclose(origin, truth[round(frames_list[0]['sim_time'], 6)], atol=1e-12)
    walls = [w for w in json.loads((episode/'inputs/static_map.json').read_text())['obstacles'] if w.get('kind') == 'wall']
    assert all(w['height_m'] == .4 for w in walls)
    rects = np.array([list(w['center_m'])+list(w['half_extents_m']) for w in walls])
    samples = base.wall_samples(rects)
    assert len(samples) == 349
    observations = base.read_rows(source/'observations.jsonl')
    admitted = {r['frame_id'] for r in observations}
    geometry = SavedGeometry(episode/'scene.xml')
    masks = {k: np.zeros(len(samples), bool) for k in ('visible', 'contact_visible', 'contact_near4', 'contact_admitted')}
    trace = []
    for f in frames_list:
        fid = f['frame_id']
        label = labels[fid]
        assert label['sha256'] == f['sha256'] and abs(label['t']-f['sim_time']) < 1e-6
        geometry.at(states[round(label['t'], 6)]['qpos'])
        camera, rotation = camera_world(label)
        contact = visible_targets(geometry, camera, rotation, np.column_stack([samples, np.full(len(samples), .005)]))
        masks['contact_visible'] |= contact
        masks['contact_near4'] |= contact & (np.linalg.norm(samples-camera[:2], axis=1) <= 4.)
        if fid in admitted:
            masks['contact_admitted'] |= contact
        masks['visible'] |= contact
        unseen = np.flatnonzero(~masks['visible'])
        if len(unseen):
            targets = np.column_stack([np.repeat(samples[unseen], len(HEIGHTS), axis=0), np.tile(HEIGHTS, len(unseen))])
            body = visible_targets(geometry, camera, rotation, targets).reshape(-1, len(HEIGHTS)).any(1)
            masks['visible'][unseen] |= body
        trace.append({'frame_id': fid, 't': label['t'], **{k: int(v.sum()) for k, v in masks.items()}})
    out.mkdir(parents=True, exist_ok=False)
    write_rows(out/'visibility.jsonl', trace)
    base.dump(out/'wall_samples.json', {'xy': samples.tolist(), **{k: v.tolist() for k, v in masks.items()}})
    evidence = Evidence(geometry, frames, labels, states)
    results, sources = {}, [source/'observations.jsonl', source/'summary.json', episode/'scene.xml', episode/'inputs/static_map.json',
                           episode/'eval_only/trajectory.jsonl', episode/f'eval_only/{robot}/camera_labels.jsonl', episode/f'robots/{robot}/frames.jsonl']
    for condition in CONDITIONS:
        path = historical(name, condition) if condition in ('off', 'v2') else base.ROOT/'outputs/self-map-prob-rbpf-v1-complete'/condition/name
        ledgerpath = path/'map_ledger.jsonl'
        if not ledgerpath.exists():
            ledgerpath = path/'observations.jsonl'
        ledger = base.read_rows(ledgerpath)
        saved = json.loads((path/'grid.json').read_text())
        grid, breakdown, records = audited_grid(robot, ledger, truth, origin, rects, evidence)
        assert grid.export()['cells'] == saved['cells'], (name, condition, 'EXACT_MAP_REBUILD')
        q = measure(grid, origin, rects, samples, masks)
        old = json.loads((path/'summary.json').read_text())['final']
        for k in ('precision_015', 'wall_coverage', 'wall_error_rmse_m', 'occupied_cells'):
            assert q[k] == old[k], (name, condition, k)
        oracle = OdomGrid(robot)
        for row in ledger:
            pose = relative_pose(truth[round(row['t'], 6)], origin)
            w = row.get('insertion_weight', 1.)
            oracle.hit, oracle.miss = grid.hit*w, grid.miss*w
            oracle.insert(transform([row['camera']], pose)[0], [transform(s, pose) for s in row['segments']])
        oq = measure(oracle, origin, rects, samples, masks)
        results[condition] = {'original': q, 'matched_gt_pose': oq, 'attribution': breakdown, 'frames': len(ledger),
                              'exact_original_grid_and_metrics': True}
        base.dump(out/f'{condition}-gt-grid.json', oracle.export())
        write_rows(out/f'{condition}-false-cells.jsonl', records)
        sources.extend([ledgerpath, path/'grid.json', path/'summary.json'])
        print(name, condition, 'P/R/Rvis/RMSE', [round(q[k], 3) for k in ('precision_015','wall_coverage','recall_visible','wall_error_rmse_m')],
              'GT', [round(oq[k], 3) for k in ('precision_015','wall_coverage','wall_error_rmse_m')], flush=True)
    write_rows(out/'pixel-evidence.jsonl', evidence.records)
    result = {'case': name, 'scope': 'evaluation-only recorded-state geometry; no dynamics, rendering, models or timing benchmark',
              'source_sha': subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
              'mujoco_geometry_version': geometry.mj.__version__, 'ray_count': geometry.ray_count,
              'recorded_frames': len(frames_list), 'wall_rectangles': len(walls), 'wall_samples_all': len(samples),
              'visibility_counts': {k: int(v.sum()) for k,v in masks.items()}, 'origin_eval_only': origin.tolist(),
              'conditions': results, 'sources': [{'path': str(p), 'sha256': base.sha(p)} for p in dict.fromkeys(sources)]}
    base.dump(out/'summary.json', result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--case', choices=[f's{s}-{r}' for s in (911,912,913) for r in ('r1','r2')])
    args = p.parse_args()
    cases = [args.case] if args.case else [f's{s}-{r}' for s in (911,912,913) for r in ('r1','r2')]
    for case in cases:
        run_case(case, args.output/case)


if __name__ == '__main__':
    main()
