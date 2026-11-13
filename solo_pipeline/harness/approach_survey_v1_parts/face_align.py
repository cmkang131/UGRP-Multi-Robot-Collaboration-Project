"""RGB-only face alignment. No simulator, plan, seed or evaluator inputs.

Public API: FaceAligner(baseline, contract, entries, index, posture),
step(jpeg, command_time) -> command; done/reason/trace/pulses are public.
Camera commands must have settled before construction. Call at 10 Hz.
"""
import math
from statistics import median

from survey_observe import _validate_entry


def wrap90(a):
    return (a + math.pi / 4) % (math.pi / 2) - math.pi / 4


def estimate(jpeg, kind, posture, previous=None):
    """Lower-envelope TLS, derived from main_yaw_feasibility. Returns rejects too."""
    import cv2
    import numpy as np
    from ground_projection import project_pixels
    if type(jpeg) is not bytes or kind not in ('red', 'cyan'):
        raise ValueError('only JPEG and observed kind accepted')
    if (type(posture) is not dict or set(posture) != {1, 3, 4, 5, 6}
            or any(type(k) is not int or type(v) is not int or not 500 <= v <= 2500
                   for k, v in posture.items())):
        raise ValueError('issued PWM only')
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None or img.shape != (480, 640, 3):
        raise ValueError('expected own 640x480 JPEG')
    b, g, r = [img[:, :, i].astype(int) for i in range(3)]
    m = ((r - np.maximum(g, b) > 60) & (r > 90) if kind == 'red'
         else (b - np.maximum(g, r) > 60) & (b > 90)).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(m, 8)
    big = max(range(1, n), key=lambda k: stats[k, 4]) if n > 1 else None
    hint = None
    if big is not None and stats[big, 4] > 150:
        hx, hy, hw, hh = (int(stats[big, i]) for i in range(4))
        hint = {'cx': float(cents[big, 0]), 'x0': hx, 'y0': hy, 'x1': hx + hw, 'y1': hy + hh}
    candidates = [k for k in range(1, n) if stats[k, 4] > 300
                  and abs(cents[k, 0] - 286.9) < 120]
    if previous is not None:
        candidates = [k for k in candidates if math.dist(cents[k], previous) < 80]
    if len(candidates) != 1:
        return {'valid': False, 'hint': hint, 'reject': 'missing_or_ambiguous_component'}
    k = candidates[0]
    comp = labels == k
    rim = cv2.dilate((img.max(axis=2) < 6).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    x, y, w, h, area = map(int, stats[k])
    if x <= 2 or y <= 2 or x+w >= 638 or y+h >= 478 or rim[comp].any():
        return {'valid': False, 'hint': hint, 'reject': 'clipped'}
    xs = np.flatnonzero(comp.any(axis=0))
    ys = np.array([np.flatnonzero(comp[:, x]).max() for x in xs])
    hits = project_pixels(np.column_stack([xs, ys]).astype(float)[2:-2], posture)
    if len(hits) < 24 or not np.isfinite(hits).all():
        return {'valid': False, 'hint': hint, 'reject': 'projection_or_short_contour'}

    def fit(p):
        _, _, vt = np.linalg.svd(p-p.mean(axis=0), full_matrices=False)
        residual = float(np.sqrt(np.mean(((p-p.mean(axis=0)) @ vt[1])**2)))
        return vt[0], residual, float(np.linalg.norm(p[-1]-p[0]))

    d0, r0, l0 = fit(hits)
    best = None
    for s in range(6, len(hits)-6):
        d1, r1, l1 = fit(hits[:s])
        d2, r2, l2 = fit(hits[s:])
        cost = r1*s+r2*(len(hits)-s)
        if best is None or cost < best[0]:
            best = cost, d1, r1, l1, d2, r2, l2
    cost, d1, r1, l1, d2, r2, l2 = best
    two = r0*len(hits) >= 1.6*cost + 1e-4*len(hits)
    d, residual, length = ((d1, r1, l1) if l1 >= l2 else (d2, r2, l2)) if two else (d0, r0, l0)
    orthogonal = abs(float(d1 @ d2)) < .35
    # 2x was too strict: 39 mm against 21 mm was rejected for ever while the robot stood still (90820).
    dominant = max(l1, l2) >= 1.4 * min(l1, l2)
    if length < .018 or residual > .004 or (two and (min(l1, l2) < .006 or (not orthogonal and not dominant))):
        return {'valid': False, 'hint': hint, 'reject': 'edge_quality', 'lengths_m': [l1, l2], 'residual_m': residual}
    contact = (np.median(hits[:3], axis=0)+np.median(hits[-3:], axis=0))/2
    return {'valid': True, 'yaw_rad': wrap90(math.atan2(d[1], d[0])-math.pi/2),
            'two_edges': two, 'lengths_m': [l1, l2], 'residual_m': residual,
            'long_edge_m': float(max(l1, l2)) if two else None,
            'contact_x_m': float(contact[0]), 'contact_y_m': float(contact[1]),
            'cx': float(cents[k, 0]), 'cy': float(cents[k, 1]), 'area': area,
            'face_type': 'see FaceAligner.face'}


class FaceAligner:
    def __init__(self, baseline, contract, entries, index, posture):
        if type(entries) is not list:
            raise ValueError('observed list required')
        for e in entries:
            _validate_entry(e)
        if type(index) is not int or not 0 <= index < len(entries):
            raise ValueError('observed index required')
        if type(posture) is not dict or set(posture) != {1, 3, 4, 5, 6}:
            raise ValueError('issued posture required')
        self.kind = entries[index]['kind']
        self.base, self.contract, self.posture = baseline, contract, dict(posture)
        self.done, self.reason = False, None
        self.trace, self.pulses, self.samples = [], [], []
        self.rest, self.previous, self.pending_turn = 3, None, False
        self.ticks, self.bad_batches = 0, 0
        self.duration = {'turn': .075, 'fwd': .05, 'lat': .10}
        self.last = None
        # Face type: the teacher always grasped across the 40 mm face. Measured at |tilt| < 5 deg with two
        # visible edges, the long edge reads 42-43 mm on that face and 35.6-36.2 mm on the 34 mm face
        # (10 development runs), so 39 mm separates them. On the narrow face: orbit a quarter turn once.
        self.long_edges, self.face = [], 'unverified'
        self.force, self.force_prev, self.quarter_used = 0, None, False
        self.wrapped = False
        self.last_lat = 0.0
        self.recover_budget, self.recover_used = 16, 0

    def step(self, jpeg, now):
        if type(jpeg) is not bytes or type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError('JPEG and own finite command clock only')
        if self.done:
            raise RuntimeError('alignment already ended')
        cmd = {'t': now, 'wheels': [0.]*4, 'duration_s': [0.]*4,
               'pwm': {str(k): v for k, v in self.posture.items()}}
        row = {'tick': self.ticks, 't': now, 'posture': dict(self.posture), 'pulse': None}
        self.ticks += 1
        if self.rest:
            self.rest -= 1
            row['state'] = 'settle'
        else:
            e = estimate(jpeg, self.kind, self.posture, self.previous)
            row['estimate'] = e
            self.samples.append(e)
            if e['valid']:
                self.previous = [e['cx'], e['cy']]
                if e.get('long_edge_m') and abs(e['yaw_rad']) < math.radians(5):
                    self.long_edges = (self.long_edges + [e['long_edge_m']])[-12:]
            if len(self.samples) == 3:
                batch = self.samples
                valid = [v for v in batch if v['valid']]
                self.samples = []
                mean = math.atan2(sum(math.sin(4*v['yaw_rad']) for v in valid),
                                  sum(math.cos(4*v['yaw_rad']) for v in valid))/4 if valid else 0
                stable = len(valid) >= 2 and max(abs(wrap90(v['yaw_rad']-mean)) for v in valid) < math.radians(3)
                recovered = False
                if not valid and self.recover_budget > 0:
                    # Nothing usable in view: the approach can hand over with the box cut off by the image
                    # edge (5 of 18 development runs). Bring it back into view with own commands only:
                    # turn towards the colour if it sits off to one side, else look down, else back up.
                    hints = [v['hint'] for v in batch if v.get('hint')]
                    h = hints[-1] if hints else None
                    off = (h['cx'] - 286.9) if h else 0.
                    action = None
                    if h and (abs(off) > 120 or h['x0'] <= 2 or h['x1'] >= 638) and abs(off) > 40:
                        action = ('turn', -math.copysign(1, off), .075)
                    elif (self.posture[3], self.posture[4]) != (500, 2500):
                        self.posture[3], self.posture[4] = 500, 2500
                        cmd['pwm'] = {str(k): v for k, v in self.posture.items()}
                        row['recover'] = 'look_down'
                        self.rest = 5
                    else:
                        action = ('fwd', -1.0, .10)
                    if action:
                        mode, sign, duration = action
                        pattern = {'fwd': [1, 1, 1, 1], 'turn': [-1, 1, -1, 1]}[mode]
                        cmd['wheels'] = [.35 * sign * q for q in pattern]
                        cmd['duration_s'] = [duration] * 4
                        row['pulse'] = {'mode': mode, 'sign': sign, 'duration_s': duration, 'recover': True}
                        self.pulses.append(dict(row['pulse'], tick=row['tick']))
                        self.rest = 3
                    self.recover_budget -= 1
                    self.recover_used += 1
                    self.previous = None
                    row['state'] = 'recover'
                    recovered = True
                if recovered:
                    pass
                elif not stable:
                    self.bad_batches += 1
                    row['state'] = 'unstable_batch'
                    # Standing still shows the same rejected frame again. After two bad batches take one
                    # short step in the last sideways direction so the view changes, then look again.
                    if self.bad_batches in (2, 4) and self.last_lat:
                        cmd['wheels'] = [.35 * self.last_lat * q for q in (-1, 1, 1, -1)]
                        cmd['duration_s'] = [.10] * 4
                        row['pulse'] = {'mode': 'lat', 'sign': self.last_lat, 'duration_s': .10, 'nudge': True}
                        self.pulses.append(dict(row['pulse'], tick=row['tick']))
                        self.rest = 3
                    if self.bad_batches >= 6:
                        self.done, self.reason = True, 'quality_exhausted'
                else:
                    self.bad_batches = 0
                    cx = median(v['cx'] for v in valid)-286.9
                    distance = median(v['contact_x_m'] for v in valid)
                    area = median(v['area'] for v in valid)
                    row['aggregate'] = {'yaw_rad': mean, 'cx_error_px': cx,
                                        'contact_x_m': distance, 'area': area, 'frames': len(valid)}
                    pulse = None
                    # Did the previous pulse move what it was meant to move? A 0.05 s pulse can be
                    # too short to overcome the wheel deadband (90800: 99 forward pulses, no motion),
                    # so a pulse that changes nothing is lengthened, and an overshoot is shortened.
                    measure = {'turn': cx, 'fwd': distance, 'lat': mean}
                    if self.last is not None:
                        mode0, before, sign0 = self.last
                        change = measure[mode0] - before
                        dead = {'turn': 3.0, 'fwd': .002, 'lat': math.radians(.6)}[mode0]
                        if abs(change) < dead:
                            self.duration[mode0] = min(.15, self.duration[mode0] + .025)
                        elif mode0 in ('turn', 'lat') and before * measure[mode0] < 0:
                            self.duration[mode0] = max(.05, self.duration[mode0] - .025)
                        elif mode0 == 'fwd' and (before - .203) * (distance - .203) < 0:
                            self.duration[mode0] = max(.05, self.duration[mode0] - .025)
                        self.last = None
                    # Order: keep the box in view, orbit to the face, centre, then fix the range.
                    # A 0.05 s wheel pulse barely moves the base and a 0.10 s turn moves the box
                    # by about 65 px, so the centring band is 30 px, not 16 (90810 oscillated).
                    # The range estimate reads about 5 mm short of the true base-to-box distance when squared up
                    # (13 runs), and the grasp held at 0.206-0.220 m true distance but not always at 0.219 m, so the
                    # target is 0.203 m estimated (0.208 m true) with a 0.196-0.210 m band.
                    # The range band was +/-1 cm: 90810 stood 3 cm too far with a +/-2 cm band and
                    # the grasp failed; with range pulses it stood 1.3 cm off and the grasp held.
                    if self.force:
                        # Quarter orbit towards the next face: keep stepping sideways in one direction.
                        # The tilt estimate climbs to 45 deg and wraps to -45 deg. Right at the diagonal the
                        # estimate flips sign from frame to frame (90800: -42 deg, then +41 deg), and the
                        # nearest-face rule then walked back to the narrow face. So the forced direction is
                        # kept until the estimate is clearly past the diagonal: wrapped, and within 25 deg of
                        # the next face on its far side.
                        if self.force_prev is not None and self.force * (mean - self.force_prev) < -.5:
                            self.wrapped = True
                        self.force_prev = mean
                        if self.wrapped and -math.radians(25) < self.force * mean < 0:
                            self.force, self.long_edges = 0, []
                    if self.force:
                        if abs(cx) > 60:
                            pulse = ('turn', -math.copysign(1, cx), self.duration['turn'])
                        else:
                            pulse = ('lat', float(self.force), self.duration['lat'])
                    elif abs(cx) > 60:
                        pulse = ('turn', -math.copysign(1, cx), self.duration['turn'])
                    elif abs(mean) > math.radians(4):
                        pulse = ('lat', -math.copysign(1, mean), self.duration['lat'])
                    elif abs(cx) > 30:
                        pulse = ('turn', -math.copysign(1, cx), self.duration['turn'])
                    elif distance < .196 or distance > .210:
                        pulse = ('fwd', math.copysign(1, distance-.203), self.duration['fwd'])
                    else:
                        width = median(self.long_edges) if len(self.long_edges) >= 3 else None
                        row['face_check'] = {'long_edge_m': width, 'samples': len(self.long_edges)}
                        if width is not None and width < .039 and not self.quarter_used:
                            self.quarter_used, self.force, self.force_prev = True, 1, mean
                            self.face = 'narrow_seen'
                            pulse = ('lat', 1.0, self.duration['lat'])
                        else:
                            self.face = ('unverified' if width is None else
                                         'wide' if width >= .039 else 'narrow_after_quarter')
                            self.done, self.reason = True, 'aligned_' + self.face + '_face'
                    if pulse:
                        self.last = (pulse[0], measure[pulse[0]], pulse[1])
                        if pulse[0] == 'lat':
                            self.last_lat = pulse[1]
                    if pulse:
                        mode, sign, duration = pulse
                        pattern = {'fwd': [1,1,1,1], 'lat': [-1,1,1,-1], 'turn': [-1,1,-1,1]}[mode]
                        cmd['wheels'] = [.35*sign*p for p in pattern]
                        cmd['duration_s'] = [duration]*4
                        row['pulse'] = {'mode': mode, 'sign': sign, 'duration_s': duration}
                        self.pulses.append(dict(row['pulse'], tick=row['tick']))
                        self.rest = 3
        if len(self.pulses) >= 260 or self.ticks >= 1600:
            self.done, self.reason = True, 'alignment_budget'
        row['command'] = cmd
        self.trace.append(row)
        return self.contract.command(cmd)
