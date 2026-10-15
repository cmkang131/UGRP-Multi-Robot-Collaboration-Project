from dataclasses import replace
import numpy as np
import pytest
from harness.self_map_integration import Options
from scripts.run_self_map_diagnostic import bundle
from harness.selfmap4_geometry import observe, static_input
from harness.self_map_landmark_sensor import Sensor
from harness.own_map_amcl_vendor.landmarks import MapFeatures


def test_selfmap_default_off_bundle_unchanged_and_explicit_toggle_roundtrip():
    kw=dict(bootstrap='command_prior_v1',initial_sweep='required_360_v1',recovery_profile='selfmap4_recovery_v1',
        revision_gate='selfmap4_revision_gate_v2',multiframe_registration='selfmap4_multiframe_registration_v1',
        correction_safety='selfmap6_correction_safety_v1',active_relocalization='reloc8_active_vision_v1')
    a=bundle('a'*40,93571,180,**kw)
    b=bundle('a'*40,93571,180,**kw,reloc9_rotation_calibration_v1=False,reloc9_wall_height_guard_v1=False)
    assert a==b
    c=bundle('a'*40,93571,180,**kw,reloc9_rotation_calibration_v1=True,reloc9_wall_height_guard_v1=True)
    assert c['options']['reloc9_rotation_calibration_v1'] is True
    assert c['options']['reloc9_wall_height_guard_v1'] is True
    assert not Options().reloc9_rotation_calibration_v1 and not Options().reloc9_wall_height_guard_v1
    with pytest.raises(ValueError):Options(reloc9_wall_height_guard_v1=True)
    with pytest.raises(ValueError):Options(reloc9_rotation_calibration_v1='on')


def test_wall_guard_missing_top_cannot_insert_wall_or_clear_from_false_wall(monkeypatch):
    import harness.selfmap4_geometry as g
    mp,hfw,_=g.modules()
    original=hfw.detect
    # The actual height-free detector shape/domain is retained; force a floor
    # candidate with no measured top and require it to disappear before linking.
    def scan(*args,**kwargs):
        value=original(*args,**kwargs)
        value['vb'][:,0]=400.;value['vt'][:,0]=np.nan
        return value
    monkeypatch.setattr(hfw,'detect',scan)
    static,_=static_input();sensor=Sensor(MapFeatures(static).hues)
    # This test isolates the wall-column guard, not the CAD self-shadow sensor.
    monkeypatch.setattr(sensor,'measure',lambda *args,**kwargs: [])
    from harness.active_relocalization import LOOK
    image=np.full((480,640,3),100,np.uint8)
    guarded=observe(image,LOOK,sensor,reloc9_wall_height_guard_v1=True)
    assert guarded['raw_columns']==guarded['fitted_columns']==0
    assert guarded['segments']==[] and guarded['floor_xy']==[]
    assert guarded['wall_height_guard']['top_supported_columns']==0


def test_mapper_receives_calibrated_model_once_and_forwards_guard(monkeypatch):
    from test_self_map_integration import fixture_mapper, receive
    from harness import self_map_integration as sm
    from harness import selfmap4_geometry as g
    from harness.self_pulse_rotation import RotationPulseOdometry
    mapper,_=fixture_mapper(monkeypatch)
    assert isinstance(mapper.odom,RotationPulseOdometry)
    # Selfmap already used rotL: toggling reloc9 keeps that measured curve,
    # never carries the v7 steady-state carry gain into this pulse response.
    from harness.reloc9_rotation import selfmap_model
    assert selfmap_model(mapper.options.motion_model,True)==mapper.options.motion_model
    static,_=static_input()
    options=Options(self_map_integration=sm.OPTION,bootstrap='command_prior_v1',recovery_profile=g.PROFILE,
        motion_model='s2_pulse_v122',reloc9_rotation_calibration_v1=True,reloc9_wall_height_guard_v1=True)
    opted=sm.SelfMapIntegration('r1',options=options,static_map=static)
    assert isinstance(opted.odom,RotationPulseOdometry)
    assert opted.options.motion_model=='s2_pulse_v122_rotL_v1'
    opted.zones=mapper.zones
    opted.command(dict(t=0.,kind='initial_servo_command',pulses=mapper.servo))
    calls=[]
    def measured(*args,**kwargs):
        calls.append(kwargs)
        return dict(camera=[0.,0.],segments=[],floor_xy=[],features=[],wall_height_guard=dict(top_supported_columns=0))
    monkeypatch.setattr(g,'observe',measured)
    monkeypatch.setattr(opted.registration,'step',lambda *args:None)
    monkeypatch.setattr(opted.flow,'step',lambda rgb,servo,t,settled,delta,Q:(delta,Q,{}))
    row=receive(opted,1)
    assert calls==[dict(reloc9_wall_height_guard_v1=True)]
    assert row['wall_height_guard']==dict(top_supported_columns=0)
    assert row['rotation_calibration']['carry_gain_applied'] is False
