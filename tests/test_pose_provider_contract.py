"""Marker-independent control seam, frozen v5c parity, fake vision. No physics/inference."""
import ast
import copy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness.owncam_time import accepted_fix_checks
from harness.zone_pair_align import ranked_look_pans, relook_reason
from harness.zone_own_guards import OwnPose
from tests.test_zone_pair_grasp import fresh, real_pair
from tests.test_zone_pair_v5c import DATA, install

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'tests/fixtures/pose_provider_v5c'


def frozen_scope():
    manifest = json.loads((FROZEN / 'manifest.json').read_text())
    for name, digest in manifest['sha256'].items():
        assert hashlib.sha256((FROZEN / name).read_bytes()).hexdigest() == digest
    scope = {}
    exec((FROZEN / 'owncam_time.py').read_text(), scope)
    # Load the exact historical functions, without redirecting their imports to
    # today's predicate. Provider-specific legacy data stays in this test seam.
    import harness.zone_pair_align as align
    scope.update({k: v for k, v in vars(align).items() if k not in scope})
    scope.update(MAX_TAG_GAP_S=6., np=np, FIX_STD_XY_M=.05, FIX_STD_YAW_RAD=math.radians(3.))
    tree = ast.parse((FROZEN / 'zone_pair_align.py').read_text())
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    funcs += [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_align_fix_checks']
    grasp = ast.parse((FROZEN / 'zone_pair_grasp.py').read_text())
    cls = next(n for n in grasp.body if isinstance(n, ast.ClassDef))
    funcs += [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_grasp_pose_checks']
    exec(compile(ast.Module(body=funcs, type_ignores=[]), '<frozen v5c>', 'exec'), scope)
    return scope


def normalize(checks):
    return {k.replace('tag', 'fix'): v for k, v in checks.items()}


def test_dev09_dev10_exact_v5c_fix_decisions_and_pan_order_are_unchanged():
    old = frozen_scope()
    outcomes = []
    for row in DATA['decisions']:
        ep = install(row)
        now = row['observation']['sim_time']
        ctl, own = ep.controller, ep.own
        own.servo = {int(k): v for k, v in row['observation']['actuator_state']['servo_pulses'].items()}
        assert ctl._align_fix_checks(now) == normalize(old['_align_fix_checks'](ctl, now))
        assert ctl._grasp_pose_checks(now) == normalize(old['_grasp_pose_checks'](ctl, now))
        outcomes.append(ctl._align_fix_ready(now))
        reason = old['relook_reason'](own.last_report, now, last_tag_t=own.pose.loc.last_tag_t)
        assert relook_reason(own.last_report, now) == (None if reason is None else reason.replace('tag', 'fix'))
        # The exact old collision guard, PWM and scoring arithmetic, on saved own poses.
        from harness.zone_pair_geometry import PairSweepGuard
        guard = PairSweepGuard(own.guard, ep.plan['beam_geometry'], ep.arguments['role'])
        before = old['ranked_look_pans'](own.map, own.last_report, own.servo, guard)
        assert len(before) == 7
        after = ranked_look_pans(own.map, own.last_report, own.servo, guard, own.pose)
        assert [(x['pan'], x['score_px2']) for x in before] == [
            (x['pan'], x['observability_score']) for x in after]
    assert len(outcomes) == 10 and sum(outcomes) == 9


@pytest.mark.parametrize('source', ['tags_temporary', 'vision_zero_tag_v1', 'future_geometry_v2'])
@pytest.mark.parametrize('capture,ok', [(1.00004, True), (.99999, False), (1., False),
                                      (2.000001, False), (None, False), (math.nan, False)])
def test_raw_fix_contract_does_not_depend_on_provider_label_or_legacy_receipt(source, capture, ok):
    _, _, eps = real_pair(); ep = eps['r1']; fresh(ep, 2.)
    ep.controller.align_look_started_at = 1.
    ep.own.last_report = replace(ep.own.last_report, t_est=2., last_fix_t=capture, fix_age_s=.1,
                                 fix_source=source, since_tag_s=None, last_valid_obs={'n_cols': 20})
    # Poison legacy state: executors may only use the immutable published report.
    ep.own.pose.loc.last_tag_t = object()
    assert ep.controller._align_fix_ready(2.) is ok


def test_rounded_age_never_fabricates_a_raw_fix_and_prediction_never_renews_it():
    from harness.owncam_pose_source import PoseReport
    r = PoseReport(1.1, True, fix_age_s=.1, std_xy_m=.01, std_yaw_rad=.01)
    assert not all(accepted_fix_checks(r, 1.10004, 1.).values())
    r = replace(r, last_fix_t=1.00004)
    assert all(accepted_fix_checks(r, 1.10004, 1.).values())
    r = replace(r, t_est=8., fix_age_s=7.)
    assert r.last_fix_t == 1.00004 and relook_reason(r, 8.) == 'fix_gap'


def test_temporary_provider_publishes_raw_not_rounded_time_and_prior_is_not_a_fix():
    from tests.test_zone_own_executor import make
    ex = make(); p = ex.pose
    p.loc.initialized = True; p.loc.t = 1.10004; p.loc.last_tag_t = 1.00004
    p.loc.px[:] = [0., 0., 0.]
    r = p.report(1.10004)
    assert r.last_fix_t == 1.00004 and r.fix_age_s == r.since_tag_s == .1
    assert r.last_fix_t != r.t_est - r.fix_age_s
    assert r.fix_source == 'tags_temporary'
    p.begin_relocalization(1.10004, {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500})
    r = p.report(1.2)
    assert not r.initialized and r.last_fix_t is None


def test_vision_fake_scan_fix_no_prediction_refresh_and_geometry_score_has_no_side_effects():
    from tests.test_vision_pose_source import provider, feed, VIS3_MAP
    p = provider()
    assert p.report(0.).initialized and p.report(0.).last_fix_t is None  # setup prior only
    r = feed(p, 0., 1.)[-1]
    assert r.last_fix_t == .8 and r.fix_source == 'vision_zero_tag_v1'
    assert r.observation_quality['informative_columns'] > 0
    later = p.report(1.)
    assert later.last_fix_t == .8 and later.fix_age_s == .2
    pose = OwnPose.from_report(later)
    before = copy.deepcopy(p.loc._pf.__dict__)
    calls = len(p.worker.calls)
    scores = [p.expected_observability(pose, pan, VIS3_MAP) for pan in [1100, 1500, 1900]]
    assert all(math.isfinite(s) and s >= 0 for s in scores) and max(scores) > 0
    with_decoys = copy.deepcopy(VIS3_MAP)
    with_decoys.setdefault('landmarks', {})['tags'] = [{'invalid_marker': True}]
    assert scores == [p.expected_observability(pose, pan, with_decoys) for pan in [1100, 1500, 1900]]
    assert len(p.worker.calls) == calls
    for key in ('px', 'logw', 'scale'):
        assert np.array_equal(before[key], getattr(p.loc._pf, key))
    assert before['rng'].bit_generator.state == p.loc.rng.bit_generator.state
    assert p.loc._pf.last_scan_t == .8
    # A reset preserves the vision filter/prior; it cannot become the temporary provider.
    old = p.loc._pf
    p.begin_relocalization(1., dict(p.servo))
    assert p.loc._pf is old and p.report(1.).last_fix_t is None
    assert p.report(1.).fix_source == 'vision_zero_tag_v1'
    p.close()


def test_vision_worker_failure_never_publishes_an_accepted_fix():
    from tests.test_vision_pose_source import provider, feed
    p = provider(fail_at=2)
    reps = feed(p, 0., 1.2)
    assert any(r.initialized and r.last_fix_t is not None for r in reps)
    failed = [r for r in reps if not r.initialized]
    assert failed and all(r.last_fix_t is None and r.fix_age_s is None for r in failed)
    assert all(not all(accepted_fix_checks(r, r.t_est, 0.).values()) for r in failed)


def test_delayed_vision_keeps_capture_time_and_cannot_reuse_queued_prelook_fix():
    from harness.zone_study_pose_delay import DelayedPoseSource
    from tests.test_vision_pose_source import provider, FRAME, VIS3_MAP
    p = provider(); d = DelayedPoseSource(p)
    assert d.on_frame(.2, FRAME).last_fix_t is None
    assert d.report(.35).last_fix_t is None
    assert d.report(.36).last_fix_t == .2
    d.on_frame(.4, FRAME)
    d.begin_relocalization(.45, p.servo)
    assert d.report(.56).last_fix_t is None  # queued .4 image was invalidated
    d.on_frame(.7, FRAME)
    r = d.report(.86)
    assert r.last_fix_t == .7 and r.t_est == pytest.approx(.7)
    assert all(accepted_fix_checks(r, .86, .45).values())
    pose = OwnPose.from_report(r)
    assert d.expected_observability(pose, 1500, VIS3_MAP) == p.expected_observability(pose, 1500, VIS3_MAP)
    d.close()


def test_executor_accepts_registered_vision_provider_directly():
    from harness.zone_own_executor import ZoneOwnExecutor
    from tests.test_vision_pose_source import provider, VIS3_MAP, CALIB
    from tests.test_zone_own_executor import SHEET, ROWS_Y
    p = provider()
    ex = ZoneOwnExecutor('r1', VIS3_MAP, CALIB['params'], SHEET, pose_source=p,
                         skill_factory=lambda *a: None, pose_estimate_cls=tuple, search_rows_y=ROWS_Y)
    assert ex.pose is p
    p.close()


def test_fresh_vision_fix_works_in_pair_and_no_fix_does_not_use_legacy_localizer():
    from tests.test_vision_pose_source import provider, feed
    _, _, eps = real_pair(); ep = eps['r1']; fresh(ep, 1.)
    p = provider(); r = feed(p, 0., 1.)[-1]
    ep.own.pose = p; ep.controller.driver._shared_pose = p
    # Controlled covariance fixture verifies the interface, not localization accuracy.
    ep.own.last_report = replace(r, std_xy_m=.01, std_yaw_rad=.01)
    ep.own.gate.state = 'ok'
    ep.controller.align_look_started_at = ep.controller.pregrasp_started_at = .4
    assert ep.controller._align_fix_ready(.8) and ep.controller._grasp_pose_ready(.8)
    ep.own.last_report = replace(ep.own.last_report, last_fix_t=None)
    assert not ep.controller._align_fix_ready(.8) and not ep.controller._grasp_pose_ready(.8)
    p.close()


@pytest.mark.parametrize('loaded', [False, True])
@pytest.mark.parametrize('age', [None, 0., 3., 3.001, 8.])
@pytest.mark.parametrize('xy,yaw', [(.01, .01), (.071, .06)])
def test_unloaded_and_loaded_look_policy_matches_frozen_thresholds(loaded, age, xy, yaw):
    from harness.owncam_drive import OwnCamDriver, LOOK_IF_NO_TAG_S
    from harness.zone_own_driver import LOOK_IF_NO_FIX_S
    from tests.test_zone_own_executor_review3 import driver_at
    assert LOOK_IF_NO_FIX_S == LOOK_IF_NO_TAG_S
    a = driver_at((1., -.85, 0., xy, yaw, age)); a.loaded = loaded
    b = driver_at((1., -.85, 0., xy, yaw, age)); b.loaded = loaded
    est = a.loc.estimate()
    before = OwnCamDriver._needs_look(a, est, 0.)
    # Omit the historical field altogether from the new controller's input.
    est.pop('since_tag_s')
    after = b._needs_look(est, 0.)
    assert after == (None if before is None else before.replace('tag', 'fix'))
    assert a.last_look_xy == b.last_look_xy and a.checkpoints_done == b.checkpoints_done


@pytest.mark.parametrize('revision', ['PREREG_V5D', 'PREREG_V5E'])
def test_prepare_hold_and_old_registration_are_fail_closed(tmp_path, revision):
    from scripts import run_zone_pair_dev as d
    args = d.parser().parse_args(['--prereg', str(getattr(d, revision)), '--run-id', 'dev11',
                                  '--output', str(tmp_path / 'unused'), '--execute'])
    with pytest.raises(ValueError, match='scene contract/hash mismatch'):
        d.load_config(args)
    args.execute = False; args.prereg = d.PREREG_V5C
    with pytest.raises(ValueError, match='scene contract/hash mismatch'):
        d.load_config(args)
    assert not args.output.exists()
