"""Numeric admission/replay and recovery coupling regressions, no plant."""
import copy,json,math
from types import SimpleNamespace
import numpy as np
import pytest
from harness import selfmap4_geometry as g, selfmap5_registration as reg
from harness.reloc12_registration import ransac_hypotheses, replay_packet
from test_selfmap5 import edges_and_lines


def test_raw_covariance_only_changes_reliability_gate(monkeypatch):
 static,_=g.static_input(); edges,lines=edges_and_lines()
 raw=np.diag([.05**2,.05**2,math.radians(2.)**2])
 states=[]
 for enabled in (False,True):
  r=g.StaticRegistration(static,multiframe_registration=reg.OPTION,reloc10_registration_v1=True,reloc12_raw_cov_gate_v1=enabled)
  r.pf.landmark_map.edges=edges
  monkeypatch.setattr(r.pf,'step',lambda **kw:dict(pose=[0,0,0],covariance=raw.tolist(),updated=True,resolved=True,cluster={'mass':1.},sensor={}))
  for i in range(3):r.step(dict(features=lines,segments=[]),[0,0,0],{6:1000+i*300},i,[0,0,0])
  states.append(r)
 assert states[0].map_from_own is None and states[1].map_from_own is not None
 np.testing.assert_allclose(states[1].last['covariance'],reg.calibrated_covariance(raw))
 np.testing.assert_array_equal(states[1].last['reloc12']['reliable_gate_covariance'],raw)
 json.dumps(states[1].last,allow_nan=False)


def evidence(outlier=False, repeated=False):
 edges,lines=edges_and_lines();m=reg.MultiFrameEvidence();m.begin(0)
 # Four good lines, one bad first line: old first-pair/all-lines search fails.
 bad=dict(kind='floor_line',hue=110,endpoints=[[5,5],[6,5]],normal=[0,1])
 m.add(dict(features=([bad] if outlier else [])+lines+copy.deepcopy(lines)),[0,0,0],0)
 if repeated:
  other=copy.deepcopy(edges)
  for e in other:e['a']+=np.array([4,0]);e['b']+=np.array([4,0])
  edges+=other
 return m,edges


def test_ransac_tolerates_first_outlier_but_rejects_two_rooms_and_exhaustion():
 m,e=evidence(outlier=True);p=np.eye(3)*1e-5
 r=ransac_hypotheses(m,e,[0,0,0],p)
 assert r['unique'] and r['support'][0]['inliers']==4
 m,e=evidence(repeated=True)
 assert ransac_hypotheses(m,e,[0,0,0],p)['candidate_count']==2
 m,e=evidence()
 r=ransac_hypotheses(m,e,[0,0,0],p,max_proposals=0)
 assert not r['unique'] and not r['search_complete']


def test_replay_packet_reconstructs_same_hypotheses():
 m,e=evidence(outlier=True);p=np.eye(3)*1e-5
 packet=json.loads(json.dumps(replay_packet(m,[0,0,0],{'features':[]},1)))
 replay=reg.MultiFrameEvidence();replay.frames=packet['frames']
 assert ransac_hypotheses(m,e,[0,0,0],p)==ransac_hypotheses(replay,e,packet['own_odometry_pose'],p)


def test_rotation_search_counts_as_progress_without_relaxing_pose_limits():
 from sim.solo_carry_to_zone import CarryToZone
 c=object.__new__(CarryToZone)
 c.active_recovery=True;c.reloc12_reacquire=True;c.recovery_reason=None;c.failure=None
 c.recovery_count=1;c.recovery_anchor=[0,0];c.stalled_recoveries=1;c.recovery_events=[]
 c.recovery_turn_anchor=0.;c.reacquire_turn_rad=math.radians(25)
 c.loc=SimpleNamespace(pose=[0,0,0],record=lambda:{},sigmas=lambda:[.05,.05,math.radians(17)],ready=lambda t:True)
 assert c.needs_recovery(3.)
 assert c.recovery_count==2 and c.stalled_recoveries==0 and c.failure is None
 assert c.recovery_events[-1]['reason']=='pose_budget'
 c.recovery_reason=None;c.recovery_count=1;c.stalled_recoveries=1
 assert c.needs_recovery(4.) and c.failure=='carry_recovery_no_progress'


