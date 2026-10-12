"""Merge-train counterexamples; real command estimator, no simulation or model."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.e2e_runtime_registration import ASSETS, BUNDLE_ID, OPTION, require_current
from scripts.run_e2e_ownmap_live import ROOT, bundle, run


def candidate(**kwargs):
    return bundle('a'*40, 61001, 'study_gemma4_31b_v1', enabled=True,
                  mapping_budget='case_cap_v1', runtime_registration=OPTION, **kwargs)


def test_historical_ids_and_default_off_are_preserved_but_require_original_checkout():
    old = bundle('a'*40, 61001, 'study_gemma4_31b_v1', enabled=True, mapping_budget='case_cap_v1')
    assert old['execution_bundle_id'] == 'e2e-stall-budget-v199'
    assert old['e2e_options']['pulse_budget'] == 'fractional_duration_v1'
    assert 'runtime_registration' not in old['e2e_options']
    with pytest.raises(ValueError, match='ORIGINAL_CHECKOUT_OR_REVIEWED_RUNTIME'):
        run(old, None, None)
    new = candidate()
    assert new['execution_bundle_id'] == BUNDLE_ID
    assert new['parent_execution_bundle_id'] == old['execution_bundle_id']
    assert new['inherited_results'] is False
    assert new['e2e_options']['pulse_budget'] == 'off'
    require_current(new, ROOT)


def test_goal_selection_and_other_data_are_hashed_and_verified_before_runtime(tmp_path):
    b = candidate()
    for name in ASSETS:
        target = tmp_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
    require_current(b, tmp_path)
    name = ASSETS[0]
    selection = json.loads((tmp_path/name).read_text())
    selection['selected']['options']['min_pixels'] *= 2
    (tmp_path/name).write_text(json.dumps(selection))
    with pytest.raises(ValueError, match='SOURCE_HASH_MISMATCH:'+name):
        require_current(b, tmp_path)
    missing = copy.deepcopy(b)
    missing['source_sha256'].pop(name)
    with pytest.raises(ValueError, match='SOURCE_HASH_MISMATCH'):
        require_current(missing, ROOT)


def test_point_1518m_transport_queue_reaches_each_real_robot_command_estimator():
    from harness.e2e_live_mapping import Robot
    from harness.e2e_live_transport import Transport
    from harness.s4_event_policy import Options
    from tests.test_s3_coarse_fine import profiles
    covariance = json.loads((ROOT/'configs/e2e_nees_egomap70_dev_v1.json').read_text())
    robots = {rid: Robot(rid, 61001+i, covariance, Options()) for i,rid in enumerate(('r1','r2'))}
    for robot in robots.values():
        robot.commanded(dict(kind='arm',servo_id=1,pulse=1500), 0.)
    key = ('order-5', 'a'*64, 1, 0)
    gate = SimpleNamespace(key=key, allowed=lambda actual,t: actual==key)
    transport = Transport(robots, gate, profiles(), pulse_budget=candidate()['e2e_options']['pulse_budget'])
    transport.plan = dict(route=[[0.,0.],[.1518,0.]], agreement_route_hash='a'*64,
                          own_route={'legs':[{'distance_m':.1518}]})
    assert transport._carry(1.)
    commands = list(transport.queue)
    assert len(commands) == 24
    for when, rid, command in commands:
        assert command['duration_s'] == .1
        assert transport.authorize(rid, command, when)
        robots[rid].commanded(command, when)
    assert all(robot.translation_commands == 12 for robot in robots.values())


def test_fabricated_current_registration_cannot_reenable_unmeasured_fractional_pulses():
    b = candidate()
    b['e2e_options']['pulse_budget'] = 'fractional_duration_v1'
    with pytest.raises(ValueError, match='ORIGINAL_CHECKOUT_OR_REVIEWED_RUNTIME'):
        require_current(b, ROOT)


def test_workflow_adapter_always_selects_its_registered_bundle(monkeypatch):
    from scripts import run_e2e_reviewed as adapter
    seen = []
    monkeypatch.setattr(adapter.runner, 'main', lambda argv: seen.append(argv))
    adapter.main(['--mapping-budget', 'case_cap_v1'])
    assert seen == [['--mapping-budget', 'case_cap_v1', '--runtime-registration', OPTION]]
    for args in (['--runtime-registration', 'off'], ['--runtime-registration=off']):
        with pytest.raises(ValueError, match='WORKFLOW_OWNS'):
            adapter.main(args)
