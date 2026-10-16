"""Regression of independent review #344 (original at 17b54de7).

REVIEW_344_ROOT may select a separate candidate checkout. The original
report/evidence at 17b54de7 is preserved; the regression now runs in the implementation. Native physics, rendering, network and model
workers are forbidden in every probe. An unexpected probe error is a RuntimeError
and cannot be swallowed by the strict AssertionError-only regressions. The original strict xfails are now required passes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = json.loads((ROOT/'experiments/2026-10-01-v3-pair-adapter/REVIEW_344_EVIDENCE.json').read_text())
BASE = "78ce79162d907d88d38ef3afcfc0c62e4a72aaba"
HEAD = "45c4ebc43daa96542cf298cea6f69964e501ec4a"
FLOOR = "04eb11c6a001f2a7d2ab916765d59b3661c06efe"
FIT = "a5cc1402049a249253893762e1ca347e448a5f3f"


def candidate():
    path = Path(os.environ.get("REVIEW_344_ROOT", ROOT)).resolve()
    if not (path / "harness/zone_final_pair_contract.py").is_file():
        pytest.skip("Set REVIEW_344_ROOT to the archived PR #344 candidate")
    return path


def blob(ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT)


def probe(source):
    env = {k: v for k, v in os.environ.items()
           if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTEST_ADDOPTS"}}
    env.update(PYTHONPATH=str(candidate()), PYTHONDONTWRITEBYTECODE="1")
    guard = """
import sys, socket
def forbidden(*a, **kw):
    raise RuntimeError('review forbids physics/render/network/real model')
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


def test_sealed_sources_and_v87_shared_definitions_have_identical_bytes():
    paths = (
        "harness/zone_pair_executor.py", "harness/zone_pair_v6_policy.py",
        "harness/zone_pair_grasp.py", "harness/zone_pair_align.py",
        "harness/owncam_localizer.py", "harness/owncam_carry_v6e.py",
        "harness/vision_pose_source_p03.py", "harness/zone_study_pose_delay_p03.py",
        "scripts/run_m2_pair.py", "scripts/study_owncam_pair_beam.py",
        "sim/camera_robot_port.py", "sim/render_profile.py", "sim/zone_final_v3_scene.py",
        "configs/final_environment_measurement_v1.json",
        "configs/simulation_workflows.json", "tests/test_zone_pair_registered_source.py",
        "tests/test_zone_study_source_pinning.py",
    )
    for path in paths:
        recorded = EVIDENCE['source_preservation'][path]
        # Audit the three recorded review trees. Post-unblinding main includes
        # the separately sealed v6h successor; it is not the old v87 checkout.
        for ref in (BASE, HEAD, FLOOR):
            assert hashlib.sha256(blob(ref, path)).hexdigest() == recorded[ref], (ref, path)
        assert recorded[BASE] == recorded[HEAD] == recorded[FLOOR], path
        if os.environ.get('REVIEW_344_ROOT'):
            # Preserve explicit historical-candidate negative controls.
            assert hashlib.sha256((candidate()/path).read_bytes()).hexdigest() == recorded[HEAD], path
    changed = subprocess.check_output(["git", "diff", "--name-only", BASE, HEAD,
                                       "--", ".github/workflows"], cwd=ROOT)
    assert not changed


