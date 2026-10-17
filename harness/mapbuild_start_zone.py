"""Default-off coarse operator/authored-zone prior, never derived from spawn.

User decision PR571 permits a region and rough heading only. The .5m box and
30-degree half-width are the coordinator's design, not a fitted success gate.
"""
import math
import numpy as np

OPTION = 'start_zone_prior_v1'
SCHEMA = 'ugrp.coarse_start_zone.v1'


def sample(field, static_map, prior, rng, n):
    required = {'schema', 'zone_id', 'map_id', 'bounds_m', 'heading_center_rad',
                'heading_half_width_rad', 'source_kind', 'source_evidence'}
    if not isinstance(prior, dict) or set(prior) != required:
        raise ValueError('COARSE_ZONE_SCHEMA_ONLY_NO_EXACT_POSE')
    if (prior['schema'] != SCHEMA or prior['map_id'] != static_map.get('map_id') or
            prior['source_kind'] not in ('operator_coarse', 'authored_static_zone') or
            not isinstance(prior['source_evidence'], str) or not prior['source_evidence'].strip() or
            not isinstance(prior['zone_id'], str) or not prior['zone_id'].strip()):
        raise ValueError('COARSE_ZONE_PROVENANCE_REQUIRED')
    box = np.asarray(prior['bounds_m'], float)
    heading, half = float(prior['heading_center_rad']), float(prior['heading_half_width_rad'])
    if (box.shape != (4,) or not np.isfinite(box).all() or not math.isfinite(heading) or
            not math.isfinite(half) or box[1] <= box[0] or box[3] <= box[2] or
            not math.pi/6 <= half <= math.pi):
        raise ValueError('REGION_AND_ROUGH_HEADING_REQUIRED')
    if prior['source_kind'] == 'operator_coarse' and min(box[1]-box[0], box[3]-box[2]) < .5-1e-12:
        raise ValueError('OPERATOR_ZONE_MINIMUM_HALF_METRE')
    # An authored zone may be smaller only if its literal map field agrees.
    if prior['source_kind'] == 'authored_static_zone':
        entry = static_map.get('start_zones', {}).get(prior['zone_id'])
        if not isinstance(entry, dict) or entry.get('bounds_m') != prior['bounds_m']:
            raise ValueError('AUTHORED_START_ZONE_NOT_FOUND')
    xy = field.free
    xy = xy[(xy[:, 0]>=box[0])&(xy[:, 0]<=box[1])&(xy[:, 1]>=box[2])&(xy[:, 1]<=box[3])]
    if not len(xy):
        raise ValueError('START_ZONE_HAS_NO_STATIC_FREE_SPACE')
    # Enumerated free cells bound work; no wall-clock rejection-sampling loop.
    selected = xy[rng.integers(len(xy), size=n)]
    yaw = heading+rng.uniform(-half, half, n)
    return np.column_stack((selected, np.arctan2(np.sin(yaw), np.cos(yaw))))
