"""crate11 measurement-only replay (no World, no render, no remote I/O, no controller change).

Run with PYTHONPATH=<tree extracted with `git archive <source sha>`> so the controller code is the
exact source that produced the saved run:
  PYTHONPATH=$TREE python crate11_trace.py <run_dir_name> <out_dir>
Replays saved visible inputs + saved applied commands, asserts every clean command equals the ledger
(t, wheels, pwm, duration<=1e-10, done, phase) and records per-tick decision detail.
"""
import hashlib, inspect, json, math, os, subprocess, sys
from copy import deepcopy
from pathlib import Path

from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from harness.static_keepouts import rect_distance
from scripts.zone_teacher import PeerDisc
from sim.cargo_teacher_profile import CRATE
from sim.crate_grasp_teacher import CrateGraspTeacher
from sim.grasp_act_teacher import local, wrap
from sim.grasp_act_visible_route import constraints, free, waypoint

RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
GUARD_SRC = os.environ.get('CRATE11_GUARD_SRC')  # path of 49d11b8e sim/crate_approach_recovery.py (counterfactual check on older code)


def counterfactual_guard(t, w, cmd):
    """Would the 49d11b8e pulse guard reject this (older-code) command?  Measurement only."""
    if not GUARD_SRC or hasattr(t, 'crate_approach_recovery'):
        return None
    if not (t.phase in ('approach', 'align', 'ready') and w['visibility'][t.rid]['visible_probes'] >= 5
            and w['beam'] is not None and any(cmd['wheels'])):
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location('cf_guard', GUARD_SRC); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    pose, _, _, _ = t._geometry(w)
    radius, discs, rects = constraints(w, t.rid, t.folded_ready, t.cargo_profile)
    return {'safe': bool(m.safe_pulse(cmd, pose, discs, rects, radius)), 'inside_margin': not free(pose[:2], discs, rects, radius)}



def zlines(p):
    p = Path(p)
    z = p if p.suffix == '.zst' else p.with_suffix(p.suffix + '.zst')
    return [json.loads(l) for l in (subprocess.check_output(['zstd', '-dc', str(z)]) if z.exists() else p.read_bytes()).splitlines()]


def zjson(p):
    z = Path(str(p) + '.zst')
    return json.loads(subprocess.check_output(['zstd', '-dc', str(z)]) if z.exists() else Path(p).read_bytes())


class Traced(CrateGraspTeacher):
    def _hold(self, now):
        frames = []; f = inspect.currentframe().f_back
        while f and f.f_code.co_name not in ('<module>', 'replay'):
            frames.append(f'{f.f_code.co_filename.split("/")[-1]}:{f.f_code.co_name}:{f.f_lineno}'); f = f.f_back
        self.hold_stack = frames
        return super()._hold(now)

    def _continuous(self, now, forward, left, turn):
        self.effort = {'forward': forward, 'left': left, 'turn': turn}
        return super()._continuous(now, forward, left, turn)

    def _check_navigation_pulse(self, truth, value, now):
        # Measurement only: classify what the 49d11b8e pulse guard saw, then call it unchanged.
        self.pulse = None
        if (getattr(self, 'crate_approach_recovery', 'off') != 'off' and self.phase in ('approach', 'align', 'ready')
                and truth['visibility'][self.rid]['visible_probes'] >= 5 and truth['beam'] is not None and any(value['wheels'])):
            from harness.grasp_act_visible_world import command_delta
            from sim.grasp_act_visible_route import segment_free
            pose, g, _, goal = self._geometry(truth)
            radius, discs, rects = constraints(truth, self.rid, self.folded_ready, self.cargo_profile)
            _, _, turn = command_delta(value, .1)
            inside = not free(pose[:2], discs, rects, radius)
            info = {'in_wheels': value['wheels'], 'in_dur': value['duration_s'], 'turn_rad_per_pulse': turn, 'inside_margin': inside}
            if abs(turn) > 1e-9 and inside:
                info['reason'] = 'turn_while_inside'
            else:
                times = sorted({0., .1, *(i * .005 for i in range(1, 20)), *(min(.1, d) for d in value['duration_s'])})
                x, y, yaw = pose; info['reason'] = 'ok'
                for a, b in zip(times, times[1:]):
                    step = {**value, 'duration_s': [max(0., d - a) for d in value['duration_s']]}
                    dx, dy, da = command_delta(step, b - a)
                    co, si = math.cos(yaw + da / 2), math.sin(yaw + da / 2)
                    end = (x + co * dx - si * dy, y + si * dx + co * dy)
                    if not segment_free((x, y), end, discs, rects, radius):
                        bad = [i for i, d in enumerate(discs) if not segment_free((x, y), end, [d], [], radius)]
                        badr = [i for i, r in enumerate(rects) if not segment_free((x, y), end, [], [r], radius)]
                        info.update(reason='segment', t_sub=[a, b], substep_len_m=math.dist((x, y), end), bad_discs=bad, bad_rects=badr)
                        break
                    x, y = end; yaw += da
            self.pulse = info
        return super()._check_navigation_pulse(truth, value, now)


