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


def margin_report(localizer, teacher, now):
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
    return dict(phase='observe',kind='localized_margin',margin_m=margin,
                lateral_clearance_m=lateral_clearance,pose_sigma_m=max(decision['sigma'][:2]),
                expected_slack_m=2*float(half[axis])-.60,
                reason='own_rgb_map_consensus')


def pair_choice(reports, robots, now):
    """Use delivered margins only; balance ends, with a fresh look every leg."""
    rows=[reports[r] for r in robots]
    if not all(r and r.get('kind')=='localized_margin' for r in rows):
        return dict(action='observe',reason='global_pose_unobserved',t=now)
    if min(r['lateral_clearance_m'] for r in rows)<MARGIN_M:
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
