"""Search17 geometry/recording boundary regressions, no simulator or renderer."""
from copy import deepcopy
import math
import sys
import pytest
from harness.grasp_act_visible_world import command_delta, VisibleWorld, SEARCH17_GAINS
from sim.grasp_act_search17 import MODES, segment_free, nearest_free, escape_command
from sim.grasp_act_search15_modes import match, options, add_arguments
from scripts.replay_grasp_act_search17 import KW
from scripts.zone_teacher import FOLDED
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher, propagate_owned
from sim.grasp_act_reobserve import remembered_blockers, ActiveReobserve


def teacher(**kw):
    t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,**KW,**kw);t.folded_ready=True
    t.started=True;t.skill_started=0.
    return t


def world():
    return {'t':10.,'robots':{'r1':{'pose':[-.4175,0.,0.]}},'objects':{},'walls':[],
            'beam':{'pose':[0.,0.,0.],'ends':{'teal':[-.27,0.,.024],'blue':[.27,0.,.024]}},
            'visibility':{'r1':{'visible_probes':15,'objects':[],'peers':[],'observations':{}}}}


@pytest.mark.parametrize('key',MODES)
def test_default_off_and_profile_provenance(key):
    import argparse
    parser=argparse.ArgumentParser();add_arguments(parser)
    assert options(parser.parse_args([]))[key]=='off'
    assert teacher().search15_modes[key]=='off'
    with pytest.raises(ValueError,match=key):match({}, {key:MODES[key]},'gate')
    with pytest.raises(ValueError,match='unknown'):teacher(**{key:'unknown'})


@pytest.mark.parametrize('profile',('legacy','pi_geometry_v1','observable_v2','visible_only'))
@pytest.mark.parametrize('pose',('issued','perfect_self_comparison'))
def test_recording_rejects_gt_before_host_or_output(tmp_path,monkeypatch,profile,pose):
    from scripts.run_grasp_act_teacher import run
    if profile=='visible_only' and pose=='issued':return
    with pytest.raises(ValueError,match='recording requires visible_only and issued'):
        run({},tmp_path/'never-created',record_training=True,teacher_profile=profile,self_pose_source=pose)
    assert not (tmp_path/'never-created').exists()


def test_recording_cli_guard_precedes_host_identity(monkeypatch):
    from scripts.run_grasp_act_teacher import main
    import scripts.grasp_act_host as host
    monkeypatch.setattr(host,'identity',lambda *a:pytest.fail('host called before recording guard'))
    monkeypatch.setattr(sys,'argv',['teacher','--plan','does-not-exist','--episode','0','--out','does-not-exist','--record-training'])
    with pytest.raises(ValueError,match='recording requires visible_only and issued'):main()


def test_recording_permitted_input_pair_continues_to_existing_handoff_guard(tmp_path):
    from scripts.run_grasp_act_teacher import run
    with pytest.raises(ValueError,match='visible handoff'):
        run({},tmp_path,record_training=True,teacher_profile='visible_only',self_pose_source='issued')


def test_inflated_start_disc_and_wall_escape_without_weakening_clear_start():
    ds=[(0.,0.,.02)]
    assert segment_free((.1475,0.),(.16,0.),ds,[],.13)
    assert segment_free((.1475,0.),(.1475,.01),ds,[],.13)
    assert not segment_free((.1475,0.),(.1474,.01),ds,[],.13)
    assert not segment_free((.16,0.),(.149,0.),ds,[],.13)
    # A chord with clear endpoints still intersects the disc.
    assert not segment_free((-.2,0.),(.2,0.),ds,[],.13)
    rect=[(0.,0.,.1,.4,0.)]
    assert segment_free((.228,0.),(.24,0.),[],rect,.13)
    assert segment_free((.228,0.),(.228,.02),[],rect,.13)
    assert not segment_free((.228,0.),(.227,0.),[],rect,.13)
    assert not segment_free((.09,0.),(.24,0.),[],rect,.13)


def test_nearest_free_checks_full_connector_and_does_not_delete_hazards():
    ds=[(0.,0.,.02)];before=deepcopy(ds);start=(.1475,0.)
    p=nearest_free(start,(-1,1,-1,1),ds,[],.13)
    assert p==pytest.approx((.15,0.)) and ds==before
    assert segment_free(start,p,ds,[],.13)
    assert nearest_free((0.,0.),(-.1,.1,-.1,.1),[(0.,0.,1.)],[],.13) is None


def test_escape_attempt_precedes_progress_handoff_and_preserves_debt():
    t=teacher(search17_escape=MODES['search17_escape']);w=world()
    # Force an expired window at the original margin violation.
    t.progress.since=0.;t.progress.retried=True;t.progress.best_distance=0.;t.progress.best_angle=0.
    pose,g,heading,goal=t._geometry(w)
    value=t._route(w,goal,heading,10.)
    assert any(value['wheels']) and t.outcome is None and t.progress.since==0.
    dx,dy,_=command_delta(value,.1)
    assert dx<0 and segment_free(pose[:2],(pose[0]+dx,pose[1]+dy),t._constraints(w)[1],[],.13)
    # Bounded escape cannot erase the original timeout indefinitely.
    t._route(w,goal,heading,11.6)
    assert t.outcome=='approach_blocked_handoff'