def detail(t, w, model):
    if w['beam'] is None:
        return {'beam': None}
    pose, g, heading, goal = t._geometry(w)
    rad, ds, rs = constraints(w, t.rid, t.folded_ready, t.cargo_profile)
    names = ['peer:' + r for r in w['robots'] if r != t.rid] + ['cargo:' + k for k in w['objects'] if k != t.cargo_profile.item_id] \
        + [f'crate_disc:{d:+.2f}' for d, _ in t.cargo_profile.discs]
    obs = []
    for n, d in zip(names, ds):
        c = math.dist(pose[:2], d[:2])
        obs.append({'id': n, 'geom': list(d), 'base_clear_m': c - d[2] - rad, 'goal_clear_m': math.dist(goal, d[:2]) - d[2] - rad})
    wn = [k for k, m in model.memory.items() if m['kind'] == 'wall']
    for n, r in zip(wn, rs):
        obs.append({'id': n, 'geom': list(r), 'base_clear_m': rect_distance(pose[:2], r) - rad, 'goal_clear_m': rect_distance(goal, r) - rad})
    gx, gy = local(pose, g)
    return {'pose': pose, 'goal': [goal[0], goal[1], wrap(heading)], 'dist_goal_m': math.dist(pose[:2], goal),
            'dist_end_m': math.dist(pose[:2], g[:2]), 'local_end': [gx, gy],
            'errors': [gx - t.staging_distance, gy, wrap(heading - pose[2])], 'staging_m': t.staging_distance,
            'choice': t.approach_choice, 'radius_m': rad, 'goal_free': free(goal, ds, rs, rad),
            'obstacles': obs, 'mem': {k: round(w['t'] - v['seen_t'], 3) for k, v in model.memory.items()},
            'fresh_peers': list(w['visibility'][t.rid]['peers'])}


