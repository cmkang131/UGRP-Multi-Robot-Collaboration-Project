"""Independent narrow fix verification of PR #344 at 747d2b9f.

Set REVIEW_344C_ROOT to the candidate's git archive. No native physics,
rendering, network, model worker or live outputs are used. Mutations exist
only in child interpreter memory. An unexpected probe exception is an error,
never a successful rejection. No unresolved counterexample was found.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
OLD = "b7bc885a27aa5ab242e9f3710a3cd7090efe9f3a"
HEAD = "747d2b9f1eb43e21804ccef58fff4db241d1a844"
CHECKS = ("calibration-unloaded", "calibration-fine", "calibration-loaded")


def candidate():
    root = Path(os.environ.get("REVIEW_344C_ROOT", ROOT)).resolve()
    if not (root / "configs/zone_final_pair_v88_clearance.json").is_file():
        pytest.skip("Set REVIEW_344C_ROOT to the archived 747d2b9f candidate")
    return root


def probe(source):
    env = {k: v for k, v in os.environ.items() if k not in {
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTEST_ADDOPTS"}}
    env.update(PYTHONPATH=str(candidate()), PYTHONDONTWRITEBYTECODE="1",
               OPENBLAS_NUM_THREADS="1", REVIEW_344B_ROOT=str(candidate()))
    guard = """
import sys, socket, json
def forbidden(*a, **kw):
    raise RuntimeError('independent review forbids physics/render/network/model')
socket.socket.connect = forbidden
for name in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
    sys.modules[name] = None
from harness.vision_loc_client import VisionWorkerClient
VisionWorkerClient.__init__ = forbidden
"""
    result = subprocess.run([sys.executable, "-B", "-c", guard + source],
                            cwd=candidate(), env=env, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return json.loads(result.stdout)


@pytest.mark.parametrize("kind,arg", [
    *[("B1_decision2", check) for check in CHECKS],
    ("B2", "second_robot"), ("B2", "beam"),
])
def test_five_updated_regressions_pass_and_semantic_reverts_fail(kind, arg):
    if kind == "B1_decision2":
        name = "test_registered_collection_advisory_reaches_fake_backend"
        mutation = """
from harness import zone_final_pair_clearance as clearance
source = open(clearance.__file__).read()
old = "return {'admitted': start['admitted'], 'envelope_policy': 'ADVISORY',"
new = "return {'admitted': bounds['no_cancellation_bound']['admitted'], 'envelope_policy': 'ADVISORY',"
assert source.count(old) == 1
exec(compile(source.replace(old, new), clearance.__file__, 'exec'), clearance.__dict__)
"""
    else:
        name = "test_nonfinite_geometry_z_is_rejected_before_projection"
        mutation = ""
        # Restore the actual old projection and guard, not a fabricated PASS.
        for module in ("harness.zone_final_pair_clearance", "sim.final_pair_v3"):
            path = module.replace(".", "/") + ".py"
            old = subprocess.check_output(["git", "show", f"{OLD}:{path}"], cwd=ROOT, text=True)
            mutation += (f"import {module} as reverted\n"
                         f"exec(compile({old!r}, reverted.__file__, 'exec'), reverted.__dict__)\n")
    result = probe(f"""
from tests import test_review_344b as tests
fn = getattr(tests, {name!r})
fn({arg!r})
original_probe = tests.probe
tests.probe = lambda source: original_probe({mutation!r} + source)
try:
    fn({arg!r})
except AssertionError:
    mutation = 'ASSERTION_FAILED'
else:
    mutation = 'SURVIVED'
print(json.dumps({{'baseline': 'PASS', 'mutation': mutation}}))
""")
    assert result == {"baseline": "PASS", "mutation": "ASSERTION_FAILED"}


@pytest.mark.parametrize("check", CHECKS)
@pytest.mark.parametrize("fault", [
    "missing", "disabled", "minimum", "buffer", "radius", "substep", "cadence", "measurement",
])
def test_all_collection_entries_require_unchanged_interlock(check, fault):
    data = probe(f"""
import copy, tempfile, pytest
from pathlib import Path
from harness import zone_final_pair_contract as c
from scripts import run_final_pair_v3 as run
from sim.final_pair_v3 import PhysicsBackend
check, fault = {check!r}, {fault!r}
case = c.cases(check)[0]
bundle = {{**c.bundle(case['map_id'], check), 'case': case}}
if fault == 'missing': del bundle['runtime_interlock']
elif fault == 'disabled': bundle['runtime_interlock']['required'] = False
elif fault == 'minimum': bundle['runtime_interlock']['minimum_m'] = 0.
elif fault == 'buffer': bundle['runtime_interlock']['abort_buffer_m'] = 0.
elif fault == 'radius': bundle['runtime_interlock']['robot_radius_bound_m'] = .01
elif fault == 'substep': bundle['runtime_interlock']['max_substep_displacement_m'] = 100.
elif fault == 'cadence': bundle['runtime_interlock']['checks'].remove('after_substep')
else: bundle['measurement']['clearance']['minimum_m'] = 0.
# An existing saved PASS cannot replace recomputed validation.
bundle['clearance_preflight']['admitted'] = True
sys.modules['sim.zone_final_v3_scene'] = None
calls, reasons = [], []
def sentinel(*a, **kw):
    calls.append('backend')
    raise RuntimeError('NO_NATIVE_EXECUTION')
