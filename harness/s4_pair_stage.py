"""S4 pair preparation, default off. No physics imports or automatic model calls.

Reuse the sealed study scheduler/dialogue/ledger and S3 own executors. The
opt-in response vocabulary is local to this trial (no global monkeypatch).
"""
import copy
from dataclasses import dataclass
from functools import lru_cache
import json
from types import MethodType

from harness import s4_live_stage as old
from harness import s4_llm_inputs as si
from harness import s4_pair_handshake as hs
from harness.zone_final_pair_binding import bind
from harness.zone_study_inputs import command_entry
from harness.zone_study_contract import digest

pair = old.s4.pair
PROMPT = '''S4 빔 mutual_go_v1 토글이 켜져 있습니다. 기존 claim으로 각자 정렬·집기를 요청합니다.
pair_handshake는 자기 명령 단계와 고정 안전 상태신호만 제공합니다. 성공·접촉 정답이 아닙니다.
wait_go에서 자기 wrist RGB로 빔이 집게에 유지되어 보일 때만 go를 선택합니다.
상대 GO를 실제로 받고 자신도 go를 낸 뒤 ack_go로 peer_go_ref를 그대로 확인하십시오.
두 로봇의 go와 ack_go가 모두 승인되기 전에는 운반할 수 없습니다. 기본 continue는 GO가 아닙니다.
carry에서는 매 요청의 자기 RGB를 확인해 held, 이탈이 보이면 grip_lost, 보이지 않거나 판단이 어려우면 unknown.
go/ack_go/held/grip_lost/unknown에는 decision_sources의 own_rgb가 반드시 필요합니다.
action 형식: {"kind":"pair_decision","epoch":0,"choice":"go"|"ack_go"|"held"|"grip_lost"|"unknown","peer_go_ref":null}.
epoch는 현재 pair_handshake.epoch, peer_go_ref는 ack_go일 때만 받은 값을 씁니다. r3는 이 행동을 쓰지 않습니다.
no_comm은 messages=[]와 고정 GO/ABORT 신호만 사용합니다. peer_ko/leader_ko는 기존 허용 상대에게 자유 한국어로
GO 의사·상대 확인·이탈을 알립니다. structured는 기존 형식의 inform/accept/cancel과 held/absent/unknown을 사용합니다.
고정 안전신호는 네 조건에 동일합니다. 상대의 자유 대화는 상태 정답이 아니며 스스로 확인해야 합니다.
응답의 자기 영상은 요청 시각부터 10 SIM초 미만만 유효합니다. 이탈/운반 중 unknown/기한 만료는 두 로봇을 정지합니다.'''

HEARTBEAT_PROMPT = '''all_phase_rgb_heartbeat_v2: pair_handshake.own_executor_phase는 자기 발행 명령의
소프트웨어 단계이며 실제 접촉/성공 판정이 아닙니다. 운반 세션의 모든 단계에서 정상 응답은 동일한 liveness
heartbeat가 됩니다. 명령 거부와 heartbeat는 별개이며, 거부된 명령은 실행되지 않습니다.
carry/lift/raise/wait_carry 단계에서는 위의 자기 RGB held/grip_lost/unknown 규칙을 따르십시오.
lower/open/refix_look/refix_post_look 등 의도적인 내려놓기·재관측 단계에는 잡고 있을 의무가 없으므로
그 이유만으로 grip_lost/unknown을 보고하지 마십시오. 열린 decision_window에 맞춰 carry_decision 또는
post_look_decision을 선택하고, 창이 없으면 continue로 자기 명령 진행을 기다리십시오.
정렬·재집기·운반 중 예상하지 않은 이탈이 자기 RGB에 보이면 abort로 정지하십시오.'''


def validate_reply(raw, **kwargs):
    try:
        value = pair.zp.parse(raw) if isinstance(raw, str) else copy.deepcopy(raw)
    except Exception:
        return pair.validate_reply(raw, **kwargs)
    action = value.get('action') if isinstance(value, dict) else None
    if not isinstance(action, dict) or action.get('kind') != 'pair_decision':
        return pair.validate_reply(raw, **kwargs)
    if (kwargs['actor'] not in hs.PAIR or set(action) != {'kind', 'epoch', 'choice', 'peer_go_ref'}
            or type(action['epoch']) is not int or action['epoch'] < 0 or action['choice'] not in hs.CHOICES
            or not isinstance(value.get('decision_sources'), list)
            or ('own_rgb' not in value['decision_sources'])
            or (action['choice'] == 'ack_go' and not pair.zp.is_message_id(action['peer_go_ref']))
            or (action['choice'] != 'ack_go' and action['peer_go_ref'] is not None)):
        raise pair.zp.ProtocolError('invalid own-camera pair decision')
    checked = pair.validate_reply({**value, 'action': {'kind': 'continue'}}, **kwargs)
    if (kwargs['condition'] != 'no_comm' and action['choice'] in ('go', 'ack_go', 'grip_lost')
            and not checked['messages']):
        raise pair.zp.ProtocolError('pair GO/ACK/loss needs a condition-channel notification')
    checked['action'] = action
    return checked


