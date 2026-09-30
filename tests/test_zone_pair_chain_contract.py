"""P04 transition contracts only: synthetic perception/clearance, NO physical success.

Real M2 handlers, ArmSequence, PairExecution, status wire and host cancellation.
The approach driver's observation outcome and geometric/perception certificates
are fixtures. We do not execute a world, detector, PF update or model request.
"""
import base64
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness.owncam_pose_source import PoseReport
from harness.pair_execution_contract import SCHEMA, PairRunTrace, summarize_attempts, verify_trace
from harness.zone_pair_executor import m2_controller
from harness.zone_pair_status import FIELDS
from scripts import run_m2_pair as m2
from tests.test_zone_pair_executor import CALIB, SHEETS, active, pair_obs, robot, start, ends
from tests.test_zone_own_executor import rgb_of
from tests.test_zone_own_executor_host import FakeHost, issued_after


class Forbidden:
    """Clock-only host permits time reads; every privileged field fails fast."""
    def __init__(self, accesses, **allowed):
        self.__dict__.update(allowed)
        self.__dict__['_accesses'] = accesses

    def __setattr__(self, name, value):
        if name != 'time' or name not in self.__dict__:
            self._accesses.append('write:' + name)
            raise AssertionError('privileged world replacement: ' + name)
        self.__dict__[name] = value

    def __getattr__(self, name):
        self._accesses.append(name)
        raise AssertionError('privileged world access: ' + name)


class FakeProvider:
    source = 'owncam_pf_v2:synthetic_contract_only'

    def __init__(self):
        self.commands, self.scans, self.frames = [], [], []
        self.fix, self.now, self.prior_resets = 0., 0., 0
        self.servo = {}
        self._loc = SimpleNamespace(predict_to=self.predict, estimate=self.estimate)
        self.fail = False
        self.unavailable = False

    @property
    def loc(self):
        return self._loc

    @loc.setter
    def loc(self, value):
        raise AssertionError('student PF replacement')

    def init_prior(self, **kwargs):
        self.prior_resets += 1
        raise AssertionError('student GT/prior reset')

    def predict(self, now):
        self.now = now

    def estimate(self):
        return dict(t=self.now, initialized=True, x=0., y=0., yaw=0., std_xy_m=.01,
                    std_yaw_rad=.01, fix_age_s=self.now-self.fix)

    def report(self, now):
        if self.fail:
            raise RuntimeError('own provider failure fixture')
        self.now = now
        if self.unavailable:
            return PoseReport(now, False, source=self.source, observation_quality={'failure': 'worker_failure'})
        return PoseReport(now, True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.01, std_yaw_rad=.01,
                          since_tag_s=now-self.fix, fix_age_s=now-self.fix, last_fix_t=self.fix, source=self.source,
                          observation_quality={'accepted': True, 'informative': True, 'settled': True})

    def on_frame(self, now, rgb):
        self.frames.append(now)
        # Deterministic capture/release delay; prediction time never renews fix.
        released = [t for t in self.frames if t + .16 <= now + 1e-9]
        if released:
            self.fix = released[-1]
        return self.report(now)

    def on_command(self, row):
        self.commands.append(copy.deepcopy(row))

    def begin_relocalization(self, now, servo):
        self.scans.append({'sim_s': now, 'command_count': len(self.commands), 'old_fix': self.fix})

    def set_motion_profile(self, *args):
        pass

    def get_motion_params(self):
        return CALIB['params']['motion']

    def expected_observability(self, *args):
        return 1.