def test_measured_chassis_camera_projects_to_the_floor_and_beam_in_the_same_frame():
    data = probe("""
import json, numpy as np
from harness import zone_final_pair_vision as v
from harness.vision_pose_source_final import camera_key, measured_column_model
from harness import vision_loc_protocol as vp
from harness.owncam_pair_beam import BEAM_TOP_Z_M
servo = {3:740, 4:2320, 5:1320, 6:1500}
# Synthetic rigid camera measured relative to a chassis 32.36 mm above floor.
# This is the collection's declared actual-chassis convention, not live GT.
height = .03236
record = {'frame':'optical_to_actual_chassis', 'origin_m':[.15, 0., .2], 'rotation':[[0,0,1],[-1,0,0],[0,-1,0]], 'chassis_to_floor':{'origin_m':[0.,0.,height],'rotation':np.eye(3).tolist()}}
v._pixel_rays = lambda step: (np.array([320]), np.array([400]), np.array([[0.,1.]]), np.array([True]))
vision = v.PairVision({'camera_models':{'unloaded':{camera_key(servo):record}}})
origin, rays, *_ = vision.base_rays(servo)
observed = origin + rays[0]*(BEAM_TOP_Z_M-origin[2])/rays[0,2]
expected = np.array([.15+.2+height-BEAM_TOP_Z_M, 0., BEAM_TOP_Z_M])
vl, _ = vp.load_vis3()
from harness.zone_final_pair_contract import camera_record
projected = camera_record(vision.calibration, 'unloaded', servo)
measured = measured_column_model(vl.mp, projected, np.array([320]))
floor_record = {**record, 'origin_m':[.15, 0., .2+height]}
correct = measured_column_model(vl.mp, floor_record, np.array([320]))
print(json.dumps({'beam_error_m':float(np.linalg.norm(observed[:2]-expected[:2])),
                  'floor_error_m':float(np.linalg.norm(measured.q0-correct.q0)),
                  'beam_x_m':float(observed[0]), 'expected_x_m':float(expected[0])}))
""")
    assert data["beam_error_m"] <= .003 and data["floor_error_m"] <= .003, data


@pytest.mark.parametrize("check", ["calibration-unloaded", "calibration-fine", "calibration-loaded"])
def test_collection_changes_the_gain_lag_excitation_that_v87_could_not_identify(check):
    # The failure evidence is an immutable offline fit, not a new SIM run.
    # Copied verbatim from the independently preserved review evidence. No
    # dependency on an unmerged remote branch being present in a CI clone.
    assert EVIDENCE['fit_346_sha'] == FIT
    fit = {'axes': EVIDENCE['fit_346_axes']}
    if any(fit["axes"][axis]["gain_lag_identified"] for axis in ("forward", "lateral")):
        raise RuntimeError("review reference changed")
    data = probe("""
import json
from harness.zone_final_pair_calibration import schedule
from harness import zone_final_pair_contract as c
protocol = c.base.read(c.ROOT/'configs/final_environment_measurement_v1.json')
reference = [e for e in protocol['events'] if e['t'] >= 72.]
def signature(rows):
    t0 = rows[0]['t']
    scale = max(abs(e['action'][a]) for e in rows for a in ('forward','left','turn'))
    return [[e['t']-t0, *[e['action'][a]/scale for a in ('forward','left','turn')],
             e['action']['duration_s']] for e in rows]
ref = [{'t':e['t'], 'action':e['actions'][0]} for e in reference]
rows = [e for e in schedule(CHECK) if e['robot_id']=='r1' and e['action']['kind']=='mecanum']
print(json.dumps({'actual':signature(rows), 'failed_v87':signature(ref)}))
""".replace("schedule(CHECK)", f"schedule({check!r})"))
    # Scaling every pulse down (fine) or translating its start time (loaded)
    # does not add a second duration/steady-state regime to identify linear lag.
    assert data["actual"] != data["failed_v87"], check


def test_loaded_schedule_can_distinguish_two_required_gain_deadband_models():
    data = probe("""
import json, numpy as np
from harness.zone_final_pair_calibration import schedule
rows = [e for e in schedule('calibration-loaded') if e['action']['kind']=='mecanum']
u = np.array([[e['action'][a] for a in ('forward','left','turn')] for e in rows])
# Both are valid profile families. With identical lag/noise, equal targets
# give equal full trajectories at ANY sample rate, including qpos at 0.05 s.
a = .5*u
b = u*np.clip((abs(u)-.01)/(.05-.01), 0., 1.)
# They predict different behavior at an unmeasured command 0.06.
print(json.dumps({'max_target_difference':float(abs(a-b).max()),
                  'unseen_target_difference':abs(.5*.06-.06)}))
""")
    assert data["unseen_target_difference"] > .01  # ensure the models really differ
    assert data["max_target_difference"] > 1e-6, data


