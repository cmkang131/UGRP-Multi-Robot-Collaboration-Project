"""crate11: run an OLDER controller (PYTHONPATH=<git archive of that sha>) on a NEWER run's saved inputs.

Valid only up to the first command difference (later saved inputs came from the newer controller's
trajectory). No World/render/remote I/O. Usage: python crate11_diverge.py <run_dir_name>
"""
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from crate11_trace import zlines, zjson, RAW  # noqa: E402
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from sim.cargo_teacher_profile import CRATE
from sim.crate_grasp_teacher import CrateGraspTeacher


def run(name):
    raw = RAW / name / 'raw'
    res = zjson(raw / 'result.json'); roles = res['prefix']['assigned']
    ev = [x for x in zlines(raw / 'eval-only.jsonl.zst') if x['stage'] == 'grasp']
    labs = {r: zlines(raw / f'teacher-{r}.jsonl.zst')[:len(ev)] for r in roles}
    kw = dict(bounds=(-20, 20, -20, 20), teacher_stability=res['teacher_stability'], teacher_search=res['teacher_search'],
              approach_goal_set=res['approach_goal_set'], crate_lift_pose=res['crate_lift_pose'])
    ts = {r: CrateGraspTeacher(r, e, labs[r][0]['applied_command']['pwm'], profile=CRATE, **kw) for r, e in roles.items()}
    ms = {r: VisibleWorld(r, e, pose_source='issued', profile=CRATE) for r, e in roles.items()}
    ss = GraspStartSync(tuple(roles), res['grasp_start_delays_s']); ls = GraspStartSync(tuple(roles), {r: 0. for r in roles})
    cl = {r: IssuedClock() for r in roles}
    for i, row in enumerate(ev):
        now = row['t']
        ws = {r: ms[r].observe(row['visible_measurements'][r], now) for r in roles}
        permits = ss.tick({r: t.prepare_signal(ws[r], now) for r, t in ts.items()}, now)
        lift = ls.tick({r: t.lift_ready() for r, t in ts.items()}, now)
        diffs = {}
        for r, t in ts.items():
            skill = 'wait' if ((t.phase == 'ready' and not permits[r]) or (t.phase == 'closed' and not lift[r])) else 'grasp'
            prev = labs[r][max(0, i - 1)]['applied_command']
            e = cl[r].observe((skill, t.end, t.handoff), now, prev['pwm'])
            t.skill_started = now - e['skill_elapsed_s']
            cmd, done = t.step(ws[r], now, permit_pick=permits[r], permit_lift=lift[r])
            ex = labs[r][i]['clean_teacher_command']
            dt = max(abs(a - b) for a, b in zip(cmd['duration_s'], ex['duration_s']))
            if cmd['wheels'] != ex['wheels'] or cmd['pwm'] != ex['pwm'] or dt > 1e-10 or t.phase != labs[r][i]['teacher_phase'] or done != labs[r][i]['done']:
                diffs[r] = {'older_wheels': cmd['wheels'], 'older_duration_s': cmd['duration_s'], 'older_phase': t.phase,
                            'newer_wheels': ex['wheels'], 'newer_duration_s': ex['duration_s'], 'newer_phase': labs[r][i]['teacher_phase']}
            t.remember_applied(labs[r][i]['applied_command']); ms[r].issue(labs[r][i]['applied_command'])
        if diffs:
            return {'run': name, 'first_diff_tick': i, 'elapsed_s': round(now - ev[0]['t'], 3), 'ledger_t': now, 'robots': diffs, 'ticks_total': len(ev)}
    return {'run': name, 'first_diff_tick': None, 'ticks_total': len(ev)}


if __name__ == '__main__':
    out = [run(n) for n in sys.argv[1:]]
    print(json.dumps(out))
