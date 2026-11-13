"""Pinned c7232b9 controller; oracle initializer removed. Facing is ego-relative."""
from __future__ import annotations

import math
import random

import cv2
import numpy as np

# Arm posture of the teacher's approach as a function of the base-to-box distance (servos 3 and 4): the median
# commanded values over the 48 clean demos (approach ticks, GT distance bins; work record). Servos 1 (2000) and
# 5 (1320) are constant; servo 6 (pan) is fixed at 1500 so that the image column of the box measures bearing.
TILT_SCHEDULE = [(0.20, 500, 2500), (0.25, 640, 2440), (0.30, 700, 2440), (0.35, 740, 2380),
                 (0.45, 780, 2380), (0.55, 760, 2360), (0.60, 740, 2320), (1.05, 740, 2320)]
FAR_POSTURE = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


def posture_for(d_m):
    """Arm posture at a base-to-box distance (piecewise linear in TILT_SCHEDULE)."""
    pts = TILT_SCHEDULE
    if d_m <= pts[0][0]:
        t3, t4 = pts[0][1], pts[0][2]
    elif d_m >= pts[-1][0]:
        t3, t4 = pts[-1][1], pts[-1][2]
    else:
        for (d0, a0, b0), (d1, a1, b1) in zip(pts, pts[1:]):
            if d0 <= d_m <= d1:
                f = (d_m - d0) / (d1 - d0)
                t3, t4 = a0 + f * (a1 - a0), b0 + f * (b1 - b0)
                break
    return {1: 2000, 3: int(round(t3)), 4: int(round(t4)), 5: 1320, 6: 1500}


# Stop reference (teacher stop frames, largest blob): centre column, row, area window.
CX_REF_PX = 286.9       # pan 1500, zero bearing (pan regression on the stop frames, residual 1.5 px)
CY_REF_PX = 327.1       # tilt (500, 2500) at the stop (recorded only, not an arrival condition)
A_REF_PX = 21289.0      # p50 (p10 20506, p90 21947)
A_LO_PX = 20506.0
A_HI_PX = 21947.0
D_STOP_M = 0.20
K_BEARING_PX_PER_RAD = 680.5

# Geometry of the fixed stop (world frame; teacher demos).
STATION_OFFSET_M = 0.20       # stop point: 0.20 m west of the box centre
PRE_STATION_OFFSET_M = 0.40   # stage A ends here: 0.40 m west of the box centre

# Pulse control (wheel speed is always 0.35, the allowed magnitude; the duration sets the step). 0.10 s is the
# physical limit: a longer pulse overlaps the next 0.1 s tick. Calibration (speed 0.35, pulse + 2 rest ticks):
#   forward 0.10 s -> 11.1 mm;  turn 0.10 s -> 0.094 rad;  turn 0.05 s -> 0.019 rad (noisy);  strafe 0.10 s -> 10.2 mm.
PULSE_SPEED = 0.35
PULSE_MIN_S, PULSE_MAX_S = 0.05, 0.10
K_FWD_S_PER_M = 9.0           # image stage: 0.111 m/s per pulse-second -> 9 pulse-seconds per metre
TURN_SHORT_S, TURN_LONG_S = 0.05, 0.10
TURN_LONG_ABOVE_RAD = 0.06
BEAR_TOL_RAD = 0.03
DIST_TOL_M = 0.004
REST_TICKS = 2                # rest ticks after each navigation pulse (as in the calibration)
LAT_M_PER_PULSE = 0.0102      # strafe (lateral) 0.10 s pulse, left positive
LAT_TOL_M = 0.006             # stage B: strafe while the box is more than this far off the heading line

# Odometry (drive record) model, per pulse-second at speed 0.35.
ODO_FWD_M_PER_S = 0.111
ODO_TURN_RAD_PER_S = 0.94
ODO_LAT_M_PER_S = 0.102
ODO_TURN_SHORT_RAD = 0.019
ODO_FWD_M_PER_PULSE = 0.0111
ODO_TURN_RAD_PER_PULSE = 0.0942

# Bounded search.
SECTOR_HALF_RAD = 0.5         # sweep and re-acquisition sector around the expected box direction
SWEEP_STEP_TOL_RAD = 0.05
SEARCH_SWEEPS_MAX = 2         # full sweeps at one position before advancing
SEARCH_TICKS_MAX = 200        # hard bound: consecutive search ticks (20 s) before the search is exhausted
ADVANCE_M = 0.05
ADVANCE_PULSES = 5            # 5 forward pulses of 0.10 s = 0.055 m (open loop, drive record)
ADVANCE_MAX = 4

# Controller tolerances for stage B (cy is recorded only).
TOL_CX_PX = 22.0
STILL_TICKS = 3

# Blobs and tracking.
MIN_COMPONENT_PX = 100
TRACK_GATE_PX = 120.0
HOLD_TICKS = 10
ACQ_CX_GATE_PX = 120.0
ACQ_LNA_GATE = 0.7
ACQ_CX_SIGMA_PX = 80.0
ACQ_LNA_SIGMA = 0.35