class ContractHost(FakeHost):
    def __init__(self, exs):
        super().__init__(exs, lambda *args: None)
        self.accesses, self.fault = [], None
        # Reuse immutable fixture bytes, while IDs/times/issued PWM stay per frame.
        self.frame_template = pair_obs('r1', 0, 0., {})
        self.rgb = rgb_of(self.frame_template)
        self.world = Forbidden(self.accesses,
                               data=Forbidden(self.accesses, time=0.),
                               model=Forbidden(self.accesses, opt=SimpleNamespace(timestep=.05)))

    def _capture_raw(self, rid, now):
        slot = self.robots[rid]
        slot.port.fid += 1
        frame = {**self.frame_template, 'robot_id': rid, 'frame_id': slot.port.fid, 'sim_time': now,
                 'actuator_state': {'motor_commands': [0.] * 4,
                                    'servo_pulses': {str(k): v for k, v in slot.port.servo.items()}}}
        if rid == 'r1' and self.fault in ('invalid', 'stale', 'black'):
            if self.fault == 'invalid':
                frame['robot_id'] = 'r2'
            elif self.fault == 'stale':
                frame['sim_time'] = now - 3.
            else:
                import cv2
                data = cv2.imencode('.jpg', np.zeros((480, 640, 3), dtype=np.uint8))[1].tobytes()
                frame.update(image=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest())
        slot.executor.on_frame(now, frame, self.rgb if self.fault != 'black' else rgb_of(frame))
        slot.frames.append({k: frame[k] for k in ('robot_id', 'frame_id', 'sim_time', 'sha256')})
        slot.next_frame = now + self.FRAME_S

    def advance(self, now):
        # Production scheduler/guard/arm cancellation on a fake clock, no physics.
        while self.world.data.time < now - 1e-9:
            at = round(self.world.data.time + .05, 6)
            self.world.data.time = at
            self._pair_safety(at)
            for rid in self.robots:
                slot = self.robots[rid]
                if not slot.dead and at + 1e-9 >= slot.next_frame:
                    self._capture(rid, at)
                self._expire(rid, at)
                if slot.timeline and slot.timeline[0][0] <= at + 1e-9:
                    self._run_timeline(rid, at)
                if not slot.dead and not slot.timeline and at + 1e-9 >= slot.next_decide:
                    self._decide(rid, at)
            self._pair_arm_tick(at)
            self._deliver_events(at)


def setup_contract(monkeypatch, *, trace_on=True, scope='transition_contract', limit=720, delayed=False):
    real_import = builtins.__import__
    def contract_import(name, *args, **kwargs):
        if name.split('.')[0] in ('mujoco', 'torch', 'transformers'):
            raise AssertionError('physics/model import forbidden in contract: ' + name)
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', contract_import)
    import socket
    import subprocess
    def forbidden_call(*args, **kwargs):
        raise AssertionError('network/worker call forbidden in contract')
    monkeypatch.setattr(socket.socket, 'connect', forbidden_call)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden_call)
    monkeypatch.setattr(subprocess, 'Popen', forbidden_call)
    trace = PairRunTrace('p04-fixture', scope=scope)
    exs = {rid: robot(rid, limit=limit) for rid in ('r1', 'r2', 'r3')}
    for ex in exs.values():
        ex.pose = FakeProvider()
        if delayed:
            from harness.zone_study_pose_delay import DelayedPoseSource
            ex.pose = DelayedPoseSource(ex.pose)
    host = ContractHost(exs)
    host.contact_record = {'profile': 'cargo_noslip_v1'}
    factory = trace.factory(m2_controller) if trace_on else m2_controller
    host.enable_pair_carry(SHEETS, CALIB['params'], controller_factory=factory)
    assert start(host)['accepted']
    eps = active(host)
    for ep in eps.values():
        ctl = ep.controller
        # Driver observation stand-in: three calls before arrival. M2 _approach
        # must consume own frames/commands and pass its actual approach barrier.
        calls = []
        def tick(now, ctl=ctl, calls=calls):
            calls.append(now)
            if len(calls) >= 3:
                ctl.driver.outcome = 'arrived'
            return [{'kind': 'hold'}]
        monkeypatch.setattr(ctl.driver, 'tick', tick)
        # Synthetic geometry certificates (NOT tested clearance or adoption).
        guard = ep.command_guard
        monkeypatch.setattr(guard, 'before_control', lambda now: True)
        monkeypatch.setattr(guard, 'check', lambda now, commands: commands)
        monkeypatch.setattr(guard, 'align_stop_ready', lambda *args: True)
        monkeypatch.setattr(guard, 'observe_standoff', lambda *args: True)
        monkeypatch.setattr(guard, 'preclose_check', lambda *args: True)
        monkeypatch.setattr(ctl, 'align_look_choices', lambda: [{'pan': 1500, 'observability_score': 1.}])
        # Use the complete static route from make_plan (8 legs), no shortening.
    beam = dict(visible=True, end_visible=True, grip_source='band_centre',
                grip_base_m=[.162, 0.], axis_heading_rad=0., lateral_spread_m=.001, visible_length_m=.5)
    monkeypatch.setattr(m2.ob2, 'observe_beam', lambda *args: dict(beam))
    # Fixture avoids approach-consistency reapproach on this synthetic close view.
    # Supply the first beam observation at the expected prestation distance.
    for ep in eps.values():
        ctl = ep.controller
        original = ctl._on_beam_obs
        def seen(now, detail, ctl=ctl, original=original):
            return original(now, {**detail, 'grip_base_m': [m2.EXPECT_GRIP_X_M, 0.]}
                            if not ctl.vo_obs else detail)
        monkeypatch.setattr(ctl, '_on_beam_obs', seen)
    monkeypatch.setattr(m2, 'grip_view_m2', lambda *args: {'seen': True})
    monkeypatch.setattr(m2.ob, 'signature_iou', lambda *args: 1.)
    monkeypatch.setattr(m2.hv3, 'hold_iou', lambda *args: 1.)
    return host, eps, trace


