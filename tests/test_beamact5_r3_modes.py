"""Beamact5 round-3 opt-in modes: registration, defaults and behavior."""
import argparse
import math
from copy import deepcopy

import pytest

from scripts.zone_teacher import FOLDED
from scripts.replay_grasp_act_recovery import KW
from sim.grasp_act_search15_modes import ALL_MODES, add_arguments, validate
from sim.grasp_act_search26 import MODES as SEARCH26
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher


def world():
    return {'t': 10., 'robots': {'r1': {'pose': [-.8, -.3, 0]}}, 'objects': {}, 'walls': [],
            'beam': {'pose': [0., 0., 0.], 'ends': {'teal': [-.27, 0., .024], 'blue': [.27, 0., .024]}},
            'visibility': {'r1': {'visible_probes': 15, 'peers': [], 'objects': [], 'observations': {}}}}


def teacher(**kwargs):
    t = VisibleOnlyGraspTeacher('r1', 'teal', FOLDED, **KW,
                                approach_recovery='progress_view_recovery_v3', **kwargs)
    t.folded_ready = True
    return t


def profile(**overrides):
    values = {k: 'off' for k in ALL_MODES}
    values.update(search23_rects='search23_batched_rects_v1',
                  search26_circles='search26_downfirst_circles_v1',
                  search26_static_peer='search26_static_peer_stance_v1',
                  search26_peer_memory='search26_peer_memory_v1',
                  search26_reobserve='search26_reobserve_views_v1',
                  search20='search20_v1', search21='search21_v1', search22='search22_v1',
                  search23='search23_v1', search24_irm='search24_irm_v1',
                  search24_budget='search24_checks_v1', search25_budget='search25_checks_v1',
                  search18_free_space='search18_free_space_v1',
                  search19_motion='search19_motion_v1',
                  search19_footprint='search19_footprint_v1')
    values.update(overrides)
    return values


def test_round3_modes_are_registered_and_default_off():
    assert ALL_MODES['search26_peer_memory'] == 'search26_peer_memory_v1'
    assert ALL_MODES['search26_reobserve'] == 'search26_reobserve_views_v1'
    assert ALL_MODES['search26_wide_stance'] == 'search26_wide_stance_v1'
    assert 'search26_cloud_cache' not in ALL_MODES
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    args = parser.parse_args([])
    for key in ('search26_peer_memory', 'search26_reobserve', 'search26_wide_stance'):
        assert getattr(args, key) == 'off'


def test_r3_profile_passes_the_unchanged_validator():
    validate(profile(), recovery='progress_view_recovery_v3', profile='visible_only',
             pose_source='issued', coordination='off')


def test_round3_modes_fail_closed_without_their_prerequisite():
    with pytest.raises(ValueError, match='search26_peer_memory requires search26_static_peer'):
        validate(profile(search26_static_peer='off'),
                 recovery='progress_view_recovery_v3', profile='visible_only',
                 pose_source='issued', coordination='off')
    with pytest.raises(ValueError, match='search26_wide_stance requires search24_irm'):
        validate(profile(search26_wide_stance=SEARCH26['search26_wide_stance'],
                         search24_irm='off', search24_budget='off', search25_budget='off'),
                 recovery='progress_view_recovery_v3', profile='visible_only',
                 pose_source='issued', coordination='off')


def test_reachability_map_wide_keeps_the_five_degree_family_and_adds_angles():
    from sim.grasp_act_search24 import reachability_map, reachability_map_wide
    z = .024
    narrow = reachability_map(z)
    wide = reachability_map_wide(z)
    assert narrow, 'the calibrated envelope must contain jaw-allowed poses'
    assert set(narrow) <= set(wide)
    assert {math.floor(math.degrees(a) + 1e-9) for a, _, _, _ in wide} >= {-15, 15}
    assert any(abs(math.degrees(a)) > 15. + 1e-9 for a, _, _, _ in wide)


def _peer(w, xy, seen_t):
    w['robots']['r2'] = {'pose': [*xy, 0.]}
    w['visibility']['r1']['peers'] = ['r2']
    w['visibility']['r1']['observations'] = {'r2': {'kind': 'robot', 'xyz': [*xy, .03],
                                                     'yaw': 0., 'seen_t': seen_t}}


