"""Independent PR #342 review: native physics/render/network are never used.

REVIEW_342_ROOT selects the archived candidate. Without it, a checkout lacking
v87 skips this review. BASE_REF is the main SHA inspected on 2026-10-01.
No confirmed implementation counterexample was found, so there are no xfails.
The deliberate enforcement mutant is tested separately from real defects.
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
BASE_REF = "78ce79162d907d88d38ef3afcfc0c62e4a72aaba"
HEAD_REF = "04eb11c6a001f2a7d2ab916765d59b3661c06efe"


def candidate():
    root = Path(os.environ.get("REVIEW_342_ROOT", ROOT)).resolve()
    if not (root / "harness/zone_final_environment_floor_light.py").is_file():
        pytest.skip("Set REVIEW_342_ROOT to the archived PR #342 candidate")
    return root


def python_in(root, source, *, xml_only=False):
    env = {k: v for k, v in os.environ.items()
           if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTEST_ADDOPTS"}}
    env.update(PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE="1")
    guard = """
import sys, types, socket
def forbidden(*args, **kwargs):
    raise AssertionError('review forbids native physics/render/network/worker')
socket.socket.connect = forbidden
for name in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
    sys.modules[name] = None
"""
    if xml_only:
        # Empty module: XML builders may import the name, but no native API
        # (MjModel, MjData, mj_step, Renderer, ...) exists or can be called.
        guard += "sys.modules['mujoco'] = types.ModuleType('mujoco')\n"
        guard += "del sys.modules['sim.multi_masterpi_production']\n"
    result = subprocess.run([sys.executable, "-B", "-c", guard + source], cwd=root,
                            env=env, text=True, capture_output=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_v84_live_main_bytes_and_all_nine_bundles_preserved():
    tree = candidate()
    record = json.loads((tree / "experiments/2026-10-01-final-env-floor-light/v84_preservation.json").read_text())
    for path, expected in record["files_sha256"].items():
        original = subprocess.check_output(["git", "show", f"{BASE_REF}:{path}"], cwd=ROOT)
        assert original == (tree / path).read_bytes(), path
        assert hashlib.sha256(original).hexdigest() == expected, path
    # Recompute in both source trees, not just against the author's receipt.
    source = """
import json
from harness import zone_final_environment as env
print(json.dumps({m+'/'+c: env.digest(env.bundle(m, check=c))
                  for m in env.registry()['maps'] for c in ('p01','calibration','p03')}))
"""
    assert python_in(tree, source) == python_in(ROOT, source) == record["bundles"]
    diff = subprocess.check_output(["git", "diff", "--name-status", f"{BASE_REF}...{HEAD_REF}",
                                    "--", "experiments", ".github/workflows"], cwd=ROOT, text=True)
    assert all(line.startswith("A\texperiments/") for line in diff.splitlines())


XML_AUDIT = """
import hashlib, json, xml.etree.ElementTree as ET
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.zone_final_v3_scene import FinalV3Scene
from sim.zone_arena import DEFAULT_GOAL
from sim.zone_cargo_contact import apply, base_profile
from sim import render_profile
from harness import zone_final_environment as env
rows = []
for mid in env.registry()['maps']:
    raw = build_multi_robot_xml(None)
    spec = {'map': mid, 'seed': 911, 'goal': DEFAULT_GOAL, 'extra_boxes': {}, 'team_cargo': []}
    scenes = [FinalV3Scene.from_spec(spec, base_profile('cargo_noslip_v1')) for _ in range(2)]
    render_profile.install(scenes[1], 'floor_light_v1')
    xmls = [s.robot_transform(apply(s.transform(raw), 'cargo_noslip_v1')) for s in scenes]
    before, after = [ET.fromstring(x) for x in xmls]
    diffs = []
    def compare(a, b, path=''):
        path += '/' + a.tag + '[' + str(a.get('name', '')) + ']'
        assert a.tag == b.tag and len(a) == len(b), path
        assert (a.text or '').strip() == (b.text or '').strip(), path
        for key in sorted(a.attrib.keys() | b.attrib.keys()):
            if a.get(key) != b.get(key):
                diffs.append([path, a.tag, a.get('name'), key, a.get(key), b.get(key)])
        for ac, bc in zip(a, b):
            compare(ac, bc, path)
    compare(before, after)
    # Same existing profile applied to the final XML must yield exactly v87.
    assert ET.tostring(after) == ET.tostring(ET.fromstring(render_profile.apply_xml(xmls[0], 'floor_light_v1')))
    assert scenes[0].manifest['robot_xml_sha256'] == scenes[1].manifest['robot_xml_sha256']
    assert all(w.get('active') == 'false' for w in after.iter('weld'))
    rows.append({'map': mid, 'diffs': diffs, 'option': after.find('option').attrib,
                 'robot_hashes': scenes[0].manifest['robot_xml_sha256'],
                 'xml_sha256': [hashlib.sha256(x.encode()).hexdigest() for x in xmls],
                 'cameras': [c.attrib for c in after.iter('camera')]})