def plan(action, job, **kwargs):
    if action['kind'] == 'pair_decision':
        return old.s4.zi.Plan('pair_decision', (action,))
    return old.s4.routing.executor_plan(action, job, **kwargs)


@lru_cache(maxsize=32)
def fixed_tokens(total, per_actor, seed, heartbeat=False):
    return max(si.pk.count_tokens(si.system_prompt(c, r, cap_window=total, cap_robot=per_actor, seed=seed)
                                 + '\n\n' + PROMPT + ('\n\n'+HEARTBEAT_PROMPT if heartbeat else ''))
               for c in old.CONDITIONS for r in si.ROBOTS)


@dataclass(frozen=True)
class Inputs:
    base: si.Inputs
    state: dict | None

    def __getattr__(self, name):
        return getattr(self.base, name)

    def payload_dict(self):
        return {**self.base.payload_dict(), 'pair_handshake': copy.deepcopy(self.state)}

    @property
    def payload_sha256(self):
        return digest(self.payload_dict())


class Link(old.Link):
    def __init__(self, *args, handshake, **kwargs):
        super().__init__(*args, **kwargs)
        self.handshake = handshake
        self.pair_claim_args = None
        self.pair_started = False
        self.pair_submission_log = []
        self.response_context = None

    def call(self, api, *args, **kwargs):
        if self.robot_id not in hs.PAIR:
            return super().call(api, *args, **kwargs)
        if api == 'pair_carry':
            ack = super().call(api, *args, **kwargs)
            if ack['accepted']:
                if not self.handshake.claim(self.robot_id, self.call_ref):
                    ack.update(accepted=False, rejected_reason='PAIR_CLAIM_CLOSED')
                else:
                    self.pair_claim_args = args
                    ack.update(scope='llm_pair_claim_pending_s3_admission', job_id=self.robot_id+'-pair-pending')
            return ack
        if api == 'pair_decision':
            ctx = self.response_context
            row = self.handshake.decide(self.robot_id, args[0], call_id=self.call_ref, **ctx)
            return dict(robot_id=self.robot_id, api=api, sim_s=self.inner.clock(),
                action_id=self.call_ref, arguments={}, job_id=None, accepted=row['accepted'],
                rejected_reason=row['reason'], local_state='command_issued' if row['accepted'] else 'command_rejected')
        if api == 'abort':
            self.handshake.abort(self.robot_id, self.clock(), 'LLM_RELEASE')
            return dict(robot_id=self.robot_id, api=api, sim_s=self.inner.clock(), action_id=self.call_ref,
                arguments={}, job_id=None, accepted=True, rejected_reason=None, local_state='hold_requested')
        return super().call(api, *args, **kwargs)

    def job(self):
        if self.robot_id in hs.PAIR and self.handshake.view(self.robot_id, self.clock())['phase'] in ('wait_go', 'carry'):
            return None  # own decision/monitor window; ordinary dialogue may wake this actor
        return super().job()


