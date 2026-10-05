"""Per-case SIM cap admission: an automatic time LOWER bound.

Every term is a duration the v96 controller cannot avoid, taken from the code
constants it actually runs (no invented speeds). Turns, obstacle detours,
barrier waits, extra look sweeps, relocalization retries, reapproaches and
servo tracking lag are counted as 0, so failing this bound proves the case is
impossible within the cap; passing it is NOT a completion forecast.

REVIEW_363 P1-2: dock start / carried-prefix P03 protocol, no staged
teleport; HIGH is kept through intermediate checkpoints (stop + re-observe,
no lower/open/re-raise). The cap is the coordinator's a-priori amendment
(contract.CASE_CAP_S = 900 SIM s per case since v98-cap-3, earlier 300 replacing the inherited 3x120,
decided from these bounds before any P03 data).
"""
import math

from harness import zone_pair_highpose as pose
from harness.zone_pair_highpose_contract import CASE_CAP_S
from harness import zone_final_pair_skill as skill
from scripts import run_m2_pair as m2
from sim.zone_model_conventions import spawn_layout

CAP_S = CASE_CAP_S                 # coordinator amendments, per case (120 -> 300 -> 900)
CHECKPOINT_REOBSERVE_S = 1.2       # runtime-enforced minimum HIGH stop (0.16 s pose delay + fresh fix + rendezvous)

# --- approach (harness/pair_owncam_approach.py PairApproachDriver.tick) -----
APPROACH_FORWARD_CMD_MAX = .12     # np.clip(.12*fwd, -.05, .12); lateral .08 is slower
APPROACH_SPEED_MAX_M_S = APPROACH_FORWARD_CMD_MAX*m2.study.FORWARD_GAIN   # 0.1886 m/s nominal
# --- mandatory look sweeps (harness/owncam_drive.py) ------------------------
#   the localizer starts uninitialised -> one full sweep before driving, and
#   arrival needs one 'arrival_check' sweep. Only the per-pan settle is
#   counted (pan travel / posture moves = 0).
# --- align + pregrasp relook (harness/zone_pair_align.py, zone_pair_grasp.py)
ALIGN_ENTRY_RELOOK_S = .8+.6+.6+.3  # first pan move+settle, return+settle (min 1 direction)
ALIGN_FRAMES_S = m2.study.LOOK_EVERY_S  # aligned_streak >= 2 => one look interval
PREGRASP_RELOOK_S = .8+.6+.8+.3      # one pan (move+settle) + return to align posture


def _sweep_s():
    from harness.owncam_drive import WIDE_LOOK_PANS, SETTLE_S
    return len(WIDE_LOOK_PANS)*SETTLE_S


def _grasp_s():
    from harness.zone_pair_grasp_entry_v6c import FINAL_DESCENT_SETTLE_S
    hover, path = skill.grasp_postures()
    # hover 1.0 s, 7 descent steps x .12 s, final settle, close .5 + .4 s
    return 1.+len(path)*.12+FINAL_DESCENT_SETTLE_S+.5+.4


def _segment(sum_s):
    return sum(duration+settle for _, duration, settle in sum_s)


def setup_parts(static):
    task = skill.task(static)
    plan = skill.make_plan(static, task['sheet'], task['target'])
    dock = spawn_layout(static)
    # Each carrier's best public dock row, straight line (through the beam);
    # both must arrive before the shared approach barrier -> max over robots.
    approach_m = max(min(math.dist(goal[:2], (dock['spawn_x'], y)) for y in dock['spawn_rows_y'])
                     for goal in plan['prestations'].values())
    parts = {'initial_look_sweep_s': _sweep_s(), 'approach_translation_s': approach_m/APPROACH_SPEED_MAX_M_S,
             'arrival_check_sweep_s': _sweep_s(), 'align_entry_relook_s': ALIGN_ENTRY_RELOOK_S,
             'align_frames_s': ALIGN_FRAMES_S, 'pregrasp_relook_s': PREGRASP_RELOOK_S,
             'floor_grasp_s': _grasp_s(), 'low_lift_s': 1.2+.3,
             'raise_to_high_s': _segment(pose.raise_path())}
    return plan, approach_m, parts


def _legs(plan, count, calibration):
    lengths = [math.dist(a, b) for a, b in zip(plan['route'], plan['route'][1:])][:count]
    align = count*(m2.DOOR_ALIGN_S+.5)          # door_schedule: align window + .5 s gap, every leg
    travel = sum(lengths)/m2.study.SPEED_M_S     # registered pair carry speed 0.06 m/s
    lag = 0.
    if calibration is not None:
        from harness.owncam_carry_v6e import lag_duration
        mp = calibration['params']['motion_loaded']
        axes = mp.get('tau_axis_s', [mp['tau_s']]*3)
        for i, distance in enumerate(lengths):
            a, b = plan['route'][i:i+2]
            axis = 1 if abs(b[1]-a[1]) > 1e-6 else 0
            lag += max(0., lag_duration(distance, m2.study.SPEED_M_S, axes[axis], mp['tau_stop_s'])
                       - distance/m2.study.SPEED_M_S)
    return sum(lengths), {'leg_align_s': align, 'carry_translation_s': travel, 'measured_lag_s': lag}


def bounds(static, check='p03', calibration=None):
    plan, approach_m, setup = setup_parts(static)
    legs = len(plan['route'])-1
    if check == 'p03':
        targets = [(name, segment) for name, segment in plan['checkpoint_segments'].items()]
    elif check == 'carry':
        targets = [('carry_full_route', legs)]
    else:
        raise ValueError('time bound covers student p03/carry only')
    rows = []
    for name, segment in targets:
        distance, leg_parts = _legs(plan, segment, calibration)
        parts = {**setup, **leg_parts}
        if check == 'p03':
            # Receipt = stop at HIGH + fresh re-observe at the n-th stop.
            parts['checkpoint_reobserve_s'] = segment*CHECKPOINT_REOBSERVE_S
        else:
            parts['checkpoint_reobserve_s'] = (segment-1)*CHECKPOINT_REOBSERVE_S
            parts['final_lower_s'] = _segment(pose.lower_path())
            parts['final_open_s'] = .4+.5
        parts['intermediate_lower_open_raise_s'] = 0.
        total = sum(parts.values())
        rows.append({'case': name, 'checkpoint': name if check == 'p03' else None, 'segment': segment,
            'map_id': static['map_id'], 'distance_m': distance, 'approach_straight_m': approach_m,
            'parts_s': parts, 'lower_bound_s': total, 'cap_s': CAP_S, 'feasible': total <= CAP_S,
            'scope': 'unavoidable-duration floor from controller constants; not a completion forecast; no stage teleport',
            'zero_counted': ['turns', 'detours', 'barrier waits', 'extra sweeps/relocalization',
                             'servo tracking lag', 'reapproach'],
            'calibration_lag': 'measured' if calibration is not None else 'zero (no measured D5 lag yet)'})
    return rows


def require_feasible(static, case=None, check='p03', calibration=None):
    rows = [r for r in bounds(static, check, calibration) if case is None or r['case'] == case]
    if not rows:
        raise ValueError('unknown time-bound case')
    failed = [r for r in rows if not r['feasible']]
    if failed:
        raise ValueError('TIME_LOWER_BOUND_EXCEEDS_CASE_CAP: '+', '.join(
            f"{r['case']}={r['lower_bound_s']:.3f}s" for r in failed))
    return rows