def test_same_unchanged_escape_candidate_removed_after_three_repeats():
    t=teacher(search17_escape=MODES['search17_escape']);w=world()
    for i in range(4):escape_command(t,w,10.+i*.1)
    assert t.search17_escape_state['excluded']
    assert any(e['event']=='escape_candidate_removed' for e in t.search17_log)


def test_fresh_blocker_retreat_not_instant_fresh_observation_completion(monkeypatch):
    w=world();w['robots']['r1']['pose']=[-.8,0.,0.]
    m={'id':'can','kind':'cargo','xyz':[-.473,.1,.03],'radius':.0314,'top_z_bound_m':.06,
       'yaw':0.,'seen_t':10.,'visible_n':7,'probe_N':7}
    w['objects']['can']={'xy':m['xyz'][:2],'radius':m['radius'],'top_z_bound_m':m['top_z_bound_m']}
    w['visibility']['r1']['observations']['can']=m
    rows=[{'goal':[-.473,0.],'reason':'blocked_goal'}]
    assert not remembered_blockers(w,'r1',rows,True)
    targets=remembered_blockers(w,'r1',rows,True,include_visible=True)
    assert targets.keys()=={'can'}
    t=teacher();a=ActiveReobserve()
    assert a.begin('obstacle',targets,w,t,10.,retreat_first=True)
    # Keep real arm/body safety checks; this clear folded view may retreat.
    value=a.step(w,t,10.)
    assert value is not None
    assert not any(e.get('reason')=='fresh_measurements_replan' for e in a.events)


def test_fixed_calibration_updates_both_memories_without_gt():
    issued={'wheels':[.35]*4,'duration_s':[.1]*4}
    old=command_delta(issued,.1);new=command_delta(issued,.1,mode=MODES['search17_odometry'])
    assert new==pytest.approx(tuple(a*b for a,b in zip(old,SEARCH17_GAINS)))
    model=VisibleWorld('r1','teal',odometry=MODES['search17_odometry']);model.observe([],0.);model.issue(issued)
    assert model.observe([],.1)['robots']['r1']['pose']==pytest.approx(new)
    assert propagate_owned([1.,0.,.03],issued,.1,mode=MODES['search17_odometry'])[0]==pytest.approx(1.-new[0])
    with pytest.raises(ValueError,match='GT self'):model.observe([],.2,comparison_pose=[1.,2.,0.])
    with pytest.raises(ValueError,match='issued'):VisibleWorld('r1','teal',pose_source='perfect_self_comparison',odometry=MODES['search17_odometry'])


def test_expansion_keeps_physical_jaw_bound():
    from sim.grasp_act_pregrasp import select_sampled_goal
    w=world();w['robots']['r1']['pose']=[-.8,0.,0.]
    selected,rows=select_sampled_goal(w,'r1','teal',(-2,2,-2,2),True,FOLDED,choices=[(math.pi/3,.203)])
    assert selected is None and rows[0]['reason']=='gripper_angle'


def test_three_saved_failure_inputs_emit_checked_recovery_pulses():
    import json
    from pathlib import Path
    from sim.grasp_act_search17 import pulse_free
    for row in json.loads((Path(__file__).parent/'fixtures/grasp_act_search17.json').read_text()):
        t=VisibleOnlyGraspTeacher(row['rid'],row['end'],row['pwm'],**KW,**{k:v for k,v in MODES.items() if k!='search17_odometry'})
        t.folded_ready=True;t.started=True;t.skill_started=0.;w=row['world'];now=w['t']
        assert not any(row['original_wheels'])
        if row['ep']==25:
            assert not t._plan_approach(w,now)
            assert any(e['event']=='expanded_candidates' for e in t.search17_log)
            assert t.reobserver.active['retreat_first']
            value=t.reobserver.step(w,t,now)
        else:
            value=escape_command(t,w,now)
            radius,discs,rects=t._constraints(w)
            assert pulse_free(w['robots'][row['rid']]['pose'],value,discs,rects,radius)
        assert value is not None and any(value['wheels'])


def test_wheel_deadline_checks_catch_inward_prefix_with_outward_endpoint():
    from sim.grasp_act_search17 import pulse_free
    # Initial leftward phase approaches the disc; the longer positive
    # diagonal later makes the net endpoint outward. The prefix must fail.
    value={'wheels':[-.35,.35,.35,-.35],'duration_s':[.02,.1,.1,.02]}
    pose=(.1475,0.,.15)
    dx,dy,_=command_delta(value,.1)
    endpoint=(pose[0]+math.cos(pose[2])*dx-math.sin(pose[2])*dy,math.sin(pose[2])*dx+math.cos(pose[2])*dy)
    assert segment_free(pose[:2],endpoint,[(0.,0.,.02)],[],.13)
    assert not pulse_free(pose,value,[(0.,0.,.02)],[],.13)


@pytest.mark.parametrize('speed,warn,blocked',[(3.5,False,False),(3.6,True,False),(6.,True,False),(6.01,True,True)])
def test_speed_is_recorded_warning_until_hard_limit(speed,warn,blocked):
    from scripts.run_grasp_act_batch import search17_speed_record
    row={'status':'complete','exit':0,'wall_per_sim':speed}
    r=search17_speed_record([row],1)
    assert r['warning']==warn and r['blocked']==blocked and not r['qualified']
    assert search17_speed_record([row],2)['blocked']
    assert search17_speed_record([{**row,'status':'HOST_ERROR'}],1)['blocked']
