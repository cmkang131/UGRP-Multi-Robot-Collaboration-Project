"""dev05/06 regressions: fake host, saved own RGB, zero physical steps/models.

Pose/tag updates below are explicit deterministic observation fixtures, not
localization accuracy claims. Pixel fixtures retain their original M2 source.
"""
import base64
import hashlib
import json
import math
from dataclasses import replace

import pytest

from harness.zone_own_guards import OwnPose
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD
from tests.test_zone_pair_executor import ROOT, active, beam_fit, m2_controller, pair_obs, setup, start
from tests.test_zone_own_executor import rgb_of


def real_pair():
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    for ep in active(host).values():
        ep.started = ep.control_started = True
        ep.controller.arm.events.clear()
        ep.controller.arm.until = 0.
        ep.controller.grip_base = [.162, 0.]
        ep.controller.look_name = 'p45'
    return host, exs, active(host)


def fresh(ep, now, *, grip=False):
    own = ep.own
    own.now = now
    own.last_obs = pair_obs(own.robot_id, own.last_obs['frame_id'] + 1, now, own.servo)
    if grip:
        jpeg = (ROOT / 'tests/fixtures/m2_pair_door_v3/grasp_824_r2_00757.jpg').read_bytes()
        own.last_obs.update(image=base64.b64encode(jpeg).decode(), sha256=hashlib.sha256(jpeg).hexdigest())
    own.last_report = replace(own.last_report, t_est=now, since_tag_s=0.)
    own.pose.loc.last_tag_t = now


def ready_to_close(ep, now):
    from harness.visual_arm import solve_grip_ik
    ctl, own = ep.controller, ep.own
    ctl.pregrasp_started_at = now - .1
    ctl.pregrasp_done = True
    ctl.grasp_pose = solve_grip_ik(.162, 0., .024, -90)
    own.servo.update(ctl.grasp_pose)
    own.servo[1] = 2000
    ctl.arm.commanded = dict(own.servo)
    ctl.state, ctl.state_t = 'wait_close', now
    fresh(ep, now, grip=True)


def test_dev05_virtual_attached_beam_false_positive_is_removed_without_changing_margin():
    _, _, eps = real_pair()
    ep, own = eps['r1'], eps['r1'].own
    ctl = ep.controller
    ctl.state = 'grasp'  # even the old phase name must not imply attachment
    own.servo = {1: 2000, 3: 672, 4: 1885, 5: 1999, 6: 1489}
    own.last_report = replace(own.last_report, x_m=1.31836, y_m=.09247, yaw_rad=.067231,
                              std_xy_m=.05985, std_yaw_rad=.02378, since_tag_s=28.2)
    pose = OwnPose.from_report(own.last_report)
    target = {**own.servo, 3: 687}
    guard = PairSweepGuard(own.guard, ep.plan['beam_geometry'], ep.arguments['role'])
    old = guard.plan(own.servo, target, [1489], pose, loaded=True, allow_backoff=False)
    assert old['reason'] == 'no_clear_pan' and not old['transition_clear']
    gap, wall = guard.arm_clearance(target, pose, loaded=True)
    assert wall == 'wall_divider_2' and -.00044 < gap < -.00038
    assert guard.margin(OwnPose(0., 0., 0., 0., 0.), .5) == pytest.approx(.035)
    assert not ep.command_guard.carrying_beam
    cmd = {'kind': 'arm', 'servo_id': 3, 'pulse': 687}
    assert ep.command_guard.check(0., [cmd]) == [cmd]
    assert not ep.terminal
    # Once own evidence confirms attachment the same wall counterexample
    # must still stop motion. This receipt is test data, not evaluator truth.
    ctl.beam_grasp_receipt = {'segment': 0}
    own.servo[1] = 1500
    assert ep.command_guard.carrying_beam
    assert ep.command_guard.check(0., [cmd]) == [{'kind': 'hold'}]
    assert ep.terminal


