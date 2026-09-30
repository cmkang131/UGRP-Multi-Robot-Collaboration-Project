"""Opt-in, output-only trace of the existing PairExecution (no new controller).

Use ``controller_factory=trace.factory(m2_controller)`` at host construction.
The observer records callbacks/issued commands and returns their original values.
It has no world, evaluator, clock advancement or provider update API. Receipts
mean controller transitions, never physical attainment. Not a registered bundle.
"""
from __future__ import annotations

import copy
import math
import re
from collections import Counter

SCHEMA = 'pair_execution_contract_v1'
SCOPES = ('transition_contract', 'stage_probe', 'student_run')


class PairRunTrace:
    def __init__(self, run_id, *, scope):
        if not isinstance(run_id, str) or not run_id or scope not in SCOPES:
            raise ValueError('run_id and explicit evidence scope required')
        self.run_id, self.scope = run_id, scope
        self.executions = []

    def factory(self, factory):
        def build(ep, plan, params):
            trace = _ExecutionTrace(self.run_id, ep)
            self.executions.append(trace)
            original_log, original_save = ep.log, ep.save

            def log(rid, kind, now, **detail):
                result = original_log(rid, kind, now, **detail)
                trace.event(kind, now, detail)
                return result

            def save(rid, obs, phase):
                result = original_save(rid, obs, phase)
                trace.frame(obs, phase)
                return result

            ep.log, ep.save = log, save
            controller = factory(ep, plan, params)
            trace.controller = controller
            original_step, original_abort, original_command = ep.step, ep.abort, ep.on_command

            def step(now):
                trace.begin(now)
                result = original_step(now)
                if ep.terminal:
                    trace.finish(now)
                return result

            def abort(now, reason):
                trace.begin(now)
                result = original_abort(now, reason)
                trace.finish(now, reason)
                return result

            def command(row):
                trace.begin(row['t'])
                trace.command(row)
                return original_command(row)

            ep.step, ep.abort, ep.on_command = step, abort, command
            return controller
        return build

    def record(self):
        return {'schema': SCHEMA, 'run_id': self.run_id, 'scope': self.scope,
                'robots': [trace.record() for trace in self.executions]}


def _identity_objects(provider):
    """Read identities only, including PFs behind delayed/fail-closed facades.

    Never call report/estimate/update or drain the provider's queue. Use stored
    wrapper links rather than __getattr__, which could proxy a stateful method.
    """
    providers, filters, seen = [], [], set()
    while provider is not None and id(provider) not in seen:
        seen.add(id(provider))
        providers.append(provider)
        loc = provider.loc
        while loc is not None and id(loc) not in seen:
            seen.add(id(loc))
            filters.append(loc)
            try:
                fields = vars(loc)
            except TypeError:  # opaque leaf filters still have an observable identity
                fields = {}
            loc = fields.get('_pf', fields.get('inner'))
        provider = vars(provider).get('provider')
    return tuple(providers), tuple(filters)


def _same_objects(before, after):
    return len(before) == len(after) and all(a is b for a, b in zip(before, after))


