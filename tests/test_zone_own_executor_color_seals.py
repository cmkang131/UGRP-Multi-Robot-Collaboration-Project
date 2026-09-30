"""Independent batch G counterexamples, pinned to the reviewed PR #325 bytes.

Offline only: hash local bytes; no simulator or model execution.
Run with pytest. Set REVIEW_E2E_G_PR325_TREE to an extracted/fixed candidate
root to check a successor. All assertions are mandatory on the current tree.
Missing git objects/files are errors, never expected failures.
PR #329 has no confirmed counterexample in this review.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Adapted from independent review 01edc483: same five mandatory assertions.
REGISTRATION = 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json'
CHANGED_PINNED_SOURCES = (
    'harness/owncam_delivery_shared.py',
    'harness/zone_own_deliver.py',
    'harness/zone_own_team_host.py',
    'harness/zone_own_executor.py',
    'harness/zone_own_status.py',
)


def _candidate(path):
    tree = os.environ.get('REVIEW_E2E_G_PR325_TREE')
    return ((Path(tree) if tree else ROOT) / path).read_bytes()


@pytest.mark.parametrize('path', CHANGED_PINNED_SOURCES)
def test_pr325_preserves_current_v6e_source_bytes(path):
    """Expected: opt-in color support leaves the existing sealed source intact."""
    original = _candidate(REGISTRATION)
    assert hashlib.sha256(original).hexdigest() == '64c2680781f1b989312c3ac091c6e0458579ced7ed65d9e9730aadbc416f4bfd', 'Do not rewrite the old seal'
    expected = json.loads(original)['v6_contract']['source_sha256'][path]
    actual = hashlib.sha256(_candidate(path)).hexdigest()
    assert actual == expected, f'{path}: v6e={expected}, candidate={actual}'


def test_historical_registration_and_sealed_successor_stay_pinned():
    from tests.v6h_successor_pins import successor_pins
    assert _candidate(REGISTRATION) == (ROOT / REGISTRATION).read_bytes()
    for contract in ('v6_contract', 'scene_contract'):
        for path, expected in successor_pins(contract).items():
            assert hashlib.sha256(_candidate(path)).hexdigest() == expected, path


@pytest.mark.parametrize('source', ['harness/zone_own_driver.py', 'harness/zone_own_team_host.py'])
def test_successor_pin_audit_rejects_changed_and_unchanged_v6e_sources(monkeypatch, source):
    original = _candidate
    monkeypatch.setitem(globals(), '_candidate', lambda path:
                        original(path) + b'\n' if path == source else original(path))
    with pytest.raises(AssertionError, match=source):
        test_historical_registration_and_sealed_successor_stay_pinned()


def test_sealed_entrypoint_cannot_import_color_extension():
    from harness.python_source_closure import source_closure
    sealed = source_closure(ROOT, CHANGED_PINNED_SOURCES)
    color = {'harness/zone_color_box_executor.py', 'harness/zone_color_box_delivery.py',
             'harness/m1_color_delivery.py', 'harness/m1_color_contract.py',
             'harness/m1_color_perception.py', 'harness/wrist_color_boxes.py'}
    assert not color.intersection(sealed)
    from harness.zone_color_box_executor import controller_source_record
    record = controller_source_record()
    assert color <= record['controller_source_files'].keys()
    assert record['controller_source_sha256'] == hashlib.sha256(json.dumps(
        record['controller_source_files'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@pytest.mark.parametrize('kind', ('red', 'green'))
def test_importing_color_executor_does_not_enable_sealed_dispatch(kind):
    from harness.zone_own_executor import ZoneOwnExecutor
    from harness.zone_own_team_host import ZoneOwnExecutor as HostExecutor
    from harness.zone_own_deliver import _DeliverController
    from harness.owncam_delivery_shared import SharedPoseDelivery
    from tests.test_zone_own_executor_color_boxes import executor, WristColorBoxDelivery, PoseEstimate, MAP, CALIB, ROWS_Y
    candidate = executor(kind)
    legacy = ZoneOwnExecutor('r1', MAP, CALIB['params'], {'orders': list(candidate.orders.values())},
        skill_factory=WristColorBoxDelivery, pose_estimate_cls=PoseEstimate, search_rows_y=ROWS_Y, judgments=False)
    assert HostExecutor is ZoneOwnExecutor
    assert _DeliverController.__bases__ == (SharedPoseDelivery,)
    assert legacy.deliver('o', 'B')['rejected_reason'] == 'KIND_NOT_SUPPORTED_BY_M1_SKILL'
    assert candidate.deliver('o', 'B')['accepted']
    assert legacy.job is None and candidate.job.args['box_kind'] == kind


@pytest.mark.parametrize('kind', ('cyan', 'red', 'green'))
def test_real_color_controller_constructor_keeps_shared_provider_and_kind(kind, monkeypatch):
    from harness.zone_color_box_delivery import ColorDeliverController
    from harness.m1_color_delivery import ColorSharedPoseDelivery
    from tests.test_zone_own_executor_color_boxes import executor, order
    ex = executor(kind)
    assert ex.deliver('o', 'B')['accepted']
    monkeypatch.setattr(ex, '_tick_sweep', lambda *a: None)
    monkeypatch.setattr(ColorDeliverController, 'decide', lambda *a: {'mode': 'tick', 'commands': [{'kind': 'hold'}]})
    assert ex._step_deliver(1., ex.job)['commands'] == [{'kind': 'hold'}]
    ctl = ex.job.ctl
    assert isinstance(ctl, ColorSharedPoseDelivery)
    assert ctl.pose is ex.pose and ctl.gate is ex.gate and ctl.guard is ex.guard
    assert ctl.box_kind == kind and ctl.box_profile == 'm1_color_boxes_v1'
    assert ctl.skill_factory(order(kind)).box.box_kind == kind


@pytest.mark.parametrize('kind', ('cyan', 'red', 'green'))
def test_actual_slot_filter_and_clip_use_selected_kind(kind, monkeypatch):
    from types import SimpleNamespace
    from harness.zone_color_box_delivery import ColorDeliverController
    from harness.m1_color_delivery import ColorSharedPoseDelivery
    from tests.test_zone_own_executor_color_boxes import executor, observation
    ex = executor(kind)
    assert ex.deliver('o', 'B')['accepted']
    monkeypatch.setattr(ex, '_tick_sweep', lambda *a: None)
    monkeypatch.setattr(ColorDeliverController, 'decide', lambda *a: {'mode': 'tick'})
    ex._step_deliver(1., ex.job)
    ctl = ex.job.ctl
    ctl.slot_rect = ((.0, .7), (-.5, .5))
    report = SimpleNamespace(initialized=True, yaw_rad=0., x_m=0., y_m=0., t_est=1., std_xy_m=.01)
    wrong = next(k for k in ('cyan', 'red', 'green') if k != kind)
    ctl._search_detect(observation(f'{wrong}_clipped.png'), report)
    assert not ctl.near_clipped and not ctl.target_detections
    ctl._search_detect(observation(f'{kind}_clipped.png', 2), report)
    assert ctl.near_clipped and not ctl.target_detections
    ctl._search_detect(observation(f'{kind}_floor.png', 3), report)
    assert len(ctl.target_detections) == 1
    ctl.target_xy = tuple(ctl.target_detections[-1]['map_xy'])
    assert ctl._make_order().kind == kind
    before = len(ctl.target_detections)
    report.x_m = 10.
    ctl._search_detect(observation(f'{kind}_floor.png', 4), report)
    assert len(ctl.target_detections) == before


def test_unknown_color_factory_profile_is_rejected():
    from tests.test_zone_own_executor_color_boxes import executor
    def factory(*a, **kw):
        pytest.fail('invalid profile must fail before constructing any skill')
    factory.box_perception_profile = 'unregistered'
    with pytest.raises(ValueError, match='unknown M1 box profile'):
        executor(factory=factory)
