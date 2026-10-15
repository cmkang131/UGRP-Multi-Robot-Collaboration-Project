"""Finite pickup-region camera search from static map + own command pose.

This is navigation before the local teacher, not a grasp controller. A cell
is a patch of static floor, never a predicted cargo location. No simulator,
scene placements, target coordinates or top camera are accepted here.
"""
from __future__ import annotations

import math

PROFILE = 'static_pickup_scan_v1'
CELL_M = .6
DWELL_S = .6  # starts AFTER the final PWM target has been issued


def floor_cells(region):
    """Boustrophedon coverage of the authored pickup rectangle, west first."""
    x, y = region['center_m']; hx, hy = region['half_extents_m']
    nx, ny = math.ceil(2*hx/CELL_M), math.ceil(2*hy/CELL_M)
    return [(x-hx+(i+.5)*2*hx/nx, y-hy+(j+.5)*2*hy/ny)
            for i in range(nx)
            for j in (range(ny) if i % 2 == 0 else reversed(range(ny)))]


class PickupSearch:
    def __init__(self, static, loc, ops):
        self.cells = floor_cells(static['regions']['pickup'])
        self.loc, self.ops = loc, ops
        self.index = 0
        self.goal_pwm = None
        self.reached_t = None
        self.views = []
        self.failure = None

    def step(self, now, pwm):
        if not self.loc.ready(now):
            self.failure = 'pickup_search_self_pose_unavailable'
        if self.failure:
            return dict(pwm), self.failure
        if self.reached_t is not None and now-self.reached_t >= DWELL_S-1e-8:
            self.views.append({'index': self.index, 'floor_xy': self.cells[self.index],
                               'command_reached_t': self.reached_t, 'end_t': now,
                               'pwm': dict(self.goal_pwm)})
            self.index += 1
            self.goal_pwm = self.reached_t = None
        if self.index == len(self.cells):
            self.failure = 'pickup_search_exhausted'
            return dict(pwm), self.failure
        if self.goal_pwm is None:
            x, y, yaw = self.loc.pose
            dx, dy = self.cells[self.index][0]-x, self.cells[self.index][1]-y
            c, s = math.cos(yaw), math.sin(yaw)
            # Reuse calibrated gaze/FK; the lens, FOV and robot do not change.
            self.goal_pwm = self.ops.gaze((c*dx+s*dy, -s*dx+c*dy, 0.), pwm)
        updated = self.ops.slew(pwm, self.goal_pwm)
        if updated == self.goal_pwm and self.reached_t is None:
            self.reached_t = now
        return updated, None

    def record(self):
        return {'profile': PROFILE, 'cell_index': self.index, 'cell_count': len(self.cells),
                'floor_xy': self.cells[self.index] if self.index < len(self.cells) else None,
                'goal_pwm': self.goal_pwm, 'command_reached_t': self.reached_t,
                'completed_views': len(self.views), 'dwell_s': DWELL_S,
                'failure': self.failure, 'source': 'static_pickup_region_and_own_command_pose',
                'command_reached_is_measured_servo': False}
