"""search_body_scan_v1: pan sweep + in-place body scan; no map, no pose anchor, no moves.

Kinematic closed loop (no MuJoCo): a fake world turns by the issued wheel pulses
with a response different from the teacher's belief and shows the band only
when it is inside a 54 deg camera cone within 2.5 m. Gate seed 76015 spun in
place for 60 s because a static wall hid the target; the start distribution now
excludes such starts and a full scan hands off instead of spinning forever.
"""
import json,math
from pathlib import Path
import pytest
from harness.grasp_act_visible_world import VisibleWorld,command_delta
from harness.visual_arm import PULSE_PER_DEGREE
from harness.static_keepouts import segment_hits_rect
from scripts.zone_teacher import FOLDED
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher

HFOV=math.radians(54)
EXP=Path(__file__).parents[1]/'experiments/2026-10-14-e2e18-grasp-rootcause'


def wrap(x):return math.atan2(math.sin(x),math.cos(x))


def make_teacher(**kw):
    return VisibleOnlyGraspTeacher('r1','blue',{**FOLDED,6:1500},bounds=(-20,20,-20,20),
        teacher_stability='align_relook_v1',teacher_search='search_body_scan_v1',**kw)


def loop(rel_deg,*,dist=1.3,limit=40.,true_gain=.73,visible=True):
    """Target at body-relative bearing rel_deg. Returns (found_t, teacher, true poses)."""
    t=make_teacher();model=VisibleWorld('r1','blue');pose=[0.,0.,0.]
    band=(dist*math.cos(math.radians(rel_deg)),dist*math.sin(math.radians(rel_deg)));log=[]
    for i in range(int(limit*10)):
        now=i*.1
        pan=wrap(math.radians((t.sink.pwm[6]-1500)/PULSE_PER_DEGREE))
        d=(band[0]-pose[0],band[1]-pose[1]);bearing=wrap(math.atan2(d[1],d[0])-pose[2]-pan)
        ms=[]
        if visible and abs(bearing)<HFOV/2:
            c,s=math.cos(pose[2]),math.sin(pose[2])
            ms=[{'id':'band_blue','kind':'band','xyz':[c*d[0]+s*d[1],-s*d[0]+c*d[1],.03],'yaw':-pose[2],'visible_n':15,'probe_N':15}]
        world=model.observe(ms,now)
        if ms:return now,t,log
        value,_=t.step(world,now)
        if t.outcome is not None:return None,t,log
        model.issue(value);t.remember_applied(value)
        dx,dy,da=command_delta(value,.1,)  # nominal
        c,s=math.cos(pose[2]),math.sin(pose[2])
        pose=[pose[0]+c*dx*true_gain-s*dy*true_gain,pose[1]+s*dx*true_gain+c*dy*true_gain,pose[2]+da*true_gain];log.append((list(pose),value))
    return None,t,log


@pytest.mark.parametrize('rel',[0,45,90,135,180,-135,-90,-45])
def test_every_body_relative_direction_is_found_without_translating(rel):
    found,t,log=loop(rel)
    assert found is not None and t.outcome is None
    assert found<=t.SEARCH_LIMIT_S
    assert max((math.hypot(p[0],p[1]) for p,_ in log),default=0.)<.12                     # turned in place
    for _,v in log:
        w=v['wheels'];assert w==[0.]*4 or w==[-.35,.35,-.35,.35]            # only the search turn pulse


def test_full_scan_without_sighting_hands_off_instead_of_spinning_for_a_minute():
    found,t,log=loop(0,visible=False,limit=45.)
    assert found is None and t.outcome=='search_timeout_handoff'
    stages=[r['stage'] for r in t.search_log]
    assert stages.count('dwelled')==7 and stages[-1]=='handoff'
    end=t.search_log[-1]['t'];assert 15.<end<=t.SEARCH_LIMIT_S
    turned=log[-1][0][2]
    assert math.degrees(turned)==pytest.approx(315.,abs=25.)                  # seven ~45 deg steps


def test_commands_depend_only_on_own_commands_not_hidden_truth():
    runs=[]
    for rel in (0,180):
        _,t,log=loop(rel,visible=False,limit=12.)
        runs.append([v['wheels']+list(v['pwm'].values()) for _,v in log])
    assert runs[0]==runs[1]


