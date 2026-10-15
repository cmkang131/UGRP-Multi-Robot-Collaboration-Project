"""Offline counterexamples for crate12; no World, renderer or network."""
import math
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit,sourced,admit
from sim.crate_approach_recovery import safe_pulse
from sim.crate_navigation_v12 import WallFootprint,FOOTPRINT,PAD_M
from sim.crate_observation_v12 import (validate_recording,own_lug,fixed_role,tagged_world,
                                      OwnLookaround,look_views)
from sim.grasp_act_release_teacher import PairReleaseCode
from sim.crate_release_teacher import CrateReleaseTeacher
from sim.cargo_teacher_profile import CRATE
from scripts.zone_teacher import FOLDED


def wall():return {'id':'wall_south','kind':'wall','xyz':[0.,-.5,0.], 'yaw':0.,'visible_n':3,'probe_N':3,'half_extents':[2.,.025]}
def band():return {'id':'band_teal','kind':'band','xyz':[.5,0,.023],'yaw':0.,'visible_n':15,'probe_N':15}


def test_only_static_wall_memory_survives_expiry():
    dynamic={'id':'r2','kind':'robot','xyz':[1.,0.,0.],'yaw':0.,'visible_n':3,'probe_N':3}
    for mode,kept in [('off',False),('persistent_walls_v1',True)]:
        m=VisibleWorld('r1','teal',profile=CRATE,static_walls=mode)
        m.observe([wall(),band(),dynamic],0.)
        v=m.observe([],12.)
        assert bool(v['walls'])==kept
        assert v['beam'] is None and 'r2' not in v['robots']


def pulse(w,d=.1):return {'wheels':w,'duration_s':[d if x else 0. for x in w]}


def test_no_closer_allows_yaw_but_no_translation_penetration_or_accumulated_mm_slack():
    pose=(0.,0.,0.);ds=[(.149,0.,.02)];turn=pulse([-.35,.35,-.35,.35])
    assert not safe_pulse(turn,pose,ds,[],.13)
    assert safe_pulse(turn,pose,ds,[],.13,mode='crate_no_closer_v1')
    assert not safe_pulse(pulse([.35]*4),pose,ds,[],.13,mode='crate_no_closer_v1')
    assert safe_pulse(pulse([-.35]*4),pose,ds,[],.13,mode='crate_no_closer_v1')
    # An obstacle crossed between endpoints still rejects the pulse.
    assert not safe_pulse(pulse([.35]*4),pose,[(.008,0.,.001)],[],.001,mode='crate_no_closer_v1')


def test_rectangular_wall_padding_and_swept_rotation():
    w={'robots':{'r1':{'pose':[0.,0.,0.]}},'beam':{'pose':[2.,0.,0.]},'objects':{},
       'walls':[(0.,-.115,2.,.02,0.)]}
    n=WallFootprint(w,'r1',True,CRATE,(-20,20,-20,20))
    assert n.free((0.,0.),0.)
    assert not n.free((0.,0.),math.pi/2)
    assert not n.segment((0.,0.),(0.,0.),0.,math.pi/2)
    # Full finite turn eventually hits with its longer diagonal before 90 deg.
    pose=(0.,0.,math.radians(15))
    assert not safe_pulse(pulse([-.35,.35,-.35,.35]),pose,[],w['walls'],.13,
                          mode='crate_no_closer_v1',wall_footprint=True)


