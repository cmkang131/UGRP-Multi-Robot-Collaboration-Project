"""v98 only: sigma-triggered set-down re-fix during the HIGH carry (user decision 2026-10-04).

User: "끝까지 옮기는 게 E2E지. 짐작해서 가는 게 맞아. 근데 어느정도 모르겠으면, 짐을 두고 주변을 둘러보면 되는 거잖아".
The pair dead-reckons at HIGH (no wall is visible there, offline note 2026-10-04). When the own estimate would leave
its budget before the next place where the pair can set the beam down, both robots set it down now, release, look
around with the existing own-camera re-look, re-grasp and continue the fixed schedule.

When (belief-space planning, coastal navigation: Roy, Burgard, Fox and Thrun 1999; Prentice and Roy 2009; Bry and
Roy 2011). At the end of carry leg k (route stop j = k+1) each robot predicts its OWN estimate over the coming
legs with its own particle filter's motion model (``predict``: the live PF is advanced through the planned commands
of those legs without observations, then restored bit for bit). The horizon runs to the next stop where a re-fix is
allowed, because no re-fix can happen in between. The robot requests a re-fix when the prediction leaves the budget
or when its own report is already over the DR receipt budget (``zone_pair_highpose_dr_checkpoint``, which every HIGH
stop runs; the HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED case is decided here, before the barrier, so an over-budget DR
report leads to a re-fix, not to the HIGH re-observe wait).

Budget (alert limit vs protection level, Reid et al. 2019; values given, nothing tuned on outcomes; ONE derivation
shared with the DR receipt, coordinator decision 5, ``dr_checkpoint.budget``):
* loaded gate 70 mm / 3 deg (``zone_own_guards.GATE_LOADED``, the gate in force, see the DR note). The gate compares
  the PF's own sigma, and the prediction forecasts that same quantity with the same model, so the only margin is the
  Monte-Carlo error of two independent N-particle spread estimates: relative standard error 1/sqrt(2N) each,
  difference sqrt(2) times that, one-sided 95 %: 1.645/sqrt(N) (3.7 % at N = 2000): 67.43 mm / 2.89 deg.
* door lateral alert limit: AL = half free width - chassis half width - BASE_MARGIN_M - BODY_COVERAGE_RESIDUAL_M
  = 0.25 - 0.105 - 0.02 - 0.015 = 0.110 m; protection level PL = 1.96 * sqrt(sigma_y^2 + (lever*sigma_yaw)^2) with
  the chassis corner lever; required PL <= AL (sigma_y <= ~56 mm) while the own chassis overlaps the door x range
  (chassis half width 0.105 m, coordinator decision 4).

Who decides (identical in all four communication conditions; skill-level coordination, not dialogue). Each robot's
bit crosses the existing fixed-enum pair status only: during the decision window [t_end, t_end + D] (t_end = the
leg's scheduled end, built from the shared carry GO; D = DECIDE_WINDOW_S = 10 SIM s at EVERY stop and in EVERY
condition, rule-only runs included, coordinator decision v4-1' 2026-10-05: LLM round trip estimated 7.1-9.9 s, and
10 s keeps the window apart from the 8 s HIGH_CHECKPOINT_REOBSERVE_TIMEOUT, which only starts after the lower
barrier that follows the decision; so the four conditions pay the same stop time) a requesting robot publishes the plain state 'uncertain' instead of 'carry'. The own sigma rule decides at
window entry (``rule_decided_s``); the pair executes at t_end + D (``executed_s``), whoever decided. Decision = own bit
OR partner bit. A robot that decided to re-fix keeps publishing 'uncertain' for C = CHECKPOINT_REOBSERVE_S more
(echo) and must see the partner's 'uncertain' by t_end + D + C; otherwise it aborts (REFIX_DISAGREEMENT) with the
beam still at HIGH, and the partner stops on the status channel. No new status value, no pose or sigma on the wire.
The prediction includes the rest of the current stop (D + the HIGH stop minimum + rendezvous) before the first leg,
because the own estimate keeps diffusing at rest in the loaded profile during the 10 s (``predict(lead_hold_s=)``).
Clock: every *_s field of these hooks (latch_until_s, decide_at_s, ...) is the controller's own SIM clock (the
``now`` of its tick), not the harness clock.

Where. Every intermediate route stop, the stop inside the doorway included (coordinator decision 2(a), 2026-10-04:
the user's rule is to set the load down and look when unsure; the earlier doorway exclusion was a coordinator rule,
dropped). The guards are unchanged there (no-entry rule, floors, hover check + blind close). The final stop is the
delivery set-down, not a re-fix.

Look move (coordinator decision 3, Nav2 BackUp-style recovery, bounded). Where the own v3 ranking finds no safe
informative view after a set-down, ``look_move_plan`` derives the back-off (reverse of the last leg, clearance-derived
distance, at most one per stop). In the offline model it does not rescue r1 at stops 5-6 and needs 0.65 m at stop 4
for little gain, so the controller does NOT execute it yet (coordinator: report rather than tune); that stop keeps
the v3 outcome ALIGN_RELOOK_NO_SAFE_VIEW and ``LOOK_MOVE_FAIL`` is reserved.

How (the existing v3 checkpoint path; no new motion primitive): lower@k barrier -> lower transit to the floor pose
(``pose.lower_path``) -> open@k barrier -> open + hover -> ``cp_open`` (segment k+1, the v3 align entry re-look) ->
align -> pregrasp re-look -> hover check + blind close -> lift@k+1 -> raise to HIGH -> carry@k+1. Segment keys are
those of a plain HIGH stop, so MAX_SEGMENTS is not touched. At most one re-fix per eligible intermediate stop.

Re-fix look directions (coordinator decision v4-4, 2026-10-05): while the re-fix looks and re-grasps, the align
re-look candidates are the dock look's eight directions (``zone_pair_highpose_relook.DOCK_LOOK_PANS``, the closing
1500 is the return), in dock order, filtered by the UNCHANGED sweep guard (plan clear + transition clear) and a
positive expected observability, up to all seven distinct directions per look (stop at the first fix-quality view,
the unchanged v3 rule), within ``REFIX_MAX_LOOK_S`` = the measured dock look bound (``LOOK_S`` 9 s; eight pans
measured 8.4 s). Why: offline (``sigma_refix_model``) r1 at stops 4-6 had all seven pans guard-clear and an expected
observability of 96-192, but its chassis lies 11 mm inside the sigma-aware margin of wall_divider_1 (std_xy 70.7 mm),
so the ``recovery_v6`` ranking weight max(0, gap/0.2) was 0 for every pan and the ranked list was empty
(ALIGN_RELOOK_NO_SAFE_VIEW). That weight is a ranking preference, not a guard; the arm sweep clearance there is
+0.146 m. The pregrasp re-look keeps its own three directions, now in dock order. The shared align code runs
unchanged (``zone_final_pair_binding.bind`` rebinds only MAX_DIRECTIONS / MAX_LOOK_S, as the dock look already does).

No-look re-grasp and keep-hold: neither. Both robots release, look and re-grasp at every decided re-fix (the v4
path; coordinator decision v6-1, 2026-10-05: the looks run in parallel, so the pair time is set by the longer look
either way, and both estimates are refreshed). v4-3 (re-grasp without a look) is refused by the frozen re-grasp gates
(``record()['no_look_regrasp']``); v5-1 (keep-hold) was built and withdrawn after the offline model showed 0-3 s saved
per stop and one more re-fix stop (+54.6 s) under the motion-proportional noise model, with no camera grip check
available at the floor pose (``record()['keep_hold']``).

Post-look refresh (decision v6-2): the fix refresh after the 10 s post-look window is ONE direction, the pan that gave
the look's fix (else the first guard-clear dock direction); worst case 885 s (note V6). An LLM ``look_again`` keeps
the full dock look.

Inputs: own PF (prediction on the own estimator only), own report, the static plan (route, passage, checkpoint
segments), the static calibration (motion profile), own schedule times and the partner's fixed-enum status. No
simulator state, no partner pose, no ground truth.
"""
from __future__ import annotations

import copy
import functools
import math

import numpy as np

from harness import zone_own_guards as guards
from harness import zone_pair_highpose_dr_checkpoint as dr_checkpoint
from harness import zone_pair_highpose_relook as dock_relook
from harness.zone_team_footprint import CHASSIS_X_M, CHASSIS_Y_M

