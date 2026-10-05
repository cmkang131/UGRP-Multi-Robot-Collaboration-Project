"""Two-robot study layer of the pair LLM test: one trial, one own link per robot.

``harness.zone_study_integration.IntegratedTrial`` is hard-wired to three robots (it refuses any link set
but r1, r2, r3, builds a three-robot channel and calls ``build_call_input`` with the three-robot
contract). ``PairTrial`` is the two-robot version. It reuses the study machinery unchanged
(``OfflineTrial``'s call log, ``DecisionScheduler``, the SIM cost model, ``ModelCallTransport`` and the
send ledger, ``zone_study_protocol`` validators and message transport with ``robots=('r1', 'r2')``) and
borrows the robot-count-free methods of ``IntegratedTrial`` by reference, so the physics clock handling,
own-wake rules and action dispatch are the same code. Only the input builder, the reply check and the
request builder are pair-specific.

Information boundary: a call sees ONLY the robot's own latest ``robot_cam`` frame (one JPEG), the static
map projection and its schematic, the order sheet, the robot's own issued commands with their own command
states, its own belief projection and the messages the condition delivered to it. The fixed-enum pair
status wire between the two controllers is not a model input. Nothing here reads the simulator.
"""
from __future__ import annotations

import base64
import collections
import copy
import hashlib
import json
import types
from collections.abc import Mapping

from harness import pair_llm_billing as billing
from harness import pair_llm_decisions as decisions
from harness import pair_llm_inputs as pi
from harness import pair_llm_status as status
from harness import zone_map_schematic as ms
from harness import zone_study_integration as zi
from harness import zone_study_offline as zo
from harness import zone_study_prompts_ko as pk
from harness import zone_study_protocol as zp
from harness.llm_completion import generated_utterances  # noqa: F401  (re-exported for callers)
from harness.pair_llm_prompts_ko import PAIR_CONDITIONS, PAIR_ROBOTS, PAIR_ROLES, PROMPT_VERSION, study_spec
from harness.zone_event_scheduler import CallPolicy, CallReply, EventScheduler  # noqa: F401
from harness.zone_sim_cost import Attempt, call_cost, delivery_delay_s, params
from harness.zone_study_contract import ContractViolation, digest, validate_log_record
from harness.zone_study_decisions import DECISION_POLICY, DecisionLimits, DecisionScheduler
from harness.zone_study_inputs import (action_log_record, belief_skeleton, command_entry, provenance,
                                       static_map_for_call)

DISPATCH_VERSION = 'ugrp.pair_llm_dispatch.v1'
BUNDLE_ID = 'zone-pair-llm-v100'
TAP_FRAMES = 64
#: LLM-arm call policy of the viability test: the study defaults except the call cap (about 5 busy re-asks
#: in a 900 SIM s case plus stop-window and event wakes) and no post-send retry (the registered live driver
#: refuses scheduler retries).
PAIR_POLICY = CallPolicy(max_calls_per_actor=decisions.CALLS_PER_ACTOR,
                         max_http_attempts_per_actor=decisions.CALLS_PER_ACTOR,
                         max_attempts_total=decisions.CALLS_TOTAL,
                         max_retries=0)


#: The one action kind the pair adds to the sealed study vocabulary (``zp.ROBOT_ACTION_KINDS``): the robot's own
#: executor already exposes ``look_around()`` (a guarded wide own-camera look sweep; whether it recovers the pose is NOT
#: verified, see the experiment README).
LOOK_AROUND = 'look_around'
PAIR_ACTION_KINDS = tuple(k for k in zp.ROBOT_ACTION_KINDS if k != 'wait') + (LOOK_AROUND,)
#: The two SIM clocks of one run's records. The harness (calls, decisions, caps, ``sim_s``) counts SIM seconds
#: since the case reset; the backend and the robot executors count absolute SIM seconds, so the same instant reads
#: ``reset_sim_s`` higher there (1.3 SIM s in the v99 smoke1, ``result.json`` ``reset_sim_s``).
CLOCKS = {
    'sim_s': 'harness clock: SIM seconds since the case reset (alias of sim_s_since_reset in dispatch rows)',
    'sim_s_since_reset': 'harness clock: calls, decisions, scheduler, caps, own_status.since_claim_s',
    'sim_s_absolute': 'backend / executor clock = sim_s_since_reset + reset_sim_s (ack.sim_s, executor event sim_s)',
    'delivered_at_sim_s_since_reset': 'executor events only: harness clock when the harness received the event '
                                      '(one observation tick after the event happened; informational, own_status dates a '
                                      'job end by the event\'s own time minus the reset origin)',
    'claim_gate_log': 'claim_gate.json rows (claim_released / claim_submitted / ...) use sim_s_absolute; '
                      'own_status reads them converted to the harness clock (PairLink.gate_view)',
    'reset_offset_s': 'sim_s_absolute - sim_s_since_reset of one dispatch row (equals result.json reset_sim_s)'}


