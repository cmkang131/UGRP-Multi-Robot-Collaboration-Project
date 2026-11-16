"""CPU-only audit of production score functions; no robot, renderer or model."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lift(module, *, n=31, clearance=.02, tilt=1., forces=(1., 1.), weld=False):
    score = module.LiftScore()
    for i in range(n):
        score.add(i / 10, clearance=clearance, tilt=tilt, forces=forces, weld=weld)
    return score.record()['lift_success']


def release(module, *, dropped=False, clearance=0., tilt=1., forces=(0., 0.), speed=0.):
    score = module.SoloScore()
    for i in range(32):
        score.add(i / 10, skill='grasp', clearance=.02, tilt=1., forces=(1., 1.),
                  linear_speed=0., weld=False)
    for i in range(32, 65):
        score.add(i / 10, skill='release', clearance=.02 if dropped and i == 32 else clearance,
                  tilt=tilt, forces=forces, linear_speed=speed, weld=False)
    return score.record({'grasp': 0., 'release': 3.2}, with_release=True)['physical_success']


def missing_sample(module):
    score = module.LiftScore()
    score.add(0., clearance=.02, tilt=1., forces=(1., 1.), weld=False)
    score.add(.2, clearance=.02, tilt=1., forces=(1., 1.), weld=False)


def missing_force_field(module):
    module.LiftScore().add(0., clearance=.02, tilt=1., weld=False)


cases = [
    ('normal_lift', lambda m: lift(m), True),
    ('no_lift', lambda m: lift(m, clearance=0.), False),
    ('one_finger_unloaded', lambda m: lift(m, forces=(1., 0.)), False),
    ('tilted', lambda m: lift(m, tilt=10.000001), False),
    ('exact_lift_thresholds_and_3s', lambda m: lift(m, clearance=.012, tilt=10., forces=(.5, .5)), True),
    ('only_2_9s', lambda m: lift(m, n=30), False),
    ('no_samples', lambda m: m.LiftScore().record()['lift_success'], False),
    ('missing_100ms_sample', missing_sample, 'ValueError'),
    ('missing_force_field', missing_force_field, 'TypeError'),
    ('weld_active', lambda m: lift(m, weld=True), 'ValueError'),
    ('normal_release', lambda m: release(m), True),
    ('drop_then_grounding', lambda m: release(m, dropped=True), False),
    ('release_moving', lambda m: release(m, speed=.020001), False),
    ('release_lower_clearance_boundary', lambda m: release(m, clearance=-.005, tilt=10., speed=.02), True),
    ('release_upper_clearance_boundary', lambda m: release(m, clearance=.006, tilt=10., speed=.02), True),
    ('release_force_exact_0_1N', lambda m: release(m, forces=(.1, .1)), False),
]
rows = []
for rel in ('harness/grasp_act_rollout.py', 'solo_pipeline/harness/grasp_act_rollout.py'):
    module = load(ROOT / rel, 'score_' + str(len(rows)))
    for name, run, expected in cases:
        detail = None
        try:
            actual = run(module)
        except Exception as exc:
            actual, detail = type(exc).__name__, str(exc)
        rows.append({'source': rel, 'case': name, 'expected': expected, 'actual': actual,
                     'matches': actual == expected, 'detail': detail})

print(json.dumps({'scope': 'synthetic evaluator contract tests, not physical reproduction',
                  'cases': rows, 'passed': sum(row['matches'] for row in rows),
                  'total': len(rows)}, indent=2))
if not all(row['matches'] for row in rows):
    raise SystemExit(1)
