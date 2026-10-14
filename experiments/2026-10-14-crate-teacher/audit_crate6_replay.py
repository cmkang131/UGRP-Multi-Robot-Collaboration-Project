"""Inspect stored decisions and replay the unchanged pick command generator.

Missing numerical inputs are NOT synthesized from evaluation truth or images.
Pick probes use FK of issued PWM as a synthetic target, not a measured pose.
They prove code equivalence on those targets, not replay of the original run.
"""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

from audit_crate6_torque import ROOT, read
from harness.visual_arm_v3 import tool_pose
from sim.crate_grasp_teacher import CrateGraspTeacher

EXP = Path(__file__).resolve().parent
REPO = EXP.parents[1]
BASE = '6f312f74'


def frozen_class():
    name = 'crate6_frozen_visible_teacher'
    mod = types.ModuleType(name)
    source = subprocess.check_output(['git', 'show', BASE+':sim/grasp_act_teacher_v3.py'])
    exec(compile(source, name, 'exec'), mod.__dict__)
    sys.modules[name] = mod
    source = subprocess.check_output(['git', 'show', BASE+':sim/crate_grasp_teacher.py']).decode()
    source = source.replace('from sim.grasp_act_teacher_v3 import', f'from {name} import')
    ns = {'__name__': 'crate6_frozen_crate_teacher'}
    exec(compile(source, ns['__name__'], 'exec'), ns)
    return ns['CrateGraspTeacher']


def same_pick_source():
    source = 'sim/crate_grasp_teacher.py'
    old = ast.parse(subprocess.check_output(['git', 'show', BASE+':'+source]))
    new = ast.parse((REPO/source).read_text())
    def methods(tree):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name in ('_queue_pick', '_queue_lift')}
    return methods(old) == methods(new)


def audit():
    old_class = frozen_class()
    output = {'scope': __doc__, 'physics_steps': 0, 'render_calls': 0,
              'full_recorded_input_replay': 'BLOCKED: visible_measurements absent',
              'baseline': subprocess.check_output(['git', 'rev-parse', BASE], text=True).strip(),
              'merged_rootcause': subprocess.check_output(['git', 'rev-parse', '77ee0ab7'], text=True).strip(),
              'pick_and_lift_source_ast_identical': same_pick_source(), 'runs': [], 'cross_version': []}
    labels_by_run = {}
    for seed in (77208, 77212, 77921):
        for sha in ('b033e5f9', BASE):
            stage = 'diag' if sha == 'b033e5f9' or seed == 77921 else 'gate'
            raw = ROOT/f'crate-{stage}-{seed}-{sha}'/'raw'
            data, ref = read(raw/'result.json'); result = json.loads(data)
            data, ev_ref = read(raw/'eval-only.jsonl')
            ev = [json.loads(line) for line in data.splitlines()]
            grasp = [e for e in ev if e['stage'] == 'grasp']
            row = {'seed': seed, 'sha': sha, 'raw': str(raw), 'sources': [ref, ev_ref],
                   'grasp_rows': len(grasp), 'saved_input_rows': sum('visible_measurements' in e for e in grasp),
                   'prefix_held': result['prefix_held'], 'robots': {}}
            for rid, teacher in result['prefix']['teachers'].items():
                data, label_ref = read(raw/f'teacher-{rid}.jsonl'); row['sources'].append(label_ref)
                labels = [json.loads(line) for line in data.splitlines()]
                labels = [l for l in labels if l['t'] <= grasp[-1]['t']+1e-8]
                labels_by_run[seed, sha, rid] = labels
                logs = teacher.get('goal_set_log', [])
                record = {'outcome': teacher['outcome'], 'staging_distance_m': teacher['staging_distance_m'],
                          'planner_calls': teacher['planner_calls'], 'blocked_goal_calls': teacher['blocked_goal_calls'],
                          'first_goal_selection': logs[0] if logs else None,
                          'last_goal_selection': logs[-1] if logs else None, 'pick_probe': None}
                closed = next((l for l in labels if l['teacher_phase'] == 'closed'), None)
                if closed is not None:
                    pwm = closed['applied_command']['pwm']
                    pose = tool_pose(pwm)
                    target = (pose.x_m, pose.y_m, pose.z_m)
                    # Same explicit numerical probe, without pretending this FK
                    # was the original visible measurement (it was not saved).
                    w = {'robots': {rid: {'pose': [0., 0., 0.]}},
                         'beam': {'ends': {'teal': target}}}
                    old = old_class(rid, 'teal', pwm, bounds=(-20, 20, -20, 20))
                    new = CrateGraspTeacher(rid, 'teal', pwm, bounds=(-20, 20, -20, 20))
                    traces = []
                    for t in (old, new):
                        t._queue_pick(deepcopy(w), 0.)
                        t._queue_lift(10.)
                        traces.append({'events': t.arm.events, 'lift_pose': t.lift_pose})
                    equal = traces[0] == traces[1]
                    assert equal
                    record['pick_probe'] = {'closed_t': closed['t'], 'issued_pwm': pwm,
                        'synthetic_fk_target_m': target, 'command_queue_equal': equal,
                        'events': len(traces[0]['events']), 'lift_pwm': traces[0]['lift_pose'],
                        'scope': 'same-input command-generator probe; not original input replay'}
                row['robots'][rid] = record
            output['runs'].append(row)
        for rid in ('r1', 'r2'):
            a, b = (labels_by_run[seed, sha, rid] for sha in (BASE, 'b033e5f9'))
            # Do not compare t fields: starts have tiny host rounding differences.
            def command(l):
                c = l['applied_command']
                return {k: c[k] for k in ('pwm', 'wheels', 'duration_s')}
            first = next((i for i, (x, y) in enumerate(zip(a, b)) if command(x) != command(y)), None)
            output['cross_version'].append({'seed': seed, 'rid': rid, 'first_issued_command_difference_tick': first,
                'baseline_N': len(a), 'b033_N': len(b),
                'note': 'observed commands differ; not a fixed-controller replay or attribution to one source change'})
    assert output['pick_and_lift_source_ast_identical']
    output['source_sha256'] = {p: hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in (
        'sim/crate_grasp_teacher.py', 'sim/grasp_act_teacher_v3.py', 'sim/grasp_act_goal_set.py',
        'scripts/run_crate_teacher.py', 'harness/visual_arm.py', 'harness/visual_arm_v3.py')}
    (EXP/'crate6-replay.json').write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps({'exact_replay': output['full_recorded_input_replay'],
        'saved_input_rows': sum(r['saved_input_rows'] for r in output['runs']),
        'grasp_rows': sum(r['grasp_rows'] for r in output['runs']),
        'equal_pick_probes': sum(r['pick_probe'] is not None for run in output['runs'] for r in run['robots'].values())}))


if __name__ == '__main__':
    audit()