def validate_reply(raw, **kwargs) -> dict:
    """``zp.validate_reply`` plus ``{"kind": "look_around"}``, without editing the sealed study validator.

    A look_around reply is checked by the sealed validator with a placeholder ``continue`` action (so the id,
    sources, messages and every other rule apply unchanged) and the real action is put back afterwards.
    Anything else goes to the sealed validator exactly as before.
    """
    try:
        value = zp.parse(raw) if isinstance(raw, str) else copy.deepcopy(raw)
    except Exception:                                        # noqa: BLE001 - the sealed validator reports it
        return zp.validate_reply(raw, **kwargs)
    action = value.get('action') if isinstance(value, dict) else None
    if isinstance(action, dict) and action.get('kind') in ('wait', 'give_up'):
        raise zp.ProtocolError('this action is excluded from the first pair cohort')
    if not (isinstance(action, dict) and action.get('kind') == LOOK_AROUND):
        return zp.validate_reply(raw, **kwargs)
    if set(action) != {'kind'}:
        raise zp.ProtocolError(f'{LOOK_AROUND} takes no other field')
    checked = zp.validate_reply({**value, 'action': {'kind': 'continue'}}, **kwargs)
    checked['action'] = {'kind': LOOK_AROUND}
    return checked


def pair_executor_plan(action, job, *, actor, orders) -> zi.Plan:
    """The study's action -> executor-call map, plus ``look_around`` -> the robot's own ``look_around()``."""
    if isinstance(action, Mapping) and action.get('kind') == LOOK_AROUND:
        return zi.Plan(LOOK_AROUND, ())
    return zi.executor_plan(action, job, actor=actor, orders=orders)


def pair_action_row(action):
    """Model action -> (package A action kind, arguments, order_id, role); ``look_around`` is an ``observe``."""
    if action['kind'] == LOOK_AROUND:
        return ('observe', {}, None, None)
    return zo._action_row(action)


def map_figure(bundle) -> tuple[bytes, dict]:
    """The schematic PNG of a map bundle, re-rendered from the map file; it must be the bundle's pinned one."""
    data, _ = ms.load_map(bundle['map_id'])
    png, meta = ms.render_schematic(data, width_px=760, landmark_detail=bundle.get('landmark_detail', 'full'))
    pinned = bundle.get('schematic') or {}
    if pinned.get('png_sha256') != meta['png_sha256']:
        raise ContractViolation('the re-rendered map schematic differs from the bundle schematic')
    return png, meta


