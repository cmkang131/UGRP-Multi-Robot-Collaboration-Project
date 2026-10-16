"""Own-map adapter contracts; no physics, renderer or provider calls."""
import math
import numpy as np
import pytest
from harness.mapbuild_rbpf import MapbuildRBPF, OPTION, propagate_covariance
from harness.active_camera import SEARCH
from harness.self_map_rbpf import RaoBlackwellizedGrid
from scripts.mapbuild5_motion import command_intervals


def test_default_off_and_full_covariance_rotated_once():
    with pytest.raises(ValueError,match='EXPLICIT'):
        MapbuildRBPF(SEARCH)
    g=RaoBlackwellizedGrid('r1',profiles={})
    g.poses[:,2]=math.pi/2;g.pending_cov[:]=0
    cov=np.array([[.04,.01,.002],[.01,.09,.003],[.002,.003,.01]])
    propagate_covariance(g,[1,0,0],cov)
    rotation=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    assert np.allclose(g.pending_cov,rotation@cov@rotation.T)
    assert np.allclose(g.poses[:,:2],[0,1])


def test_interval_prior_preserves_stop_tail_covariance_at_next_command():
    p=dict(times=[0,.1,1.],curve=[[0,0,0],[.01,0,0],[.02,0,0]],
           covariance=np.diag([.01,.02,.03]).tolist())
    cal=dict(physics_backend='mjwarp',profiles={'drive:forward:0.35:0.10':p})
    frames=[dict(frame_id=i,t=i/10) for i in range(21)]
    commands=[dict(t=t,axis='forward',value=.35,duration_s=.1) for t in (0.,1.)]
    rows=command_intervals(frames,commands,cal)
    assert np.allclose(rows[0][0],0)
    assert np.allclose(sum(r[0] for r in rows.values()),[.04,0,0])
    # Context covariance is allocated exactly twice, not lost at t=1.
    total=sum(r[1] for r in rows.values())
    assert np.all(np.diag(total)>=2*np.diag(p['covariance'])-1e-12)


def test_fixed_gauge_and_scan_rejection_cannot_resample(monkeypatch):
    rbpf=MapbuildRBPF(SEARCH,option=OPTION);g=rbpf.grid
    assert np.allclose(g.pending_cov,0)
    features=dict(height_m=.2,fy=622.,contrast=50.,band_std=1.,sharpness=50.,body_settling=1.)
    scan=dict(camera=[0,0],segments=[[[1,-.5],[1,.5]]],features=[features])
    rbpf.step(.3,3,[0,0,0],np.diag([.001,.001,.001]),scan)
    assert g.maps[0].frames==1 and all(m.cells is not g.maps[0].cells for m in g.maps[1:])
    def rejected(field,points,camera,prior,cov,rng,options):
        return prior,0.,dict(reason='low_overlap',proposal='motion_fallback')
    monkeypatch.setattr('harness.rbpf_rejection.improved_proposal',rejected)
    _,e=rbpf.step(1.3,13,[0,0,0],np.diag([.001,.001,.001]),scan)
    assert e['reason']=='low_overlap'
    assert e['inserted'] and not e['resampled'] and not e['sensor_weight_update']
    assert all(m.frames==2 for m in g.maps)


def test_unknown_scan_keeps_motion_and_does_not_carve_free():
    r=MapbuildRBPF(SEARCH,option=OPTION)
    pose,event=r.step(.1,1,[.05,0,0],np.eye(3)*.01,dict(segments=[]))
    assert np.allclose(pose,[.05,0,0])
    assert event['reason']=='no_visible_scan' and not event['resampled']
    assert all(not m.cells for m in r.grid.maps)


def test_fixed_floor_calibration_preserves_body_camera_evaluation_transform():
    from scripts.mapbuild5_manifest import fixed_floor_calibration
    cal=fixed_floor_calibration(SEARCH)
    origin=np.asarray(cal['camera_origin_body_m'])
    rotation=np.asarray(cal['camera_to_body_rotation'])
    normal=np.asarray(cal['floor_normal_camera'])
    # Arbitrary body-frame floor points must satisfy the exported camera
    # plane, and camera-centre evaluation must use the declared lever arm.
    floor=np.array([[0,0,0],[1,-2,0],[-.3,.7,0]])
    camera=(floor-origin)@rotation
    assert np.allclose(camera@normal+cal['camera_height_m'],0)
    assert np.isclose(np.linalg.norm(normal),1)
    assert np.allclose(camera@rotation.T+origin,floor)


def test_camera_evaluation_uses_nominal_lever_arm_without_world_truth():
    from scripts.mapbuild5_evaluate import estimated_camera
    calibration=dict(camera_origin_body_m=[.1,0,.2],camera_to_body_rotation=np.eye(3).tolist())
    xyz,rotation=estimated_camera([2,3,math.pi/2],calibration)
    assert np.allclose(xyz,[2,3.1,.2])
    assert np.allclose(rotation@[1,0,0],[0,1,0])


def test_evaluator_rejects_modified_sealed_prediction(tmp_path):
    import hashlib,json
    from scripts.mapbuild5_evaluate import verify_seal
    prediction=tmp_path/'trajectory.json';prediction.write_text('[1]')
    (tmp_path/'prediction-seal.json').write_text(json.dumps(dict(inputs={},predictions={
        prediction.name:hashlib.sha256(prediction.read_bytes()).hexdigest()})))
    verify_seal(tmp_path)
    prediction.write_text('[2]')
    with pytest.raises(ValueError,match='SEALED_PREDICTION_CHANGED'):
        verify_seal(tmp_path)
