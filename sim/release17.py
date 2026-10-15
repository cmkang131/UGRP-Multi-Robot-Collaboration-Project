"""Opt-in release17: single-pulse FOV recovery steps and a yaw sign check.

Two independent default-off toggles under one profile, ``release17_v1``:

* ``release_fov_step_pulse_v1`` (A1): the FOV-recovery translation of
  release15/16 sent 4 mm (31 ms) micro pulses. Stored ledgers measured those
  at 0.71-0.87 of nominal (16 pulses moved 0.8 mm in one run) while 0.1 s
  pulses were 1.02-1.07. Recovery now uses one 0.1 s / level-0.35 pulse
  (nominal 12.9 mm), escalating once to 0.15 s and then failing at once.
* ``command_motion='yaw_cal_v1'`` (A2): calibrated yaw sign/magnitude profile
  (sim/visible_belief.ODOMETRY_PROFILES). Here only its own-RGB sign check is
  implemented: after the first decisive yaw pulse the stationary beam must
  move in the image the way a counter-clockwise (Y>0) turn moves it. Every
  yaw-bearing pulse also keeps a 40 ms / level-0.35 floor (``yaw_pulse_for``):
  shorter wheel pulses fall under the wheel relay start threshold (act8 lost
  39.7% of commands; release16 74976: 31 ms pulses moved 0.8 mm).

Perception, map clearance, FOV prediction and every other limit are release16's.
Inputs are own RGB, issued commands, the fixed camera model and the static map.
Evaluation truth is never read here. Sources: see release17.md.
"""
from __future__ import annotations

import math

import numpy as np

from sim import release14, release15, release16
from sim.grasp_act_port import duty_wheels
from sim.release_regrasp_recovery import image_jacobian
from sim.visible_belief import odometry, rates

PROFILE = 'release17_v1'
PROFILES = (*release16.PROFILES, PROFILE)
FOV_STEP = 'release_fov_step_pulse_v1'
FOV_STEPS = ('off', FOV_STEP)
YAW_CAL = 'yaw_cal_v1'
YAW_CAL_PROFILES = (YAW_CAL, 'lateral_rate_cal_v1')
SAFE = release16.SAFE
BASE_PERIOD_S = .1
ESCALATED_PERIOD_S = .15
HALF = .5          # observed merit drop must reach this fraction of the predicted drop
CREDIT_MAX = 1.1   # a stalled step's cap refund uses min(observed score, this); only stalled steps are refunded
SIGN_MODEL_PX = 10.     # model-predicted centre shift needed before the sign check is decisive
SIGN_OBSERVED_PX = 6.   # observed opposite shift needed to call a mismatch (JPEG/line noise below)
SIGN_YAW_DOMINANCE = 2.  # yaw term must exceed this multiple of the lateral term in the model
EDGE_MIN_PX = 6.         # an unclipped box edge must be predicted to move this far to count as evidence
CLIP_SAMPLE_PX = 3       # pixels beyond a box edge probed for the usable-region (undistortion) boundary
YAW_FLOOR_S = .04        # shortest wheel pulse sent in a yaw-bearing command (act8 01a892fa '.35, 40-100 ms')
YAW_DEADBAND_S = .02     # a wheel needing less than this is dropped when another wheel moves; else raised to the floor


def validate(profile, record_training, options, plan):
    """Run before any backend, output or prefix exists (also the Python API)."""
    fov_step = options.get('release_fov_step', 'off')
    motion = options.get('command_motion')
    if fov_step not in FOV_STEPS:
        raise ValueError('unknown release_fov_step')
    if profile != PROFILE:
        if fov_step != 'off' or motion == YAW_CAL:
            raise ValueError('release_fov_step and yaw_cal_v1 require the release17 profile')
        return release16.validate(profile, record_training, options, plan)
    if motion not in ('native_yaw_v1', YAW_CAL):
        raise ValueError('release17 requires command_motion native_yaw_v1 or yaw_cal_v1')
    # release14.SAFE pins command_motion to native_yaw_v1; the calibrated
    # profile is the only other value this profile may use.
    release16.validate(release16.PROFILE, record_training,
                       {**options, 'command_motion': 'native_yaw_v1'}, plan)