def test_relook_after_a_sighting_never_starts_the_scan():
    t=make_teacher();t.started=True;t.skill_started=0.
    m=VisibleWorld('r1','blue')
    seen=m.observe([{'id':'band_blue','kind':'band','xyz':[.6,0.,.03],'yaw':0.,'visible_n':15,'probe_N':15}],0.)
    t._observe(seen,0.);assert t.ever_seen
    t._begin_relook(.1,'test');assert t.local_seen is None
    t.phase='approach'
    for i in range(1,200):
        v=t._observe(m.observe([],i*.1),i*.1);m.issue(v)
    assert t.phase=='search' and t.sc is None and not t.search_log and t.outcome is None


def test_search_mode_requires_stability():
    with pytest.raises(ValueError):VisibleOnlyGraspTeacher('r1','blue',FOLDED,bounds=(-20,20,-20,20),teacher_search='search_body_scan_v1')
    with pytest.raises(ValueError):VisibleOnlyGraspTeacher('r1','blue',FOLDED,bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',teacher_search='bogus')


def test_visible_start_plans_have_no_wall_between_spawn_and_end_and_old_76015_is_rejected():
    from harness.zone_final_environment import resolve
    from harness.static_keepouts import keepout_rects
    def blocked(e):
        rects=keepout_rects(resolve(e['map_id'])[0]);out=[]
        for rid,end in e['roles'].items():
            bx,by,ba=e['beam_pose'];sg=-1 if end=='teal' else .27/.27
            sg=-1 if end=='teal' else 1
            tgt=(bx+sg*.27*math.cos(ba),by+sg*.27*math.sin(ba))
            out.append(any(segment_hits_rect(e['spawns'][rid][:2],tgt,r) for r in rects))
        return any(out)
    for name in ('teacher-gcp-visible-start-plan.json','teacher-search-diagnostic-plan.json'):
        eps=json.loads((EXP/name).read_text())['episodes'];assert not any(blocked(e) for e in eps),name
    old=json.loads((EXP/'teacher-gcp-fresh-plan.json').read_text())['episodes']
    assert 76015 in [e['seed'] for e in old if blocked(e)]


def test_handoff_is_not_a_physical_failure_stop_and_is_counted_apart():
    from scripts.run_grasp_act_batch import handoff_only,summarize
    row={'status':'complete','exit':0,'physical_success':False,'search_handoff':True,'index':3,
         'teachers':{'r1':{'outcome':'search_timeout_handoff'},'r2':{'outcome':'success'}}}
    assert handoff_only(row)
    assert not handoff_only({**row,'teachers':{'r1':{'outcome':'search_timeout_handoff'},'r2':{'outcome':'episode_timeout'}}})
    s=summarize([row],1);assert s['search_handoff_n']==1 and s['n']==0 and s['N']==1


# This oracle is evaluation-only: the teacher receives only visible relative
# band measurements. No MuJoCo/model/renderer is constructed or called.
def geometric_band(episode,rid,body_yaw,pwm):
    import numpy as np
    from functools import lru_cache
    from sim.grasp_act_gaze import camera_extrinsics
    from sim.masterpi_camera_profile import scaled_camera_matrix,CAMERA_FISHEYE_D
    from harness.zone_final_environment import resolve
    from harness.static_keepouts import keepout_rects
    # Cache only rigid command FK; no stateful simulator or true pose inputs.
    if not hasattr(geometric_band,'fk'):
        geometric_band.fk=lru_cache(maxsize=4096)(lambda pairs:camera_extrinsics(dict(pairs)))
        geometric_band.rects=lru_cache(maxsize=32)(lambda mid:keepout_rects(resolve(mid)[0]))
    origin,axes=geometric_band.fk(tuple(sorted((int(k),v) for k,v in pwm.items())))
    bx,by,ba=episode['beam_pose'];end=episode['roles'][rid]
    offset=-.27 if end=='teal' else .27
    # Original band box: half extents 18/20.5/0.6 mm; 15 inset top probes.
    points=np.array([(offset+x*.018,y*.0205,.033201) for x in (-.9,-.45,0.,.45,.9) for y in (-.9,0.,.9)])
    ca,sa=math.cos(ba),math.sin(ba)
    rot=np.array([[ca,-sa,0],[sa,ca,0],[0,0,1]])
    points=points@rot.T+[bx,by,0.]
    base=np.array([*episode['spawns'][rid][:2],0.])
    c,s=math.cos(body_yaw),math.sin(body_yaw)
    body=np.array([[c,-s,0],[s,c,0],[0,0,1]])
    relative=(points-base)@body
    optical=(relative-origin)@np.asarray(axes).T
    z=optical[:,2];xy=optical[:,:2]/np.maximum(z[:,None],1e-12)
    K=scaled_camera_matrix(640,480);uv=xy*K.diagonal()[:2]+K[:2,2]
    radius=np.linalg.norm(xy,axis=1);theta=np.arctan(radius)
    distorted=theta*(1+sum(k*theta**(2*i+2) for i,k in enumerate(CAMERA_FISHEYE_D)))
    raw=xy*(distorted/np.maximum(radius,1e-12))[:,None]*K.diagonal()[:2]+K[:2,2]
    inside=(z>.005)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)&(raw[:,0]>=0)&(raw[:,0]<640)&(raw[:,1]>=0)&(raw[:,1]<480)
    lens=base+body@origin
    rects=geometric_band.rects(episode['map_id'])
    seen=sum(bool(ok) and not any(segment_hits_rect(lens[:2],p[:2],r) for r in rects)
             for ok,p in zip(inside,points))
    center=np.array([bx+offset*ca,by+offset*sa,.0326])
    return seen,((center-base)@body).tolist(),ba-body_yaw


