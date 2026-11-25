import importlib.util,sys
from pathlib import Path
import cv2,numpy as np
spec=importlib.util.spec_from_file_location('strict_wall_motion',Path(__file__).parents[1]/'harness/strict_wall_motion.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
K=np.array([[400.,0.,320.],[0.,400.,240.],[0.,0.,1.]])
AXES=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])
ORIGIN=np.array([.08,0.,.3])
def fixture():
 rng=np.random.default_rng(3)
 floor=np.c_[rng.uniform(.60,1.2,120),rng.uniform(-.4,.4,120),np.zeros(120)]
 wall=np.c_[np.full(80,1.45),rng.uniform(-.5,.5,80),rng.uniform(.08,.55,80)]
 xyz=np.r_[floor,wall];optical=(xyz-ORIGIN)@AXES
 p0=m.project(K,optical);p1=m.project(K,optical+[.035,0,0]);p2=m.project(K,optical+[.07,0,0])
 return xyz,p0,p1,p2,np.arange(len(xyz))<len(floor)
def test_floor_motion_recovers_metric_translation_and_wall_plane():
 xyz,p0,p1,p2,floor=fixture()
 prev,reason=m.floor_motion(p0,p1,floor,K,ORIGIN,AXES)
 motion,reason=m.floor_motion(p0,p2,floor,K,ORIGIN,AXES)
 assert reason=='ok'
 np.testing.assert_allclose(motion['t'],[.07,0,0],atol=1e-5)
 points,keep,reason=m.reconstruct(p0,p2,p1,motion,prev,K,ORIGIN,AXES)
 assert reason=='ok' and keep.all()
 np.testing.assert_allclose(points,xyz,atol=1e-5)
 planes=m.vertical_planes(points)
 assert len(planes)==1 and planes[0]['support']==80
 assert abs(abs(planes[0]['normal'][0])-1)<1e-7
 assert abs(planes[0]['segment'][:,0]-1.45).max()<1e-5
def test_floor_lines_are_not_vertical_walls_and_collinear_edges_abstain():
 xyz,*_=fixture()
 assert not m.vertical_planes(xyz[:120])
 line=np.c_[np.full(50,1.),np.zeros(50),np.linspace(.1,.6,50)]
 assert not m.vertical_planes(line)
def test_three_distinct_views_required_and_inconsistent_reflection_rejected():
 xyz,p0,p1,p2,floor=fixture()
 prev,_=m.floor_motion(p0,p1,floor,K,ORIGIN,AXES)
 motion,_=m.floor_motion(p0,p2,floor,K,ORIGIN,AXES)
 points,keep,reason=m.reconstruct(p0,p2,p1,motion,None,K,ORIGIN,AXES)
 assert not keep.any() and reason=='need_distinct_third_view'
 corrupt=p1.copy();corrupt[~floor]+=[20,15]
 points,keep,_=m.reconstruct(p0,p2,corrupt,motion,prev,K,ORIGIN,AXES)
 assert not keep[~floor].any()
 assert not m.vertical_planes(points)
def test_pure_rotation_or_stopped_camera_cannot_confirm_wall_depth():
 _,p0,p1,p2,floor=fixture()
 angle=.03;r,_=cv2.Rodrigues(np.array([0.,angle,0.]))
 rotated=m.project(K,(np.c_[p0,np.ones(len(p0))]@np.linalg.inv(K).T)@r.T)
 motion,_=m.floor_motion(p0,rotated,floor,K,ORIGIN,AXES)
 assert motion is None or motion['baseline_m']<m.Parameters().min_baseline_m
def test_default_off_preserves_original_object_without_inspecting_image():
 original={'segments':object()}
 assert m.verify_output(original,rgb=object()) is original


def test_active_api_off_matches_original_default_on_rgb():
 from harness.active_wall_vision import observe
 from harness.active_camera import SEARCH
 rgb=np.zeros((480,640,3),np.uint8)
 assert observe(rgb,SEARCH)==observe(rgb,SEARCH,wall_verification='off')


def test_dense_sampling_uses_older_distinct_view_instead_of_adjacent_frame():
 ids=np.arange(30);uv=np.ones((30,2))
 history=[dict(motion=dict(centre=np.array([x,0,0])),ids=ids,uv=uv*x) for x in [.004,.012,.020,.024,.028]]
 selected,pixels=m.distinct_past_view(history,dict(centre=np.array([.032,0,0])),ids)
 assert selected is not None
 assert np.linalg.norm(selected['centre']-[.032,0,0])>=m.Parameters().distinct_baseline_m
 assert np.linalg.norm(selected['centre'])>=m.Parameters().distinct_baseline_m
 np.testing.assert_allclose(pixels,uv*selected['centre'][0])


def test_weak_wall_texture_gets_tracks_despite_high_contrast_floor():
 image=np.full((480,640),128,np.uint8)
 for y in range(30,250,25):
  for x in range(30,610,30):cv2.rectangle(image,(x,y),(x+7,y+7),132,-1)
 for y in range(330,460,20):
  for x in range(25,620,20):cv2.rectangle(image,(x,y),(x+8,y+8),255,-1)
 points=m.balanced_corners(image)
 assert (points[:,1]<260).sum()>30
 assert (points[:,1]>330).sum()>30


def test_floor_can_be_minority_when_bottom_region_contains_upright_board():
 xyz,p0,p1,p2,floor=fixture()
 # Many upright-board corners dominate the lower region; floor is separate.
 indices=np.r_[np.arange(120),np.tile(np.arange(120,200),4)]
 motion,reason=m.floor_motion(p0[indices],p2[indices],np.ones(len(indices),bool),K,ORIGIN,AXES)
 assert reason=='ok'
 np.testing.assert_allclose(motion['t'],[.07,0,0],atol=1e-4)
 assert motion['floor_model_index']>=1


def test_foreground_vertical_side_edge_cannot_become_floor_contact():
 gray=np.zeros((480,640),np.uint8);gray[:,501:]=255
 floor=np.array([[510,100],[510,200],[510,300],[510,400]])
 ok,reason=m.contact_support([[500,60],[500,420]],floor,gray,[0,1])
 assert not ok and reason=='occluding_side_edge'

def test_real_crossing_floor_contact_requires_visible_edge_and_floor_support():
 gray=np.zeros((480,640),np.uint8);gray[301:]=150
 floor=np.array([[120,325],[240,330],[360,335],[480,340]])
 assert m.contact_support([[80,300],[540,300]],floor,gray,[0,1])[0]
 assert not m.contact_support([[80,300],[540,300]],[],gray,[0,1])[0]
 assert not m.contact_support([[80,300],[540,300]],floor,np.zeros_like(gray),[0,1])[0]
