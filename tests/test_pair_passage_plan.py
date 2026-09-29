"""Passage-map support for the pair-carry route (issue #221 follow-up). Static geometry only: no simulator."""
from __future__ import annotations

import copy
import inspect
import json
import math
from pathlib import Path

import pytest

from harness import pair_passage_plan as pp
from harness import pair_stage_probe as sp
from harness import zone_pair_executor as zpe
from scripts import run_m2_pair as m2

ROOT = Path(__file__).resolve().parents[1]
SHEET = m2.pa.coarse_order_sheet([1., .05, 0.])
DOOR_MAP = 'zone_wide_door_tags_v2_dock_v3'
CORRIDOR = 'zone_wide_corridor_tags_v3'
TWO_DOORS = 'zone_wide_two_doors_tags_v3'

# Golden values of the frozen (default) behaviour, computed on origin/main 45a21b23 BEFORE this change.
GOLD_PLAN_B = '4ee615b8becf0a43f5287f22697d1826cee99ee5b21e94db35e6b2afb2771007'
GOLD_PLAN_A = '1d86deaa7a3bddc9272056e7c238eb899fc2ce525b8faa493c71fd0db934a71c'
GOLD_CARRY_L1 = 'a10f349fe239ecec9b3406200014e23fdacf38c4931b11559ce0dffba64f569e'
GOLD_SETDOWN_END = '9d20ccd0bb9bfa8a7c19b254b466b9ce1d844693c65c05c82c218b9120c6c6b7'
GOLD_ALIGN = '2440c9ffcd7bbc6104541e8f3b8470e84e32f68d32eb365e2e4e9af10e74e536'


def load(map_id):
    return pp.load_map(map_id)


def narrow_corridor(width):
    """The corridor map with its 0.5 m opening replaced by `width` (upper edge fixed at the north wall)."""
    m = load(CORRIDOR)
    lower = 1.425 - width
    for o in m['obstacles']:
        if o['id'] in ('wall_corridor_1', 'wall_corridor_2'):
            o['center_m'][1] = lower - .025
        if o['id'] == 'wall_divider_1':
            o['center_m'][1], o['half_extents_m'][1] = (lower - 3.15) / 2, (lower + 3.15) / 2
    corridor = next(p for p in m['passages'] if p['id'] == 'corridor_1')
    corridor['center_m'][1], corridor['half_extents_m'][1], corridor['width_m'] = 1.425 - width / 2, width / 2, width
    return m


@pytest.fixture
def restore_make_plan():
    original = zpe.make_plan
    yield
    pp.uninstall()
    assert zpe.make_plan is original


# ------------------------------------------------------------------ frozen behaviour is unchanged
def test_default_plan_and_probe_cases_are_byte_identical_to_main():
    door = load(DOOR_MAP)
    assert zpe._digest(zpe.make_plan(door, SHEET, 'B')) == GOLD_PLAN_B
    assert zpe._digest(zpe.make_plan(door, SHEET, 'A')) == GOLD_PLAN_A
    dg = lambda x: __import__('hashlib').sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()
    assert dg(sp.teacher_cases('carry', leg=1, subset={'nominal', 'lat+/same'})) == GOLD_CARRY_L1
    assert dg(sp.teacher_cases('setdown', leg='end', subset={'nominal'})) == GOLD_SETDOWN_END
    assert dg(sp.teacher_cases('align', subset={'nominal'})) == GOLD_ALIGN
    assert 'passage' not in zpe.make_plan(door, SHEET, 'B')


def test_opt_in_on_the_m2_door_map_returns_the_frozen_plan():
    door = load(DOOR_MAP)
    for passage in (None, 'auto', 'door_1'):
        assert zpe._digest(pp.passage_make_plan(door, SHEET, 'B', passage)) == GOLD_PLAN_B


def test_executor_files_are_not_edited_and_probe_runner_default_spec_is_unchanged():
    # hash-pinned by the registered v6-family source closure; the opt-in lives in harness/pair_passage_plan.py
    text = (ROOT / 'harness/zone_pair_executor.py').read_text()
    assert 'pair_passage' not in text and 'passage=' not in text
    assert 'pair_passage' not in (ROOT / 'harness/zone_own_team_host.py').read_text()
    from scripts import run_pair_stage_probes as runner
    assert runner.order_for('B') == runner.ORDER
    args = runner.parser().parse_args(['--stage', 'carry', '--output', '/tmp/x'])
    assert args.passage_map is None and args.passage == 'auto' and args.passage_target == 'B'