class _ExecutionTrace:
    def __init__(self, run_id, ep):
        self.run_id, self.ep = run_id, ep
        self.controller = None
        self.provider, self.pf = _identity_objects(ep.own.pose)
        self.provider_changes = self.pf_changes = 0
        self.receipts, self.frames, self.commands, self.events = [], [], [], []
        self.active = self.terminal = None
        self.job_id = None
        self.identity_errors = []

    def context(self, now):
        ep = self.ep
        if self.job_id is None:
            self.job_id = ep.job_id
        elif self.job_id != ep.job_id:
            self.identity_errors.append('JOB_ID_CHANGED')
        provider, pf = _identity_objects(ep.own.pose)
        if not _same_objects(self.provider, provider):
            self.provider_changes += 1
            self.provider = provider
        if not _same_objects(self.pf, pf):
            self.pf_changes += 1
            self.pf = pf
        obs, report = ep.own.last_obs, ep.own.last_report
        return {'run_id': self.run_id, 'task_id': ep.status.channel.task_id,
                'robot_id': ep.own.robot_id, 'job_id': self.job_id, 'sim_s': float(now),
                'leg_index': self.controller.seg, 'phase': self.controller.state,
                'provider_generation': self.provider_changes, 'pf_generation': self.pf_changes,
                'command_count': len(self.commands), 'consumed_frame_count': len(self.frames),
                'frame_id': obs.get('frame_id') if obs else None,
                'frame_sha256': obs.get('sha256') if obs else None,
                'captured_at_s': obs.get('sim_time') if obs else None,
                'report_t': getattr(report, 't_est', None),
                'last_fix_t': getattr(report, 'last_fix_t', None),
                'status_seq': ep.status.seq}

    def begin(self, now):
        if self.active is None and self.terminal is None:
            self.transition(self.controller.state, now)

    def transition(self, phase, now):
        ctx = {**self.context(now), 'phase': phase}
        if self.active and (self.active['phase'], self.active['leg_index']) == (phase, ctx['leg_index']):
            return
        if self.active:
            self.end(now, 'transition')
        self.active = ctx
        self.receipts.append({**ctx, 'receipt_id': len(self.receipts) + 1, 'edge': 'start'})

    def end(self, now, outcome):
        # End belongs to the phase/leg being left, even when cp_open already
        # incremented controller.seg before logging the next transition.
        ctx = {**self.context(now), 'phase': self.active['phase'], 'leg_index': self.active['leg_index']}
        self.receipts.append({**ctx, 'receipt_id': len(self.receipts) + 1, 'edge': 'end', 'outcome': outcome})
        self.active = None

    def event(self, kind, now, detail):
        self.begin(now)
        self.events.append({**self.context(now), 'event': kind, 'detail': copy.deepcopy(detail)})
        if kind == 'state':
            self.transition(detail['state'], now)

    def frame(self, obs, phase):
        self.begin(self.ep.own.now)
        self.frames.append({**self.context(self.ep.own.now), 'phase': phase,
                            'frame_id': obs['frame_id'], 'frame_sha256': obs['sha256'],
                            'captured_at_s': obs['sim_time']})

    def command(self, row):
        self.commands.append({**self.context(row['t']), 'command_id': len(self.commands) + 1,
                              'issued': copy.deepcopy(row)})

    def finish(self, now, reason=None):
        if self.terminal is not None:
            return
        if not self.ep.terminal:
            return
        if self.active:
            self.end(now, 'failed' if reason else 'sequence_done')
        self.terminal = {**self.context(now), 'outcome': 'failed' if reason else 'unconfirmed',
                         'reason': reason or 'PAIR_SEQUENCE_DONE'}

    def record(self):
        return copy.deepcopy({'robot_id': self.ep.own.robot_id, 'job_id': self.job_id,
                              'n_legs': len(self.ep.plan['route']) - 1,
                              'receipts': self.receipts, 'frames': self.frames, 'commands': self.commands,
                              'events': self.events, 'terminal': self.terminal,
                              'provider_changes': self.provider_changes, 'pf_changes': self.pf_changes,
                              'identity_errors': self.identity_errors})


def _verify_trace(record):
    """Output-only verifier; missing receipts fail closed, including pre-lift runs."""
    errors = []
    if record.get('schema') != SCHEMA or record.get('scope') not in SCOPES or not isinstance(record.get('run_id'), str) or not record['run_id']:
        errors.append('INVALID_ENVELOPE')
    robots = record.get('robots', [])
    if Counter(r.get('robot_id') for r in robots) != Counter(('r1', 'r2')):
        errors.append('PAIR_INCOMPLETE')
    task_ids = set()
    for robot in robots:
        rid = robot['robot_id']
        if not isinstance(robot.get('job_id'), str) or not robot['job_id']:
            errors.append(f'{rid}:JOB_MISSING')
        rows = robot['receipts']
        if not rows or (rows[0]['phase'], rows[0]['leg_index'], rows[0]['edge']) != ('approach', 0, 'start'):
            errors.append(f'{rid}:APPROACH_START_MISSING')
        if len(rows) % 2 or any(a['edge'] != 'start' or b['edge'] != 'end'
                               or (a['phase'], a['leg_index']) != (b['phase'], b['leg_index'])
                               or b['sim_s'] < a['sim_s'] for a, b in zip(rows[::2], rows[1::2])):
            errors.append(f'{rid}:UNCLOSED_PHASE')
        terminal = robot.get('terminal')
        if terminal is None:
            errors.append(f'{rid}:TERMINAL_MISSING')
        for row in rows + robot['frames'] + robot['commands'] + ([terminal] if terminal else []):
            if not isinstance(row['phase'], str) or not row['phase']:
                errors.append(f'{rid}:INVALID_PHASE')
            if (row['run_id'], row['robot_id'], row['job_id']) != (record['run_id'], rid, robot['job_id']):
                errors.append(f'{rid}:IDENTITY_MISMATCH')
            if not isinstance(row['task_id'], str) or not row['task_id']:
                errors.append(f'{rid}:TASK_ID_MISSING')
            task_ids.add(row['task_id'])
        if (any(type(robot[k]) is not int or robot[k] != 0 for k in ('provider_changes', 'pf_changes'))
                or not isinstance(robot['identity_errors'], list) or robot['identity_errors']):
            errors.append(f'{rid}:CONTINUITY_BROKEN')
        if (any(type(c['command_id']) is not int for c in robot['commands'])
                or [c['command_id'] for c in robot['commands']] != list(range(1, len(robot['commands']) + 1))):
            errors.append(f'{rid}:COMMAND_GAP')
        legs = [r['leg_index'] for r in rows[::2]]
        if any(b not in (a, a + 1) for a, b in zip(legs, legs[1:])):
            errors.append(f'{rid}:LEG_DISCONTINUITY')
        if terminal and terminal['outcome'] == 'unconfirmed':
            phases = [(r['leg_index'], r['phase']) for r in rows[::2]]
            required = [(0, 'approach'), (0, 'align')]
            for leg in range(robot['n_legs']):
                required += [(leg, s) for s in ('pregrasp_look', 'pregrasp_standoff', 'pregrasp_descend',
                                                'wait_close', 'grasp', 'lift', 'carry', 'lower')]
                required.append((leg, 'cp_open' if leg < robot['n_legs'] - 1 else 'released'))
            required.append((robot['n_legs'] - 1, 'done'))
            it = iter(phases)
            if not all(any(p == want for p in it) for want in required):
                errors.append(f'{rid}:CHAIN_INCOMPLETE')
    if len(task_ids) != 1:
        errors.append('TASK_ID_MISMATCH')
    return {'valid': not errors, 'errors': sorted(set(errors))}


