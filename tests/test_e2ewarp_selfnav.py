import ast
import json
import pathlib
import types

import pytest

from harness import e2ewarp_selfnav as sn
from harness.grasp_act_contract import SERVOS

ROOT = pathlib.Path(__file__).resolve().parents[1]


def frame(sim_s=0.0, jpeg=b'jpg'):
    return types.SimpleNamespace(robot_id='r1', world_id=0, tick=int(sim_s * 10), sim_s=sim_s, jpeg=jpeg, issued=())


def test_default_off_fails_closed():
    nav = sn.navigation_factory('r1', {'orders': [{'id': 'o'}]})
    rep = nav.observe(frame(1.0))
    assert rep['map_correction_active'] is False
    assert rep['destination_arrived'] is False
    assert nav.accept_release_fix({'relocalized': True, 'memory_registered': True}) is False
    cmd = nav.command(1.0)
    assert cmd['wheels'] == [0.0, 0.0, 0.0, 0.0] and cmd['duration_s'] == [0.0, 0.0, 0.0, 0.0]
    assert set(cmd) == {'t', 'wheels', 'duration_s', 'pwm'} and set(cmd['pwm']) == {str(i) for i in SERVOS}
    assert all(isinstance(v, int) and 500 <= v <= 2500 for v in cmd['pwm'].values())


def test_no_static_map_geometry_allowed():
    with pytest.raises(ValueError, match='static map input is forbidden'):
        sn.navigation_factory('r1', {'orders': [], 'walls': [], 'zones': {}})
    assert sn.order_sheet({'orders': [], 'mission': {'destination_zone': 'B'}})['mission']['destination_zone'] == 'B'


def test_memory_updates_and_decays():
    dets = [{'kind': 'zone_B', 'range_m': 1.2, 'bearing_deg': 5.0}]
    nav = sn.navigation_factory('r1', {}, option=sn.OPTION, detector=lambda fr: dets)
    rep = nav.observe(frame(0.0))
    assert rep['evidence_revision'] == 1 and rep['self_centric_memory'][0]['kind'] == 'zone_B'
    rep = nav.observe(frame(2.0))
    assert rep['self_centric_memory'][0]['uncertainty_m'] > 0.5  # decayed before re-observation


def test_arrival_and_handoff_are_own_memory_evidence():
    dets = [{'kind': 'zone_B', 'range_m': 0.2, 'bearing_deg': 0.0}]
    nav = sn.navigation_factory('r2', {}, option=sn.OPTION, detector=lambda fr: dets)
    rep = nav.observe(frame(3.0))
    assert rep['destination_arrived'] is True and rep['robot_id'] == 'r2'


def test_abi_and_channel_isolation():
    nav = sn.navigation_factory('r1', {'orders': [{'id': 'o1'}, {'id': 'o2'}]}, option=sn.OPTION)
    assert {c['id'] for c in nav.task_candidates(['o1'])} == {'o2'}
    nav.start({'skill': 'carry_page'}, phase='carry')
    assert nav.phase == 'carry'
    nav.on_messages([{'from': 'r2', 'text': 'ready'}])
    assert nav._messages[-1]['from'] == 'r2'
    assert nav.confirm_act(frame(), 'grasp') is False
    assert nav.accept_release_fix({'relocalized': True, 'memory_registered': True, 'truth_inputs': 0, 'held_world_reads': 0}) is True


def test_two_robot_only():
    with pytest.raises(ValueError):
        sn.navigation_factory('r3', {})


def test_no_simulator_or_gt_imports_or_access():
    src = (ROOT / 'harness/e2ewarp_selfnav.py').read_text()
    tree = ast.parse(src)
    imports = set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split('.')[0])
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    forbidden = {'mujoco', 'mujoco_warp', 'warp', 'sim', 'torch'}
    assert not (imports & forbidden)
    # No ground-truth/evaluator/top-camera accessors in executable code.
    for token in ('ground_truth', 'gt_pose', 'evaluator', 'top_camera', 'truth'):
        assert token not in names


def test_contract_scenario_is_two_robot_without_static_map():
    scenario = json.loads((ROOT / 'configs/e2ewarp/contract_v1_two_robot_scenario.json').read_text())
    assert scenario['robots'] == ['r1', 'r2']
    assert scenario['static_map_input'] is False
    assert scenario['mission']['robots_required'] == 2
    assert scenario['physics']['backend'] == 'mjwarp_batch_v1' and scenario['physics']['noslip_iterations'] == 0
    assert scenario['language_conditions'] == ['no_comm', 'peer_en', 'leader_en', 'structured']