def floor_pulse(wheels, durations, floor=YAW_FLOOR_S, deadband=YAW_DEADBAND_S):
    """Raise every nonzero wheel pulse to ``floor``; a wheel under ``deadband`` is dropped if another one moves.

    If every wheel is under ``deadband`` the command is one ``floor`` pulse
    on the wheels needing at least half the largest request (the next image
    verifies it). Returns (wheels, durations, info).
    """
    d = np.array(durations, float)
    moving = d >= .001
    info = dict(requested_s=[float(v) for v in d], floor_s=floor, deadband_s=deadband)
    if not moving.any():
        return list(wheels), [0.]*len(d), dict(info, mode='none')
    if (d >= deadband).any():
        out = np.where(d >= deadband, np.maximum(d, floor), 0.)
        mode = 'floor' if (out != np.where(moving, d, 0.)).any() else 'unchanged'
    else:
        out = np.where(d >= .5*d.max(), floor, 0.)
        mode = 'single_pulse'
    kept = [float(w) if v > 0 else 0. for w, v in zip(wheels, out)]
    return kept, [float(v) for v in out], dict(info, mode=mode, applied_s=[float(v) for v in out])


def yaw_pulse_for(dx, dy, yaw, profile):
    """release14.pulse_for, plus the 40 ms floor for yaw-bearing pulses under yaw_cal_v1 only."""
    wheels, durations = release14.pulse_for(dx, dy, yaw, profile)
    if profile not in YAW_CAL_PROFILES or abs(yaw) <= 1e-9:
        return wheels, durations, None
    return floor_pulse(wheels, durations)


def recovery_pulse(dx, dy, profile, period):
    """Pulse (wheels, durations) whose nominal body motion is (dx, dy) over ``period``.

    ``period`` = 0.1 gives exactly the 0.1 s level-0.35 pulse for a
    (ax*0.1, lat*0.1) request; 0.15 is the single escalation (contract max).
    """
    ax, lat, _ = rates(profile)
    return duty_wheels([dx/ax*.35/period, dy/lat*.35/period, 0.], period)


def recovery_candidates(profile, period):
    """The release15 eight directions, each as one real pulse and its realized nominal motion.

    A diagonal shares wheels, so its realized motion is half of each axis
    request. The prediction below always uses the realized motion, never the request.
    """
    ax, lat, _ = rates(profile)
    out = []
    for sx, sy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
        wheels, durations = recovery_pulse(sx*ax*period, sy*lat*period, profile, period)
        realized = odometry([w*d/.1 for w, d in zip(wheels, durations)], .1, profile)
        out.append((wheels, durations, (float(realized[0]), float(realized[1]))))
    return out


def line_step(f, camera, pwm, *, clearance, profile='native_yaw_v1', period=BASE_PERIOD_S):
    """release15.line_step with the partition (translation) branch as single pulses."""
    zero = dict(forward=0., left=0., yaw=0., aligned=False)
    if not f.get('valid') or not f.get('points'):
        return dict(kind='unobserved', **zero)
    if f.get('line') is not None and f['fov_safe']:
        # release15's coupled IBVS branch verbatim; only its translation fall-through is replaced below.
        step = release14.line_step(f, camera, pwm)
        if step['aligned']:
            return dict(forward=0., **step)
        for scale in (1., .5, .25):
            motion = np.array([0., step['left'], step['yaw']])*scale
            if release15.inside(release15.project_motion(f['points'], camera, pwm, motion)) and clearance(*motion):
                return dict(step, forward=0., left=float(motion[1]), yaw=float(motion[2]))
    current = release15.fov_merit(f['points']); candidates = []
    for wheels, durations, (dx, dy) in recovery_candidates(profile, period):
        if not clearance(dx, dy, 0.):
            continue
        predicted = release15.project_motion(f['points'], camera, pwm, (dx, dy, 0.))
        if not release15.recovery_keeps_features(f['points'], predicted):
            continue
        merit = release15.fov_merit(predicted)
        if merit < current-1. or (current == 0. and dx < 0. and dy == 0. and release15.inside(predicted)):
            candidates.append((round(merit, 6), math.hypot(dx, dy), dx, dy, wheels, durations))
    if not candidates:
        return dict(kind='fov_blocked', **zero)
    merit, _, dx, dy, wheels, durations = min(candidates, key=lambda c: c[:4])
    return dict(kind='recover_fov', forward=dx, left=dy, yaw=0., aligned=False,
                merit=current, predicted_merit=merit, wheels=wheels, durations=durations, period=period)


