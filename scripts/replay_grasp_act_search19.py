"""Saved search18 decision replay. No dynamics, renderer, remote host or GT control.

Each counterfactual starts from the baseline's exact state, then is discarded.
Future observations and applied commands always remain the recorded ones.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess

from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput, new_input_audit
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_visible_world import command_delta
from harness.static_keepouts import rect_distance
from scripts.replay_grasp_act_search18 import KW, clone_teacher, read
from scripts.replay_grasp_act_search17 import same
from scripts.run_grasp_act_teacher import audit_visible_input
from sim.grasp_act_search15_modes import MODES as S15
from sim.grasp_act_search17 import MODES as S17
from sim.grasp_act_search18 import MODES as S18, body_clearance
import sim.grasp_act_search18 as s18
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher

BASE = {**S15, **S17, **S18, 'search18_footprint': 'off'}


def clearance_rows(world, teacher, rows):
    """Candidate clearances use only the navigation world seen by the teacher."""
    from sim.grasp_act_goal_set import geometry
    radius, discs, rects = teacher._constraints(world)
    nav = s18.Navigation(world, teacher.rid, teacher.end, teacher.sink.pwm,
                         teacher.bounds, rectangle=True, true_start=True)
    labels = [k for k in world['robots'] if k != teacher.rid]
    labels += [k for k in world['objects'] if k != 'beam_1']
    labels += ['beam:'+str(i) for i in range(5)]
    result = []
    for row in rows:
        p = row['goal']
        heading = geometry(world, teacher.rid, teacher.end,
                           (math.radians(row['offset_deg']), row['distance_m']))[2]
        gaps = [(math.dist(p, d[:2])-d[2]-radius, key) for key, d in zip(labels, discs)]
        gaps += [(rect_distance(p, r)-radius, 'wall:'+str(i)) for i, r in enumerate(rects)]
        gap, blocker = min(gaps, default=(math.inf, None))
        body_gap = body_clearance((*p, heading), nav.discs, nav.rects, bounds=teacher.bounds)
        result.append({**row, 'disc_gap_mm': gap*1000, 'nearest': blocker,
                       'body_gap_mm': body_gap*1000})
    return result


def replay(raw, variants, margin_sweep=False):
    names = ('eval-only.jsonl', 'teacher-r1.jsonl', 'teacher-r2.jsonl', 'result.json', 'plan.json')
    files = {n: read(raw/n) for n in names}
    rows = [json.loads(x) for x in files['eval-only.jsonl'].splitlines()]
    led = {r: [json.loads(x) for x in files[f'teacher-{r}.jsonl'].splitlines()] for r in ('r1', 'r2')}
    plan, result = (json.loads(files[n]) for n in ('plan.json', 'result.json'))
    prev = {r: led[r][0]['applied_command'] for r in led}
    models = {r: VisibleWorld(r, e, odometry=S17['search17_odometry']) for r, e in plan['roles'].items()}
    teachers = {r: VisibleOnlyGraspTeacher(r, e, prev[r]['pwm'], **KW, **BASE) for r, e in plan['roles'].items()}
    clocks = {r: IssuedClock() for r in led}
    sync = GraspStartSync(plan['roles'], result['grasp_start_delays_s'])
    audit = new_input_audit(True, 'issued')
    stats = {v: Counter() for v in variants}
    margins = {str(mm): Counter() for mm in (0, 5, 10, 15, 30, 45, 65)}
    diffs = {v: [] for v in variants}
    mismatch = 0
    decisions, contexts, trace = [], [], []
    original_navigation = s18.navigation

    def capture(t, w):
        contexts.append((t.rid, deepcopy(dict(w))))
        return original_navigation(t, w)

    s18.navigation = capture
    try:
        for i, row in enumerate(rows):
            now = row['t']
            worlds = {}
            for r in led:
                audit_visible_input(audit, row['visible_measurements'][r])
                worlds[r] = AuditedTeacherInput(models[r].observe(row['visible_measurements'][r], now), audit)
            permits = sync.tick({r: t.prepare_signal(worlds[r], now) for r, t in teachers.items()}, now)
            for r, t in teachers.items():
                skill = 'wait' if t.phase == 'ready' and not permits[r] else 'grasp'
                elapsed = clocks[r].observe((skill, t.end, t.handoff), now, prev[r]['pwm'])
                t.skill_started = now-elapsed['skill_elapsed_s']
                before = clone_teacher(t)
                contexts.clear()
                old_goals = len(t.goal_set_log)
                cmd, done = t.step(worlds[r], now, permit_pick=permits[r])
                mismatch += not same(cmd, done, t.phase, led[r][i])
                sim = round(now-rows[0]['t'], 4)
                if margin_sweep and before.phase in ('approach', 'align', 'ready', 'search', 'relook'):
                    w = contexts[-1][1] if contexts else deepcopy(dict(worlds[r]))
                    nav = s18.Navigation(w, r, t.end, before.sink.pwm, t.bounds, rectangle=True)
                    pose = tuple(nav.pose)
                    gap = body_clearance(pose, nav.discs, nav.rects, bounds=t.bounds)
                    times = sorted({0., .1, *(max(0., min(.1, d)) for d in cmd['duration_s'])})
                    for t0, t1 in zip(times, times[1:]):
                        a, b = (command_delta(cmd, tt, mode=S17['search17_odometry']) for tt in (t0, t1))
                        dx, dy, da = (y-x for x, y in zip(a, b))
                        n = max(1, math.ceil(math.hypot(dx, dy)/.001), math.ceil(abs(da)/math.radians(.25)))
                        for j in range(1, n+1):
                            u = j/n; angle = da*u
                            si = math.sin(angle)/angle if abs(angle)>1e-10 else 1.
                            co = (1-math.cos(angle))/angle if abs(angle)>1e-10 else 0.
                            x, y = si*dx*u-co*dy*u, co*dx*u+si*dy*u
                            c, s = math.cos(pose[2]), math.sin(pose[2])
                            end = (pose[0]+c*x-s*y, pose[1]+s*x+c*y, pose[2]+angle)
                            gap = min(gap, body_clearance(end, nav.discs, nav.rects, bounds=t.bounds))
                        pose = end
                    for mm, counter in margins.items():
                        counter.update(checked=1, moving=int(any(cmd['wheels'])),
                                       moving_rejected=int(any(cmd['wheels']) and gap<float(mm)/1000+.002))
                if not result['physical_success'] and contexts:
                    w = contexts[-1][1]
                    if w['beam'] is not None:
                        nav = original_navigation(t, w)
                        radius, ds, rs = t._constraints(w)
                        pose, point, heading, goal = t._geometry(w)
                        trace.append({'rid': r, 'sim_s': sim, 'phase': t.phase, 'outcome': t.outcome,
                                      'pose': pose, 'goal': goal, 'heading': heading, 'path': t.path,
                                      'waypoint': nav.waypoint(pose[:2], t.path, ds, rs, radius),
                                      'world': w, 'pwm': before.sink.pwm, 'command': cmd,
                                      'peer_wait_ids': sorted(t.peer_wait_ids),
                                      'peer_wait_since': t.peer_wait_since,
                                      'reobserver': t.reobserver.active})
                if len(t.goal_set_log) > old_goals and contexts:
                    w = contexts[-1][1]
                    for item in t.goal_set_log[old_goals:]:
                        decisions.append({'rid': r, 'sim_s': sim, 'selected': item['selected'],
                                          'world': w, 'pwm': before.sink.pwm,
                                          'candidates': clearance_rows(w, t, item['candidates'])})
                for v in variants:
                    c = clone_teacher(before)
                    if v.startswith('footprint@'):
                        s18.MARGIN_M = float(v.split('@')[1])/1000
                        s18.ANALYSIS_OVERRIDE = True
                        c.search15_modes['search18_footprint'] = S18['search18_footprint']
                    else:
                        from sim.grasp_act_search19 import MODES
                        c.search15_modes.update(MODES)
                    value, finished = c.step(deepcopy(worlds[r]), now, permit_pick=permits[r])
                    changed = value != cmd or finished != done or c.phase != t.phase or c.outcome != t.outcome
                    ob, nb = t.blocked_goal_calls-before.blocked_goal_calls, c.blocked_goal_calls-before.blocked_goal_calls
                    on, nn = t.no_path_calls-before.no_path_calls, c.no_path_calls-before.no_path_calls
                    worse = (nb > ob or nn > on or (t.outcome is None and c.outcome is not None)
                             or (any(cmd['wheels']) and not any(value['wheels'])) or (done and not finished))
                    stats[v].update(ticks=1, changed=int(changed), worse_decisions=int(worse),
                                    new_no_path=max(0, nn-on), resolved_no_path=max(0, on-nn),
                                    new_blocks=max(0, nb-ob), relaxed_blocks=max(0, ob-nb),
                                    body_activated=int(c.search19_body_active),
                                    projected=sum(e['event']=='route_pulse_projected' for e in c.search19_log),
                                    peer_replanned=sum(e['event']=='peer_safe_stance_selected' for e in c.search19_log),
                                    handoff_avoided=int(t.outcome is not None and c.outcome is None))
                    if changed and len(diffs[v]) < 16:
                        diffs[v].append({'rid': r, 'sim_s': sim, 'worse': worse,
                                         'phase': [t.phase, c.phase], 'outcome': [t.outcome, c.outcome],
                                         'wheels': [cmd['wheels'], value['wheels']]})
                    s18.MARGIN_M = s18.REQUIRED_MARGIN_M
                    s18.ANALYSIS_OVERRIDE = False
                t.remember_applied(led[r][i]['applied_command'])
                if done:
                    t.done_recorded = True
            for r in led:
                prev[r] = led[r][i]['applied_command']
                models[r].issue(prev[r])
    finally:
        s18.navigation = original_navigation
        s18.MARGIN_M = s18.REQUIRED_MARGIN_M
        s18.ANALYSIS_OVERRIDE = False
    return {'seed': plan['seed'], 'raw': str(raw), 'original_success': result['physical_success'],
            'robot_ticks': len(rows)*2, 'baseline_mismatch_ticks': mismatch,
            'sha256': {k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
            'input_audit': audit, 'variants': stats, 'diffs': diffs, 'decisions': decisions,
            'body_margin_sweep': margins,
            'trace': trace,
            'teachers': {r: {'outcome': t.outcome, 'progress': t.progress_log, 'recovery': t.recovery_log,
                             'events': t.events, 'search17': t.search17_log,
                             'free_space': t.search18_space.events} for r, t in teachers.items()}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--seeds', type=int, nargs='*')
    p.add_argument('--variants', nargs='*', default=[])
    p.add_argument('--margin-sweep', action='store_true')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    results = []
    for stage in ('repro4', 'novel12'):
        for raw in sorted((a.root/f'grasp-search18-{stage}-gcp-00620d7a').glob('diagnostic*/episode-*/raw')):
            seed = json.loads(read(raw/'plan.json'))['seed']
            if a.seeds and seed not in a.seeds:
                continue
            r = replay(raw, a.variants, a.margin_sweep)
            (a.out/f'{seed}.json').write_text(json.dumps(r, indent=2)+'\n')
            results.append({k: v for k, v in r.items() if k not in ('decisions', 'teachers', 'diffs', 'trace')})
            print(json.dumps(results[-1]), flush=True)
    summary = {'scope': 'same-state one-tick decisions; recorded future; NOT physical success',
               'runs': results, 'robot_ticks': sum(r['robot_ticks'] for r in results),
               'baseline_mismatch_ticks': sum(r['baseline_mismatch_ticks'] for r in results),
               'success_N': sum(r['original_success'] for r in results),
               'body_margin_sweep_success_runs_rejecting_recorded_motion': {
                   mm: sum(r['body_margin_sweep'][mm]['moving_rejected']>0 for r in results if r['original_success'])
                   for mm in ('0', '5', '10', '15', '30', '45', '65')} if a.margin_sweep else {},
               'success_runs_with_any_changed_decision': {
                   v: sum(r['variants'][v]['changed']>0 for r in results if r['original_success']) for v in a.variants},
               'success_runs_with_worse_decisions': {v: sum(r['variants'][v]['worse_decisions'] > 0 for r in results if r['original_success']) for v in a.variants}}
    source_files = ['sim/grasp_act_search19.py', 'sim/grasp_act_teacher_v3.py',
                    'sim/grasp_act_search15_modes.py', 'scripts/replay_grasp_act_search19.py',
                    'scripts/run_grasp_act_teacher.py', 'scripts/run_grasp_act_batch.py',
                    'harness/grasp_act_admission.py']
    summary['source'] = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                         'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()),
                         'sha256': {f: hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in source_files}}
    (a.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')


if __name__ == '__main__':
    main()
