import json
from types import SimpleNamespace as NS
import numpy as np
import pytest

from harness import zone_s2_realism_contract as c
from scripts import run_s2_realism as runner
from sim.s2_realism import make_scene, StopGuard, PhysicalStop


def test_registered_bundle_options_closure_and_workflow():
    from sim.workflow_manager import catalog
    b = c.bundle('a'*40, seed=1032, stage_probe='pick', pickup_slot='P1-2')
    assert b['options'] == c.OPTIONS and b['task']['seed'] == 1032
    assert b['execution_bundle_id'] == 'zone-s2-realism-v109' and b['dev_light']
    for path in ('sim/masterpi_drive_friction_v7.py', 'sim/masterpi_camera_review_v3.py',
                 'harness/zone_solo_cyan_scene_runtime.py', 'sim/assets/masterpi_drive_friction_v2/fuji_roller.stl'):
        assert b['source_sha256'][path] == c.old.hp.base.sha(c.ROOT/path)
    row = next(x for x in catalog(c.ROOT)[0]['workflows'] if x['id'] == c.BUNDLE_ID)
    assert row['version'] == '7.2.0'
    with pytest.raises(ValueError, match='unregistered'):
        c.bundle('a'*40, seed=1028, stage_probe='place', pickup_slot='P2-3')
    with pytest.raises(ValueError, match='unregistered'):
        c.bundle('a'*40, seed=1032, stage_probe='place', pickup_slot='P1-2')


def test_camera_and_v7_compile_in_same_standard_scene_without_steps():
    import mujoco
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.masterpi_drive_friction_v7 import transform_xml, DriveParameters
    from sim.zone_cargo_contact import apply
    from sim import masterpi_camera_review_v3 as camera
    b = dict(map_id=c.old.MAP_ID, contact_profile='cargo_noslip_v1', options=c.OPTIONS,
             task=dict(seed=1032, robot_id='r3', pickup_slot='P1-2', destination='B'))
    scene = make_scene(b,1032)
    xml = apply(scene.transform(build_multi_robot_xml({})), 'cargo_noslip_v1')
    xml = scene.robot_transform(xml, hardware={}, calibrated_keys=())
    m = mujoco.MjModel.from_xml_string(transform_xml(xml, DriveParameters()))
    for rid in ('r1','r2','r3'):
        assert m.camera(rid+'__robot_cam').pos == pytest.approx(camera.POSITION_M)
        assert m.camera(rid+'__robot_cam').quat == pytest.approx(camera.QUAT_WXYZ)
        aid=m.actuator(rid+'__wheel_fl_drive').id
        assert m.actuator_biastype[aid] == 0  # native torque motor, no velocity servo/wrench


def test_probe_does_not_finish_at_first_high_or_before_check_return():
    r=NS(state='lift',scene_check=NS(phase='pending',checks=[]),beam_grasp_confirmed=True)
    assert not runner.stage_reached(r,'pick')
    r.scene_check.checks=[{'status':'unknown'}];r.scene_check.phase='restore_high'
    assert not runner.stage_reached(r,'pick')
    r.state='carry';r.scene_check.phase=None
    assert runner.stage_reached(r,'pick')


def test_physical_abort_debounce_normal_release_and_tilt():
    row=dict(t=0.,cyan_z_m=.1,cyan_min_z_m=.084,robot_tilt_deg=2.,finger_contacts=[True,True])
    g=StopGuard();g.check(row,release_allowed=False)
    g.check({**row,'t':.1,'finger_contacts':[False,False]},release_allowed=False)
    with pytest.raises(PhysicalStop,match='GRIP_LOSS'):
        g.check({**row,'t':.4,'finger_contacts':[False,False]},release_allowed=False)
    g.check({**row,'t':.5,'cyan_min_z_m':0.,'finger_contacts':[False,False]},release_allowed=True)
    with pytest.raises(PhysicalStop,match='LOAD_DROP'):
        g.check({**row,'t':.6,'cyan_min_z_m':0.,'finger_contacts':[False,False]},release_allowed=False)
    with pytest.raises(PhysicalStop,match='ROBOT_TILT_LIMIT'):
        g.check({**row,'robot_tilt_deg':10.},release_allowed=True)


def test_host_eval_cannot_steer_and_abort_retains_evaluation(tmp_path):
    owners=[]
    class Backend:
        def __init__(self,*a,**kw):
            self.now=0.;self.eval_rows=[];self.commands={'r3':{1:1500}};owners.append(self)
        def reset(self,cap):return 0.
        def set_deadline(self,t):pass
        def eval_sample(self):
            self.eval_rows.append(dict(t=self.now,cyan_xyz_m=[1.,0.,.1],
                cyan_rotation=np.eye(3).ravel().tolist(),box_half_m=[.017,.02,.016]))
            if self.now >= .05:raise PhysicalStop('GRIP_LOSS')
            return {'forbidden_gt': [9,9,9]}
        def capture(self):return {'r3':('OWN_RGB',None)}
        def issue(self,*args):pass
        def advance_to(self,t):self.now=t
        def close(self):self.closed=True
    class Runtime:
        def __init__(self,*a,**kw):
            self.state='carry';self.robot_id='r3';self.beam_grasp_confirmed=True
            self.scene_check=NS(phase=None,checks=[],visual_status='unconfirmed',retries=0)
            self.terminal=False;self.failure=None;owners.append(self)
        def initial_commands(self,t,commands):assert commands=={'r3':{1:1500}}
        def on_frames(self,t,frames):assert frames=={'r3':('OWN_RGB',None)}
        def step(self,t):return []
        def record(self):return {}
        def close(self):self.closed=True
    b=dict(source_sha='a'*40,task=dict(seed=1032,robot_id='r3',destination='B'),
           tick_s=.05,case_cap_s=.2,options=c.OPTIONS)
    result=runner.run(b,tmp_path/'run',backend_factory=Backend,runtime_factory=Runtime)
    assert result['status']=='PHYSICAL_FAILURE' and result['failure']['message']=='GRIP_LOSS'
    assert result['evaluation']['lifted'] and not result['evaluation']['inside']
    assert result['physical_success'] is None and result['model_calls']==0
    assert all(x.closed for x in owners)
    assert json.loads((tmp_path/'run/artifacts.sha256.json').read_text())['result.json']