class Trial(old.Trial):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handshake = self.links['r1'].handshake
        if self.links['r2'].handshake is not self.handshake:
            raise ValueError('one pair safety wire required')
        self.pair_snapshots = {}
        self.carry_sources = {}

    def snapshot(self, call):
        super().snapshot(call)
        if call.actor in hs.PAIR:
            frame = self._snapshots[(call.actor, round(float(call.started_sim_s), 6))]['frame']
            seen = self.handshake.view(call.actor, call.started_sim_s)
            if self.handshake.carry_lease_renewal == hs.PHASE_HEARTBEAT:
                # Own executor software state only: no measurements or peer state.
                adapter = self.links[call.actor].stop_adapter
                ctl = adapter.controller() if adapter is not None else None
                seen['own_executor_phase'] = getattr(ctl, 'state', None)
            self.pair_snapshots[call.call_id] = dict(requested_at=call.started_sim_s,
                frame_t=frame.t, frame_sha256=frame.sha256, seen=seen)

    def prepare_call(self, call):
        prepared = super().prepare_call(call)
        state = self.pair_snapshots.get(call.call_id, {}).get('seen')
        bundled = Inputs(prepared.bundled, state)
        request = copy.deepcopy(prepared.request)
        body = json.loads(request['messages'][1]['content'])
        body['pair_handshake'] = state
        system = request['messages'][0]['content'] + '\n\n' + PROMPT
        if self.handshake.carry_lease_renewal == hs.PHASE_HEARTBEAT:
            system += '\n\n' + HEARTBEAT_PROMPT
        user = json.dumps(body, ensure_ascii=False, sort_keys=True)
        request.update(prompt_version='ugrp.s4_pair_prompt.v1', input_sha256=bundled.payload_sha256,
            messages=[dict(role='system', content=system), dict(role='user', content=user)])
        request['request_sha256'] = si.pk.request_digest_from_refs(system, user, request['image_refs'])
        request['tokens'] = si.pk.request_tokens(system, user, request['images'])
        caps = body.get(si.pk.WINDOW_KEY, {})
        request['billed_tokens'] = si.billing.billed_tokens(request['tokens'], system_billed=fixed_tokens(
            caps.get('max_utterances', 12), caps.get('max_your_utterances', 6), self.seed,
            self.handshake.carry_lease_renewal == hs.PHASE_HEARTBEAT))
        return old.s4.zo.PreparedCall(bundled, request, prepared.request_id)

    def finish_call(self, call, prepared, raw, **kwargs):
        reply = bind(pair.PairTrial.finish_call, validate_reply=validate_reply)(
            self, call, prepared, raw, robots=si.ROBOTS, **kwargs)
        if reply.action:
            value = pair.zp.parse(raw) if isinstance(raw, str) else raw
            self.carry_sources[call.call_id] = tuple(value['decision_sources'])
        return reply

    def _on_action(self, actor, action, sim_s):
        if action['kind'] != 'pair_decision':
            result = super()._on_action(actor, action, sim_s)
            if actor in hs.PAIR and (action['kind'] == 'carry_decision'
                    or self.handshake.carry_lease_renewal == hs.PHASE_HEARTBEAT):
                call_id = self.scheduler.calls[-1].call_id
                ack = self.dispatch_log[-1].get('ack') or {}
                row = self.handshake.renew_carry(actor, action, call_id=call_id,
                    command_accepted=ack.get('accepted', False),
                    decision_sources=self.carry_sources.get(call_id, ()),
                    **self.pair_snapshots[call_id], now=sim_s)
                if row is not None:
                    self.dispatch_log[-1]['carry_lease_renewal'] = copy.deepcopy(row)
            return result
        old.s4.live.check_health(self)
        call = self.scheduler.calls[-1]
        link = self.links[actor]
        link.call_ref = call.call_id
        link.response_context = {**self.pair_snapshots[call.call_id], 'now': sim_s}
        try:
            bind(pair.PairTrial._release_action, pair_action_row=lambda a: ('noop', {}, None, None))(
                self, actor, action, sim_s, call.call_id, planner=plan)
        finally:
            link.call_ref = link.response_context = None
        if self.handshake.carry_lease_renewal == hs.PHASE_HEARTBEAT:
            ack = self.dispatch_log[-1].get('ack') or {}
            row = self.handshake.renew_carry(actor, action, call_id=call.call_id,
                command_accepted=ack.get('accepted', False),
                decision_sources=self.carry_sources.get(call.call_id, ()),
                **self.pair_snapshots[call.call_id], now=sim_s)
            self.dispatch_log[-1]['carry_lease_renewal'] = copy.deepcopy(row)

    def _remember_command(self, actor, call_id, sim_s, plan, ack, kind, arguments, local):
        if plan.api == 'pair_decision':
            self._history[actor].append(command_entry('cmd_'+call_id.replace('-', '_'), sim_s, 'noop',
                {'reason_code': 'S4_PAIR_'+plan.args[0]['choice'].upper()+'_'+('ACCEPTED' if ack['accepted'] else 'REJECTED')},
                local_state=local))
            return
        return super()._remember_command(actor, call_id, sim_s, plan, ack, kind, arguments, local)

    def study_config(self):
        return {**super().study_config(), 'pair_mode': hs.MODE, 'research_result': False,
                'carry_lease_renewal': self.handshake.carry_lease_renewal,
                'grip_detector': 'own_RGB_LLM_unvalidated', 'fixed_safety_wire_same_all_conditions': True}