def clipped_edges(box):
    """(left, top, right, bottom) True where the visible box touches the usable-region boundary.

    Such an edge is where the image ends, not where the object ends, so it
    cannot show the motion. Stored runs: the top edge sat at row 13, the first
    usable row, for 30-40 mm of real forward motion while fov_merit stayed constant.
    """
    from harness.zone_own_perception import _usable_region
    usable = _usable_region(640, 480)
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    def outside(ys, xs):
        ys, xs = np.asarray(ys), np.asarray(xs)
        inside = (ys >= 0) & (ys < 480) & (xs >= 0) & (xs < 640)
        ok = np.zeros(len(ys), bool)
        ok[inside] = usable[ys[inside], xs[inside]]
        return float((~ok).mean()) >= .5
    span_y = np.linspace(y0, y1, 9).astype(int); span_x = np.linspace(x0, x1, 9).astype(int)
    m = CLIP_SAMPLE_PX
    return (outside(span_y, np.full(9, x0-m)), outside(np.full(9, y0-m), span_x),
            outside(span_y, np.full(9, x1+m)), outside(np.full(9, y1+m), span_x))


def edge_progress(box, points, box_after, motion, camera, pwm):
    """Did the UNCLIPPED box edges move as the one-pulse prediction says? Own RGB + issued motion only.

    Returns kind 'progress' (observed >= HALF of predicted, summed over usable edges),
    'stall', or 'inconclusive' (every edge clipped or predicted to move < EDGE_MIN_PX).
    """
    predicted = release15.project_motion(points, camera, pwm, motion)
    new = (predicted[:, 0].min(), predicted[:, 1].min(), predicted[:, 0].max(), predicted[:, 1].max())
    skip = [a or b for a, b in zip(clipped_edges(box), clipped_edges(box_after))]
    num = den = 0.
    for k in range(4):
        shift = float(new[k]-box[k])
        if skip[k] or abs(shift) < EDGE_MIN_PX:
            continue
        num += (box_after[k]-box[k])*math.copysign(1., shift); den += abs(shift)
    if den == 0.:
        return dict(kind='inconclusive', score=None, predicted_px=0., clipped=skip)
    score = num/den
    return dict(kind='progress' if score >= HALF else 'stall', score=float(score), predicted_px=float(den), clipped=skip)


def yaw_expected_shift_px(camera, pwm, left, yaw):
    """(model centre shift px, yaw term px, lateral term px) of an IBVS step; nominal fixed camera."""
    j, _ = image_jacobian(camera, pwm)
    return (float((j[0, 0]*left+j[0, 1]*yaw)*640), float(j[0, 1]*yaw*640), float(j[0, 0]*left*640))


def yaw_sign_verdict(expected_px, yaw_px, lateral_px, observed_px):
    """'verified' | 'mismatch' | 'inconclusive'. Dead bands keep JPEG noise from stopping a run."""
    if abs(expected_px) < SIGN_MODEL_PX or abs(yaw_px) < SIGN_YAW_DOMINANCE*abs(lateral_px):
        return 'inconclusive'
    if observed_px*expected_px > 0 and abs(observed_px) >= SIGN_OBSERVED_PX:
        return 'verified'
    if observed_px*expected_px < 0 and abs(observed_px) >= SIGN_OBSERVED_PX:
        return 'mismatch'
    return 'inconclusive'