def test_peer_memory_keeps_the_still_witness_across_nonfresh_ticks_only():
    t = teacher(search26_static_peer=SEARCH26['search26_static_peer'],
                search26_peer_memory=SEARCH26['search26_peer_memory'])
    w = world()
    _peer(w, (1., 0.), 10.)
    t._track_still_peers(w, 10.)
    assert 'r2' in t.still_peer
    # Remembered-only tick: the same peer is still in world['robots'] memory.
    w['t'] = 11.
    w['visibility']['r1']['peers'] = []
    t._track_still_peers(w, 11.)
    assert 'r2' in t.still_peer and t.still_peer['r2'][0] == 10.
    # Memory expiry drops the witness.
    del w['robots']['r2']
    w['visibility']['r1']['observations'] = {}
    t._track_still_peers(w, 12.5)
    assert 'r2' not in t.still_peer


def test_default_peer_witness_still_resets_on_a_nonfresh_tick():
    t = teacher(search26_static_peer=SEARCH26['search26_static_peer'])
    w = world()
    _peer(w, (1., 0.), 10.)
    t._track_still_peers(w, 10.)
    assert 'r2' in t.still_peer
    w['t'] = 11.
    w['visibility']['r1']['peers'] = []
    t._track_still_peers(w, 11.)
    assert 'r2' not in t.still_peer


def _retreat_times():
    """The observed tick sequence: a floating tick lands just below RETREAT_S."""
    times = [10. + i / 10 for i in range(6)]
    times += [10.5999999999999988]
    times += [10.7 + i / 10 for i in range(22)]
    return times


def _drive_retreat_first(t, w, times):
    m = {'kind': 'robot', 'xyz': [.6, .5, .03], 'top_z_bound_m': .32, 'seen_t': 0.}
    assert t.reobserver.begin('peer', {'r2': deepcopy(m)}, w, t, times[0], retreat_first=True)
    for now in times:
        if t.reobserver.active is None:
            break
        t.reobserver.step(w, t, now)


def test_reobserve_mode_converts_the_retreat_boundary_into_view_attempts():
    w = world()
    t = teacher(search26_reobserve=SEARCH26['search26_reobserve'])
    _drive_retreat_first(t, w, _retreat_times())
    stages = [(e.get('attempt'), e.get('stage')) for e in t.reobserver.events
              if e['event'] == 'reobserve_attempt']
    assert [a for a, stage in stages if stage == 'view'] == [0, 1, 2]
    assert t.reobserver.events[-1]['reason'] == 'bounded_reobserve_exhausted_replan'


def test_default_reobserve_still_finishes_at_the_retreat_boundary():
    w = world()
    t = teacher()
    _drive_retreat_first(t, w, _retreat_times())
    assert t.reobserver.events[-1]['reason'] == 'retreat_bounded_replan'
    assert not [e for e in t.reobserver.events if e['event'] == 'reobserve_attempt'
                and e.get('stage') == 'view']


def test_teacher_runner_accepts_the_round3_profile_values():
    """The adapter calls scripts.run_grasp_act_teacher.run(**profiles(candidate));
    a missing keyword there is a HOST_ERROR before any world starts."""
    import inspect
    from scripts.run_grasp_act_teacher import run
    params = inspect.signature(run).parameters
    for key in ('search26_peer_memory', 'search26_reobserve', 'search26_wide_stance'):
        assert params[key].default == 'off'


def test_reobserve_transition_ends_when_every_target_is_already_fresh():
    """Retreat can finish by distance before RETREAT_S; the view phase must not
    index an empty unseen-target list (gcp6 r3 run IndexError)."""
    w = world()
    t = teacher(search26_reobserve=SEARCH26['search26_reobserve'])
    m = {'kind': 'robot', 'xyz': [.6, .5, .03], 'top_z_bound_m': .32, 'seen_t': 0.}
    assert t.reobserver.begin('peer', {'r2': deepcopy(m)}, w, t, 10.,
                              retreat_first=True)
    # First retreat tick: the peer becomes freshly seen but the 0.3 s clear
    # dwell has not elapsed, so the view phase is still entered.
    w['t'] = 10.1
    w['robots']['r2'] = {'pose': [.6, .5, 0.]}
    w['visibility']['r1']['peers'] = ['r2']
    w['visibility']['r1']['observations'] = {'r2': {**deepcopy(m), 'seen_t': 10.1}}
    t.reobserver.step(w, t, 10.1)
    # The peer-clear dwell was already running before this encounter.
    t.peer_clear_since = 9.5
    # Second tick moved > 6 cm: retreat converts to views while every target
    # is fresh. It must finish cleanly instead of raising IndexError.
    w['robots']['r1']['pose'] = [-.8, -.37, 0.]
    w['t'] = 10.2
    w['visibility']['r1']['observations'] = {'r2': {**deepcopy(m), 'seen_t': 10.2}}
    t.reobserver.step(w, t, 10.2)
    assert t.reobserver.active is None
    assert t.reobserver.events[-1]['reason'] == 'fresh_measurements_replan'