def run_until(host, predicate, cap=700.):
    while not predicate() and host.world.data.time < cap:
        host.advance(round(host.world.data.time + .1, 6))
    assert predicate(), {rid: (s.executor.job, s.exception) for rid, s in host.robots.items()}


def assert_failed(host, eps, trace):
    run_until(host, lambda: all(ep.terminal for ep in eps.values()))
    at = host.world.data.time
    host.advance(at + .5)
    for rid, ep in eps.items():
        slot = host.robots[rid]
        assert ep.terminal and ep.cleared and not ep.controller.arm.events and not ep.controller.schedule
        assert not slot.timeline and not ep.port.commands
        assert slot.cancellations and any(t <= at and k == 'hold' for t, k, _ in slot.port.log)
        stopped_at = next(r['terminal']['sim_s'] for r in trace.record()['robots'] if r['robot_id'] == rid)
        assert not issued_after(slot.port, stopped_at)
        assert len(ends(ep.own)) == 1 and ends(ep.own)[0]['event'] == 'job_failed'
        assert all(e['robot_id'] == rid for e in ep.own.events)
        assert ep.status.state == 'abort'
    record = trace.record()
    assert verify_trace(record) == {'valid': True, 'errors': []}
    summary = summarize_attempts([{'run_id': trace.run_id, 'trace': record}])
    assert summary['denominator'] == 1 and summary['overall_pass'] == 0
    assert len(summary['attempts'][0]['failure_receipts']) == 2
    assert all(set(m) == FIELDS for m in eps['r1'].status.channel.log)
    assert host.accesses == []
    return summary


@pytest.fixture(scope='module')
def completed_chain():
    with pytest.MonkeyPatch.context() as monkeypatch:
        host, eps, trace = setup_contract(monkeypatch)
        run_until(host, lambda: all(ep.terminal for ep in eps.values()))
    return host, eps, trace