class Host(old.Host):
    def __init__(self, *args, **kwargs):
        bind(old.s4.Host.__init__, Trial=Trial)(self, *args, **kwargs)


def components(mode='off'):
    if mode not in ('off', hs.MODE):
        raise ValueError('unknown pair mode')
    return (old.Link, old.Host) if mode == 'off' else (Link, Host)


class Driver:
    """Injected S3 own actors only; suppress automatic runtime claims.

    Caller supplies current own frames first, then poll -> Host.step_to -> step.
    A pair failure removes commands gathered earlier in the same host tick.
    """
    def __init__(self, host, pair_runtime, *, on_admit=lambda rid, ep, now: None):
        self.host, self.runtime, self.on_admit = host, pair_runtime, on_admit
        self.handshake = host.trial.handshake
        self.attached, self.next_ask, self.ask_keys, self.next_submit = set(), {}, {}, 0.

    def _attach(self, rid, ep):
        link = self.host.links[rid]
        original = ep.controller._wait_carry
        released_epochs = set()
        def wait(ctl, now, arm_idle):
            epoch = getattr(ctl, 'grip_epoch', 0)*1000+ctl.seg
            self.handshake.open(rid, epoch, now-link.origin_s)
            if not self.handshake.allowed(rid, epoch):
                ctl.port.hold(now)
                return
            if epoch not in released_epochs:
                # The existing low-level GO timeout starts when that barrier
                # is first entered, after the separate LLM handshake wait.
                ctl.state_t = now
                released_epochs.add(epoch)
            return original(now, arm_idle)
        ep.controller._wait_carry = MethodType(wait, ep.controller)
        self.attached.add(rid)

    def poll(self, now):
        rel = now-self.host.links['r1'].origin_s
        for rid in hs.PAIR:
            view = self.handshake.view(rid, rel)
            choice = 'go' if not view['own_go_sent'] else 'ack_go' if view['peer_go_ref'] and not view['own_ack_sent'] else None
            key = (view['epoch'], choice)
            due = bool(view['phase'] == 'wait_go' and choice and self.ask_keys.get(rid) != key)
            due |= view['phase'] == 'carry' and rel >= self.next_ask.get(rid, -1.)
            if due:
                self.host.trial.scheduler.trigger(rid, 'idle', at=rel)
                self.next_ask[rid] = rel+hs.MONITOR_S
                self.ask_keys[rid] = key

    def _stop(self, now):
        for rid in hs.PAIR:
            ep = self.runtime.actors[rid]._pair
            if ep is not None:
                ep.abort(now, self.handshake.failure)
                ep._clear(now)
        self.runtime.team.poll(now)
        return [(rid, {'kind': 'hold'}) for rid in hs.PAIR]

    def step(self, now):
        rel = now-self.host.links['r1'].origin_s
        self.handshake.tick(rel)
        if self.handshake.failure:
            return self._stop(now)
        if set(self.handshake.claims) == set(hs.PAIR) and now >= self.next_submit:
            self.next_submit = now+1.
            for rid in hs.PAIR:
                link = self.host.links[rid]
                if link.pair_started:
                    continue
                link.call_ref = link.claim_call
                try:
                    ack = old.s4.S3Link.call(link, 'pair_carry', *link.pair_claim_args)
                finally:
                    link.call_ref = None
                link.pair_submission_log.append(copy.deepcopy(ack))
                if ack['accepted']:
                    link.pair_started = True
                    ep = self.runtime.actors[rid]._pair
                    self.on_admit(rid, ep, now)
                    self._attach(rid, ep)
        issued = []
        for rid in hs.PAIR:
            if not self.host.links[rid].pair_started:
                continue
            own = self.runtime.actors[rid]
            decision = own.step(now)
            if decision['mode'] != 'tick':
                raise RuntimeError('S4 pair requires a fresh own frame before tick')
            issued.extend((rid, c) for c in decision['commands'])
        self.runtime.team.poll(now)
        for rid in hs.PAIR:
            ep = self.runtime.actors[rid]._pair
            if ep is not None:
                issued.extend((rid, c) for c in ep.arm_step(now))
        self.runtime.team.poll(now)
        for rid in hs.PAIR:
            ep = self.runtime.actors[rid]._pair
            if ep is not None and ep.terminal and ep.controller.state != 'done':
                self.handshake.abort(rid, rel, 'S3_PAIR_TERMINAL')
        return self._stop(now) if self.handshake.failure else issued
