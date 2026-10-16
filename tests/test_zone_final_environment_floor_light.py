"""v87 fake/offline checks, including v84 byte preservation; no native imports."""
import copy
import hashlib
import json
import socket
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from harness import zone_final_environment as old
from harness import zone_final_environment_floor_light as env
from scripts import run_final_environment_checks as old_run
from scripts import run_final_environment_floor_light as run
from sim import workflow_manager as wm
from tests.test_zone_final_environment_runnable import FakePhysics

MAPS = tuple(old.registry()['maps'])
RECORD = 'experiments/2026-10-01-final-env-floor-light/v84_preservation.json'


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for module in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, module, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    from harness.vision_loc_client import VisionWorkerClient
    monkeypatch.setattr(VisionWorkerClient, '__init__', lambda *a, **k: pytest.fail('worker forbidden'))


def test_v84_history_and_explicit_v6h_successors_keep_their_own_receipts():
    from tests.v6h_successor_pins import SEAL, successor_blob
    from tests.pinned_source_bundle import bundle_at
    record = env.read(env.ROOT / RECORD)
    # #292's already-reviewed source/test migrations are separate from v84.
    # Do not rewrite its receipt or claim current bundle bytes are the old run.
    successors = {
        'harness/owncam_carry_v6e.py': SEAL,
        'harness/zone_own_guards.py': SEAL,
        'tests/test_zone_pair_registered_source.py': '9e13c76b0ead36ace257e05cab7cb5e60d42df72',
        'tests/test_zone_study_source_pinning.py': '9e13c76b0ead36ace257e05cab7cb5e60d42df72',
    }
    assert successors.keys() <= record['files_sha256'].keys()
    for path, sha in record['files_sha256'].items():
        original = subprocess.check_output(['git', 'show', f'{record["source_sha"]}:{path}'], cwd=env.ROOT)
        assert hashlib.sha256(original).hexdigest() == sha, path
        expected = (subprocess.check_output(['git', 'show', f'{successors[path]}:{path}'], cwd=env.ROOT)
                    if path in successors else original)
        # Historical records pin their acquisition source. Current shared
        # runners legitimately change; new-bundle tests below cover them.
        actual = (successor_blob(path) if successors.get(path) == SEAL else
                  subprocess.check_output(['git', 'show', f'{successors.get(path, record["source_sha"])}:{path}'], cwd=env.ROOT))
        assert actual == expected, path
    for key, sha in record['bundles'].items():
        mid, check = key.split('/')
        current = old.bundle(mid, check=check)
        assert env.digest(current) != sha, 'a successor must not inherit the historical bundle identity'
        historical = bundle_at(record['source_sha'], old.__name__, mid, check,
                               tuple(record['files_sha256']))
        assert historical['source_sha256'].keys() <= record['files_sha256'].keys()
        # All non-source bundle fields and the source closure remain exact;
        # only substitute the independently checked historical Git hashes.
        historical['source_sha256'] = {path: record['files_sha256'][path]
                                       for path in historical['source_sha256']}
        assert env.digest(historical) == sha, key


@pytest.mark.parametrize('mid', MAPS)
@pytest.mark.parametrize('check', ['p01', 'calibration', 'p03'])
def test_v87_only_changes_render_and_version_provenance(mid, check):
    before = old.bundle(mid, check=check)
    after = env.bundle(mid, check=check)
    assert after['execution_bundle_id'] == 'zone-final-environment-v87'
    assert after['render_profile'] == 'floor_light_v1'
    assert after['runnable'] == (check != 'p03')
    assert not after['physical_ready'] and not after['research_result']
    assert after['controller_inputs'] == ['own_rgb', 'static_map', 'own_command_history', 'delivered_messages']
    assert after['parent_bundle_sha256'] == env.digest(before)
    contract = copy.deepcopy(after['calibration_contract'])
    assert contract.pop('render_profile') == 'floor_light_v1'
    assert contract == {k: v for k, v in before['calibration_contract'].items() if k != 'render_profile'}
    changes = {k for k in before if before[k] != after[k]}
    assert changes == {'schema', 'execution_bundle_id', 'render_profile', 'calibration_contract', 'source_sha256'}
    assert {'sim/render_profile.py', env.REGISTRY, env.WORKFLOW, env.CALIBRATION,
            'sim/final_environment_floor_light.py', 'scripts/run_final_environment_floor_light.py',
            'configs/final_environment_measurement_v1.json'} <= after['source_sha256'].keys()
    assert before['source_sha256'].items() <= after['source_sha256'].items()


