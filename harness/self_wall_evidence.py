"""Separate, non-probabilistic TSDF fusion support for an own occupancy map.

Cartographer TSDF insertion equations/defaults, independently implemented. The
occupancy grid and its hit/free evidence remain untouched. TSDF weight is NOT a
calibrated probability of a true wall. Angle diversity is reported separately.
"""
from __future__ import annotations

import math
import numpy as np

from harness.self_odom_grid import ray_cells, transform
from harness.self_pose_graph import validate_rows

VALUES = ('off', 'tsdf_weight_v1')
TRUNCATION_M = .3
MAX_WEIGHT = 10.
ANGLE_BANDWIDTH_RAD = .5
DISTANCE_BANDWIDTH_M = .5


def gaussian(value, sigma):
    return math.exp(-.5*(value/sigma)**2)/(math.sqrt(2*math.pi)*sigma)


def build_evidence(rows, *, robot_id, wall_evidence='off', resolution_m=.1):
    if wall_evidence not in VALUES:
        raise ValueError('UNKNOWN_WALL_EVIDENCE')
    if wall_evidence == 'off':
        return None
    if not math.isfinite(resolution_m) or resolution_m <= 0:
        raise ValueError('INVALID_EVIDENCE_RESOLUTION')
    validate_rows(rows, robot_id)
    cells = {}
    for row in rows:
        origin = transform([row['camera']], row['pose'])[0]
        hits = []
        for a, b in [transform(s, row['pose']) for s in row['segments']]:
            tangent = b-a
            length = float(np.linalg.norm(tangent))
            if length < 1e-12:
                continue
            normal = np.array([-tangent[1], tangent[0]])/length
            if normal @ (origin-(a+b)/2) < 0:
                normal = -normal
            count = max(2, int(math.ceil(length/(resolution_m/2)))+1)
            for hit in np.linspace(a, b, count):
                ray = hit-origin
                distance = float(np.linalg.norm(ray))
                if distance < TRUNCATION_M:
                    continue
                bearing = math.atan2(ray[1], ray[0])
                angle = math.acos(float(np.clip(normal @ (-ray/distance), -1., 1.)))
                hits.append((bearing, hit, normal, distance, gaussian(angle, ANGLE_BANDWIDTH_RAD)))
        # Same first angularly ordered ray / once per scan cell policy as TSDF2D.
        updated = set()
        for bearing, hit, normal, distance, angle_weight in sorted(hits, key=lambda x:x[0]):
            ray = hit-origin
            begin = origin+(1-TRUNCATION_M/distance)*ray
            end = origin+(1+TRUNCATION_M/distance)*ray
            for key in ray_cells(begin, end, resolution_m):
                if key in updated:
                    continue
                center = (np.asarray(key)+.5)*resolution_m
                sdf = float(np.clip((center-hit) @ normal, -TRUNCATION_M, TRUNCATION_M))
                weight = angle_weight*gaussian(sdf, DISTANCE_BANDWIDTH_M)
                old = cells.get(key, dict(sdf_m=0., weight=0., observations=0, cos_sum=0., sin_sum=0.))
                combined = old['weight']+weight
                old['sdf_m'] = (old['sdf_m']*old['weight']+sdf*weight)/combined
                old['weight'] = min(combined, MAX_WEIGHT)
                old['observations'] += 1
                old['cos_sum'] += math.cos(bearing)
                old['sin_sum'] += math.sin(bearing)
                cells[key] = old
                updated.add(key)
    exported = []
    for key, value in sorted(cells.items()):
        n = value['observations']
        diversity = 1-math.hypot(value['cos_sum'], value['sin_sum'])/n
        exported.append(dict(cell=[int(k) for k in key], sdf_m=value['sdf_m'], weight=value['weight'],
                             support_score=value['weight']/MAX_WEIGHT, observations=n,
                             view_circular_variance=float(np.clip(diversity, 0., 1.))))
    return dict(schema='ugrp.self_map.tsdf_evidence_v1', robot_id=robot_id,
                frame='own start chassis: x forward, y left, metres', resolution_m=resolution_m,
                semantics='fusion support, NOT probability of a correct wall',
                parameters=dict(truncation_m=TRUNCATION_M, maximum_weight=MAX_WEIGHT,
                                angle_bandwidth_rad=ANGLE_BANDWIDTH_RAD, distance_bandwidth_m=DISTANCE_BANDWIDTH_M,
                                range_exponent=0, update_free_space=False), cells=exported)