# Rim clipping and the identity gate (fix after g675b: every 90706 blob from ticks 255-281 had its bottom at the
# fisheye rim, row 460-463, so the area under-stated the box and d_hat ran away; 90705 locked the other blue box).
LENS_BLACK_MAX = 6            # pixels with max(R,G,B) below this are the lens surround outside the image circle
CLIP_DILATE_PX = 2            # a blob within this many px of the rim is clipped (area and centroid biased)
POS_GATE_M = 0.25             # identity gate: a blob must lie within this of the odometry-expected box position
                              # (0.15 m rejected the designated box in dev 90802 at 0.167-0.177 m; the other same-colour
                              # box sits 0.52 m away in 90705, so 0.25 m keeps a factor-2 separation)
RELOOK_DIST_M = 0.45          # below this odometry distance a lost box is looked for by tilt, never by yaw
RELOOK_D_M = (0.20, 0.25, 0.30, 0.35, 0.45)   # near postures of the teacher schedule, closest first
RELOOK_DWELL_TICKS = 3        # ticks per re-look posture (servo settle, then one detection per tick)
RELOOK_CYCLES_MAX = 3         # re-look cycles per approach; after that the approach hands over to ACT
CLIP_CREEP_STOP_M = 0.30      # a clipped blob (box still under the rim, true d ~0.31-0.40 m): creep forward on the drive
                              # record while the odometry distance is above this; below it, hold. The odometry overestimates
                              # the distance by 0.11-0.13 m in 90705 (v12): a stop at 0.22 m put the robot at 0.09 m true
CLIP_HOLD_MAX = 30            # ticks held at or below CLIP_CREEP_STOP_M with the blob still clipped, then ACT takes over
CREEP_LOST_MAX_M = 0.12       # box lost near range (true d ~0.27-0.31 m, out of frame at the odometry posture): creep on the
                              # drive record at most this far past the last sighting; the posture follows the odometry distance
RELOOK_RESET_RUN = 3          # consecutive tracked ticks before a tilt re-look is reset (a flicker must not restart it)
SETTLED_TICKS = 20            # one exception (scene 90706): a tracked whole blob with no drive pulse for this many
                              # ticks in a row is arrival ('settled'); the area window is not required; the window is unchanged
VIA_CLEAR_M = 0.25            # another same-colour box within this of the start-to-P line -> route via a point
VIA_EXTRA_M = 0.25            # the via-point lies this much further west of P (wall frame)

BUDGET_TICKS = 700            # 70 s of SIM time at 0.1 s per tick (cap 90 s minus the teacher's ~16 s post-hover)
PERIOD_S = 0.1

# Remembered-coordinate error model (the movement code's memory): bearing +-5 deg, distance +-10 %, facing +-5 deg.
HINT_BEARING_NOISE_RAD = math.radians(5.0)
HINT_DISTANCE_NOISE_FRAC = 0.10
HINT_FACING_NOISE_RAD = math.radians(5.0)

_HSV_RANGES = {
    # Same thresholds as harness/seg_frontend_v1.py (OpenCV 8-bit HSV).
    'red': lambda h, s, v: ((h <= 8) | (h >= 172)) & (s > 150) & (v > 90),
    'cyan': lambda h, s, v: (h >= 110) & (h <= 124) & (s > 170) & (v > 70),
}


def _wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def _bearing_of_col(cx):
    """Robot-frame bearing (rad, + = left) of an image column with pan 1500."""
    return -(cx - CX_REF_PX) / K_BEARING_PX_PER_RAD