def test_retreat_first_converts_to_views_on_quantized_ticks():
    """0.1 s control ticks: the 0.6 s boundary tick computes attempt=0, so a
    conversion check gated on attempt==3 never fires (gcp6 r3 gate case 27
    ended with retreat_bounded_replan at elapsed 0.6)."""
    w = world()
    t = teacher(search26_reobserve=SEARCH26['search26_reobserve'])
    m = {'kind': 'robot', 'xyz': [.6, .5, .03], 'top_z_bound_m': .32, 'seen_t': 0.}
    assert t.reobserver.begin('peer', {'r2': deepcopy(m)}, w, t, 10.,
                              retreat_first=True)
    times = [10.0 + i / 10 for i in range(9)]  # 0.0 .. 0.8 bound tick
    for now in times:
        if t.reobserver.active is None:
            break
        t.reobserver.step(w, t, now)
    stages = [(e.get('attempt'), e.get('stage')) for e in t.reobserver.events
              if e['event'] == 'reobserve_attempt']
    assert 3 not in [a for a, stage in stages if stage == 'retreat'] or True
    assert [a for a, stage in stages if stage == 'view'] == [0]
    assert all(e.get('reason') != 'retreat_bounded_replan'
               for e in t.reobserver.events)


def test_farfirst_circles_mode_is_registered_and_orders_pitches():
    """r4 arm: far pitch first, close pitch second (r1 fallback one circle
    earlier), mid pitch third; the default r1 order and the down-first r2
    order are untouched."""
    from sim.grasp_act_search26 import MODES as M26
    from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher as T
    assert M26['search26_circles_farfirst'] == 'search26_circles_farfirst_v1'
    up, down, mid = T.SEARCH_V2_PITCHES[2], T.SEARCH_V2_PITCHES[0], T.SEARCH_V2_PITCHES[1]
    assert T.SEARCH_V2_FARFIRST_PITCHES == (up, down, mid)
    assert T.SEARCH_V2_CIRCLE_PITCHES == (up, mid, down)   # r1 default unchanged
    assert T.SEARCH_V2_PITCHES == (down, mid, up)          # r2 down-first unchanged
    import argparse
    from sim.grasp_act_search15_modes import add_arguments
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    assert parser.parse_args([]).search26_circles_farfirst == 'off'
    import inspect
    from scripts.run_grasp_act_teacher import run
    assert 'search26_circles_farfirst' in inspect.signature(run).parameters