def test_bundle_explicitly_records_changed_frame_and_arm_clocks():
    data = probe("""
import json
from harness import zone_final_pair_contract as c
from harness.zone_own_team_host import OwnCamTeamHost
from harness.zone_pair_status import CONTROL_S, ARM_S
b = c.bundle(c.registry()['maps'][0], 'p03')
print(json.dumps({'bundle':b, 'sealed_background_rgb_s':OwnCamTeamHost.FRAME_S,
                  'control_s':CONTROL_S, 'arm_nominal_s':ARM_S}))
""")
    # Presence of source hashes pins implementation bytes, but is not an
    # explicit receipt of applied clocks or of a change from the sealed host.
    declared = {k: v for k, v in data["bundle"].items() if k not in
                {"source_sha256", "calibration_contract"}}
    text = json.dumps(declared).lower()
    assert any(word in text for word in ("timing", "cadence", "observation_period", "clock")), declared


def test_claimed_independent_review_identifies_reviewer_revision_and_original_report():
    record = json.loads((candidate()/"experiments/2026-10-01-v3-pair-adapter/verification.json").read_text())
    review = record["independent_review"]
    # This checks auditability, not whether a private review did or did not occur.
    reviewer = any(review.get(k) for k in ("reviewer", "reviewer_id", "agent_id", "reviewer_identity"))
    revision = any(review.get(k) for k in ("reviewed_sha", "reviewed_source_sha256", "candidate_sha", "reviewed_files_sha256"))
    artifact = any(review.get(k) for k in ("report_path", "report_url", "review_url", "artifact"))
    assert reviewer and revision and artifact, review


@pytest.mark.parametrize("check", ["p03", "carry", "calibration-unloaded", "calibration-fine", "calibration-loaded"])
def test_teacher_staging_never_constructs_a_student_and_total_cap_remains_375(check):
    data = probe("""
import json, tempfile
from pathlib import Path
from harness import zone_final_pair_contract as c
from scripts import run_final_pair_v3 as run
from sim.final_pair_v3 import make_scene
from tests.test_zone_final_pair_v3 import FakePhysics, FakeRuntime
# Fake clocks only, with the real collection preflight.
check = CHECK
made, students = [], []
class Physics(FakePhysics):
    def __init__(self, b, out, *, seed):
        super().__init__(b, out, seed=seed)
        self.teacher = 'teacher_measurement_stations' in make_scene(b, seed).config['setup_only']
        made.append(self)
    def reset(self, cap):
        self.now = cap
        return cap
class Student(FakeRuntime):
    def __init__(self, *a, **kw):
        students.append(1)
        super().__init__(*a, **kw)
with tempfile.TemporaryDirectory() as tmp:
    results = []
    cases = c.cases(check)
    for row in cases:
        b = {**c.bundle(row['map_id'], check), 'case':row}
        results.append(run.run_case(b, Path(tmp)/row['id'], seed=911,
            backend_factory=Physics, runtime_factory=Student))
    print(json.dumps({'teachers':[p.teacher for p in made], 'students':len(students),
        'times':[p.now for p in made], 'closed':all(p.closed for p in made),
        'statuses':[r['status'] for r in results], 'success':[r['physical_success'] for r in results],
        'captures':[len(p.frames) for p in made]}))
""".replace("check = CHECK", f"check = {check!r}"))
    collection = check.startswith("calibration-")
    count = 1 if collection else 3
    assert data["teachers"] == [check == "calibration-loaded"]*count
    assert data["students"] == (0 if collection else 3)
    assert data["times"] == ([375.] if collection else [125.]*3) and data["closed"]
    assert sum(data["times"]) <= 375.
    assert data["statuses"] == ["COLLECTED_UNQUALIFIED"]*count
    assert data["success"] == [None]*count
    assert data["captures"] == [1851 if collection else 2401]*count