def test_ready_uses_same_rectangular_wall_rule_as_selected_goal():
    from scripts.run_crate_teacher import make_grasp_teacher
    from sim.crate_cartesian_lift import STATION_M
    from sim.grasp_act_visible_route import constraints,free
    t=make_grasp_teacher('r1','teal',FOLDED,teacher_stability='align_relook_v1',
        teacher_search='search_reacquire_v1',approach_goal_set='approach_goal_set_v1',
        crate_lift_pose='crate_antipodal_grasp_v1',crate_approach_recovery='crate_approach_recovery_v1',
        crate_wall_footprint='crate_footprint_v1',crate_pulse_safety='crate_no_closer_v1')
    w={'robots':{'r1':{'pose':[0.,0.,0.]}},'objects':{},
       'beam':{'pose':[STATION_M+.1,0.,0.],
               'ends':{'teal':[STATION_M,0.,.024],'blue':[STATION_M+.2,0.,.024]}},
       'walls':[(0.,-.115,2.,.02,0.)],'visibility':{'r1':{'visible_probes':15}}}
    t.folded_ready=True;t.approach_plan_valid=True
    r,ds,rs=constraints(w,'r1',True,CRATE)
    assert not free((0.,0.),ds,rs,r)
    assert t.ready_geometry(w)
    # Losing the target cannot bypass the retained wall during a search turn.
    t.phase='search'
    w['beam']=None;w['visibility']['r1']['visible_probes']=0
    w['robots']['r1']['pose'][2]=math.radians(15)
    turn={**pulse([-.35,.35,-.35,.35]),'t':0.,'pwm':dict(FOLDED)}
    assert not any(t._check_navigation_pulse(w,turn,0.)['wheels'])
    assert t.crate_recovery_log[-1]['recovery']=='persistent_wall_search_hold'
    t.crate_wall_footprint='off'
    assert t._check_navigation_pulse(w,turn,0.)==turn


def test_provenance_rejects_gt_under_legal_keys_and_nested_laundering():
    a=new_input_audit(True,'issued')
    legacy={'robots':{'r1':{'pose':[9.,9.,9.]}}}
    assert AuditedTeacherInput(legacy,a)['robots']==legacy['robots']  # actual old vulnerability
    with pytest.raises(ValueError,match='untagged'):AuditedTeacherInput(legacy,a,provenance='value_sources_v1')
    with pytest.raises(ValueError,match='provenance'):
        AuditedTeacherInput({'robots':sourced(legacy['robots'],'evaluation_gt')},a,provenance='value_sources_v1')
    with pytest.raises(ValueError,match='provenance'):
        admit(sourced({'innocent_name':sourced(2.,'measured_joint')},'issued_commands'),a)
    x={'robots':sourced(legacy['robots'],'issued_commands')}
    v=AuditedTeacherInput(x,a,provenance='value_sources_v1')
    v['robots']['r1']['pose'][0]=123.
    assert v['robots']['r1']['pose'][0]==9.  # consumer cannot mutate admitted payload


def test_hidden_boundary_removes_cached_cargo_too():
    model=VisibleWorld('r1','teal',profile=CRATE)
    visual=model.observe([band()],0.)
    visual['objects']['crate_1']={'xy':[1.,1.]}
    assert visual['beam'] is not None
    a=new_input_audit(True,'issued')
    w=AuditedTeacherInput(tagged_world(visual,holding=True),a,provenance='value_sources_v1')
    assert w['beam'] is None and 'crate_1' not in w['objects'] and a['held_world_reads']==0


def record_args():return dict(mode='success_measurement',profile='crate12_v1',held_object='hidden_v1',
    own_pose_source='commands',lookaround='setdown_lookaround_own_v2',assignment='fixed_rgb_lugs_v1',release_channel='fixed_signals_v1')


@pytest.mark.parametrize('field,bad',[('held_object','visible_v0'),('own_pose_source','truth_comparison'),
    ('lookaround','setdown_lookaround_v1'),('assignment','nearest'),('release_channel','legacy')])
def test_strict_and_training_preflight_refuse_gt_options(field,bad):
    for mode in ('success_measurement','training'):
        x=record_args();x.update({field:bad,'mode':mode})
        with pytest.raises(ValueError):validate_recording(**x)


def test_runner_refuses_before_creating_output_or_simulator(tmp_path):
    from scripts.run_crate_teacher import run
    out=tmp_path/'never'
    with pytest.raises(ValueError,match='hidden_v1'):run({},out,crate_profile='crate12_v1')
    assert not out.exists()
    x=record_args();x['mode']='training'
    with pytest.raises(ValueError,match='not implemented'):validate_recording(**x)