class LineAlign(release16.LineAlign):
    def __init__(self, teacher, now, *, camera, undistort, wheel_command, clearance,
                 pick_audit=None, fov_step='off'):
        if fov_step not in FOV_STEPS:
            raise ValueError('unknown release_fov_step')
        super().__init__(teacher, now, camera=camera, undistort=undistort, wheel_command=wheel_command,
                         clearance=clearance, pick_audit=pick_audit)
        self.fov_step = fov_step
        self.sign_state = 'unchecked' if teacher.odometry_profile in YAW_CAL_PROFILES else 'not_applicable'
        self.sign_pending = None; self.pending = None; self.stall = 0

    def fail(self, reason):
        self.failure = 'release17_'+reason; self.state = 'failed'
        return 'failed'

    # -- A1 helpers ------------------------------------------------------
    def settle_pending(self, f, now):
        """Judge the last one-pulse step on the NEW own RGB; update stall, 3 s timer and cap charge.

        Progress = unclipped box edges moved >= half of the prediction (edge_progress) OR
        fov_merit fell by >= half of the predicted drop. The merit alone is blind while the
        clipped top edge is pinned, so it can only add progress, never declare a stall.
        """
        pending, self.pending = self.pending, None
        if pending is None:
            return None
        if not f.get('valid') or not f.get('points') or not f.get('visible_box_px'):
            self.stall = 0
            return dict(event='fov_step_unobserved', t=now)
        merit = release15.fov_merit(f['points'])
        predicted_drop = pending['merit']-pending['predicted_merit']
        merit_ok = predicted_drop > 1e-9 and pending['merit']-merit >= HALF*predicted_drop
        try:
            edge = edge_progress(pending['box'], pending['points'], f['visible_box_px'],
                                 (pending['actual'][0], pending['actual'][1], 0.), self.camera, pending['pwm'])
        except (ValueError, np.linalg.LinAlgError):
            edge = dict(kind='inconclusive', score=None, predicted_px=0., clipped=None)
        verdict = 'progress' if (merit_ok or edge['kind'] == 'progress') else edge['kind']
        if verdict == 'stall':
            # No motion in the image: charge nothing for the step (cap counts what the image shows).
            self.motion -= np.abs(pending['actual'])*(1.-float(np.clip(max(edge['score'], 0.), 0., CREDIT_MAX)))
            self.stall += 1
        elif verdict == 'progress':
            self.stall = 0; self.progress = now
        return dict(event='fov_step_result', t=now, period=pending['period'], verdict=verdict,
                    edge_score=edge['score'], edge_predicted_px=edge['predicted_px'], clipped_edges=edge['clipped'],
                    merit_before=pending['merit'], predicted_merit=pending['predicted_merit'],
                    merit_after=merit, merit_ok=bool(merit_ok), stall=self.stall)

    def check_yaw_sign(self, f, now):
        pending = self.sign_pending
        if pending is None or self.sign_state != 'unchecked':
            return
        if f.get('center_error') is None or not f.get('valid'):
            return  # beam not seen: keep the pending check for the next usable image
        self.sign_pending = None
        observed = (f['center_error']-pending['center_error'])*640
        verdict = yaw_sign_verdict(pending['expected_px'], pending['yaw_px'], pending['lateral_px'], observed)
        self.records.append(dict(t=now, event='yaw_sign_check', verdict=verdict, observed_px=float(observed),
                                 expected_px=pending['expected_px'], yaw_px=pending['yaw_px'],
                                 lateral_px=pending['lateral_px']))
        if verdict == 'verified':
            self.sign_state = 'verified'
        elif verdict == 'mismatch':
            self.sign_state = 'mismatch'

    # -- tick: release15.tick, with the two gated changes ------------------
    def choose_step(self, f, period, now):
        if self.fov_step == 'off':
            return release15.line_step(f, self.camera, self.teacher.pwm, clearance=self.clearance)
        return line_step(f, self.camera, self.teacher.pwm, clearance=self.clearance,
                         profile=self.teacher.odometry_profile, period=period)

    def tick(self, now, capture, schedule):
        if self.fov_step == 'off' and self.sign_state == 'not_applicable':
            return super().tick(now, capture, schedule)
        if self.failure: return 'failed'
        if self.state == 'done': return 'ready'
        if now-self.started > 16.: return self.fail('line_timeout')
        if now < self.until-1e-8: return 'pending'
        rid = self.teacher.rid
        if self.state == 'open':
            schedule(rid, [(0., {1: 2000}), (1.2, self.hover)], now)
            self.state = 'align'; self.until = now+2.6; self.progress = self.until
            self.records.append(dict(t=now, event='open_then_hover'))
            return 'pending'
        if self.teacher.pwm != self.expected: return self.fail('open_hover_command_changed')
        f = self.features(self.undistort(capture(rid, now, 'line_recheck')))
        self.records.append(dict(t=now, event='image', **f))
        self.check_yaw_sign(f, now)
        if self.sign_state == 'mismatch': return self.fail('yaw_cal_sign_mismatch')
        result = self.settle_pending(f, now) if self.fov_step != 'off' else None
        if result:
            self.records.append(result)
            if result['event'] == 'fov_step_result' and self.stall >= 2:
                return self.fail('no_recover_fov_progress')
        period = ESCALATED_PERIOD_S if self.stall == 1 else BASE_PERIOD_S
        try:
            step = self.choose_step(f, period, now)
        except (ValueError, np.linalg.LinAlgError) as error: return self.fail(str(error))
        if step['kind'] == 'unobserved':
            self.stable = None
            self.missing = now if self.missing is None else self.missing
            self.wheel_command(rid, [0.]*4, [0.]*4, now)
            if now-self.missing >= 1.-1e-8: return self.fail('shaft_unobserved_1s')
            self.until = now+.2
            return 'pending'
        self.missing = None
        if self.mode != step['kind']:
            self.mode = step['kind']; self.best = math.inf; self.progress = now
            self.records.append(dict(t=now, event='mode_enter', mode=self.mode))
        if step['aligned']:
            self.stable = now if self.stable is None else self.stable
            if now-self.stable >= .3-1e-8:
                self.state = 'done'
                if self.pick_audit: self.pick_audit(now, self.teacher, self.xy)
                self.records.append(dict(t=now, event='aligned_before_pick', xy=list(self.xy), target_source='commanded_station'))
                return 'ready'
            self.until = now+.1
            return 'pending'
        self.stable = None
        if step['kind'] == 'fov_blocked': return self.fail('fov_no_safe_translation')
        one_pulse = self.fov_step != 'off' and step['kind'] == 'recover_fov'
        if step['merit'] < self.best-.1: self.best = step['merit']; self.progress = now
        elif now-self.progress >= 3.: return self.fail('no_'+self.mode+'_progress_3s')
        floor = None
        if step.get('allocated_pulse') is not None:
            w, d = step['allocated_pulse']
        elif one_pulse:
            w, d = step['wheels'], step['durations']
        else:
            w, d, floor = yaw_pulse_for(step['forward'], step['left'], step['yaw'], self.teacher.odometry_profile)
        actual = np.array(odometry([a*b/.1 for a, b in zip(w, d)], .1, self.teacher.odometry_profile))
        if np.any(self.motion+abs(actual) > np.array([.10, .10, math.radians(18)])+1e-9): return self.fail('motion_cap')
        if not self.clearance(*actual): return self.fail('map_motion_clearance')
        self.motion += abs(actual)
        self.wheel_command(rid, w, d, now)
        self.records.append(dict(t=now, event=step['kind'], wheels=w, durations=d,
                                 **({'yaw_floor': dict(floor, realized_motion=[float(v) for v in actual])} if floor else {}),
                                 **{k: v for k, v in step.items() if k not in ('wheels', 'durations')}))
        if one_pulse and step['merit'] > 0. and f.get('visible_box_px'):
            self.pending = dict(merit=step['merit'], predicted_merit=step['predicted_merit'], period=step['period'],
                                actual=actual, box=list(f['visible_box_px']), points=[list(p) for p in f['points']],
                                pwm=dict(self.teacher.pwm))
        if (self.sign_state == 'unchecked' and abs(step['yaw']) > 1e-9 and step['kind'] != 'recover_fov'
                and f.get('center_error') is not None):
            try:
                # the floored pulse turns more than requested: predict from what was issued
                left, yaw = (float(actual[1]), float(actual[2])) if floor else (step['left'], step['yaw'])
                expected, yaw_px, lateral_px = yaw_expected_shift_px(self.camera, self.teacher.pwm, left, yaw)
            except (ValueError, np.linalg.LinAlgError):
                expected = None
            if expected is not None:
                self.sign_pending = dict(center_error=f['center_error'], expected_px=expected,
                                         yaw_px=yaw_px, lateral_px=lateral_px)
        self.until = now+.2
        return 'pending'

    def record(self):
        out = super().record()
        out.update(release17=dict(fov_step=self.fov_step, yaw_sign_state=self.sign_state))
        return out


line_features = release16.line_features
map_motion_clear = release16.map_motion_clear
backoff_plan = release16.backoff_plan
approach_plan = release16.approach_plan
