"""Mac non-physical tests for the e2ewarp loaded-FK + map-correction adapters.

No simulator, no physics, no GPU.  Frames are synthetic own JPEGs; the static
map/orders are authored fixtures.  These tests assert default-off fail-closed
behaviour, the own-input boundary and the hash-bound manifest entry, not any
physical task result.
"""
import ast
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from harness.e2e_warp_runtime import OwnFrame
from harness import e2ewarp_mapcorr as mc
from harness.e2ewarp_mapcorr import (OPTION_CORRECTION, OPTION_LOADED_FK,
                                     OPTION_NAV, LoadedCameraFK,
                                     OwnStaticMapCorrection, navigation_factory)
from harness.grasp_act_contract import command as issued_command

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / 'experiments/2026-10-18-e2ewarp-r4-mapcorr'
SEARCH_PWM = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


def static_fixture():
    return dict(
        static_map=dict(
            bounds_m=[-1.05, 5.4, -3.15, 1.45],
            obstacles=[
                dict(id='wall_north', center_m=[2.175, 1.45], half_extents_m=[3.25, 0.025]),
                dict(id='wall_south', center_m=[2.175, -3.15], half_extents_m=[3.25, 0.025]),
                dict(id='wall_west', center_m=[-1.05, -0.85], half_extents_m=[0.025, 2.3]),
                dict(id='wall_east', center_m=[5.4, -0.85], half_extents_m=[0.025, 2.3]),
            ],
            regions={'B': dict(center_m=[4.6, -2.1], half_extents_m=[0.3, 0.7])},
        ),
        orders=[dict(order_id='order-1', kind='red', count=1,
                     identity='kind_fungible', required_robots=1,
                     destination_zone='B')],
    )


def toggles(**over):
    values = dict({key: 'off' for key in mc.ACCEPTED_TOGGLES})
    values.update({k: v for k, v in over.items()})
    return values


