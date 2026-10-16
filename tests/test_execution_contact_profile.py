"""Noslip default/replay boundary: compile models only, never integrate/render."""
import hashlib
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import xml.etree.ElementTree as ET

import pytest
from sim import execution_contact_profile as policy

ROOT = Path(__file__).resolve().parents[1]


def test_vendor_bytes_and_legacy_profile_are_preserved():
    from sim.zone_cargo_contact import CARGO_PROFILES
    assert hashlib.sha256((ROOT/'sim/warp_native_contact.py').read_bytes()).hexdigest() == 'a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a'
    assert CARGO_PROFILES['cargo_noslip_v1']['option'] == {'noslip_iterations': '10'}
    xml = '<mujoco><option noslip_iterations="10"/></mujoco>\n'
    assert policy.apply_xml(xml, policy.LEGACY) == xml


@pytest.mark.parametrize('profile', [policy.CPU_DEFAULT, policy.WARP_DEFAULT, policy.LEGACY])
def test_actual_model_load_and_profile_validation(profile, monkeypatch):
    mujoco = pytest.importorskip('mujoco')
    def denied(*a, **kw):raise AssertionError('physics/render forbidden')
    for name in ('mj_step', 'mj_forward', 'Renderer'):
        monkeypatch.setattr(mujoco, name, denied)
    xml = '<mujoco><option noslip_iterations="10"/><worldbody><geom type="plane" size="1 1 .1"/></worldbody></mujoco>'
    m = mujoco.MjModel.from_xml_string(policy.apply_xml(xml, profile))
    policy.assert_model_profile(m, profile)
    if profile != policy.LEGACY:
        assert (int(m.opt.noslip_iterations), int(m.opt.cone), int(m.opt.integrator), m.opt.impratio) == (0, 1, 3, 5.)
        assert (int(m.opt.solver), m.opt.iterations, m.opt.ls_iterations) == (2, 80, 50)
    with pytest.raises(ValueError, match='weld'):
        policy.assert_model_profile(m, profile, [True])
    m.opt.noslip_iterations = 0 if profile == policy.LEGACY else 10
    with pytest.raises(ValueError, match='expected noslip'):
        policy.assert_model_profile(m, profile)


@pytest.mark.parametrize('module', ['masterpi_drive_friction', 'masterpi_drive_friction_v2',
    'masterpi_drive_friction_v3','masterpi_drive_friction_v4','masterpi_drive_friction_v5',
    'masterpi_drive_friction_v5_hard','masterpi_drive_friction_v6','masterpi_drive_friction_v7'])
def test_drive_builder_defaults_before_constructor_steps(module, monkeypatch):
    pytest.importorskip('mujoco')
    factory = importlib.import_module('sim.'+module)
    assert inspect.signature(factory.build_world).parameters['contact_profile'].default == policy.CPU_DEFAULT


def test_frozen_builder_override_is_before_construction_and_scoped():
    from sim import zone_cargo_contact as cargo
    original = cargo.apply
    # Mirrors a frozen builder which has no contact_profile parameter.
    def frozen():
        xml = cargo.apply('<mujoco><option/><equality/></mujoco>', 'cargo_noslip_v1')
        return int(ET.fromstring(xml).find('option').get('noslip_iterations'))
    assert policy.build_world_with_contact(frozen, policy.WARP_DEFAULT) == 0
    assert cargo.apply is original
    assert policy.build_world_with_contact(frozen, policy.LEGACY) == 10
    def failure():
        assert cargo.apply is not original
        raise RuntimeError('construction failed')
    with pytest.raises(RuntimeError):policy.build_world_with_contact(failure, policy.WARP_DEFAULT)
    assert cargo.apply is original


def test_frozen_builder_legacy_overrides_a_current_native_default():
    from sim import zone_cargo_contact as cargo
    def builder():
        return cargo.apply('<mujoco><option/><equality/></mujoco>', policy.CPU_DEFAULT)
    xml = policy.build_world_with_contact(builder, policy.LEGACY)
    assert ET.fromstring(xml).find('option').get('noslip_iterations') == '10'


def test_batch_parsers_default_native_and_accept_explicit_replay():
    from scripts.run_warp_act_teacher import parser as solo
    from scripts.run_warp_flow_teacher import parser as pair
    for parser in (solo, pair):
        p = parser()
        assert p.get_default('contact_profile') == policy.WARP_DEFAULT
        assert policy.LEGACY in next(a.choices for a in p._actions if a.dest == 'contact_profile')


def test_loaded_external_xml_diagnostic_native_override():
    mujoco = pytest.importorskip('mujoco')
    m = mujoco.MjModel.from_xml_string('<mujoco><option noslip_iterations="10"/></mujoco>')
    policy.configure_model(m)
    assert (m.opt.noslip_iterations, m.opt.cone, m.opt.integrator, m.opt.impratio) == (0,1,3,5.)


def test_live_contracts_default_native_without_rewriting_registries():
    for module in ('zone_final_pair_contract', 'pair_llm_contract',
                   'zone_solo_cyan_contract_v106', 'zone_s3_contract', 'zone_s3_door_contract'):
        factory = importlib.import_module('harness.'+module)
        assert inspect.signature(factory.bundle).parameters['contact_profile'].default == policy.CPU_DEFAULT
    assert policy.cargo_name(policy.LEGACY) == 'cargo_noslip_v1'
