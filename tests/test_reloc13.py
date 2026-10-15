"""Regression at the covariance handoff and correlated-budget seams, no plant."""
import math
import numpy as np
import pytest
from harness import selfmap4_geometry as g, selfmap5_registration as reg
from test_selfmap5 import edges_and_lines


def test_absolute_covariance_handoff_preserves_ransac_envelope(monkeypatch):
    static, _ = g.static_input(); edges, lines = edges_and_lines()
    raw = np.diag([.05**2, .04**2, math.radians(2)**2])
    for enabled in (False, True):
        r = g.StaticRegistration(static, multiframe_registration=reg.OPTION,
            reloc10_registration_v1=True, reloc12_raw_cov_gate_v1=True,
            reloc13_execution_cov_v1=enabled)
        r.pf.landmark_map.edges = edges
        monkeypatch.setattr(r.pf, 'step', lambda **kw: dict(pose=[0,0,0], covariance=raw.tolist(),
            updated=True, resolved=True, cluster={'mass':1.}, sensor={}))
        for i in range(3):
            result = r.step(dict(features=lines,segments=[]), [0,0,0], {6:1000+i*300}, i, [0,0,0])
        assert result is not None
        np.testing.assert_allclose(result[1], raw if enabled else reg.calibrated_covariance(raw))
        np.testing.assert_allclose(r.last['reloc12']['residual_covariance'], reg.calibrated_covariance(raw))


def test_absolute_static_fix_does_not_retain_bootstrap_covariance(monkeypatch):
    from harness.selfmap6_safety import GatedPriorSLAM
    from harness.natural_floor_slam import Observation
    s=GatedPriorSLAM('r1',max_sigma_xy_m=.15,max_sigma_yaw_rad=math.radians(5))
    s.landmarks={1: object()}; s.covariance=np.eye(3)*.2
    monkeypatch.setattr(s,'_update_landmarks',lambda *a:None)
    s._gate_prediction=np.eye(3)*.2; s.reloc13_absolute_static=True
    measurement=np.eye(3)*.001
    obs=Observation(1,1.,np.empty((0,2)),np.empty((0,32),dtype=np.uint8),'a'*64)
    event=s.guarded_step(obs,command_delta=np.zeros(3),command_covariance=np.zeros((3,3)),
        correction_gate=lambda *a:dict(accepted=True),pose_override=(np.zeros(3),measurement))
    np.testing.assert_allclose(event['covariance'], measurement)
    # A rejected static fix must retain the old prediction.
    obs=Observation(2,2.,np.empty((0,2)),np.empty((0,32),dtype=np.uint8),'b'*64)
    event=s.guarded_step(obs,command_delta=np.zeros(3),command_covariance=np.eye(3)*.002,
        correction_gate=lambda *a:dict(accepted=False),pose_override=(np.ones(3),measurement))
    assert event['status']=='command_only'
    np.testing.assert_allclose(event['covariance'], np.eye(3)*.003)


def test_budget_recal_uses_logged_fraction_and_same_ready_limit():
    from sim.solo_carry_pose import CommandPose, task_start
    static={'regions':{'pickup':{'center_m':[0,0],'half_extents_m':[.5,.5]}}}
    c=CommandPose(task_start(static),drive_model_deadband_v1=True,
        reloc10_rotation_calibration_v1=True,carry_pose_budget_recal_v1=True)
    c.turn_since_fix=1.
    assert c.sigmas()[2]==pytest.approx(math.radians(3)+.29)
    assert c.ready(0)
    c.turn_since_fix=3.
    assert not c.ready(0)
    assert c.yaw_budget_limit()==pytest.approx(math.radians(41))


def test_xy_reserve_toggle_does_not_change_unfitted_translation_growth():
    from sim.solo_carry_to_zone import CarryToZone
    from types import SimpleNamespace
    c=object.__new__(CarryToZone);c.loc=SimpleNamespace(sigmas=lambda:[.45,.45,.1])
    c.xy_reserve0=False; assert c.needs_budget()
    c.xy_reserve0=True; assert not c.needs_budget()


def test_registration_keeps_command_evidence_and_execution_frames_distinct(monkeypatch):
    from harness.natural_floor_slam import compose
    static,_=g.static_input();edges,lines=edges_and_lines()
    raw=np.diag([.03**2,.03**2,math.radians(1)**2])
    r=g.StaticRegistration(static,multiframe_registration=reg.OPTION,
        reloc10_registration_v1=True,reloc12_raw_cov_gate_v1=True,
        reloc13_execution_cov_v1=True,reloc13_execution_frame_v1=True)
    r.pf.landmark_map.edges=edges
    monkeypatch.setattr(r.pf,'step',lambda **kw:dict(pose=[0,0,0],covariance=raw.tolist(),
        updated=True,resolved=True,cluster={'mass':1.},sensor={}))
    execution=np.array([.02,-.01,.2])
    for i in range(3):
        result=r.step(dict(features=lines,segments=[]),[0,0,0],{6:1000+i*300},i,[0,0,0],execution_pose=execution)
    assert result is not None
    np.testing.assert_allclose(result[0],execution,atol=1e-12)
    np.testing.assert_allclose(compose(r.map_from_own,execution),[0,0,0],atol=1e-12)
    np.testing.assert_allclose(r.command_registration_anchor,[0,0,0])
    assert not r.execution_handoff  # mapper must still see correction admission