with tempfile.TemporaryDirectory() as tmp:
    for entry in ('run_case', 'constructor'):
        try:
            if entry == 'run_case': run.run_case(bundle, Path(tmp)/entry, seed=911, backend_factory=sentinel)
            else: PhysicsBackend(bundle, Path(tmp)/entry, seed=911)
        except ValueError as exc: reasons.append(str(exc))
        else: reasons.append(None)
    files = list(Path(tmp).iterdir())
print(json.dumps({{'calls': calls, 'reasons': reasons, 'created': bool(files)}}))
""")
    reason = ("collection measurement differs from registered design" if fault == "measurement"
              else "MANDATORY_COLLECTION_INTERLOCK_REQUIRED")
    assert data == {"calls": [], "reasons": [reason, reason], "created": False}


@pytest.mark.parametrize("location", ["before_substep", "after_substep", "before_command", "eval"])
def test_real_guard_dispatch_rejects_nan_without_another_step(location):
    data = probe(f"""
import pytest
from tests.test_zone_final_pair_review_fixes import fake_guard
from sim.final_environment_checks import PhysicsBackend as Base
with pytest.MonkeyPatch.context() as patch:
    obj = fake_guard(patch, True)
    obj.collection_guard()
    steps = []
    def step(_):
        steps.append(obj.now)
        obj.world.data.time += .01
        if {location!r} == 'after_substep': obj.world.data.geom_xpos[2, 2] = float('nan')
    obj.world._physics_step_for = step
    if {location!r} != 'after_substep': obj.world.data.geom_xpos[2, 2] = float('nan')
    patch.setattr(Base, 'eval_sample', lambda _: None)
    try:
        if {location!r} in ('before_substep', 'after_substep'): obj.advance_to(.01)
        elif {location!r} == 'before_command': obj.issue('r1', {{'kind': 'hold'}})
        else: obj.eval_sample()
    except ValueError as exc: reason = str(exc)
    else: reason = None
    print(json.dumps({{'reason': reason, 'steps': steps, 'held': obj.held, 'saved': obj.saved}}))
""")
    assert data["reason"] == "INVALID_ROBOT_GEOMETRY", data
    assert data["steps"] == ([0.] if location == "after_substep" else [])
    assert data["held"] == ["r1", "r2"]
    assert data["saved"][0][0] == "eval_only/clearance_abort.jsonl"


@pytest.mark.parametrize("fault", ["wall", "nan", "missing"])
def test_real_guard_abort_writer_and_cleanup_retain_partial_files(fault):
    data = probe(f"""
import tempfile, pytest, numpy as np
from pathlib import Path
from types import SimpleNamespace
from tests.test_zone_final_pair_review_fixes import fake_guard
from harness import zone_final_pair_contract as c
from scripts import run_final_pair_v3 as run
from sim.final_environment_checks import PhysicsBackend as Base
with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as patch:
    out = Path(tmp)/'case'
    obj = fake_guard(patch, True)
    obj.out, obj.streams = out, {{}}
    obj._append = Base._append.__get__(obj)
    obj.commands = {{r: {{}} for r in obj.ports}}
    obj.world.model.neq = 0
    obj.world.data.ncon, obj.world.data.contact = 0, []
    obj.world.data.qpos, obj.world.data.qvel = np.zeros(1), np.zeros(1)
    positions = obj.world.data.geom_xpos
    obj.world.data.body = lambda name: SimpleNamespace(
        xpos=positions[{{'r1__robot':0, 'r2__robot':1, 'cargo_beam':2}}[name]], xmat=np.eye(3).ravel())
    obj.pose_sample_index = 0
    for port in obj.ports.values(): port.apply = lambda *a: None
    closed, steps = [], []
    obj.world.close = lambda: closed.append('world')
    def reset(cap):
        obj.collection_guard()
        return 0.
    obj.reset = reset
    def capture():
        obj._append('robots/r1/frames.jsonl', {{'t': obj.now, 'synthetic_test_only': True}})
        return {{}}
    obj.capture = capture
    def step(_):
        obj.world.data.time += .01
        steps.append(obj.now)
        if len(steps) == 2:
            if {fault!r} == 'wall': positions[1, 0] = 2.3
            elif {fault!r} == 'nan': positions[2, 2] = float('nan')
            else: obj.world.model.ngeom = 0
    obj.world._physics_step_for = step
    case = c.cases('calibration-loaded')[0]
    bundle = {{**c.bundle(case['map_id'], 'calibration-loaded'), 'case': case}}
    obj.bundle = bundle
    result = run.run_case(bundle, out, seed=911, backend_factory=lambda *a, **kw: obj)
    paths = ['robots/r1/frames.jsonl', 'robots/r1/commands.jsonl',
             'eval_only/r1/pose.jsonl', 'eval_only/clearance_abort.jsonl']
    hashes = json.loads((out/'artifacts.sha256.json').read_text())
    valid = all(hashes[p] == c.base.sha(out/p) for p in paths)
    abort = json.loads((out/'eval_only/clearance_abort.jsonl').read_text())
    saved = json.loads((out/'result.json').read_text())
    print(json.dumps({{'result': saved, 'abort': abort, 'valid_hashes': valid,
        'steps': steps, 'closed': closed, 'held': obj.held,
        'streams_closed': all(s.closed for s in obj.streams.values()),
        'receipt_equal': saved['clearance_preflight'] == bundle['clearance_preflight']}}))
