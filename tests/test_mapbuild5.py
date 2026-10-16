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