def verify_trace(record):
    """Malformed/missing fields are verification failures, never dropped runs."""
    try:
        result = _verify_trace(record)
        errors = result['errors']
        for robot in record['robots']:
            rid, receipts = robot['robot_id'], robot['receipts']
            if type(robot['n_legs']) is not int or robot['n_legs'] <= 0:
                errors.append(f'{rid}:INVALID_LEG_COUNT')
            if (any(type(r['receipt_id']) is not int for r in receipts)
                    or [r['receipt_id'] for r in receipts] != list(range(1, len(receipts) + 1))):
                errors.append(f'{rid}:RECEIPT_GAP')
            for sequence in (receipts, robot['frames'], robot['commands']):
                if any(type(r['sim_s']) not in (int, float) or not math.isfinite(r['sim_s'])
                       or r['sim_s'] < 0 for r in sequence):
                    errors.append(f'{rid}:INVALID_CLOCK')
                if any(b['sim_s'] < a['sim_s'] for a, b in zip(sequence, sequence[1:])):
                    errors.append(f'{rid}:CLOCK_REGRESSION')
                for row in sequence:
                    if type(row['leg_index']) is not int or not 0 <= row['leg_index'] < robot['n_legs']:
                        errors.append(f'{rid}:INVALID_LEG_INDEX')
            for row in receipts + robot['frames'] + robot['commands']:
                for field, limit in (('command_count', len(robot['commands'])),
                                     ('consumed_frame_count', len(robot['frames']))):
                    if type(row[field]) is not int or not 0 <= row[field] <= limit:
                        errors.append(f'{rid}:HISTORY_LINK_OUT_OF_RANGE')
            for command in robot['commands']:
                issued = command['issued']
                if (not isinstance(issued['kind'], str) or not issued['kind']
                        or issued['t'] != command['sim_s']):
                    errors.append(f'{rid}:INVALID_COMMAND_LINK')
            frame_keys = {}
            for frame in robot['frames']:
                if (type(frame['frame_id']) is not int or frame['frame_id'] < 0
                        or re.fullmatch('[a-f0-9]{64}', frame['frame_sha256']) is None
                        or not 0 <= frame['sim_s'] - frame['captured_at_s'] <= .25):
                    errors.append(f'{rid}:INVALID_FRAME_LINK')
                key = (frame['frame_sha256'], frame['captured_at_s'])
                if frame['frame_id'] in frame_keys and frame_keys[frame['frame_id']] != key:
                    errors.append(f'{rid}:FRAME_ID_REUSED')
                frame_keys[frame['frame_id']] = key
            terminal = robot['terminal']
            if terminal is not None:
                if terminal['outcome'] not in ('failed', 'unconfirmed') or not terminal['reason']:
                    errors.append(f'{rid}:INVALID_TERMINAL')
                if receipts and terminal['sim_s'] < receipts[-1]['sim_s']:
                    errors.append(f'{rid}:TERMINAL_BEFORE_PHASE_END')
                if terminal['outcome'] == 'unconfirmed':
                    for leg in range(robot['n_legs']):
                        looks = [r for r in receipts if r['edge'] == 'start' and
                                 r['phase'] == 'pregrasp_look' and r['leg_index'] == leg]
                        closes = [r for r in receipts if r['edge'] == 'start' and
                                  r['phase'] == 'grasp' and r['leg_index'] == leg]
                        if (not looks or not closes or closes[-1]['last_fix_t'] is None
                                or not looks[-1]['sim_s'] <= closes[-1]['last_fix_t'] <= closes[-1]['sim_s']
                                or closes[-1]['command_count'] <= looks[-1]['command_count']):
                            errors.append(f'{rid}:FRESH_CHECKPOINT_FIX_MISSING')
                    if not robot['frames'] or not robot['commands']:
                        errors.append(f'{rid}:INPUT_HISTORY_MISSING')
        return {'valid': not errors, 'errors': sorted(set(errors))}
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return {'valid': False, 'errors': ['MALFORMED_OR_MISSING_TRACE_FIELDS']}


