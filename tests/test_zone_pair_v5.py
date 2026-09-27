"""v5 own-input replay and production scheduling regressions, zero physics/models."""
import base64
import copy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

import pytest

from harness.owncam_pair_beam_v2 import observe_beam
from harness.zone_pair_align import (MAX_TAG_GAP_S, MAX_LOOKS, MAX_LOOK_S, MAX_TOTAL_LOOK_S,
                                     relook_reason, ranked_look_pans)
from harness.zone_pair_beam_track import MAX_AGE_S, RestingBeamTrack
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_pair_status import FIELDS, STATES
from tests.test_zone_pair_grasp import real_pair, fresh
from tests.test_zone_pair_standoff import servo

FIXTURES = Path(__file__).parent / 'fixtures/zone_pair_v5'
RECORD = json.loads((FIXTURES / 'manifest.json').read_text())


def frame(label):
    record = RECORD['frames'][label]
    obs = copy.deepcopy(record['observation'])
    data = (FIXTURES / record['file']).read_bytes()
    assert len(data) == record['bytes'] < 1024 * 1024
    assert hashlib.sha256(data).hexdigest() == obs['sha256']
    obs['image'] = base64.b64encode(data).decode()
    return obs


def report(ep, r):
    return replace(ep.own.last_report, t_est=r['t_est'], initialized=r['initialized'],
                   x_m=r['xyyaw'][0], y_m=r['xyyaw'][1], yaw_rad=r['xyyaw'][2],
                   std_xy_m=r['std_xy_m'], std_yaw_rad=r['std_yaw_rad'], since_tag_s=r['since_tag_s'],
                   last_valid_obs=r['last_valid_obs'], load_state=r['load_state'])


def install(ep, label):
    obs = frame(label)
    ep.own.now = RECORD['frames'][label]['report']['t_est']
    ep.own.last_obs = obs
    ep.own.last_report = report(ep, RECORD['frames'][label]['report'])
    ep.own.servo = servo(obs)
    ep.controller.arm.commanded = dict(ep.own.servo)
    ep.own.pose.loc.last_tag_t = ep.own.now - ep.own.last_report.since_tag_s
    return ep.own.now


def preclose():
    host, _, eps = real_pair()
    ep = eps['r1']
    now = install(ep, 'dev07_standoff')
    ep.controller.state = 'align'
    ep.controller.look(now)
    assert ep.command_guard.beam_track.beam is not None
    for row in RECORD['dev07_commands']:
        ep.own.on_command(row)
    assert ep.own.servo == servo(frame('dev07_open_grasp'))
    now = install(ep, 'dev07_open_grasp')
    ctl = ep.controller
    ctl.state, ctl.state_t = 'wait_close', now
    ctl.pregrasp_done, ctl.pregrasp_started_at = True, 190.4
    ctl.grasp_pose = dict(ep.own.servo)
    for endpoint in eps.values():
        endpoint.own.job.deadline = now + 60
        endpoint.status.tick('aligning', now)
    return host, eps, ep, now


def test_dev07_actual_end_clipped_progresses_to_ready_without_refilling_anchor():
    _, _, ep, now = preclose()
    obs, track = ep.own.last_obs, ep.command_guard.beam_track
    assert observe_beam(obs['image'], ep.own.servo)['reason'] == 'END_CLIPPED'  # v4 rejected here
    before = copy.deepcopy(track.beam)
    estimate = track.estimate(now, obs, ep.own.servo, 0)
    assert estimate['partial_reason'] == 'END_CLIPPED'
    assert estimate['partial_support_fraction'] == 1.
    for key in ('grip_base_m', 'axis_heading_rad', 'anchor_time_s', 'anchor_frame_id', 'anchor_sha256'):
        assert estimate[key] == before[key]
    assert estimate['std_xy_m'] >= before['std_xy_m']
    assert estimate['std_yaw_rad'] >= before['std_yaw_rad']
    assert estimate['std_xy_m'] == pytest.approx(.018945, abs=1e-7)
    ep.controller._wait_close(now, True)
    assert ep.controller.failure is None
    assert ep.status.state == 'close_ready_0'
    assert not ep.controller.arm.events  # one-sided readiness never closes
    assert ep.command_guard.check(now, [{'kind': 'arm', 'servo_id': 1, 'pulse': 1986}]) == [
        {'kind': 'arm', 'servo_id': 1, 'pulse': 1986}]


@pytest.mark.parametrize('fault', ['doorpost', 'missing', 'expired', 'segment', 'xy', 'yaw',
                                  'shifted', 'camera', 'stale', 'black', 'wrong_hue'])
