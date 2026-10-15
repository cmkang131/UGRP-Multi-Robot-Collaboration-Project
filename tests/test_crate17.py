"""Crate17 saved-world feedback and adversarial geometry; no simulation/render."""
import importlib.util
import json
import math
import random
from copy import deepcopy
from pathlib import Path
import pytest
from harness.grasp_act_contract import command, MEMORY_S
from harness.grasp_act_visible_world import command_delta
from harness.static_keepouts import polygon_at, rect_corners
from sim.crate_motion_v15 import polygon_gap
from sim.crate_motion_v16 import Navigation as Navigation16
from sim.crate_motion_v17 import Navigation, MODE, NO_CLEARANCE, advance, translation
from sim.crate_navigation_v12 import FOOTPRINT
from sim.cargo_teacher_profile import CRATE
from scripts.run_crate_teacher import run
from test_crate15 import teacher, empty, hold

HERE = Path(__file__).resolve().parents[1]/'experiments/2026-10-15-crate17'
spec = importlib.util.spec_from_file_location('crate17_verify', HERE/'verify.py')
verify = importlib.util.module_from_spec(spec); spec.loader.exec_module(verify)
CASES = verify.js(HERE/'closed-loop-fixtures.json.zst')['cases']


@pytest.fixture(autouse=True)
def no_physics(monkeypatch):
    import mujoco
    def forbidden(*a, **k): raise AssertionError('physics/render forbidden')
    for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_inverse', 'Renderer', 'mjr_render'):
        monkeypatch.setattr(mujoco, name, forbidden)


@pytest.mark.parametrize('mode', (MODE, NO_CLEARANCE))
@pytest.mark.parametrize('case', CASES, ids=lambda c: c['run']+'-'+str(round(c['world']['t'], 1)))
def test_saved_world_closed_loop_issues_translation_instead_of_alternating_spin(case, mode):
    result = verify.closed_loop(case, mode)
    assert result['translation_ticks'] >= 3
    assert result['net_xy_mm'] > 5.
    signs = []
    for row in result['trace']:
        dx, dy, da = row['delta']
        signs.append(0 if math.hypot(dx, dy) >= .0005 or abs(da) < 1e-9 else math.copysign(1, da))
    assert not any(all(a*b < 0 for a, b in zip(signs[i:i+10], signs[i+1:i+10])) for i in range(3))


def test_closed_loop_fixture_reproduces_old_period_two_failure():
    result = verify.closed_loop(CASES[0], 'crate_motion_v16')
    assert result['translation_ticks'] == 0
    da = [r['delta'][2] for r in result['trace'][:10]]
    assert all(a*b < 0 for a,b in zip(da, da[1:]))


def test_waypoint_does_not_skip_to_yaw_interpolated_lookahead():
    case = CASES[0]; w = case['world']; pose = w['robots'][case['robot']]['pose']
    nav = Navigation(w, case['robot'], True, CRATE, (-20,20,-20,20), end=case['end'])
    point = nav.waypoint(pose[:2], case['path'], nav.focus)
    assert point == case['path'][1]
    assert nav.stats['waypoint_first_node_fallbacks'] == 1
    assert not nav.segment(pose[:2], case['path'][2], pose[2], pose[2])
    t = verify.teacher(case)
    actual = t._check_navigation_pulse(w, case['proposal'], w['t'])
    assert math.hypot(*command_delta(actual,.1)[:2]) >= .0005 and nav.pulse_safe(actual)


def test_order_shorter_same_pulse_then_direction_then_bearing_then_retreat():
    case = CASES[0]; t = verify.teacher(case, NO_CLEARANCE); nav = t._navigation(case['world'])
    candidates = list(nav.escape_candidates(case['proposal']))
    kinds = [k for k,_ in candidates]
    assert kinds[:3] == ['scale_0.75', 'scale_0.5', 'scale_0.25']
    assert kinds[3:7] == ['direction_+15', 'direction_-15', 'direction_+30', 'direction_-30']
    assert kinds[-1] == 'retreat'
    for _, c in candidates[:3]:
        assert c['wheels'] == case['proposal']['wheels'] and max(c['duration_s']) >= .025
    # Large proposal-yaw noise must not trigger a <2 degree lug-bearing turn.
    nav.focus = [nav.pose[0]+math.cos(nav.pose[2]), nav.pose[1]+math.sin(nav.pose[2])]
    assert 'face_lug' not in [k for k,_ in nav.escape_candidates(case['proposal'])]
    nav.focus = [nav.pose[0]+math.cos(nav.pose[2]+.1), nav.pose[1]+math.sin(nav.pose[2]+.1)]
    spin = dict(nav.escape_candidates(case['proposal']))['face_lug']
    yaw = command_delta(spin,.1)[2]
    assert 0 < yaw <= .05+1e-10
    nav.focus = None
    assert 'face_lug' not in [k for k,_ in nav.escape_candidates(case['proposal'])]


