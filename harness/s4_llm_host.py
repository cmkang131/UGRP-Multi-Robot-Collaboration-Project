"""S4 orchestration over injected S3 RobotLinks. No simulator or live launcher.

One three-robot scheduler/channel/ledger handles claims and pair stop choices.
S3 must disable its automatic claims before handing links to this host. S4
owns only decisions: S3 still owns time, observations, jobs and all motion.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from harness import pair_llm_dispatch as pair
from harness import pair_llm_clock as clock
from harness import pair_llm_live as live
from harness import pair_llm_prompts_ko as pp
from harness import s4_llm_inputs as inputs
from harness import s4_llm_routing as routing
from harness import zone_study_integration as zi
from harness import zone_study_llm_driver as llm
from harness import zone_study_offline as zo
from harness import zone_study_prompts_ko as pk
from harness.pair_llm_stop_adapter import StopAdapter
from harness.zone_event_scheduler import CallPolicy
from harness.zone_study_contract import ContractViolation, digest
from harness.zone_study_decisions import DecisionLimits
from harness.zone_study_inputs import OrderSheetSource, belief_skeleton, provenance

VERSION = 'ugrp.s4_llm_host.v1'
CONDITIONS = ('rule', 'no_comm', 'peer_nl')
POLICY = CallPolicy(max_calls_per_actor=30, max_http_attempts_per_actor=30,
                    max_attempts_total=90, max_retries=0)
LIMITS = DecisionLimits(max_calls_total=90, max_utterances_per_actor=6, max_utterances_total=12)


class Link:
    """Own S3 RobotLink plus #371's own-executor stop adapter for r1/r2 only.

    ``executor`` is the caller's executor, never the runtime/team/evaluator.
    The inner link implements deliver/pair_carry/abort/hold/look_around.
    """

    def __init__(self, inner, *, condition, executor=None, origin_s=0.):
        if condition not in CONDITIONS or inner.robot_id not in routing.ROBOTS:
            raise ContractViolation('unknown S4 condition or robot')
        self.inner, self.robot_id = inner, inner.robot_id
        self.origin_s = float(origin_s)
        self.stop_adapter = None
        if self.robot_id in inputs.PAIR:
            if executor is None or executor.robot_id != self.robot_id:
                raise ContractViolation('a pair link needs exactly its own executor')
            self.stop_adapter = StopAdapter(executor, condition=condition, origin_s=origin_s)
        elif executor is not None:
            raise ContractViolation('r3 must not receive a pair executor')
        self._counter, self._call_ref = 0, None

    @property
    def call_ref(self):
        return self._call_ref

    @call_ref.setter
    def call_ref(self, value):
        self._call_ref = value
        self.inner.call_ref = value

    def frame_at(self, t):
        return self.inner.frame_at(t)

    def belief(self):
        return self.inner.belief()

    def job(self):
        return self.inner.job()

    def clock(self):
        return self.inner.clock()

    def call(self, api, *args, window_ref=None):
        if api not in pair.decisions.HOOK_ACTIONS:
            return self.inner.call(api, *args)
        if self.stop_adapter is None:
            raise ContractViolation('a solo executor has no pair decision API')
        self._counter += 1
        at = self.clock() + self.origin_s
        verdict = self.stop_adapter.command(api, args[0], absolute_now=at, window_ref=window_ref)
        accepted = verdict['accepted']
        return {'robot_id': self.robot_id, 'api': api, 'sim_s': at,
                'action_id': f'{self.robot_id}-s4-stop-{self._counter}', 'arguments': {'choice': args[0]},
                'accepted': accepted, 'rejected_reason': None if accepted else verdict['own_status'],
                'job_id': None, 'local_state': 'command_issued' if accepted else 'command_rejected'}


class S3Link(Link):
    """Adapt #394 OwnLink (e4b72aaf): explicit pair role, absolute clock, sparse ACK.

    This does not take over S3 Runtime's scripted claims. The embedding caller
    must disable them before starting Host; #394 has no takeover API yet.
    Solo raw pose estimates are not the study belief schema, so stay unknown.
    APIs not published by S3 are rejected without calling its executor.
    """

    def clock(self):
        return clock.relative(self.inner.clock(), self.origin_s)

    def frame_at(self, t):
        frame = self.inner.frame_at(t + self.origin_s)
        if frame is None:
            return None
        return zi.OwnFrame(frame.index, clock.relative(frame.t, self.origin_s), frame.jpeg, frame.sha256)

    def belief(self):
        return belief_skeleton() if self.robot_id == 'r3' else self.inner.belief()

    def call(self, api, *args, window_ref=None):
        if api in pair.decisions.HOOK_ACTIONS:
            return super().call(api, *args, window_ref=window_ref)
        self._counter += 1
        arguments = {}
        if api == 'pair_carry' and self.robot_id in inputs.PAIR:
            role = pp.PAIR_ROLES[self.robot_id]
            raw = self.inner.call(api, *args, role)
            arguments = {'order_id': args[0], 'target_ref': args[1], 'role': role}
        elif api == 'deliver' and self.robot_id == 'r3':
            raw = self.inner.call(api, *args)
            arguments = {'order_id': args[0], 'target_ref': args[1]}
        else:
            raw = {'accepted': False, 'rejected_reason': 'S3_API_UNAVAILABLE'}
        if raw.get('robot_id', self.robot_id) != self.robot_id:
            raise ContractViolation('S3 acknowledgement belongs to another robot')
        accepted = raw['accepted']
        return {**raw, 'robot_id': self.robot_id, 'api': api,
                'action_id': raw.get('action_id', f'{self.robot_id}-s4-s3-{self._counter}'),
                'sim_s': self.inner.clock(), 'arguments': arguments,
                'job_id': raw.get('job_id'), 'accepted': accepted,
                'rejected_reason': raw.get('rejected_reason'),
                'local_state': raw.get('local_state', 'command_issued' if accepted else 'command_rejected')}


class _Transport(zi._LiveTransport):
    def reply(self, call):
        # A 429 seen for one actor must prevent another actor's POST, even
        # inside the same scheduler tick. Keep the first failure's ledger row.
        hits = live.rate_limited_rows(self.send_ledger)
        if hits:
            raise live.RateLimited(hits)
        return super().reply(call)


class Trial(zi.IntegratedTrial):
    """The general 3-robot trial with #371 reply, billing and action handling."""

    sim_output_tokens = pair.PairTrial.sim_output_tokens
    _archive = pair.PairTrial._archive
    _collect = pair.PairTrial._collect
    cost_summary = pair.PairTrial.cost_summary
    _remember_command = pair.PairTrial._remember_command
    on_claim_result = pair.PairTrial.on_claim_result
    channel_summary = pair.PairTrial.channel_summary

    def __init__(self, scenario, *, arm, links, seed, horizon_s, map_bundle, model_adapter,
                 code_sha='unknown', policy=POLICY, decision_limits=LIMITS):
        if arm not in pp.PAIR_CONDITIONS:
            raise ContractViolation('rule has no model trial')
        if not isinstance(model_adapter.send_ledger, live.PairLiveLedger):
            raise ContractViolation('S4 requires the existing durable PairLiveLedger')
        self.arm = arm
        super().__init__(scenario, condition=pp.study_spec(arm), seed=seed, links=links,
                         horizon_s=horizon_s, map_bundle=map_bundle, model_adapter=model_adapter,
                         actor='gemini_proxy', code_sha=code_sha, policy=policy,
                         decision_limits=decision_limits)
        self.bundle_id = VERSION  # library identity only; no runnable bundle is registered
        self.run_id = f's4-{arm}-{self.scenario_id}-s{seed}'
        self.map_png, self.map_meta = pair.map_figure(self.bundle)
        self._output_token_counts, self._window_refs, self._claim_entries = {}, {}, {}
        self.language_rows, self.claim_results = [], []
        # The scheduler already owns this ledger; change only its transport,
        # retaining that owner and the sealed scheduling/charging algorithm.
        self.transport = _Transport(self, send_ledger=self.send_ledger, client_factory=self.client_factory)
        self.scheduler.transport = self.transport
        self.scheduler.event_available_at = lambda actor, cause: (
            float('inf') if cause and self._message_own_job(actor) is not None else self.scheduler.clock)
        if not self.spec.channel_open:
            self.channel.cap_total = 0
        self.provenance = provenance(source=self.source, code_sha=code_sha, execution_bundle_id=VERSION,
            model=self.client_factory.settings['model'], provider='gemini_subscription_proxy',
            model_settings_sha256=digest(self.client_factory.settings),
            prompt_template_sha256=digest({c: {r: inputs.system_prompt(c, r) for r in routing.ROBOTS}
                                          for c in pp.PAIR_CONDITIONS}), cost_profile_id=self.params.version)

    def _message_own_job(self, actor):
        adapter = self.links[actor].stop_adapter
        if adapter is not None and adapter.window.is_open(self.scheduler.clock):
            return None
        return self.links[actor].job()

    def snapshot(self, call):
        super().snapshot(call)
        adapter = self.links[call.actor].stop_adapter
        if adapter is not None:
            snap = self._snapshots[(call.actor, round(float(call.started_sim_s), 6))]
            snap['own_belief'] = adapter.own_belief(call.started_sim_s + adapter.origin_s)
            snap['decision_window'] = adapter.window.snapshot(call.started_sim_s)
            self._window_refs[call.call_id] = adapter.window.reference(call.started_sim_s)

    def build_inputs(self, actor, *, sim_time_s, request_id):
        snap = self._snapshots[(actor, round(float(sim_time_s), 6))]
        estimate, window = snap.get('own_belief'), snap.get('decision_window')
        base = super().build_inputs(actor, sim_time_s=sim_time_s, request_id=request_id)
        base = pk.StudyInputs(base.payload, wrist_jpeg=base.wrist_jpeg, map_figure_jpeg=self.map_png,
                              seed=self.seed, pinned=self.source.pinned)
        return inputs.Inputs(base, self.arm, estimate, window)

    def prepare_call(self, call):
        request_id = f'req_{call.call_id.replace("-", "_")}'
        bundled = self.build_inputs(call.actor, sim_time_s=call.started_sim_s, request_id=request_id)
        window = self.channel.window_context(call.actor, now_sim_s=call.started_sim_s) if self.spec.channel_open else None
        return zo.PreparedCall(bundled, inputs.build_request(bundled, window=window), request_id)

    def finish_call(self, call, prepared, raw, *, provider_usage=None):
        return pair.PairTrial.finish_call(self, call, prepared, raw, provider_usage=provider_usage,
                                          robots=routing.ROBOTS)

    def _on_action(self, actor, action, sim_s):
        live.check_health(self)
        call_id = self.scheduler.calls[-1].call_id
        self.links[actor].call_ref = call_id
        try:
            pair.PairTrial._release_action(self, actor, action, sim_s, call_id, planner=routing.executor_plan)
        finally:
            self.links[actor].call_ref = None
        row = self.dispatch_log[-1]
        if row['api'] == 'pair_carry' and row['ack'] and row['ack']['accepted']:
            self._claim_entries[call_id] = self._history[actor][-1]

    def on_executor_event(self, event, *, at_s):
        super().on_executor_event(event, at_s=at_s)
        adapter = self.links[event['robot_id']].stop_adapter
        if adapter is not None:
            opened = adapter.window.on_event(event, origin_s=adapter.origin_s)
            if opened and adapter.window.is_open(at_s) and at_s <= self.horizon_s:
                self.scheduler.trigger(event['robot_id'], 'idle', at=at_s)
                if self.spec.channel_open:
                    self.scheduler.available(event['robot_id'], at=at_s)

    def study_config(self):
        row = super().study_config()
        row.update(schema=VERSION, execution_bundle_id=None, condition=self.arm, study_spec=self.condition,
                   prompt_version=inputs.PROMPT_VERSION, fixed_roles={'r1': 'end_neg', 'r2': 'end_pos', 'r3': 'west'},
                   stop_decisions=pair.decisions.record(), input_billing=pair.billing.record(),
                   runnable=False, physical_verified=False)
        return row


