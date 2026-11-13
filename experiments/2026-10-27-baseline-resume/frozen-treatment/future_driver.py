"""Future launch PLAN + AST-only audit; --execute is never used in CPU work.

Adds administrative callbacks to a runtime AST COPY of L. Frozen files are
never written. No original runner/model/simulator is imported in plan mode.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent


def instrument(source):
    tree = ast.parse(source)
    counts = dict(completion=0, progress=0)

    class Hooks(ast.NodeTransformer):
        def visit_ExceptHandler(self, node):
            self.generic_visit(node)
            if isinstance(node.type, ast.Name) and node.type.id == 'StopIteration' and node.name == 'done':
                body = []
                for line in node.body:
                    body.append(line)
                    if ast.dump(line).startswith("Assign(targets=[Subscript(value=Name(id='results'"):
                        body.extend(ast.parse("if __treatment_guard.completed(int(i), done.value, a, report):\n"
                                              "    report['status'] = 'treatment_administrative_stop'\n"
                                              "    return").body)
                        counts['completion'] += 1
                node.body = body
            return node

        def visit_Expr(self, node):
            self.generic_visit(node)
            call = node.value
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'write'
                    and len(call.args) == 2 and isinstance(call.args[1], ast.Name) and call.args[1].id == 'progress'
                    and isinstance(call.args[0], ast.BinOp) and isinstance(call.args[0].right, ast.Constant)
                    and call.args[0].right.value == 'progress.json'):
                counts['progress'] += 1
                return [node, *ast.parse("if __treatment_guard.progress(progress, a):\n"
                    "    report['status'] = 'treatment_administrative_stop'\n    return").body]
            return node

    tree = Hooks().visit(tree)
    if counts != dict(completion=1, progress=1):
        raise ValueError('pinned runner AST hook mismatch: ' + str(counts))
    ast.fix_missing_locations(tree)
    return tree, counts


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


class Guard:
    def __init__(self, arm):
        self.arm, self.completions, self.speed_checked, self.stop = arm, [], False, False
        self.physical_motion = {}

    def completed(self, world, raw, args, report):
        self.completions.append((world, raw))
        if self.arm == 'arm_c' and len(self.completions) <= 4:
            from audit_cpu import read_physical_motion
            # Evaluation-only completed-lane logs; never sent to a policy,
            # stage transition, command correction or success notification.
            motion = read_physical_motion(args.out / f'world-{world:03d}' / 'raw', raw)
            self.physical_motion[world] = motion
            save_new(args.out / f'physical-motion-world-{world:03d}.json', motion)
        if self.arm == 'arm_c' and len(self.completions) == 4:
            from audit_cpu import pilot_gate
            decision = pilot_gate(self.completions, self.physical_motion)
            save_new(args.out / 'pilot-gate.json', decision)
            self.stop = not decision['pass_gate']
        return self.stop

    def progress(self, progress, args):
        if not self.speed_checked and progress['sim_s'] >= 30. - 1e-8:
            self.speed_checked = True
            clocks = progress.get('world_sim_s') or []
            elapsed = progress['loop_wall_s']
            ratios = [elapsed / (sim * len(clocks)) for sim in clocks if sim > 0]
            median = statistics.median(ratios) if len(ratios) == len(clocks) and clocks else None
            failed = median is None or median > 6.
            save_new(args.out / 'treatment-first30-audit.json', dict(median_wall_per_world_SIM=median,
                per_world_ratios=ratios, original_batch_metric=progress.get('per_world_wall_SIM'),
                denominator='loop wall allocated equally across N lanes, divided by each completed/active task SIM',
                threshold_basis='MiniMax P-23 / existing project >6.0, warning >3.5',
                SPEED_GATE_FAIL=failed, warning=median is not None and median > 3.5))
            self.stop = self.stop or failed
        return self.stop

    def finalize(self, output):
        # C-04: process exit 0 / an already measured speed gate must never
        # turn fewer than four Arm C completions into permission to follow up.
        if self.arm == 'arm_c' and not (output / 'pilot-gate.json').exists():
            save_new(output / 'pilot-gate.json', dict(
                schema='ugrp.baseline-treatment.pilot-gate.v2', pass_gate=False,
                reason=('fewer_than_four_completed_episodes' if len(self.completions) < 4
                        else 'missing_fourth_completion_decision'),
                completed_worlds=[world for world, _ in self.completions],
                required_completed_episodes=4, observed_completed_episodes=len(self.completions),
                followup_allowed=False,
                administrative_stop=self.stop,
                raw_statuses=[dict(world=world, status=raw.get('status')) for world, raw in self.completions]))
            self.stop = True
        # Learned done can terminate every lane before 30 SIM s. Do not claim
        # a measured speed gate or lengthen episodes to obtain that sample.
        if not self.speed_checked:
            save_new(output / 'treatment-first30-audit.json', dict(SPEED_GATE_FAIL=True,
                reason='all_lanes_ended_before_first30_measurement', median_wall_per_world_SIM=None))
            self.stop = True
        return self.stop


def make_plan(arm, out):
    plan = json.loads((HERE / 'launch-template.json').read_text())
    argv = list(plan['original_argv'])
    for flag, value in [('--out', out), ('--student-eval', str(HERE / ('student-eval-' + arm.replace('_', '-') + '.json'))),
                        ('--rejection-table', str(HERE / 'prior-funnel.json'))]:
        argv[argv.index(flag) + 1] = value
    return dict(arm=arm, python=plan['python'], argv=argv, cwd=plan['cwd'],
        environment={'WARP_SOURCE_ROOT': plan['cwd'], 'PYTHONDONTWRITEBYTECODE': '1'},
        pilot='callback immediately after fourth completed Arm C lane; before any next lane/physics step',
        execute=False, budget_authorized_by_this_plan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=('arm_c', 'arm_s'), default='arm_c')
    parser.add_argument('--out', required=True)
    parser.add_argument('--execute', action='store_true', help='future separately authorized GPU execution only')
    options = parser.parse_args()
    plan = make_plan(options.arm, options.out)
    reference = json.loads((HERE / 'baseline-reference.json').read_text())
    launcher = Path(reference['aliases']['L'])
    source = launcher.read_bytes()
    expected = next(row['expected_sha256'] for row in reference['files'] if row['label'] == 'L')
    if hashlib.sha256(source).hexdigest() != expected:
        raise ValueError('pinned launcher hash mismatch')
    tree, hooks = instrument(source)
    compiled = compile(tree, str(launcher) + ':external-treatment-copy', 'exec')
    if not options.execute:
        print(json.dumps(dict(plan, ast_compile='PASS', ast_hooks=hooks), indent=2))
        return
    # This branch is deliberately not exercised by CPU implementation/tests.
    from verify_baseline import verify
    checked = verify(reference)
    if not checked['all_match']:
        raise ValueError('frozen artifact/hash mismatch')
    if checked['disk']['free'] < 8 * 2**30:
        raise ValueError('existing project 8 GiB disk floor')
    # Entire expected write budget, latest GPU ledger/credits, VM lease and
    # no-competing-CPU work are operator preflight requirements, not inferred
    # from this simple disk-floor check. See prereg P-22..P-24.
    if os.environ.get('CUDA_VISIBLE_DEVICES') == '':
        raise ValueError('CPU-only environment: future GPU launch refused')
    guard = Guard(options.arm)
    os.environ.update(plan['environment'])
    os.chdir(plan['cwd'])
    sys.path.insert(0, str(launcher.parent))
    sys.argv = plan['argv']
    scope = dict(__name__='__main__', __file__=str(launcher), __treatment_guard=guard)
    try:
        exec(compiled, scope)
    finally:
        # Also leave a fail-closed pilot decision on runner exceptions once
        # its output directory exists; no frozen launcher bytes are changed.
        output = Path(options.out)
        if output.is_dir():
            guard.finalize(output)
    if guard.stop:
        sys.exit(3)


if __name__ == '__main__':
    main()