def test_dev07_partial_counterexamples_still_abort_both_and_clear_queues(fault):
    _, eps, ep, now = preclose()
    track = ep.command_guard.beam_track
    if fault == 'doorpost':
        ep.own.last_report = replace(ep.own.last_report, x_m=1.5, y_m=.4, yaw_rad=0., std_xy_m=.001, std_yaw_rad=.001)
    elif fault == 'missing': track.beam = None
    elif fault == 'expired': track.beam['anchor_time_s'] = now - MAX_AGE_S - .1
    elif fault == 'segment': track.segment = 1
    elif fault == 'xy': track.beam['std_xy_m'] = .05001
    elif fault == 'yaw': track.beam['std_yaw_rad'] = math.radians(3.001)
    elif fault == 'shifted': track.beam['grip_base_m'][1] += .5
    elif fault == 'camera': ep.own.servo[6] += 10
    elif fault == 'stale': ep.own.last_obs['sim_time'] -= 1.
    else:
        # Deliberately negative image fixtures, no modifications to source JPEGs.
        import cv2
        import numpy as np
        rgb = np.zeros((480, 640, 3), dtype=np.uint8)
        if fault == 'wrong_hue': rgb[:, :, 0] = 255
        _, jpg = cv2.imencode('.jpg', rgb)
        data = jpg.tobytes()
        ep.own.last_obs.update(image=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest())
    assert not ep.command_guard.preclose_check(now, ep.own.last_obs)
    for endpoint in eps.values():
        endpoint.controller.arm.events = [(now + .05, 1, 1986)]
    if fault == 'stale':
        assert ep.step(now)['commands'] == [{'kind': 'hold'}]
        assert ep.terminal
    else:
        ep.controller._wait_close(now, True)
        assert ep.controller.failure == 'PREGRASP_NOT_READY'
    for endpoint in eps.values():
        endpoint.check(now)
    assert all(e.terminal and not e.controller.arm.events for e in eps.values())
    assert not any(m['state'] == 'close_ready_0' for m in ep.status.channel.log)


def test_dev07_partial_cannot_initialize_or_renew_life_or_uncertainty():
    obs = frame('dev07_open_grasp')
    empty = RestingBeamTrack()
    assert not empty.observe_standoff(obs, servo(obs), 0)
    assert empty.estimate(obs['sim_time'], obs, servo(obs), 0) is None
    _, _, ep, now = preclose()
    track = ep.command_guard.beam_track
    before = copy.deepcopy(track.beam)
    for t in (now, now + .1, now + 1.):
        assert track.estimate(t, obs, ep.own.servo, 0) is not None
    assert track.beam['anchor_time_s'] == before['anchor_time_s']
    assert track.beam['grip_base_m'] == before['grip_base_m']
    assert track.beam['std_xy_m'] > before['std_xy_m']
    assert track.beam['std_yaw_rad'] > before['std_yaw_rad']


def test_dev08_saved_153_frame_gap_triggers_9_seconds_before_high_in_real_step():
    _, _, eps = real_pair()
    ep = eps['r2']
    reasons = [(row, relook_reason(report(ep, row['report']), row['t'])) for row in RECORD['dev08_reports']]
    row, why = next((row, why) for row, why in reasons if why)
    assert (row['t'], why) == (166.3, 'tag_gap')
    assert row['report']['std_xy_m'] == .05486 < .07
    assert row['report']['since_tag_s'] == MAX_TAG_GAP_S
    assert RECORD['dev08_reports'][-1]['t'] - row['t'] == pytest.approx(9.3)
    assert RECORD['dev08_reports'][-1]['report']['std_xy_m'] > .07
    now = install(ep, 'dev08_trigger')
    ctl = ep.controller
    ctl.state, ctl.state_t = 'align', 152.2
    ctl.look_name = 'p45'
    ctl.arm.events = [(now + .05, 3, 600)]
    ep.command_guard.motion_until = now + .15
    for endpoint in eps.values():
        endpoint.status.tick('aligning', now)
        endpoint.own.job.deadline = now + 60
    result = ep.step(now)
    assert result['commands'] == [{'kind': 'hold'}]
    assert ctl.state == 'align_relook_stop' and not ctl.arm.events
    assert not ep.terminal
    ep.own.on_command({'t': now, 'kind': 'hold'})
    assert ep.command_guard.motion_until == now
    assert ctl.align_look_choices()  # actual static map + own saved estimate, no mock
    for message in ep.status.channel.log:
        assert set(message) == FIELDS and message['state'] in STATES