@pytest.mark.parametrize('kind', ('stationary', 'alternating'))
def test_ten_escape_ticks_enter_existing_12_24_second_deadlines(kind):
    t = teacher(MODE); w = empty()
    for i in range(10):
        now = 1.+.1*i; w['t'] = now
        v = hold()
        if kind == 'alternating':
            sign = (-1)**i
            v.update(wheels=[-.35*sign,.35*sign,-.35*sign,.35*sign], duration_s=[.025]*4)
        t._motion17_progress(w, now, v, escape=True)
        if i < 9: assert t.motion_blocked_since is None
    assert t.motion_blocked_since == 1.
    assert t._motion_timeout(w, 13.) is not None and t.phase == 'relook'
    assert t._motion_timeout(w, 25.) is not None and t.outcome == 'approach_blocked_handoff'


def test_sustained_usable_route_progress_under_5cm_retires_stale_deadline():
    t = teacher(MODE); w = empty(); t.approach_plan_valid = True
    t._motion_blocked(w, 1.)
    moving = translation(hold(), .002, 0.)
    for i in range(7):
        w['robots']['r1']['pose'][0] = .002*i
        t._motion17_progress(w, 2.+.1*i, moving, escape=False)
    assert t.motion_blocked_since is None and t.motion_recovery_at is None
    # Merely replanning without moving must not erase the deadline.
    t._motion_blocked(w, 3.)
    for i in range(7): t._motion17_progress(w, 4.+.1*i, hold(), escape=False)
    assert t.motion_blocked_since == 3.


def test_walls_only_scan_keeps_current_visible_peer_rectangle_and_expiry():
    w = empty(); w['beam'] = None
    w['robots']['r2'] = {'pose': [0., .172, 0.]}
    w['visibility']['r1'].update(visible_probes=0, peers=['r2'])
    nav = Navigation(w, 'r1', True, CRATE, (-20,20,-20,20), search=True)
    assert nav.walls_only and any(k == 'peer' for k,_ in nav.rectangles)
    toward = translation(hold(), 0., .012)
    assert not nav.pulse_safe(toward)
    w['visibility']['r1']['peers'] = []
    assert all(k != 'peer' for k,_ in Navigation(w,'r1',True,CRATE,(-20,20,-20,20),search=True).rectangles)
    w = deepcopy(CASES[0]['world']); rid = CASES[0]['robot']
    w['t'] = w['beam']['seen_t']+MEMORY_S+.001; w['visibility'][rid]['visible_probes'] = 0
    assert Navigation(w,rid,True,CRATE,(-20,20,-20,20),search=True).crate_source == 'none'


def test_clearance_preference_is_the_only_difference_between_paired_modes():
    case = CASES[0]; full = verify.teacher(case, MODE); off = verify.teacher(case, NO_CLEARANCE)
    w = case['world']
    fc = full._check_navigation_pulse(w,case['proposal'],w['t'])
    oc = off._check_navigation_pulse(w,case['proposal'],w['t'])
    assert full.crate_recovery_log[-1]['kind'].startswith('preferred_')
    assert off.crate_recovery_log[-1]['kind'].startswith(('scale_', 'direction_'))
    for t,c in ((full,fc),(off,oc)):
        assert t._navigation(w).pulse_safe(c)
    nav = full._navigation(w)
    before = min(v for _,v in nav.clearances(nav.pose[:2],nav.pose[2],.015))
    after = advance(nav.pose,fc)
    assert min(v for _,v in nav.clearances(after[:2],after[2],.015)) > before


