"""Partial geometry association and navigation-vs-observation retry contracts."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness.e2e_boundary_association import Association, overlap, install
from harness.e2e_boundary_views import CandidateNavigator


def fixture():
    candidate = dict(kind='B', source='own', center_m=[1., 0.],
                     observation=dict(partial_extent=True, bounds_m=[[0.,-.5],[2.,.5]]))
    boundary = dict(complete=True, white_markers=3, center=[1.,-.6],
                    polygon=[[.5,-1.1],[1.5,-1.1],[1.5,-.1],[.5,-.1]])
    gate = SimpleNamespace(current=None, references={})
    gate.remember_B = lambda: gate.references.setdefault('B', copy.deepcopy(gate.current))
    goal = SimpleNamespace(entities={'B':candidate}, e2e_gate=gate, event=lambda *a, **k:None)
    return goal, boundary


def receive(a, boundary, i, t):
    a.goal.e2e_gate.current = dict(boundary=boundary, ref=dict(frame_id=i,t_sim=t))
    a.observe()


def test_complete_boundary_replaces_partial_centroid_only_after_fresh_stable_overlap():
    g,b=fixture();a=Association(g)
    assert overlap(g.entities['B'], b) == pytest.approx(.4)
    for i in range(2):
        receive(a,b,i,i*.2);assert not g.e2e_gate.references
    receive(a,b,2,.4)
    assert g.e2e_gate.references['B']['boundary']==b
    assert g.entities['B']['center_m']==[1.,-.6] and a.last['accepted']
    # Existing GoalRoute must not overwrite the anchored full-region endpoint.
    g.entities['B']['center_m']=[1.,0.]
    receive(a,None,3,.6)
    assert g.entities['B']['center_m']==[1.,-.6]


@pytest.mark.parametrize('change', ['partial','markers','disjoint','peer','replay','gap','unstable'])
def test_association_rejects_incomplete_unrelated_replayed_or_unstable_evidence(change):
    g,b=fixture();a=Association(g)
    if change=='partial':b['complete']=False
    if change=='markers':b['white_markers']=2
    if change=='disjoint':b['polygon']=[[10,10],[11,10],[11,11],[10,11]]
    if change=='peer':g.entities['B']['source']='peer'
    for i in range(3):
        if change=='unstable':b['center']=[1.+i,-.6]
        receive(a,b,0 if change=='replay' else i,i*(1. if change=='gap' else .2))
    assert not g.e2e_gate.references


def test_navigation_failures_have_finite_separate_budget_and_off_preserves_three_attempts():
    g,_=fixture();g.explorer=SimpleNamespace(map_to_odom=np.zeros(3))
    n=CandidateNavigator(SimpleNamespace(pose=np.zeros(3)),g)
    for i in range(3):
        n.view_target_own=np.array([i,0.]);n.end_view(i,'B_view_path_lost')
    assert not n.can_attempt()
    n.retry_option='navigation_v1'
    assert n.can_attempt() and n.completed_views==0
    for i in range(3,6):n.end_view(i,'B_view_action_failed')
    assert not n.can_attempt() and n.navigation_failures==6
    n=CandidateNavigator(SimpleNamespace(pose=np.zeros(3)),g);n.retry_option='navigation_v1'
    for i in range(3):n.end_view(i,'B_view_observed_still_unconfirmed')
    assert not n.can_attempt() and n.navigation_failures==0


def test_bundle_default_identity_three_candidates_relay_and_real_wiring():
    from scripts.run_e2e_ownmap_live import bundle
    from scripts.s4_proxy_relay import accepted_call_id
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options
    x=object();assert install(x) is x
    kw=dict(enabled=True,stall_odometry='rgb_vo_us_v1',ultrasonic_front='on_v1',
        exploration_progress='frontier_progress_v1',boundary_views='candidate_views_v1',b_marker_detect='contrast_v1',
        vo_floor_mask='homography_v1',vo_rotation_policy='no_ransac_v1',explore_deadlock='replan_v1')
    old=bundle('sha',61001,'study_gemma4_31b_v1',**kw)
    assert old==bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_association='off',boundary_retry='off')
    for association,retry in [('extent_v1','off'),('off','navigation_v1'),('extent_v1','navigation_v1')]:
        b=bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_association=association,boundary_retry=retry)
        assert b['execution_bundle_id']=='e2e-boundary-repair-v211'
        assert b['e2e_options']['boundary_association']==association
        assert b['e2e_options']['boundary_retry']==retry
    for name in ['e2e-idle-a-s61001-r2','e2e-idle-b-s61003-r3']:
        assert accepted_call_id(name+':call-0001-r1:1')
    assert not accepted_call_id('e2e-idle-a-s61010-r2:call-0001-r1:1')
    cov=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    r=Robot('r1',61001,cov,Options(),exploration_progress='frontier_progress_v1',
        boundary_views='candidate_views_v1',boundary_association='extent_v1',boundary_retry='navigation_v1')
    assert isinstance(r.goal.boundary_association,Association)
    assert r.goal.explorer.navigator.retry_option=='navigation_v1'


def test_recorded_full_boundary_replay_overcomes_partial_centroid_rejection():
    replay=json.loads(Path('experiments/2026-10-12-e2e-idle/boundary-repair-replay.json').read_text())
    g,_=fixture();a=Association(g)
    for r in replay['rows']:
        g.entities['B']=copy.deepcopy(r['candidate'])
        g.e2e_gate.current=copy.deepcopy(r)
        assert np.linalg.norm(np.asarray(r['boundary']['center'])-r['candidate']['center_m'])>.20
        a.observe()
    assert g.e2e_gate.references and a.last['accepted']


def test_native_coverage_distinguishes_unknown_from_obstacles_without_making_free_cells():
    from harness import e2e_boundary_views as v
    from harness.public_navigation_unknown import UnknownCostmap
    g,_=fixture();g.explorer=SimpleNamespace(map_to_odom=np.zeros(3))
    n=CandidateNavigator(SimpleNamespace(pose=np.zeros(3)),g)
    n.coverage_option=v.COVERAGE_OPTION
    c=UnknownCostmap(np.full((100,100),255,np.uint8),[-2.5,-2.5],.05)
    before=c.raw.copy();path=[[0.,0.],[.5,0.]]
    assert not v.observed_path_clear(c,[0,0,0],path,0)
    assert n.coverage_check(c,[0,0,0],path,0,1.)
    assert n.coverage_would_stops==1 and np.array_equal(before,c.raw)
    # Known occupied perimeter remains rejected by the native planner.
    c.raw[:]=254;c.costs=c.inflate()
    assert not n.coverage_check(c,[0,0,0],path,0,2.)
    assert not n.coverage_check(c,[0,0,0],[],0,3.)


def test_native_coverage_bundle_is_dev_only_and_off_is_identical():
    from scripts.run_e2e_ownmap_live import bundle
    kw=dict(enabled=True,stall_odometry='rgb_vo_us_v1',ultrasonic_front='on_v1',
        exploration_progress='frontier_progress_v1',boundary_views='candidate_views_v1',b_marker_detect='contrast_v1',
        vo_floor_mask='homography_v1',vo_rotation_policy='no_ransac_v1',explore_deadlock='replan_v1',
        boundary_association='extent_v1')
    old=bundle('sha',61001,'study_gemma4_31b_v1',**kw)
    assert old==bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_coverage='off')
    with pytest.raises(ValueError,match='DEV_V211'):
        bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_coverage='native_v1')
    for retry in ('off','navigation_v1'):
        new=bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_coverage='native_v1',boundary_retry=retry,dev_light=True)
        assert new['execution_bundle_id']=='e2e-boundary-native-v212'
        assert new['e2e_options']['boundary_coverage']=='native_v1'