""")
    result = data["result"]
    assert result["status"] == "HOST_ERROR" and not result["protocol_complete"]
    assert result["collection_data_status"] == "PARTIAL_INVALID_HOST_ERROR"
    assert result["partial_data_retained"] and result["physical_success"] is None
    assert result["failure"]["message"] == data["abort"]["reason"]
    assert data["valid_hashes"] and data["streams_closed"] and data["receipt_equal"]
    assert data["steps"] == [.01, .02] and data["closed"] == ["world"]
    assert data["held"] == ["r1", "r2", "r1", "r2"]


def test_shared_measurement_v2_helpers_are_the_same_functions():
    data = probe("""
from harness import zone_final_pair_clearance as pair, final_environment_measurement_v2 as measurement
names = ['rectangles', 'free_floor_area', 'clearance', 'require_clearance', 'geometry_envelope']
print(json.dumps({name: getattr(pair, name) is getattr(measurement, name) for name in names}))
""")
    assert all(data.values()), data


@pytest.mark.parametrize("check,absolute_integral,paired_integral,radius,paired_radius", [
    ("calibration-unloaded", 1.51, .61, 8.2648, 3.9939825034593914),
    ("calibration-fine", 1.208, .528, 6.91184, 3.551184855453375),
    ("calibration-loaded", 1.9525, .6325, 11.295597782702377, 4.9600122871912316),
])
def test_advisory_plan_numbers_match_independent_command_sums(
        check, absolute_integral, paired_integral, radius, paired_radius):
    data = probe(f"""
import contextlib, io
from scripts import run_final_pair_v3 as run
from harness.zone_final_pair_calibration import schedule
stream = io.StringIO()
with contextlib.redirect_stdout(stream):
    run.main(['--check', {check!r}, '--expected-source-sha', {HEAD!r}, '--output', '/unused-review-plan'])
print(json.dumps({{'plan': json.loads(stream.getvalue()), 'events': schedule({check!r})}}))
""")
    import math

    plan = data["plan"]
    receipt = plan["clearance_preflight"][0]
    assert plan["runnable"] and not plan["blocked_on"]
    assert receipt["envelope_policy"] == "ADVISORY" and receipt["runtime_interlock"]["required"]
    assert not receipt["no_cancellation_bound"]["admitted"]
    robots = ("r1", "r2") if check == "calibration-loaded" else ("r1",)
    for rid in robots:
        for axis in ("forward", "left", "turn"):
            motion = [e for e in data["events"] if e["robot_id"] == rid and e["action"]["kind"] == "mecanum"]
            total = math.fsum(abs(e["action"][axis]) * e["action"]["duration_s"] for e in motion)
            position = peak = 0.
            other = []
            for e in motion:
                impulse = e["action"][axis] * e["action"]["duration_s"]
                if e["phase"].endswith("_step"):
                    position += impulse
                    peak = max(peak, abs(position))
                else:
                    other.append(abs(impulse))
            assert total == pytest.approx(absolute_integral)
            assert peak + math.fsum(other) == pytest.approx(paired_integral)
            assert receipt["no_cancellation_bound"]["bodies"][rid]["absolute_command_integral_s"][axis] == pytest.approx(total)
            assert receipt["pair_cancellation_estimate"]["bodies"][rid]["estimated_excursion_integral_s"][axis] == pytest.approx(peak + math.fsum(other))
        assert receipt["no_cancellation_bound"]["bodies"][rid]["disc_radius_m"] == pytest.approx(radius)
        assert receipt["pair_cancellation_estimate"]["bodies"][rid]["disc_radius_m"] == pytest.approx(paired_radius)
