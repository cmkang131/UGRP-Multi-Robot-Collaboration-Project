"""Offline decision replay of crate14 (8007db00) runs from stored inputs with extra instrumentation.
Read-only: no simulation, render, or remote call. Does not modify repository code (monkeypatch in-process).
usage: replay13.py <run-name> [--align-trace r1]"""
import argparse, json, math, subprocess, sys
from pathlib import Path
WT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WT))
# Exact numerical memoization only; preserve mutable return ownership.
from functools import lru_cache
from copy import deepcopy
import harness.visual_arm_v3 as va
_original_ik = va.solve_grip_site_ik
@lru_cache(maxsize=65536)
def _ik(point, kwargs):
    return _original_ik(point, **dict(kwargs))
def cached_ik(point, **kwargs):
    return dict(_ik(tuple(point), tuple(sorted(kwargs.items()))))
va.solve_grip_site_ik = cached_ik
import sim.crate_cartesian_lift as cl
_original_lift = cl.plan_lift
@lru_cache(maxsize=8192)
def _lift(pwm):
    return _original_lift(dict(pwm))
def cached_lift(pwm):
    return deepcopy(_lift(tuple(sorted((int(k), int(v)) for k,v in pwm.items()))))
cl.plan_lift = cached_lift
import mujoco
def forbidden(*a, **k):
    raise AssertionError('offline replay forbids physics/render')
for name in ('mj_step', 'mj_forward', 'Renderer'):
    setattr(mujoco, name, forbidden)
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput, new_input_audit
from scripts.run_crate_teacher import make_grasp_teacher
from sim.crate_observation_v12 import tagged_world
from sim.cargo_teacher_profile import CRATE
RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')

def read(p):
    p = Path(p)
    if not p.exists(): p = Path(str(p)+'.zst')
    return subprocess.check_output(['zstd', '-dc', str(p)]) if p.suffix == '.zst' else p.read_bytes()
def js(p): return json.loads(read(p))
def rows(p): return [json.loads(l) for l in read(p).splitlines()]

def delays_fallback(name):
    # interrupted runs never wrote grasp_start_delays_s: re-derive with the runner's own RNG rule (seed -> uniform(0,1.5) for r2)
    import random
    plan = js(RAW/name/'raw'/'plan.json'); rng = random.Random(plan['seed'])
    return {rid: (0. if k == 0 else rng.uniform(0, 1.5)) for k, rid in enumerate(('r1', 'r2'))}

def replay(name, hook=None, options=None):
    raw = RAW/name/'raw'; res = js(raw/'result.json')
    ev = [r for r in rows(raw/'eval-only.jsonl') if r['stage'] == 'grasp']; roles = res.get('prefix', {}).get('assigned') or {'r1': 'teal', 'r2': 'blue'}
    lab = {r: [v for v in rows(raw/f'teacher-{r}.jsonl') if 'clean_teacher_command' in v] for r in roles}
    keys = ('teacher_stability', 'teacher_search', 'approach_goal_set', 'crate_lift_pose', 'crate_approach_recovery',
            'crate_wall_footprint', 'crate_stances', 'crate_pulse_safety', 'crate_candidate_recovery', 'crate_alignment')
    opts = {k: res.get(k, 'off') for k in keys}
    opts.update(options or {})
    ts = {r: make_grasp_teacher(r, e, lab[r][0]['applied_command']['pwm'], **opts) for r, e in roles.items()}
    ms = {r: VisibleWorld(r, e, profile=CRATE, static_walls=res['static_walls']) for r, e in roles.items()}
    audit = new_input_audit(True, 'issued')
    clocks = {r: IssuedClock() for r in roles}
    sync = GraspStartSync(tuple(roles), res.get('grasp_start_delays_s') or delays_fallback(name)); lift = GraspStartSync(tuple(roles), {r: 0. for r in roles})
    mism = []; checked = 0; total = 0
    for i, row in enumerate(ev):
        now = row['t']; holding = any(t.phase in ('lift', 'complete') for t in ts.values())
        plain = {r: ms[r].observe(row['visible_measurements'][r], now) for r in roles}
        ws = {r: AuditedTeacherInput(tagged_world(plain[r], holding=holding), audit, provenance='value_sources_v1') for r in roles}
        permits = sync.tick({r: t.prepare_signal(ws[r], now) for r, t in ts.items()}, now)
        lifts = lift.tick({r: t.lift_ready() for r, t in ts.items()}, now)
        for r, t in ts.items():
            prev = lab[r][max(0, i-1)]['applied_command']
            skill = 'wait' if ((t.phase == 'ready' and not permits[r]) or (t.phase == 'closed' and not lifts[r])) else 'grasp'
            c = clocks[r].observe((skill, t.end, t.handoff), now, prev['pwm']); t.skill_started = now-c['skill_elapsed_s']
            if hook: hook('pre', i, now, r, t, ws[r], plain[r], row)
            command, done = t.step(ws[r], now, permit_pick=permits[r], permit_lift=lifts[r])
            exp = lab[r][i]['clean_teacher_command']
            same = (all(command[k] == exp[k] for k in ('t', 'wheels', 'pwm')) and all(abs(a-b) <= 1e-10 for a, b in zip(command['duration_s'], exp['duration_s']))
                    and done == lab[r][i]['done'] and t.phase == lab[r][i]['teacher_phase'])
            total += 1; checked += int(same)
            if not same: mism.append({'tick': i, 't': now, 'robot': r})
            if hook: hook('post', i, now, r, t, ws[r], plain[r], row, command)
            t.remember_applied(lab[r][i]['applied_command']); ms[r].issue(lab[r][i]['applied_command'])

    return {'run': name, 'matched': checked, 'total': total, 'mismatch': mism[:3], 'teachers': ts, 'audit': audit}

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('run'); a = ap.parse_args()
    r = replay(a.run)
    print(a.run, 'matched', r['matched'], '/', r['total'], 'mismatch', r['mismatch'])