def test_planner_constants_match_the_sources_they_mirror():
    assert "{'x_m': [-.625, .625], 'y_m': [-.20, .20]}" in inspect.getsource(zpe.make_plan)
    assert pp.PAIR_ENVELOPE == {'x_m': [-.625, .625], 'y_m': [-.20, .20]}
    from harness import map_goto
    from harness.zone_pair_status import MAX_SEGMENTS
    assert pp.ROUTE_MARGIN_M == map_goto.MARGIN_M and pp.MAX_LEGS == MAX_SEGMENTS
    assert pp.DOOR_ALIGN_MAX_M == m2.DOOR_ALIGN_MAX_M
    assert (pp.PRIOR_STD[0], pp.PRIOR_STD[1]) == (sp.E2E_MATCHED_PRIOR['std_xy_m'], sp.E2E_MATCHED_PRIOR['std_yaw_rad'])
    assert pp.TEMPLATE_MAP_ID == sp.MAP_ID


# ------------------------------------------------------------------ map loading and widths
def test_passage_maps_load_and_bays_are_not_routes():
    assert [p['id'] for p in pp.traversable_passages(load(CORRIDOR))] == ['corridor_1']
    assert [p['id'] for p in pp.traversable_passages(load(TWO_DOORS))] == ['door_narrow', 'door_wide']
    assert [p['id'] for p in pp.traversable_passages(load(DOOR_MAP))] == ['door_1']
    assert pp.traversable_passages(load('zone_wide')) == []


@pytest.mark.parametrize('map_id,passage,width', [(CORRIDOR, 'corridor_1', .5), (TWO_DOORS, 'door_narrow', .5),
                                                  (TWO_DOORS, 'door_wide', 1.0), (DOOR_MAP, 'door_1', .5)])
def test_measured_opening_matches_declared_width(map_id, passage, width):
    m = load(map_id)
    opening = pp.measured_opening(m, next(p for p in m['passages'] if p['id'] == passage))
    assert opening['width_m'] == pytest.approx(width, abs=1e-9)
    assert opening['lower_m'] == pytest.approx(width / 2, abs=1e-9) and opening['upper_m'] == pytest.approx(width / 2, abs=1e-9)


def test_corridor_binding_section_is_the_walled_part_not_the_passing_bay():
    m = load(CORRIDOR)
    opening = pp.measured_opening(m, m['passages'][0])
    assert opening['x_m'] < 2.83 or opening['x_m'] > 3.37        # bay opening (x 2.8..3.4) is wider
    assert {opening['lower_id'], opening['upper_id']} <= {'wall_corridor_1', 'wall_corridor_2', 'map_bound', 'wall_divider_1'}   # map_bound = wall_north's inner face


def test_required_width_uses_envelope_and_pair_spacing():
    assert pp.required_width('x') == pytest.approx(.44)           # beam / chassis y extent + 2 * 0.02
    assert pp.required_width('y') == pytest.approx(1.29)          # beam length + two-robot spacing + 2 * 0.02


@pytest.mark.parametrize('width,ok', [(.50, True), (.45, True), (.44, True), (.43, False), (.40, False)])
def test_width_check_boundary_and_explicit_code(width, ok):
    m = narrow_corridor(width)
    if ok:
        info = pp.check_passage(m, m['passages'][0])
        assert info['slack_per_side_m'] == pytest.approx((width - .44) / 2, abs=1e-9)
    else:
        with pytest.raises(pp.PassageRefusal) as raised:
            pp.check_passage(m, m['passages'][0])
        assert raised.value.code == 'PAIR_PASSAGE_TOO_NARROW'
        assert raised.value.detail['required_width_m'] == pytest.approx(.44)
        assert raised.value.detail['measured_free_width_m'] == pytest.approx(width, abs=1e-9)


def test_narrow_map_is_refused_by_the_planner_with_the_same_code():
    with pytest.raises(pp.PassageRefusal, match='PAIR_PASSAGE_TOO_NARROW'):
        pp.plan_passage_route(narrow_corridor(.42), [1., 0., 0.], 'A')


