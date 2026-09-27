"""Expected target occupancy from an active own pair job, RGB and static order.

This semantic exclusion does not remove any beam/wall collision geometry.
Ambiguous/merged components remain obstacles. No world or peer pose is read.
"""
import copy
import math

import cv2
import numpy as np

from harness.owncam_pair_beam_v2 import observe_beam
from harness.owncam_view import base_rays
from harness.owncam_time import pose_report_fresh, finite_time


def target_context(own, report, now):
    ep, job = getattr(own, '_pair', None), own.job
    if (ep is None or ep.terminal or job is None or job.kind != 'pair_carry'
            or job.args.get('order_id') != ep.arguments.get('order_id')
            or not pose_report_fresh(report, now) or not report.initialized):
        return None
    order = own.orders.get(job.args['order_id'], {})
    if order.get('kind') != 'long_beam' or order.get('count') != 1:
        return None
    from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD
    from harness.zone_own_guards import GATE_LOADED
    if not all(finite_time(v) for v in (report.x_m, report.y_m, report.yaw_rad)):
        return None
    if not (0 <= report.std_xy_m <= GATE_LOADED.high_xy_m and 0 <= report.std_yaw_rad <= GATE_LOADED.high_yaw_rad):
        return None
    # Propagate a copy using own issued commands; never mutate/renew a safety anchor.
    track = copy.deepcopy(ep.command_guard.beam_track)
    track.advance(now)
    b = track.beam
    if b is not None and track.segment == ep.controller.seg:
        from harness.zone_pair_beam_track import MAX_AGE_S
        if (not 0 <= now - b['anchor_time_s'] <= MAX_AGE_S
                or not 0 <= b['std_xy_m'] <= FIX_STD_XY_M
                or not 0 <= b['std_yaw_rad'] <= FIX_STD_YAW_RAD
                or b.get('prediction_time_s') != now):
            return None
        grip, heading = b['grip_base_m'], b['axis_heading_rad']
        xy_slack, yaw_slack = 2 * b['std_xy_m'], 2 * b['std_yaw_rad']
        source = 'own segment RGB anchor + issued commands'
    elif ep.controller.seg == 0 and not ep.command_guard.carrying_beam:
        # Only the initial pickup may use the fixed coarse order; never use a
        # planned checkpoint as a measurement after the cargo has moved.
        sheet = ep.plan['sheet']; x, y, yaw = sheet['beam_xyyaw']
        sign = -1 if ep.arguments['role'] == 'end_neg' else 1
        x += sign * .27 * math.cos(yaw); y += sign * .27 * math.sin(yaw)
        c, s = math.cos(report.yaw_rad), math.sin(report.yaw_rad)
        dx, dy = x - report.x_m, y - report.y_m
        grip = [c * dx + s * dy, -s * dx + c * dy]
        heading = yaw + (math.pi if sign == 1 else 0) - report.yaw_rad
        xy_slack = math.sqrt(2) * sheet['grid']['xy_m'] / 2 + 2 * report.std_xy_m
        yaw_slack = sheet['grid']['yaw_rad'] / 2 + 2 * report.std_yaw_rad
        source = 'static coarse order + own pose'
    else:
        return None
    return {'order_id': job.args['order_id'], 'grip_base_m': list(grip), 'axis_heading_rad': heading,
            'xy_slack_m': xy_slack, 'yaw_slack_rad': yaw_slack, 'source': source,
            'allow_shape_identity': bool(getattr(getattr(ep,'policy',None),'beam_relative',False))}


def target_component(frame, model, labels, index, pose, target):
    """Require band/full-shape identity, association and whole-component support.

    A yellow component alone is insufficient. The small shadow allowance must
    match floor chromaticity and be dimmer; arbitrary residual pixels, another
    colour or a geometrically incompatible merged object prevents exclusion.
    """
    if target is None or not all(finite_time(v) for v in (
            *target['grip_base_m'], target['axis_heading_rad'], target['xy_slack_m'], target['yaw_slack_rad'])):
        return None
    mask = labels == index
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # The bright top clips toward yellow; side faces retain catalogue lime.
    colour = cv2.inRange(hsv, np.array([27, 60, 40]), np.array([54, 255, 255])) > 0
    dark = hsv[..., 2] <= 60
    f, floor = frame.astype(float), model.astype(float)
    ratio = f.sum(axis=2) / np.maximum(floor.sum(axis=2), 1)
    shadow = ((ratio >= .35) & (ratio < 1) &
              (np.max(np.abs(f - floor * ratio[..., None]), axis=2) <= 25))
    area = int(mask.sum())
    if (not area or (colour & mask).sum() / area < .75
            or ((colour | dark | shadow) & mask).sum() / area < .98):
        return None
    beam = observe_beam(frame, pose)
    if not beam.get('end_visible') or beam.get('grip_source') != 'band_centre':
        if not target.get('allow_shape_identity',False):
            return None
        # The v6 A flag allows a complete catalogue shape instead of a band.
        # Partial endpoint updates cannot establish semantic object identity.
        from harness.zone_pair_relative import shape_fit
        from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD
        beam, _ = shape_fit(frame,pose)
        if (beam is None or beam['std_xy_m']+beam['bias_bound_m'] > FIX_STD_XY_M
                or beam['std_yaw_rad'] > FIX_STD_YAW_RAD):
            return None
    delta = math.atan2(math.sin(beam['axis_heading_rad'] - target['axis_heading_rad']),
                       math.cos(beam['axis_heading_rad'] - target['axis_heading_rad']))
    if (math.dist(beam['grip_base_m'], target['grip_base_m']) > target['xy_slack_m']
            or abs(delta) > target['yaw_slack_rad']):
        return None
    origin, rays, xs, ys, valid = base_rays(pose, 2)
    xi, yi = xs.astype(int), ys.astype(int)
    hit = mask[yi, xi] & colour[yi, xi] & valid & (rays[:, 2] < -1e-6)
    distance = (.032 - origin[2]) / rays[hit, 2]
    points = origin[:2] + distance[:, None] * rays[hit, :2]
    u = np.array([math.cos(beam['axis_heading_rad']), math.sin(beam['axis_heading_rad'])])
    rel = points - np.array(beam['grip_base_m'])
    along, across = rel @ u, rel @ np.array([-u[1], u[0]])
    # Top-plane projection of the 32 mm end face extends toward the camera;
    # retain a small geometric allowance, independent of control clearances.
    pad = target['xy_slack_m']
    support = (distance > 0) & (along >= -.03 - pad) & (along <= .57 + pad) & (abs(across) <= .04)
    if len(points) < 60 or support.mean() < .98:
        return None
    # Dark/shadow appendages outside the narrow pixel envelope are ambiguous.
    ys_c, xs_c = np.nonzero(mask & colour)
    ys_m, xs_m = np.nonzero(mask)
    if (xs_m.min() < xs_c.min() - 30 or xs_m.max() > xs_c.max() + 5
            or ys_m.min() < ys_c.min() - 5 or ys_m.max() > ys_c.max() + 5):
        return None
    return {'order_id': target['order_id'], 'source': target['source'],
            'classification': 'expected_target_occupancy', 'support_fraction': float(support.mean()),
            'grip_base_m': beam['grip_base_m']}