ID = 'v98_sigma_refix_v6'
DECIDE_STATE = 'refix_decide'
REQUEST_STATUS = 'uncertain'            # existing fixed-enum value (zone_pair_status.STATES)
GATE_XY_M = guards.GATE_LOADED.high_xy_m
GATE_YAW_RAD = guards.GATE_LOADED.high_yaw_rad
MC_Z = dr_checkpoint.MC_Z               # one-sided 95 % (one derivation, decision 5)
DOOR_K = 1.96                           # 1-D two-sided 95 %, as in the DR note
DOOR_LEVER_M = math.hypot(max(abs(CHASSIS_X_M[0]), abs(CHASSIS_X_M[1])), CHASSIS_Y_M[1])
PREDICT_STEP_S = .05                    # = owncam_localizer.STEP_S
DECIDE_WINDOW_S = 10.                   # carry-stop decision window, every stop, every condition (decision v4-1')
POST_LOOK_WINDOW_S = 10.                # post-look window, every re-fix look, every condition (decision v4-1')
STOP_TAIL_S = 1.2+.5                    # the unchanged HIGH stop minimum (CHECKPOINT_REOBSERVE_S) + barrier rendezvous
STOP_HOLD_S = DECIDE_WINDOW_S+STOP_TAIL_S   # one whole intermediate stop in the prediction
# Re-fix look (decision v4-4): the dock look's eight directions; the closing 1500 is the return to the start pan.
REFIX_LOOK_PANS = tuple(dict.fromkeys(dock_relook.DOCK_LOOK_PANS))
REFIX_MAX_DIRECTIONS = len(REFIX_LOOK_PANS)
REFIX_MAX_LOOK_S = dock_relook.LOOK_S   # measured eight-pan dock look 8.4 s; v3 path: stop + .8+.6 + 6*(.4+.6) + .6+.3
REFIX_LOOK_PHASES = ('looking', 'regrasping')
# look_again caps (decision v6-2): one per stop, one per robot per case (pair at most two); over a cap: closed code
LOOK_AGAIN_PER_STOP = 1
LOOK_AGAIN_PER_CASE = 1
REFRESH_MAX_DIRECTIONS = 1              # post-look fix refresh: one direction (decision v6-2)
DISAGREE = 'REFIX_DISAGREEMENT'
PARTNER_UNSEEN = 'REFIX_PARTNER_STATUS_UNSEEN'
INFEASIBLE = 'REFIX_HORIZON_INFEASIBLE'
LOOK_MOVE_STEP_M = .05                  # candidate back-off distances (search grid, not a tolerance)
LOOK_MOVE_CLEAR_STEP_M = .01            # clearance scan resolution along the path
LOOK_MOVE_FAIL = 'REFIX_LOOK_MOVE_NO_VIEW'
EVENTS = ('refix_decision', 'refix_set_down', 'refix_released', 'refix_resumed_high')

# ---- hover@k+1 pair barrier (review delta2 P1-1; coordinator decision (A), 2026-10-05: 고정 상태 관례 추가, 조정자 승인).
# In the re-fix re-grasp each robot waits at the hover, after its own hover confirmation (HoverConfirm: 2 distinct
# passing own frames, 3 mm) and BEFORE the blind descent arms the 22.14 s blind window, until both robots are hover
# ready. Then each robot passes a FRESH hover confirmation and descends, so the close@k+1 arrival skew is the
# re-confirmation/descent difference only (the descent is the same fixed path) and fits the blind window. Before
# this, a look_again or a longer own look could exceed CLOSE_WAIT_S at close@k+1 (BARRIER_CLOSE_TIMEOUT).
# Wire: the existing fixed-enum approach_{ready,go}_{seg} states at seg = k+1 (zone_pair_status_v5 unchanged; the
# approach barrier is used only at seg 0, and its phase is 'aligning' like every other state of this stretch).
# Identical in all four communication conditions; no natural language.
HOVER_BARRIER = 'hover'
HOVER_BARRIER_WIRE = 'approach'
HOVER_TIMEOUT = 'REFIX_HOVER_BARRIER_TIMEOUT'
HOVER_ABORT = 'REFIX_HOVER_BARRIER_ABORT'
HOVER_MOVE_S = 1.                       # HoverConfirm._queue_open_descent: hover posture queue duration
HOVER_EVENTS = ('refix_hover_barrier_wait', 'refix_hover_reconfirmed', 'refix_hover_barrier_timeout')


def hover_barrier_limit_terms():
    """The partner's own limits from the open GO to its close readiness (each phase ends by its own limit, so the sum
    bounds how long the partner can keep the pair waiting while it is alive and not aborted). Conservative sum: looks
    inside the align limit are counted again in the look budget, and the descent term is kept although the partner
    is hover ready before its descent (coordinator decision: 123.94 s)."""
    from harness import zone_pair_highpose_blind_close as blind
    from harness.zone_pair_align import MAX_TOTAL_LOOK_S
    from scripts.study_owncam_pair_beam import STATE_LIMIT_S
    return {'align_state_limit_s': float(STATE_LIMIT_S['align']),
            'post_look_windows_s': POST_LOOK_WINDOW_S*(1+LOOK_AGAIN_PER_STOP),
            'look_budget_s': float(MAX_TOTAL_LOOK_S), 'hover_move_s': HOVER_MOVE_S,
            'hover_settle_s': float(blind.HOVER_SETTLE_S), 'hover_confirm_max_s': float(blind.HOVER_CONFIRM_MAX_S),
            'descent_s': float(blind.limits()['blind_max_s_terms']['descent_s']),
            'grid_slack_s': float(blind.GRID_SLACK_S)}


def hover_barrier_limit_s():
    return round(sum(hover_barrier_limit_terms().values()), 6)

# ---- LLM decision hooks (#371, coordinator 2026-10-04). Own robot only; identical in all four conditions.
# Events go to the own ``refix_hook_events`` list (and the run log). Commands are latched one-shot requests that the
# controller reads on its next tick; it never waits inside a tick. Without a latched command the rule default (the
# sigma rule above, unchanged) applies at the deadline. A command may only make the outcome more conservative.
# v4 (decision v4-2): 'wait' is not in the first cohort's vocabulary (a one-robot extra stop at HIGH); it is refused
# as UNKNOWN_CHOICE like any other word outside the closed set.
HOOK_EVENTS = ('carry_leg_started', 'carry_stop_reached', 'setdown_started', 'setdown_completed',
               'relook_result', 'regrasp_result', 'carry_resumed')
CARRY_CHOICES = ('continue', 'set_down')
POST_LOOK_CHOICES = ('regrasp', 'look_again')
# closed rejection reasons (``own_status`` reason vocabulary of the #371 layer)
NOT_AT_STOP, NOT_AFTER_LOOK, UNKNOWN_CHOICE = 'NOT_AT_STOP', 'NOT_AFTER_LOOK', 'UNKNOWN_CHOICE'
ALREADY_LATCHED, DEADLINE_PASSED, OVER_BUDGET = 'ALREADY_LATCHED', 'DEADLINE_PASSED', 'OVER_BUDGET'
LOOK_OVER_BUDGET, LOOK_AGAIN_USED = 'LOOK_OVER_BUDGET', 'LOOK_AGAIN_USED'
LOOK_AGAIN_CASE_LIMIT = 'LOOK_AGAIN_CASE_LIMIT'
REJECT_REASONS = (NOT_AT_STOP, NOT_AFTER_LOOK, UNKNOWN_CHOICE, ALREADY_LATCHED, DEADLINE_PASSED, OVER_BUDGET,
                  LOOK_OVER_BUDGET, LOOK_AGAIN_USED, LOOK_AGAIN_CASE_LIMIT)
SIGMA_BANDS = ('fix', 'budget', 'over', 'unknown')
RELOOK_LEVELS = {'ALIGN_RELOOK_NO_FIX': 'no_fix', 'ALIGN_RELOOK_NO_SAFE_VIEW': 'no_safe_view',
                 'ALIGN_RELOOK_TIMEOUT': 'timeout', 'ALIGN_RELOOK_FIX_EXPIRED': 'expired',
                 'ALIGN_RELOOK_LIMIT': 'limit', 'ALIGN_RELOOK_WHILE_CLOSED': 'closed'}


def latch_margin_s():
    """A set_down latched at t reaches the partner by t + 2 control periods: the own tick that applies it publishes
    'uncertain' at once (status on change), and the partner reads it on its own next tick (tick order within a step
    is not fixed). The partner decides at t_end + D, so the last accepted set_down is at t_end + D - 2 CONTROL_S."""
    from harness.zone_pair_status import CONTROL_S
    return 2*CONTROL_S


def sigma_band(report):
    """Closed band of the own report: 'fix' (new-fix threshold 50 mm / 3 deg), 'budget' (derived DR budget
    67.4 mm / 2.89 deg), 'over', 'unknown'. No number crosses to the LLM."""
    if report is None:
        return 'unknown'
    sxy, syaw = getattr(report, 'std_xy_m', None), getattr(report, 'std_yaw_rad', None)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (sxy, syaw)):
        return 'unknown'
    if sxy <= dr_checkpoint.FIX_XY_M and syaw <= dr_checkpoint.FIX_YAW_RAD:
        return 'fix'
    if sxy <= dr_checkpoint.BUDGET_XY_M and syaw <= dr_checkpoint.BUDGET_YAW_RAD:
        return 'budget'
    return 'over'