def test_reacquire_is_preempted_before_return_then_resumes_same_search(monkeypatch):
 from sim.solo_carry_to_zone import CarryToZone
 from sim.solo_carry_pose import task_start
 from sim.grasp_act_solo_teacher import SoloTeacher,primitives
 from sim.solo_carry9_search import CargoSearch
 static={'bounds_m':[-3,3,-3,3],'obstacles':[],'regions':{'pickup':{'center_m':[0,0],'half_extents_m':[.75,.5]},'zone_A':{'center_m':[1,0],'half_extents_m':[.5,.5]}}}
 c=CarryToZone(static,'A',start=task_start(static),recovery_profile='carry5_active_localization_v1',
  carry5_rank_aware_views_v1=True,carry7_robust_recovery_v1=True,reloc12_carry_reacquire_v1=True)
 ops=primitives();look=SimpleNamespace(armed=True,rank_retry=0,start=lambda *a:None,issue=lambda *a:None)
 t=SoloTeacher('cyan','west',ops.folded,profile='solo_visible_only_v1',held_object_hidden_v1=True,
  setdown_lookaround_v1=True,lookaround=look,rgb_lift_mode='solo_lift_lookback_v1',solo_carry_to_zone_v1=True,carry=c,ops=ops)
 t.phase='carry_reacquire';t.phase_t=0;t.skill_started=0;t.recovery_started=0;t.recovery_return='approach'
 t.recovery_world=[1,0,.024]
 t.reacquirer=CargoSearch(c.loc.pose,t.recovery_world,0,t.sink.pwm,ops,source='previous_own_visible_target')
 search=t.reacquirer;search.stage='body_scan';search.scan_yaw=.6
 monkeypatch.setattr(c.loc,'sigmas',lambda:[.05,.05,math.radians(17)])
 # Even a fresh target cannot return to approach with a spent map pose budget.
 t.step(0,measurement=dict(xyz=[.5,0,.024],yaw=0))
 assert t.phase=='carry_reobserve' and t.reacquirer is search and t.resume_reacquire
 assert c.recovery_reason=='pose_budget'
 t.phase='carry_recover_restore';t.phase_t=0;c.recovery_reason=None
 monkeypatch.setattr(c.loc,'sigmas',lambda:[.05,.05,math.radians(3)])
 t.step(.1)
 assert t.phase=='carry_reacquire' and t.reacquirer is search and search.scan_yaw==.6
 t.step(.2,measurement=dict(xyz=[.5,0,.024],yaw=0))
 assert t.phase=='approach' and t.recovery_world is None


def test_route_rejection_names_wall_and_signed_minimum_gap():
 from harness.reloc12_ledger import route_context
 r=route_context((0,0),(1,0),[],[(.5,0,.05,1,0)],.17,names=['wall_mid'])
 assert r['blocked_object']=='wall_mid' and r['minimum_gap_m']==pytest.approx(-.17)
 assert r['diagnostic_checks']==101


def test_ransac_refreshes_on_pf_update_and_propagates_other_frames(monkeypatch):
 import harness.reloc12_registration as rr
 static,_=g.static_input();r=g.StaticRegistration(static,multiframe_registration=reg.OPTION,
  correction_safety='selfmap6_correction_safety_v1',active_relocalization='reloc8_active_vision_v1',
  reloc10_registration_v1=True,reloc12_raw_cov_gate_v1=True,reloc12_ransac_hypotheses_v1=True)
 calls=[]
 monkeypatch.setattr(rr,'ransac_hypotheses',lambda *a:(calls.append(1) or dict(candidate_count=0,unique=False,candidates=[],search_complete=True)))
 update=[True]
 monkeypatch.setattr(r.pf,'step',lambda **kw:dict(pose=[0,0,0],covariance=np.eye(3).tolist(),updated=update[0],resolved=False,cluster={'mass':0.},sensor={}))
 r.step(dict(features=[],segments=[]),[0,0,0],{6:1500},0,[0,0,0]);update[0]=False
 r.step(dict(features=[],segments=[]),[0,0,0],{6:1500},.2,[.01,0,0])
 assert len(calls)==1 and not r.last['resolved']
 update[0]=True;r.step(dict(features=[],segments=[]),[0,0,0],{6:1500},.4,[.01,0,0])
 assert len(calls)==2