@pytest.mark.parametrize('kind', ('wall','crate','peer'))
def test_random_real_collision_rejection_with_independent_polygon_oracle(kind):
    rng = random.Random(1701); collisions = 0; checked = 0
    for _ in range(1800):
        w = empty(); w['beam'] = None
        nav = Navigation(w,'r1',True,CRATE,(-20,20,-20,20),search=True)
        a = rng.uniform(-math.pi,math.pi); d = rng.uniform(.1,.22)
        rect = (d*math.cos(a),d*math.sin(a),rng.uniform(.02,.07),rng.uniform(.02,.06),rng.uniform(-math.pi,math.pi))
        nav.rectangles = [(kind,rect)]; poly = rect_corners(rect)
        if polygon_gap(polygon_at(nav.pose,FOOTPRINT),poly) <= 0.: continue
        v = command({**hold(), 'wheels':[rng.choice((-.35,.35)) for _ in range(4)],
                     'duration_s':[rng.uniform(.025,.1) for _ in range(4)]})
        x,y,yaw = nav.pose; collision = False
        # Independent finer integration, including every wheel expiry.
        times = sorted({0.,.1,*(i*.001 for i in range(1,100)),*v['duration_s']})
        for ta,tb in zip(times,times[1:]):
            dx,dy,da = command_delta({**v,'duration_s':[max(0.,t-ta) for t in v['duration_s']]},tb-ta)
            c,s = math.cos(yaw+da/2),math.sin(yaw+da/2)
            x,y,yaw = x+c*dx-s*dy,y+s*dx+c*dy,yaw+da
            collision |= polygon_gap(polygon_at((x,y,yaw),FOOTPRINT),poly) <= 0.
        checked += 1
        if collision:
            collisions += 1
            assert not nav.pulse_safe(v)
    assert checked > 600 and collisions > 10


def test_new_profile_is_opt_in_and_stats_cover_prepare_and_step(tmp_path):
    from sim.crate_observation_v12 import PROFILES
    assert 'crate17_v1' in PROFILES and 'crate17_no_clearance_v1' in PROFILES
    with pytest.raises(ValueError,match='held_object'):
        run({},tmp_path/'forbidden',crate_profile='crate17_v1')
    assert not (tmp_path/'forbidden').exists()
    t = teacher(MODE); w = empty()
    n = t._navigation(w); n.path((0.,0.),(-.2,0.),0.)
    assert t._navigation(w) is n
    t._step = lambda *a, **k: (t._hold(1.),False)
    t.step(w,1.)
    assert n in t.navigation_cache.values()
    stats = t.navigation_stats()
    assert stats['path_pads_m'] == [.015] and stats['attempted_pads_m'] == [.015]
    assert isinstance(stats['expansions'],int) and stats['remaining_expansions'] <= 384
    assert t.teacher_compute_s > 0.
    assert teacher('off').crate_motion == 'off'


def test_queue_paired_seeds_and_independent_first_two_row_approval():
    spec = importlib.util.spec_from_file_location('queue17',HERE/'queue.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    q = m.build('f'*40,{})
    assert len(q['runs']) == 30
    assert q['per_candidate_stage_counts'] == {'reproduction':5,'diagnostic':10,'gate':0}
    pairs = {}
    for r in q['runs']:
        pairs.setdefault((r['stage'],r['seed']),set()).add(r['candidate'])
    assert len(pairs) == 15 and all(v == {'full','no_clearance'} for v in pairs.values())
    assert q['runs'][0]['seed'] == q['runs'][1]['seed'] == 77990
    fresh = {r['seed'] for r in q['runs'] if r['stage'] == 'diagnostic'}
    assert len(fresh) == 10 and all(79100 <= s <= 79139 for s in fresh)
    def flags_false(v):
        if isinstance(v,dict):
            for k,item in v.items():
                if any(s in k for s in ('approved','enabled','authorized','ready','submitted')):
                    assert item is False or isinstance(item,dict) and not any(item.values())
                flags_false(item)
        elif isinstance(v,list):
            for item in v: flags_false(item)
        elif isinstance(v,bool): assert v is False
    flags_false(q)
    q['runs'][0]['approved'] = q['runs'][1]['approved'] = True
    assert [r['row_id'] for r in q['runs'] if r['approved']] == [0,1]
    assert not q['approved'] and not q['coordinator_approval']['approved']


def test_held_input_audit_and_new_tick_cache_expiry():
    from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit
    from sim.crate_observation_v12 import tagged_world
    case = CASES[0]; t = verify.teacher(case); w = deepcopy(case['world'])
    t._navigation(w)
    w['t'] += .1
    audit = new_input_audit(True,'issued')
    held = AuditedTeacherInput(tagged_world(w,holding=True),audit,provenance='value_sources_v1')
    t.phase = 'closed'
    t._step = lambda *a, **k: (t._hold(w['t']),False)
    t.step(held,w['t'])
    assert not t.navigation_cache
    nav = t._navigation(held)
    assert nav.crate_source == 'none' and all(k != 'crate' for k,_ in nav.rectangles)
    assert audit['held_world_reads'] == audit['invisible_measurements'] == 0
