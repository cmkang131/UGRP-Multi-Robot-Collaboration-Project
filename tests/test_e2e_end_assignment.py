import math
import pytest
from harness.e2e_end_assignment import Selector

B=dict(pose_own_m=[0.,0.,0.],rgb=dict(t_sim=1.,frame_id=1,sha256='a'*64))
def test_locked_axis_does_not_flip_when_B_estimate_crosses_beam():
 s=Selector('r2','lock_v1');a=s.candidates(B,[2,0],[1,1,0]);chosen,_=s.choose(a)
 b=s.candidates(B,[-2,0],[1,1,0]);second,_=s.choose(b)
 assert chosen['grip_own_m']==second['grip_own_m']==[.27,0.]

def test_occupied_end_is_not_model_or_fallback_selectable():
 s=Selector('r2','gemma_v1');a=s.candidates(B,[2,0],[1,1,0]);s.choose(a)
 s.blocked.add('end1');a=s.candidates(B,[2,0],[1,1,0])
 assert s.choose(a)[0]['id']=='end0'
 with pytest.raises(ValueError,match='OCCUPIED'):s.choose(a,reply=dict(choice='end1',message='',reason=''))

def test_no_comm_blocks_both_input_and_output_side_channels():
 s=Selector('r1','gemma_v1');a=s.candidates(B,[2,0],[1,1,0])
 with pytest.raises(ValueError,match='NO_COMM_PEER'):s.context(a,delivered_text=['peer'])
 with pytest.raises(ValueError,match='NO_COMM_MESSAGE'):s.choose(a,reply=dict(choice='end0',message='claim',reason=''))
 assert s.choose(a,reply=dict(choice='end1',message='',reason='own RGB'))[1]['source']=='judgment_model'

def test_fixed_channel_only_accepts_fixed_symbols_and_both_blocked_waits():
 s=Selector('r1','gemma_v1',condition='fixed_signal');s.blocked.update(['end0','end1']);a=s.candidates(B,[2,0],[1,1,0])
 assert s.choose(a)[0] is None
 with pytest.raises(ValueError,match='FIXED_SIGNAL'):s.choose(a,reply=dict(choice='wait',message='hidden pose',reason=''))

def test_off_does_not_assert_occupancy():
 s=Selector('r1');a=s.candidates(B,[2,0],[1,1,0]);assert s.observe_occupancy(a,[0,0,0],{},b'',1,1,1)=={}

def test_sparse_images_cannot_supply_two_consecutive_occupancy_votes(monkeypatch):
 import harness.e2e_end_assignment as mod
 monkeypatch.setattr(mod,'rgb_peer_regions',lambda jpeg:[{'bbox_px':[0,0,10,10]}])
 monkeypatch.setattr(mod,'occupied_candidates',lambda *args:{'end0':[],'end1':[{'bbox_px':[0,0,10,10]}]})
 s=Selector('r2','rgb_rule_v1');a=s.candidates(B,[2,0],[1,1,0])
 s.observe_occupancy(a,[0,0,0],{},b'jpeg',1,1,1)
 s.observe_occupancy(a,[0,0,0],{},b'jpeg',2,25,25)
 assert s.blocked==set()
 s.observe_occupancy(a,[0,0,0],{},b'jpeg',3,25.4,25.4)
 assert s.blocked=={'end1'}

def test_relay_reserves_full_context_and_retains_ambiguous_cost(tmp_path):
 from scripts.e2e_end_model_relay import Budget
 b=Budget(tmp_path/'budget',attempts=2,usd=.30)
 one=b.admit();two=b.admit();assert (one,two)==(1,2)
 assert b.admit() is None
 b.finish(one,None,{'error':'timeout'})
 b.finish(two,.0001,{'usage':'known'})
 assert b.charged==pytest.approx(b.reserve_usd+.0001)
 assert b.pending==pytest.approx(0.)

def test_relay_never_admits_beyond_reserved_dollar_limit(tmp_path):
 from scripts.e2e_end_model_relay import Budget
 b=Budget(tmp_path/'budget',attempts=600,usd=.10)
 assert b.admit()==1
 assert b.admit() is None
 b.finish(1,None,{})
 assert b.admit() is None

def test_runtime_off_is_exact_noop():
 from types import SimpleNamespace
 from harness.e2e_end_assignment import install,update_station,PARAMS
 from harness.zone_s3_coarse_fine import arm,PARAMS as physical
 tr=SimpleNamespace();install(tr)
 assert vars(tr)=={} and update_station(tr,'r1',1.,{},None) is None
 assert PARAMS['reach_m']==pytest.approx(arm.MOUNT_X_M+physical['pair_radius_m'])

def test_ground_guard_requires_current_beam_not_just_current_rgb(monkeypatch):
 import harness.e2e_end_ground as ground
 monkeypatch.setattr(ground,'occupied',lambda *args:pytest.fail('stale beam used for occupancy'))
 s=Selector('r1','rgb_ground_v2');a=s.candidates(B,[2,0],[1,1,0])
 for frame,now in [(2,1.4),(3,1.8)]:
  row=s.observe_occupancy(a,[0,0,0],{},b'jpeg',frame,now,now)
  assert row['status']=='unknown_no_current_beam_RGB' and not s.blocked

def test_ground_range_disambiguates_same_bearing_and_rejects_clipped_feet():
 import numpy as np
 from harness.e2e_end_ground import foot_point,occupied
 from harness.owncam_view import project_base_points
 from harness.owncam_pair_beam_v2 import pose_of
 servo=pose_of('search');xy=[1.,.05];uv=project_base_points(servo,np.array([[*xy,0.]]))[0]
 bbox=[uv[0]-12,uv[1]-25,uv[0]+12,uv[1]]
 assert foot_point(servo,bbox)==pytest.approx(xy,abs=1e-6)
 c=[dict(id='near',station_own_m=[1.,.05,0.]),dict(id='far',station_own_m=[2.,.1,0.])]
 hits=occupied(c,[0.,0.,0.],servo,[dict(bbox_px=bbox)])
 assert len(hits['near'])==1 and not hits['far']
 assert foot_point(servo,[0,100,30,200]) is None