def run(name, outdir):
    raw = RAW / name / 'raw'
    plan = json.loads((raw / 'plan.json').read_text()); res = zjson(raw / 'result.json')
    roles = res['prefix']['assigned']
    ev = [x for x in zlines(raw / 'eval-only.jsonl.zst') if x['stage'] == 'grasp']
    labs = {r: zlines(raw / f'teacher-{r}.jsonl.zst')[:len(ev)] for r in roles}
    kw = dict(bounds=(-20, 20, -20, 20), teacher_stability=res['teacher_stability'], teacher_search=res['teacher_search'],
              approach_goal_set=res['approach_goal_set'], crate_lift_pose=res['crate_lift_pose'])
    if res.get('crate_approach_recovery', 'off') != 'off':
        kw['crate_approach_recovery'] = res['crate_approach_recovery']
    ts = {r: Traced(r, e, labs[r][0]['applied_command']['pwm'], profile=CRATE, **kw) for r, e in roles.items()}
    ms = {r: VisibleWorld(r, e, pose_source='issued', profile=CRATE) for r, e in roles.items()}
    ss = GraspStartSync(tuple(roles), res['grasp_start_delays_s']); ls = GraspStartSync(tuple(roles), {r: 0. for r in roles})
    cl = {r: IssuedClock() for r in roles}
    trace = {r: [] for r in roles}; maxd = 0.; n = 0
    for i, row in enumerate(ev):
        now = row['t']
        ws = {r: ms[r].observe(row['visible_measurements'][r], now) for r in roles}
        permits = ss.tick({r: t.prepare_signal(ws[r], now) for r, t in ts.items()}, now)
        lift = ls.tick({r: t.lift_ready() for r, t in ts.items()}, now)
        for r, t in ts.items():
            skill = 'wait' if ((t.phase == 'ready' and not permits[r]) or (t.phase == 'closed' and not lift[r])) else 'grasp'
            prev = labs[r][max(0, i - 1)]['applied_command']
            e = cl[r].observe((skill, t.end, t.handoff), now, prev['pwm'])
            t.skill_started = now - e['skill_elapsed_s']; t.hold_stack = []; t.effort = None; t.pulse = None
            cmd, done = t.step(ws[r], now, permit_pick=permits[r], permit_lift=lift[r])
            ex = labs[r][i]['clean_teacher_command']
            dt = max(abs(a - b) for a, b in zip(cmd['duration_s'], ex['duration_s'])); maxd = max(maxd, dt)
            assert all(cmd[k] == ex[k] for k in ('t', 'wheels', 'pwm')) and dt <= 1e-10, (name, i, r, 'cmd')
            assert done == labs[r][i]['done'] and t.phase == labs[r][i]['teacher_phase'], (name, i, r, 'phase')
            n += 1
            gs = t.goal_set_log[-1] if t.goal_set_log else None
            trace[r].append({'tick': i, 'elapsed': round(now - ev[0]['t'], 3), 't': now, 'phase': t.phase, 'outcome': t.outcome,
                             'wheels': cmd['wheels'], 'duration_s': cmd['duration_s'], 'crate_rec': [e['recovery'] for e in getattr(t, 'crate_recovery_log', []) if e['t'] == now], 'rec': [e['recovery'] for e in getattr(t, 'recovery_log', []) if e['t'] == now], 'pwm6': cmd['pwm']['6'], 'effort': t.effort, 'pulse': t.pulse, 'cf_guard': counterfactual_guard(t, ws[r], cmd), 'hold': t.hold_stack, 'vis': ev[i]['visible_probes'][r],
                             'wait_since': getattr(t, 'peer_wait_since', None), 'blocked_since': t.approach_blocked_since,
                             'relooks': t.align_relooks, 'ever_seen': t.ever_seen,
                             'goal_set_last_t': gs['t'] if gs else None,
                             'detail': detail(t, ws[r], ms[r]),
                             'gt': {'pose': ev[i]['robots'][r]['pose'], 'ends': ev[i]['crate']['ends'], 'crate_pose': ev[i]['crate']['pose']}})
            t.remember_applied(labs[r][i]['applied_command']); ms[r].issue(labs[r][i]['applied_command'])
    final = {r: {'outcome': t.outcome, 'phase': t.phase, 'events': t.events, 'goal_set_log': t.goal_set_log, 'recovery_log': getattr(t, 'recovery_log', []),
                 'crate_recovery_log': getattr(t, 'crate_recovery_log', []), 'progress_log': getattr(t, 'progress_log', []), 'search_log': t.search_log[-6:],
                 'relooks': t.align_relooks} for r, t in ts.items()}
    out = {'run': name, 'seed': plan['seed'], 'source_sha': res['source_sha'], 'ticks': len(ev), 'verified_commands': n,
           'max_duration_delta_s': maxd, 'result_outcomes': res['prefix']['outcomes'], 'roles': roles, 'final': final}
    Path(outdir).mkdir(parents=True, exist_ok=True)
    (Path(outdir) / f'{name}.trace.json').write_text(json.dumps({'trace': trace}))
    (Path(outdir) / f'{name}.final.json').write_text(json.dumps(out))
    print(name, 'OK', n, maxd, res['prefix']['outcomes'], flush=True)


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