def begin(ep, now=1.):
    fresh(ep, now)
    ep.controller.set('align', now)
    ep.own.on_command({'t': now, 'kind': 'hold'})
    return ep.controller


def test_align_entry_chooses_safe_map_view_and_requires_new_shared_pose_before_resume():
    _, _, eps = real_pair()
    ep = eps['r1']
    ctl = begin(ep)
    old_loc = ep.own.pose.loc
    assert ctl.state == 'align_relook_stop'
    choices = ctl.align_look_choices()
    assert choices and all(c['score_px2'] > 0 and c['predicted_tag_ids'] for c in choices)
    assert choices == sorted(choices, key=lambda c: (-c['score_px2'], abs(c['pan'] - ep.own.servo[6]), c['pan']))
    ctl._align_relook_stop(1.1, True)
    assert ctl.state == 'align_relook' and ctl.driver.loc is ep.own.pose.loc
    assert ep.own.pose.loc is not old_loc
    assert ctl.arm.commanded[6] == choices[0]['pan']
    ctl.arm.events.clear(); ctl.arm.until = 2.5
    fresh(ep, 2.5)
    ep.own.pose.loc.last_tag_t = 1.  # old low-sigma evidence / VO cannot resume
    ctl.vo_pose = [0., 0., 0.]
    assert not ctl._align_fix_ready(2.5)
    ep.own.pose.loc.last_tag_t = 2.5
    ctl._align_relook(2.5, True)
    assert ctl.state == 'align_relook_return'
    ctl.arm.events.clear(); ctl.arm.until = 3.4
    fresh(ep, 3.4)
    ctl._align_relook_return(3.4, True)
    assert ctl.state == 'align' and ctl.state_t == 1.
    assert ctl.aligned_streak == 0
    assert ctl.align_look_total_s == pytest.approx(2.4)


@pytest.mark.parametrize('fault', ['count', 'time', 'total', 'no_fix', 'closed', 'peer_holding', 'no_view'])
def test_align_relook_bounds_and_unsafe_states_abort_both(fault, monkeypatch):
    _, _, eps = real_pair()
    ep = eps['r1'];ctl = ep.controller
    if fault == 'count': ctl.align_look_count = MAX_LOOKS
    if fault == 'closed': ep.own.servo[1] = 1500
    if fault == 'peer_holding': eps['r2'].status.tick('ready', 1.)
    begin(ep)
    if fault in ('time', 'total'):
        if fault == 'total': ctl.align_look_total_s = MAX_TOTAL_LOOK_S - .5
        now = 1. + (MAX_LOOK_S if fault == 'time' else .5)
        assert not ep.command_guard.before_control(now)
    elif fault in ('no_fix', 'no_view'):
        if fault == 'no_view': monkeypatch.setattr(ctl, 'align_look_choices', lambda: [])
        ctl._align_relook_stop(1.1, True)
        if fault == 'no_fix':
            ctl.arm.events.clear(); ctl.arm.until = 2.5; ctl.align_pans.clear()
            fresh(ep, 2.5); ep.own.pose.loc.last_tag_t = None
            ctl._align_relook(2.5, True)
        now = 2.5
    else: now = 1.
    for endpoint in eps.values():
        endpoint.check(now)
    assert all(e.terminal and not e.controller.arm.events and not e.controller.schedule for e in eps.values())
    assert ep.status.state == 'abort'


def test_static_view_failure_does_not_invent_landmarks():
    _, _, eps = real_pair();ep=eps['r1']
    guard = PairSweepGuard(ep.own.guard, ep.plan['beam_geometry'], ep.arguments['role'])
    assert ranked_look_pans({'landmarks': {'tags': []}}, ep.own.last_report, ep.own.servo, guard) == []


def test_real_host_arm_dispatch_stops_relooks_and_returns_before_align_motion():
    host, _, eps = real_pair()
    ep = eps['r1']; ctl = ep.controller
    ctl.state = 'align_start'
    states = []
    for i in range(20, 100):
        now = round(i * .05, 8)
        # Explicit fake observation delivery. This tests scheduling, not tag accuracy.
        fresh(ep, now)
        fresh(eps['r2'], now)
        eps['r2'].status.tick('aligning', now)
        host._decide('r1', now)
        host._pair_arm_tick(now)
        assert not ep.terminal, ctl.failure
        states.append(ctl.state)
        if ctl.state == 'align':
            break
    assert all(s in states for s in ('align_relook_stop', 'align_relook', 'align_relook_return', 'align'))
    commands = [c for c in host.robots['r1'].commands if c['t'] >= 1.]
    assert commands[0]['kind'] == 'hold'
    assert any(c['kind'] in ('arm', 'look') for c in commands)
    assert all(c['kind'] in ('hold', 'arm', 'look') for c in commands)
    assert all(c.get('servo_id') != 1 or c['pulse'] == 2000 for c in commands)
    assert ctl.align_look_count == 1
    assert ctl.state_t == 1.


