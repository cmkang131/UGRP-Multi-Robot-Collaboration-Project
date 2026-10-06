"""v98 frame gate: floor_light_v1 contrast values through a v98-only module; the shared module stays frozen.

No simulator, renderer or model. Reviewer BLOCK 5970668877 (2026-10-04).
"""
import base64
import builtins
import hashlib
import json
import sys
import types
from pathlib import Path

import cv2
import numpy as np
import pytest

from harness import zone_pair_admission as admission
from harness import zone_pair_grasp as grasp
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_frame_gate as fg
from harness import zone_pair_highpose_runtime as rt
from harness import zone_pair_vision as vision
from harness.zone_own_executor import ZoneOwnExecutor
from tests.test_highpose_grasp_view import Fake, representative_class
from tests.test_zone_pair_executor import robot

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures/highpose_recorded_frames'
FROZEN_VISION_SHA256 = 'cce72504edf01d119aafbefc8cb4ea1aa5a407196f9809f6cb5b8ec0bfecc9fc'   # origin/main b23fc087
KEYS = {'zone_pair_vision', 'zone_pair_admission', '_frame_gate', 'valid_frame', 'valid_frame_ob',
        'frame_gate', 'readiness_snapshot'}


def obs_from_jpeg(data, *, now=10., rid='r1'):
    return {'camera': 'robot_cam', 'robot_id': rid, 'frame_id': 3, 'sim_time': now - .05,
            'image': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest()}


def jpeg(frame):
    return cv2.imencode('.jpg', frame)[1].tobytes()


def recorded():
    return [(FIXTURES/row['file']).read_bytes()
            for row in json.loads((FIXTURES/'manifest.json').read_text())['frames']]


def synthetic():
    rng = np.random.default_rng(7)
    textured = rng.integers(40, 220, (480, 640, 3), dtype=np.uint8)
    covered = textured.copy()
    covered[300:] = 0                               # lower part of the valid circle black-covered
    smooth = cv2.GaussianBlur(textured, (0, 0), 25)
    return [jpeg(textured), jpeg(covered), jpeg(smooth), jpeg(np.full((480, 640, 3), 0, np.uint8)),
            jpeg(np.full((480, 640, 3), 128, np.uint8)), b'not a jpeg']


def refs(code):
    names = set(code.co_names) | {k for k in code.co_consts if isinstance(k, str)}
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            names |= refs(k)
    return names


def test_shared_frame_gate_module_is_byte_identical_to_main_and_has_no_process_state():
    assert hashlib.sha256((ROOT/'harness/zone_pair_vision.py').read_bytes()).hexdigest() == FROZEN_VISION_SHA256
    assert not hasattr(vision, 'use_gates') and not hasattr(vision, '_CONTRAST')


def test_v1_values_reproduce_the_frozen_verdicts_and_the_pinned_values_change_only_contrast():
    """FrameGate(15, 3) == frozen gate on every frame; the pinned gate differs only where contrast decided."""
    v1, pinned = fg.FrameGate(15., 3.), fg.gate()
    assert (pinned.spread_min, pinned.std_min) == (1., .22)
    frames = recorded() + synthetic()
    changed = 0
    for data in frames:
        for now in (10., 10.4):                       # fresh and stale (> .25 s) frames
            obs = obs_from_jpeg(data)
            for name in ('valid_frame', 'valid_frame_ob'):
                frozen = getattr(vision, name)(obs, 'r1', now)
                assert getattr(v1, name)(obs, 'r1', now) is frozen
                new = getattr(pinned, name)(obs, 'r1', now)
                if new is not frozen:
                    changed += 1
                    assert now == 10. and frozen is False and new is True   # only the contrast rule moved
    assert changed >= 20
    for level in (0, 128):                            # blank / uniform views stay invalid with the pinned values
        flat = obs_from_jpeg(jpeg(np.full((480, 640, 3), level, np.uint8)))
        assert not pinned.valid_frame(flat, 'r1', 10.) and not pinned.valid_frame_ob(flat, 'r1', 10.)


def test_policy_and_controller_selection_match_the_frozen_rules():
    g = fg.gate()
    ob, plain = types.SimpleNamespace(own_image_ob=True), types.SimpleNamespace(own_image_ob=False)
    assert g.frame_gate(ob) == g.valid_frame_ob and g.frame_gate(plain) == g.valid_frame
    assert g.frame_gate(None) == g.valid_frame
    assert g.controller_gate(types.SimpleNamespace(policy=ob)) == g.valid_frame_ob
    assert g.controller_gate(object()) == g.valid_frame
    assert vision.frame_gate(ob) is vision.valid_frame_ob and grasp._frame_gate(object()) is grasp.valid_frame


