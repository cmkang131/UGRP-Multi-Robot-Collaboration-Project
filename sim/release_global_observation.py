"""Own-camera global localization and bounded release observation recovery.

Only scalar margins cross the existing PairReleaseCode channel. No partner
pose, image, landmark, or map hypothesis is provided to a robot.
"""
from __future__ import annotations
import math
import numpy as np

OPTION = 'global_localized_release_v1'
BACKSTEP_M = .10
BODY_TURN_RAD = math.radians(45)
MAX_SHIFT_M = .20
MAX_CORRECTIONS = 5
MARGIN_M = .04
CENTER_TOL_M = .05
LATERAL_MODES = ('off', 'bounded_v1')
MAX_LATERAL_SHIFT_M = .10


def margin_report(localizer, teacher, now, *, lateral_recovery='off'):
    """Static zone bounds through the accepted own RGB pose, own release FK."""
    decision = localizer.decision or {}
    base = dict(phase='observe', kind='none', margin_m=None)
    if not decision.get('accepted'):
        return {**base, 'reason': decision.get('reason', 'unlocalized')}
    (ex,ey),(ox,oy),_=teacher.end_and_outward(now)
    x,y,a=localizer.own.x; c,s=math.cos(a),math.sin(a)
    point=np.array([x+c*ex-s*ey,y+s*ex+c*ey])
    outward=np.array([c*ox-s*oy,s*ox+c*oy])
    cx,cy,hx,hy=teacher.zone_rect
    axis=1 if hy>=hx else 0; lateral=1-axis
    # The unchanged teacher transports axially. Rotation is an observation
    # action only and returns to its starting heading before a grasp/shift.
    if abs(outward[axis])<math.cos(math.radians(10)):
        return {**base,'reason':'release_axis_unaligned'}
    center=np.array([cx,cy]);half=np.array([hx,hy]);sign=1 if outward[axis]>0 else -1
    margin=float(half[axis]-sign*(point[axis]-center[axis]))
    other=point-.60*outward
    lateral_clearance=float(half[lateral]-max(abs(point[lateral]-center[lateral]),abs(other[lateral]-center[lateral]))-.02)
    report = dict(phase='observe',kind='localized_margin',margin_m=margin,
                lateral_clearance_m=lateral_clearance,pose_sigma_m=max(decision['sigma'][:2]),
                expected_slack_m=2*float(half[axis])-.60,
                reason='own_rgb_map_consensus')
    if lateral_recovery == 'bounded_v1':
        # Same full-beam envelope and 2 cm thickness as the existing guard.
        # Transmit an admissible scalar displacement interval, never a pose.
        ends = [float(point[lateral]-center[lateral]), float(other[lateral]-center[lateral])]
        report.update(lateral_shift_lo_m=float(-half[lateral]+.02+MARGIN_M-min(ends)),
                      lateral_shift_hi_m=float(half[lateral]-.02-MARGIN_M-max(ends)))
    return report


def pair_choice(reports, robots, now, *, lateral_recovery='off'):
    """Use delivered margins only; balance ends, with a fresh look every leg."""
    rows=[reports[r] for r in robots]
    if not all(r and r.get('kind')=='localized_margin' for r in rows):
        return dict(action='observe',reason='global_pose_unobserved',t=now)
    if min(r['lateral_clearance_m'] for r in rows)<MARGIN_M:
        if lateral_recovery == 'bounded_v1':
            bounds = [(r.get('lateral_shift_lo_m'), r.get('lateral_shift_hi_m')) for r in rows]
            if any(v is None or not math.isfinite(v) for pair in bounds for v in pair):
                return dict(action='observe',reason='lateral_bounds_unobserved',t=now)
            lo=max(p[0] for p in bounds); hi=min(p[1] for p in bounds)
            if lo>hi:
                return dict(action='observe',reason='lateral_bounds_disagree',t=now)
            # Recenter the intersection rather than barely crossing a noisy
            # threshold. A bounded leg must improve both robots' constraints.
            shift=max(-MAX_LATERAL_SHIFT_M,min(MAX_LATERAL_SHIFT_M,(lo+hi)/2))
            if (lo>0 and shift<=0) or (hi<0 and shift>=0):
                return dict(action='observe',reason='lateral_direction_disagreement',t=now)
            return dict(action='shift',shift_m=0.,lateral_shift_m=shift,
                        lateral_interval_m=[lo,hi],reason='localized_lateral_correction',t=now)
        return dict(action='stop',reason='lateral_clearance_unresolved',t=now)
    margins=[r['margin_m'] for r in rows]
    shift=(margins[1]-margins[0])/2
    # Two independent estimates must agree that the beam fits this zone.
    # For long beams in this map: available axial slack = 2*0.70 - 0.60.
    # Consistency is evaluated via the posted expected slack (not positions).
    expected=[r.get('expected_slack_m') for r in rows]
    if None not in expected and abs(sum(margins)-sum(expected)/2)>.20:
        return dict(action='observe',reason='margin_disagreement',t=now,margins_m=margins)
    if abs(shift)<=CENTER_TOL_M and min(margins)>=MARGIN_M:
        return dict(action='lower',reason='localized_margins_centered',t=now,margins_m=margins)
    return dict(action='shift',shift_m=max(-MAX_SHIFT_M,min(MAX_SHIFT_M,shift)),
                reason='localized_margin_correction',t=now,margins_m=margins)