def own_jpeg(seed=0):
    rng = np.random.RandomState(seed)
    rgb = rng.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    ok, raw = cv2.imencode('.jpg', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return raw.tobytes()


def issued(*, grip=2000, wheels=(0., 0., 0., 0.), duration=(0., 0., 0., 0.),
           t=0.):
    pwm = {str(k): v for k, v in SEARCH_PWM.items()}
    pwm['1'] = grip
    return dict(t=float(t), wheels=list(wheels), duration_s=list(duration), pwm=pwm)


def frame(robot='r1', world=0, tick=0, sim=0., *, grip=2000, issued_rows=None):
    rows = issued_rows or (issued(grip=grip, t=sim),)
    return OwnFrame(robot, world, tick, sim, own_jpeg(tick), tuple(rows))


# -- import boundary ---------------------------------------------------------
def test_module_imports_only_own_input_libraries():
    tree = ast.parse((ROOT / 'harness/e2ewarp_mapcorr.py').read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split('.')[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])
    allowed = {'__future__', 'hashlib', 'json', 'math', 'numpy', 'cv2',
               'harness', 'pathlib'}
    assert imported <= allowed, imported - allowed
    for forbidden in ('mujoco', 'warp', 'torch', 'sim', 'scripts'):
        assert forbidden not in imported
    source = (ROOT / 'harness/e2ewarp_mapcorr.py').read_text()
    for needle in ('e2e_warp_physics', 'mjwarp', 'import mujoco', 'render('):
        assert needle not in source


# -- toggles / loaded FK -----------------------------------------------------
def test_toggles_are_default_off_and_validated():
    values = mc.resolve_toggles(static_fixture())
    assert set(values) == set(mc.ACCEPTED_TOGGLES)
    assert not any(values.values())
    on = mc.resolve_toggles(static_fixture(), toggles={OPTION_NAV: 'on'})
    assert on[OPTION_NAV] and not on[OPTION_CORRECTION]
    with pytest.raises(ValueError, match='UNKNOWN_MAPCORR_TOGGLE'):
        mc.resolve_toggles(static_fixture(), toggles={'other_toggle_v1': 'on'})
    with pytest.raises(ValueError, match='TOGGLE_VALUES_OFF_ON'):
        mc.resolve_toggles(static_fixture(), toggles={OPTION_NAV: 'yes'})


def test_loaded_fk_default_off_fails_closed_on_carry_command():
    result = LoadedCameraFK(option='off').resolve(issued(grip=1500)['pwm'])
    assert result['qualified'] is False
    assert result['reason'] == 'loaded_or_unknown_load_not_qualified'
    assert result['carry_command'] is True
    assert result['truth_inputs'] == 0 and result['held_world_reads'] == 0


def test_loaded_fk_on_qualifies_only_as_command_only_carry_model():
    result = LoadedCameraFK(option=OPTION_LOADED_FK).resolve(issued(grip=1500)['pwm'])
    assert result['qualified'] is True
    assert result['reason'] == 'servo_fk_nominal_carry_commands'
    assert result['carry_command'] is True
    assert result['command_only'] is True and result['load_measured'] is False
    assert len(result['origin']) == 3
    rotation = np.asarray(result['rotation'], float)
    assert rotation.shape == (3, 3)
    assert np.isfinite(rotation).all()


@pytest.mark.parametrize('option', ('off', OPTION_LOADED_FK))
def test_loaded_fk_unloaded_commands_qualified_for_both_options(option):
    result = LoadedCameraFK(option=option).resolve(issued(grip=2000)['pwm'])
    assert result['qualified'] is True
    assert result['reason'] == 'servo_fk_nominal_unloaded'
    assert result['carry_command'] is False


def test_loaded_fk_invalid_owned_command_fails_closed():
    result = LoadedCameraFK(option=OPTION_LOADED_FK).resolve({'1': 1500})
    assert result['qualified'] is False
    assert result['reason'].startswith('invalid_owned_command:')


def test_loaded_fk_camera_model_validation():
    with pytest.raises(ValueError, match='camera_model intrinsics required'):
        LoadedCameraFK(camera_model={'width': 640})
    with pytest.raises(ValueError, match='positive finite'):
        LoadedCameraFK(camera_model=dict(width=640, height=480, fx=0., fy=1.,
                                         cx=320., cy=240.))


# -- own/static map correction ----------------------------------------------
def test_correction_off_never_attempts_or_claims():
    correction = OwnStaticMapCorrection(static_fixture(), option='off')
    row = correction.step(0.1, 1, flow=dict(status='bootstrap', delta=None),
                          scan=dict(segments=[], camera=None),
                          issued=[issued(t=0.)], perception_available=True)
    assert row['status'] == 'off'
    assert row['reason'] == 'selfmap_map_correction_off'
    assert row['accepted'] is False and row['attempted'] is False
    assert row['map_correction_active'] is False
    report = correction.report()
    assert report['map_correction_active'] is False
    assert report['odometry_only'] is False and report['truth_inputs'] == 0


def test_correction_blocks_odometry_only_updates():
    correction = OwnStaticMapCorrection(static_fixture(), option=OPTION_CORRECTION)
    row = correction.step(0.1, 1, flow=dict(status='unknown_servo_change'),
                          scan=dict(segments=[], camera=None),
                          issued=[issued(t=0.)], perception_available=False)
    assert row['reason'] == 'own_rgb_perception_unavailable'
    assert row['accepted'] is False and row['attempted'] is False
    assert row['map_correction_active'] is False
    assert row['odometry_only'] is False
    assert row['spawn_anchor_used'] is False and row['truth_inputs'] == 0


def test_correction_ledger_carries_mandatory_rejection_fields():
    correction = OwnStaticMapCorrection(static_fixture(), option=OPTION_CORRECTION)
    row = correction.step(0.1, 1, flow=dict(status='bootstrap', delta=None),
                          scan=dict(segments=[], camera=None),
                          issued=[issued(t=0.)], perception_available=True)
    for key in ('category', 'reason', 'blocked_object', 'minimum_gap_m',
                'gap_status', 'truth_inputs', 'spawn_anchor_used',
                'odometry_only', 'static_map_sha256'):
        assert key in row
    assert row['category'] == 'map_correction'
    assert row['gap_status'] == 'not_measured'
    assert row['accepted'] is False


def test_correction_requires_causal_frames():
    correction = OwnStaticMapCorrection(static_fixture(), option=OPTION_CORRECTION)
    correction.step(0.1, 1, flow=dict(status='bootstrap', delta=None),
                    scan=dict(segments=[], camera=None), issued=[issued(t=0.)],
                    perception_available=True)
    with pytest.raises(ValueError, match='causal own frames required'):
        correction.step(0.1, 2, flow=dict(status='bootstrap', delta=None),
                        scan=dict(segments=[], camera=None), issued=[issued(t=0.)],
                        perception_available=True)


def test_correction_rejects_unsupported_issued_command_shape():
    correction = OwnStaticMapCorrection(static_fixture(), option=OPTION_CORRECTION)
    row = correction.step(0.1, 1, flow=dict(status='bootstrap'),
                          scan=dict(segments=[], camera=None),
                          issued=[issued(wheels=(1., 0., 0., 0.),
                                         duration=(0.1, 0.2, 0.1, 0.1))],
                          perception_available=True)
    assert row['reason'] == 'unsupported_issued_command_shape'
    assert row['accepted'] is False and row['attempted'] is False


# -- navigation ABI ----------------------------------------------------------
def test_navigation_default_off_reports_fail_closed():
    nav = navigation_factory('r1', static_fixture())
    report = nav.observe(frame())
    assert report['map_correction_active'] is False
    assert report['reason'] == 'e2e_warp_navigation_off'
    for key in ('handoff_ready', 'destination_arrived', 'holding_status',
                'evidence_revision', 'static_map_registered', 'input_audit'):
        assert key in report
    assert report['truth_inputs'] == 0 and report['spawn_anchor_used'] is False
    assert report['input_audit']['top_camera_control'] is False


def test_navigation_rejects_cross_robot_and_non_causal_frames():
    nav = navigation_factory('r1', static_fixture(), toggles=toggles(**{OPTION_NAV: 'on'}))
    with pytest.raises(ValueError, match='cross-robot'):
        nav.observe(frame(robot='r2'))
    nav.observe(frame(sim=0.))
    with pytest.raises(ValueError, match='causal own frames required'):
        nav.observe(frame(tick=1, sim=0.))


def test_navigation_enabled_builds_correction_evidence_and_audit():
    nav = navigation_factory(
        'r1', static_fixture(),
        toggles=toggles(**{OPTION_NAV: 'on', OPTION_CORRECTION: 'on',
                           OPTION_LOADED_FK: 'on'}))
    first = nav.observe(frame(tick=0, sim=0.))
    second = nav.observe(frame(tick=1, sim=0.1, issued_rows=(
        issued(grip=2000, t=0.1),)))
    correction = second['correction']
    assert second['map_correction_active'] is True
    assert correction['last']['category'] == 'map_correction'
    assert correction['last']['spawn_anchor_used'] is False
    assert correction['last']['truth_inputs'] == 0
    assert correction['static_map_sha256'] == nav.static_sha256
    audit = second['input_audit']
    assert audit['top_camera_control'] is False and audit['held_world_reads'] == 0
    assert audit['truth_inputs'] == 0 and audit['spawn_anchor_used'] is False
    assert audit['odometry_only'] is False
    assert first['map_correction_active'] is True


def test_navigation_blocks_map_correction_when_carry_fk_unqualified():
    nav = navigation_factory(
        'r1', static_fixture(),
        toggles=toggles(**{OPTION_NAV: 'on', OPTION_CORRECTION: 'on'}))
    report = nav.observe(frame(grip=1500))
    assert report['map_correction_active'] is False
    assert report['reason'].startswith('own_rgb_perception_unavailable:')
    assert 'loaded_or_unknown_load_not_qualified' in report['reason']
    assert report['loaded_fk']['qualified'] is False


def test_navigation_hold_command_is_contract_valid():
    nav = navigation_factory('r1', static_fixture(),
                             toggles=toggles(**{OPTION_NAV: 'on'}))
    value = nav.command(0.1)
    checked = issued_command(value)
    assert checked['wheels'] == [0.] * 4 and checked['duration_s'] == [0.] * 4
    assert nav.task_candidates(completed=[]) == []


def test_navigation_start_validation():
    nav = navigation_factory('r1', static_fixture(),
                             toggles=toggles(**{OPTION_NAV: 'on'}))
    with pytest.raises(ValueError, match='missing task token'):
        nav.start(dict(object_kind='red'), phase='approach')
    with pytest.raises(ValueError, match='unknown navigation phase'):
        nav.start(dict(object_kind='red', role='solo', destination_zone='B',
                       order_id='order-1'), phase='fly')
    nav.start(dict(object_kind='red', role='solo', destination_zone='B',
                   order_id='order-1'), phase='approach')
    assert nav.instruction['order_id'] == 'order-1'


def test_confirm_act_uses_only_own_rgb_zone_evidence():
    nav = navigation_factory('r1', static_fixture(),
                             toggles=toggles(**{OPTION_NAV: 'on'}))
    nav.observe(frame())
    assert nav.confirm_act(frame(), 'grasp') is False
    assert nav.confirm_act(frame(), 'release') is False
    nav.last_zone = dict(destination_arrived=True, zone_visible=True)
    nav.instruction = dict(object_kind='red', role='solo',
                           destination_zone='B', order_id='order-1')
    assert nav.confirm_act(frame(), 'release') is True
    with pytest.raises(ValueError, match='unknown ACT skill'):
        nav.confirm_act(frame(), 'fly')


def test_accept_release_fix_requires_registered_correction():
    nav = navigation_factory('r1', static_fixture(),
                             toggles=toggles(**{OPTION_NAV: 'on',
                                                OPTION_CORRECTION: 'on'}))
    owner = dict(relocalized=True, static_map_registered=True,
                 truth_inputs=0, held_world_reads=0)
    assert nav.accept_release_fix(owner) is False          # unregistered
    nav.correction._registered = lambda: True
    assert nav.accept_release_fix(owner) is True
    assert nav.accept_release_fix(dict(owner, truth_inputs=1)) is False
    assert nav.accept_release_fix(dict(owner, relocalized=False)) is False


def test_on_messages_only_accepts_channel_rows():
    nav = navigation_factory('r1', static_fixture(),
                             toggles=toggles(**{OPTION_NAV: 'on'}))
    nav.on_messages([dict(sender='r2', body={'text': 'wait'})])
    assert nav.messages[0]['sender'] == 'r2'
    with pytest.raises(ValueError, match='channel message rows required'):
        nav.on_messages('wait')


class _Owner:
    """Injected owner navigation stub (not a physical controller)."""

    def __init__(self):
        self.started = None

    def observe(self, frame):
        return dict(handoff_ready=True, destination_arrived=True,
                    holding_status='held', evidence_revision=7,
                    map_correction_active=True)

    def task_candidates(self, completed):
        return [dict(id='owner-task', skill='transport',
                     instruction=dict(object_kind='red', role='solo',
                                      destination_zone='B', order_id='order-1'))]

    def start(self, instruction, phase):
        self.started = (dict(instruction), phase)

    def command(self, now):
        return issued_command(dict(t=float(now), wheels=[0.] * 4,
                                   duration_s=[0.] * 4,
                                   pwm={str(k): v for k, v in SEARCH_PWM.items()}))

    def confirm_act(self, frame, skill):
        return True

    def on_messages(self, rows):
        pass


def test_owner_navigation_injection_is_delegated_and_audited():
    owner = _Owner()
    nav = navigation_factory('r1', static_fixture(), owner_navigation=owner,
                             toggles=toggles(**{OPTION_NAV: 'on',
                                                OPTION_CORRECTION: 'on'}))
    report = nav.observe(frame())
    assert report['handoff_ready'] is True and report['destination_arrived'] is True
    assert report['map_correction_active'] is True
    assert report['holding_status'] == 'held'
    assert nav.task_candidates([])[0]['id'] == 'owner-task'
    nav.start(dict(object_kind='red', role='solo', destination_zone='B',
                   order_id='order-1'), phase='approach')
    assert owner.started[1] == 'approach'
    assert issued_command(nav.command(0.1))['wheels'] == [0.] * 4
    assert nav.confirm_act(frame(), 'release') is True

    class _BadOwner(_Owner):
        def observe(self, frame):
            return dict(map_correction_active=False)

    bad = navigation_factory('r1', static_fixture(), owner_navigation=_BadOwner(),
                             toggles=toggles(**{OPTION_NAV: 'on'}))
    with pytest.raises(ValueError, match='owner cannot disable'):
        bad.observe(frame())


# -- hash-bound manifest entry ----------------------------------------------
def test_manifest_entry_is_hash_bound_and_default_off():
    manifest = json.loads((EXPERIMENT / 'manifest-entry.json').read_text())
    assert manifest['schema'] == 'ugrp.e2ewarp.mapcorr_adapter_entry.v1'
    adapter = manifest['adapter']
    for entry in (adapter['navigation_factory'], adapter['loaded_camera_fk'],
                  adapter['selfmap_map_correction']):
        module, _, attr = entry['entry'].partition(':')
        assert module == 'harness.e2ewarp_mapcorr'
        assert callable(getattr(mc, attr))
        path = ROOT / (module.replace('.', '/') + '.py')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
    assert all(entry['default'] == 'off' for entry in adapter.values())
    correction = manifest['component_records']['selfmap_map_correction']
    assert correction['mode'] == 'on'
    assert correction['own_and_static_map'] is True
    assert correction['spawn_anchor_used'] is False
    assert correction['ready'] is False   # new physical gate still required
    loaded = manifest['component_records']['loaded_camera_fk']
    assert loaded['ready'] is False
    assert loaded['command_only'] is True and loaded['load_measured'] is False
    test_sha = hashlib.sha256((ROOT / 'tests/test_e2ewarp_mapcorr.py').read_bytes()).hexdigest()
    assert manifest['tests']['sha256'] == test_sha
    assert manifest['no_pooling'] is True
    assert manifest['owner_assets']['origin_commit'] == mc.OWNER_ORIGIN