def _turn_steps(theta):
    """Open-loop turn for theta (rad, + = counter-clockwise): 0.10 s pulses, then 0.05 s pulses for the remainder."""
    sgn = 1.0 if theta >= 0 else -1.0
    rem = abs(theta)
    n_long = int(rem // ODO_TURN_RAD_PER_PULSE)
    rem -= n_long * ODO_TURN_RAD_PER_PULSE
    n_short = int(round(rem / ODO_TURN_SHORT_RAD))
    return [('turn', sgn, TURN_LONG_S)] * n_long + [('turn', sgn, TURN_SHORT_S)] * n_short


def pre_station_rel(hint):
    """Pre-station point P (0.40 m west of the box, wall frame) and the unit west vector, in the start frame."""
    b, d, face = hint['bearing_rad'], hint['distance_m'], hint['facing_rad']
    psi0 = -face                                   # start heading (world yaw) implied by the remembered facing
    c_rel = (d * math.cos(b), d * math.sin(b))     # box centre in the start frame
    west = (-math.cos(psi0), math.sin(psi0))
    p_rel = (c_rel[0] + PRE_STATION_OFFSET_M * west[0], c_rel[1] + PRE_STATION_OFFSET_M * west[1])
    return p_rel, west


def _seg_dist(p, a, b):
    """Distance from point p to the segment a-b (start frame)."""
    ax, ay = a
    bx, by = b
    px, py = p
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def navigation_plan(hint, via_rel=None):
    """Stage A plan from the hint only: turn to P (through a via-point when one is given), drive to P, turn to face
    east. Returns the step list and the geometry (all in the start frame)."""
    face = hint['facing_rad']
    p_rel, _west = pre_station_rel(hint)
    legs = ([via_rel] if via_rel is not None else []) + [p_rel]
    steps, cur, heading, legs_geo = [], (0.0, 0.0), 0.0, []
    for wp in legs:
        th = _wrap(math.atan2(wp[1] - cur[1], wp[0] - cur[0]) - heading)
        dist = math.hypot(wp[0] - cur[0], wp[1] - cur[1])
        n_fwd = int(round(dist / ODO_FWD_M_PER_PULSE))
        steps += _turn_steps(th) + [('fwd', 1.0, PULSE_MAX_S)] * n_fwd
        legs_geo.append({'to_rel_m': [round(wp[0], 4), round(wp[1], 4)], 'turn_rad': round(th, 4),
                         'forward_m': round(dist, 4)})
        heading, cur = heading + th, wp
    th2 = _wrap(face - heading)
    steps += _turn_steps(th2)
    th1 = legs_geo[0]['turn_rad']
    geo = {'pre_station_rel_start_m': [round(p_rel[0], 4), round(p_rel[1], 4)], 'turn1_rad': th1,
           'forward_m': round(sum(l['forward_m'] for l in legs_geo), 4), 'turn2_rad': round(th2, 4),
           'steps': len(steps), 'legs': legs_geo, 'via_rel_start_m': None if via_rel is None else
           [round(via_rel[0], 4), round(via_rel[1], 4)]}
    return steps, geo


def duty_wheels(drive, contract, period=PERIOD_S):
    """The teacher's pulse-width wheel law (sim/grasp_act_port.duty_wheels)."""
    desired = contract.wheel_mix(drive)
    scale = max(.35, max(map(abs, desired)))
    wheels, durations = [], []
    for v in desired:
        dt = period * abs(v) / scale
        if dt < .001:
            wheels.append(0.)
            durations.append(0.)
        else:
            wheels.append(math.copysign(.35, v))
            durations.append(dt)
    return wheels, durations


def components(jpeg, object_kind):
    """Connected blobs of the target colour on the full 640x480 own frame, largest first."""
    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape[:2] != (480, 640):
        raise ValueError('own RGB frame must decode to 640x480')
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = _HSV_RANGES[object_kind](h, s, v).astype(np.uint8)
    # The fisheye image circle ends at about row 460-464 in the centre; the black lens surround outside it is the rim.
    lens = (frame.max(axis=2) < LENS_BLACK_MAX).astype(np.uint8)
    k = 2 * CLIP_DILATE_PX + 1
    rim = cv2.dilate(lens, np.ones((k, k), np.uint8)) > 0
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < MIN_COMPONENT_PX:
            continue
        x, y = int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP])
        w, hgt = int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])
        out.append({'A': area, 'cx': float(cents[i][0]), 'cy': float(cents[i][1]), 'w': w,
                    'x0': x, 'y0': y, 'x1': x + w - 1, 'y1': y + hgt - 1,
                    'clipped': bool(rim[labels == i].any())})
    out.sort(key=lambda b: -b['A'])
    return out


def _is_whole(blob):
    """Whole: not touching the frame edge and not cut by the fisheye rim (its area is then under-stated)."""
    return (blob['x0'] > 1 and blob['y0'] > 1 and blob['x1'] < 638 and blob['y1'] < 478
            and not blob.get('clipped', False))


def _identity_dev(blob, d_est, b_est):
    """Deviation (m) of a blob from the odometry-expected box position (robot frame, from the drive record).
    A whole blob gives a 2-D position (bearing from the column, distance from the area); a clipped or edge blob
    gives only the lateral offset at the expected distance, since its distance is not measured."""
    beta = _bearing_of_col(blob['cx'])
    if _is_whole(blob):
        d_blob = D_STOP_M * math.sqrt(A_REF_PX / blob['A'])
        return math.hypot(d_blob * math.cos(beta) - d_est * math.cos(b_est),
                          d_blob * math.sin(beta) - d_est * math.sin(b_est))
    return d_est * abs(math.sin(_wrap(beta - b_est)))


def largest_component(jpeg, object_kind):
    """Reference helper (teacher stop statistics, offline calibration); not used by the runtime controller."""
    comps = components(jpeg, object_kind)
    if not comps:
        return None, 0, 0
    return comps[0], (comps[1]['A'] if len(comps) > 1 else 0), len(comps)


def _overlap(a, b):
    return not (a['x1'] < b['x0'] or b['x1'] < a['x0'] or a['y1'] < b['y0'] or b['y1'] < a['y0'])


