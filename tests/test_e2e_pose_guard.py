import json,math
from pathlib import Path
import numpy as np
import pytest
from harness.ego_pose_continuity import Reporter,Options,MAHALANOBIS,MAHALANOBIS_SE2,CHI2_99_SE2
from harness.e2e_pose_guard import configure


def test_xy_gate_accepts_wrong_yaw_but_se2_gate_preserves_prediction():
    old=Reporter([0.,0.,0.],np.eye(3)*1e-3,Options(correction_gate=MAHALANOBIS))
    new=Reporter([0.,0.,0.],np.eye(3)*1e-3,Options(correction_gate=MAHALANOBIS_SE2))
    for r in (old,new):r.predict([.02,0.,.01],np.eye(3)*1e-4)
    before=new.pose.copy();cov=new.covariance.copy()
    assert old.measure([.02,0.,math.pi/2],np.eye(3)*1e-3)['accepted']
    row=new.measure([.02,0.,math.pi/2],np.eye(3)*1e-3)
    assert not row['accepted'] and row['mahalanobis_xy']==0
    assert row['mahalanobis_se2']>CHI2_99_SE2 and row['gate_dof']==3
    np.testing.assert_array_equal(new.pose,before);np.testing.assert_array_equal(new.covariance,cov)
    assert new.measure([.025,0.,.011],np.eye(3)*1e-3)['accepted']
    assert np.linalg.eigvalsh(new.covariance).min()>0


def test_yaw_wrap_is_short_rotation_and_correlated_covariance_is_supported():
    P=np.array([[.01,0.,.003],[0.,.01,0.],[.003,0.,.01]])
    r=Reporter([0.,0.,math.pi-.01],P,Options(correction_gate=MAHALANOBIS_SE2))
    row=r.measure([.01,0.,-math.pi+.01],P)
    assert row['accepted'] and row['innovation'][2]==pytest.approx(.02)
    assert row['threshold']==pytest.approx(CHI2_99_SE2)


def test_live_instance_and_trace_option_are_consistent_default_unchanged():
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options as Study
    import cv2,base64,hashlib
    cov=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    r=Robot('r1',61003,cov,Study(),pose_fix='innovation')
    view=r.goal._pose_continuity_view;configure(r.goal)
    assert view.options.correction_gate==MAHALANOBIS
    configure(r.goal,'se2_innovation_v1');assert view.reporter.options is view.options
    rgb=np.zeros((480,640,3),np.uint8);ok,data=cv2.imencode('.jpg',rgb);data=data.tobytes()
    trace=r.receive(dict(frame_id=1,sim_time=0.,sha256=hashlib.sha256(data).hexdigest(),image=base64.b64encode(data).decode()),rgb)
    assert trace['pose_continuity']['options']['correction_gate']==MAHALANOBIS_SE2
    assert Options().correction_gate=='off'


def test_bundle_registers_full_guard_and_source_closure():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    b=bundle('a'*40,61003,'study_gemma4_31b_v1',**options(),speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1')
    assert b['execution_bundle_id']=='e2e18-v226';require_current(b,ROOT)
    assert 'harness/e2e_pose_guard.py' in b['source_sha256']
    b['e2e_options']['pose_guard']='off'
    with pytest.raises(ValueError,match='SE2'):require_current(b,ROOT)