def test_passage_along_y_needs_the_beam_length_not_the_beam_width():
    m = load(CORRIDOR)
    side = {'id': 'side', 'kind': 'corridor', 'axis': 'y', 'center_m': [3., 0.], 'half_extents_m': [.25, 1.], 'width_m': .5}
    with pytest.raises(pp.PassageRefusal) as raised:
        pp.check_passage(m, side)
    assert raised.value.code == 'PAIR_PASSAGE_TOO_NARROW' and raised.value.detail['required_width_m'] == pytest.approx(1.29)
    side.update(half_extents_m=[.75, 1.], width_m=1.5)
    with pytest.raises(pp.PassageRefusal, match='PAIR_PASSAGE_AXIS_UNSUPPORTED'):
        pp.check_passage(m, side)


def test_declared_width_that_disagrees_with_the_walls_is_refused():
    m = load(CORRIDOR)
    m['passages'][0]['width_m'] = .6
    m['passages'][0]['half_extents_m'][1] = .3
    with pytest.raises(pp.PassageRefusal, match='PAIR_PASSAGE_MAP_INCONSISTENT'):
        pp.check_passage(m, m['passages'][0])


def test_passage_selection_codes():
    m = load(CORRIDOR)
    with pytest.raises(pp.PassageRefusal, match='PAIR_PASSAGE_UNKNOWN'):
        pp.plan_passage_route(m, [1., 0., 0.], 'A', 'nope')
    with pytest.raises(pp.PassageRefusal, match='PAIR_PASSAGE_NONE'):
        pp.plan_passage_route(load('zone_wide'), [1., 0., 0.], 'A')


# ------------------------------------------------------------------ route / legs
def axis_aligned(route):
    return all(abs(a[0] - b[0]) < 1e-9 or abs(a[1] - b[1]) < 1e-9 for a, b in zip(route, route[1:]))


def test_unsupported_by_default_becomes_supported_with_the_opt_in():
    m = load(CORRIDOR)
    with pytest.raises(ValueError, match='UNSUPPORTED_PAIR_MAP'):
        zpe.make_plan(m, SHEET, 'A')
    plan = pp.passage_make_plan(m, SHEET, 'A', 'auto')
    route = plan['route']
    assert plan['passage']['id'] == 'corridor_1' and plan['door_plan']['door_id'] == 'corridor_1'
    assert plan['door_plan']['axis_y_m'] == pytest.approx(1.175) and plan['door_plan']['headings_rad'] == m2.DOOR_PLAN['headings_rad']
    assert axis_aligned(route) and len(route) - 1 == 8 <= zpe.MAX_SEGMENTS
    assert route[-1] == m['regions']['zone_A']['center_m']
    assert max(math.dist(a, b) for a, b in zip(route, route[1:])) <= .85 + 1e-9
    # everything that is not the route is the frozen plan's own data
    frozen = zpe.make_plan(load(DOOR_MAP), SHEET, 'A')
    assert all(plan[k] == frozen[k] for k in ('sheet', 'prestations', 'keepouts', 'beam_geometry', 'target_zone'))
    assert plan['map_sha256'] == zpe._digest(m) != frozen['map_sha256']


def test_corridor_route_geometry_and_leg_roles():
    plan = pp.passage_make_plan(load(CORRIDOR), SHEET, 'A', 'auto')
    info, route = plan['passage'], plan['route']
    assert route[0] == [1.0, 0.0] and route[2] == [1.0, 1.175]      # lateral (2 legs) onto the corridor axis first
    assert all(abs(p[1] - 1.175) < 1e-9 for p in route[2:8]) and route[7][0] == pytest.approx(4.6)
    assert info['exit_x_m'] == pytest.approx(4.6)                    # trailing chassis clears corridor_2 (x <= 3.925)
    assert info['leg_roles'] == {'lateral_to_axis': [0, 1], 'entry': [2], 'inside': [3, 4, 5], 'exit': [6],
                                 'all_crossing': [2, 3, 4, 5, 6]}
    assert info['a_star']['passages'] == ['corridor_1']              # the A* oracle also goes through the corridor
    assert plan['door_plan']['target_beam_x_m'] == pytest.approx(4.6)


@pytest.mark.parametrize('target,ok', [('A', True), ('B', False), ('C', False)])
def test_frozen_eight_segment_protocol_bounds_the_corridor_targets(target, ok):
    m = load(CORRIDOR)
    if ok:
        assert len(pp.passage_make_plan(m, SHEET, target, 'auto')['route']) - 1 == 8
    else:
        with pytest.raises(pp.PassageRefusal) as raised:
            pp.passage_make_plan(m, SHEET, target, 'auto')
        assert raised.value.code == 'PAIR_PASSAGE_TOO_MANY_SEGMENTS' and raised.value.detail['legs'] > pp.MAX_LEGS


