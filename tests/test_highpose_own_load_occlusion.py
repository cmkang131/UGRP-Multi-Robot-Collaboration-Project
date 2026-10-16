"""v98 own-load occlusion rule: a camera blocked by the held beam is no observation, not INVALID_OWN_IMAGE.

No simulator, renderer or model. Trigger: pair-llm-DEV-v103b-light-s911-8a1acdad-fast1 (no_comm), r1 frame 6736 at
SIM 338.05 under floor_light_nearclip_v1: a uniform dark view (value spread 0) refused by the per-step own-image gate
while the beam was held at the set-down pose. The recorded frames are in tests/fixtures/own_load_occlusion.
"""
import base64
import hashlib
import json
import types
from pathlib import Path

import cv2
import numpy as np
import pytest

from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_frame_gate as fg
from harness import zone_pair_highpose_grip as grip
from harness import zone_pair_highpose_own_load_occlusion as occ
from harness import zone_pair_highpose_runtime as rt
from harness.zone_pair_executor import PairExecution
from tests.test_highpose_frame_gate import obs_from_jpeg, recorded, synthetic
from tests.test_zone_pair_executor import SEARCH_POSE, active, ends, pair_obs, setup, start

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures/own_load_occlusion'


def frame(name):
    row = next(r for r in json.loads((FIXTURES/'manifest.json').read_text())['frames'] if r['file'] == name)
    data = (FIXTURES/name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == row['sha256']
    return data, row


def uniform(level, shape=(480, 640, 3)):
    return cv2.imencode('.jpg', np.full(shape, level, np.uint8))[1].tobytes()


HELD_VIEW, _ = frame('r1_frame_6705.jpg')         # held beam fills the view, thin floor band: still valid
OCCLUDED, _ = frame('r1_frame_6736.jpg')          # the frame the gate refused at SIM 338.05


def at(data, now, *, rid='r1', fid=7):
    """An observation of ``data`` captured 0.05 s before ``now``."""
    return obs_from_jpeg(data, now=now, rid=rid) | {'frame_id': fid, 'sim_time': now-.05}


# ---- the three-way verdict --------------------------------------------------------------------------------
def test_recorded_failure_frame_is_content_only_and_the_boolean_gate_still_refuses_it():
    g = fg.gate()
    obs = at(OCCLUDED, 338.05)
    for ob in (True, False):
        verdict, measures = g.assess(obs, 'r1', 338.05, ob=ob)
        assert verdict == fg.CONTENT_ONLY
        assert measures['value_spread'] == 0. and measures['dark_fraction'] == 0.
        assert measures['value_std'] == pytest.approx(.2244, abs=1e-3)           # std alone passes the 0.22 floor; the frame fails on value_spread 0 (< 1.0)
    assert not g.valid_frame(obs, 'r1', 338.05) and not g.valid_frame_ob(obs, 'r1', 338.05)
    held = at(HELD_VIEW, 336.55)
    assert g.assess(held, 'r1', 336.55, ob=True)[0] == fg.VALID and g.valid_frame_ob(held, 'r1', 336.55)


def test_verdict_is_the_boolean_gate_everywhere_and_content_only_needs_a_decodable_fresh_frame():
    g = fg.gate()
    for data in recorded()+synthetic()+[OCCLUDED, HELD_VIEW]:
        for now in (10., 10.4):                                   # fresh and stale (> 0.25 s)
            obs = obs_from_jpeg(data, now=10.)
            for ob, boolean in ((False, g.valid_frame), (True, g.valid_frame_ob)):
                verdict, measures = g.assess(obs, 'r1', now, ob=ob)
                assert (verdict == fg.VALID) is boolean(obs, 'r1', now)
                assert (measures is None) == (verdict == fg.INVALID)
                if now == 10.4:
                    assert verdict == fg.INVALID                  # stale: never content-only
    junk = obs_from_jpeg(b'not a jpeg', now=10.)
    small = obs_from_jpeg(uniform(0, (100, 100, 3)), now=10.)
    assert g.assess(junk, 'r1', 10., ob=True)[0] == fg.INVALID
    assert g.assess(small, 'r1', 10., ob=True)[0] == fg.INVALID   # wrong shape
    assert g.assess({**obs_from_jpeg(uniform(0), now=10.), 'sha256': '0'*64}, 'r1', 10., ob=True)[0] == fg.INVALID
    assert g.assess(None, 'r1', 10., ob=True)[0] == fg.INVALID
    for level in (0, 128):                                        # blank and uniform fresh views: content only
        assert g.assess(obs_from_jpeg(uniform(level), now=10.), 'r1', 10., ob=True)[0] == fg.CONTENT_ONLY


def test_accepted_binding_runs_the_frozen_code_with_an_accepting_gate_only_for_step_and_arm_step():
    def probe():
        from harness.zone_pair_vision import frame_gate
        return frame_gate
    gate = fg.gated_accepted(probe)()(types.SimpleNamespace(own_image_ob=True))
    assert gate({}, 'r1', 0.) is True and gate(None, 'r9', 1e9) is True
    assert fg.gated(probe)() == fg.gate().frame_gate                  # the ordinary v98 gate is untouched
    assert not fg.gate().valid_frame_ob(at(OCCLUDED, 338.05), 'r1', 338.05)
    for name in ('step', 'arm_step'):
        base = getattr(PairExecution, name)
        for attr in (f'_{name}_gated', f'_{name}_accepted'):
            assert getattr(rt.Execution, attr).__code__ is base.__code__
        assert fg.is_gated_accepted(getattr(rt.Execution, f'_{name}_accepted'))
        assert not fg.is_gated_accepted(getattr(rt.Execution, f'_{name}_gated'))
    # the accepting builtins answer nothing else of the frozen gate modules
    def plain():
        import harness.zone_pair_vision  # noqa: F401
    with pytest.raises(ImportError):
        fg.gated_accepted(plain)()


# ---- window and classification on a fake endpoint ---------------------------------------------------------
def fake_ep(state='carry', held=True, *, events=(), until=0., obs=None, ob=True, terminal=False):
    ctl = types.SimpleNamespace(state=state, beam_grasp_confirmed=held,
                                arm=types.SimpleNamespace(events=list(events), until=until))
    ep = types.SimpleNamespace(controller=ctl, own=types.SimpleNamespace(robot_id='r1', last_obs=obs),
                               policy=types.SimpleNamespace(own_image_ob=ob), terminal=terminal, events=[])
    ep.log = lambda rid, kind, now, **detail: ep.events.append({'robot_id': rid, 'event': kind, 'sim_s': now, **detail})
    return ep


def test_loaded_phases_need_the_own_grasp_receipt_and_the_release_window_needs_a_busy_arm():
    for state in sorted(occ.LOADED_PHASES):
        assert occ.OwnLoadOcclusion(fake_ep(state)).window(5.) == occ.LOADED
        assert occ.OwnLoadOcclusion(fake_ep(state, held=False)).window(5.) is None      # no receipt: not loaded
    for state in ('approach', 'align', 'pregrasp_descend', 'wait_close', 'grasp', 'done', 'failed', 'cp_backoff'):
        assert occ.OwnLoadOcclusion(fake_ep(state)).window(5.) is None                  # receipt alone is not enough
    for state in sorted(occ.RELEASE_PHASES):
        busy = occ.OwnLoadOcclusion(fake_ep(state, held=False, events=[(5.2, 1, 2000)], until=5.2))
        assert busy.window(5.) == occ.RELEASE
        assert occ.OwnLoadOcclusion(fake_ep(state, held=False, until=6.)).window(5.) == occ.RELEASE   # settle running
        assert occ.OwnLoadOcclusion(fake_ep(state, held=False, until=5.)).window(5.) is None          # arm idle
    assert occ.LOADED_PHASES >= {'lift', 'carry', 'lower', 'wait_open', 'refix_decide'}
    assert not occ.LOADED_PHASES & occ.RELEASE_PHASES


def test_occluded_frame_is_accepted_logged_once_per_episode_and_ends_on_the_next_valid_frame():
    ep = fake_ep('lower', obs=at(OCCLUDED, 338.05, fid=6736))
    o = occ.OwnLoadOcclusion(ep)
    assert o.accepts(338.05) and o.accepts(338.05)                      # same tick twice: one record
    ep.own.last_obs = at(OCCLUDED, 338.10, fid=6737)
    assert o.accepts(338.10)
    ep.own.last_obs = at(HELD_VIEW, 338.15, fid=6738)
    assert o.accepts(338.15) and o.episode is None                       # valid frame closes the episode
    names = [e['event'] for e in ep.events]
    assert names == [occ.EVENT_START, occ.EVENT_END]
    start, end = ep.events
    assert start['verdict'] == occ.VERDICT == 'OCCLUDED_BY_OWN_LOAD' and start['frame_id'] == 6736
    assert start['window'] == occ.LOADED and start['phase'] == 'lower' and start['value_spread'] == 0.
    assert end['frames'] == 2 and end['duration_s'] == pytest.approx(.1) and end['last_frame_id'] == 6737
    export = o.export()
    assert export['occluded_frames'] == 2 and export['episodes'][0]['open_at_job_end'] is False
    assert o.note_row({'frame_id': 6736}) == {'own_image': occ.VERDICT} and o.note_row({'frame_id': 6738}) == {}
    assert o.note_row({'kind': 'anchor'}) == {}


def test_everything_else_is_left_to_the_unchanged_gate():
    now = 338.05
    cases = {
        'unloaded dark frame': dict(state='carry', held=False, obs=at(OCCLUDED, now)),
        'grasp posture, no receipt': dict(state='wait_close', held=False, obs=at(OCCLUDED, now)),
        'stale frame while loaded': dict(state='lower', obs=obs_from_jpeg(OCCLUDED, now=now-1.)),
        'undecodable while loaded': dict(state='lower', obs=at(b'not a jpeg', now)),
        'wrong shape while loaded': dict(state='lower', obs=at(uniform(0, (100, 100, 3)), now)),
        'no frame while loaded': dict(state='lower', obs=None),
        'terminal endpoint': dict(state='lower', obs=at(OCCLUDED, now), terminal=True),
        'released, arm idle': dict(state='released', held=False, obs=at(OCCLUDED, now), until=now-.01),
    }
    for name, kw in cases.items():
        ep = fake_ep(**kw)
        assert occ.OwnLoadOcclusion(ep).accepts(now) is False, name
        assert not ep.events, name
    for name, kw in {'valid frame, unloaded': dict(state='carry', held=False, obs=at(HELD_VIEW, now))}.items():
        assert occ.OwnLoadOcclusion(fake_ep(**kw)).accepts(now) is False                 # not loaded: frozen path


def test_verdict_is_memoised_per_frame_and_tick():
    ep = fake_ep('carry', obs=at(HELD_VIEW, 5.))
    o = occ.OwnLoadOcclusion(ep)
    calls = []
    real = fg.gate().assess
    gate = types.SimpleNamespace(assess=lambda *a, **k: calls.append(a) or real(*a, **k))
    import harness.zone_pair_highpose_own_load_occlusion as module
    original = module.frame_gate.gate
    module.frame_gate.gate = lambda: gate
    try:
        assert o.accepts(5.) and o.accepts(5.) and o.accepts(5.)
        assert len(calls) == 1
        assert o.accepts(5.05) and len(calls) == 2                       # new tick: freshness is re-evaluated
    finally:
        module.frame_gate.gate = original


# ---- the real frozen step/arm_step through the v98 dispatchers --------------------------------------------
def carrying_pair():
    host, exs = setup()
    assert start(host)['accepted']
    a, b = (active(host)[r] for r in ('r1', 'r2'))
    for ep in (a, b):
        ep.__class__ = rt.Execution                                        # the v98 dispatchers over the frozen code
        ep.command_guard.before_control = lambda now: True                 # pose/guard checks are not under test here
        ep.command_guard.check = lambda now, commands: commands
    for now in (0., .1, .2):                                               # the executor tests' lift handshake
        for ep in (a, b):
            ep.step(now)
    assert a.controller.state == b.controller.state == 'carry'
    return host, exs, a, b, .25


def feed(exs, now, data, rids=('r1', 'r2'), *, fid=[100]):
    for rid in rids:
        fid[0] += 1
        exs[rid].last_obs = pair_obs(rid, fid[0], now-.05, SEARCH_POSE) | {
            'image': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest()}


@pytest.mark.parametrize('dev_light', [True, False])
def test_loaded_occlusion_does_not_abort_the_real_step_and_arm_step(monkeypatch, dev_light):
    monkeypatch.setattr(c, 'DEV_LIGHT', dev_light)                         # a sensing rule: formal and DEV alike
    host, exs, a, b, now = carrying_pair()
    a.controller.beam_grasp_confirmed = True
    commands = None
    for _ in range(6):
        feed(exs, now, OCCLUDED, rids=('r1',))
        feed(exs, now, HELD_VIEW, rids=('r2',))
        commands = [ep.step(now) for ep in (a, b)]
        assert a.arm_step(now) is not None and b.arm_step(now) is not None
        now = round(now+.05, 3)
    assert not a.terminal and not b.terminal and not ends(exs['r1']) and not ends(exs['r2'])
    assert commands[0]['commands'][0]['kind'] == 'mecanum'                # the commanded motion went on
    assert [e['event'] for e in a.events if e['event'].startswith('own_image_')] == [occ.EVENT_START]
    assert a.own_load_occlusion.export()['occluded_frames'] == 6 and not b.own_load_occlusion.episodes
    feed(exs, now, HELD_VIEW)                                              # a valid frame again closes the episode
    for ep in (a, b):
        ep.step(now)
    assert [e['event'] for e in a.events if e['event'].startswith('own_image_')] == [occ.EVENT_START, occ.EVENT_END]
    assert not a.terminal


def test_unloaded_or_stale_frames_still_abort_the_real_step_with_invalid_own_image():
    for case in ('unloaded', 'stale', 'garbage', 'released_idle'):
        host, exs, a, b, now = carrying_pair()
        if case == 'unloaded':
            a.controller.beam_grasp_confirmed = False
            feed(exs, now, OCCLUDED, rids=('r1',))
        elif case == 'stale':
            a.controller.beam_grasp_confirmed = True
            exs['r1'].last_obs = pair_obs('r1', 500, now-1., SEARCH_POSE) | {
                'image': base64.b64encode(OCCLUDED).decode(), 'sha256': hashlib.sha256(OCCLUDED).hexdigest()}
        elif case == 'garbage':
            a.controller.beam_grasp_confirmed = True
            feed(exs, now, b'not a jpeg', rids=('r1',))
        else:
            a.controller.beam_grasp_confirmed, a.controller.state = False, 'released'
            a.controller.arm.events, a.controller.arm.until = [], now-.5
            feed(exs, now, OCCLUDED, rids=('r1',))
        feed(exs, now, HELD_VIEW, rids=('r2',))
        a.step(now)
        assert a.terminal, case
        assert [e['detail']['reason'] for e in exs['r1'].events if e['event'] == 'job_failed'] == ['INVALID_OWN_IMAGE'], case
        assert not a.own_load_occlusion.episodes, case


def test_arm_step_also_aborts_unloaded_and_continues_when_loaded():
    host, exs, a, b, now = carrying_pair()
    a.controller.beam_grasp_confirmed = True
    feed(exs, now, OCCLUDED)
    assert a.arm_step(now) == [] or isinstance(a.arm_step(now), list)
    assert not a.terminal
    host2, exs2, a2, b2, now2 = carrying_pair()
    feed(exs2, now2, OCCLUDED, rids=('r1',))
    assert a2.arm_step(now2) == [] and a2.terminal
    assert [e['detail']['reason'] for e in exs2['r1'].events if e['event'] == 'job_failed'] == ['INVALID_OWN_IMAGE']


def test_release_window_keeps_an_occluded_view_open_until_the_queued_arm_motion_ends():
    host, exs, a, b, now = carrying_pair()
    a.controller.beam_grasp_confirmed, a.controller.state = False, 'cp_open'    # open issued: receipt cleared
    a.controller.arm.events, a.controller.arm.until = [(now+10., 1, 2000)], now+1.5   # events stay queued (a rig clock)
    t = now
    while t < now+1.45:                                                       # open issued, arm motion still queued
        t = round(t+.05, 3)
        feed(exs, t, OCCLUDED, rids=('r1',))
        feed(exs, t, HELD_VIEW, rids=('r2',))
        a.step(t)
        b.step(t)
        assert not a.terminal and not b.terminal, t
    assert a.own_load_occlusion.episode is not None
    a.controller.arm.events, a.controller.arm.until = [], t                    # arm finished: the view must be clear
    t = round(t+.05, 3)
    feed(exs, t, OCCLUDED, rids=('r1',))
    feed(exs, t, HELD_VIEW, rids=('r2',))
    b.step(t)
    a.step(t)
    assert a.terminal
    assert [e['detail']['reason'] for e in exs['r1'].events if e['event'] == 'job_failed'] == ['INVALID_OWN_IMAGE']


# ---- records ------------------------------------------------------------------------------------------------
def test_grip_monitor_rows_of_an_occluded_frame_are_tagged_and_other_rows_are_not():
    o = occ.OwnLoadOcclusion(fake_ep('lower', obs=at(OCCLUDED, 338.05, fid=6736)))
    assert o.accepts(338.05)
    log = grip.GripMonitorLog(annotate=o.note_row)
    log.record('r1', 'transit_view', 338.05, frame_id=6736, relation={'ok': False})
    log.record('r1', 'transit_view', 338.0, frame_id=6735)
    log.record('r1', 'anchor', 338.0)
    rows = log.export()
    assert [r.get('own_image') for r in rows] == [occ.VERDICT, None, None]
    assert [r['scope'] for r in rows] == [grip.MONITOR_SCOPE]*3
    plain = grip.GripMonitorLog()
    plain.record('r1', 'transit_view', 1., frame_id=6736)
    assert 'own_image' not in plain.export()[0]


def test_bundle_and_student_record_carry_the_profile():
    rec = occ.record()
    assert rec['profile'] == occ.PROFILE == 'zone_pair_own_load_occlusion_v1_v98' and rec['version'] == occ.VERSION
    assert rec['applies_in'].startswith('formal and DEV') and rec['gate_values_changed'] is False
    assert rec['frozen_modules_modified'] is False and rec['max_occluded_duration_s'] is None
    assert set(rec['loaded_phases']) == occ.LOADED_PHASES and set(rec['release_phases']) == occ.RELEASE_PHASES
    bundle = c.bundle('zone_wide_door_geometry_v3', 'p03')
    assert bundle['own_load_occlusion'] == rec
    for path in ('harness/zone_pair_highpose_own_load_occlusion.py', 'harness/zone_pair_highpose_frame_gate.py'):
        assert bundle['source_sha256'][path] == c.base.sha(ROOT/path)
    assert rt.adopt_v98_frame_gate.__code__.co_names.count('record') >= 1
