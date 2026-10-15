"""Opt-in box retreat margin; the RGB judge and camera remain unchanged.

150 mm is checked statically with 40 mm retreat shortfall, +/-5 mm held-centre
translation and +/-1 degree tilt. These are sensitivity cases, not verified
physical uncertainty bounds. No live evaluator data enters this action plan.
"""
from harness.visual_arm_v3 import forward_grip
from sim.grasp_act_solo_lookback import plan_lookback, regions
from sim.grasp_act_solo_teacher import BOX_KINDS

MODE = 'solo_lift_lookback_margin_v1'
BACKOFF_M = .150
SHORTFALL_M = .040


def plan_with_margin(kind, grasp_pwm, lift_pwm):
    if kind not in BOX_KINDS:
        raise ValueError('lookback margin v1 is box-only')
    plan = plan_lookback(kind, grasp_pwm, lift_pwm)
    x, y, _ = forward_grip(grasp_pwm)
    checks = [regions(kind, grasp_pwm, plan['pwm'], site=(x+BACKOFF_M+d, y, 0.))[2]
              for d in (-SHORTFALL_M-.005, -SHORTFALL_M, -.005, 0., .005)]
    if not all(c['qualified'] for c in checks):
        raise ValueError('box retreat margin has no framed unoccluded site')
    return {**plan, 'backoff_m': BACKOFF_M, 'geometry': checks[3],
            'action_margin_mode': MODE, 'short_retreat_geometry': checks[0],
            'retreat_shortfall_sensitivity_m': SHORTFALL_M,
            'held_shift_sensitivity_m': .005, 'held_tilt_sensitivity_deg': 1.,
            'scope': 'static sensitivity; actual retreat and held pose unverified'}