def test_reset_overrun_stops_before_any_capture_or_command():
    data = probe("""
import json, tempfile
from pathlib import Path
from harness import zone_final_pair_contract as c
from scripts import run_final_pair_v3 as run
from tests.test_zone_final_pair_v3 import FakePhysics
# Fake lifecycle/reset test with real collection admission.
made=[]
class Physics(FakePhysics):
    def __init__(self,*a,**kw): super().__init__(*a,**kw); made.append(self)
    def reset(self,cap): self.now=cap+.00025; return self.now
row=c.cases('calibration-loaded')[0]
with tempfile.TemporaryDirectory() as tmp:
    r=run.run_case({**c.bundle(row['map_id'],'calibration-loaded'),'case':row},Path(tmp)/'case',
                   seed=911,backend_factory=Physics)
    print(json.dumps({'result':r,'commands':made[0].actions,'frames':made[0].frames,'closed':made[0].closed}))
""")
    assert data["result"]["status"] == "HOST_ERROR"
    assert data["result"]["failure"]["message"] == "RESET_SIM_CAP_EXCEEDED"
    assert data["commands"] == data["frames"] == [] and data["closed"]


@pytest.mark.parametrize("fault", ["missing", "partial", "v2", "missing_loaded"])
def test_p03_bad_calibration_stops_before_physics_import(fault):
    data = probe("""
import json, tempfile
from pathlib import Path
from tests.test_zone_final_pair_v3 import synthetic
from harness import zone_final_pair_contract as c
from scripts import run_final_pair_v3 as run
run.check_source=lambda sha: None
sys.modules['sim.final_pair_v3']=None
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    path, cal=synthetic(root)
    fault=FAULT
    if fault=='partial': cal['status']='PARTIAL_UNLOADED_SIM'
    elif fault=='v2': cal['robot_model']='masterpi_v2'
    elif fault=='missing_loaded': del cal['params']['motion_loaded']
    run.write(path,cal)
    argv=['--check','p03','--expected-source-sha','a'*40,'--output',str(root/'output'),'--execute']
    if fault!='missing': argv+=['--calibration',str(path),'--calibration-sha256',c.base.sha(path)]
    try: run.main(argv)
    except ValueError as e: reason=str(e)
    else: reason=None
    print(json.dumps({'reason':reason,'output_exists':(root/'output').exists()}))
""".replace("fault=FAULT", f"fault={fault!r}"))
    assert data["reason"] and not data["output_exists"]


@pytest.mark.parametrize("fault", ["shadow", "reflection", "spot", "dark", "missing_floor"])
def test_floor_light_enforcement_rejects_bad_model_and_closes_backend(fault):
    data = probe("""
import json, tempfile, copy
from pathlib import Path
from types import SimpleNamespace
from harness import zone_final_pair_contract as c
from scripts import run_final_pair_v3 as run
from sim.final_pair_v3 import PhysicsBackend
from sim.final_environment_checks import PhysicsBackend as Base
from sim import render_profile as rp
# Fake render-profile owner only; the real collection preflight remains enabled.
audit={'light_castshadow':[0]*4, 'materials_with_reflectance':{}, 'light_cutoff':[180.]*4,
       'ground_texture_mean_rgb':[125.,122.,118.]}
fault=FAULT
if fault=='shadow': audit['light_castshadow'][0]=1
if fault=='reflection': audit['materials_with_reflectance']={'groundmat':.035}
if fault=='spot': audit['light_cutoff'][0]=45.
if fault=='dark': audit['ground_texture_mean_rgb']=[60.,62.,65.]
if fault=='missing_floor': audit['ground_texture_mean_rgb']=None
rp.audit_model=lambda model: copy.deepcopy(audit)
Base.reset=lambda self,cap: 1.
made=[]
def factory(bundle,out,*,seed):
    obj=PhysicsBackend.__new__(PhysicsBackend)
    obj.out,obj.bundle,obj.ports,obj.streams=Path(out),bundle,{},{}
    obj.world=SimpleNamespace(model=object(),data=SimpleNamespace(time=1.),close=lambda:made.append('closed'))
    return obj
row=c.cases('calibration-unloaded')[0]
with tempfile.TemporaryDirectory() as tmp:
    r=run.run_case({**c.bundle(row['map_id'],'calibration-unloaded'),'case':row},Path(tmp)/'case',
                   seed=911,backend_factory=factory)
    print(json.dumps({'result':r,'cleanup':made}))
""".replace("fault=FAULT", f"fault={fault!r}"))
    assert data["result"]["status"] == "HOST_ERROR"
    assert "render profile floor_light_v1" in data["result"]["failure"]["message"]
    assert not data["result"]["protocol_complete"] and data["cleanup"] == ["closed"]