print(json.dumps(rows))
"""


def test_full_xml_diff_is_existing_render_profile_only():
    rows = python_in(candidate(), XML_AUDIT, xml_only=True)
    assert len(rows) == 3
    for row in rows:
        assert len(row["diffs"]) == 23
        for _, tag, name, key, _, _ in row["diffs"]:
            assert ((tag == "light" and key in {"ambient", "diffuse", "specular", "cutoff", "castshadow"})
                    or (tag == "material" and key == "reflectance")
                    or (tag == "texture" and name == "ground" and key in {"rgb1", "rgb2"}))
        assert row["option"]["timestep"] == ".00025"
        assert row["option"]["noslip_iterations"] == "10"


RENDER_GATE = """
import json, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from harness import zone_final_environment_floor_light as env
from scripts.run_final_environment_checks import run_case
from sim import final_environment_floor_light as physics, zone_final_v3_scene as scenes
from sim import camera_robot_port
calls = []
scene = SimpleNamespace(manifest={}, transform=lambda x: x, engine_layout='fixed')
world = SimpleNamespace(model=SimpleNamespace(opt=SimpleNamespace(timestep=.00025)),
                        data=SimpleNamespace(time=0), close=lambda: calls.append('closed'))
audit = {'nlight': 4, 'light_castshadow': [0]*4, 'materials_with_reflectance': {},
         'light_cutoff': [180.]*4, 'ground_texture_mean_rgb': [125.,122.,118.]}
if fault == 'shadow': audit['light_castshadow'][0] = 1
if fault == 'reflection': audit['materials_with_reflectance'] = {'groundmat': .035}
if fault == 'cutoff': audit['light_cutoff'][0] = 45.
if fault == 'texture': audit['ground_texture_mean_rgb'] = [60.,65.,70.]
if fault == 'missing_texture': audit['ground_texture_mean_rgb'] = None
def fake_reset(self, cap):
    calls.append('reset')
    self.world.data.time = 5.
    return 5.
def advance(self, t): self.world.data.time = t
original_verify = physics.render_profile.verify_model
def verify(model, name):
    return physics.render_profile.audit_model(model) if mutant else original_verify(model, name)
with tempfile.TemporaryDirectory() as out, \
     patch.object(scenes.FinalV3Scene, 'from_spec', return_value=scene), \
     patch.object(scenes, 'build_world', return_value=world), \
     patch.object(camera_robot_port, 'CameraRobotPort', return_value=SimpleNamespace(hold=lambda t: None)), \
     patch.object(physics.render_profile, 'audit_model', return_value=audit), \
     patch.object(physics.render_profile, 'verify_model', side_effect=verify), \
     patch.object(physics.PhysicsBackend, 'reset', fake_reset), \
     patch.object(physics.PhysicsBackend, 'advance_to', advance), \
     patch.object(physics.PhysicsBackend, 'capture', lambda self: None), \
     patch.object(physics.PhysicsBackend, 'eval_sample', lambda self: {'pose_gt': 'must not be consumed'}):
    bundle = env.bundle(next(iter(env.registry()['maps'])))
    result = run_case(bundle, Path(out)/'case', seed=911, backend_factory=physics.PhysicsBackend)
    print(json.dumps({'result': result, 'calls': calls}))