def test_two_doors_narrow_door_route_equals_the_frozen_door_route():
    frozen = zpe.make_plan(load(DOOR_MAP), SHEET, 'B')
    plan = pp.passage_make_plan(load(TWO_DOORS), SHEET, 'B', 'auto')
    assert plan['passage']['id'] == 'door_narrow' and plan['route'] == frozen['route']
    assert plan['door_plan']['checkpoints_beam_x_m'] == m2.DOOR_PLAN['checkpoints_beam_x_m']


def test_two_doors_wide_door_passes_the_width_check_but_its_route_exceeds_the_segment_protocol():
    m = load(TWO_DOORS)
    wide = m['passages'][1]
    assert pp.check_passage(m, wide)['slack_per_side_m'] == pytest.approx((1.0 - .44) / 2)
    with pytest.raises(pp.PassageRefusal) as raised:          # y=0 pickup -> y=-2.625 door needs > 8 legs
        pp.plan_passage_route(m, [1., 0., 0.], 'A', 'door_wide')
    assert raised.value.code == 'PAIR_PASSAGE_TOO_MANY_SEGMENTS' and raised.value.detail['passage'] == 'door_wide'
    assert pp.plan_passage_route(m, [1., 0., 0.], 'A')['passage']['id'] == 'door_narrow'   # auto: the valid one


def test_terrain_on_the_axis_route_is_refused_and_terrain_off_route_is_not():
    m = load(CORRIDOR)
    m['terrain'] = [{'id': 'ridge', 'kind': 'ridge', 'center_m': [1.0, .6], 'half_extents_m': [.15, .15]}]
    with pytest.raises(pp.PassageRefusal, match='PAIR_PASSAGE_ROUTE_CROSSES_UNVALIDATED_TERRAIN') as raised:
        pp.plan_passage_route(m, [1., 0., 0.], 'A')
    assert raised.value.detail['blocker'] == 'unvalidated_ridge'
    m['terrain'] = [{'id': 'ridge', 'kind': 'ridge', 'center_m': [3.0, -2.5], 'half_extents_m': [.3, .3]}]
    assert pp.plan_passage_route(m, [1., 0., 0.], 'A')['route'] == pp.plan_passage_route(load(CORRIDOR), [1., 0., 0.], 'A')['route']


def test_terrain_inside_the_passage_narrows_it():
    m = load(CORRIDOR)
    m['terrain'] = [{'id': 'bump', 'kind': 'mound', 'center_m': [3.0, 1.175], 'half_extents_m': [.1, .1]}]
    with pytest.raises(pp.PassageRefusal, match='PAIR_PASSAGE_TOO_NARROW'):
        pp.plan_passage_route(m, [1., 0., 0.], 'A')


def test_all_candidates_refused_distinguishes_no_path_from_no_axis_route(monkeypatch):
    m = load(TWO_DOORS)

    def refuse(*a, **k):
        raise pp.PassageRefusal('PAIR_PASSAGE_TOO_NARROW')
    monkeypatch.setattr(pp, '_candidate', refuse)
    monkeypatch.setattr(pp, '_astar', lambda *a, **k: {'length_m': 1., 'passages': []})
    with pytest.raises(pp.PassageRefusal) as raised:
        pp.plan_passage_route(m, [1., 0., 0.], 'B')
    assert raised.value.code == 'PAIR_PASSAGE_NONE_USABLE' and len(raised.value.detail['refused']) == 2
    monkeypatch.setattr(pp, '_astar', lambda *a, **k: None)
    with pytest.raises(pp.PassageRefusal, match='PAIR_NO_PATH_FOR_PAIR_ENVELOPE'):
        pp.plan_passage_route(m, [1., 0., 0.], 'B')


def test_a_star_oracle_is_the_repo_planner_and_sees_the_corridor():
    found = pp._astar(load(CORRIDOR), [1., 0.], [4.6, .4], pp.PAIR_ENVELOPE)
    assert found['passages'] == ['corridor_1'] and found['planner'].startswith('grid A*')
    assert pp._astar(narrow_corridor(.42), [1., 0.], [4.6, .4], pp.PAIR_ENVELOPE) is None