def test_real_handlers_full_route_and_fresh_checkpoint_receipts(completed_chain):
    host, eps, trace = completed_chain
    assert all(ep.controller.state == 'done' for ep in eps.values())
    record = trace.record()
    assert verify_trace(record) == {'valid': True, 'errors': []}
    for rid, ep in eps.items():
        assert len(ends(ep.own)) == 1 and ends(ep.own)[0]['event'] == 'job_done'
        provider = ep.own.pose
        assert provider.prior_resets == 0 and ep.controller.driver.loc is provider.loc
        assert provider.commands == host.robots[rid].commands
        assert len(provider.scans) >= len(ep.controller.segments)
        rob = next(r for r in record['robots'] if r['robot_id'] == rid)
        assert rob['provider_changes'] == rob['pf_changes'] == 0
        for leg in range(len(ep.controller.segments)):
            start_look = next(r for r in rob['receipts'] if r['edge'] == 'start' and
                              r['phase'] == 'pregrasp_look' and r['leg_index'] == leg)
            close = next(r for r in rob['receipts'] if r['edge'] == 'start' and
                         r['phase'] == 'grasp' and r['leg_index'] == leg)
            assert close['last_fix_t'] >= start_look['sim_s']
            assert close['captured_at_s'] >= close['last_fix_t']
            assert close['command_count'] > start_look['command_count']
        assert rob['commands'] and rob['frames']
    assert all(set(m) == FIELDS for m in eps['r1'].status.channel.log)
    assert host.accesses == []
    # Even a forged stage/evaluator PASS cannot promote a synthetic transition.
    for scope in ('transition_contract', 'stage_probe'):
        record['scope'] = scope
        summary = summarize_attempts([{'run_id': trace.run_id, 'trace': record,
                                       'stage_pass': True, 'eval_only': {'verdict': 'PASS'}}])
        assert summary['overall_pass'] == 0 and summary['attempts'][0]['sequence_done']
    if os.environ.get('P04_TRACE_DIR'):
        path = Path(os.environ['P04_TRACE_DIR'])
        path.mkdir(parents=True, exist_ok=True)
        (path / 'full_trace.json').write_text(json.dumps(trace.record(), indent=1) + '\n')


@pytest.mark.parametrize('fault', ['invalid', 'black', 'stale', 'heartbeat', 'partner_abort',
                                 'preclose', 'provider', 'budget'])
def test_failure_cancels_both_and_records_own_terminal(monkeypatch, fault):
    host, eps, trace = setup_contract(monkeypatch)
    def pending():
        for ep in eps.values():
            host.robots[ep.own.robot_id].timeline = [(1000., [{'kind': 'arm', 'servo_id': 1, 'pulse': 1500}])]
            ep.controller.arm.events.append((1000., 1, 1500))
            ep.controller.schedule = [(1000., 1001., {'forward': .1})]

    queued = []
    for ep in eps.values():
        original_abort = ep.abort
        def abort(now, reason, original_abort=original_abort):
            # A pending host macro suppresses control/heartbeats. Inject exactly
            # at the abort boundary so it tests cancellation, not a different
            # PARTNER_SILENT failure before the selected fault is consumed.
            if not queued:
                pending()
                queued.append(now)
            return original_abort(now, reason)
        monkeypatch.setattr(ep, 'abort', abort)

    if fault == 'preclose':
        def refuse(*args):
            return False
        monkeypatch.setattr(eps['r1'].command_guard, 'preclose_check', refuse)
    elif fault == 'budget':
        host.advance(.3)
        host.close_episode('SIM_LIMIT')
    else:
        host.advance(.3)
        if fault in ('invalid', 'black', 'stale'):
            host.fault = fault
        elif fault == 'provider':
            eps['r1'].own.pose.fail = True
        elif fault == 'partner_abort':
            host.call('r1', 'abort', 'fixture')
        elif fault == 'heartbeat':
            # Restore publication for abort so the endpoint records its own stop.
            real_tick = type(eps['r1'].status).tick
            monkeypatch.setattr(eps['r1'].status, 'tick', lambda state, now, **kw:
                                real_tick(eps['r1'].status, state, now, **kw) if state == 'abort' else None)
    summary = assert_failed(host, eps, trace)
    assert len(queued) == 1
    assert all(any(c['dropped_macro_commands'] > 0 for c in host.robots[rid].cancellations)
               for rid in eps)
    expected = {'invalid': 'EXCEPTION:ExecutorContractError', 'black': 'INVALID_OWN_IMAGE',
                'stale': 'EXCEPTION:M1ContractError', 'heartbeat': 'PARTNER_SILENT',
                'partner_abort': 'ABORTED', 'preclose': 'PREGRASP_NOT_READY',
                'provider': 'EXCEPTION:RuntimeError', 'budget': 'EPISODE_END:SIM_LIMIT'}
    assert expected[fault] in [r['terminal']['reason'] for r in trace.record()['robots']]
    assert summary['categories'].get('approach_not_reached', 0) + summary['categories'].get('grasp_not_reached', 0) == 1


