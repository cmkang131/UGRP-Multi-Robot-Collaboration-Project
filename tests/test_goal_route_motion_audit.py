import copy
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest
from scripts import run_goal_route_motion_audit as runner
from scripts import run_goal_route_preflight as previous
from harness import own_map_heading
from harness.self_pulse_rotation import selected_model, OPTION
from harness.zone_solo_cyan_path_heading import command_reason


def load_audit():
    spec=importlib.util.spec_from_file_location('motion_audit_test',runner.EXP/'code/diagnose.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


@pytest.mark.parametrize('seed',runner.SEEDS)
def test_registered_conditions_only_shared_contract_changes(seed):
    old=previous.bundle(seed,'test');new=runner.bundle(seed,'test')
    assert new.pop('motion_audit')['startup_correction']=='off'
    new['heading_contract'].pop('command_contract_source')
    new['heading_contract'].pop('command_contract')
    new['execution_bundle_id']=old['execution_bundle_id']
    assert new==old


def test_replay_uses_admitted_history_and_observes_before_issue():
    replay=load_audit().replay
    initial={'kind':'initial_servo_command','t':0.,'pulses':{1:2000}}
    pulse={'kind':'mecanum','t':1.,'forward':.35,'left':0.,'turn':0.,'duration_s':.1}
    times=[0.,1.,1.2,2.]
    a=replay([initial,pulse],times)
    assert np.array_equal(a[:2],np.zeros((2,3)))
    p=selected_model(OPTION)['profiles']['0:forward:0.35:0.10']
    assert np.allclose(a[2],p['mean_delta'],rtol=0,atol=1e-12)
    assert np.array_equal(a[2],a[3])
    # A proposed invalid .06s pulse absent from admitted history cannot move DR.
    assert np.array_equal(replay([initial],times),np.zeros((4,3)))


def test_exact_saved_host_fault_proposal_replaced_by_shared_selector():
    fixture=json.loads(Path('tests/fixtures/path_heading/command-contract.json').read_text())
    # Exercise own-map host API rather than cloning the common algorithm.
    rows=fixture if isinstance(fixture,list) else fixture.get('cases',[])
    assert rows or fixture
    profiles=selected_model(OPTION)['profiles']
    plan={'coordinate_frame':'r3/own_odom','status':'goal_approach',
          'path_m':[[0.,0.],[0.,.04]],'heading_rad':0.}
    result=own_map_heading.command(plan,[0.,0.,0.],profiles,robot_id='r3')
    assert command_reason(result) is None
    assert result['kind']=='hold' or result['duration_s']>=.10


def test_heading_off_preserves_object():
    value={'kind':'mecanum','duration_s':.06,'forward':0.,'left':.35,'turn':0.}
    assert own_map_heading.command(None,None,None,robot_id='r3',heading_mode='off',legacy_action=value) is value