# ------------------------------------------------------------------ controller guard margin (offline SweepGuard)
def test_guard_slack_of_the_corridor_equals_the_validated_door_and_shrinks_with_width():
    door = load(DOOR_MAP)
    door_slack = pp.guard_slack(door, door['passages'][0], (1.0, 3.2))
    corridor = load(CORRIDOR)
    slack = pp.guard_slack(corridor, corridor['passages'][0], (1.0, 4.6))
    assert slack['min_clearance_at_prior_m'] == pytest.approx(door_slack['min_clearance_at_prior_m'], abs=1e-6)
    assert slack['min_clearance_at_prior_m'] > .05
    assert slack['max_sigma_xy_m'] == pytest.approx(door_slack['max_sigma_xy_m'], abs=2e-3)
    assert .05 < slack['max_sigma_xy_m'] < .07 and .2 < slack['max_pair_yaw_offset_rad'] < .25
    tight = narrow_corridor(.46)
    narrower = pp.guard_slack(tight, tight['passages'][0], (1.0, 4.6))
    assert narrower['max_sigma_xy_m'] < slack['max_sigma_xy_m'] and narrower['max_pair_yaw_offset_rad'] < slack['max_pair_yaw_offset_rad']


# ------------------------------------------------------------------ executor blocker + probe-only view
def test_own_executor_cannot_be_built_on_a_corridor_map_without_the_probe_view():
    """harness/zone_own_executor.py:134 needs a door-kind passage (frozen file): the blocker behind the alias view."""
    from tests.test_zone_pair_executor import CALIB, ORDER, ROWS_Y, ZoneOwnExecutor

    def build(static):
        return ZoneOwnExecutor('r1', static, CALIB['params'], ORDER, skill_factory=lambda *a, **k: None,
                               pose_estimate_cls=tuple, search_rows_y=ROWS_Y, judgments=False)
    corridor = load(CORRIDOR)
    with pytest.raises(StopIteration):
        build(corridor)
    assert build(pp.executor_view(corridor)).door_id == 'corridor_1_executor_alias'


def test_executor_view_is_only_an_alias_the_planner_and_map_hash_ignore():
    corridor = load(CORRIDOR)
    view = pp.executor_view(corridor)
    assert [p['id'] for p in corridor['passages']] == ['corridor_1', 'bay_1'] and len(view['passages']) == 3
    alias = view['passages'][-1]
    assert alias['kind'] == 'door' and alias['alias_of'] == 'corridor_1'
    assert [p['id'] for p in pp.traversable_passages(view)] == ['corridor_1']
    assert pp.without_aliases(view) == corridor
    a, b = (pp.passage_make_plan(m, SHEET, 'A', 'auto') for m in (corridor, view))
    assert a == b and a['map_sha256'] == zpe._digest(corridor)
    door = load(DOOR_MAP)
    assert pp.executor_view(door) is door and pp.executor_view(load('zone_wide')) == load('zone_wide')


# ------------------------------------------------------------------ opt-in install
def test_install_swaps_make_plan_process_locally_and_logs_refusals(restore_make_plan):
    m = load(CORRIDOR)
    pp.REFUSALS.clear()
    frozen = pp.install('auto')
    assert zpe.make_plan is not frozen
    with pytest.raises(RuntimeError):
        pp.install('auto')
    assert zpe.make_plan(m, SHEET, 'A')['passage']['id'] == 'corridor_1'
    assert zpe._digest(zpe.make_plan(load(DOOR_MAP), SHEET, 'B')) == GOLD_PLAN_B
    with pytest.raises(pp.PassageRefusal, match='PAIR_PASSAGE_TOO_MANY_SEGMENTS'):
        zpe.make_plan(m, SHEET, 'B')
    assert [r['code'] for r in pp.REFUSALS] == ['PAIR_PASSAGE_TOO_MANY_SEGMENTS']
    pp.uninstall()
    with pytest.raises(ValueError, match='UNSUPPORTED_PAIR_MAP'):
        zpe.make_plan(m, SHEET, 'A')


