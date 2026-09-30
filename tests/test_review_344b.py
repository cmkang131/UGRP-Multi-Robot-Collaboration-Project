"""Independent fix verification of PR #344, b7bc885a (no native execution).

Set REVIEW_344B_ROOT to a git archive of the candidate. The reviewer checkout
only owns this test/report. The five original strict xfails are required passes after REVIEW_344b fixes.
Probe/setup exceptions remain errors, not successful rejection evidence.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
OLD = "45c4ebc43daa96542cf298cea6f69964e501ec4a"
HEAD = "b7bc885a27aa5ab242e9f3710a3cd7090efe9f3a"


def candidate():
    path = Path(os.environ.get("REVIEW_344B_ROOT", ROOT)).resolve()
    if not (path / "harness/zone_final_pair_excitation.py").is_file():
        pytest.skip("Set REVIEW_344B_ROOT to the archived b7bc885a candidate")
    return path


def probe(source):
    env = {k: v for k, v in os.environ.items()
           if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTEST_ADDOPTS"}}
    env.update(PYTHONPATH=str(candidate()), PYTHONDONTWRITEBYTECODE="1")
    guard = """
import sys, socket, json
def forbidden(*a, **kw):
    raise RuntimeError('review forbids native physics/render/network/model')
socket.socket.connect = forbidden
for name in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
    sys.modules[name] = None
from harness.vision_loc_client import VisionWorkerClient
VisionWorkerClient.__init__ = forbidden
"""
    result = subprocess.run([sys.executable, "-B", "-c", guard + source],
                            cwd=candidate(), env=env, text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return json.loads(result.stdout)


REGRESSIONS = [
    ("R1", "test_measured_chassis_camera_projects_to_the_floor_and_beam_in_the_same_frame", None),
    *[("R2", "test_collection_changes_the_gain_lag_excitation_that_v87_could_not_identify", check)
      for check in ("calibration-unloaded", "calibration-fine", "calibration-loaded")],
    ("R2", "test_loaded_schedule_can_distinguish_two_required_gain_deadband_models", None),
    ("R3", "test_bundle_explicitly_records_changed_frame_and_arm_clocks", None),
    ("R4", "test_claimed_independent_review_identifies_reviewer_revision_and_original_report", None),
]


@pytest.mark.parametrize("finding,name,arg", REGRESSIONS)
def test_original_seven_regressions_pass_and_each_semantic_revert_fails(finding, name, arg):
    # Reverts are scoped to child-interpreter module objects, never the
    # candidate files. R2 compiles the exact old schedule, not a fake output.
    prefix = ""
    if finding == "R1":
        prefix = """
from harness import zone_final_pair_contract as c
source = open(c.__file__).read()
assert source.count('return floor_camera(record)') == 1
source = source.replace('return floor_camera(record)', 'return dict(record)')
exec(compile(source, c.__file__, 'exec'), c.__dict__)
"""
    elif finding == "R2":
        old = subprocess.check_output(
            ["git", "show", OLD + ":harness/zone_final_pair_calibration.py"], cwd=ROOT, text=True)
        prefix = ("from harness import zone_final_pair_calibration as cal\n"
                  f"exec(compile({old!r}, cal.__file__, 'exec'), cal.__dict__)\n")
    elif finding == "R3":
        prefix = """
from harness import zone_final_pair_contract as c
original_bundle = c.bundle
def undeclared_bundle(*a, **kw):
    value = original_bundle(*a, **kw)
    del value['timing']
    return value
c.bundle = undeclared_bundle
"""
    old_review = None
    if finding == "R4":
        old_review = json.loads(subprocess.check_output([
            "git", "show", OLD + ":experiments/2026-10-01-v3-pair-adapter/verification.json"], cwd=ROOT))
    data = probe(f"""
