"""PR #292 delta review counterexamples. No model construction, steps or render.

Only Path reads are patched; repository source/input bytes remain untouched.
These are admission failures, not claims about measured physical performance.
"""
import importlib
import json
from pathlib import Path

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


@pytest.mark.xfail(strict=True, raises=pytest.fail.Exception,
                   reason='R292-D1: runtime dynamics calibration JSON is outside the 268 source pins')
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


@pytest.mark.xfail(strict=True, raises=pytest.fail.Exception,
                   reason='R292-D1: runtime masterpi_scene.xml is outside the 268 source pins')
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