def summarize_attempts(attempts):
    """Include EVERY declared fresh start; stage/fake PASS never earns delivery.

    Each attempt has run_id, optional trace, and a separate eval_only verdict.
    A verified contract is deliberately insufficient for physical success:
    student_run also requires an explicit complete boundary audit and a matching
    run/job-bound destination verdict. Neither is returned to a controller.
    """
    ids = [a['run_id'] for a in attempts]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate run_id')
    rows = []
    for attempt in attempts:
        raw_trace = attempt.get('trace')
        check = verify_trace(raw_trace) if raw_trace is not None else {'valid': False, 'errors': ['TRACE_MISSING']}
        trace = raw_trace if isinstance(raw_trace, dict) else {}
        if trace and trace.get('run_id') != attempt['run_id']:
            check = {'valid': False, 'errors': [*check['errors'], 'RUN_ID_MISMATCH']}
        robots = trace.get('robots', []) if trace else []
        # Invalid payloads still occupy a denominator slot; do not index them.
        if not check['valid']:
            robots = []
        phases = [{r['phase'] for r in rob['receipts'] if r['edge'] == 'start'} for rob in robots]
        reached = lambda name: len(phases) == 2 and all(name in p for p in phases)
        sequence_done = len(robots) == 2 and all(r['terminal'] and r['terminal']['outcome'] == 'unconfirmed' for r in robots)
        ev, audit = attempt.get('eval_only'), attempt.get('boundary_audit')
        ev = ev if isinstance(ev, dict) else {}
        audit = audit if isinstance(audit, dict) else {}
        boundary_ok = (audit.get('complete') is True and all(type(audit.get(k)) is int and audit[k] == 0 for k in
                       ('teacher_state_replacements', 'gt_prior_resets', 'privileged_accesses')))
        delivered = (check['valid'] and sequence_done and trace['scope'] == 'student_run' and boundary_ok
                     and ev.get('run_id') == attempt['run_id']
                     and ev.get('job_ids') == {r['robot_id']: r['job_id'] for r in robots}
                     and ev.get('destination_released') is True and ev.get('verdict') == 'PASS')
        category = ('evidence_incomplete' if not check['valid'] else
                    'delivered' if delivered else 'approach_not_reached' if not reached('align') else
                    'grasp_not_reached' if not reached('lift') else 'destination_failed_or_unverified')
        scope = trace.get('scope')
        if scope is not None and (not isinstance(scope, str) or scope not in SCOPES):
            scope = 'invalid'  # malformed JSON metadata must still occupy its denominator slot
        rows.append({'run_id': attempt['run_id'], 'scope': scope,
                     'category': category, 'contract': check,
                     'sequence_done': sequence_done, 'overall_pass': bool(delivered),
                     'failure_receipts': [r['terminal'] for r in robots if r['terminal'] and r['terminal']['outcome'] == 'failed']})
    return {'schema': SCHEMA, 'denominator': len(attempts), 'overall_pass': sum(r['overall_pass'] for r in rows),
            'categories': dict(Counter(r['category'] for r in rows)),
            'scope_counts': dict(Counter(r['scope'] or 'missing' for r in rows)), 'attempts': rows}