def lateral_shift_plans(localizers, teachers, shift_m):
    """Same map translation from each own RGB heading; shared 100 ms clock.

    Invert the existing mecanum map with nominal command odometry. Native
    magnitudes stay 0.35; per-wheel durations preserve the body-vector ratio.
    The next set-down/sweep closes the loop on slip and nominal-rate error.
    """
    from sim.visible_belief import rates
    from sim.grasp_act_release_teacher import check_wheels
    ax,lat,_=rates(); required={}
    if not math.isfinite(shift_m) or not 0<abs(shift_m)<=MAX_LATERAL_SHIFT_M+1e-9:
        raise ValueError('bounded nonzero lateral displacement required')
    for rid,teacher in teachers.items():
        loc=localizers[rid]
        if not (loc.decision or {}).get('accepted'):
            raise ValueError('own RGB map pose required')
        a=float(loc.own.x[2]); c,s=math.cos(a),math.sin(a)
        _,_,hx,hy=teacher.zone_rect
        dx,dy=(shift_m,0.) if hy>=hx else (0.,shift_m)
        f=(c*dx+s*dy)/ax; l=(-s*dx+c*dy)/lat
        required[rid]=[f-l,f+l,f+l,f-l]  # integrated wheel time at 0.35, yaw=0
    periods=math.ceil(max(abs(v) for row in required.values() for v in row)/.1)
    plans={}
    for rid,row in required.items():
        levels=[math.copysign(.35,v) if v else 0. for v in row]
        durations=[abs(v)/periods for v in row]
        if any(0<d<.04 for d in durations):
            raise ValueError('lateral vector below effective native pulse window')
        check_wheels(levels,durations)
        plans[rid]=[(levels.copy(),durations.copy()) for _ in range(periods)]
    return plans


def recovery_script(localizer, teacher, stage, now):
    """Pan -> bounded backstep -> body turn/return. No hidden pose inputs.

    Translation/turn clearance is checked against every surviving map
    hypothesis, inflated by 3*5 cm localization uncertainty. Unknown/unsafe
    clearance skips that motion, but still collects the next camera sweep.
    """
    from sim.lookaround_localization import look_servo, LOOK_ARM, LOOK_ARM_V2, rotate_plan
    restore={k:teacher.pwm[k] for k in (3,4,5,6)}
    decision=localizer.decision or {}
    candidates=decision.get('credible_hypotheses',decision.get('alternatives',[]))
    hypotheses=np.array([h['pose'] for h in candidates],float).reshape(-1,3)
    matcher=localizer.global_matcher
    safe=bool(len(hypotheses))
    # The matcher free() includes robot radius .18; this adds the 3-sigma halo.
    if safe:
        for distance in np.linspace(0,BACKSTEP_M if stage==2 else 0,6):
            q=hypotheses.copy();q[:,0]-=distance*np.cos(q[:,2]);q[:,1]-=distance*np.sin(q[:,2])
            safe &= bool(matcher.free(q,extra_clearance=.15).all())
    steps=[dict(servo=look_servo(0,LOOK_ARM_V2),wait=1.,capture=False,label='recovery_fold')]
    action='pan'
    if stage==2 and safe:
        steps.append(dict(wheels=teacher.shift_plan(BACKSTEP_M,-1.),wait=.3,capture=False,label='recovery_back_0.10m'))
        action='backstep'
    elif stage==3 and safe:
        steps.append(dict(wheels=rotate_plan(BODY_TURN_RAD),wait=.3,capture=False,label='recovery_turn_45deg'))
        action='body_turn'
    elif stage>1:
        action='motion_skipped_clearance_unknown_or_unsafe'
    for arm,label in ((LOOK_ARM_V2,'surroundings'),(LOOK_ARM,'floor')):
        for i,p in enumerate((-90.,-45.,0.,45.,90.)):
            steps.append(dict(servo=look_servo(p,arm),wait=1. if i==0 else .8,capture=True,label=f'recovery_{stage}_{label}_{p:+.0f}'))
    if stage==3 and safe:
        steps.append(dict(wheels=rotate_plan(-BODY_TURN_RAD),wait=.3,capture=False,label='recovery_turn_return'))
    steps.append(dict(servo=restore,wait=1.,capture=False,label='restore_arm'))
    return steps,dict(stage=stage,action=action,t=now,backstep_cap_m=BACKSTEP_M,
                      body_turn_rad=BODY_TURN_RAD,all_retained_hypotheses_clear=safe)


def recovery_round(localizers, teachers, reports, stages, now, *, active_recovery='off', nbv_history=None):
    """Build one round atomically. Accepted own margins wait for the partner.

    Extra NBV rounds run only where the old three-stage policy would stop.
    All successful legacy trajectories therefore keep their decisions.
    No robot receives another robot's localization inputs or hypotheses.
    """
    from sim.release_nbv_observation import MODES, MAX_ROUNDS, script
    if active_recovery not in MODES:
        raise ValueError(active_recovery)
    pending = [rid for rid in teachers if reports[rid]['kind'] != 'localized_margin']
    if not pending:
        pending = list(teachers)  # scalar margins disagree
    history = nbv_history if nbv_history is not None else {rid: [] for rid in teachers}
    if active_recovery == 'off' and any(stages[rid] >= 3 for rid in pending):
        return None, []
    steps = {rid: [] for rid in teachers}; entries = []
    for rid in pending:
        if stages[rid] < 3:
            steps[rid], entry = recovery_script(localizers[rid], teachers[rid], stages[rid]+1, now)
        else:
            if len(history[rid]) >= MAX_ROUNDS:
                return None, []
            used = [v['key'] for previous in history[rid] for v in previous['views']]
            steps[rid], entry = script(localizers[rid], teachers[rid], now, used=used)
            if not steps[rid]:
                return None, [dict(robot=rid, stage=stages[rid], **entry)]
        entries.append({**entry, 'robot':rid, 'stage':stages[rid]+1})
    for entry in entries:
        rid = entry['robot']; stages[rid] += 1
        if entry['action'] == 'map_nbv':
            history[rid].append(entry)
    return steps, entries
