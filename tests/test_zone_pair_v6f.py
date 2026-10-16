"""v6f: own_image_ob (optical-black dark reference) and bounded_retreat (no physics, no models).

Frames are synthetic (a bright beam band over a floor in shadow at V=7, as the destination set-down
r1 view is) so the tests need no recorded raw; the recorded-corpus figures are in
experiments/2026-09-29-pair-v6f-place/README.md.
"""
import base64
import dataclasses
import hashlib
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

import harness.zone_pair_geometry as geometry
import harness.zone_pair_vision as vision
from harness.owncam_pair_beam_v2 import _valid
from harness.zone_pair_v6_policy import POLICIES, REVISION_POLICIES, pair_policy
from harness.zone_pair_vision import frame_gate, valid_frame, valid_frame_ob

ROOT = Path(__file__).resolve().parents[1]


def obs_of(v, *, rid='r1', now=10., frame_id=3):
    """A robot_cam observation whose gray level is ``v`` (H x W uint8, so V == v before JPEG)."""
    ok, jpeg = cv2.imencode('.jpg', cv2.merge([v, v, v]), [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    data = jpeg.tobytes()
    return {'camera': 'robot_cam', 'robot_id': rid, 'frame_id': frame_id, 'sim_time': now - .05,
            'image': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest()}


def scene(floor_v, *, bright=120, bright_rows=250, black=0, texture=1):
    """Bright upper part (the beam/room), floor at ``floor_v`` below, optical-black exterior at ``black``."""
    rng = np.random.default_rng(3)
    v = np.full((480, 640), floor_v, np.int16)
    v += rng.integers(-texture, texture + 1, v.shape)
    v[:bright_rows] = bright + rng.integers(-8, 9, v[:bright_rows].shape)
    v[~_valid()] = black
    return np.clip(v, 0, 255).astype(np.uint8)


def test_flags_are_off_in_every_existing_policy_and_the_v6f_policies_are_v6c_plus_flags():
    for name in ('v5h', 'b-only', 'a+b', 'b-boot', 'a+b-boot', 'b-v6c'):
        p = pair_policy(name)
        assert (p.own_image_ob, p.bounded_retreat) == (False, False)
        assert frame_gate(p) is valid_frame
    base = pair_policy('b-v6c')
    assert pair_policy('b-v6f-a') == dataclasses.replace(base, name='b-v6f-a', own_image_ob=True)
    assert pair_policy('b-v6f-b') == dataclasses.replace(base, name='b-v6f-b', bounded_retreat=True)
    assert pair_policy('b-v6f') == dataclasses.replace(base, name='b-v6f', own_image_ob=True, bounded_retreat=True)
    assert frame_gate(pair_policy('b-v6f')) is valid_frame_ob and frame_gate(pair_policy('b-v6f-b')) is valid_frame
    assert frame_gate(None) is valid_frame
    assert REVISION_POLICIES['v6c'] == ('v5h', 'b-only', 'b-v6c')        # the registered v6c set is unchanged


def test_a_floor_in_shadow_is_rejected_by_the_fixed_level_and_accepted_against_the_optical_black_reference():
    v = scene(7)
    dark = (v[_valid()] < 8).mean()
    assert .25 <= dark <= .6                                              # the destination r1 view: 32-41 % of pixels < 8
    o = obs_of(v)
    assert valid_frame(o, 'r1', 10.) is False
    assert valid_frame_ob(o, 'r1', 10.) is True
    assert vision.dark_level(cv2.cvtColor(cv2.imdecode(np.frombuffer(base64.b64decode(o['image']), np.uint8), 1),
                                          cv2.COLOR_BGR2HSV)[..., 2]) == 2      # OB median 0 + 2 LSB


def test_a_view_that_is_wholly_black_uniform_or_mostly_covered_by_a_black_occluder_still_fails():
    for v in (np.zeros((480, 640), np.uint8),                              # lens capped / black frame
              np.where(_valid(), 5, 0).astype(np.uint8),                   # uniform dim: no contrast
              scene(0)):                                                    # black floor over 60 %
        o = obs_of(v)
        assert valid_frame(o, 'r1', 10.) is False and valid_frame_ob(o, 'r1', 10.) is False
    covered = scene(90, bright=200, bright_rows=480)                        # a lit scene, 40 % covered by exact black
    ys, xs = np.nonzero(_valid())
    covered[ys[xs < np.percentile(xs, 40)], xs[xs < np.percentile(xs, 40)]] = 0
    o = obs_of(covered)
    assert valid_frame(o, 'r1', 10.) is False and valid_frame_ob(o, 'r1', 10.) is False


def test_the_other_rules_are_shared_and_the_dark_level_is_capped_at_the_fixed_level():
    good = obs_of(scene(60, bright=140))
    assert valid_frame(good, 'r1', 10.) is True and valid_frame_ob(good, 'r1', 10.) is True   # a healthy view passes both
    assert valid_frame_ob(good, 'r2', 10.) is False and valid_frame_ob(good, 'r1', 10.6) is False   # robot id, staleness
    assert valid_frame_ob({**good, 'sha256': '0' * 64}, 'r1', 10.) is False
    assert valid_frame_ob({**good, 'frame_id': -1}, 'r1', 10.) is False
    assert valid_frame_ob({**good, 'image': 'AAAA'}, 'r1', 10.) is False
    # An exterior lifted to V=30 (a different sensor/JPEG floor) does not raise the dark level above 7.
    lifted = obs_of(scene(7, black=30))
    v = cv2.cvtColor(cv2.imdecode(np.frombuffer(base64.b64decode(lifted['image']), np.uint8), 1), cv2.COLOR_BGR2HSV)[..., 2]
    assert vision.dark_level(v) == vision.LEGACY_DARK_MAX == 7
    assert valid_frame_ob(lifted, 'r1', 10.) is False and valid_frame(lifted, 'r1', 10.) is False


def test_a_near_black_cover_above_the_optical_black_level_is_a_documented_limit_of_the_reference():
    # Not a promise: a cover whose pixels are V 3..7 (not exact black) is a low-light view to this gate.
    covered = scene(90, bright=200, bright_rows=480)
    ys, xs = np.nonzero(_valid())
    left = xs < np.percentile(xs, 40)
    covered[ys[left], xs[left]] = 6
    o = obs_of(covered)
    assert valid_frame(o, 'r1', 10.) is False and valid_frame_ob(o, 'r1', 10.) is True


def test_executor_step_uses_the_policy_gate(monkeypatch):
    from tests.test_zone_pair_grasp import fresh, real_pair
    for name, aborts in (('b-v6c', ['INVALID_OWN_IMAGE']), ('b-v6f-a', []), ('b-v6f', [])):
        _, _, eps = real_pair()
        ep = eps['r1']
        ep.policy = pair_policy(name)
        ep.check = lambda now: None
        fresh(ep, 5.)
        reasons, orig = [], ep.abort
        ep.abort = lambda now, reason, o=orig, r=reasons: (r.append(reason), o(now, reason))
        with monkeypatch.context() as m:
            m.setattr(vision, 'valid_frame', lambda o, rid, now: False)
            m.setattr(vision, 'valid_frame_ob', lambda o, rid, now: True)
            ep.step(5.)
        assert reasons == aborts, name


REVERSE = {'kind': 'mecanum', 'forward': -.04, 'left': 0., 'turn': 0., 'duration_s': .15}


def guard_check(policy, state, command, monkeypatch, *, veto=True):
    from harness.zone_pair_guards import PairCommandGuard
    from tests.test_zone_pair_grasp import fresh, real_pair
    _, _, eps = real_pair()
    ep = eps['r1']
    ep.policy = pair_policy(policy)
    fresh(ep, 5.)
    ep.controller.state = state
    reasons, events, orig = [], [], ep.abort
    ep.abort = lambda now, reason: (reasons.append(reason), orig(now, reason))
    ep.log = lambda rid, event, now, **kw: events.append(event)
    guard = PairCommandGuard(ep)
    monkeypatch.setattr(geometry.PairSweepGuard, 'motion_clear', lambda self, servo, pose, cmd, *, loaded: not veto)
    out = guard.check(5., [dict(command)])
    return out, reasons, events


def test_bounded_retreat_holds_instead_of_failing_only_for_the_reverse_command_after_release(monkeypatch):
    out, reasons, events = guard_check('b-v6f-b', 'released', REVERSE, monkeypatch)
    assert out == [{'kind': 'hold'}] and reasons == [] and events == ['retreat_bounded']
    # flag off: the unchanged veto still fails the job
    out, reasons, _ = guard_check('b-v6c', 'released', REVERSE, monkeypatch)
    assert out == [{'kind': 'hold'}] and reasons == ['PAIR_COLLISION_GUARD']
    # flag on but not the released reverse retreat: still the unchanged failure
    for state, cmd in (('lower', REVERSE), ('wait_open', REVERSE),
                       ('released', {**REVERSE, 'forward': .04}),
                       ('released', {**REVERSE, 'left': .02}),
                       ('released', {**REVERSE, 'turn': .1})):
        out, reasons, events = guard_check('b-v6f-b', state, cmd, monkeypatch)
        assert reasons == ['PAIR_COLLISION_GUARD'] and events == [], (state, cmd)


def test_bounded_retreat_never_clears_a_command_the_guard_would_have_cleared_differently(monkeypatch):
    # No veto: the flag changes nothing, the reverse command is issued as before.
    for policy in ('b-v6c', 'b-v6f-b'):
        out, reasons, events = guard_check(policy, 'released', REVERSE, monkeypatch, veto=False)
        assert out == [REVERSE] and reasons == [] and events == []


def test_probe_lists_the_v6f_policies_and_forces_the_ob_gate_with_the_image_valid_diagnostic():
    from harness import pair_stage_probe as sp
    assert set(POLICIES) - set(sp.POLICIES) == {'b-boot', 'a+b-boot'}       # the probe's policies are a subset
    assert {'b-v6f-a', 'b-v6f-b', 'b-v6f'} <= set(sp.POLICIES)
    program = ('from scripts import run_pair_stage_probes as r\n'
               'import harness.zone_pair_grasp as gr, harness.zone_pair_vision as vis\n'
               'from harness.zone_pair_v6_policy import pair_policy\n'
               'vis.valid_frame = lambda obs, rid, now: False\n'
               'vis.valid_frame_ob = lambda obs, rid, now: rid == "r2"\n'
               'r.IMAGE_VALID_REAL.clear()\n'
               'r.install_diag_patch("image_valid_off")\n'
               'for policy in ("b-v6c", "b-v6f"):\n'
               '    gate = vis.frame_gate(pair_policy(policy))\n'
               '    assert gate(None, "r1", 1.) is True and gate(None, "r2", 1.) is True\n'
               'assert gr.valid_frame_ob(None, "r1", 1.) is True and gr._frame_gate(type("C", (), {"policy": pair_policy("b-v6f")})())(None, "r1", 1.) is True\n'
               'assert r.IMAGE_VALID_REAL == {"r1": [0, 4], "r2": [1, 1]}, r.IMAGE_VALID_REAL\n')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_probe_records_the_omp_thread_count():
    from scripts import run_pair_stage_probes as r
    assert r.parser().parse_args([]).omp_threads == 2
    assert r.parser().parse_args(['--omp-threads', '1']).omp_threads == 1