class BlobTracker:
    def __init__(self, hint):
        self.hint = hint
        self.expected = None
        if hint is not None:
            self.expected = {'cx': CX_REF_PX - K_BEARING_PX_PER_RAD * hint['bearing_rad'],
                             'A': A_REF_PX * (D_STOP_M / max(hint['distance_m'], 1e-3)) ** 2}
        self.track = None
        self.last_accept = None
        self.lost = 0
        self.acquisitions = 0
        self.reacquisitions = 0
        self.switches = 0
        self.two_blob_frames = 0
        self.held_frames = 0
        self.search_frames = 0
        self.first_acq = None
        self.events = []

    def reset_for_approach(self):
        self.track = None
        self.lost = 0

    def _accept(self, blob, tick):
        self.track = blob
        self.last_accept = tick
        self.lost = 0

    def _is_switch(self, prev, cur):
        ratio = cur['A'] / float(prev['A'])
        return (not _overlap(prev, cur)) or ratio < .5 or ratio > 2.

    def search_sign(self, expect_bearing):
        return 1.0 if expect_bearing >= 0 else -1.0

    def _initial(self, comps, tick):
        best, best_cost = None, None
        for b in comps:
            dcx = b['cx'] - self.expected['cx']
            lna = math.log(b['A'] / self.expected['A'])
            if abs(dcx) > ACQ_CX_GATE_PX or abs(lna) > ACQ_LNA_GATE:
                continue
            cost = (dcx / ACQ_CX_SIGMA_PX) ** 2 + (lna / ACQ_LNA_SIGMA) ** 2
            if best is None or cost < best_cost:
                best, best_cost = b, cost
        if best is None:
            return None
        self._accept(best, tick)
        self.acquisitions += 1
        self.first_acq = {'tick': tick, 'cost': round(best_cost, 3), 'A': best['A'], 'cx': round(best['cx'], 2),
                          'cy': round(best['cy'], 2), 'n_blobs': len(comps)}
        return 'acquired', best

    def _sector_acquire(self, comps, tick, expect_bearing, sector=True):
        """Re-acquisition: the blob nearest to the odometry bearing of the box. Far from the box the choice is limited to
        the +-SECTOR_HALF_RAD sector; at near range (sector=False) the identity gate is the only limit: the odometry
        bearing drifts by up to ~28 deg there (measured, 90706 v12) and the sector excluded the true box."""
        best, best_d = None, None
        for b in comps:
            d = abs(_bearing_of_col(b['cx']) - expect_bearing)
            if sector and d > SECTOR_HALF_RAD:
                continue
            if best is None or d < best_d:
                best, best_d = b, d
        if best is None:
            return None
        self._accept(best, tick)
        self.reacquisitions += 1
        self.events.append({'tick': tick, 'kind': 'reacquired_sector', 'A': best['A'], 'cx': round(best['cx'], 1),
                            'bearing_off_rad': round(best_d, 3)})
        return 'acquired', best

    def update(self, comps, tick, expect_bearing, sector=True):
        """Return (state, blob): state in acquired / tracked / held / search."""
        if len(comps) >= 2:
            self.two_blob_frames += 1
        if self.track is None:
            if not comps:
                self.search_frames += 1
                return 'search', None
            res = self._initial(comps, tick) if self.acquisitions == 0 else self._sector_acquire(comps, tick, expect_bearing, sector)
            if res is None:
                self.search_frames += 1
                return 'search', None
            return res
        if not comps:
            return self._miss(tick)
        tr = self.track
        cand = min(comps, key=lambda b: math.hypot(b['cx'] - tr['cx'], b['cy'] - tr['cy']))
        dist = math.hypot(cand['cx'] - tr['cx'], cand['cy'] - tr['cy'])
        if dist <= TRACK_GATE_PX:
            if self.last_accept == tick - 1 and self._is_switch(tr, cand):
                self.switches += 1
                self.events.append({'tick': tick, 'kind': 'switch', 'from_A': tr['A'], 'to_A': cand['A'],
                                    'n_blobs': len(comps)})
            self._accept(cand, tick)
            return 'tracked', cand
        return self._miss(tick)

    def _miss(self, tick):
        self.lost += 1
        if self.lost <= HOLD_TICKS:
            self.held_frames += 1
            return 'held', None
        self.track = None
        self.lost = 0
        self.search_frames += 1
        return 'search', None


