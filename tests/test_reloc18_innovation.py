"""Numerical and pre-mutation integration checks; no plant or renderer."""
import math
import numpy as np
import pytest
from harness.reloc18_innovation import fuse,InnovationGate,calibration
from harness.selfmap6_safety import GatedFloorSLAM
from harness.natural_floor_slam import Observation

def test_low_command_uncertainty_limits_measurement_influence():
    low=fuse([0,0,0],[.1,0,0],np.eye(3)*1e-6,np.eye(3)*.01,threshold=11.344866730144373)
    high=fuse([0,0,0],[.1,0,0],np.eye(3)*.1,np.eye(3)*.01,threshold=11.344866730144373)
    assert low['accepted'] and high['accepted']
    assert low['posterior_pose'][0]<.00002 and high['posterior_pose'][0]>.09

def test_wrapped_yaw_and_cross_covariance_joseph_update():
    P=np.array([[.1,.02,0],[.02,.1,.01],[0,.01,.05]])
    r=fuse([0,0,math.pi-.01],[.02,0,-math.pi+.01],P,np.eye(3)*.02,threshold=11.344866730144373)
    assert r['accepted'] and abs(r['innovation'][2]-.02)<1e-10
    post=np.asarray(r['posterior_covariance'])
    assert np.linalg.eigvalsh(post).min()>0 and post[0,0]<P[0,0]

def test_outlier_or_singular_directions_never_mutate_prediction():
    for P,R in [(np.eye(3)*.001,np.eye(3)*.001),(np.zeros((3,3)),np.zeros((3,3)))]:
        r=fuse([0,0,0],[1,0,0],P,R,threshold=11.344866730144373)
        assert not r['accepted'] and r['posterior_pose']==[0,0,0]
        np.testing.assert_array_equal(r['posterior_covariance'],P)

def test_raw_covariance_collapse_cannot_erase_empirical_floor_or_reuse_rgb():
    gate=InnovationGate();r=gate.consider([0,0,0],[.01,0,0],np.eye(3)*.001,np.zeros((3,3)),t=0,source='static')
    assert r['accepted'] and np.linalg.eigvalsh(r['measurement_covariance']).min()>0
    assert not gate.consider([0,0,0],[.01,0,0],np.eye(3)*.001,np.zeros((3,3)),t=.1)['accepted']
    assert gate.last['reason']=='correlated_measurement_thinned'

@pytest.mark.parametrize('bank',[False,True])
def test_actual_static_fit_seam_uses_fused_pose_before_mutating_bank(bank):
    slam=GatedFloorSLAM('r3');slam.reloc15_pose_handoff=True
    points=np.array([[.3,0],[.4,.2]]);desc=np.zeros((2,32),np.uint8)
    if bank:slam.step(Observation(0,0,points,desc),command_delta=np.zeros(3),command_covariance=np.zeros((3,3)))
    P=np.eye(3)*1e-6;slam.covariance=P.copy();slam._gate_prediction=P.copy();gate=InnovationGate()
    event=slam.guarded_step(Observation(1,1,points,desc),command_delta=np.zeros(3),command_covariance=np.zeros((3,3)),
        correction_gate=lambda p,q,P,d:gate.consider(p,q,P,d['covariance'],t=1,source='static'),
        pose_override=(np.array([.05,0,0]),np.eye(3)*1e-6))
    assert event['status']=='visual_relocalized'
    assert 0<slam.pose[0]<.001
    np.testing.assert_allclose(slam.pose,event['correction_gate']['posterior_pose'])

def test_default_off_and_explicit_bundle_delivery():
    from scripts.run_self_map_diagnostic import bundle
    from harness.self_map_integration import Options
    assert bundle('a'*40,93584,60)==bundle('a'*40,93584,60,reloc18_innovation_v1=False)
    with pytest.raises(ValueError):Options(reloc18_innovation_v1=1)
    with pytest.raises(ValueError):Options(reloc18_innovation_v1=True)
    kw=dict(recovery_profile='selfmap4_recovery_v1',revision_gate='selfmap4_revision_gate_v2',
        multiframe_registration='selfmap4_multiframe_registration_v1',correction_safety='selfmap6_correction_safety_v1')
    assert bundle('a'*40,93584,60,reloc18_innovation_v1=True,**kw)['options']['reloc18_innovation_v1'] is True

@pytest.mark.parametrize('bad',[float('nan'),-1])
def test_invalid_covariance_is_rejected(bad):
    with pytest.raises(ValueError):fuse([0,0,0],[0,0,0],np.diag([bad,1,1]),np.eye(3),threshold=11.3)
