import math
import pytest
import numpy as np
from sim.settle_pulse import PulseSettler
from harness.reloc10_settle import settle_turn, turn_quantum
from harness.selfmap5_registration import MultiFrameEvidence


class Clear:
    def pose_clear(self,pose): return True


def test_quantized_plant_finishes_instead_of_99_reversals():
    model='s2_pulse_v122_rotL_v1'; q=turn_quantum(model)
    assert q > math.radians(2)
    for target in (-.785,.785):
        s=PulseSettler(math.radians(2)); yaw=0.
        for i in range(30):
            cmd,receipt=settle_turn(s,target-yaw,i*.2,costmap=Clear(),pose=np.zeros(3),motion_model=model)
            if receipt['settled']: break
            assert cmd['kind']=='mecanum'
            yaw += receipt['pulse']['predicted_delta'][2]
        assert receipt['settled'] and i<12 and s.total_reversals<=3
        assert abs(target-yaw)<=receipt['acceptance_band']


def test_blocked_pulse_does_not_accumulate_reversals():
    class Blocked:
        def pose_clear(self,pose): return False
    s=PulseSettler(0.)
    for i in range(10):
        cmd,r=settle_turn(s,(-1)**i*.2,i*.2,costmap=Blocked(),pose=np.zeros(3),motion_model='s2_pulse_v122_rotL_v1')
        assert cmd['kind']=='hold' and not r['settled']
    assert s.pulses==s.total_reversals==0


def test_rolling_evidence_keeps_live_views_beyond_30_seconds_only_when_on():
    line=dict(kind='floor_line',hue=10,endpoints=[[0,0],[1,0]],normal=[0,1])
    a,b=MultiFrameEvidence(),MultiFrameEvidence(); b.rolling=True
    for e in (a,b):
        e.begin(0.); e.add(dict(features=[line]),np.zeros(3),1.)
        e.add(dict(features=[line]),np.zeros(3),32.)
    assert not a.frames and not a.active
    assert [f['t'] for f in b.frames]==[32.]
    b.end(); b.add(dict(features=[line]),np.zeros(3),33.)
    assert [f['t'] for f in b.frames]==[32.,33.]


def test_bundle_toggles_off_unchanged_and_on_recorded():
    from scripts.run_self_map_diagnostic import bundle
    kw=dict(bootstrap='command_prior_v1', initial_sweep='required_360_v1', recovery_profile='selfmap4_recovery_v1',
        revision_gate='selfmap4_revision_gate_v2',multiframe_registration='selfmap4_multiframe_registration_v1',
        correction_safety='selfmap6_correction_safety_v1', active_relocalization='reloc8_active_vision_v1')
    a=bundle('a'*40,93571,60,**kw)
    assert a==bundle('a'*40,93571,60,**kw,reloc10_settle_v1=False,reloc10_registration_v1=False)
    b=bundle('a'*40,93571,60,**kw,reloc10_settle_v1=True,reloc10_registration_v1=True)
    assert b['options']['reloc10_settle_v1'] and b['options']['reloc10_registration_v1']


def test_texture_adapter_is_instance_local_and_restores_factory(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from sim import own_map_closed_loop as module, active_wall_map as host, natural_scene_texture as texture
    calls=[]
    scene=SimpleNamespace(transform=lambda xml: xml,manifest={})
    def original(bundle,seed):
        assert bundle['options']['render_profile']=='floor_light_v1'
        return scene
    monkeypatch.setattr(host,'make_scene',original)
    monkeypatch.setattr(texture,'manifest',lambda: {})
    monkeypatch.setattr(texture,'apply',lambda xml: (calls.append('apply') or xml))
    monkeypatch.setattr(texture,'verify_model',lambda model: dict(checked=True))
    def build(self,bundle,out,*,seed):
        self.world=SimpleNamespace(model=object())
        self.scene=host.make_scene(bundle,seed)
        self.scene.transform('<root/>')
    monkeypatch.setattr(module.Base,'__init__',build)
    x=module.PhysicsBackend(dict(options=dict(render_profile='floor_light_textured_v1')),tmp_path,seed=1)
    assert calls==['apply'] and host.make_scene is original
    assert x.texture_audit==dict(checked=True)
    assert x.scene.manifest['natural_scene_texture']['source_commit']=='db0a6858f6387e9048d4a37e78bc8eefd2ead484'


def test_executor_settle_receipt_reaches_dwell_and_records_reason(monkeypatch):
    from harness.self_map_executor import SelfMapExecutor
    from test_self_map_integration import fixture_mapper
    from test_self_map_executor import Sweep
    mapper,_=fixture_mapper(monkeypatch)
    c=SelfMapExecutor('r1',mapper=mapper,sweep=Sweep(),reloc10_settle_v1=True)
    c.active_stage='turn'; c.active_view=dict(heading_rad=0.)
    c.active_target=float(mapper.odom.pose[2])+.05
    c.active_until=0.; c.turn_settler=PulseSettler(math.radians(2))
    monkeypatch.setattr(c,'costmap',lambda *a,**kw: Clear())
    assert c.active_look(1.,np.zeros(3))['kind']=='hold'
    assert c.active_stage=='dwell'
    assert c.events[-1]['reason']=='reloc10_settle'
    assert c.events[-1]['settle_reason']=='quantum_deadband'


def test_registration_buffer_uses_one_command_frame_across_slam_corrections(monkeypatch):
    from test_self_map_integration import fixture_mapper,receive
    from harness import self_map_integration as sm, selfmap4_geometry as g
    from harness.self_map_integration import Options
    fixture,_=fixture_mapper(monkeypatch)
    static,_=g.static_input()
    opts=Options(self_map_integration=sm.OPTION,bootstrap='command_prior_v1',
        recovery_profile=g.PROFILE,multiframe_registration='selfmap4_multiframe_registration_v1',
        reloc10_registration_v1=True)
    m=sm.SelfMapIntegration('r1',options=opts,static_map=static)
    m.zones=fixture.zones
    m.command(dict(t=0.,kind='initial_servo_command',pulses=fixture.servo))
    m.slam.pose=np.array([3.,-2.,.4])  # synthetic independent SLAM revision
    observed=[]
    monkeypatch.setattr(g,'observe',lambda *a,**kw:dict(camera=[0.,0.],segments=[],floor_xy=[],features=[]))
    def captured(*args):
        observed.append(np.array(args[-1]))
        raise RuntimeError('captured registration boundary')
    monkeypatch.setattr(m.registration,'step',captured)
    monkeypatch.setattr(m.flow,'step',lambda rgb,servo,t,settled,delta,Q:(delta,Q,{}))
    with pytest.raises(RuntimeError,match='captured registration boundary'):
        receive(m,1)
    np.testing.assert_allclose(observed[0],m.odom.pose)
    assert not np.allclose(observed[0],[3.,-2.,.4])
