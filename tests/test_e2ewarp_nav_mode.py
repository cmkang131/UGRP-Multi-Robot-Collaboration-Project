"""Nav-only two-robot mode gate. No mujoco/warp/GPU imports or renders.

Covers the opt-in CLI mode, the two-robot/leader contract, navigation-only
component admission, r3 rejection and the static-map exclusion. The default
smoke/mission paths are asserted unchanged by the same tests.
"""
import hashlib
import json
from pathlib import Path

import pytest

from harness import e2ewarp_nav_mode as nav
from harness.e2e_warp_components import (NAV_REQUIRED, REQUIRED, require_components,
                                         require_navigation)
from harness.e2e_warp_runtime import Channels, OwnFrame, Planner, encode
from harness.zone_study_contract import ContractViolation
from scripts import run_e2e_warp as runner

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / 'configs/e2ewarp/contract_v1_two_robot_scenario.json'
PWM = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}


def frame(robot='r1'):
    return OwnFrame(robot, 0, 0, 0., b'own-image', ())


def hold(now):
    return dict(t=float(now), wheels=[0.] * 4, duration_s=[0.] * 4, pwm=dict(PWM))


class FakeNavigation:
    """Owner-supplied adapter stand-in: navigation ABI only, no simulator."""

    def __init__(self, robot_id, static=None):
        self.robot_id, self.static = robot_id, static
        self.arrived = False
        self.messages = []
        self.instructions = []

    def observe(self, current):
        assert current.robot_id == self.robot_id
        return dict(destination_arrived=self.arrived, evidence_revision=1,
                    map_correction_active=False)

    def task_candidates(self, completed):
        return [dict(id='pair_carry_1', skill='navigate',
                     order={'id': 'pair_carry_1', 'required_robots': 2})]

    def start(self, instruction, phase='navigate'):
        self.instructions.append((instruction, phase))

    def command(self, now):
        return hold(now)

    def on_messages(self, rows):
        self.messages.extend(rows)


def nav_manifest(tmp_path):
    """Minimal nav manifest: navigation ready, factory hash-bound, nothing else."""
    adapter = tmp_path / 'fakenav.py'
    adapter.write_text('def navigation_factory(robot_id, static=None):\n    return None\n')
    value = dict(
        schema='ugrp.e2ewarp.components.v1',
        navigation=dict(ready=True, owner='mapbuild8', evidence='nav-gate unit test'),
        navigation_factory=dict(entry='fakenav:navigation_factory',
                                sha256=hashlib.sha256(adapter.read_bytes()).hexdigest()))
    return value, tmp_path


def test_default_mode_is_unchanged():
    parser = runner.build_parser()
    default = parser.parse_args(['--output', 'unused'])
    assert default.mode == 'smoke'
    assert default.seed == 601 and default.nworld == 1 and default.condition == 'no_comm'
    assert parser.parse_args(['--mode', 'mission', '--output', 'unused']).mode == 'mission'

    # Default invocation still starts no execution and advertises no nav mode.
    assert runner.main(['--output', 'unused']) == 0
    # Full mission admission (all five components) is untouched.
    assert REQUIRED == ('navigation', 'loaded_camera_fk', 'static_map_registration',
                        'selfmap_map_correction', 'release_relocalization')
    with pytest.raises(ValueError, match='DEPENDENCY_WAIT'):
        require_components(None, ROOT)
    # The default leader rotation is still seed % 3 over the three study robots.
    assert Channels('leader_en', 601).leader == 'r2'
    assert Channels('leader_en', 601).robots == runner.ROBOTS == ('r1', 'r2', 'r3')