class PairLink:
    """``zi.RobotLink`` over ONE robot of a ``GatedRuntime``: own frames, own executor, own job API.

    The runner feeds the robot's own capture through :meth:`observe` (exactly the frame the executor got).
    ``call('pair_carry', ...)`` does not start anything: it releases a permit to the claim gate; the
    scripted ``Runtime.step`` submits it on the robot's next idle tick.
    """

    def __init__(self, runtime, rid, *, origin_s=0.):
        if rid not in PAIR_ROBOTS:
            raise ContractViolation(f'{rid!r} is not a pair robot {PAIR_ROBOTS}')
        self.robot_id, self._rt, self._ex = rid, runtime, runtime.actors[rid]
        self._frames = collections.deque(maxlen=TAP_FRAMES)
        self.origin_s, self._abs_now = float(origin_s), float(origin_s)
        self.call_ref = None
        self.api_calls, self.abort_log = [], []
        self._counter = 0
        self.decision_window = decisions.DecisionWindow()

    # -- time and frames -----------------------------------------------------------------
    def set_origin(self, origin_s) -> None:
        self.origin_s = float(origin_s)

    def tick(self, abs_now) -> None:
        self._abs_now = float(abs_now)

    def clock(self):
        return round(self._abs_now - self.origin_s, 6)

    def observe(self, obs) -> None:
        """Keep the robot's OWN latest ``robot_cam`` JPEG (hash-checked against its observation)."""
        rid = self.robot_id
        if obs.get('robot_id') != rid or obs.get('camera') != 'robot_cam':
            raise ContractViolation(f'{rid}: the study frame tap takes only its own robot_cam frame')
        jpeg = base64.b64decode(obs['image'])
        digest_hex = hashlib.sha256(jpeg).hexdigest()
        if digest_hex != obs['sha256']:
            raise ContractViolation(f'{rid}: frame bytes do not hash to the observation sha256')
        self._frames.append(zi.OwnFrame(int(obs['frame_id']), round(float(obs['sim_time']) - self.origin_s, 4),
                                        jpeg, digest_hex))
        self._abs_now = float(obs['sim_time'])

    def frame_at(self, t):
        return next((f for f in reversed(self._frames) if f.t <= t + 1e-9), None)

    # -- own state -------------------------------------------------------------------------
    def belief(self):
        return self._ex.belief_projection()

    def job(self):
        job = self._ex.job
        return None if job is None else {'kind': job.kind, 'order_id': job.args.get('order_id'),
                                         'job_id': job.job_id}

    def gate_view(self) -> dict:
        """The robot's OWN claim bookkeeping (permit, latest start outcome, refusal total); nothing of the partner.

        The gate records the executor / backend clock (absolute SIM seconds). Every model-facing time is on the
        harness clock (SIM seconds since the case reset: call starts, ``claim_issued_s``, job-end delivery), and
        ``pair_llm_status.build`` compares them with each other, so the gate's times are converted here, once and
        explicitly: ``harness = absolute - origin_s``. (Before this, a permit at relative 10.0 and a job end at
        relative 10.5 compared as 11.3 vs 10.5 at origin 1.3 and picked the older fact.)
        """
        view = self._rt.gate.status_view(self.robot_id)
        origin = self.origin_s
        if view['permit_released_at_sim_s'] is not None:
            view['permit_released_at_sim_s'] = round(view['permit_released_at_sim_s'] - origin, 6)
        if view['last_event'] is not None:
            view['last_event']['sim_s'] = round(view['last_event']['sim_s'] - origin, 6)
        return view

    # -- own job API -----------------------------------------------------------------------
    def _ack(self, api, arguments, accepted, reason=None, job_id=None):
        self._counter += 1
        ack = {'robot_id': self.robot_id, 'api': api, 'action_id': f'{self.robot_id}-llm-act-{self._counter:03d}',
               'sim_s': round(self._abs_now, 3), 'arguments': arguments, 'accepted': bool(accepted),
               'rejected_reason': reason, 'job_id': job_id,
               'local_state': 'command_issued' if accepted else 'command_rejected'}
        self.api_calls.append(copy.deepcopy(ack))
        return ack

    def call(self, api, *args):
        ex = self._ex
        if api == 'pair_carry':
            order_id, zone, partner = args
            arguments = {'order_id': ex._token(order_id), 'target_ref': ex._token(zone),
                         'role': PAIR_ROLES[self.robot_id]}
            if ex.stopped is not None:
                return self._ack(api, arguments, False, 'STOPPED')
            job = ex.job
            if job is not None and job.kind == 'pair_carry':
                return self._ack(api, arguments, False, f'BUSY:{job.kind}:{job.job_id}')
            self._rt.grant(self.robot_id, order_id, zone, partner, now=self._abs_now, call_ref=self.call_ref)
            return self._ack(api, arguments, True)
        if api == LOOK_AROUND:
            ack = ex.look_around()                      # refused (BUSY:...) while any own job runs
            self.api_calls.append(copy.deepcopy(ack))
            return ack
        if api in ('abort', 'hold'):
            job = ex.job
            ack = getattr(ex, api)(*args)
            # A caller-issued stop revokes a claim that has not started yet.
            if ack['accepted']:
                self._rt.gate.revoke(self.robot_id, now=self._abs_now, reason=f'{api}_requested')
            if api == 'abort':
                self.abort_log.append({'sim_s': round(self._abs_now, 3), 'robot_id': self.robot_id,
                                       'job_kind': None if job is None else job.kind,
                                       'accepted': bool(ack['accepted'])})
            self.api_calls.append(copy.deepcopy(ack))
            return ack
        raise ContractViolation(f'{self.robot_id}: the pair layer has no executor call {api!r}')