@pytest.mark.parametrize('kind', ['mecanum', 'drive'])
def test_new_align_states_reject_base_motion_even_with_low_sigma(kind):
    _, _, eps = real_pair();ep=eps['r1']
    begin(ep)
    assert ep.command_guard.check(1., [{'kind': kind, 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .1}]) == [{'kind': 'hold'}]
    assert ep.terminal


@pytest.mark.parametrize('sigma,yaw', [(.055, .01), (.01, math.radians(2.5))])
def test_sigma_reserve_can_trigger_before_time_budget(sigma, yaw):
    _, _, eps = real_pair();ep=eps['r1']
    r=replace(ep.own.last_report, t_est=1., since_tag_s=.1, std_xy_m=sigma, std_yaw_rad=yaw)
    assert relook_reason(r, 1.) == 'sigma_reserve'


@pytest.mark.parametrize('run', ['dev09', 'dev10'])
@pytest.mark.parametrize('current_source_fixture', [False, True])
def test_v5_prepare_copies_frozen_registration_without_physics_or_models(tmp_path, run, current_source_fixture):
    import subprocess
    import sys
    from scripts import run_zone_pair_dev as dev
    code = '''
import sys, importlib.abc
class Forbidden(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco','torch','tensorflow','openai','anthropic'}:
            raise AssertionError('forbidden physics/model import: ' + fullname)
sys.meta_path.insert(0, Forbidden())
from scripts.run_zone_pair_dev import main
raise SystemExit(main(sys.argv[1:]))
'''
    out = tmp_path / run
    registration = dev.PREREG_V5
    if current_source_fixture:
        # Synthetic prepare-only receipt tests the success branch on this
        # tree. The historical v5 file and physical authorization stay intact.
        from scripts.zone_pair_grasp_contract import grasp_contract
        p = json.loads(dev.PREREG_V5.read_text())
        p.update(scene_contract=dev.scene_contract(), grasp_contract=grasp_contract())
        registration = tmp_path / 'synthetic-current-prereg.json'
        registration.write_text(json.dumps(p))
    result = subprocess.run([sys.executable, '-c', code, '--prereg', str(registration),
                             '--run-id', run, '--output', str(out)], cwd=dev.ROOT, capture_output=True, text=True)
    from tests.test_zone_start_dock import registered_tree
    if not current_source_fixture and not registered_tree(dev.PREREG_V5):
        assert result.returncode != 0 and 'scene contract/hash mismatch' in result.stderr, result.stderr
        assert not out.exists()
        return
    assert result.returncode == 0, result.stderr
    m = json.loads((out / 'manifest.json').read_text())
    assert m['state'] == 'prepared_not_executed' and m['applied'] is None and m['model_calls'] == 0
    assert m['physical_success'] is None
    assert (out / 'prereg.json').read_bytes() == registration.read_bytes()
    assert not (out / 'eval_only/trace.jsonl').exists()
    p = json.loads(dev.PREREG_V5.read_text())
    case = next(r for r in p['runs'] if r['id'] == run)
    from scripts.zone_pair_dev_runtime import make_scene
    scene = make_scene({'map': p['environment']['map'], 'seed': case['seed'], 'goal': {'B': {'cyan': 1}},
                        'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': case['setup_beam_xyyaw']}]})
    dev.validate_scene(p, scene)


@pytest.mark.parametrize('fault', ['criteria', 'seed', 'hash', 'stage_rules', 'old_prereg_hash'])
def test_v5_refuses_modified_registration(tmp_path, fault):
    from scripts import run_zone_pair_dev as dev
    p = json.loads(dev.PREREG_V5.read_text())
    if fault == 'criteria': p['criteria']['lift_bottom_m'] /= 2
    elif fault == 'seed': p['runs'][0]['seed'] = 903
    elif fault == 'hash': p['grasp_contract']['sha256'] = '0' * 64
    elif fault == 'old_prereg_hash': p['supersedes']['sha256'] = '0' * 64
    else: p['stage_rules']['contacts'] = 'allow'
    path = tmp_path / 'invalid.json'; path.write_text(json.dumps(p))
    args = dev.parser().parse_args(['--prereg', str(path), '--run-id', 'dev09', '--output', str(tmp_path / 'out')])
    with pytest.raises(ValueError): dev.load_config(args)
    assert not args.output.exists()
