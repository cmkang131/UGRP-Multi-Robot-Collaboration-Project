import copy
import pytest
from harness import zone_s2_realism_contract_v130 as old
from harness import zone_s2_realism_contract_v131 as new
from sim.s2_eval_wall_contacts import category


def test_one_explicit_policy_difference_and_old_registration_unchanged():
    kwargs=dict(carry_pose='look_ahead_v1',servo_stiffness='real_v1',camera_pitch='stiff_target_v1')
    a=old.bundle('a'*40,**kwargs); old.require_execution(a)
    b=new.bundle('a'*40,**kwargs,pregrasp_policy='log_only_v1');new.require_execution(b)
    options=copy.deepcopy(b['options']);assert options.pop('pregrasp_policy')=='log_only_v1'
    assert options==a['options']
    assert b['task']==a['task'] and b['case_cap_s']==a['case_cap_s']
    assert new.bundle('a'*40)['options']['pregrasp_policy']=='off'
    with pytest.raises(ValueError):new.require_execution(new.bundle('a'*40,**kwargs))


def test_wall_contact_scope():
    assert category(['r3__wheel_fl_roller','north_wall'],'r3')=='wheel'
    assert category(['r2__wheel_fl_roller','north_wall'],'r3') is None
    assert category(['r3__wheel_fl_roller','floor'],'r3') is None
    assert category(['cargo_box_00_geom','divider_1'],'r3')=='cargo'
