"""Own-only offline scan/submap SPA (Hess 2016, section V).

No simulator, scene, GT, peer map, or external solver install. The frontend's
local pose lineage is immutable. Frozen policy/provenance: experiment README §22.
"""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy.ndimage import map_coordinates
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

from harness.self_map_csm import DistanceField, sample_segments
from harness.self_odom_grid import OdomGrid, transform

VALUES = ('off', 'own_submap_v1')


def wrap(angle):
    return (angle + np.pi) % (2*np.pi) - np.pi


def between(a, b):
    """T_a^-1 T_b, in a's frame; unlike a world-coordinate subtraction."""
    a, b = np.asarray(a), np.asarray(b)
    c, s = np.cos(a[..., 2]), np.sin(a[..., 2])
    dx, dy = b[..., 0]-a[..., 0], b[..., 1]-a[..., 1]
    return np.stack([c*dx+s*dy, -s*dx+c*dy, wrap(b[..., 2]-a[..., 2])], axis=-1)


def compose(a, b):
    a, b = np.asarray(a), np.asarray(b)
    c, s = np.cos(a[..., 2]), np.sin(a[..., 2])
    return np.stack([a[..., 0]+c*b[..., 0]-s*b[..., 1],
                     a[..., 1]+s*b[..., 0]+c*b[..., 1], wrap(a[..., 2]+b[..., 2])], axis=-1)


@dataclass(frozen=True)
class GraphOptions:
    submap_scans: int = 20
    stride: int = 10
    separation_s: float = 5.
    candidate_distance_m: float = 6.
    translation_window_m: float = 1.
    yaw_window_deg: float = 15.
    translation_step_m: float = .1
    yaw_step_deg: float = 1.
    min_score: float = .55
    min_overlap: float = .60
    overlap_m: float = .20
    max_residual_m: float = .15
    mode_distance_m: float = .20
    mode_yaw_deg: float = 5.
    mode_gap: float = .02
    hessian_ratio: float = .03
    min_points: int = 6
    effective_points: float = 12.
    sigma_xy_m: float = .10
    sigma_yaw_deg: float = 2.
    huber_delta: float = 1.5
    max_nfev: int = 200

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError('INVALID_POSE_GRAPH_OPTION')
        if any(type(v) is not int for v in (self.submap_scans, self.stride, self.min_points, self.max_nfev)):
            raise ValueError('INVALID_POSE_GRAPH_COUNT')
        if self.submap_scans != 2*self.stride or max(self.min_score, self.min_overlap, self.hessian_ratio) >= 1:
            raise ValueError('INVALID_POSE_GRAPH_RATIO')
        if self.translation_window_m/self.translation_step_m > 20 or self.yaw_window_deg/self.yaw_step_deg > 30:
            raise ValueError('POSE_GRAPH_SEARCH_TOO_LARGE')

    def covariance(self):
        return np.diag([self.sigma_xy_m**2]*2+[math.radians(self.sigma_yaw_deg)**2])


def insert_row(grid, row, pose):
    hit, miss = grid.hit, grid.miss
    weight = row.get('insertion_weight', 1.)
    grid.hit, grid.miss = hit*weight, miss*weight
    grid.insert(transform([row['camera']], pose)[0], [transform(s, pose) for s in row['segments']])
    grid.hit, grid.miss = hit, miss


def rebuild(robot_id, ledger):
    grid = OdomGrid(robot_id)
    for row in ledger:
        insert_row(grid, row, row['pose'])
    return grid


class ProbabilityField:
    def __init__(self, grid):
        keys = np.array(list(grid.cells))
        self.resolution = grid.resolution_m
        self.lower = keys.min(0)-2
        size = keys.max(0)-self.lower+3
        self.values = np.full(tuple(size), .5)
        for key, value in grid.cells.items():
            self.values[tuple(np.array(key)-self.lower)] = 1/(1+math.exp(-value))

    def query(self, points, order=0):
        shape = points.shape[:-1]
        # Cells are centred at (index+.5)*r. Nearest grid score follows Hess BBS.
        ij = (points.reshape(-1, 2)/self.resolution-.5-self.lower).T
        return map_coordinates(self.values, ij, order=order, mode='constant', cval=.5).reshape(shape)