def test_private_import_answers_only_the_two_frozen_modules_and_patches_nothing():
    def probe():
        from harness.zone_pair_vision import frame_gate, valid_frame
        from harness.zone_pair_admission import readiness_snapshot
        return frame_gate, valid_frame, readiness_snapshot
    import_before, module_before = builtins.__import__, sys.modules['harness.zone_pair_vision']
    gate, valid, snapshot = fg.gated(probe)()
    assert gate == fg.gate().frame_gate and valid == fg.gate().valid_frame
    assert fg.is_gated(snapshot) and snapshot.__code__ is admission.readiness_snapshot.__code__
    assert probe() == (vision.frame_gate, vision.valid_frame, admission.readiness_snapshot)
    assert builtins.__import__ is import_before and sys.modules['harness.zone_pair_vision'] is module_before

    def plain():
        import harness.zone_pair_vision  # noqa: F401
    def package():
        from harness import zone_pair_vision  # noqa: F401
    def missing():
        from harness.zone_pair_vision import dark_level  # noqa: F401
    for function in (plain, package, missing):
        with pytest.raises(ImportError):
            fg.gated(function)()


GATED = {'step': 'harness.zone_pair_executor.PairExecution', 'arm_step': 'harness.zone_pair_executor.PairExecution',
         'preclose_check': 'harness.zone_final_pair_guards.CommandGuard',
         'observe_standoff': 'harness.zone_pair_guards.PairCommandGuard',
         '_ack': 'harness.zone_own_executor.ZoneOwnExecutor',
         'pair_readiness': 'harness.zone_own_executor.ZoneOwnExecutor'}


# v98 Execution.step/arm_step are v98 dispatchers (zone_pair_highpose_own_load_occlusion); the frozen code objects
# live in four bound copies: the v98 gate (_*_gated) and the accepting gate chosen per tick (_*_accepted).
BOUND = {'step': ('_step_gated', '_step_accepted'), 'arm_step': ('_arm_step_gated', '_arm_step_accepted')}


def owner(cls, name):
    return next(k for k in cls.__mro__ if name in vars(k))


def test_every_frozen_gate_reference_in_the_v98_classes_is_replaced():
    """Walk every class of each v98 MRO: each frozen function that reaches the shared gate is shadowed by a
    v98 replacement that runs the same code object with the v98 gate (or is v98's own code)."""
    replaced = {'harness.zone_pair_grasp.PairGraspRelook._wait_close': 'HighController._wait_close (v98 code)',
                'harness.zone_pair_grasp.PairGraspRelook._grasp': 'HighController._grasp -> _RELOOK_GRASP',
                'harness.zone_pair_guards.PairCommandGuard.preclose_check': 'CommandGuard.preclose_check'}
    seen = set()
    for cls in (representative_class(), rt.Execution, rt.CommandGuard, rt.OwnExecutor):
        for k in cls.__mro__:
            for name, f in vars(k).items():
                f = getattr(f, '__func__', f)
                if not isinstance(f, types.FunctionType) or not refs(f.__code__) & KEYS:
                    continue
                key = f'{k.__module__}.{k.__qualname__}.{name}'
                seen.add(key)
                if k.__module__.startswith('harness.zone_pair_highpose'):
                    assert fg.is_gated(f) or k is rt.HighController, key
                    continue
                resolved = getattr(cls, BOUND[name][0] if cls is rt.Execution and name in BOUND else name)
                if fg.is_gated(resolved) and resolved.__code__ is f.__code__:
                    continue
                assert key in replaced, key
    assert seen == {f'{m}.{n}' for n, m in GATED.items()} | set(replaced) | {
        'harness.zone_pair_highpose_runtime.HighController._wait_close',
        'harness.zone_pair_highpose_runtime.CommandGuard.preclose_check',
        'harness.zone_pair_highpose_runtime.CommandGuard.observe_standoff',
        'harness.zone_pair_highpose_runtime.Execution._step_gated',
        'harness.zone_pair_highpose_runtime.Execution._arm_step_gated',
        'harness.zone_pair_highpose_runtime.Execution._step_accepted',
        'harness.zone_pair_highpose_runtime.Execution._arm_step_accepted',
        'harness.zone_pair_highpose_runtime.OwnExecutor._ack',
        'harness.zone_pair_highpose_runtime.OwnExecutor.pair_readiness'}
    for name, frozen_owner in GATED.items():
        cls = {'step': rt.Execution, 'arm_step': rt.Execution, 'preclose_check': rt.CommandGuard,
               'observe_standoff': rt.CommandGuard}.get(name, rt.OwnExecutor)
        base = owner(cls.__mro__[1], name)
        assert f'{base.__module__}.{base.__qualname__}' == frozen_owner
        for attr in (BOUND[name] if cls is rt.Execution else (name,)):
            resolved = getattr(cls, attr)
            assert fg.is_gated(resolved) and resolved.__code__ is getattr(base, name).__code__
            assert 'super' not in resolved.__code__.co_names
    assert all(fg.is_gated_accepted(getattr(rt.Execution, a)) and not fg.is_gated_accepted(getattr(rt.Execution, g))
               for g, a in (BOUND['step'], BOUND['arm_step']))
    relook = rt._RELOOK_GRASP
    assert fg.is_gated(relook) and relook.__code__ is grasp.PairGraspRelook._grasp.__code__
    assert relook.__globals__['_frame_gate'] is fg.controller_gate
    mro = representative_class().__mro__
    between = mro[mro.index(rt.HighController)+1:mro.index(grasp.PairGraspRelook)]
    assert not [k for k in between if '_grasp' in vars(k)]
    assert 'super' not in rt.HighController._grasp.__code__.co_names


