"""Saved-input/geometry regressions only. Never simulate or render."""
import importlib.util
import json
import math
from copy import deepcopy
from pathlib import Path
import pytest
from harness.grasp_act_visible_world import command_delta
from harness.grasp_act_contract import MEMORY_S
from harness.static_keepouts import polygon_at, rect_corners
from sim.crate_motion_v15 import polygon_gap
from sim.crate_motion_v16 import Navigation, MODE, MAX_EXPANSIONS, rectangle_gap
from sim.crate_navigation_v12 import FOOTPRINT
from sim.cargo_teacher_profile import CRATE
from sim.grasp_act_goal_set import geometry
from sim.crate_observation_v12 import tagged_world
from harness.grasp_act_input_audit import AuditedTeacherInput, new_input_audit
from scripts.run_crate_teacher import run
from test_crate15 import teacher, empty, hold, no_physics

HERE = Path(__file__).resolve().parents[1]/'experiments/2026-10-15-crate16'
CASES = json.loads((HERE/'route-fixtures.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['run'])
def test_saved_routes_and_hidden_lug_search_turn_and_side_view(case):
    w = case['world']; rid = case['robot']; pose = w['robots'][rid]['pose']
    nav = Navigation(w, rid, True, CRATE, (-20, 20, -20, 20), end=case['end'], search=case['kind']=='hidden_lug')
    if case['kind'] == 'saved_route':
        _, _, yaw, goal = geometry(w, rid, case['end'], case['choice'])
        assert nav.path(pose[:2], goal, yaw)
    else:
        assert nav.crate_source == 'memory'
        value = {**hold(), 'wheels': [-.35, .35, -.35, .35], 'duration_s': [.05]*4}
        assert nav.pulse_safe(value) and command_delta(value, .1)[2] != 0.
        centre = w['objects']['crate_1']['xy']; origin = math.atan2(pose[1]-centre[1], pose[0]-centre[0])
        found = []
        for key in (60, -60, 90, -90, 120, -120, 180):
            angle = origin+math.radians(key)
            goal = (centre[0]+.45*math.cos(angle), centre[1]+.45*math.sin(angle))
            yaw = math.atan2(centre[1]-goal[1], centre[0]-goal[0])
            found.append(nav.path(pose[:2], goal, yaw))
        assert any(found)
        t = teacher(MODE); t.rid = rid; t.end = case['end']; t.folded_ready = True; t.phase = 'search'
        # Even the ordinary body-turn proposal survives at both saved ticks.
        command = t._check_navigation_pulse(w, value, w['t'])
        assert command_delta(command,.1)[2] != 0. and nav.pulse_safe(command)
        if 'crate_1' in w['visibility'][rid]['objects']:
            command = t._observe_stable(w, w['t'])
            command = t._check_navigation_pulse(w, command, w['t'])
            assert any(command['wheels']) and nav.pulse_safe(command)


def test_memory_horizon_and_held_cargo_are_not_bypassed():
    w = deepcopy(CASES[-1]['world']); rid = 'r2'; w['t'] = w['beam']['seen_t']+MEMORY_S
    nav = Navigation(w, rid, True, CRATE, (-20,20,-20,20), end='blue', search=True)
    assert sum(k == 'crate' for k, _ in nav.rectangles) == 3
    w['t'] += .00001
    expired = Navigation(w, rid, True, CRATE, (-20,20,-20,20), end='blue', search=True)
    assert expired.walls_only and not expired.circles and all(k=='wall' for k, _ in expired.rectangles)
    audit = new_input_audit(True, 'issued')
    held = AuditedTeacherInput(tagged_world(w, holding=True), audit, provenance='value_sources_v1')
    t = teacher(MODE); t.rid = rid; t.end = 'blue'; t.phase = 'search'
    t._navigation(w)  # populate with pre-hold admitted memory
    n = t._navigation(held)
    assert n.crate_source == 'none' and all(k != 'crate' for k, _ in n.rectangles)
    assert audit['held_world_reads'] == 0 and audit['invisible_measurements'] == 0


def test_margin_escape_increases_clearance_and_rejects_closer_and_rotation_collision():
    w = empty(); w['beam'] = None
    w['walls'] = [(0., .105, 1., .02, 0.)]  # 4 mm physical gap, inside 5 mm pad
    nav = Navigation(w, 'r1', True, CRATE, (-20,20,-20,20), search=True)
    assert not nav.free((0.,0.),0.)
    assert nav.segment((0.,0.),(0.,-.03),0.,0.)
    assert nav.segment((0.,0.),(0.,0.),.1,0.)  # yaw can also increase an existing margin
    assert not nav.segment((0.,0.),(0.,.001),0.,0.)
    assert not nav.segment((0.,0.),(0.,0.),0.,math.pi/2)
    t = teacher(MODE); t.phase = 'search'
    assert nav.pulse_safe(t._continuous(1.,0.,-.05,0.))
    assert not nav.pulse_safe(t._continuous(1.,0.,.05,0.))


def test_analytic_sat_matches_polygon_and_cache_does_not_change_result():
    for i in range(25):
        p = (.01*i, -.02*i, .13*i); r = (.3, .1, .07, .05, -.05*i)
        assert rectangle_gap(p,r,.015) == pytest.approx(polygon_gap(polygon_at(p,FOOTPRINT), rect_corners(r,margin=.015)))
    w = empty(); nav = Navigation(w,'r1',True,CRATE,(-20,20,-20,20))
    first = nav.segment((0.,0.),(-.2,0.),0.,0.)
    assert nav.segment((0.,0.),(-.2,0.),0.,0.) == first
    assert nav.stats['segment_cache_hits'] == 1


def test_unreachable_empty_goal_has_deterministic_expansion_bound():
    w = empty(); w['beam']=None; w['walls']=[(1.5,0.,.02,10.,0.)]
    nav=Navigation(w,'r1',True,CRATE,(-20,20,-20,20))
    assert nav.free((2.4,0.),0.) and nav.path((0.,0.),(2.4,0.),0.) is None
    assert 0 < nav.stats['expansions'] <= 2*MAX_EXPANSIONS
    expansions=nav.stats['expansions']
    assert nav.path((0.,0.),(2.4,0.),0.) is None and nav.stats['expansions']==expansions


@pytest.mark.parametrize('cause', ['staging_peer', 'route'])
def test_peer_wait_retreats_after_12s_and_hands_off_after_finite_second_attempt(cause):
    t=teacher(MODE); w=empty(); t.folded_ready=True; t.phase='approach'
    if cause=='staging_peer':
        t.staging_since=1.; t.staging_peer_blocked=True; t._motion_blocked(w,1.)
    else:
        assert t._peer_route(w,(-1.,0.),1.) is not None
    assert t._motion_timeout(w,12.9) is None and not t._staging_expired(12.9)
    value=t._motion_timeout(w,13.)
    assert value is not None and any(value['wheels']) and t.phase=='relook'
    assert t.motion_recovery_at==13. and t.outcome is None
    assert t._motion_timeout(w,14.1) is None
    assert t._motion_timeout(w,25.) is not None and t.outcome=='approach_blocked_handoff'


def test_preferred_pad_then_narrow_fallback_and_strict_profile(tmp_path):
    w=empty(); w['beam']=None
    nav=Navigation(w,'r1',True,CRATE,(-20,20,-20,20))
    assert nav.path((0.,0.),(-.2,0.),0.) and nav.stats['path_pads_m']==[.015]
    w['walls']=[(-.2,.11,1.,.02,0.)]
    nav=Navigation(w,'r1',True,CRATE,(-20,20,-20,20))
    assert nav.path((0.,0.),(-.2,0.),0.) and nav.stats['path_pads_m']==[.005]
    with pytest.raises(ValueError,match='held_object'):
        run({},tmp_path/'forbidden',crate_profile='crate16_v1')
    assert not (tmp_path/'forbidden').exists()
    assert teacher('off').crate_motion=='off'


def test_queue_fresh_seeds_and_every_execution_flag_false():
    spec=importlib.util.spec_from_file_location('queue16',HERE/'queue.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    q=m.build('f'*40,{})
    assert len(q['runs'])==15 and q['stage_counts']=={'reproduction':5,'diagnostic':10,'gate':0}
    assert q['crate_profile']=='crate16_v1'
    assert {r['seed'] for r in q['runs'] if r['stage']=='reproduction'}=={77990,79314,79317,79450,79451}
    old=json.loads((HERE.parent/'2026-10-15-crate15/diagnostic-plan.json').read_text())
    fresh={r['seed'] for r in q['runs'] if r['stage']=='diagnostic'}
    assert len(fresh)==10 and not fresh & {e['seed'] for e in old['episodes']}
    def check(v):
        if isinstance(v,dict):
            for k,item in v.items():
                if any(s in k for s in ('approved','enabled','authorized','ready','submitted')):
                    assert item is False or isinstance(item,dict) and not any(item.values())
                check(item)
        elif isinstance(v,list):
            for item in v:check(item)
        elif isinstance(v,bool):
            assert v is False
    check(q)
