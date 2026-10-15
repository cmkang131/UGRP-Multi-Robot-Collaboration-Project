"""Bounded, default-off IBVS retry. Own RGB + issued PWM; no world input.

The two image features are shaft centre and row-to-row centre difference.
The interaction matrix uses the existing command-camera calibration and a
fixed nominal beam-top plane, NOT an observed cargo position/depth. It is an
approximation (Chaumette/Hutchinson 2006); every pulse needs a fresh image.
Solo/beam teacher truth-coordinate aligners are deliberately not called.
"""
from __future__ import annotations

import math
import numpy as np

from sim.release_regrasp import beam_mask
from sim.grasp_act_port import duty_wheels
from sim.visible_belief import rates, odometry

OPTION = 'own_rgb_realign_v1'
MODES = ('off', OPTION)
BACKOFF_M = .03
ALIGN_CAP_S = 12.
RECOVERY_CAP_S = 22.
MAX_LATERAL_M = .10
MAX_YAW_RAD = math.radians(12)
CENTER_TOL = .025
SLOPE_TOL = .025


def shaft_features(frame):
    """Normalized row-centre features; clipped edges never license yaw/pick."""
    import cv2
    from harness.zone_own_perception import _usable_region
    if frame is None or frame.shape != (480,640,3) or frame.dtype != np.uint8:
        return dict(valid=False,reason='shaft_invalid_frame')
    mask = beam_mask(frame)
    h, w = mask.shape
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype('uint8'))
    ranked = sorted(range(1, count), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    if not ranked or stats[ranked[0], cv2.CC_STAT_AREA] < .015*w*h:
        return dict(valid=False, reason='shaft_missing')
    if len(ranked)>1 and stats[ranked[1], cv2.CC_STAT_AREA] > .3*stats[ranked[0], cv2.CC_STAT_AREA]:
        return dict(valid=False, reason='shaft_ambiguous')
    component = labels == ranked[0]
    ys, xs = np.nonzero(component)
    usable = _usable_region(w, h)
    rows = []
    for y in range(h//5, 4*h//5, 4):
        x = np.flatnonzero(component[y]); bounds = np.flatnonzero(usable[y])
        if len(x) < 8 or not len(bounds):
            continue
        clear = x[0] > bounds[0]+3 and x[-1] < bounds[-1]-3
        rows.append((y, (x[0]+x[-1])/2., clear))
    base = dict(valid=True, center_x_px=float(xs.mean()),
                offset_px=float(xs.mean()-(w-1)/2), image_width=w,
                center_error=float((xs.mean()-(w-1)/2)/w), slope_error=None,
                unclipped=False, reason='shaft_clipped')
    clear = np.array([(y,x) for y,x,ok in rows if ok])
    if len(clear)<12 or np.ptp(clear[:,0]) < .25*h:
        return base
    slope, intercept = np.polyfit(clear[:,0], clear[:,1], 1)
    if np.quantile(abs(clear[:,1]-(slope*clear[:,0]+intercept)), .9) > .02*w:
        return dict(valid=False, reason='shaft_nonlinear')
    base.update(center_error=float((slope*(h-1)/2+intercept-(w-1)/2)/w),
                slope_error=float(slope*.4*h/w), unclipped=True, reason='shaft_rows')
    return base


def image_jacobian(camera, pwm):
    """Desired-line image Jacobian for body left metres / CCW yaw radians.

    Only static nominal top height (.032 m), K, and issued camera FK enter.
    Project a fixed reference line then differentiate its IMAGE features.
    No current target/world pose is reconstructed or accepted as an input.
    """
    cam, reason = camera.pose(pwm)
    if cam is None:
        raise ValueError('camera_'+str(reason))
    origin, rot = map(np.asarray, cam)
    k = np.asarray(camera.K); kinv = np.linalg.inv(k)
    uv = np.array([[k[0,2], .3*480, 1.], [k[0,2], .7*480, 1.]])
    rays = (rot@kinv@uv.T).T
    if np.any(rays[:,2] >= -1e-4):
        raise ValueError('camera_plane_unobservable')
    distance = (.032-origin[2])/rays[:,2]
    if np.any(distance <= 0) or np.any(distance > 1.5):
        raise ValueError('camera_plane_unobservable')
    points = origin+distance[:,None]*rays
    # Fixed desired centreline in the command-camera frame.
    def features(left, yaw):
        c, s = math.cos(yaw), math.sin(yaw)
        q = points-np.array([0.,left,0.])
        q = q@np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
        optical = (q-origin)@rot
        if np.any(optical[:,2] <= .01):
            raise ValueError('camera_line_behind')
        px = optical@k.T; px = px[:,:2]/px[:,2,None]
        if abs(px[1,1]-px[0,1]) < 10:
            raise ValueError('camera_line_short')
        slope = (px[1,0]-px[0,0])/(px[1,1]-px[0,1])
        center = px[0,0]+slope*(239.5-px[0,1])
        return np.array([(center-319.5)/640, slope*192/640])
    j = np.column_stack(((features(.001,0)-features(-.001,0))/.002,
                         (features(0,.005)-features(0,-.005))/.010))
    if not np.isfinite(j).all() or np.linalg.cond(j)>100:
        raise ValueError('camera_line_singular')
    return j, features(0,0)


class RealignRecovery:
    """One failed robot only; open before motion, recheck before close.

    Callbacks are own-image capture, own arm scheduling and own wheel pulses.
    The owner enforces peer stationarity and clears all old confirmations.
    """
    def __init__(self, teacher, now, *, camera, undistort, wheel_command):
        from harness.visual_arm_v3 import MOUNT_X_M, solve_grip_site_ik
        self.teacher = teacher
        self.camera, self.undistort, self.wheel_command = camera, undistort, wheel_command
        self.started = now; self.until = now; self.state = 'open'; self.failure = None
        self.records = []; self.lateral = self.yaw = 0.; self.axial = 0.
        self.xy = (MOUNT_X_M+teacher.reach_mid(), 0.)
        self.hover = {k:int(v) for k,v in solve_grip_site_ik((*self.xy,.095)).items() if k in (3,4,5,6)}
        self.expected = {**teacher.pwm, **self.hover, 1:2000}
        self.plan = []; self.returned = False; self.stable = None
        self.best = math.inf; self.progress = now; self.align_started = None
        self.missing = None

    def fail(self, reason):
        self.failure = 'regrasp_realign_'+reason
        self.state = 'failed'
        return 'failed'

    def pulse(self, wheels, durations, now, label):
        # Record actual issued pulse integrals, never measured displacement.
        effective = [w*d/.1 for w,d in zip(wheels,durations)]
        dx,dy,da = odometry(effective,.1,self.teacher.odometry_profile)
        if self.axial+abs(dx)>.08 or self.lateral+abs(dy)>MAX_LATERAL_M+1e-9 or self.yaw+abs(da)>MAX_YAW_RAD+1e-9:
            return self.fail('motion_cap')
        self.axial += abs(dx); self.lateral += abs(dy); self.yaw += abs(da)
        self.wheel_command(self.teacher.rid,wheels,durations,now)
        self.records.append(dict(t=now,event=label,wheels=wheels,durations=durations))
        self.until = now+.2  # pulse <= .1 s, then quiet image acquisition
        return 'pending'

    def tick(self, now, capture, schedule):
        if self.failure:return 'failed'
        if now-self.started>RECOVERY_CAP_S:return self.fail('timeout')
        if now<self.until-1e-8:return 'pending'
        rid = self.teacher.rid
        if self.state=='open':
            # Open at the restored lift pose BEFORE moving arm/base.
            schedule(rid,[(0.,{1:2000}),(1.2,self.hover)],now)
            self.records.append(dict(t=now,event='open_then_hover'))
            self.state='back'; self.until=now+2.6
            self.plan=self.teacher.shift_plan(BACKOFF_M,-1.)
            return 'pending'
        if self.teacher.pwm != self.expected:
            return self.fail('open_hover_command_changed')
        if self.state in ('back','return'):
            if self.plan:
                w,d=self.plan.pop(0)
                return self.pulse(w,d,now,self.state)
            self.state='align'; self.until=now+.3
            if self.align_started is None:self.align_started=now
            self.best=math.inf; self.progress=now; self.stable=None
            return 'pending'
        if now-self.align_started>ALIGN_CAP_S:return self.fail('align_timeout')
        feature=shaft_features(self.undistort(capture(rid,now,'realign_'+('final' if self.returned else 'back'))))
        self.records.append(dict(t=now,event='image',**feature))
        if not feature['valid']:
            self.stable=None; self.missing=now if self.missing is None else self.missing
            if now-self.missing>=1.:return self.fail(feature['reason'])
            self.until=now+.2
            return 'pending'
        self.missing=None
        try:j, desired=image_jacobian(self.camera,self.teacher.pwm)
        except ValueError as error:return self.fail(str(error))
        e=feature['center_error']-desired[0]
        slope=feature['slope_error']
        aligned=feature['unclipped'] and abs(e)<=CENTER_TOL and abs(slope-desired[1])<=SLOPE_TOL
        if aligned:
            self.stable=now if self.stable is None else self.stable
            if now-self.stable>=.3-1e-8:
                if not self.returned:
                    self.returned=True;self.state='return';self.plan=self.teacher.shift_plan(BACKOFF_M,1.)
                else:
                    self.state='done'
                    self.records.append(dict(t=now,event='aligned_before_pick',target_source='commanded_station',xy=list(self.xy)))
                    return 'ready'
            self.until=now+.1
            return 'pending'
        self.stable=None
        merit=abs(e)/CENTER_TOL+(abs(slope-desired[1])/SLOPE_TOL if slope is not None else 1.)
        if merit<self.best-.25:self.best=merit;self.progress=now
        elif now-self.progress>=3.:return self.fail('no_image_progress_3s')
        if feature['unclipped']:
            delta=-np.linalg.solve(j,np.array([feature['center_error'],slope])-desired)
            # Same single-axis yaw-before-left policy as solo align_relook_v1.
            left,yaw=(0.,float(np.clip(.7*delta[1],-.10,.10))) if abs(delta[1])>.035 else (float(np.clip(.7*delta[0],-.04,.04)),0.)
        else:
            left=float(np.clip(-.7*e/j[0,0],-.04,.04));yaw=0.
        _,lat_rate,yaw_rate=rates(self.teacher.odometry_profile)
        w,d=duty_wheels([0.,left/lat_rate*.35,yaw/yaw_rate*.35])
        d=[max(.04,v) if level else 0. for level,v in zip(w,d)]
        return self.pulse(w,d,now,'align_pulse')

    def record(self):
        return dict(robot=self.teacher.rid,state=self.state,failure=self.failure,
            commanded_absolute_motion=dict(axial_m=self.axial,lateral_m=self.lateral,yaw_rad=self.yaw),
            events=self.records,inputs='own RGB and issued PWM; fixed camera/nominal beam height',
            physical_validation='unverified')