@pytest.mark.parametrize('target', ['render', 'physics', 'cap', 'calibration'])
def test_changed_contract_rejected(tmp_path, target):
    for path in env.bundle(MAPS[0])['source_sha256']:
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((env.ROOT / path).read_bytes())
    reg = env.read(tmp_path / env.REGISTRY)
    if target == 'render':
        reg['render_profile'] = 'default'
    elif target == 'physics':
        reg['contact_profile'] = 'local_contact_fine'
    elif target == 'cap':
        reg['checks']['calibration']['per_case_sim_cap_s'] = 121
    else:
        path = tmp_path / env.CALIBRATION
        cal = env.read(path)
        cal['render_profile'] = 'default'
        run.write(path, cal)
        for row in reg['maps'].values():
            row['calibration_contract_sha256'] = env.sha(path)
    run.write(tmp_path / env.REGISTRY, reg)
    with pytest.raises(ValueError, match='differs'):
        env.resolve(MAPS[0], root=tmp_path)


def test_both_workflows_discoverable_new_plan_and_ci_collection(capsys, tmp_path):
    from scripts.run_ci_tests import collect_test_files, TEST_PATTERNS
    path = 'tests/test_zone_final_environment_floor_light.py'
    assert collect_test_files(env.ROOT, TEST_PATTERNS).count(path) == 1
    assert wm._row(env.ROOT, 'zone-final-environment-check')[0]['version'] == '2.17.0'
    row, _ = wm._row(env.ROOT, 'zone-final-environment-floor-light-check')
    assert row['version'] == '2.20.0'
    plan = wm.plan(env.ROOT, row['id'], ['--check', 'calibration', '--expected-source-sha', 'a' * 40])
    assert plan['command'][1:3] == ['-m', 'scripts.run_final_environment_floor_light']
    assert not plan['execution_started']
    for check, cap in [('p01', 90), ('calibration', 360), ('p03', 360)]:
        run.main(['--check', check, '--expected-source-sha', 'a' * 40, '--output', str(tmp_path / check)])
        value = json.loads(capsys.readouterr().out)
        assert value['execution_bundle_id'] == env.BUNDLE_ID and value['render_profile'] == 'floor_light_v1'
        assert value['caps']['total_sim_cap_s'] == cap and not value['execution_started']
        assert value['runnable'] == (check != 'p03')
        assert not (tmp_path / check).exists()


@pytest.mark.parametrize('check,cap', [('p01', 30), ('calibration', 120)])
@pytest.mark.parametrize('failure', [False, True])
def test_three_map_cli_schedule_caps_failure_and_no_overwrite(monkeypatch, tmp_path, check, cap, failure):
    from scripts import agent_lock
    from sim import final_environment_floor_light as physics
    owned = []

    class Backend(FakePhysics):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            owned.append(self)
        def capture(self):
            if failure:
                raise OSError(28, 'synthetic full disk')
            super().capture()

    def git(argv, **kw):
        if argv == ['git', 'rev-parse', '--path-format=absolute', '--git-common-dir']:
            return str(tmp_path / '.git')
        if argv == ['git', 'branch', '--show-current']:
            return 'codex/fake-v87'
        pytest.fail(str(argv))
    monkeypatch.setattr(run, 'check_source', lambda sha: sha)
    monkeypatch.setattr(run.subprocess, 'check_output', git)
    monkeypatch.setattr(run.shutil, 'disk_usage', lambda path: SimpleNamespace(free=20 * 1024 ** 3))
    monkeypatch.setattr(agent_lock, 'status', lambda path: {'pid_alive': True, 'owner': 'codex', 'branch': 'codex/fake-v87'})
    monkeypatch.setattr(physics, 'PhysicsBackend', Backend)
    out = tmp_path / 'outputs' / check
    argv = ['--check', check, '--expected-source-sha', 'a' * 40, '--output', str(out), '--execute', '--lock-owner', 'codex']
    assert run.main(argv) == int(failure)
    result = env.read(out / 'result.json')
    assert result['denominator'] == 3 and result['physical_success'] is None and result['source_unchanged']
    assert len(owned) == len(result['cases']) == (1 if failure else 3)
    assert result['unattempted'] == (list(MAPS[1:]) if failure else [])
    assert all(b.closed for b in owned)
    assert run.run_case is old_run.run_case
    for b in owned:
        assert b.bundle['render_profile'] == 'floor_light_v1'
        if not failure:
            assert b.now == 1 + cap and b.frames[-1] == b.now
            protocol = env.read(env.ROOT / 'configs/final_environment_measurement_v1.json')
            expected = [(e['t'] + 1, 'r1', a) for e in protocol['events'] for a in e['actions']] if check == 'calibration' else []
            assert b.actions == expected  # eval_sample returns malicious truth; ignored
    if not failure:
        assert sum(c['check_sim_s'] for c in result['cases']) == 3 * cap
        assert sum(c['check_sim_s'] + c['reset_sim_s'] for c in result['cases']) <= 3 * (cap + 5)
    saved = (out / 'result.json').read_bytes()
    with pytest.raises(FileExistsError):
        run.main(argv)
    assert (out / 'result.json').read_bytes() == saved


