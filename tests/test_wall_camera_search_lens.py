import cv2,numpy as np
from harness.wall_camera_search import WallCameraSearch,bounded_pan_steps
from harness.wall_lens_residual import ResidualLens,brown,fit_residual,line_residual,validation_report
K=np.array([[620.,0,288.],[0,622.,219.],[0,0,1.]])
D=np.array([-.02,-.17,-.25,.96])

def test_occluded_camera_search_checks_up_down_both_sides_and_does_not_claim_success():
 s=WallCameraSearch(1900);views=[]
 while (v:=s.next_view()) is not None:views.append(v)
 assert [v.posture for v in views[:3]]==['up','down','ahead']
 assert {v.pan for v in views}>={500,2500}
 assert len(views)==len(set(views))<=30
 assert set(v.posture for v in views)=={'up','down','ahead'}
 assert all(abs(b-a)<=250 for a,b in zip([1900]+bounded_pan_steps(1900,500),bounded_pan_steps(1900,500)))
 s=WallCameraSearch();assert s.next_view(confirmed=True,observed_floor_support=0) is not None
 assert s.next_view(confirmed=True,observed_floor_support=4) is None

def test_zero_residual_is_same_fisheye_geometry_and_nonzero_composition_roundtrips():
 a=ResidualLens(K,D);expected=cv2.fisheye.initUndistortRectifyMap(K,D,np.eye(3),K,(640,480),cv2.CV_32FC1)
 actual=a.maps();assert max(float(abs(x-y).max()) for x,y in zip(actual,expected))<1e-4
 p=np.array([[-.3,-.2],[.3,.2],[0.,.1]]);m=ResidualLens(K,D,(.08,-.03,.01,-.006))
 raw=cv2.fisheye.distortPoints(brown(p,m.coefficients).reshape(-1,1,2),K,D)
 want=p@K[:2,:2].T+K[:2,2];np.testing.assert_allclose(m.points(raw),want,atol=1e-6)

def test_plumbline_fit_recovers_unseen_edges_but_one_side_cannot_be_adopted():
 truth=(.08,-.03,.008,-.006);lines=[];validation=[]
 for i,(x,y,dx,dy) in enumerate([(-.4,-.3,.75,.15),(-.4,.2,.75,-.05),(-.35,-.3,.05,.6),(.3,-.3,.08,.6),(-.4,-.2,.8,.4),(-.35,.32,.7,-.35),(-.38,-.25,.07,.5),(.2,-.3,.12,.55)]):
  xy=np.array([x,y])+np.linspace(0,1,60)[:,None]*[dx,dy];raw=cv2.fisheye.distortPoints(brown(xy,truth).reshape(-1,1,2),K,D).reshape(-1,2)
  if i<6:lines.append(raw)
  else:validation.append(dict(id=str(i),side='left' if i==6 else 'right',points=raw))
 model,diag=fit_residual(lines,K,D);assert diag['success']
 assert max(np.std(line_residual(model.points(r['points']))) for r in validation)<.005
 assert not validation_report(model,validation)['adopt']