FIX_AGE_BUCKETS = ('none', 'lt_6s', 'lt_60s', 'ge_60s')        # 6 s = zone_pair_align.MAX_FIX_GAP_S
BUDGET_LEFT_BUCKETS = ('gt_50pct', '25_50pct', 'lt_25pct', 'none', 'unknown')


def own_belief(report, now):
    """#371 item 6: closed summary of the OWN estimate (no position, no exact threshold).
    sigma_xy_band as ``sigma_band``; sigma_yaw_band within/over the derived yaw budget; fix age bucket; share of the
    xy/yaw DR budget still left (the smaller of the two); over_budget = the DR receipt rule."""
    def num(v):
        return isinstance(v, (int, float)) and math.isfinite(v)
    sxy, syaw = getattr(report, 'std_xy_m', None), getattr(report, 'std_yaw_rad', None)
    fix_t = getattr(report, 'last_fix_t', None)
    if not (num(sxy) and num(syaw)):
        yaw_band, left, over = 'unknown', 'unknown', True
    else:
        yaw_band = 'within' if syaw <= dr_checkpoint.BUDGET_YAW_RAD else 'over'
        frac = min(1.-sxy/dr_checkpoint.BUDGET_XY_M, 1.-syaw/dr_checkpoint.BUDGET_YAW_RAD)
        left = 'gt_50pct' if frac > .5 else '25_50pct' if frac > .25 else 'lt_25pct' if frac >= 0. else 'none'
        over = not (sxy <= dr_checkpoint.BUDGET_XY_M and syaw <= dr_checkpoint.BUDGET_YAW_RAD)
    if not num(fix_t):
        age = 'none'
    else:
        a = float(now)-float(fix_t)
        age = 'lt_6s' if a < 6. else 'lt_60s' if a < 60. else 'ge_60s'
    return {'sigma_xy_band': sigma_band(report), 'sigma_yaw_band': yaw_band, 'fix_age_bucket': age,
            'dr_budget_remaining_bucket': left, 'over_budget': over}


def _receipt_estimate(report):
    """Log-only own estimate for the floor re-fix receipt (same fields as the DR receipt detail); never raises."""
    out = dict(dr_checkpoint._own_estimate(report))
    for key in ('std_xy_m', 'std_yaw_rad'):
        try:
            v = float(getattr(report, key))
            out[key] = v if math.isfinite(v) else None
        except Exception:  # noqa: BLE001 - log only
            out[key] = None
    try:
        out['report_t_est'] = float(report.t_est)
    except Exception:  # noqa: BLE001 - log only
        out['report_t_est'] = None
    return out


def decide_window_s():
    """D: the carry-stop decision window (decision v4-1'), the same at every stop and in every condition."""
    return DECIDE_WINDOW_S


def post_look_window_s():
    """The post-look window (decision v4-1'): 10 SIM s in every condition. Longer than MAX_FIX_GAP_S (6 s), so the
    regrasp after it refreshes the fix with one more own look (``_align_relook_return``)."""
    return POST_LOOK_WINDOW_S


def confirm_window_s():
    """C = CHECKPOINT_REOBSERVE_S (1.2 s): the echo after a re-fix decision (only the partner's next tick must see it)."""
    from harness.zone_pair_highpose_timing import CHECKPOINT_REOBSERVE_S
    return CHECKPOINT_REOBSERVE_S


def lead_hold_s(t_end, now):
    """The rest of the current stop before the first predicted leg: decision window left + STOP_TAIL_S."""
    return max(0., float(t_end)+DECIDE_WINDOW_S-float(now))+STOP_TAIL_S


mc_margin = dr_checkpoint.mc_margin
budget = dr_checkpoint.budget


def door_alert_limit(plan):
    passage = (plan or {}).get('passage')
    if not passage:
        return None
    half = float(passage['measured_free_width_m'])/2.
    return half-CHASSIS_Y_M[1]-guards.BASE_MARGIN_M-guards.BODY_COVERAGE_RESIDUAL_M


def eligible(plan, j):
    """Route point ``j`` (stop after leg j-1) allows a set-down re-fix: every intermediate stop (decision 2(a))."""
    return 0 < j < len(plan['route'])-1


def horizon(plan, j):
    """Legs [j, h) to the next eligible stop h (or the destination): no re-fix can happen in between."""
    last = len(plan['route'])-1
    h = j+1
    while h < last and not eligible(plan, h):
        h += 1
    return list(range(j, h))


def leg_plan(plan, k, rid, motion_loaded):
    """Leg k's own command and duration with the formulas of ``V3Controller.door_schedule`` (no align part)."""
    from harness.owncam_carry_v6e import lag_duration
    from harness.zone_final_pair_skill import motor_command
    from harness.zone_pair_executor import carry_role_sign
    from scripts.study_owncam_pair_beam import SPEED_M_S

    a, b = plan['route'][k:k+2]
    mp = motion_loaded
    tau_axis = np.asarray(mp.get('tau_axis_s', [mp['tau_s']]*3), float)
    delta = np.asarray(b, float)-np.asarray(a, float)
    distance = float(np.linalg.norm(delta))
    axis = 1 if abs(delta[1]) > 1e-6 else 0
    velocity = np.r_[carry_role_sign(rid)*delta/distance*SPEED_M_S, 0.]
    u = motor_command(mp, velocity)
    duration = lag_duration(distance, abs(float(velocity[axis])), tau_axis[axis], mp['tau_stop_s'])
    return {'leg': k, 'u': [float(v) for v in u], 'duration_s': float(duration), 'distance_m': distance,
            'axis': 'lateral' if axis else 'axial'}


# ---------------------------------------------------------------- bounded look move (coordinator decision 3)
def _command(motion, velocity):
    """The PF's own gain inverted (``motor_command``); profiles without a deadband are a plain gain."""
    from harness.zone_final_pair_skill import motor_command
    if motion.get('deadband') is None:
        return np.linalg.solve(np.asarray(motion['gain'], float), velocity)
    return motor_command(motion, velocity)


def look_move_plan(plan, j, rid, pose, servo, guard, motion, *, rank, step_m=LOOK_MOVE_STEP_M,
                   clear_step_m=LOOK_MOVE_CLEAR_STEP_M):
    """Back-off along the reverse of the last carry leg for a re-fix look (pure; own estimate + static map).

    Distance: the smallest multiple of ``step_m`` at which ``rank`` (the unchanged v3 ranking at the moved pose)
    finds a view, within d_clear = the longest prefix of the straight path on which the guard's own chassis and
    arm clearances (its sigma-aware margin) stay >= 0, and never past the previous route point (the path the pair
    just drove). A start already inside the guard margin may move only where the clearance does not get worse (the
    live guard's start relief floor). The move never goes toward the own grip point (the beam end ahead of the chassis).
    """
    from harness.owncam_carry_v6e import lag_duration
    from harness.zone_own_guards import OwnPose
    from scripts.study_owncam_pair_beam import SPEED_M_S

    a, b = (np.asarray(p, float) for p in plan['route'][j-1:j+1])
    leg = float(np.linalg.norm(b-a))
    d_world = (a-b)/leg
    fwd = np.array([math.cos(pose.yaw), math.sin(pose.yaw)])
    out = {'stop': j, 'direction_world': [round(float(v), 9) for v in d_world], 'leg_m': round(leg, 6)}
    if float(d_world @ fwd) > 1e-6:
        return {**out, 'ok': False, 'reason': 'toward_own_grip'}

    def at(d):
        return OwnPose(pose.x+d_world[0]*d, pose.y+d_world[1]*d, pose.yaw, pose.std_xy, pose.std_yaw)

    def clear(p):
        return min(guard.chassis_clearance(p)[0], guard.arm_clearance(servo, p, loaded=False)[0])

    # Floor as in the live base guard (zone_pair_highpose_start_relief): a start that is clear must stay >= 0, a start
    # already inside the margin must not get worse anywhere along the path. Nothing is widened.
    start = clear(at(0.))
    floor = min(0., start)
    d_clear, n = 0., 1
    while n*clear_step_m <= leg+1e-9 and clear(at(n*clear_step_m)) >= floor:
        d_clear, n = n*clear_step_m, n+1
    out['start_clearance_m'], out['clearance_floor_m'] = round(start, 6), round(floor, 6)
    out['d_clear_m'] = round(d_clear, 6)
    k = 1
    while k*step_m <= d_clear+1e-9:
        ranked = rank(at(k*step_m))
        if ranked:
            d = k*step_m
            c, s = math.cos(pose.yaw), math.sin(pose.yaw)
            v_base = np.array([c*d_world[0]+s*d_world[1], -s*d_world[0]+c*d_world[1]])*SPEED_M_S
            axis = int(abs(v_base[1]) > abs(v_base[0]))
            tau_axis = np.asarray(motion.get('tau_axis_s', [motion['tau_s']]*3), float)
            dur = lag_duration(d, float(np.hypot(*v_base)), tau_axis[axis], motion['tau_stop_s'])
            u, back = (_command(motion, np.r_[sgn*v_base, 0.]) for sgn in (1., -1.))
            return {**out, 'ok': True, 'distance_m': round(d, 6), 'duration_s': float(dur),
                    'out_u': [float(v) for v in u], 'back_u': [float(v) for v in back],
                    'ranked': ranked, 'pan': ranked[0]['pan']}
        k += 1
    return {**out, 'ok': False, 'reason': 'no_view_within_clearance'}


