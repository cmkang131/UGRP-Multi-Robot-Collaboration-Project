"""Search18 geometry, start-node and negative-evidence regressions (no simulator)."""
from copy import deepcopy
import math
import pytest
import sim.grasp_act_search18 as s18
from sim.grasp_act_search18 import (MODES, HALF_X, HALF_Y, REQUIRED_MARGIN_M, body_clearance, body_free,
                                    exact_start_path, navigation, rectangles_overlap)
from sim.grasp_act_search15_modes import match, options, add_arguments, ALL_MODES
from sim.grasp_act_free_space import FreeSpace, ghost_visible_region, DWELL_S
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from scripts.replay_grasp_act_search17 import KW
from scripts.zone_teacher import FOLDED


def teacher(**kw):
    t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,**KW,**kw);t.folded_ready=True
    t.started=True;t.skill_started=0.
    return t


def world(ghost_seen=None):
    w={'t':10.,'robots':{'r1':{'pose':[-.4175,0.,0.]}},'objects':{},'walls':[],
       'beam':{'pose':[0.,0.,0.],'ends':{'teal':[-.27,0.,.024],'blue':[.27,0.,.024]}},
       'visibility':{'r1':{'visible_probes':15,'objects':[],'peers':[],'observations':{}}}}
    return w


@pytest.mark.parametrize('key',MODES)
def test_default_off_and_profile_provenance(key):
    import argparse
    parser=argparse.ArgumentParser();add_arguments(parser)
    assert options(parser.parse_args([]))[key]=='off'
    assert teacher().search15_modes[key]=='off'
    assert ALL_MODES[key]==MODES[key]
    with pytest.raises(ValueError,match=key):match({}, {key:MODES[key]},'gate')
    with pytest.raises(ValueError,match='unknown'):teacher(**{key:'unknown'})


def test_admission_signature_rejects_mode_mismatch():
    from harness.grasp_act_admission import recording_admission
    import inspect
    names=inspect.signature(recording_admission).parameters
    assert all(k in names for k in MODES)


def test_body_clearance_uses_real_rectangle_not_disc():
    # Obstacle on the long (x) axis, then on the short (y) axis of the same body.
    r=.02
    assert body_clearance((0.,0.,0.),[(HALF_X+.05+r,0.,r)],[])==pytest.approx(.05)
    assert body_clearance((0.,0.,0.),[(0.,HALF_Y+.05+r,r)],[])==pytest.approx(.05)
    # Rotating the body by 90 degrees swaps the two axes.
    assert body_clearance((0.,0.,math.pi/2),[(0.,HALF_X+.05+r,r)],[])==pytest.approx(.05)


def test_clearance_corner_is_euclidean_not_sharp_box():
    corner=(HALF_X,HALF_Y);r=.001
    d=.05;ux=uy=1/math.sqrt(2)
    obstacle=(corner[0]+d*ux+r*ux,corner[1]+d*uy+r*uy,r)
    assert body_clearance((0.,0.,0.),[obstacle],[])==pytest.approx(d,abs=1e-6)


def test_wall_rectangle_gap_and_crossing_wall():
    # Wall (half 0.05 x 0.5) 0.1 m ahead of the nose.
    wall=(HALF_X+.1+.05,0.,.05,.5,0.)
    assert body_clearance((0.,0.,0.),[],[wall])==pytest.approx(.1)
    assert body_clearance((.2,0.,0.),[],[wall])==0.
    assert rectangles_overlap((0,0,.1,.1,0.),(.05,.0,.1,.1,math.pi/4))
    assert not rectangles_overlap((0,0,.1,.1,0.),(.5,.0,.1,.1,0.))


def test_margin_is_65mm_and_cannot_be_lowered_outside_analysis(monkeypatch):
    assert s18.MARGIN_M==REQUIRED_MARGIN_M==.065
    d=[(HALF_X+.064+.02,0.,.02)]
    assert not body_free((0.,0.,0.),d,[]) and body_free((0.,0.,0.),[(HALF_X+.066+.02,0.,.02)],[])
    with pytest.raises(ValueError,match='65mm'):body_free((0.,0.,0.),d,[],margin=.05)
    monkeypatch.setattr(s18,'MARGIN_M',.03)
    with pytest.raises(ValueError,match='outside offline analysis'):navigation(teacher(search18_footprint=MODES['search18_footprint']),world())


def test_exact_start_path_uses_actual_start_when_snapped_cell_is_forbidden():
    # Forbidden disc covers the snapped grid cell (0,0) but not the true start.
    hazard=(0.,0.,.03)
    point_free=lambda p:math.dist(p,hazard[:2])>=hazard[2]
    start=(0.04,0.)
    assert point_free(start) and not point_free((0.,0.))
    def edge_free(a,b):
        n=50
        return all(point_free((a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n)) for i in range(n+1))
    path=exact_start_path(start,(0.4,0.),(-.5,.5,-.5,.5),point_free,edge_free)
    assert path is not None and path[0]==start and path[-1]==(0.4,0.)
    assert all(edge_free(a,b) for a,b in zip(path,path[1:]))
    # A blocked goal is never cleared or accepted.
    assert exact_start_path(start,(0.,0.),(-.5,.5,-.5,.5),point_free,edge_free) is None


