"""Injected provider constructor regressions; static maps/fake worker, no physics."""
import copy

import pytest

from harness.zone_own_driver import GuardedDriver
from harness.zone_own_executor import ZoneOwnExecutor
from harness.zone_pair_guards import GuardedPairApproach
from tests.test_vision_pose_source import CALIB, SEARCH_POSE, VIS3_MAP, provider
from tests.test_zone_own_executor import ROWS_Y, SHEET


def make_own(pose, static):
    own = ZoneOwnExecutor('r1', static, CALIB['params'], SHEET, pose_source=pose,
                          skill_factory=lambda *a: None, pose_estimate_cls=tuple, search_rows_y=ROWS_Y)
    own.servo = dict(SEARCH_POSE)
    return own


def make_driver(kind, own):
    if kind == 'pair':
        return GuardedPairApproach(own, own.params, goal_xyyaw=(1., .05, .4),
                                   door_xy=own.door_xy, initial_servo=own.servo)
    return GuardedDriver(own.pose.loc, own.map, own.params, loaded=kind == 'goto_loaded',
                         goal_xy=(1., .05), door_xy=own.door_xy, initial_servo=own.servo,
                         gate=own.gate, guard=own.guard)


@pytest.mark.parametrize('kind', ['pair', 'goto', 'goto_loaded'])
@pytest.mark.parametrize('boundary', ['no_landmarks', 'no_tag_fields', 'detector', 'localizer', 'frozen_init'])
def test_injected_vision_constructs_without_legacy_initialization(monkeypatch, kind, boundary):
    from harness.owncam_drive import OwnCamDriver
    from harness.owncam_localizer import OwnCamLocalizer
    from harness.wall_tags import TagDetector
    from harness.pose_provider import is_own_pose_provider

    p = provider()
    try:
        assert is_own_pose_provider(p)
        static = copy.deepcopy(VIS3_MAP)
        if boundary == 'no_landmarks':
            static.pop('landmarks', None)
        elif boundary == 'no_tag_fields':
            static['landmarks'] = {'tags': [{'center_m': [0., 0., 0.]}]}

        def forbidden(*args, **kwargs):
            pytest.fail(f'injected driver called {boundary}')

        if boundary == 'detector':
            monkeypatch.setattr(TagDetector, 'for_map', forbidden)
        elif boundary == 'localizer':
            monkeypatch.setattr(OwnCamLocalizer, '__init__', forbidden)
        elif boundary == 'frozen_init':
            monkeypatch.setattr(OwnCamDriver, '__init__', forbidden)
        own = make_own(p, static)
        before = copy.deepcopy(p.loc.rng.bit_generator.state)
        driver = make_driver(kind, own)
        assert driver.loc is p.loc and not hasattr(driver, 'detector')
        assert driver.last_estimate == p.loc.estimate()
        assert p.loc.rng.bit_generator.state == before and not p.worker.calls
        # Exercise the first active control tick with the injected belief only.
        assert driver.tick(0.)
        if kind == 'pair':
            assert driver._shared_pose is p and driver.goal_yaw == .4 and driver.has_door
            assert driver.relocalizations == 0 and driver.hold_yaw is None
    finally:
        p.close()


@pytest.mark.parametrize('kind', ['pair', 'goto', 'goto_loaded'])
def test_shared_constructor_preserves_frozen_controller_state(kind):
    from harness.owncam_drive_v2 import OwnCamDriverV2
    from harness.pair_owncam_approach import PairApproachDriverV2
    from tests.test_zone_own_executor import make

    own = make()
    own.servo = dict(SEARCH_POSE)
    active = make_driver(kind, own)
    kwargs = dict(door_xy=own.door_xy, initial_servo=own.servo)
    if kind == 'pair':
        frozen = PairApproachDriverV2(own.map, own.params, goal_xyyaw=(1., .05, .4), **kwargs)
    else:
        frozen = OwnCamDriverV2(own.map, own.params, loaded=kind == 'goto_loaded',
                                goal_xy=(1., .05), **kwargs)
    # Every non-provider field of both frozen constructors must be retained.
    state = {k: v for k, v in vars(frozen).items() if k not in ('loc', 'detector', 'last_estimate')}
    assert {k: getattr(active, k) for k in state} == state
    assert active.last_estimate == own.pose.loc.estimate()