def test_summary_keeps_all_starts_and_missing_evidence(monkeypatch):
    host, eps, trace = setup_contract(monkeypatch)
    host.close_episode('SIM_LIMIT')
    record = trace.record()
    summary = summarize_attempts([{'run_id': trace.run_id, 'trace': record},
                                  {'run_id': 'never-admitted', 'stage_pass': True},
                                  {'run_id': 'host-error', 'failure': 'ENOSPC'}])
    assert summary['denominator'] == 3 and summary['overall_pass'] == 0
    assert summary['categories'] == {'approach_not_reached': 1, 'evidence_incomplete': 2}
    assert summary['attempts'][1]['contract']['errors'] == ['TRACE_MISSING']
    with pytest.raises(ValueError, match='duplicate'):
        summarize_attempts([{'run_id': 'same'}, {'run_id': 'same'}])


@pytest.mark.parametrize('scope', [['stage_probe'], {'unexpected': 'PASS'}])
def test_corrupt_scope_is_counted_without_crashing_summary(scope):
    record = {'schema': SCHEMA, 'run_id': 'broken', 'scope': scope, 'robots': []}
    result = summarize_attempts([{'run_id': 'broken', 'trace': record}, {'run_id': 'missing'}])
    assert result['denominator'] == 2 and result['overall_pass'] == 0
    assert result['categories'] == {'evidence_incomplete': 2}
    assert result['scope_counts'] == {'invalid': 1, 'missing': 1}


def test_privileged_world_and_prior_sentinel_is_effective(monkeypatch):
    host, eps, _ = setup_contract(monkeypatch)
    with pytest.raises(AssertionError, match='privileged'):
        host.world.data.qpos
    with pytest.raises(AssertionError, match='privileged'):
        host.world.robot('r1')
    with pytest.raises(AssertionError, match='privileged'):
        host.world.data.qpos = np.zeros(1)
    with pytest.raises(AssertionError, match='privileged'):
        host.world.data = SimpleNamespace()
    with pytest.raises(AssertionError, match='privileged'):
        host.world.model = SimpleNamespace()
    with pytest.raises(AssertionError, match='prior reset'):
        eps['r1'].own.pose.init_prior(x=0.)
    with pytest.raises(AssertionError, match='PF replacement'):
        eps['r1'].own.pose.loc = object()
    from scripts.zone_teacher import ArmSequence
    assert isinstance(eps['r1'].controller.arm, ArmSequence)  # helper import is not GT access
    with pytest.raises(AssertionError, match='model import forbidden'):
        __import__('mujoco')
    with pytest.raises(AssertionError, match='worker call forbidden'):
        __import__('subprocess').Popen(['never-started'])


@pytest.mark.parametrize('mutation,error', [
    ('drop_phase', 'UNCLOSED_PHASE'), ('drop_frame', 'INPUT_HISTORY_MISSING'),
    ('job', 'IDENTITY_MISMATCH'), ('run', 'IDENTITY_MISMATCH'), ('leg', 'LEG_DISCONTINUITY'),
    ('provider', 'CONTINUITY_BROKEN'), ('pf', 'CONTINUITY_BROKEN'),
    ('command', 'COMMAND_GAP'), ('old_fix', 'FRESH_CHECKPOINT_FIX_MISSING'),
    ('clock', 'CLOCK_REGRESSION'), ('terminal', 'TERMINAL_MISSING'),
    ('frame_reuse', 'FRAME_ID_REUSED'), ('history_link', 'HISTORY_LINK_OUT_OF_RANGE'),
    ('unknown_continuity', 'CONTINUITY_BROKEN'), ('command_payload', 'MALFORMED_OR_MISSING_TRACE_FIELDS'),
    ('phase_type', 'INVALID_PHASE'),
    ('malformed', 'MALFORMED_OR_MISSING_TRACE_FIELDS')])
