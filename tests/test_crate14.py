"""Crate14 saved/numerical regressions; physics and render are forbidden."""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import pytest
from scripts.run_crate_teacher import make_grasp_teacher, run
from scripts.zone_teacher import FOLDED
from sim.crate_alignment_v14 import MODE, STATION_M, OUTER, pick_closed_pwm, stance_valid, peer_blocks_stances
from sim.crate_cartesian_lift import plan_lift
from sim.grasp_act_teacher import local

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(autouse=True)
def no_physics(monkeypatch):
    import mujoco
    def forbidden(*a, **k):
        raise AssertionError('physics/render forbidden')
    for key in ('mj_step', 'mj_forward', 'Renderer'):
        monkeypatch.setattr(mujoco, key, forbidden)


def teacher(mode=MODE):
    return make_grasp_teacher('r1', 'teal', FOLDED, teacher_stability='align_relook_v1',
        teacher_search='search_reacquire_v1', approach_goal_set='approach_goal_set_v1',
        crate_lift_pose='crate_antipodal_grasp_v1', crate_approach_recovery='crate_approach_recovery_v1',
        crate_wall_footprint='crate_footprint_v1', crate_stances='crate_stances_v1',
        crate_pulse_safety='crate_no_closer_v1', crate_candidate_recovery='crate_candidates_v1', crate_alignment=mode)


def world(x=STATION_M, y=0.):
    return {'t': 1., 'robots': {'r1': {'pose': [0., 0., 0.]}}, 'objects': {}, 'walls': [],
            'beam': {'pose': [x+.1, y, 0.], 'ends': {'teal': [x, y, .02396]}},
            'visibility': {'r1': {'visible_probes': 15, 'objects': [], 'peers': []}}}


def prepared(t):
    t.folded_ready = True
    t.approach_plan_valid = True
    t.phase = 'align'
    return t


def test_79317_coupled_lift_failure_cannot_stay_all_axes_off():
    w=world(.2001,-.0167);t=prepared(teacher());t.align_active=[False]*3
    assert not t.ready_geometry(w)
    cmd,ready=t._approach(w,1.)
    assert not ready and any(cmd['wheels']) and any(t.align_active)
    # Inactive Schmitt region: explicitly force the largest normalized axis.
    t.align_active=[False]*3;t._resume_alignment((.0008,.003,.007))
    assert t.align_active==[True,False,False]


def test_actual_queued_descent_endpoint_is_the_feasibility_input():
    w=world();t=prepared(teacher());t.phase='ready'
    assert t.ready_geometry(w)
    expected=pick_closed_pwm(STATION_M,0.,.02396)
    t._queue_pick(w,1.)
    # Apply only the queued issued samples, without a simulator.
    t.arm.tick(t.arm.until)
    assert all(t.sink.pwm[s]==expected[s] for s in expected)
    assert plan_lift(t.sink.pwm)[0] is not None


def test_stance_edges_reject_fragile_79316_angle_and_distances_are_inside_window():
    import math
    w=world();g=w['beam']['ends']['teal']
    def pose(deg):
        a=math.radians(deg);return (g[0]-STATION_M*math.cos(a),g[1]-STATION_M*math.sin(a),a)
    assert stance_valid(w,'r1','teal',pose(0))
    assert stance_valid(w,'r1','teal',pose(15))
    assert not stance_valid(w,'r1','teal',pose(17.5))
    assert teacher().approach_distances==(STATION_M,)
    assert teacher('off').staging_distance==pytest.approx(.1962)


def test_ready_wait_keeps_servo_and_hidden_input_does_not_grant_ready():
    t=prepared(teacher());t.phase='ready';w=world(STATION_M+.0008)
    assert t.ready_geometry(w)
    cmd,ready=t._wait_ready(w,1.)
    assert any(cmd['wheels']) and not ready
    w['visibility']['r1']['visible_probes']=4
    assert not t.ready_geometry(w)


def test_peer_disc_pause_resumes_and_static_block_does_not_pause():
    w=world();w['robots']['r2']={'pose':[0.,0.,0.], 'radius':.17}
    t=prepared(teacher())
    assert peer_blocks_stances(w,t)
    assert not t._plan_approach(w,1.)
    t._staging_recovery(w,1.)
    t._staging_recovery(w,21.)
    assert t.outcome is None and t.staging_paused_s==20.
    t=prepared(teacher())
    t.staging_since=1.;t.staging_peer_blocked=True
    assert not t._staging_expired(1.)
    assert not t._staging_expired(21.)
    assert t.staging_elapsed_s==0. and t.staging_paused_s==20.
    t.staging_peer_blocked=False
    assert not t._staging_expired(32.9)
    assert t._staging_expired(33.)
    w['walls']=[(0.,0.,3.,3.,0.)]
    assert not peer_blocks_stances(w,teacher())
    peer=teacher()
    assert not peer._peer_wait_expired(1.,True)
    assert not peer._peer_wait_expired(21.,True)
    assert not peer._peer_wait_expired(22.,False)
    assert peer._peer_wait_expired(34.,False)
    old=teacher('off');old.staging_since=1.
    assert old._staging_expired(13.)


def test_profile_preflight_rejects_unsafe_modes_before_world(tmp_path):
    with pytest.raises(ValueError,match='held_object'):
        run({},tmp_path/'none',crate_profile='crate14_v1')
    assert not (tmp_path/'none').exists()


def test_new_plan_distribution_los_and_clearance():
    from scripts.make_crate_teacher_plan import prepare,station_clearance
    p=prepare(count=2,seed=79450,split='crate14_diagnostic',assignment='fixed_rgb_lugs_v1',
              scenario_set='v6',near_wall_policy='exclude_report_v1',crate_profile='crate14_v1')
    assert all(min(station_clearance(e).values())>=.34 and e['start_los_audit']['accepted'] for e in p['episodes'])
    d=p['start_distribution']
    assert d['proposals']==d['station_rejected']+d['los_rejected']+p['near_wall_filter']['drawn_episode_count']
    assert d['los_tested']==d['proposals']-d['station_rejected']
    assert len(d['rejected_starts'])==d['rejected']


def test_queue_is_review_only_with_3_reproductions_and_10_fresh():
    path=ROOT/'experiments/2026-10-14-crate-teacher/crate14_queue.py'
    spec=importlib.util.spec_from_file_location('queue14',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    q=m.build('f'*40,{})
    assert len(q['runs'])==13 and q['crate_profile']=='crate14_v1'
    assert [r['seed'] for r in q['runs'] if r['stage']=='reproduction']==[77990,79314,79317]
    def check(v):
        if isinstance(v,dict):
            for k,item in v.items():
                if k in ('approved','enabled','ready','stage_ready'):
                    assert item is False or isinstance(item,dict) and not any(item.values())
                check(item)
        elif isinstance(v,list):
            for item in v:check(item)
    check(q)
