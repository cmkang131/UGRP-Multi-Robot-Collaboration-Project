"""Opt-in association of a partial B extent with a complete own RGB boundary.

The partial patch centroid is not a complete-region measurement. Require
overlapping measured extents and three fresh stable complete detections. No
missing edge, marker, pose, successful arrival or free corridor is invented.
"""
import copy
import math
import cv2
import numpy as np

OPTION = 'extent_v1'
PARAMS = dict(min_overlap_fraction=.20, stable_center_m=.10, frames=3,
              max_gap_s=.5, min_span_s=.2)


def overlap(candidate, boundary):
    if (candidate.get('kind') != 'B' or candidate.get('source') != 'own' or
            not candidate.get('observation', {}).get('partial_extent')):
        return 0.
    if not boundary or not boundary.get('complete') or boundary.get('white_markers') != 3:
        return 0.
    bounds = np.asarray(candidate['observation'].get('bounds_m', []), float)
    polygon = np.asarray(boundary.get('polygon', []), np.float32)
    if (bounds.shape != (2, 2) or polygon.shape != (4, 2) or
            not np.isfinite(bounds).all() or not np.isfinite(polygon).all() or
            np.any(bounds[1] <= bounds[0]) or not cv2.isContourConvex(polygon)):
        return 0.
    (x0, y0), (x1, y1) = bounds
    rectangle = np.array([[x0,y0], [x1,y0], [x1,y1], [x0,y1]], np.float32)
    denominator = min(cv2.contourArea(rectangle), cv2.contourArea(polygon))
    if denominator <= 1e-8: return 0.
    area, _ = cv2.intersectConvexConvex(rectangle, polygon)
    return float(area / denominator)


class Association:
    def __init__(self, goal):
        self.goal = goal
        self.rows = []
        self.last = None

    def observe(self):
        g = self.goal
        candidate, row = g.entities.get('B'), g.e2e_gate.current
        if candidate is None or row is None: return
        reference = g.e2e_gate.references.get('B')
        if reference is not None:
            # GoalRoute refreshes the old partial centroid every image. Keep
            # the endpoint attached to the actual remembered complete image.
            candidate['center_m'] = list(reference['boundary']['center'])
            return
        boundary = row['boundary']
        fraction = overlap(candidate, boundary)
        self.last = dict(overlap_fraction=fraction, accepted=False, frames=0)
        if fraction < PARAMS['min_overlap_fraction']:
            self.rows.clear(); return
        ref, center = row['ref'], boundary['center']
        if self.rows:
            previous = self.rows[-1]
            if ref['frame_id'] == previous['ref']['frame_id']: return
            if (not 0 < ref['t_sim']-previous['ref']['t_sim'] <= PARAMS['max_gap_s'] or
                    ref['frame_id'] <= previous['ref']['frame_id'] or
                    any(math.dist(center, r['center']) > PARAMS['stable_center_m'] for r in self.rows)):
                self.rows.clear()
        self.rows.append(dict(ref=copy.deepcopy(ref), center=list(center)))
        del self.rows[:-PARAMS['frames']]
        self.last['frames'] = len(self.rows)
        if (len(self.rows) == PARAMS['frames'] and
                ref['t_sim']-self.rows[0]['ref']['t_sim'] >= PARAMS['min_span_s']-1e-8):
            old_center = list(candidate['center_m'])
            g.e2e_gate.remember_B()
            candidate['center_m'] = list(boundary['center'])
            self.last.update(accepted=True, old_partial_center=old_center,
                             complete_center=list(boundary['center']), sources=copy.deepcopy(self.rows))
            g.event(ref['t_sim'], 'B_partial_extent_associated', **self.last)


def install(goal, option='off'):
    if option == 'off': return goal
    if option != OPTION: raise ValueError('UNKNOWN_BOUNDARY_ASSOCIATION')
    association = Association(goal)
    goal.boundary_association = association
    observe, receive = goal.own_rgb_received, goal.receive
    def observed(**kwargs):
        observe(**kwargs)
        association.observe()
    def received(**kwargs):
        command, trace = receive(**kwargs)
        trace['boundary_association'] = copy.deepcopy(association.last)
        return command, trace
    goal.own_rgb_received, goal.receive = observed, received
    return goal
