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
    assert new['execution_bundle_id']=='e2e-speed3-v214'
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