"""


@pytest.mark.parametrize("fault", ["shadow", "reflection", "cutoff", "texture", "missing_texture"])
def test_applied_render_failure_becomes_host_error_before_reset(fault):
    result = python_in(candidate(), f"fault={fault!r}\nmutant=False\n" + RENDER_GATE)
    assert result["result"]["status"] == "HOST_ERROR"
    assert result["result"]["protocol_complete"] is False
    assert result["result"]["failure"]["type"] == "RuntimeError"
    assert result["calls"] == ["closed"]


def test_render_enforcement_mutation_is_detected():
    # Mutate verification into receipt-only audit in memory, never source files.
    original = python_in(candidate(), "fault='shadow'\nmutant=False\n" + RENDER_GATE)
    mutant = python_in(candidate(), "fault='shadow'\nmutant=True\n" + RENDER_GATE)
    assert original["result"]["status"] == "HOST_ERROR"
    assert mutant["result"]["status"] == "COLLECTED_UNQUALIFIED"
    # The same acceptance assertion fails on the mutant: gate removal is killed.
    with pytest.raises(AssertionError):
        assert mutant["result"]["status"] == "HOST_ERROR"


@pytest.mark.parametrize("check,cap", [("p01", 30), ("calibration", 120)])
def test_actual_step_guard_max_reset_and_fixed_commands(check, cap):
    result = python_in(candidate(), f"check={check!r}\ncap={cap}\n" + """
import json, tempfile
from pathlib import Path
from types import SimpleNamespace
from harness import zone_final_environment_floor_light as env
from scripts.run_final_environment_checks import run_case
from sim.final_environment_floor_light import PhysicsBackend
from sim.zone_final_v3_scene import cap_world_steps
from tests.test_zone_final_environment_runnable import FakePhysics
owned = []
class Clock(FakePhysics):
    advance_to = PhysicsBackend.advance_to
    set_deadline = PhysicsBackend.set_deadline
    now = PhysicsBackend.now
    def __init__(self, bundle, out, *, seed):
        self.bundle, self.dt, self.ports = bundle, .00025, {}
        self.deadline, self.closed = None, False
        self.actions, self.frames, self.samples = [], [], []
        self.steps = 0
        self.world = SimpleNamespace(data=SimpleNamespace(time=0.),
                                     model=SimpleNamespace(opt=SimpleNamespace(timestep=self.dt)),
                                     robot=lambda rid: rid)
        def step(rid):
            self.steps += 1
            self.world.data.time = self.steps * self.dt
        self.world._physics_step_for = step
        cap_world_steps(self.world, 5.)
        owned.append(self)
    def reset(self, limit):
        assert limit == 5.
        self.set_deadline(limit)
        self.advance_to(limit)
        return self.now
with tempfile.TemporaryDirectory() as out:
    results=[]
    protocol=env.read(env.ROOT/'configs/final_environment_measurement_v1.json')
    for mid in env.registry()['maps']:
        b=env.bundle(mid, check=check)
        result=run_case(b, Path(out)/mid, seed=911, backend_factory=Clock)
        clock=owned[-1]
        assert result['protocol_complete'], result
        assert clock.now == 5 + cap and clock.closed
        assert len(clock.samples) == int(cap/.05)+1
        period = 5 if check == 'p01' else .2
        assert len(clock.frames) == int(cap/period)+1
        expected=[(e['t']+5.,'r1',a) for e in protocol['events'] for a in e['actions']] if check=='calibration' else []
        assert clock.actions == expected
        before=clock.steps
        try: clock.world._physics_step_for('r1')
        except RuntimeError as error: assert str(error) == 'SIM_CAP_EXCEEDED'
        else: raise AssertionError('step crossed cap')
        assert clock.steps == before and clock.now == 5 + cap
        results.append(result)
    print(json.dumps(results))