def test_verifier_rejects_missing_or_broken_chain(completed_chain, mutation, error):
    record = completed_chain[2].record()
    rob = record['robots'][0]
    if mutation == 'drop_phase':
        rob['receipts'].pop(3)
    elif mutation == 'drop_frame':
        rob['frames'] = []
    elif mutation in ('job', 'run'):
        rob['receipts'][2][mutation + '_id'] = 'another'
    elif mutation == 'leg':
        rob['receipts'][2]['leg_index'] = 7
    elif mutation in ('provider', 'pf'):
        rob[mutation + '_changes'] = 1
    elif mutation == 'command':
        rob['commands'].pop(0)
    elif mutation == 'old_fix':
        next(r for r in rob['receipts'] if r['edge'] == 'start' and
             r['phase'] == 'grasp' and r['leg_index'] == 1)['last_fix_t'] = 0.
    elif mutation == 'clock':
        rob['receipts'][2]['sim_s'] = -1.
    elif mutation == 'terminal':
        rob['terminal'] = None
    elif mutation == 'unknown_continuity':
        rob['pf_changes'] = None
    elif mutation == 'command_payload':
        rob['commands'][0].pop('issued')
    elif mutation == 'phase_type':
        # A consistent start/end pair previously admitted non-string phases on
        # failed chains, then crashed summary's reached-phase set construction.
        rob['receipts'][2]['phase'] = rob['receipts'][3]['phase'] = {'bad': 'phase'}
        rob['terminal']['outcome'] = 'failed'
    elif mutation == 'history_link':
        rob['receipts'][0]['command_count'] = len(rob['commands']) + 1
    elif mutation == 'frame_reuse':
        rob['frames'][1]['frame_id'] = rob['frames'][0]['frame_id']
        rob['frames'][1]['frame_sha256'] = '0' * 64
    else:
        del rob['receipts']
    result = verify_trace(record)
    assert not result['valid'] and any(error in e for e in result['errors'])
    assert summarize_attempts([{'run_id': record['run_id'], 'trace': record}])['denominator'] == 1


def test_success_requires_separate_complete_boundary_and_destination_evidence(completed_chain):
    record = completed_chain[2].record()
    audit = {'complete': True, 'teacher_state_replacements': 0, 'gt_prior_resets': 0, 'privileged_accesses': 0}
    evaluator = {'run_id': record['run_id'], 'verdict': 'PASS', 'destination_released': True,
                 'job_ids': {r['robot_id']: r['job_id'] for r in record['robots']}}
    attempt = {'run_id': record['run_id'], 'trace': record, 'boundary_audit': audit, 'eval_only': evaluator}
    # Complete-looking evaluator data still cannot turn fake/staged runs into E2E.
    for scope in ('transition_contract', 'stage_probe'):
        record['scope'] = scope
        assert summarize_attempts([attempt])['overall_pass'] == 0
    # Schema positive control ONLY: changing scope here is a deliberate fixture
    # mutation, not a new measured student run or a result eligible for reporting.
    record['scope'] = 'student_run'
    assert summarize_attempts([attempt])['overall_pass'] == 1
    for key in audit:
        bad = copy.deepcopy(attempt)
        bad['boundary_audit'].pop(key)
        assert summarize_attempts([bad])['overall_pass'] == 0
    for key in ('teacher_state_replacements', 'gt_prior_resets', 'privileged_accesses'):
        bad = copy.deepcopy(attempt)
        bad['boundary_audit'][key] = 1
        assert summarize_attempts([bad])['overall_pass'] == 0
    for key, value in (('run_id', 'other'), ('job_ids', {}), ('verdict', 'FAIL'), ('destination_released', False)):
        bad = copy.deepcopy(attempt)
        bad['eval_only'][key] = value
        summary = summarize_attempts([bad])
        assert summary['overall_pass'] == 0 and summary['categories'] == {'destination_failed_or_unverified': 1}


def test_output_observer_does_not_change_commands_transitions_or_status():
    results = []
    for trace_on in (False, True):
        with pytest.MonkeyPatch.context() as patch:
            host, eps, trace = setup_contract(patch, trace_on=trace_on)
            host.advance(5.)
            host.close_episode('SIM_LIMIT')
            results.append({'commands': {r: s.commands for r, s in host.robots.items()},
                            'events': {r: ep.events for r, ep in eps.items()},
                            'status': [{k: v for k, v in row.items() if k != 'task_id'}
                                       for row in eps['r1'].status.channel.log]})
            assert host.accesses == []
    assert results[0] == results[1]