def make_submaps(robot_id, rows, options):
    submaps, constraints = [], []
    for start in range(0, len(rows), options.stride):
        indices = list(range(start, min(start+options.submap_scans, len(rows))))
        anchor = np.zeros(3) if start == 0 else np.array(rows[start]['pose'])
        grid = OdomGrid(robot_id)
        segments = []
        for j in indices:
            local = between(anchor, rows[j]['pose'])
            insert_row(grid, rows[j], local)
            segments.extend(transform(np.asarray(rows[j]['segments']).reshape(-1, 2), local).reshape(-1, 2, 2))
            constraints.append({'kind':'intra', 'submap':len(submaps), 'scan':j,
                                'relative_pose':local.tolist(), 'covariance':options.covariance().tolist()})
        submaps.append({'pose':anchor, 'members':indices, 'grid':grid,
                        'segments':np.asarray(segments), 'interval':[rows[indices[0]]['t'], rows[indices[-1]]['t']]})
    return submaps, constraints


def match_loop(submap, row, initial, options):
    """Hess Alg.1 exhaustive probability score, continuous refinement, gates.

    Additional mode/normal observability gates reflect our narrow-FOV contacts.
    The frontend prior centres the finite window but cannot manufacture a match.
    """
    o = options
    points = sample_segments(row['segments'])
    event = {'accepted':False, 'reason':'insufficient_points', 'points':len(points)}
    if len(points) < o.min_points or not submap['grid'].cells:
        return event
    field = ProbabilityField(submap['grid'])
    steps = np.array([o.translation_step_m]*2+[math.radians(o.yaw_step_deg)])
    limits = np.array([o.translation_window_m]*2+[math.radians(o.yaw_window_deg)])
    counts = np.floor(limits/steps+1e-8).astype(int)
    offsets = np.stack(np.meshgrid(*[np.arange(-n,n+1)*s for n,s in zip(counts,steps)],indexing='ij'),axis=-1).reshape(-1,3)
    poses = initial+offsets
    scores = np.empty(len(poses))
    for start in range(0,len(poses),512):
        p = poses[start:start+512]
        c, s = np.cos(p[:,2,None]), np.sin(p[:,2,None])
        xy = np.stack([c*points[:,0]-s*points[:,1],s*points[:,0]+c*points[:,1]],axis=-1)+p[:,None,:2]
        scores[start:start+len(p)] = field.query(xy).mean(1)
    best = int(np.argmax(scores))
    candidate = poses[best]
    far = (np.linalg.norm(offsets[:,:2]-offsets[best,:2],axis=1) >= o.mode_distance_m-1e-9) | (abs(offsets[:,2]-offsets[best,2]) >= math.radians(o.mode_yaw_deg)-1e-9)
    gap = float(scores[best]-scores[far].max()) if far.any() else 1.
    event.update(score=float(scores[best]), mode_gap=gap, candidates=len(poses), initial_pose=initial.tolist(),
                 coarse_pose=candidate.tolist(), search_boundary=bool(np.any(abs(offsets[best])>=counts*steps-1e-9)))
    if scores[best] < o.min_score:
        event['reason'] = 'low_probability'
        return event
    if event['search_boundary']:
        event['reason'] = 'search_boundary'
        return event
    if gap < o.mode_gap:
        event['reason'] = 'ambiguous_modes'
        return event
    # Smooth probability residual (Hess CS); bilinear interpolation keeps [.0,1].
    fit = least_squares(lambda p: 1-field.query(transform(points,p),order=1),candidate,
                        bounds=(initial-limits,initial+limits),max_nfev=o.max_nfev,
                        diff_step=1e-4,xtol=1e-8,ftol=1e-8,gtol=1e-8)
    candidate = fit.x
    distance = DistanceField(submap['segments'], .05, 1.)
    world = transform(points,candidate)
    d = distance.query(world)
    overlap, residual = float(np.mean(d<=o.overlap_m)), float(np.sqrt(np.mean(d*d)))
    relative = world-candidate[:2]
    info = distance.information(world,relative,np.full(len(points),o.sigma_xy_m),o.overlap_m,o.effective_points)
    # Nondimensionalize yaw at a 1m lever arm before applying the existing ratio.
    eigen = np.linalg.eigvalsh(info)
    ratio = float(max(0.,eigen[0])/max(eigen[-1],1e-12))
    score = float(field.query(world,order=1).mean())
    boundary = bool(np.any(abs(candidate-initial)>=limits-1e-6))
    event.update(relative_pose=candidate.tolist(), refined_score=score, overlap=overlap, residual_m=residual,
                 hessian_eigenvalues=eigen.tolist(), hessian_ratio=ratio, refinement_success=bool(fit.success))
    reason = ('refinement_failed' if not fit.success else 'search_boundary' if boundary else
              'low_probability' if score < o.min_score else 'low_overlap' if overlap < o.min_overlap else
              'high_residual' if residual > o.max_residual_m else 'unobservable' if ratio < o.hessian_ratio else 'accepted')
    event['reason'], event['accepted'] = reason, reason == 'accepted'
    if event['accepted']:
        event['covariance'] = (np.linalg.inv(info)+o.covariance()).tolist()
    return event