""")
    assert sum(row["reset_sim_s"] + row["check_sim_s"] for row in result) == 3 * (5 + cap)
    assert all(row["physical_success"] is None and not row["student_control"] for row in result)


@pytest.mark.parametrize("calibration", ["absent", "null_contract", "v2"])
def test_p03_refuses_before_physics_even_with_null_or_v2_calibration(calibration):
    result = python_in(candidate(), f"calibration={calibration!r}\n" + """
import json, tempfile
from pathlib import Path
from unittest.mock import patch
from harness import zone_final_environment_floor_light as env
from scripts import run_final_environment_floor_light as run
sys.modules['sim.final_environment_floor_light'] = None
sys.modules['harness.vision_pose_source_final'] = None
with tempfile.TemporaryDirectory() as temp:
    out=Path(temp)/'must-not-exist'
    args=['--check','p03','--expected-source-sha','a'*40,'--output',str(out),'--execute']
    if calibration != 'absent':
        path=env.ROOT/(env.CALIBRATION if calibration=='null_contract' else 'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json')
        args+=['--calibration',str(path),'--calibration-sha256',env.sha(path)]
    with patch.object(run, 'check_source', return_value='a'*40):
        try: run.main(args)
        except ValueError as error: message=str(error)
        else: raise AssertionError('P03 accepted')
    assert not out.exists()
    print(json.dumps(message))
""")
    expected = "MEASURED_V3_CALIBRATION_REQUIRED" if calibration == "absent" else "FINAL_V3_PAIR_CHAIN_ADAPTER_REQUIRED"
    assert expected in result


def test_gt_labels_are_written_only_under_eval_only_without_provider():
    result = python_in(candidate(), """
import json, tempfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from sim.final_environment_floor_light import PhysicsBackend
sys.modules['harness.vision_pose_source_final'] = None
sys.modules['harness.vision_pose_source_p03'] = None
sys.modules['mujoco'] = SimpleNamespace(
    mj_id2name=lambda *a: 'synthetic_geom',
    mjtObj=SimpleNamespace(mjOBJ_GEOM=1), mjtEq=SimpleNamespace(mjEQ_WELD=2))
sentinel = 987654.321
pose = SimpleNamespace(xpos=np.array([sentinel]*3), xmat=np.eye(3).ravel())
world = SimpleNamespace(
    model=SimpleNamespace(neq=0),
    data=SimpleNamespace(time=5., body=lambda rid: pose, camera=lambda rid: pose,
                         ncon=0, contact=[], eq_active=[]),
    render_rgb=lambda **kw: np.zeros((480,640,3), dtype=np.uint8))
# A fixed zero array is written as a fixture; no renderer or engine exists.
with tempfile.TemporaryDirectory() as temp:
    backend = PhysicsBackend.__new__(PhysicsBackend)
    backend.out, backend.world = Path(temp), world
    backend.frame, backend.streams = 0, {}
    backend.commands = {rid: {6:1500} for rid in ('r1','r2','r3')}
    assert backend.capture() is None
    assert backend.eval_sample() is None
    for stream in backend.streams.values(): stream.close()
    paths = [str(p.relative_to(backend.out)) for p in backend.out.rglob('*') if p.is_file()]
    for relative in paths:
        if relative.endswith('.jsonl'):
            text=(backend.out/relative).read_text()
            if not relative.startswith('eval_only/'):
                assert str(sentinel) not in text and 'base_position_m' not in text
            assert 'MEASURED_SIM' not in text
    labels = [p for p in paths if p.endswith('camera_labels.jsonl')]
    assert len(labels)==3 and all(p.startswith('eval_only/') for p in labels)
    print(json.dumps(paths))
""")
    assert "eval_only/contacts.jsonl" in result
