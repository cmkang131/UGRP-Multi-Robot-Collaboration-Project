"""search_body_scan_v1: static-map next-best-view search, kinematic closed loop.

No MuJoCo. A fake world integrates the issued wheel pulses with a response
gain different from the teacher's belief (drift), applies static-wall line of
sight and a 54 deg camera cone, and delivers a band measurement only when the
cone sees the band. Seed 76015 of the GCP gate started with the target hidden
behind zone_wall_divider_1 and r1 only ever turned in place.
"""
import math
import pytest
from harness.grasp_act_visible_world import VisibleWorld,command_delta
from harness.visual_arm import PULSE_PER_DEGREE
from scripts.zone_teacher import FOLDED
from sim.grasp_act_search import StaticMapSearch,segment_hits_rect,SECTOR_RAD
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher

BOUNDS=(-1.05,5.4,-3.15,1.45)
RECTS=((2.2,-1.675,.025,1.475,0.),(2.2,.875,.025,.575,0.))
START=(2.5906,.0200,-2.9492)          # 76015 r1 at 1.8 s
BAND=(1.640,-.9385,math.atan2(.9607,-.2776)+0.)   # blue band centre and beam yaw
HFOV=math.radians(54)


def wrap(x):return math.atan2(math.sin(x),math.cos(x))


def make_teacher(**kw):
    return VisibleOnlyGraspTeacher('r1','blue',FOLDED,bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',
        teacher_search='search_body_scan_v1',odometry_gain=.75,static_map={'bounds':BOUNDS,'rects':RECTS},**kw)


def run_loop(start=START,band=BAND,limit=40.,true_gain=.72,rects=RECTS):
    t=make_teacher();model=VisibleWorld('r1','blue',initial_pose=list(start),response_gain=.75)
    pose=list(start);log=[]
    for i in range(int(limit*10)):
        now=i*.1
        pan=wrap(math.radians((t.sink.pwm[6]-1500)/PULSE_PER_DEGREE))
        d=(band[0]-pose[0],band[1]-pose[1]);dist=math.hypot(*d)
        bearing=wrap(math.atan2(d[1],d[0])-pose[2]-pan)
        clear=not any(segment_hits_rect(pose[:2],band[:2],r) for r in rects)
        ms=[]
        if clear and dist<2.5 and abs(bearing)<HFOV/2:
            c,s=math.cos(pose[2]),math.sin(pose[2])
            ms=[{'id':'band_blue','kind':'band','xyz':[c*d[0]+s*d[1],-s*d[0]+c*d[1],.03],'yaw':band[2]-pose[2],'visible_n':15,'probe_N':15}]
        world=model.observe(ms,now)
        if ms:return now,t,log
        value,_=t.step(world,now)
        if t.outcome is not None:return now,t,log
        model.issue(value);t.remember_applied(value)
        dx,dy,da=command_delta(value,.1,true_gain);c,s=math.cos(pose[2]),math.sin(pose[2])
        pose=[pose[0]+c*dx-s*dy,pose[1]+s*dx+c*dy,pose[2]+da];log.append(list(pose))
    return None,t,log


def test_segment_clip_hits_thin_wall_and_door_gap():
    assert segment_hits_rect((2.59,.02),(1.64,-.94),RECTS[0])
    assert not segment_hits_rect((2.1,-.07),(1.64,-.94),RECTS[0])


def test_candidates_stay_clear_of_walls_and_sweep_is_blocked_by_divider():
    s=StaticMapSearch(BOUNDS,RECTS)
    assert all(abs(c[0]-2.2)>=.22 or -.2<=c[1]<=.3 or c[1]>1.5 or c[1]<-3.2 for c in s.candidates)
    mask,_=s.visibility((2.59,.02))
    target=min(range(len(s.cells)),key=lambda i:math.dist(s.cells[i],(1.64,-.94)))
    assert not mask[target]          # divider hides the blue end from the start pose


def test_seed_76015_geometry_is_found_by_moving_not_only_turning():
    found,t,log=run_loop()
    assert found is not None and found<t.SEARCH_LIMIT_S+3.
    assert max(math.dist(p[:2],START[:2]) for p in log)>.3       # actually left the start spot
    stages=[r['stage'] for r in t.search_log]
    assert stages.count('swept')>=2 and 'move' in stages
    assert t.outcome is None


def test_search_never_reads_object_or_peer_positions():
    # Identical perceived input (no band) with different hidden truth gives identical commands.
    runs=[]
    for band in (BAND,(4.5,-2.5,0.)):
        t=make_teacher();m=VisibleWorld('r1','blue',initial_pose=list(START),response_gain=.75);out=[]
        for i in range(120):
            w=m.observe([],i*.1);v,_=t.step(w,i*.1);m.issue(v);t.remember_applied(v);out.append(v['wheels']+list(v['pwm'].values()))
        runs.append(out)
    assert runs[0]==runs[1]


def test_unfindable_target_times_out_with_explicit_outcome():
    walled=RECTS+((1.64,-.94,.6,.6,0.),)    # not in the teacher's map: target never visible
    found,t,_=run_loop(rects=walled,limit=45.)
    assert found is not None and t.outcome=='search_timeout'
    assert found>=t.SEARCH_LIMIT_S


def test_search_mode_requires_stability_and_map():
    with pytest.raises(ValueError):VisibleOnlyGraspTeacher('r1','blue',FOLDED,bounds=(-20,20,-20,20),teacher_search='search_body_scan_v1')
    with pytest.raises(ValueError):VisibleOnlyGraspTeacher('r1','blue',FOLDED,bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',teacher_search='search_body_scan_v1')