def test_vo_never_skips_look_and_own_frame_updates_guard_shared_pose(monkeypatch):
    _, _, eps = real_pair()
    ep, own = eps['r1'], eps['r1'].own
    ctl = ep.controller
    ctl.vo_pose = [1.32, .09, .067]
    monkeypatch.setattr(ctl, '_vo_pose', lambda: pytest.fail('VO bypass called'))
    old_loc = own.pose.loc
    ctl._queue_grasp(0.)
    assert ctl.state == 'pregrasp_look' and not ctl.pregrasp_done
    assert ctl.driver.loc is own.pose.loc and own.pose.loc is not old_loc
    assert ctl.vo_pose is None and not any(s == 1 and p < 2000 for _, s, p in ctl.arm.events)
    seen = []
    def update(t, detections, servo):
        seen.append((t, detections, servo))
        loc = own.pose.loc
        loc.initialized = True
        loc.px[:] = [.56, .045, .01]
        loc.t = loc.last_tag_t = t
    monkeypatch.setattr(own.pose.loc, 'update', update)
    monkeypatch.setattr(own.pose.detector, 'detect', lambda rgb: [{'id': 1}])
    frame = pair_obs('r1', 2, 1., own.servo)
    own.on_frame(1., frame, rgb_of(frame))
    assert seen and seen[0][0] == 1.
    assert own.last_report.x_m == pytest.approx(.56)
    assert ep.command_guard._pose(1.).x == pytest.approx(.56)
    ctl.pg_pans.clear()
    ctl.arm.events.clear()
    ctl.arm.until = 1.
    ctl._pregrasp_look(1., True)
    assert ctl.state == 'pregrasp_standoff' and ctl.pregrasp_done
    assert ctl.grasp_estimate == pytest.approx([.56, .045, .01])
    assert not any(s == 1 and p < 2000 for _, s, p in ctl.arm.events)


@pytest.mark.parametrize('after_yaw,tag', [(math.radians(2.), True), (.05238, True), (.01, False)])
def test_dev06_yaw_relook_then_progress_or_safe_abort(after_yaw, tag):
    _, _, eps = real_pair()
    ep, ctl, own = eps['r1'], eps['r1'].controller, eps['r1'].own
    own.last_report = replace(own.last_report, std_yaw_rad=.05238, std_xy_m=.05753)
    ctl._queue_grasp(0.)
    assert not ctl.pregrasp_done
    ctl.pregrasp_sweeps = 2
    ctl.pg_pans.clear()
    ctl.arm.events.clear()
    ctl.arm.until = 1.
    fresh(ep, 1.)
    own.last_report = replace(own.last_report, std_xy_m=.04, std_yaw_rad=after_yaw,
                              since_tag_s=0. if tag else None)
    own.pose.loc.last_tag_t = 1. if tag else None
    ctl._pregrasp_look(1., True)
    if tag and after_yaw <= FIX_STD_YAW_RAD:
        assert ctl.state == 'pregrasp_standoff'
    else:
        assert ctl.state == 'failed' and ctl.failure == 'DOOR_POSE_NOT_LOCALIZED'
    assert not any(s == 1 and p < 2000 for _, s, p in ctl.arm.events)
    assert FIX_STD_XY_M == .05 and FIX_STD_YAW_RAD == math.radians(3.)


@pytest.mark.parametrize('fault', ['xy', 'yaw', 'old_tag', 'different_loc', 'stale_pose', 'closed', 'invalid_image'])
def test_close_requires_current_own_readiness(fault):
    _, _, eps = real_pair()
    ep, own = eps['r1'], eps['r1'].own
    ready_to_close(ep, 1.)
    if fault == 'xy': own.last_report = replace(own.last_report, std_xy_m=.05001)
    elif fault == 'yaw': own.last_report = replace(own.last_report, std_yaw_rad=math.radians(3.001))
    elif fault == 'old_tag': own.pose.loc.last_tag_t = 0.
    elif fault == 'different_loc': ep.controller.driver._shared_pose = type('Pose', (), {'loc': object()})()
    elif fault == 'stale_pose': own.last_report = replace(own.last_report, t_est=0.)
    elif fault == 'closed': own.servo[1] = 1500
    else: own.last_obs['image'] = ''
    if fault == 'invalid_image':
        # Use the production outer frame interlock: controller capture also
        # validates image integrity and must never be reached for this frame.
        assert ep.step(1.)['commands'] == [{'kind': 'hold'}]
    else:
        ep.controller._wait_close(1., True)
        assert ep.controller.failure == 'PREGRASP_NOT_READY'
    assert not any(s == 1 and p < 2000 for _, s, p in ep.controller.arm.events)


def test_two_robots_close_on_same_go_only_after_both_announce_ready(beam_fit):
    _, _, eps = real_pair()
    a, b = eps.values()
    for ep in eps.values():
        ready_to_close(ep, 1.)
        ep.status.tick('aligning', 1.)
    a.controller._wait_close(1., True)
    assert not a.controller.arm.events and not b.controller.arm.events
    b.controller._wait_close(1., True)
    for now in (1.1, 1.2):
        for ep in eps.values():
            fresh(ep, now, grip=True)
            ep.controller._wait_close(now, True)
    assert a.controller.state == b.controller.state == 'grasp'
    assert a.controller.arm.events == b.controller.arm.events
    assert min(t for t, _, _ in a.controller.arm.events) == pytest.approx(1.25)
    assert a.controller.close_started_at == b.controller.close_started_at == 1.2
    assert all(not ep.command_guard.carrying_beam for ep in eps.values())
    assert {r['robot_id'] for r in a.status.channel.log if r['state'] == 'close_go_0'} == {'r1', 'r2'}


