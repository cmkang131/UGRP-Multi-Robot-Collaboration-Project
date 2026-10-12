import copy
import xml.etree.ElementTree as ET
from types import SimpleNamespace
import pytest
from harness.e2e_runtime_registration import require_current
from scripts.run_e2e_ownmap_live import bundle,ROOT
from sim.e2e_speed3_profile import PROFILES,transform_xml
from scripts.e2e_speed_measure import audit_row

@pytest.mark.parametrize('mode',PROFILES)
def test_explicit_new_cohort_keeps_scene_and_contact(mode):
    common=dict(enabled=True,runtime_registration='reviewed_v1')
    old=bundle('a'*40,61001,'study_gemma4_31b_v1',**common)
    new=bundle('a'*40,61001,'study_gemma4_31b_v1',**common,speed3=mode)
    assert new['execution_bundle_id']==('e2e-speed3-v215' if mode=='adaptive_v1' else 'e2e-speed3-v214')
    assert not new['inherited_results']
    assert len(new['e2e_options']['exact_speedups'])==10
    assert all(new['e2e_options']['exact_speedups'].values())
    assert new['contact_profile']==old['contact_profile']
    assert new['weld'] is False and new['scenario_id']==old['scenario_id']
    require_current(new,ROOT)
    new['speed3_profile']['timestep_s']=.01
    with pytest.raises(ValueError,match='PROFILE_MISMATCH'):require_current(new,ROOT)

@pytest.mark.parametrize('mode',PROFILES)
def test_xml_changes_only_declared_solver_fields(mode):
    xml='<mujoco><option timestep=".00025" iterations="100" integrator="implicitfast" noslip_iterations="10"/><worldbody><camera name="own" fovy="60" pos="1 2 3"/></worldbody></mujoco>'
    root=ET.fromstring(transform_xml(xml,mode))
    assert root.find('option').get('noslip_iterations')=='10'
    assert float(root.find('option').get('timestep'))==PROFILES[mode]['timestep_s']
    assert ET.tostring(root.find('worldbody'))==ET.tostring(ET.fromstring(xml).find('worldbody'))

def test_audit_disabled_never_reads_particle_state():
    robot=SimpleNamespace(robot_id='r1',frame=SimpleNamespace(index=4),now=1.)
    assert audit_row(robot,'none',{})==dict(robot='r1',frame=4,t=1.)

def test_capture_same_sim_time_renders_once(monkeypatch):
    from sim.e2e_ownmap_live import PhysicsBackend,Evaluation
    calls=[]
    monkeypatch.setattr(Evaluation,'capture',lambda self:calls.append(self.now) or {'r1':object()})
    host=SimpleNamespace(bundle={'e2e_options':{'speed3':'dt1_v1'}},now=1.)
    # Bind method to a real backend shell without building a simulator.
    host=PhysicsBackend.__new__(PhysicsBackend)
    host.bundle={'e2e_options':{'speed3':'dt1_v1'}}
    host.world=SimpleNamespace(data=SimpleNamespace(time=1.))
    a=host.capture();assert host.capture() is a
    host.world.data.time=1.2
    assert host.capture() is not a and calls==[1.,1.2]


def test_adaptive_switch_uses_issued_action_and_resnaps_clock():
    from sim.e2e_speed3_profile import enter_contact
    calls=[]
    host=SimpleNamespace(bundle={'e2e_options':{'speed3':'adaptive_v1'}},dt=.002,now=12.4,
         world=SimpleNamespace(model=SimpleNamespace(opt=SimpleNamespace(timestep=.002))),
         _clock_snap=lambda:calls.append('snap'),_append=lambda *x:calls.append(x))
    assert not enter_contact(host,dict(kind='arm',servo_id=3,pulse=740))
    assert not enter_contact(host,dict(kind='look',pan_pulse=1600))
    assert enter_contact(host,dict(kind='arm',servo_id=1,pulse=1700))
    assert host.dt==host.world.model.opt.timestep==.00025
    assert calls[0]=='snap'
    assert not enter_contact(host,dict(kind='arm',servo_id=1,pulse=1600))


def test_issue_keeps_high_level_drive_conversion_in_parent(monkeypatch):
    from sim.e2e_ownmap_live import PhysicsBackend,Evaluation
    action=dict(kind='drive',forward=.3,lateral=0.,yaw=0.)
    calls=[]
    monkeypatch.setattr(Evaluation,'issue',lambda self,rid,a:calls.append((rid,a)))
    host=PhysicsBackend.__new__(PhysicsBackend)
    host.bundle={'e2e_options':{'speed3':'adaptive_v1'}}
    host.issue('r1',action)
    assert calls==[('r1',action)]
