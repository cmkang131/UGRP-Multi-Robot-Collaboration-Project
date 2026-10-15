"""Offline active-perception and configuration-space checks; no World/renderer."""
import math
from copy import deepcopy
from collections import Counter
import pytest
from scripts.zone_teacher import FOLDED
from scripts.replay_grasp_act_recovery import KW
from sim.grasp_act_search15_modes import MODES, match
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_reobserve import ActiveReobserve, remembered_blockers
from sim.grasp_act_pregrasp import select_sampled_goal, jaw_geometry, actual_pick_cloud, collision_reason
from sim.grasp_act_teacher import grasp_poses
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit


def world():
    return {'t':10.,'robots':{'r1':{'pose':[-.8,-.3,0]}},'objects':{},'walls':[],
            'beam':{'pose':[0.,0.,0.],'ends':{'teal':[-.27,0.,.024],'blue':[.27,0.,.024]}},
            'visibility':{'r1':{'visible_probes':15,'peers':[],'objects':[],'observations':{}}}}


def teacher(**kwargs):
    t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,**KW,approach_recovery='progress_view_recovery_v3',**kwargs)
    t.folded_ready=True
    return t


def obstacle(w, fresh=False):
    m={'id':'box','kind':'cargo','xyz':[-.5,.14,.02],'radius':.02,
       'top_z_bound_m':.05,'yaw':0.,'seen_t':w['t'] if fresh else w['t']-1.,'visible_n':3,'probe_N':3}
    w['objects']['box']={'xy':m['xyz'][:2],'radius':.02,'top_z_bound_m':.05}
    w['visibility']['r1']['observations']['box']=m
    return m


@pytest.mark.parametrize('key',MODES)
def test_independent_toggles_default_off_and_reject_wrong_profile_before_host(tmp_path,key):
    from scripts.run_grasp_act_teacher import run
    assert teacher().search15_modes[key]=='off'
    with pytest.raises(ValueError,match='search15'):
        run({},tmp_path,**{key:MODES[key]})
    with pytest.raises(ValueError,match='unknown'):
        teacher(**{key:'typo'})
    with pytest.raises(ValueError,match=key):
        match({}, {key:MODES[key]},'gate')


def test_visible_metadata_carries_only_admitted_measurements_and_original_seen_time():
    v=VisibleWorld('r1','teal')
    m={'id':'r2','kind':'robot','xyz':[1.,.2,.03],'yaw':0.,'visible_n':3,'probe_N':6}
    w=v.observe([m],0.)
    assert w['visibility']['r1']['observations']['r2']['seen_t']==0.
    assert v.observe([],1.)['visibility']['r1']['observations']['r2']['seen_t']==0.
    assert not v.observe([],5.3)['visibility']['r1']['observations']
    assert not VisibleWorld('r1','teal').observe([{**m,'visible_n':1}],0.)['visibility']['r1']['observations']


def test_stale_blocker_refresh_replaces_coordinates_without_margin_change():
    w=world();m=obstacle(w);t=teacher(obstacle_reobserve=MODES['obstacle_reobserve'])
    checks=[{'goal':[-.473,0.],'reason':'blocked_goal'}]
    stale=remembered_blockers(w,'r1',checks,True)
    assert set(stale)=={'box'}
    t.reobserver.begin('obstacle',stale,w,t,10.)
    expired=deepcopy(w);expired['objects']={};expired['visibility']['r1']['observations']={}
    assert 'box' in t.reobserver.planning_world(expired,'r1')['objects']
    fresh=deepcopy(w);fresh['t']=10.1
    fresh['visibility']['r1']['observations']['box'].update(seen_t=10.1,xyz=[-.5,.25,.02])
    fresh['objects']['box']['xy']=[-.5,.25]
    t.reobserver.observe(fresh,'r1')
    assert t.reobserver.step(fresh,t,10.1) is None
    assert t.reobserver.events[-1]['reason']=='fresh_measurements_replan'
    assert not remembered_blockers(fresh,'r1',checks,True)
    assert t.reobserver.planning_world(expired,'r1')['objects']['box']['xy']==[-.5,.25]


def test_expired_peer_causes_finite_active_view_and_bounded_retreat():
    w=world();t=teacher(peer_reobserve=MODES['peer_reobserve'])
    m={'kind':'robot','xyz':[.6,.5,.03],'top_z_bound_m':.32,'seen_t':0.}
    t.reobserver.hints['r2']=m;t.peer_wait_ids={'r2'};t.peer_wait_since=9.
    audit=new_input_audit(True,'issued');w=AuditedTeacherInput(w,audit)
    first=t._peer_reobserve_hold(w,10.)
    assert first is not None and t.reobserver.active is not None
    commands=[t.reobserver.step(w,t,10.+i/10) for i in range(1,29) if t.reobserver.active]
    assert any(c and any(c['wheels']) for c in commands)
    assert t.reobserver.active is None
    assert t.reobserver.events[-1]['reason'] in ('retreat_bounded_replan','bounded_reobserve_exhausted_replan')
    assert t.peer_wait_since==9. and t.peer_wait_ids=={'r2'}
    assert audit['held_world_reads']==audit['invisible_measurements']==0
    assert max(e.get('attempt',0) for e in t.reobserver.events)==3


def test_peer_single_glimpse_is_not_clear_but_three_tenths_fresh_is():
    w=world();t=teacher(peer_reobserve=MODES['peer_reobserve']);t.peer_wait_since=9.;t.peer_wait_ids={'r2'}
    m={'id':'r2','kind':'robot','xyz':[1.,0.,.03],'yaw':0.,'seen_t':9.}
    t.reobserver.begin('peer',{'r2':m},w,t,10.)
    for now in (10.,10.1,10.2,10.3):
        w['t']=now;w['robots']['r2']={'pose':[1.,0.,0.]}
        w['visibility']['r1']['peers']=['r2'];w['visibility']['r1']['observations']={'r2':{**m,'seen_t':now}}
        t.reobserver.step(w,t,now)
        if now<10.3:assert t.peer_wait_since==9.
    assert t.peer_wait_since is None and t.reobserver.active is None


