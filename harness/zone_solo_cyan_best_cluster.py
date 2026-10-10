"""S2 report adapter: Nav2 connected-bin maximum-mass pose, default off.

navigation2 235fc5ce pf_kdtree.c / pf.c / amcl_node.cpp (LGPL-2.1+).
The measurement, prediction and resampling distributions are untouched.
"""
import copy
import hashlib
import math

import numpy as np
from scipy.ndimage import label

from harness.zone_solo_cyan_global_start import cluster_labels, maximum_mode

OPTION = 'amcl_best_cluster_v1'
PARAMS = dict(bin_xy_m=.5, bin_yaw_deg=10., yaw_wrap=False,
              uncertain_maximum_mass_below=.5, covariance='overall_filter',
              uncertainty_action='record_only')


def connected_labels(px):
    """Same 27-neighbor partition as the Nav2 kd-tree, vectorized dense grid.

    IDs use first particle order; extract reproduces kd-tree allocation order
    for exact mass ties. No weight pruning or yaw seam connection.
    """
    keys = np.floor(px / [.5, .5, math.pi/18]).astype(np.int64)
    keys -= keys.min(axis=0)
    shape = keys.max(axis=0) + 1
    if math.prod(map(int, shape)) > 2_000_000:
        return cluster_labels(px)  # Identical partition, bounded grid memory.
    grid = np.zeros(shape, dtype=bool)
    grid[tuple(keys.T)] = True
    labels, _ = label(grid, structure=np.ones((3, 3, 3), dtype=bool))
    raw = labels[tuple(keys.T)]
    values, first = np.unique(raw, return_index=True)
    remap = np.zeros(int(raw.max())+1, dtype=int)
    remap[values[np.argsort(first)]] = np.arange(len(values))
    return remap[raw]


def tie_order(px, labels):
    """Nav2 insert_node leaf splitting/allocation, then reverse node traversal.

    Only needed for equal maximum masses; connectivity itself uses the faster
    equivalent grid partition. Repeated keys add weight without allocating.
    """
    keys = [tuple(k) for k in np.floor(px/[.5, .5, math.pi/18]).astype(int)]
    groups = dict(zip(keys, map(int, labels)))
    nodes = [dict(key=keys[0])]
    for key in dict.fromkeys(keys):
        i = 0
        while 'children' in nodes[i]:
            node = nodes[i]
            i = node['children'][int(key[node['dim']] >= node['pivot'])]
        node = nodes[i]; old = node['key']
        if old == key: continue
        dim = int(np.argmax([abs(a-b) for a, b in zip(key, old)]))
        pivot = (key[dim]+old[dim])/2
        children = (key, old) if key[dim] < pivot else (old, key)
        node.update(dim=dim, pivot=pivot, children=[len(nodes), len(nodes)+1])
        nodes.extend(dict(key=k) for k in children)
    return list(dict.fromkeys(groups[n['key']] for n in reversed(nodes) if 'children' not in n))


def extract(px, weights, labels, old):
    """getMaxWeightHyp pose; publishAmclPose overall (not cluster) covariance."""
    w = weights / weights.sum()
    mass = np.bincount(labels, weights=w)
    if np.count_nonzero(mass == mass.max()) > 1:
        order = tie_order(px, labels)
        mapping = np.empty(len(mass), dtype=int)
        mapping[order] = np.arange(len(mass))
        labels = mapping[labels]
    mean, cluster_cov, modes = maximum_mode(px, w, labels)
    center = w @ px[:, :2]
    delta = px[:, :2] - center
    cov = np.zeros((3, 3))
    cov[:2, :2] = (w[:, None] * delta).T @ delta
    resultant = math.hypot(w @ np.cos(px[:, 2]), w @ np.sin(px[:, 2]))
    cov[2, 2] = max(0., -2*math.log(max(resultant, 1e-300)))
    yaw = mean[2] + old.get('pan_yaw_offset', 0.)
    modes.update(uncertain=bool(modes['cluster_count'] > 1 and
        modes['maximum_cluster_weight'] < PARAMS['uncertain_maximum_mass_below']),
        selected_cluster_cov=cluster_cov.tolist(), overall_mean_xy=center.tolist())
    return {**old, 'x': float(mean[0]), 'y': float(mean[1]),
            'yaw': math.atan2(math.sin(yaw), math.cos(yaw)), 'cov': cov.tolist(),
            'std_xy_m': float(np.sqrt(np.trace(cov[:2, :2]))),
            'std_yaw_rad': float(np.sqrt(cov[2, 2])), 'best_cluster': modes}


def install(source):
    """At loc.estimate, before PoseReport/delay/control, survives PF handoff."""
    inner = source.provider
    loc = inner.loc
    pf = loc._pf
    previous = loc.estimate
    cache = dict(key=None, labels=None)
    audit = dict(option=OPTION, parameters=copy.deepcopy(PARAMS), gt_inputs=False,
                 rows=[], filter_distribution_changed=False)

    def estimate():
        old = previous()
        if not old.get('initialized'):
            return old
        # px mutates in place on prediction, not just resampling. Never cache
        # by resample count/time alone; weights are recomputed on every call.
        key = hashlib.blake2b(pf.px.tobytes(), digest_size=16).digest()
        if key != cache['key']:
            cache.update(key=key, labels=connected_labels(pf.px))
        out = extract(pf.px, pf._weights(), cache['labels'], old)
        modes = out['best_cluster']
        pf.diag['pose_estimate'] = copy.deepcopy(modes)
        row = dict(t=float(pf.t), **copy.deepcopy(modes))
        if not audit['rows'] or audit['rows'][-1] != row:
            audit['rows'].append(row)
        return out

    loc.estimate = estimate
    from harness.zone_solo_cyan_v106 import hp
    inner.runtime_contract['s2_pose_estimate'] = dict(option=OPTION, parameters=PARAMS)
    inner.identity_sha256 = hp.base.digest(inner.runtime_contract)
    inner.source = 'owncam_pf_s2_best_cluster:' + inner.identity_sha256[:8]
    source.source = inner.source
    return audit


def runtime_class(previous):
    class Runtime(previous):
        def __init__(self, *args, pose_estimate='off', **kwargs):
            if pose_estimate not in ('off', OPTION):
                raise ValueError('unknown pose_estimate')
            super().__init__(*args, **kwargs)
            self.pose_estimate = pose_estimate
            if pose_estimate != 'off':
                self.best_cluster_audit = install(self.pose)

        def record(self):
            out = super().record()
            if self.pose_estimate != 'off':
                out['pose_estimate'] = copy.deepcopy(self.best_cluster_audit)
            return out

        def on_frames(self, now, frames):
            super().on_frames(now, frames)
            if self.pose_estimate != 'off':
                quality = self.last_report.observation_quality or {}
                modes = quality.get('diagnostics', {}).get('pose_estimate', {})
                if modes.get('uncertain'):
                    self.soft('POSE_CLUSTER_UNCERTAIN', now)
    return Runtime