def test_actual_capture_keeps_truth_labels_out_of_student_frames():
    data = probe("""
import json, tempfile, copy
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from sim.final_pair_v3 import PhysicsBackend
from harness.zone_final_pair_runtime import Runtime
from tests.test_zone_pair_executor import pair_obs
from tests.test_zone_final_pair_v3 import SERVO
with tempfile.TemporaryDirectory() as tmp:
    backend=PhysicsBackend.__new__(PhysicsBackend)
    backend.out=Path(tmp)
    backend.frame=0
    backend.commands={r:dict(SERVO) for r in ('r1','r2')}
    backend.bundle={'check':'p03'}
    body=SimpleNamespace(xpos=np.array([1.,2.,.03236]),xmat=np.eye(3).reshape(-1))
    camera=SimpleNamespace(xpos=np.array([1.15,2.,.23236]),xmat=np.eye(3).reshape(-1))
    backend.world=SimpleNamespace(data=SimpleNamespace(time=1.,body=lambda name:body,camera=lambda name:camera))
    backend.ports={r:SimpleNamespace(capture=lambda r=r:pair_obs(r,1,1.,SERVO)) for r in ('r1','r2')}
    labels=[]
    backend._append=lambda path,row:labels.append((path,copy.deepcopy(row)))
    first=backend.capture()
    first_labels=[r for p,r in labels if p.startswith('eval_only/')]
    body.xpos=np.array([900.,-900.,.50])
    body.xmat=np.diag([-1.,-1.,1.]).reshape(-1)
    camera.xpos=np.array([-800.,700.,.99])
    labels.clear()
    second=backend.capture()
    second_labels=[r for p,r in labels if p.startswith('eval_only/')]
    inbox={r:[] for r in ('r1','r2')}
    runtime=Runtime.__new__(Runtime)
    runtime.actors={r:SimpleNamespace(on_frame=lambda now,obs,rgb,r=r:inbox[r].append(obs['robot_id'])) for r in inbox}
    runtime.on_frames(1.,second)
    print(json.dumps({'same_observations':all(first[r][0]==second[r][0] for r in first),
        'same_pixels':all(np.array_equal(first[r][1],second[r][1]) for r in first),
        'changed_labels':first_labels!=second_labels,'inbox':inbox,
        'control_keys':sorted(second['r1'][0])}))
""")
    assert data["same_observations"] and data["same_pixels"] and data["changed_labels"]
    assert data["inbox"] == {"r1": ["r1"], "r2": ["r2"]}
    assert data["control_keys"] == sorted(
        ["robot_id", "frame_id", "sim_time", "image", "sha256", "camera", "actuator_state"])


def test_active_weld_is_rejected_by_real_evaluation_owner():
    data = probe("""
import json
from types import SimpleNamespace
from sim.final_pair_v3 import PhysicsBackend
sys.modules['mujoco']=SimpleNamespace(mjtEq=SimpleNamespace(mjEQ_WELD=1))
obj=PhysicsBackend.__new__(PhysicsBackend)
obj.world=SimpleNamespace(model=SimpleNamespace(neq=1,eq_type=[1]),
                          data=SimpleNamespace(time=0.,ncon=0,contact=[],eq_active=[1]))
saved=[]
obj._append=lambda path,row:saved.append((path,row))
try: obj.eval_sample()
except RuntimeError as e: reason=str(e)
else: reason=None
print(json.dumps({'reason':reason,'saved':saved}))
""")
    assert data["reason"] == "WELD_OFF_VIOLATION"
    assert data["saved"][0][0] == "eval_only/contacts.jsonl"
    assert data["saved"][0][1]["active_weld_ids"] == [0]
