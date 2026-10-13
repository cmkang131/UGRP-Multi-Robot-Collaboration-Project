import copy
import pytest
from sim.e2e_stage_physics import RELEASE,update
from tests.test_e2e_stage_cadence import shell
from tests.test_e2e_jev_current_route import candidate
from harness.e2e_release_physics import compose
from harness.e2e_runtime_registration import require_current
from scripts.run_e2e_ownmap_live import ROOT


def test_release_requires_both_issued_open_grips_relook_and_settle():
    host,_=shell(RELEASE);host.commands={'r1':{1:1500},'r2':{1:1500}}
    update(host,'grasp_lift',dict(kind='arm',servo_id=1,pulse=1500),robot_id='r1')
    assert host.dt==.00025
    host.commands['r1'][1]=2000;update(host,'relook');host.now+=1
    update(host,'relook');assert host.dt==.00025
    host.commands['r2'][1]=2000;update(host,'relook')
    host.now+=.79;update(host,'relook');assert host.dt==.00025
    host.now+=.02;update(host,'relook');assert host.dt==.001 and not host._stage_contact_latched
    update(host,'carry');assert host.dt==.00025
    update(host,'align');assert host.dt==.001
    update(host,'align',dict(kind='arm',servo_id=1,pulse=1500),robot_id='r2')
    assert host.dt==.00025 and host._stage_contact_latched


def test_missing_commands_or_open_during_loaded_phase_cannot_release():
    host,_=shell(RELEASE)
    update(host,'grasp_lift',dict(kind='arm',servo_id=1,pulse=1500))
    update(host,'relook');host.now+=5;update(host,'relook');assert host.dt==.00025
    host.commands={'r1':{1:2000},'r2':{1:2000}}
    update(host,'grasp_lift');host.now+=5;update(host,'grasp_lift');assert host.dt==.00025


def test_release_waits_for_coarse_clock_boundary_without_moving_time():
    host,_=shell(RELEASE);host.commands={'r1':{1:2000},'r2':{1:2000}}
    host._stage_contact_latched=True;update(host,'relook')
    host.now+=1.00025;before=host.now
    assert not update(host,'relook') and host.dt==.00025 and host.now==before
    host.now+=.00075;assert update(host,'relook') and host.dt==.001


def test_release_and_jev_keep_original_parent_admission(monkeypatch):
    b=candidate(monkeypatch);compose(b,RELEASE)
    assert b['execution_bundle_id']=='e2e18-v282'
    require_current(b,ROOT)
    bad=copy.deepcopy(b);bad['stage_physics_profile']['contact_dt_s']=.001
    with pytest.raises(ValueError):require_current(bad,ROOT)