def test_pair_team_refuses_passage_map_by_default_and_accepts_it_after_install(restore_make_plan):
    from tests.test_zone_pair_executor import CALIB, ORDER, PairFakeHost, SHEETS, FakeM2, robot, start
    import tests.test_zone_pair_executor as base

    corridor = load(CORRIDOR)
    view = pp.executor_view(corridor)

    def build():
        saved = base.MAP
        base.MAP = view
        try:
            exs = {r: robot(r) for r in ('r1', 'r2', 'r3')}
        finally:
            base.MAP = saved
        for ex in exs.values():
            ex.orders['cargoX']['destination_zone'] = 'A'
        host = PairFakeHost(exs, lambda *a: None)
        host.contact_record = {'profile': 'cargo_noslip_v1'}
        host.enable_pair_carry(SHEETS, CALIB['params'], controller_factory=FakeM2)
        return host, exs

    def go(host):
        first = host.call('r1', 'pair_carry', 'cargoX', 'A', 'r2')
        return first if not first['accepted'] else host.call('r2', 'pair_carry', 'cargoX', 'A', 'r1')

    host, _ = build()
    ack = go(host)
    assert not ack['accepted'] and ack['rejected_reason'] == 'INVALID_PAIR_PLAN'      # frozen behaviour
    pp.install('auto')
    host, exs = build()
    ack = go(host)
    assert ack['accepted'] and all(exs[r].job.kind == 'pair_carry' for r in ('r1', 'r2'))
    plans = [s['plan'] for s in host.pairs.sessions]
    assert plans[0]['passage']['id'] == 'corridor_1' and plans[0]['route'][-1] == corridor['regions']['zone_A']['center_m']


# ------------------------------------------------------------------ stage probe support
def test_plan_route_with_passage_matches_the_passage_plan():
    route = sp.plan_route(SHEET, map_id=CORRIDOR, target='A', passage='auto')
    assert route == pp.passage_make_plan(load(CORRIDOR), SHEET, 'A', 'auto')['route']
    assert sp.plan_route(SHEET) == zpe.make_plan(load(DOOR_MAP), SHEET, 'B')['route']         # default unchanged


def test_passage_cases_stage_the_crossing_legs_and_carry_the_opt_in_fields():
    cases = pp.passage_teacher_cases('carry', CORRIDOR, passage='auto', target='A', leg=3, subset={'nominal'}, seeds=(911,))
    assert [c['case_id'] for c in cases][0] == 'carry:teacher:nominal:s911:L3:Mcorridor_tags_v3'
    c = cases[0]
    assert (c['map'], c['pair_passage'], c['target'], c['leg']) == (CORRIDOR, 'auto', 'A', 3)
    assert c['route'] == sp.plan_route(SHEET, map_id=CORRIDOR, target='A', passage='auto')
    # staged on the corridor axis (true beam keeps the 5 cm sheet offset), both carriers inside the walls
    assert c['beam_xyyaw'] == pytest.approx([1.72, 1.225, 0.])
    from harness.zone_own_guards import OwnPose, SweepGuard
    guard = SweepGuard(load(CORRIDOR))
    for x, y, yaw in c['placement_xyyaw'].values():
        assert guard.chassis_clearance(OwnPose(x, y, yaw, 0., 0.))[0] > .05
    assert c['pair_policy'] == 'v5h' and c['teacher_held'] is True and 'passage' not in json.dumps(
        sp.teacher_cases('carry', leg=1, subset={'nominal'}))


def test_passage_cases_are_refused_with_an_explicit_code_when_the_pair_cannot_pass():
    with pytest.raises(pp.PassageRefusal, match='PAIR_PASSAGE_TOO_MANY_SEGMENTS'):
        pp.passage_teacher_cases('carry', CORRIDOR, passage='auto', target='B', leg=3)


def test_runner_builds_passage_cases_only_when_asked():
    from scripts import run_pair_stage_probes as runner
    base = ['--stage', 'carry', '--sources', 'teacher', '--legs', '2', '3', '--cells', 'nominal', '--output', '/tmp/unused']
    plain = runner.build_cases(runner.parser().parse_args(base))
    assert all('map' not in c and 'pair_passage' not in c for c in plain)
    got = runner.build_cases(runner.parser().parse_args(base + ['--passage-map', CORRIDOR, '--passage-target', 'A']))
    assert len(got) == 6 and {c['leg'] for c in got} == {2, 3} and all(c['map'] == CORRIDOR for c in got)
    assert len({c['case_id'] for c in got}) == 6


def test_cli_reports_plan_and_refusal(capsys):
    assert pp.main(['--map', CORRIDOR, '--target', 'A']) == 0
    assert json.loads(capsys.readouterr().out)['passage']['id'] == 'corridor_1'
    assert pp.main(['--map', CORRIDOR, '--target', 'B']) == 2
    assert json.loads(capsys.readouterr().out)['refused'] == 'PAIR_PASSAGE_TOO_MANY_SEGMENTS'
    assert pp.main(['--map', DOOR_MAP]) == 0
    assert json.loads(capsys.readouterr().out)['legacy_m2_door_route'] is True