def test_last_valid_plan_is_retained_only_after_revalidation():
    t=teacher(search18_start_plan=MODES['search18_start_plan']);w=world();w['robots']['r1']['pose']=[-.8,0.,0.]
    nav=navigation(t,w);goal=(-.6,0.)
    path=[(-.9,0.),(-.8,0.),(-.7,0.),goal]
    kept=nav.retained_path((-.8,0.),path,goal,[],[],.13)
    assert kept and kept[0]==(-.8,0.) and kept[-1]==goal
    assert nav.retained_path((-.8,0.),path,(-.5,0.),[],[],.13) is None  # goal changed
    wall=[(-.65,0.,.02,.5,0.)]
    assert nav.retained_path((-.8,0.),path,goal,[],wall,.13) is None   # path now blocked


def anchor(key,t):
    return {'id':key,'kind':'cargo','xyz':[.2,-.6,.03],'radius':.03,'top_z_bound_m':.06,'yaw':0.,'seen_t':t,'visible_n':7,'probe_N':7}


def ghost_world(now,peer_xy,*,anchor_seen=True):
    w=world();w['t']=now
    w['robots']['r1']['pose']=[0.,0.,0.]
    w['robots']['r2']={'pose':[*peer_xy,0.]}
    obs={'r2':{'id':'r2','kind':'robot','xyz':[*peer_xy,.1],'yaw':0.,'radius':.17,'top_z_bound_m':.32,'seen_t':1.,'visible_n':9,'probe_N':9}}
    if anchor_seen:obs['can']=anchor('can',now)
    w['visibility']['r1']['observations']=obs
    return w


def stub(rid='r1'):
    class T:pass
    t=T();t.rid=rid;t.last_command=None;t.sink=type('S',(),{'pwm':dict(FOLDED)})();t.peer_wait_ids={'r2'}
    t.reobserver=type('R',(),{'active':None})()
    return t


def test_ghost_in_view_without_peer_clears_after_dwell_and_never_by_time():
    fs=FreeSpace();t=stub()
    # The peer was last seen straight ahead; it is now absent while a fresh anchor proves vision is alive.
    w0=ghost_world(1.,(.9,0.));w0['visibility']['r1']['peers']=['r2'];fs.update(w0,t,1.)
    assert 'r2' in fs.ghosts
    clear,reason=ghost_visible_region(ghost_world(1.2,(.9,0.)),'r1',fs.ghosts['r2'],t.sink.pwm,1.2)
    assert clear and reason=='covered_empty'
    for k in range(5):
        now=1.2+.1*k;fs.update(ghost_world(now,(.9,0.)),t,now)
    assert fs.cleared and 'r2' in fs.cleared
    assert fs.events[0]['event']=='peer_free_space_clear' and fs.events[0]['dwell_s']>=DWELL_S-1e-6


def test_ghost_outside_view_or_without_fresh_frame_is_kept_even_after_long_time():
    fs=FreeSpace();t=stub()
    w0=ghost_world(1.,(-.9,0.));w0['visibility']['r1']['peers']=['r2'];fs.update(w0,t,1.)
    clear,reason=ghost_visible_region(ghost_world(5.,(-.9,0.)),'r1',fs.ghosts['r2'],t.sink.pwm,5.)
    assert not clear and reason=='outside_view_or_range'
    # Ahead of the camera, but no fresh anchor: an empty frame is not a negative detection.
    clear,reason=ghost_visible_region(ghost_world(50.,(.9,0.),anchor_seen=False),'r1',fs.ghosts['r2'],t.sink.pwm,50.)
    assert not clear and reason in ('no_fresh_frame_anchor','outside_view_or_range')
    for k in range(200):
        now=5.+.5*k
        w=fs.update(ghost_world(now,(-.9,0.)),t,now)
    assert not fs.cleared and 'r2' in w['robots']  # remembered ghost still blocks; no timeout release


def test_visible_peer_is_never_cleared_and_ghost_is_refreshed():
    fs=FreeSpace();t=stub()
    w=ghost_world(2.,(.9,0.));w['visibility']['r1']['peers']=['r2'];w['visibility']['r1']['observations']['r2']['seen_t']=2.
    fs.update(w,t,2.)
    assert not fs.cleared and fs.ghosts['r2']['seen_t']==2.
    clear,reason=ghost_visible_region(w,'r1',fs.ghosts['r2'],t.sink.pwm,2.)
    assert not clear and reason=='peer_seen'


def test_occluder_between_camera_and_ghost_blocks_clearing():
    fs=FreeSpace();t=stub()
    w0=ghost_world(1.,(.9,0.));w0['visibility']['r1']['peers']=['r2'];fs.update(w0,t,1.)
    w=ghost_world(1.2,(.9,0.));w['objects']['crate']={'xy':(.45,0.),'radius':.1,'top_z_bound_m':.4}
    clear,reason=ghost_visible_region(w,'r1',fs.ghosts['r2'],t.sink.pwm,1.2)
    assert not clear and reason=='occluded'