# ---------------------------------------------------------------- prediction on the live PF, restored afterwards
def _snapshot(pf):
    state = {k: copy.deepcopy(v) for k, v in vars(pf).items()
             if not callable(v) and k != 'rng'}
    return state, copy.deepcopy(pf.rng.bit_generator.state)


def _restore_into(cur, saved):
    """Copy ``saved`` into the existing object ``cur`` in place (keeps identities closures hold); False if not."""
    if isinstance(cur, np.ndarray) and isinstance(saved, np.ndarray):
        if cur.shape != saved.shape or cur.dtype != saved.dtype:
            return False
        np.copyto(cur, saved)
        return True
    if isinstance(cur, dict) and isinstance(saved, dict):
        for k in [k for k in cur if k not in saved]:
            del cur[k]
        for k, v in saved.items():
            if not (k in cur and _restore_into(cur[k], v)):
                cur[k] = v
        return True
    if (hasattr(cur, '__dict__') and type(cur) is type(saved) and not callable(cur)
            and not isinstance(cur, (np.ndarray, np.random.Generator))):
        _restore_into(vars(cur), vars(saved))
        return True
    return False


def _restore(pf, snap):
    state, rng_state = snap
    attrs = vars(pf)
    for k in [k for k, v in attrs.items() if not callable(v) and k != 'rng' and k not in state]:
        del attrs[k]                               # attributes the prediction created
    for k, v in state.items():
        if not (k in attrs and _restore_into(attrs[k], v)):
            attrs[k] = v
    pf.rng.bit_generator.state = rng_state


def predict(pf, plan, rid, legs, motion_loaded, *, door=None, stop_hold_s=STOP_HOLD_S, align_hold_s=None,
            lead_hold_s=0.):
    """Own estimate over ``legs`` from the live PF state (no observations), restored afterwards.

    Returns the worst sigma along the horizon and the door protection level while the own chassis overlaps the
    passage. Holds (the rest of the current stop ``lead_hold_s``, align window, pause, stops) are predicted too: the
    loaded profile diffuses at rest.
    """
    from scripts.run_m2_pair import DOOR_ALIGN_S
    align_hold_s = DOOR_ALIGN_S+.5 if align_hold_s is None else align_hold_s
    snap = _snapshot(pf)
    rows, t = [], float(pf.t)
    try:
        def advance(until, leg):
            nonlocal t
            while t < until-1e-9:
                t = min(until, round(t+PREDICT_STEP_S, 9))
                pf.predict_to(t)
                est = pf.estimate()
                cov = np.asarray(est['cov'], float)
                rows.append((t, leg, est['x'], est['yaw'], est['std_xy_m'], est['std_yaw_rad'],
                             math.sqrt(max(cov[0, 0], 0.)), math.sqrt(max(cov[1, 1], 0.))))
        if legs and lead_hold_s > 0.:
            pf.command({'t': t, 'kind': 'hold'})
            advance(t+float(lead_hold_s), legs[0])
        for i, k in enumerate(legs):
            p = leg_plan(plan, k, rid, motion_loaded)
            pf.command({'t': t, 'kind': 'hold'})
            advance(t+align_hold_s, k)
            u = np.asarray(p['u'], float)
            pf.pair_plan = {'t0': t, 't1': t+p['duration_s'], 'own': u.copy(), 'partner': -u.copy()}
            pf.command({'t': t, 'kind': 'mecanum', 'forward': p['u'][0], 'left': p['u'][1], 'turn': p['u'][2],
                        'duration_s': p['duration_s']})
            advance(t+p['duration_s'], k)
            pf.command({'t': t, 'kind': 'hold'})
            if i < len(legs)-1:
                advance(t+stop_hold_s, k)
        n = int(pf.n)
    finally:
        _restore(pf, snap)
    return summarize(rows, n, door=door)


def summarize(rows, n, *, door=None):
    bxy, byaw = budget(n)
    worst = {'std_xy_m': 0., 'std_yaw_rad': 0., 'door_pl_m': None, 'door_t': None}
    for t, leg, x, yaw, sxy, syaw, sx, sy in rows:
        worst['std_xy_m'] = max(worst['std_xy_m'], sxy)
        worst['std_yaw_rad'] = max(worst['std_yaw_rad'], syaw)
        if door is not None and overlaps_door(x, yaw, sx, door['x_range_m']):
            pl = DOOR_K*math.hypot(sy, DOOR_LEVER_M*syaw)
            if worst['door_pl_m'] is None or pl > worst['door_pl_m']:
                worst['door_pl_m'], worst['door_t'] = pl, t
    reasons = []
    if not worst['std_xy_m'] <= bxy:
        reasons.append('gate_xy')
    if not worst['std_yaw_rad'] <= byaw:
        reasons.append('gate_yaw')
    if door is not None and worst['door_pl_m'] is not None and not worst['door_pl_m'] <= door['alert_limit_m']:
        reasons.append('door_pl')
    end = rows[-1] if rows else None
    return {**{k: (None if v is None else round(float(v), 6)) for k, v in worst.items()},
            'end_std_xy_m': None if end is None else round(end[4], 6),
            'end_std_yaw_rad': None if end is None else round(end[5], 6),
            'budget_xy_m': round(bxy, 6), 'budget_yaw_rad': round(byaw, 6), 'n_particles': n,
            'door_alert_limit_m': None if door is None else round(door['alert_limit_m'], 6),
            'over': bool(reasons), 'reasons': reasons, 'steps': len(rows)}


def overlaps_door(x, yaw, sx, x_range):
    c, s = math.cos(yaw), math.sin(yaw)
    xs = [x+c*cx-s*cy for cx in CHASSIS_X_M for cy in (-CHASSIS_Y_M[1], CHASSIS_Y_M[1])]
    pad = DOOR_K*sx
    return min(xs)-pad <= x_range[1] and max(xs)+pad >= x_range[0]


def door_of(plan):
    al = door_alert_limit(plan)
    return None if al is None else {'x_range_m': list(plan['passage']['x_range_m']), 'alert_limit_m': al}


