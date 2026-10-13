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