def robust_block(residual, delta):
    """Exact Huber on a whitened SE(2) residual *block*, not each component."""
    norm = np.linalg.norm(residual,axis=-1)
    rho = np.where(norm<=delta,norm**2,2*delta*norm-delta**2)
    return residual*np.sqrt(rho/np.maximum(norm**2,1e-30))[...,None]


def optimize(submaps, rows, constraints, options):
    """Hess SPA residuals; first submap constant, Huber only inter-submap."""
    m, n = len(submaps), len(rows)
    initial = np.vstack([s['pose'] for s in submaps]+[r['pose'] for r in rows])
    a = np.array([c['submap'] for c in constraints])
    b = np.array([m+c['scan'] for c in constraints])
    target = np.array([c['relative_pose'] for c in constraints])
    whiten = np.array([np.linalg.cholesky(np.linalg.inv(c['covariance'])).T for c in constraints])
    loops = np.array([c['kind']=='loop' for c in constraints])
    fixed = initial[0].copy()
    def unpack(x):
        return np.vstack([fixed,x.reshape(-1,3)])
    def residual(x):
        p = unpack(x)
        e = between(p[a],p[b])-target
        e[:,2] = wrap(e[:,2])
        r = np.einsum('nij,nj->ni',whiten,e)
        r[loops] = robust_block(r[loops],options.huber_delta)
        return r.ravel()
    sparsity = lil_matrix((3*len(constraints),3*(m+n-1)),dtype=int)
    for i,(ia,ib) in enumerate(zip(a,b)):
        for j in (ia,ib):
            if j:
                sparsity[3*i:3*i+3,3*(j-1):3*j] = 1
    x = initial[1:].ravel()
    before = float(residual(x)@residual(x)/2)
    fit = least_squares(residual,x,jac_sparsity=sparsity.tocsr(),method='trf',tr_solver='lsmr',
                        max_nfev=options.max_nfev,ftol=1e-7,xtol=1e-7,gtol=1e-7)
    valid = bool(fit.success and np.isfinite(fit.x).all() and fit.cost<=before+1e-10)
    result = unpack(fit.x) if valid else initial
    result[:,2] = wrap(result[:,2])
    return result, {'accepted':valid,'reason':'converged' if valid else 'optimizer_failed',
                    'initial_cost':before,'final_cost':float(fit.cost),'nfev':fit.nfev,'status':fit.status,
                    'message':fit.message,'max_translation_change_m':float(np.linalg.norm(result[:,:2]-initial[:,:2],axis=1).max())}


def validate_rows(rows, robot_id):
    keys, last = set(), -math.inf
    for row in rows:
        if row.get('robot_id') != robot_id:
            raise ValueError('POSE_GRAPH_PEER_INPUT_FORBIDDEN')
        if row['frame_id'] in keys or not math.isfinite(row['t']) or row['t'] <= last:
            raise ValueError('POSE_GRAPH_DUPLICATE_OR_UNORDERED_SCAN')
        keys.add(row['frame_id'])
        last = row['t']
        segments, camera, pose = np.asarray(row['segments']), np.asarray(row['camera']), np.asarray(row['pose'])
        if (segments.ndim != 3 or segments.shape[1:] != (2,2) or not len(segments) or
                camera.shape != (2,) or pose.shape != (3,) or
                not all(np.isfinite(v).all() for v in (segments,camera,pose))):
            raise ValueError('POSE_GRAPH_INVALID_GEOMETRY')
        if np.linalg.norm(segments-camera,axis=-1).max() >= 4.+1e-10:
            raise ValueError('POSE_GRAPH_RANGE_GATE_REQUIRED')
        if not 0 < row.get('insertion_weight',1.) <= 1:
            raise ValueError('POSE_GRAPH_INVALID_WEIGHT')