@pytest.fixture
def frozen_gate_tripwire(monkeypatch):
    """Any call into the shared frame gate fails the test."""
    def boom(*a, **k):
        raise AssertionError('frozen zone_pair_vision gate reached from v98')
    for module, names in ((vision, ('valid_frame', 'valid_frame_ob', 'frame_gate')),
                          (grasp, ('valid_frame', 'valid_frame_ob', '_frame_gate'))):
        for name in names:
            monkeypatch.setattr(module, name, boom)


def flat_floor_obs(rid, now):
    """A recorded valid floor view that the frozen valid_frame rejects and the v98 gate accepts."""
    for data in recorded():
        obs = obs_from_jpeg(data, now=now, rid=rid)
        if not fg.FrameGate(15., 3.).valid_frame(obs, rid, now) and fg.gate().valid_frame(obs, rid, now):
            return obs
    raise AssertionError('no recorded flat floor view')


def test_v98_admission_uses_the_v98_valid_frame_and_never_the_shared_gate(frozen_gate_tripwire):
    frozen, new = robot('r1'), robot('r1')
    new.__class__ = rt.OwnExecutor
    obs = {**frozen.last_obs, **flat_floor_obs('r1', 0.)}
    frozen.last_obs, new.last_obs = dict(obs), dict(obs)
    assert new.pair_readiness(0., 'cargoX', 'B') == 'available'
    new._ack('pair_carry', {'order_id': 'cargoX', 'target_ref': 'B'}, False, 'SELF_UNCERTAIN')
    assert new.pair_admission_log[0]['checks']['image_valid'] is True
    with pytest.raises(AssertionError, match='frozen'):
        ZoneOwnExecutor.pair_readiness(frozen, 0., 'cargoX', 'B')


def test_admission_keeps_valid_frame_not_the_policy_gate(monkeypatch):
    """readiness_snapshot imports valid_frame; v98 keeps that (no own_image_ob switch at admission)."""
    calls = []
    g = fg.gate()
    monkeypatch.setattr(g, 'valid_frame_ob', lambda *a: calls.append('ob') or True, raising=False)
    monkeypatch.setattr(g, 'valid_frame', lambda *a: calls.append('plain') or True, raising=False)
    fg._views.cache_clear()
    try:
        ex = robot('r1')
        ex.__class__ = rt.OwnExecutor
        ex.policy = types.SimpleNamespace(own_image_ob=True)
        ex.pair_readiness(0., 'cargoX', 'B')
        assert calls == ['plain']
    finally:
        fg._views.cache_clear()


def test_v98_close_and_grasp_use_the_v98_gate_and_never_the_shared_gate(monkeypatch, frozen_gate_tripwire):
    from scripts import run_m2_pair as m2
    monkeypatch.setattr(m2, 'grip_view_m2', lambda image: {'seen': False})
    ctl = Fake()
    ctl.obs = flat_floor_obs('r1', 10.5)
    rt.HighController._wait_close(ctl, 10.5, True)
    assert ctl.failed is None and ctl.state == 'grasp'
    stale = Fake()
    stale.obs = flat_floor_obs('r1', 10.5)
    rt.HighController._wait_close(stale, 10.9, True)            # frame older than .25 s: still refused
    assert stale.failed == 'PREGRASP_NOT_READY'


def test_runtime_record_and_registry_pin_the_v98_gate(monkeypatch):
    reg = c.registry()
    assert reg['frame_gate']['profile'] == c.FRAME_GATE_PROFILE == fg.PROFILE
    assert reg['frame_gate']['process_global_state'] is False
    assert reg['provider_id'] == c.PROVIDER_ID == 'opencv_owncam_final_pair_highpose_v98'
    assert fg.record()['frame_contrast_spread_min'] == c.own_image_gates()['values']['frame_contrast_spread_min']
    b = c.bundle('zone_wide_door_geometry_v3', 'p03')
    for path in ('harness/zone_pair_highpose_frame_gate.py', 'harness/zone_final_pair_binding.py'):
        assert b['source_sha256'][path] == c.base.sha(ROOT/path)
    bad = json.loads((ROOT/c.REGISTRY).read_text())
    bad['frame_gate']['profile'] = 'zone_pair_frame_gate_v1_dev'
    read = c.base.read
    monkeypatch.setattr(c.base, 'read', lambda path: bad if str(path).endswith(c.REGISTRY) else read(path))
    with pytest.raises(ValueError, match='registry mismatch'):
        c.registry()


def test_actor_adoption_fails_closed_on_an_unexpected_actor_class():
    class Other(ZoneOwnExecutor):
        pass
    ex = robot('r1')
    ex.__class__ = Other
    with pytest.raises(TypeError, match='ZoneOwnExecutor'):
        rt.adopt_v98_frame_gate(types.SimpleNamespace(actors={'r1': ex}))