@pytest.mark.parametrize('has_calibration', [False, True])
def test_p03_never_imports_physics_or_creates_output(monkeypatch, tmp_path, has_calibration):
    monkeypatch.setattr(run, 'check_source', lambda sha: sha)
    monkeypatch.setitem(sys.modules, 'sim.final_environment_floor_light', None)
    args = ['--check', 'p03', '--expected-source-sha', 'a' * 40, '--output', str(tmp_path / 'p03'), '--execute']
    if has_calibration:
        args += ['--calibration', '/not/a/qualified/calibration.json', '--calibration-sha256', 'b' * 64]
    with pytest.raises(ValueError, match='FINAL_V3_PAIR_CHAIN_ADAPTER_REQUIRED' if has_calibration else 'MEASURED_V3_CALIBRATION_REQUIRED'):
        run.main(args)
    assert not (tmp_path / 'p03').exists()


@pytest.mark.parametrize('reject_audit', [False, True])
def test_backend_installs_profile_before_world_audits_and_records_receipt(monkeypatch, tmp_path, reject_audit):
    from sim import final_environment_floor_light as physics, zone_final_v3_scene as scenes
    from sim import camera_robot_port
    xml = '<mujoco><asset><texture name="ground" rgb1=".2 .22 .24" rgb2=".27 .29 .31"/><material reflectance=".035"/></asset><worldbody><light castshadow="true" cutoff="45"/><camera fovy="42.19"/></worldbody></mujoco>'
    scene = SimpleNamespace(manifest={}, transform=lambda source: source, engine_layout='fixed')
    monkeypatch.setattr(scenes.FinalV3Scene, 'from_spec', lambda spec, profile: scene)
    calls = []
    world = SimpleNamespace(model=SimpleNamespace(opt=SimpleNamespace(timestep=.00025)),
                            data=SimpleNamespace(time=0), close=lambda: calls.append('closed'))
    def build(scene, profile, **kwargs):
        assert profile == 'cargo_noslip_v1'
        assert kwargs['width'] == 640 and kwargs['height'] == 480 and kwargs['render'] is True
        transformed = ET.fromstring(scene.transform(xml))
        assert transformed.find('.//light').get('castshadow') == 'false'
        assert transformed.find('.//light').get('cutoff') == '180'
        assert transformed.find('.//texture').get('rgb1') == '.36 .35 .34'
        assert transformed.find('.//camera').get('fovy') == '42.19'
        calls.append('built')
        return world
    monkeypatch.setattr(scenes, 'build_world', build)
    audit = {'light_castshadow': [0], 'materials_with_reflectance': {}, 'light_cutoff': [180.], 'ground_texture_mean_rgb': [125., 122., 118.]}
    def inspect(model):
        assert model is world.model
        calls.append('audited')
        return {**audit, 'light_castshadow': [1]} if reject_audit else audit
    monkeypatch.setattr(physics.render_profile, 'audit_model', inspect)
    monkeypatch.setattr(camera_robot_port, 'CameraRobotPort', lambda *a, **kw: SimpleNamespace(hold=lambda t: None))
    if reject_audit:
        with pytest.raises(RuntimeError, match='shadows/reflections'):
            physics.PhysicsBackend(env.bundle(MAPS[0]), tmp_path, seed=911)
        assert calls == ['built', 'audited', 'closed']
        return
    backend = physics.PhysicsBackend(env.bundle(MAPS[0]), tmp_path, seed=911)
    def reset(self, cap):
        assert cap == 5
        run.write(tmp_path / 'eval_only/applied.json', {'scene_xml_sha256': 'unchanged'})
        return 1.3
    monkeypatch.setattr(physics.PreviousBackend, 'reset', reset)
    assert backend.reset(5) == 1.3
    applied = env.read(tmp_path / 'eval_only/applied.json')
    assert applied['render_profile']['name'] == 'floor_light_v1'
    assert applied['render_profile_applied'] == audit
    assert scene.manifest['render_profile']['name'] == 'floor_light_v1'
    backend.close()
    assert calls == ['built', 'audited', 'closed']