def apply_pose_graph(rows, poses, *, robot_id, pose_graph='off', options=None):
    """Off returns original objects without inspecting input or loading a graph.

    On requires an explicit own-robot id per scan/pose. Call only after positive-
    depth and settle/range admission; intrinsic camera data never enters SPA.
    """
    if pose_graph not in VALUES:
        raise ValueError('UNKNOWN_POSE_GRAPH')
    if pose_graph == 'off':
        return rows, poses, None
    o = GraphOptions(**(options or {}))
    validate_rows(rows,robot_id)
    stamps = [p['t'] for p in poses]
    if any(p.get('robot_id')!=robot_id for p in poses):
        raise ValueError('POSE_GRAPH_PEER_INPUT_FORBIDDEN')
    if any(not np.isfinite(p['pose']).all() or np.asarray(p['pose']).shape!=(3,) or not math.isfinite(p['t']) for p in poses) or any(b<=a for a,b in zip(stamps,stamps[1:])):
        raise ValueError('POSE_GRAPH_INVALID_PATH')
    if not rows:
        return copy.deepcopy(rows), copy.deepcopy(poses), {'options':asdict(o),'submaps':[], 'constraints':[], 'loops':[],
            'loop_counts':{},'optimization':{'accepted':False,'reason':'empty_ledger'}, 'changed':False}
    submaps, constraints = make_submaps(robot_id,rows,o)
    events = []
    for i,submap in enumerate(submaps):
        for j,row in enumerate(rows):
            event = {'submap':i,'scan':j,'frame_id':row['frame_id'],'accepted':False}
            if j in submap['members']:
                event['reason'] = 'member_scan'
            elif submap['interval'][0]-o.separation_s < row['t'] < submap['interval'][1]+o.separation_s:
                event['reason'] = 'temporal_separation'
            else:
                initial = between(submap['pose'],row['pose'])
                pts = submap['grid'].occupied_points()
                if not len(pts) or np.min(np.linalg.norm(pts-initial[:2],axis=1))>o.candidate_distance_m:
                    event['reason'] = 'outside_candidate_radius'
                else:
                    event.update(match_loop(submap,row,initial,o))
            events.append(event)
            if event['accepted']:
                constraints.append({'kind':'loop','submap':i,'scan':j,'relative_pose':event['relative_pose'],
                                    'covariance':event['covariance']})
    changed = any(e['accepted'] for e in events)
    diagnostic = {'options':asdict(o),'loops':events,'loop_counts':dict(Counter(e['reason'] for e in events)),
                  'constraints':constraints}
    corrected, path = copy.deepcopy(rows), copy.deepcopy(poses)
    if changed:
        solution, diagnostic['optimization'] = optimize(submaps,rows,constraints,o)
        changed = diagnostic['optimization']['accepted']
        if changed:
            for row,pose in zip(corrected,solution[len(submaps):]):
                row['pose'] = pose.tolist()
            times = np.array([r['t'] for r in rows])
            for p in path:
                idx = int(np.searchsorted(times,p['t'],side='right')-1)
                if idx>=0:
                    p['pose'] = compose(corrected[idx]['pose'],between(rows[idx]['pose'],p['pose'])).tolist()
    else:
        solution = np.vstack([s['pose'] for s in submaps]+[r['pose'] for r in rows])
        diagnostic['optimization'] = {'accepted':False,'reason':'no_loop_constraints'}
    diagnostic['changed'] = changed
    diagnostic['submaps'] = [{'id':i,'local_pose':s['pose'].tolist(),'global_pose':solution[i].tolist(),
                              'members':[rows[j]['frame_id'] for j in s['members']], 'interval':s['interval'],
                              'cells':s['grid'].export()['cells']} for i,s in enumerate(submaps)]
    return corrected,path,diagnostic