class Host:
    """Caller drives time/events. No method steps physics or creates a model adapter.

    On failure, stop calling executors/advancing physics, then save(). Saving
    never drains pending calls; a RATE_LIMIT must not become a retry on close.
    """

    def __init__(self, scenario, *, condition, links, seed, map_bundle, horizon_s=1800.,
                 model_adapter=None, code_sha='unknown', policy=POLICY, decision_limits=LIMITS):
        if condition not in CONDITIONS or set(links) != set(routing.ROBOTS):
            raise ContractViolation('S4 needs one own link for each of r1/r2/r3 and a supported condition')
        if any(not isinstance(link, Link) or link.robot_id != rid for rid, link in links.items()):
            raise ContractViolation('S4 links must be identity-checked Link wrappers')
        if any(link.stop_adapter is not None and link.stop_adapter.condition != condition for link in links.values()):
            raise ContractViolation('stop adapters and host must use the same condition')
        if (condition == 'rule') != (model_adapter is None):
            raise ContractViolation('rule has no model adapter; no_comm/peer_nl require one')
        self.condition, self.links = condition, dict(links)
        self.source = OrderSheetSource(scenario, map_bundle)
        orders = self.source.sheet()['orders']
        if (scenario.get('scenario_id') != 'dev_s1lite' or len(orders) != 2
                or {(o['kind'], o['required_robots'], o['count']) for o in orders}
                != {('cyan', 1, 1), ('long_beam', 2, 1)}):
            raise ContractViolation('S4 currently supports only the dev_s1lite cyan + beam orders')
        self.trial = None if condition == 'rule' else Trial(
            scenario, arm=condition, links=links, seed=seed, horizon_s=horizon_s, map_bundle=map_bundle,
            model_adapter=model_adapter, code_sha=code_sha, policy=policy, decision_limits=decision_limits)
        self.failed, self.started, self.finished = None, False, False
        self.rule_dispatch = []

    def _guard(self):
        if self.failed is not None:
            raise self.failed
        if self.finished:
            raise RuntimeError('S4 host is finished')
        if self.trial is not None:
            live.check_health(self.trial)

    def _run(self, fn):
        try:
            self._guard()
            value = fn()
            self._guard()
            return value
        except Exception as exc:
            self.failed = self.failed or exc
            raise

    def _poll(self):
        for rid, link in self.links.items():
            if link.stop_adapter is not None:
                for event in link.stop_adapter.poll():
                    if self.trial is not None:
                        self.trial.on_executor_event(event, at_s=link.clock())

    def begin(self, at_s=0.):
        if self.started:
            raise RuntimeError('S4 host already started')
        self.started = True
        def start():
            self._poll()
            if self.trial is not None:
                return self.trial.begin(at_s)
            for rid in routing.ROBOTS:
                kind, role = ('cyan', 'west') if rid == 'r3' else ('long_beam', pp.PAIR_ROLES[rid])
                order = next(row for row in self.source.sheet()['orders'] if row['kind'] == kind)
                action = dict(kind='claim', order_id=order['order_id'], role=role,
                              destination_zone=order['destination_zone'])
                plan = routing.executor_plan(action, self.links[rid].job(), actor=rid, orders=self.source.sheet()['orders'])
                ack = self.links[rid].call(plan.api, *plan.args) if plan.api else None
                self.rule_dispatch.append(dict(actor=rid, action=action, api=plan.api, ack=ack,
                                                rejected_reason=plan.rejected_reason))
        return self._run(start)

    def step_to(self, at_s):
        if not self.started:
            raise RuntimeError('begin S4 host first')
        def step():
            self._poll()
            return self.trial.step_to(at_s) if self.trial is not None else None
        return self._run(step)

    def on_executor_event(self, event, *, at_s):
        return self._run(lambda: self.trial.on_executor_event(event, at_s=at_s) if self.trial else None)

    def finish(self, at_s):
        def end():
            if self.trial is not None:
                result = self.trial.finish(at_s)
                live.check_health(self.trial, final=True)
                return result
        result = self._run(end)
        self.finished = True
        return result

    def save(self, output):
        """New directory, texts/images/hashes/accounting even after RATE_LIMIT. No I/O to a model."""
        out = Path(output)
        out.mkdir(parents=True, exist_ok=False)
        trial = self.trial
        def write(name, value):
            (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        records = live.live_records(trial.send_ledger) if trial else None
        label = getattr(self.failed, 'failure_label', None)
        row = {'schema': VERSION, 'condition': self.condition, 'physical_verified': False,
               'status': 'FAILED' if self.failed else 'FINISHED' if self.finished else 'INCOMPLETE',
               'failure_label': label, 'failure_class': llm.classify_exception(self.failed) if self.failed else None,
               'exception_type': type(self.failed).__name__ if self.failed else None,
               'model_usage': records['usage'] if records else {'requests': 0},
               'response_wall_s': live.live_walls(trial) if trial else [],
               'scheduler_settled': self.finished,
               'wire_dir': str(trial.send_ledger.store_dir) if trial else None,
               'live': bool(trial and trial.send_ledger.live)}
        write('result.json', row)
        write('dispatch.json', trial.dispatch_log if trial else self.rule_dispatch)
        if trial:
            write('requests.json', trial.requests)
            write('model_calls.json', records['rows'])
            write('inputs.json', trial.input_log)
            write('channel.json', trial.channel_summary())
            write('scheduler_events.json', trial.scheduler.events)
            write('scheduler_ledger.json', trial.scheduler.ledger)
            write('unsent_calls.json', trial.scheduler.unsent_calls)
            write('transport_errors.json', trial.scheduler.transport_errors)
            write('executor_events.json', trial.executor_events)
            write('claims.json', trial.claim_results)
            write('actions.json', trial.actions)
            write('stop_adapters.json', {rid: {'events': link.stop_adapter.events,
                                               'decisions': link.stop_adapter.decisions}
                                        for rid, link in self.links.items() if link.stop_adapter is not None})
            write('study_config.json', trial.study_config())
            write('send_ledger.json', trial.send_ledger.to_dict())
            # Includes sent-but-failed calls: the durable wire ledger hashes
            # images before POST, independent of whether parsing ever succeeds.
            write('image_sha256.json', [{'call_id': r['call_id'], 'images': r.get('images', [])}
                                        for r in records['rows']])
            image_dir = out / 'request_images'
            image_dir.mkdir()
            for sha, data in trial.request_images.items():
                (image_dir / f'{sha}.jpg').write_bytes(data)
            (out / 'map_figure.png').write_bytes(trial.map_png)
        manifest = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(out.rglob('*')) if p.is_file()}
        write('artifacts.sha256.json', manifest)
        return row
