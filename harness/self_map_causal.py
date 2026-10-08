"""Causal own-map/landmark snapshots; no static layout or ground-truth inputs.

All positions come from contemporaneous own estimates. No hindsight graph,
future RGB, reconstructed unobserved region bounds, or cross-robot records.
"""
import copy
from types import SimpleNamespace
import numpy as np
from harness.self_odom_grid import transform

TIME_EPS = 1e-8


def before(t, cut):
    return float(t) < float(cut)-TIME_EPS


def after(t, cut):
    return float(t) > float(cut)+TIME_EPS


def snapshot_before(snapshots, cut, *, robot_id):
    eligible = [r for r in snapshots if before(r['t'], cut)]
    if not eligible:
        raise ValueError('NO_CAUSAL_SNAPSHOT')
    row = max(eligible, key=lambda r: r['t'])
    if row['view'] != 'online_frontend' or row['grid']['robot_id'] != robot_id:
        raise ValueError('OWN_ONLINE_SNAPSHOT_REQUIRED')
    if any(not before(r['t'], cut) or r['t'] > row['t']+TIME_EPS or
           r.get('robot_id', robot_id) != robot_id for r in row['ledger']):
        raise ValueError('FUTURE_OR_PEER_SCAN_IN_SNAPSHOT')
    return copy.deepcopy(row)


def own_landmarks_before(measurements, poses, cut, *, robot_id):
    """Retain every observed partial feature as an ML correspondence candidate.

    No averaging or selection: duplicate observations are alternatives in the
    pinned S2 maximum, not extra likelihood factors. Source covariance is kept
    for audit; the original fixed sensor likelihood remains unchanged.
    """
    lookup = {r['frame_id']: r for r in poses if before(r['t'], cut)}
    edges, doors = [], []
    for row in measurements:
        if not before(row['t'], cut):
            continue
        if row['robot_id'] != robot_id:
            raise ValueError('PEER_LANDMARK_FORBIDDEN')
        own = lookup[row['frame_id']]
        if abs(own['t']-row['t']) > TIME_EPS:
            raise ValueError('CONTEMPORANEOUS_POSE_REQUIRED')
        pose = np.asarray(own['pose'], float)
        c, s = np.cos(pose[2]), np.sin(pose[2])
        rot = np.array([[c, -s], [s, c]])
        source = dict(robot_id=robot_id, t=row['t'], frame_id=row['frame_id'],
            obs_id=f"{robot_id}-obs-{row['frame_id']:06d}", frame_sha256=row['frame_sha256'],
            pose=own['pose'], covariance=own['covariance'])
        for f in row['features']:
            if f['kind'] == 'floor_line':
                a, b = transform(f['endpoints'], pose)
                edges.append(dict(region=None, hue=f['hue'], a=a.tolist(), b=b.tolist(),
                    normal=(rot@np.asarray(f['normal'])).tolist(), source=copy.deepcopy(source),
                    partial_extent=True))
            elif f['kind'] == 'door':
                doors.append(dict(center=transform([f['center']], pose)[0].tolist(),
                    width=f['width'], source=copy.deepcopy(source)))
            else:
                raise ValueError('UNKNOWN_LANDMARK_KIND')
    return dict(robot_id=robot_id, frame=f'{robot_id}/own_start', before_t=cut,
        edges=edges, doors=doors, world_alignment=None, future_observations=0)


def landmark_object(record):
    edges = [{**r, **{k: np.asarray(r[k], float) for k in ('a', 'b', 'normal')}}
             for r in record['edges']]
    doors = [{**r, 'center': np.asarray(r['center'], float)} for r in record['doors']]
    return SimpleNamespace(edges=edges, doors=doors,
        hues=sorted(set(r['hue'] for r in edges)))