def record() -> dict:
    bxy, byaw = budget(2000)
    return {'id': ID, 'decide_state': DECIDE_STATE, 'request_status': REQUEST_STATUS, 'new_status_value': False,
            'gate_xy_m': GATE_XY_M, 'gate_yaw_rad': GATE_YAW_RAD, 'mc_z': MC_Z,
            'budget_at_2000_particles': {'xy_m': round(bxy, 6), 'yaw_rad': round(byaw, 6)},
            'door': {'k': DOOR_K, 'lever_m': round(DOOR_LEVER_M, 6), 'chassis_x_m': list(CHASSIS_X_M),
                     'chassis_half_width_m': CHASSIS_Y_M[1], 'base_margin_m': guards.BASE_MARGIN_M,
                     'residual_m': guards.BODY_COVERAGE_RESIDUAL_M},
            'window': 'scheduled leg end + DECIDE_WINDOW_S (10 SIM s, every stop, every condition, rule-only '
                      'included); echo CHECKPOINT_REOBSERVE_S after the decision on a re-fix',
            'decide_window_s': DECIDE_WINDOW_S, 'confirm_window_s': confirm_window_s(),
            'post_look_window_s': POST_LOOK_WINDOW_S,
            'timer_separation': {'decision_window': '[t_end, t_end + 10 s] in refix_decide',
                                 'echo_deadline': 't_end + 10 s + 1.2 s (re-fix only)',
                                 'high_reobserve_timeout_8s': 'starts at checkpoint_started, after the lower barrier '
                                                              'that follows a continue decision: disjoint',
                                 'close_wait_20s': 'starts at wait_close; the post-look hold and the refresh look come '
                                                   'before it in each robot; the pair is aligned before the blind '
                                                   'descent by the hover@k+1 barrier (review delta2 P1-1, decision A), '
                                                   'so the close@k+1 arrival skew is the re-confirmation/descent '
                                                   'difference only'},
            'stop_tail_s': STOP_TAIL_S, 'lead_hold': 'prediction starts with the rest of the current stop '
                                                      '(t_end + D - now + STOP_TAIL_S)',
            'stop_hold_s': STOP_HOLD_S, 'dr_receipt_budget_xy_m': dr_checkpoint.BUDGET_XY_M,
            'bundle_revision_required': {
                'required': True,
                'why': ['carry-stop decision window 1.2 -> 10 SIM s at every stop (stop time, rest diffusion under '
                        'the calibrated loaded profile)', 'sigma rule prediction now includes the current stop (lead '
                        'hold) and 11.7 s per later stop', 'post-look window 10 s in every condition + one fix '
                        'refresh look before the regrasp', 're-fix look directions (dock eight, up to 7 per look, '
                        '9 s)', "'wait' and 'give_up' removed from the hook vocabulary",
                        'v6: look_again capped at 1 per stop and 1 per robot per case',
                        'v6: the post-look fix refresh looks in ONE direction (the pan of the look fix first)'],
                'note': 'a run made with v3 timing is not the v4 controller; no v3 result carries over'},
            'refix_look': {'pans': list(REFIX_LOOK_PANS), 'source': 'zone_pair_highpose_relook.DOCK_LOOK_PANS',
                           'max_directions': REFIX_MAX_DIRECTIONS, 'max_look_s': REFIX_MAX_LOOK_S,
                           'phases': list(REFIX_LOOK_PHASES),
                           'filter': 'unchanged sweep guard (plan clear + transition clear) and expected observability '
                                     '> 0; the recovery_v6 clearance ranking weight is not applied',
                           'pregrasp': 'own three directions, dock order (unchanged count)',
                           'why': 'offline: r1 stops 4-6 all pans guard-clear, observability 96-192, ranking weight 0 '
                                  '(chassis 11 mm inside the sigma margin of wall_divider_1 at std_xy 70.7 mm)'},
            'no_look_regrasp': {
                'implemented': False, 'decision': 'coordinator v4-3, replaced by v5-1, withdrawn in v6-1',
                'blocking_gates': ['align relook_reason: fix gap >= 6 s starts a re-look',
                                   '_align_fix_checks: fix gap < 6 s, sigma <= 50 mm / 3 deg',
                                   '_grasp_pose_checks: fix after the pregrasp start, sigma <= 50 mm / 3 deg',
                                   'preclose_check: sigma <= 50 mm / 3 deg',
                                   'blind track: beam std <= 50 mm / 3 deg']},
            'keep_hold': {
                'implemented': False, 'decision': 'coordinator v5-1 built, withdrawn v6-1 (2026-10-05)',
                'why_withdrawn': ['offline route_sim4: pair time saved 0-3 s per stop (the looking robot sets it)',
                                  'unreset sigma: one more re-fix stop (+54.6 s) under the motion-proportional model',
                                  'no camera grip check at the floor pose (beam outside the view; contract pins '
                                  'in-run grip-loss detection off)', 'sigma growth while holding'],
                'path': 'both robots release, look (dock eight directions) and re-grasp (v4)'},
            'hover_barrier': {
                'name': 'hover@k+1', 'wire': 'approach_{ready,go}_{k+1} (existing zone_pair_status_v5 values)',
                'decision': '고정 상태 관례 추가 (조정자 승인 2026-10-05, review delta2 P1-1 option A)',
                'where': 'after the own hover confirmation, before the blind descent (re-fix re-grasp only)',
                'limit_s': hover_barrier_limit_s(), 'limit_terms': hover_barrier_limit_terms(),
                'codes': [HOVER_TIMEOUT, HOVER_ABORT], 'events': list(HOVER_EVENTS),
                'reconfirm': 'after the GO a fresh hover confirmation (2 new passing own frames, unchanged bounded '
                             'retries) is required before the descent',
                'while_waiting': 'hover checks continue on every own frame (fresh report, window re-armed); a failing '
                                 'check withdraws the readiness and fails closed after HOVER_CONFIRM_MAX_S from the '
                                 'last passing frame'},
            'refresh_look': {'max_directions': REFRESH_MAX_DIRECTIONS,
                             'order': 'the pan that gave the look fix first, then dock order (guard-clear only)',
                             'look_again': 'full dock look (up to 7 directions)'},
            'look_again_caps': {'per_stop': LOOK_AGAIN_PER_STOP, 'per_robot_per_case': LOOK_AGAIN_PER_CASE,
                                'codes': [LOOK_AGAIN_USED, LOOK_AGAIN_CASE_LIMIT],
                                'note': 'counted per robot (own count only; no count crosses the wire)'},
            'dr_receipt_budget_yaw_rad': dr_checkpoint.BUDGET_YAW_RAD,
            'codes': [DISAGREE, PARTNER_UNSEEN, INFEASIBLE],
            'events': list(EVENTS),
            'eligibility': 'every intermediate stop, the doorway stop included (coordinator decision 2(a))',
            'receipt_request': 'own report over the DR receipt budget at any intermediate stop requests a re-fix',
            'look_move': {'rule': 'reverse of the last leg, smallest 5 cm step with a ranked view within the guard'
                                  ' clearance (start relief floor), never toward the own grip; at most one per stop',
                          'executed': False, 'reserved_code': LOOK_MOVE_FAIL,
                          'why_not_executed': 'offline model: no view for r1 at stops 5-6, 0.65 m for little gain at 4'},
            'max_refixes': 'one per intermediate stop', 'shared_sources_modified': False,
            'llm_hooks': {
                'scope': 'own robot only; identical in all four conditions; no new wire state, no number to the wire',
                'events': list(HOOK_EVENTS), 'carry_choices': list(CARRY_CHOICES),
                'post_look_choices': list(POST_LOOK_CHOICES), 'reject_reasons': list(REJECT_REASONS),
                'sigma_bands': list(SIGMA_BANDS),
                'latch_margin_s': latch_margin_s(),
                'carry_rule': 'own bit = sigma rule OR own LLM set_down; pair = own bit OR partner uncertain; '
                              'continue is rejected (OVER_BUDGET) when the sigma rule asks for a set-down',
                'wait': 'removed from the first cohort (decision v4-2); refused as UNKNOWN_CHOICE',
                'post_look': 'opened in every condition after a fix-quality look, 10 s; executed at the window end; '
                             'rule default regrasp; the hold is not look or align time; the regrasp then refreshes '
                             'the fix with one more own look (fix gap < 6 s, unchanged); give_up removed (v4); '
                             'look_again at most once per stop and once per robot per case (v6); the fix refresh '
                             'looks in one direction (v6)',
                'relook_result_levels': sorted(set(RELOOK_LEVELS.values()) | {'fix'}),
                'clock': 'controller SIM clock (the tick now), not the harness clock',
                'never_blocks_tick': True,
                'read': {'own_belief': ['sigma_xy_band', 'sigma_yaw_band', 'fix_age_bucket',
                                        'dr_budget_remaining_bucket', 'over_budget'],
                         'fix_age_buckets': list(FIX_AGE_BUCKETS), 'budget_left_buckets': list(BUDGET_LEFT_BUCKETS)},
                'stop_window_s': DECIDE_WINDOW_S, 'post_look_window_s': POST_LOOK_WINDOW_S,
                'stop_window_note': "decision v4-1': 10 SIM s at every stop in every condition; the rule default is "
                                    'recorded at the rule decision time (window entry), executed at the window end',
                'record_fields': ['condition', 'stop', 'sigma_band', 'rule_would_do', 'llm_choice', 'latency_s',
                                  'decided_by', 'decided_s', 'rule_decided_s', 'executed_s', 'outcome',
                                  'refix_from', 'commands'],
                'outside_this_module': {'grip_event': 'log only (zone_pair_highpose_grip.GripMonitorLog), user 10/3',
                                        'pose_uncertain': '#371 layer; may use sigma_band()',
                                        'eval_truth_error': 'evaluation writer only, never back to the controller'}},
            'references': ['Roy, Burgard, Fox, Thrun 1999 coastal navigation (ICRA)',
                           'Prentice & Roy 2009 belief roadmap (IJRR 28)', 'Bry & Roy 2011 RRBT (ICRA)',
                           'Reid et al. 2019 localization requirements for autonomous vehicles (SAE J. CAV)']}


@functools.lru_cache(maxsize=1)
def _refix_align():
    """The unchanged PairAlignRelook methods with only MAX_DIRECTIONS / MAX_LOOK_S rebound (decision v4-4); the
    same private rebinding the dock look uses (``zone_final_pair_binding.bind``)."""
    from harness.zone_final_pair_binding import bind
    from harness.zone_pair_align import PairAlignRelook as A
    return {'stop': bind(A._align_relook_stop, MAX_DIRECTIONS=REFIX_MAX_DIRECTIONS),
            'relook': bind(A._align_relook, MAX_DIRECTIONS=REFIX_MAX_DIRECTIONS),
            'stop_refresh': bind(A._align_relook_stop, MAX_DIRECTIONS=REFRESH_MAX_DIRECTIONS),
            'relook_refresh': bind(A._align_relook, MAX_DIRECTIONS=REFRESH_MAX_DIRECTIONS),
            'expired': bind(A.align_relook_expired, MAX_LOOK_S=REFIX_MAX_LOOK_S)}


