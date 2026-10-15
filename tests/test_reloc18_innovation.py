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

def test_heading_has_one_dof_and_small_prior_is_not_overwritten():
    from harness.reloc18_innovation import fuse_heading
    low=fuse_heading([0,0,0],.03,np.eye(3)*1e-6,.01)
    assert low['dof']==1 and low['accepted'] and low['posterior_pose'][2]<.00001
    assert not fuse_heading([0,0,0],1.3,np.eye(3)*.001,.001)['accepted']

def test_carry_pf_catastrophic_jump_is_rejected_and_epoch_not_refreshed(monkeypatch):
    from types import SimpleNamespace
    from sim.solo_carry_pose import CommandPose,task_start
    from harness.selfmap4_geometry import static_input
    from harness.reloc18_innovation import carry_calibration
    static,_=static_input();cp=CommandPose(task_start(static),now=94.2)
    # Original 93315 t94.2: pose jumped 1.24m/77deg despite concentrated PF.
    cp.own.x=np.array([1.126,-1.907,.407]);cp.own.P=np.diag([.02,.02,.001])
    cp.reloc18_innovation=True;cp.reloc18_fit=carry_calibration()
    before=cp.own.x.copy();P=cp.own.P.copy()
    cp.tracker=SimpleNamespace(last={},observe=lambda *a:(np.array([-.087,-2.138,-.938]),np.diag([.0005,.0004,.00116])))
    cp.observe_own(np.zeros((480,640,3),np.uint8),94.2,camera='r1/robot_cam')
    assert not cp.tracker.last['accepted'] and cp.fixes==0 and cp.last_fix is None
    np.testing.assert_array_equal(before,cp.own.x);np.testing.assert_array_equal(P,cp.own.P)

def test_command_only_wrapper_restores_fix_epochs_as_well_as_pose(monkeypatch):
    import importlib.util
    from pathlib import Path
    from sim.solo_carry_pose import CommandPose,task_start
    from harness.selfmap4_geometry import static_input
    from sim.lookaround_localization import LookaroundLocalizer
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('reloc18_runner',Path(__file__).resolve().parents[1]/'experiments/2026-10-16-reloc18/run_round.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    # Register restoration before the explicit ablation modifies these methods.
    for name in ('__init__','issue','record','observe_own'):monkeypatch.setattr(CommandPose,name,getattr(CommandPose,name))
    monkeypatch.setattr(LookaroundLocalizer,'observe',LookaroundLocalizer.observe)
    mod.instrument(True)
    static,_=static_input();cp=CommandPose(task_start(static),now=1)
    cp.distance_since_fix=1.;cp.turn_since_fix=.2
    cp.tracker=SimpleNamespace(observe=lambda *a:(np.array([1,2,3]),np.eye(3)),last={})
    before=cp.own.x.copy();cp.observe_own(np.zeros((480,640,3),np.uint8),1,camera='r1/robot_cam')
    np.testing.assert_array_equal(cp.own.x,before)
    assert cp.fixes==0 and cp.last_fix is None and cp.distance_since_fix==1. and cp.turn_since_fix==.2
