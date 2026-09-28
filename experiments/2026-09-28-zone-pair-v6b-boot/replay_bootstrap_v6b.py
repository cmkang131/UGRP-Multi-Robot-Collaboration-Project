"""Offline start-bootstrap replay for the v6 dev cohort (no MuJoCo, no physics, no model calls).

Control inputs are the robot's own saved JPEGs + own issued commands + the
static map/calibration saved in each run's ``inputs/``. The GT start pose is
read from ``eval_only/trace.jsonl`` ONLY for the evaluation columns
``eval_err_*`` and never reaches the PF, the gate or the guard.

Part A: first stationary view (all six runs, r1/r2). The saved frame at
1.30025 s is the only own frame with landmarks before the arm tilted the
camera. Schedules:

- ``v5h_logged``      frozen v5h PF, commands as logged (arm command 0.25 ms before the frame).
- ``v6_logged``       v6 recovery PF, as logged (reproduces the recorded failure).
- ``v6_prior_logged`` v6b PF + dock prior, commands as logged (frame excluded: arm moving).
- ``v6_stop_noprior`` v6 recovery PF, arm commands deferred (stop-and-look only, no prior).
- ``v6b_first_view``  v6b PF + dock prior + stop-and-look (first view of the v6b schedule).

Stop-and-look is emulated by withholding the first arm/look command until
after the frame, as the v6b executor does. The pixels were rendered 0.25 ms
(one physics step) after the logged arm command; the replay assumes the arm
had not moved visibly in that step. The v6b pan-scan views (folded arm,
other pans) do not exist in any saved run; the sim probe covers them.

Part B (PF machinery only, not the v6b schedule): the two v5h runs kept the
base at the dock until 60.7 s and raised the arm/panned there. Feeding those
own frames/commands through the v6b localizer checks that resample-move on the
stationary belief combines several stationary views into an informative fix and
agree with the frozen v5h PF. The settle rule excludes frames < 0.3 s after
each own servo command, exactly as in the executor.

usage: replay_bootstrap_v6b.py <raw_root> <out.json> [extra_pf_seeds]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness import zone_own_guards as guards                       # noqa: E402
from harness.owncam_bootstrap_v6b import (belief_hypotheses, belief_pan_clear,  # noqa: E402
                                          bootstrap_fix, enable_bootstrap)
from harness.owncam_drive import LOOK_P20, WIDE_LOOK_PANS             # noqa: E402
from harness.owncam_pose_source import OwnCamPoseSource              # noqa: E402
from harness.owncam_recovery_v6 import enable_provider               # noqa: E402

RUNS = ('v6-s911-b', 'v6-s911-ab', 'v6-s912-b', 'v6-s912-ab', 'v6-s911-v5h', 'v6-s912-v5h')
V5H_RUNS = ('v6-s911-v5h', 'v6-s912-v5h')
MOTION = ('arm', 'look', 'mecanum', 'drive')
SCHEDULES = ('v5h_logged', 'v6_logged', 'v6_prior_logged', 'v6_stop_noprior', 'v6b_first_view')
DECIDE_T = 1.4          # next executor tick after the first frame (TICK_S 0.1)


def load(run, rid):
    static = json.loads((run/'inputs/static.json').read_text())
    cmds = [c for c in map(json.loads, open(run/'commands.jsonl')) if c['robot_id'] == rid]
    frames = sorted((json.loads(p.read_text()) for p in (run/'inputs'/rid).glob('*.json')),
                    key=lambda f: f['sim_time'])
    gt = json.loads(open(run/'eval_only/trace.jsonl').readline())['robots'][rid]
    return static, cmds, frames, gt


def make(static, schedule, pf_seed):
    src = OwnCamPoseSource(static['map'], static['calibration']['params'], seed=pf_seed)
    if schedule != 'v5h_logged':
        enable_provider(src)
    if schedule in ('v6_prior_logged', 'v6b_first_view', 'v6b_pf_multiview'):
        enable_bootstrap(src, 0.)
    return src


def feed(run, src, cmds, frames, until):
    events = sorted([(c['t'], 0, c) for c in cmds if c['t'] <= until]
                    + [(f['sim_time'], 1, f) for f in frames if f['sim_time'] <= until],
                    key=lambda e: (e[0], e[1]))
    fix_at = None
    for t, kind, row in events:
        if kind == 0:
            src.on_command(row)
            continue
        bgr = cv2.imread(str(run/row['image_file']))
        rep = src.on_frame(t, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        if fix_at is None and bootstrap_fix(rep):
            fix_at = {'t': round(t, 4), 'std_xy_m': round(rep.std_xy_m, 4), 'std_yaw_rad': round(rep.std_yaw_rad, 4)}
    return fix_at


def assess(src, static, gt, now, schedule):
    rep = src.report(now)
    q = dict(rep.observation_quality or {})
    out = {'initialized': rep.initialized, 'std_xy_m': None, 'std_yaw_rad': None}
    if rep.initialized:
        pose = guards.OwnPose.from_report(rep)
        servo = dict(src.servo)
        look = {**LOOK_P20, 6: servo.get(6, 1500)}
        guard = guards.SweepGuard(static['map'])
        err = math.hypot(rep.x_m - gt[0], rep.y_m - gt[1])
        yerr = abs((rep.yaw_rad - gt[2] + math.pi) % (2*math.pi) - math.pi)
        clear = guard.transition_clear(servo, look, pose, loaded=False)
        nominal = guards.OwnPose(pose.x, pose.y, pose.yaw, 0., 0.)
        unc = pose.std_xy > guards.GATE_UNLOADED.low_xy_m or pose.std_yaw > guards.GATE_UNLOADED.low_yaw_rad
        # zone_own_sweep.SweepRecheck semantics for the unchanged arm-raise guard.
        decision = ('clear' if clear else 'wait' if unc or guard.transition_clear(servo, look, nominal, loaded=False)
                    else 'blocked')
        out.update(std_xy_m=round(rep.std_xy_m, 4), std_yaw_rad=round(rep.std_yaw_rad, 4),
                   xy=[round(rep.x_m, 3), round(rep.y_m, 3)], yaw=round(rep.yaw_rad, 4),
                   gate_class=guards.UncertaintyGate().classify(True, rep.std_xy_m, rep.std_yaw_rad),
                   sigma_within_cap=bool(rep.std_xy_m <= guards.SIGMA_CAP_XY_M
                                         and rep.std_yaw_rad <= guards.SIGMA_CAP_YAW_RAD),
                   arm_raise_decision=decision,
                   belief_pan_1230_clear=belief_pan_clear(guard, servo, 1230, rep,
                                                          hypotheses=belief_hypotheses(src)),
                   belief_pans_clear=[p for p in (1230, 970, 1770, 2030) if belief_pan_clear(
                       guard, servo, p, rep, hypotheses=belief_hypotheses(src))],
                   sigma_point_pan_1230_clear=belief_pan_clear(guard, servo, 1230, rep),
                   eval_err_xy_m=round(err, 4), eval_err_yaw_rad=round(yerr, 4))
    out.update(v6_informative_fix=bool(schedule != 'v5h_logged' and bootstrap_fix(rep)),
               fix_t=rep.last_fix_t, inlier_fraction=q.get('inlier_fraction'),
               posterior_support=q.get('posterior_support'), reason=q.get('reason'))
    return out


def first_view(run, rid, schedule, pf_seed):
    static, cmds, frames, gt = load(run, rid)
    first = min(c['t'] for c in cmds if c['kind'] in MOTION)
    src = make(static, schedule, pf_seed)
    if schedule in ('v6_stop_noprior', 'v6b_first_view'):
        cmds = [c for c in cmds if c['t'] < first or c['kind'] not in MOTION]
    feed(run, src, cmds, frames, DECIDE_T)
    return assess(src, static, gt, DECIDE_T, schedule)


def multiview(run, rid, schedule, pf_seed):
    static, cmds, frames, gt = load(run, rid)
    wheel = min(c['t'] for c in cmds if c['kind'] in ('mecanum', 'drive'))
    until = wheel - 1e-6
    src = make(static, schedule, pf_seed)
    fix_at = feed(run, src, cmds, frames, until)
    return {'until_s': round(until, 3), 'first_informative_fix': fix_at,
            **assess(src, static, gt, until, schedule)}


def main():
    raw, dest = Path(sys.argv[1]), Path(sys.argv[2])
    extra = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    rows = []
    for name in RUNS:
        run = raw/name
        seed = json.loads((run/'eval_only/setup.json').read_text())['seed']
        for rid in ('r1', 'r2'):
            for schedule in SCHEDULES:
                for pf_seed in [seed, *range(10_000, 10_000 + extra)]:
                    rows.append({'part': 'A', 'run': name, 'robot': rid, 'schedule': schedule,
                                 'pf_seed': pf_seed, 'recorded_seed': pf_seed == seed,
                                 **first_view(run, rid, schedule, pf_seed)})
                    print(json.dumps(rows[-1]), flush=True)
    for name in V5H_RUNS:
        run = raw/name
        seed = json.loads((run/'eval_only/setup.json').read_text())['seed']
        for rid in ('r1', 'r2'):
            for schedule in ('v5h_logged', 'v6b_pf_multiview'):
                rows.append({'part': 'B', 'run': name, 'robot': rid, 'schedule': schedule, 'pf_seed': seed,
                             'recorded_seed': True, **multiview(run, rid, schedule, seed)})
                print(json.dumps(rows[-1]), flush=True)
    dest.write_text(json.dumps({'raw_root': str(raw), 'decide_t': DECIDE_T, 'rows': rows}, indent=1))


if __name__ == '__main__':
    main()