@pytest.mark.parametrize('closed,fresh_frame,seen', [(False, True, True), (True, False, True), (True, True, False), (True, True, True)])
def test_attachment_requires_issued_close_and_later_own_grip_view(closed, fresh_frame, seen):
    _, _, eps = real_pair()
    ep, ctl, own = eps['r1'], eps['r1'].controller, eps['r1'].own
    ctl.state = 'grasp'
    ctl.close_started_at = 0.
    if closed:
        own.on_command({'t': .5, 'kind': 'arm', 'servo_id': 1, 'pulse': 1500})
    fresh(ep, 1. if fresh_frame else .5, grip=seen)
    if not seen:
        jpeg = (ROOT / 'tests/fixtures/m2_pair_door_v3/approach_824_r2_00010.jpg').read_bytes()
        own.last_obs.update(image=base64.b64encode(jpeg).decode(), sha256=hashlib.sha256(jpeg).hexdigest())
    ctl._grasp(own.now, True)
    assert ep.command_guard.carrying_beam == (closed and fresh_frame and seen)
    if ep.command_guard.carrying_beam:
        assert ctl.beam_grasp_receipt['sha256'] == own.last_obs['sha256']
        ctl._queue_grasp(own.now)
        assert ctl.failure == 'PREGRASP_RELOOK_WHILE_CLOSED'
        own.on_command({'t': own.now, 'kind': 'arm', 'servo_id': 1, 'pulse': 2000})
        assert not ep.command_guard.carrying_beam


def test_new_prereg_preserves_all_v3_judgement_and_uses_fresh_cohort(tmp_path):
    from scripts import run_zone_pair_dev as dev
    from scripts.zone_pair_grasp_contract import grasp_contract
    old = json.loads(dev.PREREG_V3.read_text())
    p = json.loads(dev.PREREG_V5.read_text())
    for key in ('criteria', 'stage_rules', 'planned_setdown', 'limits', 'timing', 'safety_coverage', 'environment', 'inputs'):
        assert p[key] == old[key], key
    current_grasp = grasp_contract()
    # The merged workflow catalogue (including integration v65) changes its
    # file receipt. Preserve the historical registration and every behavior.
    strip = lambda c: {k: v for k, v in c.items() if k not in ('source_sha256', 'sha256')}
    assert strip(p['grasp_contract']) == strip(current_grasp)
    expected_sources = p['grasp_contract']['source_sha256']
    assert set(expected_sources) == set(current_grasp['source_sha256'])
    assert {k for k, v in expected_sources.items() if v != current_grasp['source_sha256'][k]} <= {
        'configs/simulation_workflows.json'}
    workflow = next(w for w in json.loads((dev.ROOT / 'configs/simulation_workflows.json').read_text())['workflows']
                    if w['id'] == 'zone-pair-dev')
    assert workflow['version'] == p['grasp_contract']['workflow']['version']
    assert p['commands']['owner'] == 'claude'
    for rid, seed in [('dev09', 905), ('dev10', 906)]:
        args = dev.parser().parse_args(['--prereg', str(dev.PREREG_V5), '--run-id', rid, '--output', str(tmp_path / rid)])
        from tests.test_zone_start_dock import registered_tree
        if registered_tree(dev.PREREG_V5) and p['grasp_contract'] == current_grasp:
            assert dev.load_config(args)[1]['seed'] == seed
        else:
            with pytest.raises(ValueError, match='scene contract/hash mismatch|grasp contract/hash mismatch'):
                dev.load_config(args)
    # Historical v3 bytes remain bound to their old source, never silently
    # accepted with a changed controller under the old registration.
    args.prereg, args.run_id = dev.PREREG_V3, 'dev05'
    with pytest.raises(ValueError, match='scene contract'):
        dev.load_config(args)
    args.prereg, args.run_id = dev.PREREG_V4, 'dev07'
    with pytest.raises(ValueError, match='scene contract'):
        dev.load_config(args)


def test_peer_grip_status_forbids_unilateral_relook():
    _, _, eps = real_pair()
    eps['r2'].status.tick('ready', 0.)
    eps['r1'].controller._queue_grasp(0.)
    assert eps['r1'].controller.failure == 'PREGRASP_RELOOK_WHILE_CLOSED'
    assert not eps['r1'].controller.arm.events


