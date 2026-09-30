"""PR #292 delta review counterexamples. No model construction, steps or render.

Only Path reads are patched; repository source/input bytes remain untouched.
These are admission failures, not claims about measured physical performance.
"""
import importlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from scripts import zone_pair_v6_contract as contract
from scripts import zone_pair_v6h_admission as admission
from scripts.zone_pair_authorization import digest, registration_payload


BUILDER = importlib.import_module('experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h')


def sealed_plan(monkeypatch):
    plan = BUILDER.build()
    plan['sealed'] = True
    plan['registration_sha256'] = digest(registration_payload(plan))
    monkeypatch.setattr(contract, 'CURRENT_REVISION', 'v6h')
    admission.validate_plan(plan)
    return plan


def replace_reads(monkeypatch, path, raw):
    original_text, original_bytes = Path.read_text, Path.read_bytes
    monkeypatch.setattr(Path, 'read_text', lambda self, *a, **k:
                        raw.decode('utf-8') if self == path else original_text(self, *a, **k))
    monkeypatch.setattr(Path, 'read_bytes', lambda self, *a, **k:
                        raw if self == path else original_bytes(self, *a, **k))


def test_sealed_admission_rejects_changed_runtime_dynamics_manifest(monkeypatch):
    from sim import masterpi_dynamics_v2 as dynamics

    plan = sealed_plan(monkeypatch)
    path = contract.ROOT / 'sim/masterpi_dynamics_calibration.json'
    before, _ = dynamics.load_fitted_dynamics()
    data = json.loads(path.read_text())
    data['parameters']['max_forward_force_n'] = 3.3
    replace_reads(monkeypatch, path, json.dumps(data).encode())
    after, _ = dynamics.load_fitted_dynamics()
    assert before.get('max_forward_force_n') != after['max_forward_force_n'] == 3.3
    # The production template loads this default manifest; same seal must reject it.
    with pytest.raises(ValueError, match='sealed.*(source|plan)'):
        admission.validate_plan(plan)


def test_sealed_admission_rejects_changed_canonical_scene_xml(monkeypatch):
    from sim import masterpi_dynamics_v2 as dynamics, render_profile

    plan = sealed_plan(monkeypatch)
    path = contract.ROOT / 'sim/masterpi_scene.xml'
    before = render_profile.apply_xml(dynamics.build_v2_xml(), 'floor_light_v1')
    raw = path.read_bytes()
    assert b'znear=".002"' in raw
    replace_reads(monkeypatch, path, raw.replace(b'znear=".002"', b'znear=".02"'))
    after = render_profile.apply_xml(dynamics.build_v2_xml(), 'floor_light_v1')
    assert before != after and 'znear=".02"' in after
    # XML string generation only: never instantiate a MuJoCo model or renderer.
    with pytest.raises(ValueError, match='sealed.*(source|plan)'):
        admission.validate_plan(plan)


@pytest.mark.parametrize('source', [
    'maps/zones/zone_wide_door.json',
    'maps/zones/zone_wide_door_geometry_v2.json',
    'maps/zones/zone_wide_door_tags_v2.json',
    'maps/zones/zone_wide_door_tags_v2_dock_v3.json',
    'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json',
    'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json',
    'experiments/2026-09-29-pair-v6e-carry/carry_dr_fit_cal1.json',
    'experiments/2026-09-29-pair-v6e-carry/carry_pair_fit.json',
    'experiments/2026-09-29-pair-v6e-carry/carry_general_fit.json',
    'experiments/2026-09-29-pair-v6e-carry/hR2_samples.json',
    'sim/masterpi_camera_profile.py',
    'sim/render_profile.py',
    'harness/wrist_zone_skill_v7.py',
    'harness/wrist_zone_skill_v8.py',
    'harness/wrist_zone_skill_v9.py',
])
def test_sealed_admission_rejects_changed_runtime_input_bytes(monkeypatch, source):
    plan = sealed_plan(monkeypatch)
    assert source in plan['v6_contract']['source_sha256']
    path = contract.ROOT / source
    # Valid trailing whitespace isolates the byte pin, not parser/semantic checks.
    replace_reads(monkeypatch, path, path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='sealed.*source'):
        admission.validate_plan(plan)


@pytest.mark.parametrize('source', ['sim/masterpi_dynamics_calibration.json', 'sim/masterpi_scene.xml'])
def test_sealed_admission_rejects_missing_runtime_input(monkeypatch, source):
    plan = sealed_plan(monkeypatch)
    path = contract.ROOT / source
    original = Path.read_bytes

    def missing(file, *args, **kwargs):
        if file == path:
            raise FileNotFoundError(path)
        return original(file, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_bytes', missing)
    # In particular, the dynamics loader's fallback must not bypass admission.
    with pytest.raises(FileNotFoundError):
        admission.validate_plan(plan)


def test_chain_scene_maps_and_inline_mjcf_assets_are_covered():
    from scripts.zone_pair_dev_runtime import make_scene
    from sim.masterpi_dynamics_v2 import SCENE_PATH
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim import render_profile
    from sim.zone_cargo_contact import apply
    from sim.zone_start_dock import MAP_ID

    plan = BUILDER.build()
    scene = make_scene({'map': MAP_ID, 'seed': 941, 'goal': {'B': {'cyan': 1}},
                        'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam',
                                        'pose': plan['cases'][0]['beam_xyyaw']}]})
    pins = plan['v6_contract']['source_sha256']
    for source in scene.sources:
        assert Path(source).relative_to(contract.ROOT).as_posix() in pins
    render_profile.install(scene, 'floor_light_v1')
    # Pure XML transforms only: no model compilation, rendering or stepping.
    final_xml = apply(scene.transform(build_multi_robot_xml()), 'cargo_noslip_v1')
    for xml in (SCENE_PATH.read_text(), final_xml):
        for node in ET.fromstring(xml).iter():
            assert node.tag != 'include', 'new MJCF includes require explicit transitive input pins'
            assert not any(key.startswith('file') for key in node.attrib), \
                'new file-backed MJCF assets require explicit input pins'