import importlib.util, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location('review_regressions', 'tests/test_review_344.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
fn = getattr(tests, {name!r})
args = [] if {arg!r} is None else [{arg!r}]
fn(*args)
baseline = 'PASS'
original_probe = tests.probe
tests.probe = lambda source: original_probe({prefix!r} + source)
with tempfile.TemporaryDirectory() as tmp:
    if {finding!r} == 'R4':
        path = Path(tmp)/'experiments/2026-10-01-v3-pair-adapter/verification.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({old_review!r}))
        tests.candidate = lambda: Path(tmp)
    try:
        fn(*args)
    except AssertionError as exc:
        mutation = 'ASSERTION_FAILED'
        failure = str(exc)[:500]
    else:
        mutation = 'SURVIVED'
        failure = ''
print(json.dumps({{'baseline':baseline, 'mutation':mutation, 'failure':failure}}))
""")
    assert data["baseline"] == "PASS" and data["mutation"] == "ASSERTION_FAILED", data


@pytest.mark.parametrize("check", ["calibration-unloaded", "calibration-fine", "calibration-loaded"])
def test_registered_collection_exceeding_envelope_stops_before_backend(check):
    data = probe(f"""
import contextlib, io, tempfile
from pathlib import Path
from harness import zone_final_pair_contract as c
from scripts import run_final_pair_v3 as run
check={check!r}
stream=io.StringIO()
with contextlib.redirect_stdout(stream):
    run.main(['--check',check,'--expected-source-sha',{'b7bc885a27aa5ab242e9f3710a3cd7090efe9f3a'!r},
              '--output','/unused-review-plan'])
plan=json.loads(stream.getvalue())
made=[]
def sentinel(*a, **kw):
    made.append('backend reached')
    raise RuntimeError('REVIEW_SENTINEL_NO_PHYSICS')
row=c.cases(check)[0]
bundle={{**c.bundle(row['map_id'],check),'case':row}}
with tempfile.TemporaryDirectory() as tmp:
    try:
        result=run.run_case(bundle,Path(tmp)/'case',seed=911,backend_factory=sentinel)
    except ValueError as exc:
        result={{'failure':str(exc)}}
print(json.dumps({{'plan_runnable':plan['runnable'], 'backend_calls':made,
                  'result':result, 'blocked_on':plan['blocked_on']}}))
""")
    # 2026-10-01 coordinator decision replaces exact path qualification.
    # These unchanged schedules still exceed the conservative disc envelope.
    assert not data["plan_runnable"] and not data["backend_calls"], data
    assert 'CONSERVATIVE_ENVELOPE_EXCEEDS_WALLS' in data['blocked_on'][0]
    assert 'radius=' in data['blocked_on'][0] and 'wall_distance=' in data['blocked_on'][0]


@pytest.mark.parametrize("fault", ["second_nan_xy", "second_nan_radius", "second_negative_radius"])
def test_all_geometry_entries_fail_closed_and_hold(fault):
    data = probe(f"""
import numpy as np, pytest
from tests.test_zone_final_pair_review_fixes import fake_guard
with pytest.MonkeyPatch.context() as patch:
    obj=fake_guard(patch,True)
    obj.collection_guard()
    if {fault!r}=='second_nan_xy': obj.world.data.geom_xpos[1,0]=float('nan')
    elif {fault!r}=='second_nan_radius': obj.world.model.geom_rbound[1]=float('nan')
    else: obj.world.model.geom_rbound[1]=-.1
    try: obj.collection_guard()
    except ValueError as exc: reason=str(exc)
    else: reason=None
    print(json.dumps({{'reason':reason, 'held':obj.held, 'saved':obj.saved}}))
""")
    assert data["reason"] and data["held"] == ["r1", "r2"], data
    assert data["saved"][0][0] == "eval_only/clearance_abort.jsonl"


@pytest.mark.parametrize("geometry", ["second_robot", "beam"])
def test_nonfinite_geometry_z_is_rejected_before_projection(geometry):
    data = probe(f"""
import pytest
from tests.test_zone_final_pair_review_fixes import fake_guard
with pytest.MonkeyPatch.context() as patch:
    obj=fake_guard(patch,True)
    obj.collection_guard()
    index=1 if {geometry!r}=='second_robot' else 2
    obj.world.data.geom_xpos[index,2]=float('nan')
    try: obj.collection_guard()
    except ValueError as exc: reason=str(exc)
    else: reason=None
    print(json.dumps({{'reason':reason, 'held':obj.held, 'saved':obj.saved,
                      'returned_clearance':obj._clearance_min}}))
""")
    assert data["reason"] and data["held"] == ["r1", "r2"], data
    assert data["saved"][0][0] == "eval_only/clearance_abort.jsonl"


def independent_response(segments, dt, gain, tau, stop_tau, deadband, knee=None):
    """Closed-form integration; deliberately does not use repository integrators."""
    velocity = position = 0.
    rows = [position]
    for duration, command in segments:
        target = gain * (np.sign(command)*max(abs(command)-deadband, 0.) if knee is None else
                         command*np.clip((abs(command)-deadband)/(knee-deadband), 0., 1.))
        q = tau if command else stop_tau
        decay = math.exp(-dt/q)
        for _ in range(round(duration/dt)):
            position += target*dt + (velocity-target)*q*(1-decay)
            velocity = target + (velocity-target)*decay
            rows.append(position)
    return np.array(rows)


def test_loaded_nominal_clearance_is_not_a_motion_uncertainty_bound():
    data = probe("""
from harness.zone_final_pair_excitation import design
from harness.zone_final_pair_calibration import teacher_stations
from harness.zone_final_pair_contract import resolve
plan=design('calibration-loaded')
static=resolve(plan['map_id'])[0]
print(json.dumps({'plan':plan,'static':static,'start':teacher_stations(static)['r2']}))
""")
    # Hypothetical loaded sensitivity, not a fitted/observed motion model.
    # Until the first left command there is no yaw; r2 faces pi and receives
    # negative local-forward commands, so its world x displacement is +x.
    segments = [(data["plan"]["motion_start_s"], 0.)]
    for segment in data["plan"]["segments"]:
        if segment["axis"] != "forward":
            break
        segments.append((segment["duration_s"], segment["value"]))
    static = data["static"]
    x0, x1, y0, y1 = static["bounds_m"]
    start_x, y, _ = data["start"]

    def minimum(gain):
        delta = independent_response(segments, .05, gain, .84, .08, .005)
        gaps = []
        for x in start_x + delta:
            distances = [x-x0, x1-x, y-y0, y1-y]
            for wall in static["obstacles"]:
                cx, cy = wall["center_m"]
                hx, hy = wall["half_extents_m"]
                distances.append(math.hypot(max(cx-hx-x, 0., x-cx-hx),
                                            max(cy-hy-y, 0., y-cy-hy)))
            gaps.append(min(distances) - .4)
        return min(gaps)

    assert minimum(1.576) == pytest.approx(.4421213331325532, abs=1e-10)
    assert minimum(2.5) == pytest.approx(.14329957666965976, abs=1e-10)
    assert minimum(2.5) < data["plan"]["clearance"]["minimum_m"]


@pytest.mark.parametrize("check", ["calibration-unloaded", "calibration-fine", "calibration-loaded"])
def test_conditional_identifiability_matches_actual_commands_and_independent_integral(check):
    data = probe(f"""
from harness.zone_final_pair_excitation import design, AXES
from harness.zone_final_pair_calibration import schedule
from scripts.check_pair_v88_identifiability import response
from pathlib import Path
evidence=json.loads(Path('experiments/2026-10-01-v3-pair-adapter/identifiability_v2.json').read_text())
plan=design({check!r})
rows=[e for e in schedule({check!r}) if e['robot_id']=='r1' and e['action']['kind']=='mecanum']
actual=[[e['action'][a] for a in AXES] for e in rows]
expected=[[s['value'] if a==s['axis'] else 0. for a in AXES]
          for s in plan['segments'] for _ in range(round(s['duration_s']/.05))]
result=[]
for axis,row in evidence['profiles'][{check!r}].items():
    axis_name='forward' if axis=='runtime_ramp' else axis
    segments=[(s['duration_s'],s['value']) for s in plan['segments'] if s['axis']==axis_name]
    p=row['synthetic_parameters']
    values=[p[k] for k in ('gain','drive_tau_s','stop_tau_s','deadband')]
    if 'knee' in p: values.append(p['knee'])
    y=p['gain']*response(segments,.05,p['drive_tau_s'],p['stop_tau_s'],p['deadband'],p.get('knee'))
    result.append({{'axis':axis,'segments':segments,'values':values,'response':y.tolist(),'record':row}})
print(json.dumps({{'same_schedule':actual==expected,'result':result}}))
""")
    assert data["same_schedule"]
    for row in data["result"]:
        values, segments = row["values"], row["segments"]
        expected = independent_response(segments, .05, *values)
        np.testing.assert_allclose(expected, row["response"], atol=1e-12)
        columns = []
        for i in range(len(values)):
            low, high = values.copy(), values.copy()
            low[i] *= math.exp(-1e-4)
            high[i] *= math.exp(1e-4)
            columns.append((independent_response(segments, .05, *high) -
                            independent_response(segments, .05, *low))/(2e-4))
        jacobian = np.column_stack(columns)
        # stop tau is an additional nuisance, absent from the reported rank.
        assert np.linalg.matrix_rank(jacobian) == len(values)
        selected = [i for i in range(len(values)) if i != 2]
        information = jacobian[:, selected].T @ jacobian[:, selected] / .0001**2
        eigenvalues = np.linalg.eigvalsh(information)
        assert eigenvalues[-1]/eigenvalues[0] == pytest.approx(row["record"]["fisher_condition"], rel=1e-7)