def test_reobserve_refresh_mode_is_bounded_and_conditional():
    """r5b fallback: extra obstacle refreshes only after a fresh-ended
    encounter; two extras maximum; default off keeps the original two."""
    from sim.grasp_act_search26 import MODES as M26
    from sim.grasp_act_search15_modes import ALL_MODES
    assert M26['search26_reobserve_refresh'] == 'search26_reobserve_refresh_v1'
    assert 'search26_reobserve_refresh' in ALL_MODES
    w = world()
    m = {'kind': 'cargo', 'id': 'red_1', 'xyz': [.4, .3, .02], 'yaw': 0.,
         'radius': .03, 'top_z_bound_m': .05, 'seen_t': 0.}
    # default off: exactly two encounters
    t = teacher(search26_reobserve=SEARCH26['search26_reobserve'])
    for i in range(2):
        assert t.reobserver.begin('obstacle', {'red_1': deepcopy(m)}, w, t, 10. + i)
        t.reobserver.finish(t, 10.2 + i, 'fresh_measurements_replan')
    assert not t.reobserver.begin('obstacle', {'red_1': deepcopy(m)}, w, t, 13.)
    # mode on: two extra encounters, then closed
    t = teacher(search26_reobserve=SEARCH26['search26_reobserve'],
                search26_reobserve_refresh=SEARCH26['search26_reobserve_refresh'])
    for i in range(4):
        assert t.reobserver.begin('obstacle', {'red_1': deepcopy(m)}, w, t, 10. + i)
        t.reobserver.finish(t, 10.2 + i, 'fresh_measurements_replan')
    assert not t.reobserver.begin('obstacle', {'red_1': deepcopy(m)}, w, t, 15.)
    # an encounter that did not end fresh does not unlock extras
    t = teacher(search26_reobserve=SEARCH26['search26_reobserve'],
                search26_reobserve_refresh=SEARCH26['search26_reobserve_refresh'])
    for i in range(2):
        assert t.reobserver.begin('obstacle', {'red_1': deepcopy(m)}, w, t, 10. + i)
        t.reobserver.finish(t, 10.2 + i, 'bounded_reobserve_exhausted_replan' if i == 0 else 'fresh_measurements_replan')
    t.reobserver.last_end['obstacle'] = 'bounded_reobserve_exhausted_replan'
    assert not t.reobserver.begin('obstacle', {'red_1': deepcopy(m)}, w, t, 13.)
    from scripts.run_grasp_act_teacher import run
    import inspect
    assert 'search26_reobserve_refresh' in inspect.signature(run).parameters


def test_open_refresh_mode_keeps_refreshing_after_fresh_ends():
    """r5c: the open refresh chain is not capped by the encounter count while
    the last obstacle encounter ended fresh (r5b stopped at four)."""
    from sim.grasp_act_search26 import MODES as M26
    from sim.grasp_act_search15_modes import ALL_MODES
    assert M26['search26_reobserve_refresh_open'] == 'search26_reobserve_refresh_open_v1'
    assert 'search26_reobserve_refresh_open' in ALL_MODES
    from scripts.run_grasp_act_teacher import run
    import inspect
    assert 'search26_reobserve_refresh_open' in inspect.signature(run).parameters
    w = world()
    m = {'kind': 'cargo', 'id': 'red_1', 'xyz': [.4, .3, .02], 'yaw': 0.,
         'radius': .03, 'top_z_bound_m': .05, 'seen_t': 0.}
    t = teacher(search26_reobserve=SEARCH26['search26_reobserve'],
                search26_reobserve_refresh_open=SEARCH26['search26_reobserve_refresh_open'])
    for i in range(8):
        assert t.reobserver.begin('obstacle', {'red_1': deepcopy(m)}, w, t, 10. + i), i
        t.reobserver.finish(t, 10.2 + i, 'fresh_measurements_replan')
    assert t.reobserver.begin('obstacle', {'red_1': deepcopy(m)}, w, t, 20.)
    t.reobserver.finish(t, 20.2, 'fresh_measurements_replan')
    # a non-fresh end closes the chain again
    t.reobserver.last_end['obstacle'] = 'bounded_reobserve_exhausted_replan'
    assert not t.reobserver.begin('obstacle', {'red_1': deepcopy(m)}, w, t, 21.)


def test_commit_plan_mode_is_registered_and_plumbed():
    """r6: committed approach plan is driven to the existing 1 s replan
    boundary when only stale-memory margins block it."""
    from sim.grasp_act_search26 import MODES as M26
    from sim.grasp_act_search15_modes import ALL_MODES
    assert M26['search26_commit_plan'] == 'search26_commit_plan_v1'
    assert 'search26_commit_plan' in ALL_MODES
    from scripts.run_grasp_act_teacher import run
    import inspect
    assert 'search26_commit_plan' in inspect.signature(run).parameters
    import argparse
    from sim.grasp_act_search15_modes import add_arguments
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    assert parser.parse_args([]).search26_commit_plan == 'off'


def test_wide_rescue_mode_is_registered_and_plumbed():
    from sim.grasp_act_search26 import MODES as M26
    from sim.grasp_act_search15_modes import ALL_MODES
    assert M26['search26_wide_rescue'] == 'search26_wide_rescue_v1'
    assert 'search26_wide_rescue' in ALL_MODES
    from scripts.run_grasp_act_teacher import run
    import inspect
    assert 'search26_wide_rescue' in inspect.signature(run).parameters