class PairTrial(zo.OfflineTrial):
    """One condition x scenario x seed trial of the two-robot pair, driven by live links."""

    # Robot-count-free methods of the three-robot trial, shared by reference (same code, same clock rules).
    begin = zi.IntegratedTrial.begin
    step_to = zi.IntegratedTrial.step_to
    decision_budget_spent = zi.IntegratedTrial.decision_budget_spent
    quiescent = zi.IntegratedTrial.quiescent
    decision_end_reason = zi.IntegratedTrial.decision_end_reason
    end_state = zi.IntegratedTrial.end_state
    finish = zi.IntegratedTrial.finish
    _remember_command = zi.IntegratedTrial._remember_command
    _arm_reask = zi.IntegratedTrial._arm_reask
    wakeups = zi.IntegratedTrial.wakeups

    def __init__(self, scenario, *, condition, seed, links, horizon_s, code_sha='unknown', map_bundle,
                 model_adapter, model_settings, cost_params=None, policy=None, decision_limits=None,
                 bundle_id=BUNDLE_ID, run_id=None):
        if condition not in PAIR_CONDITIONS:
            raise ContractViolation(f'{condition!r} is not a pair LLM condition {PAIR_CONDITIONS}')
        if sorted(links) != sorted(PAIR_ROBOTS) or any(links[r].robot_id != r for r in links):
            raise ContractViolation(f'links must be exactly one own PairLink per robot {PAIR_ROBOTS}')
        policy = policy or PAIR_POLICY
        for name in ('max_calls_per_actor', 'max_http_attempts_per_actor', 'max_attempts_total'):
            if type(getattr(policy, name)) is not int or getattr(policy, name) < 1:
                raise ContractViolation(f'pair {name} must be a positive integer')
        if policy.max_outstanding_per_actor != 1:
            raise ContractViolation('pair decisions require one outstanding call per robot')
        self.links = dict(links)
        self.decision_limits = decision_limits or DecisionLimits(
            max_calls_total=decisions.CALLS_TOTAL, max_utterances_per_actor=decisions.UTTERANCES_PER_ACTOR,
            max_utterances_total=decisions.UTTERANCES_TOTAL)
        # ``arm`` is the pair's own name (peer_nl); ``condition`` is the sealed study name the borrowed
        # study methods validate against (``study_spec``). Everything the pair writes carries ``arm``.
        self.arm, self.condition, self.seed = condition, study_spec(condition), int(seed)
        self.spec = zp.spec(self.condition)
        self.params = cost_params or params()
        self.library = zi._NoStoredFrames()
        self.horizon_s, self.code_sha, self.bundle_id = float(horizon_s), code_sha, bundle_id
        self.bundle = map_bundle
        self.source = pi.PairSheetSource(scenario, self.bundle)
        self.scenario_id = self.source.scenario_id
        self.static_map = static_map_for_call(self.bundle)
        self.map_png, self.map_meta = map_figure(self.bundle)
        self.sheet = self.source.sheet()
        self.leader_id = None
        self.actors = PAIR_ROBOTS
        self.run_id = run_id or f'{self.arm}-{self.scenario_id}-s{self.seed}'
        self.client_factory, self.send_ledger = model_adapter.client_factory, model_adapter.send_ledger
        # ``OfflineTrial.cost_summary`` reads ``wire.requests``; the pair never uses the fixture wire (the
        # real count is reconciled from the send ledger), so this is a zero placeholder reported as None.
        self.wire = types.SimpleNamespace(requests=0)
        self.actor = 'gemini_proxy'
        self.model_settings = dict(model_settings)
        self.prompt_template_sha256 = digest({'version': PROMPT_VERSION, 'template': _template_sha()})
        self.provenance = provenance(source=self.source, code_sha=code_sha, execution_bundle_id=bundle_id,
                                     model=self.model_settings['model'],
                                     provider=self.model_settings.get('provider'),
                                     model_settings_sha256=digest(self.client_factory.settings),
                                     prompt_template_sha256=self.prompt_template_sha256,
                                     cost_profile_id=self.params.version)
        self.channel = zp.Transport(self.condition, seed=self.seed, robots=PAIR_ROBOTS,
                                    vocabulary=zo._vocabulary(self.sheet, self.bundle), delivery_owner=zo.BUS_OWNER,
                                    delivery_delay_sim_s=delivery_delay_s(1, self.params))
        self.channel.open_window('w1', at_sim_s=0.)
        if self.spec.channel_open:
            self.channel.cap_robot = self.decision_limits.max_utterances_per_actor
            self.channel.cap_window = self.decision_limits.max_utterances_total
        else:
            self.channel.cap_robot = min(self.channel.cap_robot, self.decision_limits.max_utterances_per_actor)
        self.channel.cap_total = self.decision_limits.max_utterances_total if self.spec.channel_open else 0
        self.policy = policy
        self.transport = zi._LiveTransport(self, send_ledger=self.send_ledger, client_factory=self.client_factory)
        self.scheduler = DecisionScheduler(
            self.transport, cost_params=self.params, policy=self.policy, actors=PAIR_ROBOTS,
            on_action=self._on_action, bus=self.channel, bus_owner=zo.BUS_OWNER,
            own_job=self._message_own_job, decision_limits=self.decision_limits,
            external_budget_spent=lambda: self.transport.budget_exhausted)
        self.calls, self.messages, self.actions, self.requests = [], [], [], []
        self._output_token_counts = {}
        self.envelopes = {}
        self._history, self._issued = {a: [] for a in PAIR_ROBOTS}, []
        self._call_index = {a: 0 for a in PAIR_ROBOTS}
        self._observations = {a: 0 for a in PAIR_ROBOTS}
        self._snapshots, self._jobs, self._claim_entries = {}, {}, {}
        self.request_images: dict[str, bytes] = {}
        self.input_log, self.dispatch_log, self.executor_events = [], [], []
        self.language_rows, self.claim_results = [], []
        self._last_end = {a: None for a in PAIR_ROBOTS}      # latest own job end (class only, never the detail)
        self._refusal_mark = {a: 0 for a in PAIR_ROBOTS}      # refusal total at this robot's previous call start
        self.clock_drift_s = 0.0

    # -- inputs -----------------------------------------------------------------------------
    def _message_own_job(self, actor):
        """Coordinator-approved deviation e7: only received-text availability sees the open window.

        The real own job, controller, busy re-ask timer and sealed scheduler are unchanged.
        """
        link = self.links[actor]
        if link.decision_window.is_open(self.scheduler.clock):
            return None
        return link.job()

    def snapshot(self, call):
        """The caller's OWN inputs at the call start: the study's snapshot plus the closed own-status record."""
        zi.IntegratedTrial.snapshot(self, call)
        actor, t = call.actor, float(call.started_sim_s)
        snap = self._snapshots[(actor, round(t, 6))]
        link = self.links[actor]
        view = link.gate_view()
        since = view['refusal_total'] - self._refusal_mark[actor]
        self._refusal_mark[actor] = view['refusal_total']
        claim = next((e for e in reversed(snap['history']) if e['kind'] == 'claim_order'), None)
        job = link.job()
        snap['status'] = status.build(
            now=t, claim_issued_s=None if claim is None else claim['issued_at_sim_s'], view=view,
            job_kind=None if job is None else job['kind'], last_end=self._last_end[actor],
            refusals_since_last_call=since)

    def on_executor_event(self, event, *, at_s):
        """The study's own-event handling, plus the class of the robot's latest finished job (own status)."""
        zi.IntegratedTrial.on_executor_event(self, event, at_s=at_s)
        self.executor_events[-1].update(delivered_at_sim_s_since_reset=float(at_s), sim_s_absolute=event.get('sim_s'))
        link = self.links[event['robot_id']]
        opened = link.decision_window.on_event(event, origin_s=link.origin_s)
        if opened and link.decision_window.is_open(at_s) and at_s <= self.horizon_s:
            # Existing pair_progress, pair-owned trigger label; the sealed EVENTS/trigger map is untouched.
            self.scheduler.trigger(event['robot_id'], 'idle', at=at_s)
            if self.spec.channel_open:
                self.scheduler.available(event['robot_id'], at=at_s)
        if event['event'] in ('job_done', 'job_failed') and event.get('job_kind') in ('pair_carry', LOOK_AROUND):
            reason = (event.get('detail') or {}).get('reason')
            # The end is dated by the event's own backend time on the harness clock (backend time - reset origin),
            # the same axis and the same kind of stamp as the gate's submission events. The delivery time ``at_s``
            # is up to one tick later and would tie with, or pass, a refusal that really came after the end.
            happened = event.get('sim_s')
            ended_s = float(at_s) if happened is None else float(happened) - self.links[event['robot_id']].origin_s
            self._last_end[event['robot_id']] = {'job_kind': event['job_kind'], 'sim_s': round(ended_s, 6),
                                                 'reason_class': status.end_class(reason)}

    def build_inputs(self, actor, *, sim_time_s, request_id):
        snap = self._snapshots.pop((actor, round(float(sim_time_s), 6)), None)
        if snap is None:
            raise ContractViolation(f'no own-input snapshot of {actor} at {sim_time_s}')
        frame = snap['frame']
        payload = pi.build_payload(
            robot_id=actor, condition=self.arm, request_id=request_id, sim_time_s=sim_time_s,
            static_map=self.static_map, order_sheet=self.source.sheet(),
            own_rgb_refs=[pi.own_rgb_ref(actor, frame.index, frame.t, frame.sha256)],
            own_command_history=snap['history'], self_belief=snap['belief'], own_status=snap['status'],
            inbox=snap['inbox'], pinned=self.source.pinned)
        self.request_images[frame.sha256] = frame.jpeg
        self.input_log.append({'request_id': request_id, 'robot': actor, 'sim_s': sim_time_s,
                               'frame_index': frame.index, 'frame_t': frame.t, 'frame_sha256': frame.sha256,
                               'history_entries': len(snap['history']), 'own_status': dict(snap['status']),
                               'inbox_ids': [m['message_id'] for m in snap['inbox'] or ()]})
        return pi.PairInputs(payload, frame.jpeg, self.map_png, self.source.pinned)

    def prepare_call(self, call) -> zo.PreparedCall:
        request_id = f'req_{call.call_id.replace("-", "_")}'
        bundled = self.build_inputs(call.actor, sim_time_s=call.started_sim_s, request_id=request_id)
        window = self.channel.window_context(call.actor, now_sim_s=call.started_sim_s) \
            if self.spec.channel_open else None
        return zo.PreparedCall(bundled=bundled, request=pi.build_request(bundled, window=window),
                               request_id=request_id)

    def finish_call(self, call, prepared, raw, *, provider_usage=None) -> CallReply:
        """Reply text -> validation -> relay -> costed attempts. ``zo.OfflineTrial.finish_call`` with the pair."""
        actor, bundled, request, request_id = call.actor, prepared.bundled, prepared.request, prepared.request_id
        self._output_token_counts[call.call_id] = pk.count_tokens(
            raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False))
        input_tokens = request['billed_tokens']['total_billed']       # text bill + fixed image charge (v2)
        try:
            value = validate_reply(raw, request_id=request_id, condition=self.condition, actor=actor,
                                      order_ids=bundled.order_ids(), item_ids=bundled.item_ids(),
                                      roles_by_order=bundled.roles_by_order(), vocabulary=bundled.vocabulary(),
                                      passages=bundled.passages(), location_refs=bundled.location_refs(),
                                      robots=PAIR_ROBOTS)
        except zp.ProtocolError as exc:
            produced = zo.generated_utterances(raw)
            attempts = (Attempt(outcome='invalid', input_tokens=input_tokens,
                                output_tokens=pk.count_tokens(raw if isinstance(raw, str) else json.dumps(raw)),
                                utterances=produced),)
            self._archive(call, bundled, request, status='invalid_json', messages_out=0,
                          unparsed_utterances=produced, error=str(exc), provider_usage=provider_usage)
            return CallReply(attempts=attempts, action=None, messages=(), unparsed_utterances=produced,
                             provider_usage=provider_usage)
        utterances = len(value['messages'])
        attempts = (Attempt(outcome='ok', input_tokens=input_tokens,
                            output_tokens=self.sim_output_tokens(raw, utterances), utterances=utterances),)
        cost = call_cost(attempts, self.params)
        release = round(call.started_sim_s + cost.sim_s, 6)
        receipts = zp.relay(self.channel, actor, value, at_sim_s=release) if value['messages'] else ()
        messages = []
        for index, receipt in enumerate(receipts):
            sent = value['messages'][index]
            language = receipt.language or {}
            self.language_rows.append({
                'call_id': call.call_id, 'sender': actor, 'accepted': receipt.accepted,
                'rejection': receipt.rejection, 'hangul_ratio': language.get('hangul_ratio'),
                'korean': language.get('korean'), 'flags': list(language.get('flags', ())),
                'chars': len(sent.get('text') or ''), 'language_violation': receipt.language_violation})
            if not receipt.accepted:
                messages.append(zo.Message(sender=actor, recipients=tuple(sent['recipients']), body=None,
                                           encoding=self.spec.encoding,
                                           message_id=f'{call.call_id}-rejected-{index + 1}',
                                           rejection=receipt.rejection or 'rejected'))
                continue
            envelope = receipt.envelope
            self.envelopes[envelope.message_id] = envelope.record()
            self.language_rows[-1]['message_id'] = envelope.message_id
            messages.append(zo.Message(sender=actor, recipients=tuple(envelope.recipients), body=envelope.body(),
                                       encoding=self.spec.encoding, message_id=envelope.message_id,
                                       reply_to=envelope.reply_to))
        self._record(call, bundled, value, release, request, provider_usage=provider_usage)
        return CallReply(attempts=attempts, action=value['action'], messages=tuple(messages),
                         provider_usage=provider_usage)

    def sim_output_tokens(self, raw, utterances):
        return pk.count_tokens(raw)

    def _archive(self, call, bundled, request, **kwargs):
        row = zo.OfflineTrial._archive(self, call, bundled, request, **kwargs)
        row['token_measurement'] = billing.token_measurement(
            request, output_tokens=self._output_token_counts.get(call.call_id),
            provider_usage=kwargs.get('provider_usage'))
        return row

    def channel_summary(self):
        row = zo.OfflineTrial.channel_summary(self)
        row.update(condition=self.arm, study_spec=self.condition)
        return row

    def _collect(self):
        """Call rows as the study builds them, then the image part of the input bill moved to its own field.

        ``Attempt.input_tokens`` carries the whole bill (text + images) so the SIM cost includes the images; the
        study's call row would file all of it under ``input_tokens.text``. Rows whose bill is known from the
        archived request are split ``{text, image, cached}`` (the contract's own field names).
        """
        zo.OfflineTrial._collect(self)
        bills = {row['request_id']: row['billed_tokens'] for row in self.requests}
        for row in self.calls:
            bill = bills.get(row['request_id'])
            tokens = row.get('input_tokens')
            if bill and isinstance(tokens, dict) and tokens.get('text') == bill['total_billed']:
                row['input_tokens'] = {'text': bill['total_text_billed'], 'image': bill['image_tokens_billed'],
                                       'cached': tokens.get('cached', 0)}
                validate_log_record(row)

    def cost_summary(self):
        row = zo.OfflineTrial.cost_summary(self)
        image = sum(c['input_tokens'].get('image', 0) for c in self.calls)
        row.update(wire_requests=None, wire_requests_basis='requires_provider_reconciliation',
                   input_tokens_image=image, input_tokens_charged=row['input_tokens'] + image,
                   image_billing=billing.record()['version'])
        return row

    def literals(self) -> tuple:
        ids = list(zo.OfflineTrial.literals(self))
        return tuple(i for i in dict.fromkeys(ids) if i != 'r3')

    # -- actions ----------------------------------------------------------------------------
    def _release_action(self, actor, action, sim_s, call_id):
        """``zi.IntegratedTrial._on_action`` with the pair's action plan (``look_around`` added); otherwise identical."""
        extra = getattr(self, '_pending', {}).get(call_id)
        if extra is None or self.scheduler.calls[-1].actor != actor:
            raise AssertionError(f'released action of {actor} has no recorded call')
        link = self.links[actor]
        plan = pair_executor_plan(action, link.job(), actor=actor, orders=self.sheet['orders'])
        kind, arguments, order_id, role = pair_action_row(action)
        ack = link.call(plan.api, *plan.args) if plan.api else None
        absolute = None if ack is None else ack['sim_s']
        self.dispatch_log.append({'call_id': call_id, 'actor': actor, 'sim_s': sim_s, 'action': action,
                                  'api': plan.api, 'args': list(plan.args), 'ack': ack,
                                  'rejected_reason': plan.rejected_reason,
                                  'sim_s_since_reset': sim_s, 'sim_s_absolute': absolute,
                                  'reset_offset_s': None if absolute is None else round(absolute - sim_s, 6)})
        accepted = ack['accepted'] if ack else plan.rejected_reason is None
        reason = ack['rejected_reason'] if ack else plan.rejected_reason
        local = ack['local_state'] if ack else ('command_rejected' if reason else
                                                'command_issued' if link.job() else 'queue_empty')
        self.actions.append(action_log_record(
            run_id=self.run_id, condition_name=self.condition, seed=self.seed, actor=actor,
            action_id=extra['action_id'], request_id=extra['request_id'], submitted_at_sim_s=sim_s, kind=kind,
            arguments=arguments, accepted=accepted, order_id=order_id, role=role, rejected_reason=reason,
            local_state=local))
        if ack or reason:
            self._remember_command(actor, call_id, sim_s, plan, ack, kind, arguments, local)
        if self.scheduler.call_causes[call_id]['cause'] == 'common':
            self._arm_reask(actor, sim_s)

    def _on_action(self, actor, action, sim_s):
        call_id = self.scheduler.calls[-1].call_id
        self.links[actor].call_ref = call_id
        self._release_action(actor, action, sim_s, call_id)
        self.links[actor].call_ref = None
        row = self.dispatch_log[-1]
        if row['api'] == 'pair_carry' and row['ack'] and row['ack']['accepted']:
            self._claim_entries[call_id] = self._history[actor][-1]

    def on_claim_result(self, row) -> None:
        """The claim gate consumed a permit: the robot's OWN command state follows the submission's ack."""
        entry = self._claim_entries.pop(row.get('call_ref'), None)
        self.claim_results.append(copy.deepcopy(row))
        if entry is None:
            return
        if row['accepted']:
            if row.get('job_id'):
                self._jobs[row['job_id']] = entry
        else:
            entry['local_state'] = 'command_rejected'

    # -- records ----------------------------------------------------------------------------
    def study_config(self) -> dict:
        policy = {k: getattr(self.policy, k) for k in self.policy.__dataclass_fields__}
        return {'schema': DISPATCH_VERSION, 'execution_bundle_id': self.bundle_id, 'condition': self.arm,
                'study_spec': self.condition,
                'topology': self.spec.topology, 'encoding': self.spec.encoding, 'robots': list(PAIR_ROBOTS),
                'roles': dict(PAIR_ROLES), 'seed': self.seed, 'model_settings': dict(self.model_settings),
                'prompt_version': PROMPT_VERSION, 'prompt_template_sha256': self.prompt_template_sha256,
                'cost_params': {'version': self.params.version, 'digest': self.params.digest(),
                                'provisional': self.params.provisional},
                'input_billing': billing.record(), 'own_status': status.record(),
                'stop_decisions': decisions.record(),
                'action_kinds': list(PAIR_ACTION_KINDS), 'clocks': dict(CLOCKS),
                'call_policy': policy, 'quantum_s': zi.QUANTUM_S, 'think_hold_policy': zi.THINK_HOLD_POLICY,
                'action_map': {'version': zi.ACTION_MAP_VERSION, 'wait_hold_s': zi.WAIT_HOLD_S},
                'decision_policy': DECISION_POLICY, 'decision_limits': {
                    'max_calls_total': self.decision_limits.max_calls_total,
                    'max_utterances_per_actor': self.decision_limits.max_utterances_per_actor,
                    'max_utterances_total': self.decision_limits.max_utterances_total},
                'dialogue_caps': {'window': self.channel.cap_window, 'actor': self.channel.cap_robot,
                                  'episode': self.channel.cap_total, 'windows_per_episode': 1},
                'order_sheet_sha256': self.source.sha256, 'map_schematic': dict(self.map_meta),
                'inter_robot_channels': (['dialogue'] if self.spec.channel_open else []) + ['pair_status']}


def _template_sha() -> str:
    from harness.pair_llm_prompts_ko import prompt_template_sha256
    return prompt_template_sha256()


__all__ = ['DISPATCH_VERSION', 'BUNDLE_ID', 'PAIR_POLICY', 'PairLink', 'PairTrial', 'map_figure']
