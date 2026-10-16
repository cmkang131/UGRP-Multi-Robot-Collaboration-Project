import copy,json
from pathlib import Path
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision,rt
from harness.zone_solo_cyan_look_ahead import Runtime,Previous,validate
from harness.zone_solo_cyan_real_carry import LOOK_AHEAD
from harness import zone_s2_realism_contract_v130 as c


def test_default_off_commands_record_byte_equal(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(Previous,{}),(Runtime,{}),(Runtime,dict(carry_pose='off'))]]
    try:
        for r in rs:r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}});r.last_report=r.pose.report(1.);r.state='lift';r.receipt=True
        for t in (1.,1.05,1.1,1.2,1.65,1.8):
            commands=[r.step(t) for r in rs];assert len(set(json.dumps(x).encode() for x in commands))==1
            for r,rows in zip(rs,commands):
                for rid,a in rows:r.on_command(rid,t,a)
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_measured_table_fail_closed():
    t=json.loads(Path(c.TABLE).read_text());validate(t)
    for key,value in [('fit_uses_gt',True),('admission_pass',False),('bilateral_fraction',.5),('pitch_difference_deg',.6)]:
        bad=copy.deepcopy(t);bad[key]=value
        with pytest.raises(ValueError):validate(bad)


def test_full_runtime_uses_measured_loaded_camera_and_all_adopted_options(static):
    from scripts.run_s2_look_ahead import runtime_factory
    from harness.zone_final_pair_camera import floor_camera
    b=c.bundle('a'*40,carry_pose='look_ahead_v1',servo_stiffness='real_v1',camera_pitch='stiff_target_v1');c.require_execution(b)
    assert b['task']['seed']==1051 and b['options']['slip_recovery']=='slip_recovery_v1'
    bad=copy.deepcopy(b);bad['scenario']='S3'
    with pytest.raises(ValueError):c.require_execution(bad)
    bad=copy.deepcopy(b);bad['options']['carry_pose']='off'
    with pytest.raises(ValueError):c.require_execution(bad)
    r=runtime_factory(b)(static,c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA,**b['task'])
    try:
        r.initial_commands(0.,{'r3':LOOK_AHEAD});r.pose.report(.2)
        r.on_command('r3',.3,dict(kind='hold'));inner=r.pose.provider;pf=inner.loc._pf;pf.load.loaded=True
        cm=pf.column_model_for(LOOK_AHEAD);measured=floor_camera(b['look_ahead_calibration']['camera_models']['loaded'])
        np.testing.assert_allclose(cm.origin,measured['origin_m'],atol=1e-12)
        np.testing.assert_allclose(cm._rot,measured['rotation'],atol=1e-12)
        assert r.visual_pose_supported(LOOK_AHEAD) and not pf.settled(7.) and pf.settled(10.)
        assert r.record()['look_ahead_calibration']['loaded_measured']
        r.on_command('r3',11.,dict(kind='arm',servo_id=3,pulse=1000));r.pose.report(12.)
        assert not pf.settled(30.)
    finally:r.close()