def test_nav_mode_requires_only_navigation_and_two_robots(tmp_path):
    manifest, root = nav_manifest(tmp_path)
    (tmp_path / 'components.json').write_text(json.dumps(manifest))
    assert require_navigation(tmp_path / 'components.json', root)['navigation']['ready'] is True
    assert NAV_REQUIRED == ('navigation',) == nav.REQUIRED
    assert nav.ROBOTS == ('r1', 'r2')
    assert [nav.leader_for_seed(seed) for seed in (0, 1, 601, 602)] == ['r1', 'r2', 'r2', 'r1']

    assert runner.build_parser().parse_args(['--mode', 'nav', '--output', 'unused']).mode == 'nav'
    fields = nav.queue_fields(601)
    assert fields['nav_only'] is True and fields['robots'] == ['r1', 'r2']
    assert fields['leader_id'] == 'r2' and fields['static_map_input'] is False
    assert fields['component_requirements'] == ['navigation']
    assert nav.validate_queue(fields, 601) is fields

    scenario = json.loads(SCENARIO.read_text())
    assert tuple(scenario['robots']) == nav.ROBOTS
    assert scenario['static_map_input'] is False
    assert scenario['mission']['robots_required'] == 2


def test_nav_mode_rejects_r3(tmp_path):
    manifest, root = nav_manifest(tmp_path)
    with pytest.raises(ValueError, match='two-robot'):
        nav.NavRobot('r3', {}, manifest)
    with pytest.raises(ValueError, match='two-robot'):
        nav.NavigationOnlyController('r3', {}, FakeNavigation('r3'))
    assert all(nav.leader_for_seed(seed) != 'r3' for seed in range(-6, 6))

    # The default three-robot channel still accepts r3...
    default = Channels('peer_en', 601)
    default.send('r1', dict(recipients=['r3'], body={'text': '기다려'}), now=0.)
    # ...but a nav-mode channel fails closed before message validation.
    channel = Channels('peer_en', 601, robots=nav.ROBOTS)
    with pytest.raises(ContractViolation):
        channel.send('r1', dict(recipients=['r3'], body={'text': '기다려'}), now=0.)
    with pytest.raises(ContractViolation):
        channel.send('r3', dict(recipients=['r1'], body={'text': '기다려'}), now=0.)
    with pytest.raises(ContractViolation):
        channel.inbox('r3')

    tampered = dict(nav.queue_fields(601), robots=['r1', 'r3'])
    with pytest.raises(ValueError, match='NAV_ROBOTS_REQUIRED'):
        nav.validate_queue(tampered, 601)


def test_static_map_key_is_never_passed_in_nav_mode(tmp_path):
    orders = [dict(id='pair_carry_1', kind='long_beam', required_robots=2, destination_zone='B')]
    with pytest.raises(ValueError, match='static_map'):
        nav.nav_static(dict(orders=orders, condition='no_comm', static_map={'map_id': 'x'}))
    metadata = nav.nav_static(dict(orders=orders, condition='no_comm', robot_count=2))
    assert list(metadata) == ['orders', 'condition', 'robot_count']
    assert nav.nav_static(None) == {}

    # The LLM prompt carries only the stripped order/condition metadata.
    planner = Planner('http://127.0.0.1:1', tmp_path / 'llm', metadata,
                      run_id='nav-gate-test', world_id=0, robot='r1')
    prompt = planner.body(frame(), {'sim_s': 0.})['messages'][1]['content']
    assert prompt == encode(metadata)
    assert 'static_map' not in prompt

    # The navigation adapter receives exactly the same stripped metadata.
    manifest, root = nav_manifest(tmp_path)
    observed = {}

    def build(robot_id, static=None):
        observed['static'] = static
        return FakeNavigation(robot_id, static)

    robot = nav.NavRobot('r1', metadata, manifest, navigation_factory=build)
    assert observed['static'] == metadata
    assert robot.component.static == metadata
    assert 'static_map' not in robot.component.static
    issued = robot.command(0.)
    assert issued['wheels'] == [0.] * 4 and set(issued['pwm']) == set(PWM)


def test_nav_result_fails_closed_without_an_evaluator(tmp_path):
    fields = nav.fail_closed_result_fields()
    assert fields['E2E_success'] is False
    assert fields['research_result'] is False
    assert fields['physical_success_available'] is False
    assert fields['success_claim'] == 'not_available' and fields['success_evidence'] is None

    adapter = FakeNavigation('r1')
    adapter.arrived = True
    controller = nav.NavigationOnlyController('r1', None, adapter)
    controller.select({'id': 'pair_carry_1'}, 0.)
    report = controller.observe(frame())
    assert controller.phase == 'ARRIVED'
    assert controller.complete is False
    assert report['arrival_claim_verified'] is False
    assert report['physical_success_available'] is False
