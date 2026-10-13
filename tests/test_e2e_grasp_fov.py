import math
from types import SimpleNamespace
import numpy as np
import pytest
from harness import e2e_grasp_fov as fov


@pytest.fixture(autouse=True)
def clear_guard(monkeypatch):
    monkeypatch.setattr(fov,'projected_clear',lambda *a:True)


def case(bearing=105.,option='turn60_v1'):
    a=math.radians(bearing)
    r=SimpleNamespace(goal=SimpleNamespace(explorer=SimpleNamespace(local_pose=np.zeros(3))),
      grasp_track=dict(band=[math.cos(a),math.sin(a)],seen=0.,sigma_m=.03,rgb={'frame_id':1}),carrier_approach={})
    return SimpleNamespace(grasp_fov=option,robots={'r1':r},profiles={}),r


def test_bearing_outside_pan_range_removes_translation(monkeypatch):
    tr,r=case();seen=[]
    def calibrated(plan,pose,profiles,robot_id):
        seen.append(plan);return dict(kind='mecanum',forward=0.,left=0.,turn=.35,duration_s=.1),{}
    monkeypatch.setattr(fov,'command',calibrated)
    state={'efficient_cruise':object()};fine,actions=fov.step(tr,'r1',1.,state)
    assert not fine and len(actions)==1 and actions[0]['forward']==0
    assert seen[0]['path_m']==[[0.,0.]]
    assert seen[0]['heading_rad']==pytest.approx(math.radians(60)+.07)
    assert 'efficient_cruise' not in state and r.carrier_approach['status']=='turn_for_own_beam_view'


def test_off_expired_track_and_in_range_preserve_original_navigation():
    for option,t,angle in [('off',1,105),('turn60_v1',121,105),('turn60_v1',1,40)]:
        tr,r=case(angle,option);assert fov.step(tr,'r1',t,{}) is None


def test_hysteresis_and_no_fabricated_fresh_rgb(monkeypatch):
    tr,r=case(55,'turn60_v1')
    monkeypatch.setattr(fov,'command',lambda *a,**kw:(dict(kind='hold'),{}))
    assert fov.step(tr,'r1',1,{}) is None
    state={'fov_turning':True};assert fov.step(tr,'r1',1,state) is not None
    assert r.grasp_track['seen']==0 and r.grasp_track['rgb']=={'frame_id':1}
    r.goal.explorer.local_pose[2]=math.radians(20)
    assert fov.step(tr,'r1',2,state) is None and 'fov_turning' not in state


def test_anticipatory_candidate_and_mixed_axis_rejection(monkeypatch):
    tr,r=case(50,'turn45_v1')
    monkeypatch.setattr(fov,'command',lambda *a,**kw:(dict(kind='mecanum',forward=.35,left=0,turn=0,duration_s=.1),{}))
    with pytest.raises(ValueError,match='ROTATION_ONLY'):fov.step(tr,'r1',1,{})


def test_collision_guard_holds_except_explicit_dev_light(monkeypatch):
    tr,r=case();events=[];tr.event=lambda *a,**kw:events.append(kw)
    monkeypatch.setattr(fov,'projected_clear',lambda *a:False)
    monkeypatch.setattr(fov,'command',lambda *a,**kw:(dict(kind='mecanum',forward=0.,left=0.,turn=.35,duration_s=.1),{}))
    tr.dev_light=False
    assert fov.step(tr,'r1',1,{})[1]==[dict(kind='hold')]
    tr.dev_light=True
    assert fov.step(tr,'r1',1,{})[1][0]['turn']==.35
    assert len(events)==2