# ---------------------------------------------------------------- controller mixin
class SigmaRefix:
    """Placed in front of ``HighController`` (``zone_pair_highpose_runtime.controller_class``).

    LLM hooks (#371): ``carry_decision`` and ``post_look_decision`` are the only entry points; both return a closed
    verdict at once and latch an accepted command for the next tick. Both windows (carry stop, post-look) open
    in every condition for 10 SIM s and execute at their end, so a rule-only run pays the same time."""

    refix_llm_attached = False                # record only since v4 (the post-look window opens in every condition)
    refix_condition = None                    # set by the LLM layer for the record only (rule / no_comm / peer_nl / ...)

    def own_belief(self, now):
        """#371 item 6 (read, own robot only)."""
        return own_belief(self.port.own.last_report, now)

    def _refix_plan(self):
        return getattr(self, 'v3_plan', None)

    def _refix_rows(self):
        return self.__dict__.setdefault('refix_log', [])

    def _refix_log(self, kind, now, **values):
        self._refix_rows().append({'event': kind, 'sim_s': round(float(now), 4), 'seg': self.seg, **values})
        self.log(self.rid, kind, now, seg=self.seg, **values)

    # ---------------------------------------------------------------- hook plumbing (own robot only)
    def _hook_emit(self, kind, now, **payload):
        assert kind in HOOK_EVENTS, kind
        row = {'event': kind, 'sim_s': round(float(now), 4), 'seg': self.seg, **payload}
        self.__dict__.setdefault('refix_hook_events', []).append(row)
        self.log(self.rid, kind, now, **{k: v for k, v in row.items() if k not in ('event', 'sim_s')})

    def _hook_verdict(self, command, choice, now, reason=None):
        row = {'command': command, 'choice': choice, 'sim_s': round(float(now), 4), 'seg': self.seg,
               'accepted': reason is None, 'own_status': reason or 'LATCHED'}
        self.__dict__.setdefault('refix_hook_commands', []).append(row)
        self.log(self.rid, 'refix_hook_command', now, **{k: v for k, v in row.items() if k != 'sim_s'})
        return dict(row)

    def carry_decision(self, choice, now):
        """LLM command at a carry stop. Rejections (closed): NOT_AT_STOP, UNKNOWN_CHOICE (anything outside
        continue / set_down, 'wait' included since v4), ALREADY_LATCHED, OVER_BUDGET (continue while the own sigma rule
        asks for a set-down), DEADLINE_PASSED (once the pair has decided, or set_down after the latch cutoff)."""
        d = self.__dict__.get('refix_decision')
        if self.state != DECIDE_STATE or d is None:
            return self._hook_verdict('carry_decision', choice, now, NOT_AT_STOP)
        if choice not in CARRY_CHOICES:
            return self._hook_verdict('carry_decision', choice, now, UNKNOWN_CHOICE)
        h = d['hook']
        if h['pending'] is not None or h['final'] is not None:
            return self._hook_verdict('carry_decision', choice, now, ALREADY_LATCHED)
        if choice == 'continue' and d['own']['request']:
            return self._hook_verdict('carry_decision', choice, now, OVER_BUDGET)
        if d['decided'] or (choice == 'set_down' and now > h['cutoff']+1e-8):
            return self._hook_verdict('carry_decision', choice, now, DEADLINE_PASSED)
        h['pending'] = {'choice': choice, 'submitted_s': round(float(now), 4)}
        return self._hook_verdict('carry_decision', choice, now)

    def post_look_decision(self, choice, now):
        """LLM command after the own look that follows a re-fix set-down. Rejections (closed): NOT_AFTER_LOOK,
        UNKNOWN_CHOICE, ALREADY_LATCHED, LOOK_OVER_BUDGET (regrasp while the own sigma is over the derived DR budget),
        LOOK_AGAIN_USED (one extra look per stop), LOOK_AGAIN_CASE_LIMIT (one per robot per case, decision v6-2; v5-3 allowed two)."""
        w = self._post_look_window()
        if w is None or w.get('resolved'):
            return self._hook_verdict('post_look_decision', choice, now, NOT_AFTER_LOOK)
        if choice not in POST_LOOK_CHOICES:
            return self._hook_verdict('post_look_decision', choice, now, UNKNOWN_CHOICE)
        if w['pending'] is not None:
            return self._hook_verdict('post_look_decision', choice, now, ALREADY_LATCHED)
        if choice == 'regrasp' and sigma_band(self.port.own.last_report) not in ('fix', 'budget'):
            return self._hook_verdict('post_look_decision', choice, now, LOOK_OVER_BUDGET)
        if choice == 'look_again' and self.refix_look['look_again_used'] >= LOOK_AGAIN_PER_STOP:
            return self._hook_verdict('post_look_decision', choice, now, LOOK_AGAIN_USED)
        if choice == 'look_again' and getattr(self, 'refix_look_again_total', 0) >= LOOK_AGAIN_PER_CASE:
            return self._hook_verdict('post_look_decision', choice, now, LOOK_AGAIN_CASE_LIMIT)
        w['pending'] = {'choice': choice, 'submitted_s': round(float(now), 4)}
        return self._hook_verdict('post_look_decision', choice, now)

    def _own_bit(self, d):
        return bool(d['own']['request'] or d['hook']['set_down'])

    def _hook_apply_carry(self, d, now):
        h = d['hook']
        p, h['pending'] = h['pending'], None
        if p is None:
            return
        h['final'] = p['choice']
        h['set_down'] = h['set_down'] or p['choice'] == 'set_down'
        h['applied'].append({**p, 'applied_s': round(float(now), 4)})

    def _hook_finish_stop(self, d, now, outcome):
        h = d['hook']
        if h.get('record') is not None:
            return
        rule = 'set_down' if d['own']['request'] else 'continue'
        first = h['applied'][0]['applied_s'] if h['applied'] else None
        # Decision v4-1': without an LLM command the rule decided at window entry (when the own sigma rule ran); the
        # pair still executes at the window end (``executed_s``), the same time in every condition.
        h['record'] = {'condition': self.refix_condition, 'stop': d['stop'], 'sigma_band': h.get('band'),
                       'rule_would_do': rule, 'llm_choice': h['final'],
                       'latency_s': None if first is None else round(first-h['entered_s'], 4),
                       'decided_by': 'llm' if h['final'] is not None else 'rule_default',
                       'rule_decided_s': h['entered_s'],
                       'decided_s': first if first is not None else h['entered_s'],
                       'executed_s': d.get('decided_at'), 'outcome': outcome,
                       'refix_from': [k for k, v in (('own_rule', d['own']['request']),
                                                     ('own_llm', h['set_down'] and not d['own']['request']),
                                                     ('partner', d['partner_request'])) if v],
                       'commands': list(h['applied']), 'sim_s': round(float(now), 4)}
        self.__dict__.setdefault('refix_hook_decisions', []).append(h['record'])
        self.log(self.rid, 'refix_hook_decision', now, seg=self.seg, **h['record'])

    def _post_look_window(self):
        look = self.__dict__.get('refix_look')
        return None if look is None else look.get('window')

    def _post_look_held(self, now):
        w = self._post_look_window()
        return max(0., now-w['opened_s']) if w is not None and not w.get('resolved') else 0.

    def align_relook_expired(self, now):
        # The post-look window is a hold on top of the look; it does not spend the look's own time budget.
        held = self._post_look_held(now)
        if self._refix_dock_look():
            return _refix_align()['expired'](self, now-held)
        parent = getattr(super(), 'align_relook_expired', None)
        return False if parent is None else parent(now-held)

    # ---------------------------------------------------------------- re-fix look directions (decision v4-4)
    def _refix_dock_look(self):
        """During the re-fix look and re-grasp, on the real align re-look (PairAlignRelook in the class)."""
        if self.__dict__.get('refix_phase') not in REFIX_LOOK_PHASES:
            return False
        from harness.zone_pair_align import PairAlignRelook
        return isinstance(self, PairAlignRelook)

    def align_look_choices(self):
        """Re-fix phases: the dock look's directions in dock order, filtered by the unchanged sweep guard and a positive
        expected observability (``ranked_look_pans`` with ``recovery_v6=False``: no clearance ranking weight). The
        v98 execution hands the controller its command guard's ``sweep_guard`` (``refix_sweep_guard``); without it
        (unit-test classes) the parent's ranked list is only re-ordered."""
        if not self._refix_dock_look():
            return super().align_look_choices()
        sweep = getattr(self, 'refix_sweep_guard', None)
        if sweep is None:
            ranked = super().align_look_choices()
        else:
            from harness.zone_pair_align import ranked_look_pans
            own = self.port.own
            ranked = ranked_look_pans(own.map, own.last_report, own.servo, sweep(), own.pose, recovery_v6=False,
                                      excluded=getattr(self, 'relook_excluded', ()))
        by_pan = {row['pan']: row for row in ranked}
        order = list(REFIX_LOOK_PANS)
        fix_pan = (self.__dict__.get('refix_look') or {}).get('fix_pan')
        if self.__dict__.get('refix_refresh_look') and fix_pan in by_pan:
            order = [fix_pan]+[p for p in order if p != fix_pan]           # refresh: the pan that gave the fix first
        kind = 'refix_refresh' if self.__dict__.get('refix_refresh_look') else 'refix_dock_look'
        return [{**by_pan[p], 'order': kind} for p in order if p in by_pan]

    def _align_relook_stop(self, now, arm_idle):
        if self._refix_dock_look():
            key = 'stop_refresh' if self.__dict__.get('refix_refresh_look') else 'stop'
            return _refix_align()[key](self, now, arm_idle)
        return super()._align_relook_stop(now, arm_idle)

    def _align_relook(self, now, arm_idle):
        if self._refix_dock_look():
            key = 'relook_refresh' if self.__dict__.get('refix_refresh_look') else 'relook'
            return _refix_align()[key](self, now, arm_idle)
        return super()._align_relook(now, arm_idle)

    def fail(self, reason, now):
        out = super().fail(reason, now)
        self._hook_transition(now)              # a failed controller is not ticked again
        return out

    def _hook_transition(self, now):
        # Compared with the last state this mixin saw (not the state at this tick's start): a tick that a class in
        # front of this mixin handles without super() (posture_defer.DeferRelook) cannot hide a transition.
        prev = self.__dict__.get('refix_hook_last_state')
        self.refix_hook_last_state = self.state
        if prev is None or self.state == prev:
            return
        phase = self.__dict__.get('refix_phase')
        if self.state == 'carry':
            sched = getattr(self, 'schedule', None)
            self._hook_emit('carry_leg_started', now, n_segs=len(self.segments),
                            planned_leg_s=None if not sched else round(float(sched[-1][1])-float(now), 4))
        elif self.state == 'wait_lift' and phase in ('looking', 'regrasping'):
            look = self.__dict__.get('refix_look') or {}
            self._hook_emit('regrasp_result', now, ok=True, post_look_offered=bool(look.get('offered')))
            self.refix_phase = 'lifting'
        elif self.state == 'failed' and phase in ('looking', 'regrasping'):
            if phase == 'looking' and self.failure in RELOOK_LEVELS:
                self._hook_emit('relook_result', now, level=RELOOK_LEVELS[self.failure],
                                sigma_band=sigma_band(self.port.own.last_report))
            else:
                self._hook_emit('regrasp_result', now, ok=False, code=self.failure)

    # ---------------------------------------------------------------- sigma rule (unchanged)
    def _refix_sigma(self):
        r = self.port.own.last_report
        if r is None:
            return None
        out = {'std_xy_m': getattr(r, 'std_xy_m', None), 'std_yaw_rad': getattr(r, 'std_yaw_rad', None),
               'last_fix_t': getattr(r, 'last_fix_t', None), 't_est': getattr(r, 't_est', None)}
        return {k: (round(float(v), 6) if isinstance(v, (int, float)) and math.isfinite(v) else v)
                for k, v in out.items()}

    def _refix_predict(self, legs, now, lead_hold_s=0.):
        hook = getattr(self, 'refix_predictor', None)          # unit tests only
        plan = self._refix_plan()
        if hook is not None:
            return hook(self, legs, now, lead_hold_s=lead_hold_s)
        pf = self.port.own.pose.provider.loc._pf
        return predict(pf, plan, self.rid, legs, self.v3_params['motion_loaded'], door=door_of(plan),
                       lead_hold_s=lead_hold_s)

    def _own_request(self, j, now, t_end=None):
        plan = self._refix_plan()
        legs = horizon(plan, j)
        # v4: the rest of this stop (10 s window + HIGH stop minimum + rendezvous) is predicted before the first leg,
        # so a report that would cross the budget during the window requests the re-fix now (decided at entry).
        lead = 0. if t_end is None else lead_hold_s(t_end, now)
        pred = self._refix_predict(legs, now, lead)
        named = [name for name, seg in (plan.get('checkpoint_segments') or {}).items() if seg == j]
        # Every HIGH stop runs the DR receipt (runtime ``_wait_carry``): an own report already over its budget here
        # requests the re-fix now instead of an abort after the barrier. Decided once, at window entry.
        r = self.port.own.last_report
        sxy, syaw = (float(getattr(r, 'std_xy_m', math.inf)), float(getattr(r, 'std_yaw_rad', math.inf)))
        receipt_over = not (math.isfinite(sxy) and math.isfinite(syaw)
                            and sxy <= dr_checkpoint.BUDGET_XY_M and syaw <= dr_checkpoint.BUDGET_YAW_RAD)
        return {'horizon_legs': legs, 'prediction': pred, 'named_checkpoints': named, 'lead_hold_s': round(lead, 6),
                'dr_receipt_over': receipt_over, 'request': bool(pred['over'] or receipt_over)}

    def tick(self, now):
        self._hook_transition(now)
        if self.state != DECIDE_STATE:
            out = super().tick(now)
            self._hook_transition(now)
            return out
        d = self.refix_decision
        self._hook_apply_carry(d, now)          # a latched command acts before this tick's status
        echo = d['decided'] and d['refix']
        self.status[1].tick(REQUEST_STATUS if (self._own_bit(d) or echo) else 'carry', now)
        if any(v['state'] == 'abort' for v in self.status[0].partner_view(self.rid, now).values()):
            self.port.hold(now)
            self._hook_finish_stop(d, now, 'PARTNER_ABORT')
            return self.fail('PARTNER_ABORT', now)
        self.port.hold(now)
        out = self._refix_decide(now)
        self._hook_transition(now)
        return out

    def _refix_decide(self, now):
        d, D, C = self.refix_decision, decide_window_s(), confirm_window_s()
        for v in self.status[0].partner_view(self.rid, now).values():
            if v['alive'] and v['state'] in ('carry', REQUEST_STATUS):
                d['partner_seen'] = True
            if v['alive'] and v['state'] == REQUEST_STATUS:
                d['partner_request'] = True
        if not d['decided']:
            if now < d['t_end']+D-1e-8:
                return
            if not d['partner_seen']:
                self._hook_finish_stop(d, now, PARTNER_UNSEEN)
                self._refix_log('refix_decision', now, **self._refix_public(d), failure=PARTNER_UNSEEN)
                return self.fail(PARTNER_UNSEEN, now)
            d['decided'], d['refix'] = True, bool(self._own_bit(d) or d['partner_request'])
            d['decided_at'] = round(float(now), 4)
            self._refix_log('refix_decision', now, **self._refix_public(d))
            if not d['refix']:
                self._hook_finish_stop(d, now, 'continue')
                return self.set('wait_lower', now)
            return
        if not d['partner_request']:
            # The echo only has to reach the partner's next tick: C after the decision, not another D.
            if now < d['t_end']+D+C-1e-8:
                return
            self._hook_finish_stop(d, now, DISAGREE)
            self._refix_log('refix_decision', now, **self._refix_public(d), failure=DISAGREE)
            return self.fail(DISAGREE, now)
        self._hook_finish_stop(d, now, 'set_down')
        self.refix_active = True
        self.refix_count = getattr(self, 'refix_count', 0)+1
        return self.set('wait_lower', now)

    def _refix_public(self, d):
        h = d['hook']
        return {'stop': d['stop'], 't_end': d['t_end'], 'own': d['own'], 'partner_request': d['partner_request'],
                'partner_seen': d['partner_seen'], 'decided': d['decided'], 'refix': d['refix'],
                'sigma': d['sigma'], 'rule_would_do': 'set_down' if d['own']['request'] else 'continue',
                'decided_by': 'llm' if h['final'] is not None else 'rule_default',
                'llm': {'choice': h['final'], 'set_down': h['set_down'], 'cutoff_s': h['cutoff']},
                'rule_decided_s': h['entered_s'], 'decide_window_s': decide_window_s(),
                'decision_basis': 'own PF prediction + own DR receipt + own LLM set_down (OR) + fixed-enum partner status'}

    def _wait_lower(self, now, arm_idle):
        plan = self._refix_plan()
        j = self.seg+1
        intermediate = j < len(self.segments)
        decided = getattr(self, 'refix_decided_seg', None) == self.seg
        if intermediate and plan is not None and not decided:
            self.refix_decided_seg = self.seg
            if eligible(plan, j):
                t_end = float(self.schedule[-1][1]) if getattr(self, 'schedule', None) else float(now)
                own = self._own_request(j, now, t_end)
                decide_at = round(t_end+decide_window_s(), 6)
                cutoff = round(t_end+decide_window_s()-latch_margin_s(), 6)
                self.refix_decision = {'stop': j, 't_end': round(t_end, 6), 'own': own,
                                       'partner_request': False, 'partner_seen': False, 'decided': False,
                                       'refix': False, 'sigma': self._refix_sigma(),
                                       'hook': {'pending': None, 'final': None, 'set_down': False,
                                                'cutoff': cutoff, 'decide_at': decide_at,
                                                'applied': [], 'record': None,
                                                'entered_s': round(float(now), 4),
                                                'band': sigma_band(self.port.own.last_report)}}
                self._hook_emit('carry_stop_reached', now, stop=j, high=bool(getattr(self, 'high_ready', False)),
                                over_budget=own['request'], sigma_band=sigma_band(self.port.own.last_report),
                                receipt='over' if own['dr_receipt_over'] else 'within',
                                rule_default='set_down' if own['request'] else 'continue',
                                options=[c for c in CARRY_CHOICES if not (c == 'continue' and own['request'])],
                                latch_until_s=cutoff, decide_at_s=decide_at)
                self.port.hold(now)
                return self._enter_decide(now)
        if getattr(self, 'refix_active', False) and self.state == 'wait_lower' and not getattr(self, 'refix_lowering', False):
            self.refix_lowering = True
            self.refix_phase = 'setting_down'
            self._refix_log('refix_set_down', now, stop=j, sigma_before=self._refix_sigma())
            self._hook_emit('setdown_started', now, stop=j)
        return super()._wait_lower(now, arm_idle)

    def _enter_decide(self, now):
        self.set(DECIDE_STATE, now)
        return self._refix_decide(now)

    def hover_barrier_gate(self, now, obs):
        """Called by HoverConfirm with a passing hover confirmation; True = descend now (see HOVER_BARRIER above)."""
        if not self.__dict__.get('refix_resume'):
            return True                                     # not a re-fix re-grasp: the unchanged path
        h = self.__dict__.get('refix_hover')
        if h is None or h['seg'] != self.seg:
            h = self.refix_hover = {'seg': self.seg, 'started_s': float(now), 'go_s': None, 'last_frame': None,
                                    'limit_s': hover_barrier_limit_s(), 'reports': 0}
            self.log(self.rid, 'refix_hover_barrier_wait', now, seg=self.seg, limit_s=h['limit_s'],
                     wire=f'{HOVER_BARRIER_WIRE}@{self.seg}')
        if h['go_s'] is not None:
            h['descend_s'] = round(float(now), 4)
            self.log(self.rid, 'refix_hover_reconfirmed', now, seg=self.seg, go_s=h['go_s'],
                     after_go_s=round(float(now)-h['go_s'], 4), frame_id=obs.get('frame_id'))
            return True
        self.blind_hover_started = now      # bounded hover retries count from the last passing frame while waiting
        waited = float(now)-h['started_s']
        if waited > h['limit_s']+1e-9:
            self.log(self.rid, 'refix_hover_barrier_timeout', now, seg=self.seg, waited_s=round(waited, 4),
                     limit_s=h['limit_s'])
            self.fail(HOVER_TIMEOUT, now)
            return False
        if obs.get('frame_id') != h['last_frame']:
            h['last_frame'] = obs.get('frame_id')
            h['reports'] += 1
            self.report(HOVER_BARRIER_WIRE, obs, now, ready=True, reason='own hover confirmation (re-fix hover@k+1)')
        decision = self.sync_for(HOVER_BARRIER_WIRE).authorize(now)
        if decision['phase'] == 'ABORT':
            self.fail(HOVER_ABORT, now)
            return False
        if decision['phase'] == 'GO':
            h['go_s'], h['waited_s'] = round(float(now), 4), round(waited, 4)
            self.log(self.rid, 'barrier_go', now, barrier=HOVER_BARRIER, wire=f'{HOVER_BARRIER_WIRE}@{self.seg}',
                     waited_s=h['waited_s'])
            # A fresh confirmation after the GO: the count restarts, this frame does not count, unchanged retries.
            self.blind_hover_streak, self.blind_hover_last_frame = 0, obs.get('frame_id')
            self.blind_hover_started = now
        return False

    def _cp_open(self, now, arm_idle):
        if arm_idle and getattr(self, 'refix_active', False):
            self.refix_active = self.refix_lowering = False
            self.refix_resume = True
            self._refix_log('refix_released', now, sigma=self._refix_sigma())
            self._hook_emit('setdown_completed', now)
            self.refix_phase = 'looking'
            self.refix_refresh_look = False
            self.refix_look = {'stop': self.seg+1, 'window': None, 'look_again_used': 0, 'offered': False,
                               'decisions': []}
        return super()._cp_open(now, arm_idle)

    def _align_relook_return(self, now, arm_idle):
        # Post-look decision point (v4, decision of 2026-10-05): after the own look that follows a re-fix set-down, a
        # window of POST_LOOK_WINDOW_S opens in EVERY condition (rule-only included); whatever was decided, the pair
        # executes at the window end. The unchanged align return check needs a fix younger than MAX_FIX_GAP_S (6 s),
        # which a 10 s hold always voids, so a regrasp after the window refreshes the fix with one more own look
        # (same dock directions) instead of failing ALIGN_RELOOK_FIX_EXPIRED; no gate is widened.
        look = self.__dict__.get('refix_look')
        if look is None or self.__dict__.get('refix_phase') != 'looking' or not arm_idle:
            if arm_idle:
                self.refix_refresh_look = False          # the one-direction refresh ends with its return
            return super()._align_relook_return(now, arm_idle)
        w = look['window']
        if w is None:
            if not all(self._align_fix_checks(now).values()):
                return super()._align_relook_return(now, arm_idle)      # unchanged failure path
            band = sigma_band(self.port.own.last_report)
            look['fix_pan'] = getattr(self, 'active_relook_pan', None)      # the refresh looks here first
            self._hook_emit('relook_result', now, level='fix', sigma_band=band,
                            window_until_s=round(float(now)+post_look_window_s(), 6))
            look['offered'] = True
            w = look['window'] = {'opened_s': round(float(now), 4), 'rule_default': 'regrasp', 'pending': None,
                                  'deadline_s': round(float(now)+post_look_window_s(), 6)}
        if now < w['deadline_s']-1e-8:
            return                                                       # hold; the relook tick holds the base
        if w['pending'] is not None:
            choice, decided_by, decided_s = w['pending']['choice'], 'llm', w['pending']['submitted_s']
        else:
            choice, decided_by, decided_s = w['rule_default'], 'rule_default', w['opened_s']
        held = now-w['opened_s']
        w.update(resolved=True, choice=choice, decided_by=decided_by, held_s=round(held, 4))
        # The hold is neither look time nor align time (both keep their unchanged limits for the real work).
        if hasattr(self, 'align_look_started_at'):
            self.align_look_started_at += held
        if getattr(self, 'align_started_at', None) is not None:
            self.align_started_at += held
        fresh = all(self._align_fix_checks(now).values())
        rec = {'stop': look['stop'], 'rule_would_do': w['rule_default'], 'choice': choice, 'decided_by': decided_by,
               'decided_s': decided_s, 'executed_s': round(float(now), 4), 'held_s': round(held, 4),
               'fix_still_fresh': fresh, 'sim_s': round(float(now), 4)}
        look['decisions'].append(rec)
        self.log(self.rid, 'refix_hook_post_look', now, seg=self.seg, **rec)
        if choice == 'look_again':
            look['look_again_used'], look['window'] = look['look_again_used']+1, None
            self.refix_look_again_total = getattr(self, 'refix_look_again_total', 0)+1
            return self._refix_relook_after_window(now, 'refix_look_again')
        self.refix_phase = 'regrasping'
        if fresh:
            return super()._align_relook_return(now, arm_idle)
        return self._refix_relook_after_window(now, 'refix_post_look_refresh')

    def _refix_relook_after_window(self, now, reason):
        # the look that just ended counts as look time, as the unchanged return would have counted it
        self.align_look_total_s = getattr(self, 'align_look_total_s', 0.)+now-self.align_look_started_at
        self.refix_refresh_look = reason == 'refix_post_look_refresh'      # decision v6-2: one direction
        return self._begin_align_relook(now, reason)

    def _lift(self, now, arm_idle):
        out = super()._lift(now, arm_idle)
        if self.state == 'wait_carry' and getattr(self, 'refix_resume', False):
            self.refix_resume = False
            plan = self._refix_plan()
            check = None
            if plan is not None and self.seg < len(self.segments):
                legs = horizon(plan, self.seg)
                check = {'horizon_legs': legs, 'prediction': self._refix_predict(legs, now)}
            # Log only (review delta2 P2-6): the floor re-fix receipt carries the own report mean, covariance and
            # report time like the DR receipts, so the evaluation-only NEES scorer can score it. Never a decision input.
            report = self.port.own.last_report
            self._refix_log('refix_resumed_high', now, sigma_after=self._refix_sigma(), horizon_check=check,
                            **_receipt_estimate(report))
            self.refix_phase = None
            if check is not None and check['prediction']['over']:
                return self._transit_abort(INFEASIBLE, now)
            self._hook_emit('carry_resumed', now, sigma_band=sigma_band(self.port.own.last_report))
        return out