def test_confirmed_beam_cannot_sweep_and_old_segment_receipt_is_not_reused():
    _, _, eps = real_pair()
    ep = eps['r1']
    ep.controller.beam_grasp_receipt = {'segment': 0}
    ep.own.servo[1] = 1500
    ep.controller.state = 'pregrasp_look'
    assert not ep.command_guard.before_control(0.)
    assert ep.terminal
    ep.controller.seg = 1
    assert not ep.command_guard.carrying_beam


@pytest.mark.parametrize('phase', ['pregrasp_standoff', 'pregrasp_descend', 'wait_close'])
@pytest.mark.parametrize('fault', [None, 'drop', 'wrong_segment', 'off_target', 'no_go'])
@pytest.mark.parametrize('version', [4, 5])
def test_v4_checkpoint_subphases_keep_v3_physical_criteria(phase, fault, version):
    from tests.test_zone_pair_dev import checkpoint_evidence
    from scripts import evaluate_zone_pair_dev as ev
    m, p, rows, contacts, protocol = checkpoint_evidence()
    p['registration_version'] = version
    target = next(r for r in rows if r['states']['r1'] == 'grasp' and r['segments']['r1'] == 2)
    for r in rows:
        if r['states']['r1'] == 'grasp':
            r['states'] = dict.fromkeys(('r1', 'r2'), phase)
    assert ev.planned_setdown(target, p, protocol) is not None
    if fault == 'drop':
        # Unsupported, ungripped elevated cargo is still an unplanned drop.
        target['beam_corners'] = [[x, y, z + .03] for x, y, z in target['beam_corners']]
    elif fault == 'wrong_segment': target['segments']['r1'] += 1
    elif fault == 'off_target': target['beam_xyz'][0] += .2
    elif fault == 'no_go': protocol['go_times'].pop('lower_go_1')
    result = ev.score(m, p, rows, contacts, protocol, video_review={'verified': True})
    assert result['physical_success'] == (fault is None)


@pytest.mark.parametrize('fault', ['criteria', 'seed', 'grasp_hash', 'stage_rules'])
def test_v4_prepare_rejects_changed_contract(tmp_path, fault):
    from scripts import run_zone_pair_dev as dev
    p = json.loads(dev.PREREG_V4.read_text())
    if fault == 'criteria': p['criteria']['lift_bottom_m'] /= 2
    elif fault == 'seed': p['runs'][0]['seed'] = 901
    elif fault == 'grasp_hash': p['grasp_contract']['sha256'] = '0' * 64
    else: p['stage_rules']['contacts'] = 'allow'
    path = tmp_path / 'invalid.json'
    path.write_text(json.dumps(p))
    args = dev.parser().parse_args(['--prereg', str(path), '--run-id', 'dev07', '--output', str(tmp_path / 'out')])
    with pytest.raises(ValueError): dev.load_config(args)
    assert not args.output.exists()


def test_host_issues_synchronized_close_then_confirms_only_from_later_rgb(beam_fit):
    host, _, eps = real_pair()
    for ep in eps.values():
        ready_to_close(ep, 1.)
        ep.status.tick('aligning', 1.)
    for now in (1., 1.1, 1.2):
        for ep in eps.values():
            fresh(ep, now, grip=True)
            ep.controller._wait_close(now, True)
            ep.next_control = 1.3
    for i in range(25, 43):
        now = round(i * .05, 4)
        for ep in eps.values():
            fresh(ep, now, grip=True)
            ep.step(now)
        host._pair_arm_tick(now)  # fake ports; production host dispatch/command receipts
        if now < 2.1:
            assert all(not ep.command_guard.carrying_beam for ep in eps.values())
    assert all(ep.controller.state == 'wait_lift' for ep in eps.values())
    assert all(ep.command_guard.carrying_beam for ep in eps.values())
    closing = {r: [(c['t'], c['pulse']) for c in host.robots[r].commands
                   if c['kind'] == 'arm' and c['servo_id'] == 1] for r in eps}
    assert closing['r1'] == closing['r2']
    assert closing['r1'][-1] == (1.7, 1500)


def test_one_ready_robot_waits_open_and_stops_at_close_timeout(beam_fit):
    _, _, eps = real_pair()
    a, b = eps.values()
    ready_to_close(a, 1.)
    for now in (1., 1.1, 1.2, 21.1):
        fresh(a, now, grip=True)
        b.status.tick('aligning', now)
        a.controller._wait_close(now, True)
        assert not a.controller.arm.events
    assert a.controller.failure == 'BARRIER_CLOSE_TIMEOUT'
