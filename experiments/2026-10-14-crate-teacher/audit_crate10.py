"""Pinned saved-input replay. No World, simulation, rendering or remote I/O.

Baseline checks every grasp command. Candidate observations remain valid only
through the first differing command; later archived images are not its result.
"""
import hashlib
import json
import math
import subprocess
from pathlib import Path
from types import ModuleType

from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput, new_input_audit
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.run_grasp_act_teacher import audit_visible_input
from sim.cargo_teacher_profile import CRATE
from sim.crate_approach_recovery import OPTION
from sim.crate_grasp_teacher import CrateGraspTeacher
from sim.crate_lift_pose import ANTIPODAL_OPTION

EXP = Path(__file__).resolve().parent
ROOT = EXP.parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')


def digest(p):
    p = actual(p)
    return hashlib.sha256(p.read_bytes()).hexdigest()


def actual(p):
    return p if p.exists() else p.with_suffix(p.suffix+'.zst')


def read(p):
    p = actual(p)
    return subprocess.check_output(['zstd', '-dc', str(p)]) if p.suffix == '.zst' else p.read_bytes()


def lines(p):
    return [json.loads(l) for l in read(p).splitlines()]


def pinned(sha):
    def source(path):
        return subprocess.check_output(['git', 'show', f'{sha}:{path}'], cwd=ROOT, text=True)
    parent = ModuleType('crate10_pinned_parent_'+sha)
    exec(compile(source('sim/grasp_act_teacher_v3.py'), sha+'/parent.py', 'exec'), parent.__dict__)
    module = ModuleType('crate10_pinned_'+sha)
    module.VisibleOnlyGraspTeacher = parent.VisibleOnlyGraspTeacher
    code = source('sim/crate_grasp_teacher.py').replace(
        'from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher', '')
    exec(compile(code, sha+'/crate.py', 'exec'), module.__dict__)
    return module.CrateGraspTeacher


def replay(raw):
    result = json.loads(read(raw/'result.json'))
    roles = result['prefix']['assigned']
    # Evaluation fields are discarded before either controller is constructed.
    inputs = [{'t': x['t'], 'measurements': x['visible_measurements']}
              for x in lines(raw/'eval-only.jsonl.zst') if x['stage'] == 'grasp']
    labels = {r: lines(raw/f'teacher-{r}.jsonl.zst')[:len(inputs)] for r in roles}
    baseline = pinned(result['source_sha'])
    kw = dict(bounds=(-20, 20, -20, 20), teacher_stability='align_relook_v1',
              teacher_search='search_reacquire_v1', approach_goal_set='approach_goal_set_v1')
    sets = [{r: baseline(r, e, labels[r][0]['applied_command']['pwm'],
                        **kw, crate_lift_pose=result['crate_lift_pose']) for r, e in roles.items()},
            {r: CrateGraspTeacher(r, e, labels[r][0]['applied_command']['pwm'],
                                 **kw, crate_lift_pose=ANTIPODAL_OPTION,
                                 crate_approach_recovery=OPTION) for r, e in roles.items()}]
    syncs = [GraspStartSync(tuple(roles), result['grasp_start_delays_s']) for _ in sets]
    lifts = [GraspStartSync(tuple(roles), {r: 0. for r in roles}) for _ in sets]
    clocks = [{r: IssuedClock() for r in roles} for _ in sets]
    models = {r: VisibleWorld(r, e, profile=CRATE) for r, e in roles.items()}
    audit = new_input_audit(True, 'issued')
    first = None; identical = 0; maximum = 0.; trace_hash = hashlib.sha256()
    fixture = None
    for i, row in enumerate(inputs):
        now = row['t']; worlds = {}
        for r in roles:
            audit_visible_input(audit, row['measurements'][r])
            worlds[r] = AuditedTeacherInput(models[r].observe(row['measurements'][r], now), audit)
        ticks = []
        for k, ts in enumerate(sets if first is None else sets[:1]):
            permits = syncs[k].tick({r: t.prepare_signal(worlds[r], now) for r, t in ts.items()}, now)
            lift = lifts[k].tick({r: t.lift_ready() for r, t in ts.items()}, now)
            tick = {}
            for r, t in ts.items():
                skill = 'wait' if ((t.phase == 'ready' and not permits[r]) or
                                   (t.phase == 'closed' and not lift[r])) else 'grasp'
                prev = labels[r][max(0, i-1)]['applied_command']
                elapsed = clocks[k][r].observe((skill, t.end, t.handoff), now, prev['pwm'])
                t.skill_started = now-elapsed['skill_elapsed_s']
                cmd, done = t.step(worlds[r], now, permit_pick=permits[r], permit_lift=lift[r])
                tick[r] = (cmd, done, t.phase, t.outcome)
                if k == 0:
                    expected = labels[r][i]
                    dt = max(abs(a-b) for a, b in zip(cmd['duration_s'], expected['clean_teacher_command']['duration_s']))
                    maximum = max(maximum, dt)
                    assert all(cmd[x] == expected['clean_teacher_command'][x] for x in ('t', 'wheels', 'pwm')) and dt <= 1e-10, (raw, i, r)
                    assert t.phase == expected['teacher_phase'] and done == expected['done'], (raw, i, r, 'phase')
                    trace_hash.update(json.dumps(cmd, sort_keys=True).encode())
                t.remember_applied(labels[r][i]['applied_command'])
            ticks.append(tick)
        if first is None:
            changed = [r for r in roles if ticks[0][r] != ticks[1][r]]
            if changed:
                first = {'tick': i, 't': now, 'elapsed_sim_s': now-inputs[0]['t'], 'robots': changed,
                         'baseline': {r: ticks[0][r] for r in changed},
                         'candidate': {r: ticks[1][r] for r in changed},
                         'decisions': {r: compact(sets[1][r].diagnostic()) for r in changed}}
                r = changed[0]
                fixture = {'seed': json.loads(read(raw/'plan.json'))['seed'], 'rid': r, 'end': roles[r],
                           'world': dict(worlds[r]), 'baseline_command': ticks[0][r][0],
                           'candidate_command': ticks[1][r][0], 'folded': sets[1][r].folded_ready,
                           'phase': sets[1][r].phase, 'path': sets[1][r].path,
                           'choice': sets[1][r].approach_choice}
            else:
                identical += len(roles)
        for r in roles:
            models[r].issue(labels[r][i]['applied_command'])
    return {'seed': json.loads(read(raw/'plan.json'))['seed'], 'source_sha': result['source_sha'],
            'saved_success': bool(result['prefix_held'] and result['release_success']),
            'baseline_commands_verified': len(inputs)*len(roles), 'baseline_command_sha256': trace_hash.hexdigest(),
            'baseline_max_duration_delta_s': maximum, 'candidate_identical_prefix_commands': identical,
            'first_divergence': first, 'input_audit': audit,
            'raw': str(raw), 'sources': [{'path': str(actual(raw/n)), 'sha256': digest(raw/n)} for n in
                     ('plan.json', 'result.json', 'eval-only.jsonl.zst', 'teacher-r1.jsonl.zst', 'teacher-r2.jsonl.zst')]}, fixture