class ApproachServo:
    # The student contract module is passed in by the runner (never imported here): the runner calls run()
    # inside the frozen-dependency import scope, where 'harness' resolves to the pinned teacher package.
    def __init__(self, object_kind, contract, hint):
        if object_kind not in _HSV_RANGES:
            raise ValueError('approach_code_v1 needs object_kind red or cyan, got %r' % (object_kind,))
        if hint is None:
            raise ValueError('approach_code_v1 needs the handoff hint (plan_handoff_hint)')
        self.c = contract
        self.object_kind = object_kind
        self.hint = hint
        self.ticks = 0
        self.visible_ticks = 0
        self.still = 0
        self.arrived = False
        self.reason = None
        self.arrival = None
        self.tracker = BlobTracker(hint)
        self.trace = []
        self.posture = dict(FAR_POSTURE)
        self.stage = 'nav'
        self.nav_steps, self.nav_geo = navigation_plan(hint)
        self.nav_rest = 0
        self.nav_done_tick = None
        self.rest_next = False
        # Drive record (odometry) in the start frame; the box position from the hint (noisy memory).
        self.pos = [0.0, 0.0]
        self.yaw = 0.0
        self.box_xy = (hint['distance_m'] * math.cos(hint['bearing_rad']),
                       hint['distance_m'] * math.sin(hint['bearing_rad']))
        self.sweep = None
        self.search_pulses = 0
        self.search_run = 0
        self.relook_idx = None        # index into RELOOK_D_M while a near-range tilt re-look runs
        self.relook_dwell = 0
        self.relook_cycles = 0
        self.clip_hold = 0            # ticks held at the creep stop while the box is rim-clipped
        self.gate_rejected = 0        # blob detections rejected by the identity gate (all ticks)
        self.via_info = None          # first-frame same-colour check for the route (see _plan_via)
        self.last_seen_pos = None     # drive-record position at the last accepted blob (blind creep is measured from it)
        self.track_run = 0            # consecutive tracked ticks (a re-look resets only after RELOOK_RESET_RUN of them)
        self.settled_run = 0          # consecutive tracked, whole, pulse-free approach ticks (see SETTLED_TICKS)

    def _odo(self, kind, sgn, secs):
        if kind == 'fwd':
            s = ODO_FWD_M_PER_S * secs * sgn
            self.pos[0] += s * math.cos(self.yaw)
            self.pos[1] += s * math.sin(self.yaw)
        elif kind == 'lat':
            s = ODO_LAT_M_PER_S * secs * sgn
            self.pos[0] += -s * math.sin(self.yaw)
            self.pos[1] += s * math.cos(self.yaw)
        elif kind == 'turn':
            self.yaw = _wrap(self.yaw + ODO_TURN_RAD_PER_S * secs * sgn)

    def _est(self):
        """(distance, robot-frame bearing, absolute direction) to the box from the drive record."""
        dx, dy = self.box_xy[0] - self.pos[0], self.box_xy[1] - self.pos[1]
        d = math.hypot(dx, dy)
        abs_dir = math.atan2(dy, dx)
        return d, _wrap(abs_dir - self.yaw), abs_dir

    def _hold(self, now, posture):
        return self.c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
                               'pwm': {str(s): posture[s] for s in posture}})

    def _pulse_row(self, now, kind, sgn, secs):
        self._odo(kind, sgn, secs)
        if kind == 'fwd':
            wheels = [sgn * PULSE_SPEED] * 4
        elif kind == 'lat':  # strafe, positive = left: wheel_mix((0, l, 0)) = (-l, +l, +l, -l)
            wheels = [-sgn * PULSE_SPEED, sgn * PULSE_SPEED, sgn * PULSE_SPEED, -sgn * PULSE_SPEED]
        else:  # turn, positive = counter-clockwise: wheel_mix((0, 0, t)) = (-t, +t, -t, +t)
            wheels = [-sgn * PULSE_SPEED, sgn * PULSE_SPEED, -sgn * PULSE_SPEED, sgn * PULSE_SPEED]
        return self.c.command({'t': now, 'wheels': wheels, 'duration_s': [secs] * 4,
                               'pwm': {str(s): self.posture[s] for s in self.posture}})

    def _search_pulse(self, b_exp, abs_dir):
        """One bounded search pulse, or None (no pulse this tick)."""
        if self.sweep is None:
            self.sweep = {'side': 1.0, 'sweeps': 0, 'advances': 0, 'mode': 'sweep', 'adv_left': 0}
        sw = self.sweep
        if sw['mode'] == 'advance':                      # open-loop advance along the expected direction
            if sw['adv_left'] > 0:
                sw['adv_left'] -= 1
                return ('fwd', 1.0, PULSE_MAX_S)
            sw['mode'] = 'sweep'
            sw['sweeps'] = 0
            sw['side'] = 1.0
            return None
        if sw['sweeps'] >= SEARCH_SWEEPS_MAX:            # face the expected direction, then advance
            if abs(_wrap(abs_dir - self.yaw)) > SWEEP_STEP_TOL_RAD:
                err = _wrap(abs_dir - self.yaw)
                return ('turn', 1.0 if err > 0 else -1.0,
                        TURN_LONG_S if abs(err) > TURN_LONG_ABOVE_RAD else TURN_SHORT_S)
            if sw['advances'] >= ADVANCE_MAX:
                return 'exhausted'
            sw['advances'] += 1
            sw['mode'] = 'advance'
            sw['adv_left'] = ADVANCE_PULSES
            return None
        target = abs_dir + sw['side'] * SECTOR_HALF_RAD  # sweep edge in the expected-direction sector
        err = _wrap(target - self.yaw)
        if abs(err) > SWEEP_STEP_TOL_RAD:
            return ('turn', 1.0 if err > 0 else -1.0,
                    TURN_LONG_S if abs(err) > TURN_LONG_ABOVE_RAD else TURN_SHORT_S)
        sw['side'] = -sw['side']                          # reached an edge: go to the other one
        if sw['side'] > 0:
            sw['sweeps'] += 1
        return None

    def _plan_via(self, raw, d_est, b_est):
        """Same-colour box on the route, from the first frame only (the robot has not moved): other whole blobs of
        the target colour (not the designated box, by the identity gate) give start-frame positions from their
        columns and areas. If the start-to-P line passes within VIA_CLEAR_M of one, the route goes via a point
        VIA_EXTRA_M further west of P. Replans the stage-A steps (the robot is still at the start)."""
        p_rel, west = pre_station_rel(self.hint)
        others = []
        for b in raw:
            if not _is_whole(b) or _identity_dev(b, d_est, b_est) <= POS_GATE_M:
                continue
            d_b = D_STOP_M * math.sqrt(A_REF_PX / b['A'])
            beta = _bearing_of_col(b['cx'])
            others.append((d_b * math.cos(beta), d_b * math.sin(beta)))
        clear = [_seg_dist(o, (0.0, 0.0), p_rel) for o in others]
        via = any(c < VIA_CLEAR_M for c in clear)
        self.via_info = {'others_start_m': [[round(x, 3), round(y, 3)] for x, y in others],
                         'clearance_to_line_m': [round(c, 3) for c in clear], 'via_used': bool(via)}
        if via:
            wp = (p_rel[0] + VIA_EXTRA_M * west[0], p_rel[1] + VIA_EXTRA_M * west[1])
            self.nav_steps, self.nav_geo = navigation_plan(self.hint, wp)

    def _blind_creep(self, d_est):
        """Box lost at near range: one creep pulse toward it on the drive record, while the odometry distance is above
        CLIP_CREEP_STOP_M and less than CREEP_LOST_MAX_M of drive has passed since the last sighting. None otherwise."""
        if self.last_seen_pos is None or not (CLIP_CREEP_STOP_M + DIST_TOL_M < d_est < RELOOK_DIST_M):
            return None
        travel = math.hypot(self.pos[0] - self.last_seen_pos[0], self.pos[1] - self.last_seen_pos[1])
        if travel >= CREEP_LOST_MAX_M:
            return None
        return ('fwd', 1.0, PULSE_MAX_S)

    def _relook_step(self):
        """One near-range re-look tick: cycle the teacher's near postures, closest first, RELOOK_DWELL_TICKS each.
        A miss at close range is a vertical one (the box is below the rim), so only the tilt changes. Returns
        'exhausted' when the cycles are used up."""
        if self.relook_idx is None:
            if self.relook_cycles >= RELOOK_CYCLES_MAX:
                return 'exhausted'
            self.relook_idx, self.relook_dwell = 0, 0
            self.relook_cycles += 1
        if self.relook_idx >= len(RELOOK_D_M):
            return 'exhausted'
        self.posture = posture_for(RELOOK_D_M[self.relook_idx])
        self.relook_dwell += 1
        if self.relook_dwell >= RELOOK_DWELL_TICKS:
            self.relook_idx += 1
            self.relook_dwell = 0
        return None

    def step(self, jpeg, now):
        """Return the command row for this tick, or None when ACT takes this tick (timeout or exhausted search)."""
        if self.arrived:
            raise RuntimeError('approach servo stepped after arrival')
        if self.ticks >= BUDGET_TICKS:
            self.arrived, self.reason = True, 'timeout'
            self.arrival = {'tick': self.ticks, 't': now, 'A': None}
            return None
        tick = self.ticks
        self.ticks += 1
        d_est, b_est, abs_dir = self._est()
        raw = components(jpeg, self.object_kind)
        comps = []                   # identity gate: only blobs within POS_GATE_M of the odometry-expected box
        for b in raw:
            b['gate_dev_m'] = round(_identity_dev(b, d_est, b_est), 4)
            if b['gate_dev_m'] <= POS_GATE_M:
                comps.append(b)
            else:
                self.gate_rejected += 1
        state, blob = self.tracker.update(comps, tick, b_est, sector=(d_est >= RELOOK_DIST_M))
        crit = False
        pulse = None                 # (kind, sign, seconds) or None for rest/hold
        bearing = None
        d_hat = None
        cy_ok = None
        exhausted = False
        relook_used = False
        clip_exhausted = False
        cmd_src = 'hold'
        if tick == 0:
            self._plan_via(raw, d_est, b_est)

        if self.stage == 'nav':
            self.posture = posture_for(d_est)
            if self.nav_rest > 0:
                self.nav_rest -= 1
                cmd_src = 'nav_rest'
            elif self.nav_steps:
                pulse = self.nav_steps.pop(0)
                self.nav_rest = REST_TICKS
                cmd_src = 'nav'
            else:
                self.stage = 'approach'
                self.nav_done_tick = tick
                self.rest_next = False
                self.tracker.reset_for_approach()

        if self.stage == 'approach' and cmd_src == 'hold':
            cmd_src = 'approach'
            if state in ('acquired', 'tracked'):
                self.visible_ticks += 1
                self.sweep = None
                self.search_run = 0
                self.track_run += 1
                if self.track_run >= RELOOK_RESET_RUN:   # a stable sighting only: 1-tick flickers must not reset the creep
                    self.last_seen_pos = (self.pos[0], self.pos[1])
                    self.relook_idx = None
                cx, cy = blob['cx'], blob['cy']
                bearing = _bearing_of_col(cx)
                whole = _is_whole(blob)
                if whole:
                    self.clip_hold = 0
                    d_hat = D_STOP_M * math.sqrt(A_REF_PX / blob['A'])
                    d_use = d_hat
                else:
                    # Rim-clipped or edge blob: its area under-states the box, so d_hat is not used. The tilt stays on the
                    # odometry distance (the schedule does not lift a clipped box: measured clipped at 0.33-0.38 m
                    # true at every tried posture), and the robot creeps forward on the drive record until whole.
                    d_use = d_est
                self.posture = posture_for(d_use)
                e_d = d_use - D_STOP_M
                cy_ok = abs(cy - CY_REF_PX) <= 12.0
                crit = whole and (abs(cx - CX_REF_PX) <= TOL_CX_PX and A_LO_PX <= blob['A'] <= A_HI_PX)
                if not self.rest_next:
                    lat = d_use * math.tan(bearing)  # box offset from the heading line, metres, + = left
                    if abs(lat) > LAT_TOL_M:          # keep bearing 0 by lateral pulses (heading unchanged)
                        pulse = ('lat', 1.0 if lat > 0 else -1.0,
                                 min(PULSE_MAX_S, max(PULSE_MIN_S, abs(lat) / LAT_M_PER_PULSE)))
                    elif whole and abs(e_d) > DIST_TOL_M:
                        pulse = ('fwd', 1.0 if e_d > 0 else -1.0,
                                 min(PULSE_MAX_S, max(PULSE_MIN_S, K_FWD_S_PER_M * abs(e_d))))
                    elif not whole and d_est > CLIP_CREEP_STOP_M + DIST_TOL_M:
                        pulse = ('fwd', 1.0, PULSE_MAX_S)     # creep toward the box on the drive record
                    elif not whole:
                        self.clip_hold += 1                   # at the creep stop and still clipped
                        if self.clip_hold > CLIP_HOLD_MAX:
                            clip_exhausted = True
            elif state == 'held':
                self.track_run = 0
                self.posture = posture_for(d_est)
                pulse = None if self.rest_next else self._blind_creep(d_est)
            elif d_est < RELOOK_DIST_M:
                # Near range, box lost: first close on the drive record (the posture follows the odometry distance, so
                # the box returns into the frame), then re-look by tilt only. No yaw sweep and no advance.
                self.track_run = 0
                self.search_run += 1
                pulse = None
                if not self.rest_next:
                    creep = self._blind_creep(d_est)
                    if creep is not None:
                        pulse = creep
                        self.posture = posture_for(d_est)
                    else:
                        relook_used = True
                        if self.search_run > SEARCH_TICKS_MAX or self._relook_step() == 'exhausted':
                            exhausted = True
            else:  # search: bounded sweep around the expected direction, and a hard tick bound
                self.track_run = 0
                self.posture = posture_for(d_est)
                self.search_run += 1
                if self.search_run > SEARCH_TICKS_MAX:
                    exhausted = True
                    pulse = None
                elif not self.rest_next:
                    res = self._search_pulse(b_est, abs_dir)
                    if res == 'exhausted':
                        exhausted = True
                        pulse = None
                    else:
                        pulse = res
                        self.search_pulses += 1 if res is not None else 0
            self.rest_next = pulse is not None and cmd_src != 'nav'

        if clip_exhausted:
            exhausted = True
        idle_tracked = (self.stage == 'approach' and state in ('acquired', 'tracked') and blob is not None
                        and _is_whole(blob) and pulse is None)
        self.settled_run = self.settled_run + 1 if idle_tracked else 0
        self.still = self.still + 1 if (self.stage == 'approach' and crit and pulse is None) else 0
        self.trace.append({'tick': tick, 't': round(now, 3), 'stage': self.stage, 'state': state,
                           'n_blobs': len(raw), 'n_gated': len(comps),
                           'gate_dev_m': None if blob is None else blob.get('gate_dev_m'),
                           'clipped': None if blob is None else bool(blob.get('clipped')),
                           'relook_idx': self.relook_idx, 'clip_hold': self.clip_hold, 'settled_run': self.settled_run,
                           'posture': {str(k): self.posture[k] for k in (3, 4)},
                           'A': None if blob is None else blob['A'],
                           'cx': None if blob is None else round(blob['cx'], 2),
                           'cy': None if blob is None else round(blob['cy'], 2),
                           'w': None if blob is None else blob['w'],
                           'whole': None if blob is None else _is_whole(blob),
                           'bearing_deg': None if bearing is None else round(math.degrees(bearing), 2),
                           'd_hat_m': None if d_hat is None else round(d_hat, 4),
                           'd_est_m': round(d_est, 4), 'b_est_deg': round(math.degrees(b_est), 2),
                           'odo': [round(self.pos[0], 4), round(self.pos[1], 4), round(self.yaw, 4)],
                           'pulse': None if pulse is None else [pulse[0], int(pulse[1]), round(pulse[2], 3)],
                           'crit': bool(crit), 'cy_ok': cy_ok, 'switches_so_far': self.tracker.switches})
        if exhausted:
            self.arrived = True
            self.reason = ('handover_near_clipped' if clip_exhausted else
                           'handover_near_no_blob' if relook_used else 'search_exhausted')
            self.arrival = {'tick': tick, 't': now, 'A': None, 'advances': None if self.sweep is None else self.sweep['advances'],
                            'search_run_ticks': self.search_run, 'relook_cycles': self.relook_cycles,
                            'gate_rejected': self.gate_rejected}
            return self._hold(now, self.posture)
        if self.stage == 'approach' and self.still >= STILL_TICKS:
            self.arrived, self.reason = True, 'arrived'
            self.arrival = {'tick': tick, 't': now, 'A': blob['A'], 'cx': blob['cx'], 'cy': blob['cy'],
                            'w': blob['w'], 'bearing_deg': round(math.degrees(bearing), 2),
                            'd_hat_m': round(d_hat, 4) if d_hat is not None else None, 'cy_ok': cy_ok}
            return self._hold(now, self.posture)
        if self.stage == 'approach' and self.settled_run >= SETTLED_TICKS:
            self.arrived, self.reason = True, 'settled'
            self.arrival = {'tick': tick, 't': now, 'A': blob['A'], 'cx': blob['cx'], 'cy': blob['cy'],
                            'w': blob['w'], 'bearing_deg': round(math.degrees(bearing), 2),
                            'd_hat_m': round(d_hat, 4) if d_hat is not None else None, 'cy_ok': cy_ok,
                            'settled_ticks': self.settled_run, 'area_window_met': bool(crit)}
            return self._hold(now, self.posture)
        if pulse is None:
            return self._hold(now, self.posture)
        return self._pulse_row(now, pulse[0], pulse[1], pulse[2])

    def record(self):
        tr = self.tracker
        return {'enabled': True, 'object_kind': self.object_kind, 'arrived': self.reason in ('arrived', 'settled'),
                'reason': self.reason, 'ticks_code': self.ticks, 'ticks_visible': self.visible_ticks,
                'arrival': self.arrival, 'posture_at_end': {str(s): self.posture[s] for s in self.posture},
                'handoff_hint': {k: (round(v, 5) if isinstance(v, float) else v) for k, v in self.hint.items()},
                'navigation': dict(self.nav_geo, nav_done_tick=self.nav_done_tick),
                'search': {'pulses': self.search_pulses,
                           'sweep_state': None if self.sweep is None else
                           {k: self.sweep[k] for k in ('sweeps', 'advances')}},
                'via_check': self.via_info,
                'near_range': {'relook_cycles': self.relook_cycles, 'gate_rejected_detections': self.gate_rejected,
                               'relook_d_m': list(RELOOK_D_M), 'relook_dist_m': RELOOK_DIST_M,
                               'pos_gate_m': POS_GATE_M, 'clip_creep_stop_m': CLIP_CREEP_STOP_M,
                               'clip_hold_max': CLIP_HOLD_MAX, 'creep_lost_max_m': CREEP_LOST_MAX_M,
                               'relook_reset_run': RELOOK_RESET_RUN},
                'odometry_end': [round(self.pos[0], 4), round(self.pos[1], 4), round(self.yaw, 4)],
                'tracking': {'acquisitions': tr.acquisitions, 'reacquisitions': tr.reacquisitions,
                             'switches': tr.switches, 'two_blob_frames': tr.two_blob_frames,
                             'held_frames': tr.held_frames, 'search_frames': tr.search_frames,
                             'first_acquisition': tr.first_acq, 'events': tr.events[:50]},
                'references': {'cx_ref_px': CX_REF_PX, 'cy_ref_px': CY_REF_PX, 'A_lo_px': A_LO_PX,
                               'A_hi_px': A_HI_PX, 'A_ref_px': A_REF_PX, 'd_stop_m': D_STOP_M},
                'inputs': 'own RGB blobs of the target colour, object_kind, the handoff hint once at the start, and the '
                          'drive record (own issued pulses); no ground truth, no map, no teacher, no ACT input',
                'trace_file': 'approach-trace.json'}
