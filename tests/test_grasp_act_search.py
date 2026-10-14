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