def geometric_search(episode,rid,*,mode='search_body_scan_v2',gain=.73,hidden=False):
    from scripts.run_grasp_act_teacher import audit_visible_input
    end=episode['roles'][rid];yaw=episode['spawns'][rid][3]
    t=VisibleOnlyGraspTeacher(rid,end,{**FOLDED,6:episode['initial_pan'][rid]},
        bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',teacher_search=mode)
    model=VisibleWorld(rid,end);pwm={str(k):v for k,v in t.sink.pwm.items()}
    audit={'measurement_rows':0,'invisible_measurements':0};commands=[]
    for i in range(600):
        now=i*.1;n,xyz,ba=geometric_band(episode,rid,yaw,pwm)
        ms=[] if hidden or n<5 else [{'id':'band_'+end,'kind':'band','xyz':xyz,'yaw':ba,'visible_n':n,'probe_N':15}]
        audit_visible_input(audit,ms)
        value,_=t.step(model.observe(ms,now),now)
        if t.ever_seen:
            assert t.phase in ('approach','align','ready')
            return now,t,commands,audit
        commands.append(value);model.issue(value);t.remember_applied(value);pwm=value['pwm']
        dx,dy,da=command_delta(value,.1)
        assert dx==dy==0.  # no commanded translation before a sighting
        yaw+=gain*da
        if t.outcome is not None:return None,t,commands,audit
    pytest.fail('search did not terminate before the episode cap')


DIAGNOSTICS=json.loads((EXP/'teacher-search-diagnostic-plan.json').read_text())['episodes']


@pytest.mark.parametrize('gain',[.69,.73,.78])
@pytest.mark.parametrize('rid',['r1','r2'])
@pytest.mark.parametrize('episode',DIAGNOSTICS,ids=lambda e:str(e['seed']))
def test_six_frozen_starts_acquire_assigned_band_with_real_camera_geometry(episode,rid,gain):
    found,t,commands,audit=geometric_search(episode,rid,gain=gain)
    assert found is not None,(episode['seed'],rid,gain,t.search_log)
    assert t.outcome is None and found<t.SEARCH_V2_LIMIT_S
    assert audit['invisible_measurements']==0


@pytest.mark.parametrize('seed',[78111,79217])
def test_v1_close_stance_misses_all_probes_even_with_360_degrees(seed):
    episode=next(e for e in DIAGNOSTICS if e['seed']==seed)
    for yaw_deg in range(360):
        for w,e in ((700,2440),(820,2320)):
            n,_,_=geometric_band(episode,'r2',math.radians(yaw_deg),{**FOLDED,3:w,4:e,6:1500})
            assert n==0
    found,t,_,_=geometric_search(episode,'r2',mode='search_body_scan_v1')
    assert found is None and t.outcome=='search_timeout_handoff'


@pytest.mark.parametrize('pan',[500,2500])
def test_v2_unseen_scan_covers_every_pitch_and_settles_issued_pwm(pan):
    from copy import deepcopy
    ep=deepcopy(DIAGNOSTICS[0]);ep['initial_pan']['r1']=pan
    found,t,commands,audit=geometric_search(ep,'r1',hidden=True)
    assert found is None and t.outcome=='search_timeout_handoff'
    circles=[r for r in t.search_log if r['stage']=='circle_complete']
    assert len(circles)==3 and all(r['command_estimated_yaw_deg']>=390 for r in circles)
    assert t.search_log[-1]['stage']=='handoff'
    assert t.search_log[-1]['t']<t.SEARCH_V2_LIMIT_S
    # Each new turning posture was issued with stopped wheels for >=0.3 s.
    for i,v in enumerate(commands):
        if any(v['wheels']) and not any(commands[i-1]['wheels']):
            assert i>=4
            assert all(p['pwm']==v['pwm'] and not any(p['wheels']) for p in commands[i-4:i])
    assert audit['invisible_measurements']==0
    # A probe may keep ticking after a terminal result; never turn again or
    # index past the last pitch while the runner finishes its fixed clock.
    terminal=list(t.search_log)
    for i in range(10):
        _,v=t._search_step_v2(60.+i*.1,60.+i*.1)
        assert not any(v['wheels'])
    assert t.search_log==terminal


def test_pair_handoff_finalization_preserves_failures_and_gate_denominator():
    from types import SimpleNamespace
    from scripts.run_grasp_act_teacher import finalize_outcomes
    from scripts.run_grasp_act_batch import handoff_only,summarize
    def result(peer=None,complete=False):
        ts={'r1':SimpleNamespace(outcome=peer,command_complete=complete),
            'r2':SimpleNamespace(outcome='search_timeout_handoff',command_complete=False)}
        finalize_outcomes(ts,strict=True,joint_held=False)
        return {'status':'complete','exit':0,'search_handoff':True,'physical_success':False,
                'index':5,'teachers':{rid:vars(t) for rid,t in ts.items()}}
    row=result();assert row['teachers']['r1']['outcome']=='peer_search_handoff'
    assert handoff_only(row)
    assert not handoff_only(result('alignment_no_progress'))
    assert not handoff_only(result(complete=True))
    assert not handoff_only(result('episode_timeout'))
    summary=summarize([row,{'status':'interrupted','exit':130}],6)
    assert (summary['n'],summary['N'],summary['planned_N'])==(0,1,6)
    assert summary['search_handoff_rate']==1. and summary['search_handoff_indices']==[5]


@pytest.mark.parametrize('heading_delta',[90,180,270])
@pytest.mark.parametrize('gain',[.69,.78])
def test_v2_close_target_behind_initial_heading_is_found_during_turn(heading_delta,gain):
    from copy import deepcopy
    ep=deepcopy(next(e for e in DIAGNOSTICS if e['seed']==79217))
    ep['spawns']['r2'][3]+=math.radians(heading_delta)
    ep['initial_pan']['r2']=1500
    found,t,commands,audit=geometric_search(ep,'r2',gain=gain)
    assert found is not None and found<t.SEARCH_V2_LIMIT_S
    assert any(any(c['wheels']) for c in commands)
    assert audit['invisible_measurements']==0


def test_v2_unseen_commands_do_not_depend_on_hidden_geometry():
    from copy import deepcopy
    a=deepcopy(DIAGNOSTICS[0]);b=deepcopy(DIAGNOSTICS[-1])
    a['initial_pan']['r1']=b['initial_pan']['r1']=500
    _,_,ca,_=geometric_search(a,'r1',hidden=True)
    _,_,cb,_=geometric_search(b,'r1',hidden=True)
    assert ca==cb