def test_reobserve_never_extends_blocked_deadline_and_cannot_restart_forever():
    w=world();t=teacher(**MODES);t.approach_blocked_since=9.
    m=obstacle(w);t.reobserver.begin('obstacle',{'box':m},w,t,10.)
    t._approach_handoff(12.)
    assert t.outcome=='approach_blocked_handoff' and t.approach_blocked_since==9.
    assert t.reobserver.events[-1]['reason']=='approach_deadline'
    assert t.reobserver.begin('peer',{'r2':m},w,t,13.)
    t.reobserver.finish(t,13.1,'test')
    assert t.reobserver.begin('peer',{'r2':m},w,t,14.)
    t.reobserver.finish(t,14.1,'test')
    assert not t.reobserver.begin('peer',{'r2':m},w,t,15.)


def test_sampled_angles_pass_ik_geometry_route_arm_retreat_and_cost_minimum():
    w=world()
    selected,rows=select_sampled_goal(w,'r1','teal',(-2,2,-2,2),True,FOLDED)
    assert len(rows)==65 and {round(r['offset_deg']) for r in rows}==set(range(-90,91,15))
    assert selected is not None
    feasible=[r for r in rows if r['reason']=='feasible']
    assert selected['cost']==min(r['cost'] for r in feasible)
    assert all(r['arm_sweep'] and r['body_sweep'] and r['predicted_visible_probes']>=5 for r in feasible)
    assert all(abs(r['offset_deg'])<=15.00001 for r in feasible)
    assert all(r['reason'] in ('gripper_angle','ik_unreachable') for r in rows if abs(r['offset_deg'])>29)


def test_obstructed_axis_can_select_angled_stance_with_unchanged_clearance():
    w=world();obstacle(w,True)
    selected,rows=select_sampled_goal(w,'r1','teal',(-2,2,-2,2),True,FOLDED)
    assert selected is not None and selected['choice'][0]!=0
    assert any(r['reason']=='blocked_goal' and r['offset_deg']==0 for r in rows)


def test_angle_limit_comes_from_pitched_pad_and_jaw_gap_not_arbitrary_90_degrees():
    _,descent=grasp_poses((.198,0.,.024))
    assert jaw_geometry(math.radians(15),descent[-1])['allowed']
    assert not jaw_geometry(math.radians(30),descent[-1])['allowed']
    assert not jaw_geometry(math.radians(90),descent[-1])['allowed']


def test_arm_sweep_rejects_high_obstruction_despite_free_body():
    w=world();xyz,radii,contact=actual_pick_cloud(FOLDED,(.198,0.,.024))
    base=(-.468,0.,0.)
    w['objects']['high']={'xy':[-.32,0.],'radius':.005,'top_z_bound_m':.4}
    assert collision_reason(w,'r1',base,xyz,radii,contact)=='arm_cargo_sweep:high'


def test_visibility_and_ik_filters_cannot_be_bypassed(monkeypatch):
    import sim.grasp_act_pregrasp as g
    w=world()
    monkeypatch.setattr(g,'band_view',lambda *a:(0,FOLDED))
    selected,rows=g.select_sampled_goal(w,'r1','teal',(-2,2,-2,2),True,FOLDED)
    assert selected is None and 'band_not_visible' in {r['reason'] for r in rows}
    monkeypatch.setattr(g,'grasp_poses',lambda *a:(_ for _ in ()).throw(ValueError('no IK')))
    selected,rows=g.select_sampled_goal(w,'r1','teal',(-2,2,-2,2),True,FOLDED)
    assert selected is None and {r['reason'] for r in rows}=={'ik_unreachable'}


def test_peer_reacquisition_works_while_band_is_outside_camera():
    w=world();t=teacher(**MODES);t.peer_wait_since=9.;t.peer_wait_ids={'r2'}
    m={'id':'r2','kind':'robot','xyz':[1.,0.,.03],'yaw':0.,'seen_t':9.}
    t.reobserver.begin('peer',{'r2':m},w,t,10.)
    w['beam']=None;w['visibility']['r1']['visible_probes']=0
    for now in (10.,10.1,10.2,10.3):
        w['t']=now;w['robots']['r2']={'pose':[1.,0.,0.]}
        w['visibility']['r1']['peers']=['r2'];w['visibility']['r1']['observations']={'r2':{**m,'seen_t':now}}
        t.reobserver.step(w,t,now)
    assert t.peer_wait_since is None and t.reobserver.active is None
    assert not t.ready_geometry(w)


def test_expired_peer_hint_still_blocks_unsafe_retreat_and_camera_sweep():
    w=world();t=teacher(**MODES)
    # This peer expired from the observer. Its last location still constrains recovery motion.
    m={'id':'r2','kind':'robot','xyz':[-.9,-.3,.03],'yaw':0.,'seen_t':0.,'top_z_bound_m':.32}
    t.reobserver.begin('peer',{'r2':m},w,t,10.)
    assert 'r2' in t.reobserver.active['world']['robots']
    before=dict(t.sink.pwm)
    value=t.reobserver.step(w,t,11.9)
    assert not any(value['wheels'])
    assert t.reobserver.active is None and t.reobserver.events[-1]['reason'].startswith('unsafe_motion_replan')
    assert t.sink.pwm==before