def frame(end):
    rgb=np.zeros((80,120,3),dtype=np.uint8)
    rgb[30:50,50:75]=[240,130,200]
    rgb[30:50,40:50]=[20,230,180] if end=='teal' else [20,20,240]
    return rgb


def test_assignment_uses_only_fixed_ticket_and_own_rgb():
    assert (fixed_role('r1'),fixed_role('r2'))==('teal','blue')
    assert own_lug(frame('teal'),'r1')['confirmed']
    assert not own_lug(frame('blue'),'r1')['confirmed']
    assert own_lug(frame('blue'),'r2')['confirmed']
    assert not own_lug(np.zeros((80,120,3),np.uint8),'r1')['confirmed']
    # A zone-colour patch without crate body does not become a lug.
    f=frame('blue');f[30:50,50:75]=0
    assert not own_lug(f,'r2')['confirmed']


def release(a):return CrateReleaseTeacher('r1','teal',FOLDED,handoff_pose_estimate=None,zone_rect=(0,0,1,1),input_audit=a)


def test_fixed_release_channel_forbids_margin_side_channel_and_gt_values():
    a=new_input_audit(True,'issued');code=PairReleaseCode(('r1','r2'),channel='fixed_signals_v1',input_audit=a)
    with pytest.raises(ValueError):code.post('r1',sourced({'phase':'look','signal':'INSIDE'},'evaluation_gt'),0.)
    with pytest.raises(ValueError):code.post('r1',sourced({'phase':'look','signal':'INSIDE','margin_m':.3},'own_rgb'),0.)
    with pytest.raises(ValueError):code.post('r1',sourced({'phase':'look margin=.3','signal':'INSIDE'},'own_rgb'),0.)
    for r,signal in [('r1','OUTSIDE'),('r2','INSIDE')]:code.post(r,sourced({'phase':'look','signal':signal},'own_rgb'),0.)
    code.deliver(.2)
    assert code.decide(.2)['shift_m']==.08
    assert all(set(m)=={'phase','signal','t'} for m in code.delivered.values())
    for r in ('r1','r2'):code.post(r,sourced({'phase':'look','signal':'INSIDE'},'own_rgb'),.3)
    code.deliver(.5);assert code.decide(.5)['action']=='lower'


def test_missing_scan_cannot_send_inside_or_outside_and_perception_rejects_gt():
    a=new_input_audit(True,'issued');t=release(a)
    obs={'scan':[],'band':None,'own_band_visible':False,'partner_visible':False}
    with pytest.raises(ValueError):t.perceive(sourced(obs,'evaluation_gt'),0.)
    t.perceive(sourced(obs,'visible_teacher_measurement','issued_commands'),0.)
    t.report(0.);assert admit(t.fixed_message('look',0.),a)['signal']=='UNKNOWN'
    t.last_scan=(0.,[(0.,True)])
    t.last_report={'kind':'inside_lb','margin_m':.01}
    assert admit(t.fixed_message('look',0.),a)['signal']=='UNKNOWN'


def test_lookaround_uses_local_static_frame_and_real_captures_without_gt_fix():
    m=VisibleWorld('r1','teal',profile=CRATE,static_walls='persistent_walls_v1')
    # A far wall provides view directions without colliding with the rotation.
    q=wall();q['xyz'][1]=-2.;m.observe([q],0.)
    scan=OwnLookaround(m);pan=[];wheel=[];captures=[]
    def capture():captures.append(True);return frame('teal')
    for i in range(1500):
        active=scan.step(i*.1,apply_pan=lambda *a:pan.append(a),issue_wheels=lambda *a:wheel.append(a),capture=capture)
        if not active:break
    assert not active and captures and wheel and pan
    assert len(captures)==len(scan.script)
    assert scan.log['pose_updates']==0 and scan.log['identified_landmarks'] is None
    assert all(len(f['rgb_sha256'])==64 for f in scan.log['frames'])
    assert look_views((0,0,0),[{'id':'wall','xy':(1,0)}])!=look_views((0,0,math.pi/2),[{'id':'wall','xy':(1,0)}])