def test_provider_uninitialized_report_stops_loaded_pair_with_production_guard(monkeypatch):
    from harness.zone_pair_guards import PairCommandGuard
    host, eps, trace = setup_contract(monkeypatch)
    run_until(host, lambda: all(ep.controller.state == 'carry' for ep in eps.values()))
    ep = eps['r1']
    # Restore the actual uncertainty gate for a structured (non-raising) worker
    # failure. This is the provider's fail-closed API, not an evaluator verdict.
    monkeypatch.setattr(ep.command_guard, 'before_control',
                        lambda now: PairCommandGuard.before_control(ep.command_guard, now))
    ep.own.pose.unavailable = True
    summary = assert_failed(host, eps, trace)
    assert 'POSE_UNCERTAIN' in [r['terminal']['reason'] for r in trace.record()['robots']]
    assert summary['categories'] == {'destination_failed_or_unverified': 1}


def test_checkpoint_rejects_previous_leg_fix(monkeypatch):
    host, eps, trace = setup_contract(monkeypatch)
    run_until(host, lambda: eps['r1'].controller.seg == 1 and eps['r1'].controller.state == 'pregrasp_look')
    provider = eps['r1'].own.pose
    # p20 sees frames, but receives no accepted fix after the new look began.
    monkeypatch.setattr(provider, 'on_frame', lambda now, rgb: provider.report(now))
    assert_failed(host, eps, trace)
    reasons = [r['terminal']['reason'] for r in trace.record()['robots']]
    assert 'DOOR_POSE_NOT_LOCALIZED' in reasons


def test_eval_failure_receipt_cannot_reenter_control(monkeypatch):
    host, eps, trace = setup_contract(monkeypatch)
    host.advance(3.)
    before = {r: (ep.controller.state, copy.deepcopy(ep.port.commands), ep.status.seq) for r, ep in eps.items()}
    result = summarize_attempts([{'run_id': trace.run_id, 'trace': trace.record(),
                                 'eval_only': {'verdict': 'FAIL', 'reason': 'GT_CONTACT'}}])
    assert result['overall_pass'] == 0
    after = {r: (ep.controller.state, copy.deepcopy(ep.port.commands), ep.status.seq) for r, ep in eps.items()}
    assert before == after
    assert all('GT_CONTACT' not in str(ep.own.events) for ep in eps.values())


@pytest.mark.parametrize('replacement', ['provider', 'pf', 'wrapped_pf'])
def test_identity_check_sees_through_stable_delayed_facade(monkeypatch, replacement):
    from harness.vision_pose_source import FailClosedLoc
    host, eps, trace = setup_contract(monkeypatch, delayed=True)
    ep = eps['r1']
    delayed, facade = ep.own.pose, ep.own.pose.loc
    # Do not execute the fake filters: the observer reads identities only.
    if replacement == 'wrapped_pf':
        wrapped = FailClosedLoc(SimpleNamespace())
        delayed.provider._loc = wrapped
        host.world.data.time = .01
        ep.on_command({'t': .01, 'kind': 'hold'})
        before = trace.record()['robots'][0]['pf_changes']
        wrapped._pf = SimpleNamespace()
    elif replacement == 'provider':
        delayed.provider = FakeProvider()
    else:
        delayed.provider._loc = SimpleNamespace()
    pending_before = list(delayed.pending)
    host.close_episode('SIM_LIMIT')
    assert delayed.loc is facade
    # No queue is drained by the trace; host close may enqueue final holds.
    assert delayed.pending[:len(pending_before)] == pending_before
    row = next(r for r in trace.record()['robots'] if r['robot_id'] == 'r1')
    assert row['pf_changes'] > (before if replacement == 'wrapped_pf' else 0)
    if replacement == 'provider':
        assert row['provider_changes'] == 1
    assert any('CONTINUITY_BROKEN' in e for e in verify_trace(trace.record())['errors'])