def compact(d):
    return {k: (v[-2:] if isinstance(v, list) else v) for k, v in d.items()}


def snapshots():
    cases = []
    for seed, sha, rid, when in [(77969, '5644e3dd', 'r2', 11.3),
                                 (77978, 'bf31840f', 'r1', 11.9),
                                 (77979, 'bf31840f', 'r1', 10.7)]:
        raw = RAW/f'crate-diag-{seed}-{sha}'/'raw'
        result = json.loads(read(raw/'result.json')); end = result['prefix']['assigned'][rid]
        model = VisibleWorld(rid, end, profile=CRATE)
        for i, (row, label) in enumerate(zip(lines(raw/'eval-only.jsonl.zst'), lines(raw/f'teacher-{rid}.jsonl.zst'))):
            world = model.observe(row['visible_measurements'][rid], row['t'])
            if row['t'] >= when-1e-8:
                cases.append({'seed': seed, 'rid': rid, 'end': end, 'world': world,
                              'baseline_command': label['clean_teacher_command'],
                              'phase': label['teacher_phase'], 'folded': True,
                              'source': {'path': str(raw/'eval-only.jsonl.zst'),
                                         'sha256': digest(raw/'eval-only.jsonl.zst'), 'tick': i}})
                break
            model.issue(label['applied_command'])
    return cases


def main():
    rows = []; fixtures = []
    for seed, sha in [(77969, '5644e3dd'), *((n, 'bf31840f') for n in range(77970, 77980))]:
        row, fixture = replay(RAW/f'crate-diag-{seed}-{sha}'/'raw')
        rows.append(row)
        if fixture is not None and not row['saved_success']:
            fixtures.append(fixture)
        print(seed, row['baseline_commands_verified'], 'same' if row['first_divergence'] is None else
              (row['first_divergence']['t'], row['first_divergence']['robots']), flush=True)
    summary = {'scope': 'all baseline grasp commands; candidate only through first divergence; no new physical result',
               'physics_steps': 0, 'render_calls': 0, 'remote_calls': 0,
               'baseline_commands_verified': sum(x['baseline_commands_verified'] for x in rows),
               'successful_unchanged': [x['seed'] for x in rows if x['saved_success'] and x['first_divergence'] is None],
               'successful_changed': [x['seed'] for x in rows if x['saved_success'] and x['first_divergence'] is not None],
               'invisible_measurements': sum(x['input_audit']['invisible_measurements'] for x in rows),
               'held_world_reads': sum(x['input_audit']['held_world_reads'] for x in rows), 'runs': rows}
    (EXP/'crate10-replay.json').write_text(json.dumps(summary, separators=(',', ':'))+'\n')
    (ROOT/'tests/fixtures/crate10-visible-approach.json').write_text(json.dumps(
        {'scope': 'isolated archived visible-input slices; not a candidate trajectory after pair divergence',
         'cases': snapshots()}, indent=2)+'\n')


if __name__ == '__main__':
    main()
