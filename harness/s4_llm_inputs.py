"""Three-robot study inputs plus the existing closed pair stop-window fields.

The general payload is validated by StudyInputs. Only r1/r2 may add the pair's
own estimate/window, validated by #371; no runtime or evaluator is reachable.
"""
from dataclasses import dataclass
from functools import lru_cache
import json

from harness import pair_llm_billing as billing
from harness import pair_llm_prompts_ko as pp
from harness import zone_study_prompts_ko as pk
from harness.pair_llm_stop_adapter import belief_violations, window_violations
from harness.zone_study_contract import ContractViolation, digest

VERSION = 'ugrp.s4_llm_inputs.v1'
PROMPT_VERSION = 'ugrp.s4_llm_prompt.v2'
MODEL_CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured', 'peer_nl')

def study_spec(condition):
    if condition not in MODEL_CONDITIONS:
        raise ContractViolation('unknown S4 model condition')
    return 'peer_ko' if condition == 'peer_nl' else condition
PAIR = ('r1', 'r2')
ROBOTS = (*PAIR, 'r3')

HEAD = '''당신은 로봇 {rid}입니다. r1, r2, r3가 한 호스트에서 각자 판단합니다.
개발용 역할은 고정입니다: r1은 빔의 end_neg, r2는 빔의 end_pos, r3는 cyan의 west입니다.
claim은 order_sheet의 주문에 맞는 기존 실행기를 선택합니다.
cyan은 r3 단독 deliver, long_beam은 r1/r2 각자의 pair_carry로 연결됩니다.
목적 구역과 역할은 주문 그대로 쓰십시오. 다른 로봇을 대신 배정하지 마십시오.
진행 중에는 continue, 중단은 자기 작업에 대한 release입니다.
자기 wrist RGB와 자기 발행 명령, 정적 지도·주문, 실제 수신 메시지만 근거입니다.
정적 지도 그림은 현재 상황이 아닙니다. 명령 종료는 배달 성공 판정이 아닙니다.
보이지 않는 상태는 unknown으로 두십시오. 다른 로봇의 영상·상태는 주어지지 않습니다.'''
PAIR_BEHAVIOUR = '''빔 운반은 두 로봇이 각자 같은 주문을 claim해야 시작됩니다.
look_around는 자기 실행기의 둘러보기 요청입니다.
own_belief는 자기 영상·명령으로 추정한 불확실성 구간입니다.
decision_window가 있을 때만 carry_decision 또는 post_look_decision을 낼 수 있습니다.
carry_decision: continue 또는 set_down. post_look_decision: regrasp 또는 look_again.
모든 시간은 호스트 시작 이후 시간이며, set_down은 latch_until_sim_s까지 도착해야 합니다.
결정은 요청 시 보았던 창에만 적용됩니다. 닫혔거나 바뀐 창의 답은 거절됩니다.
기본 continue는 정지 결정을 바꾸지 않으며, 창이 끝나면 기존 규칙을 따릅니다.
안전 규칙은 유지됩니다. look_again은 로봇당 사례 1회·정지점당 1회입니다.
own_belief와 decision_window를 근거로 쓰면 decision_sources에 own_commands를 씁니다.'''
ACTION = '''- action은 정확히 하나입니다:
  {"kind":"claim","order_id":"주문 ID","role":"역할","destination_zone":"구역"},
  {"kind":"continue"}, {"kind":"release","order_id":"주문 ID"}.
  r1/r2만 {"kind":"look_around"}, {"kind":"carry_decision","choice":"continue"|"set_down"},
  {"kind":"post_look_decision","choice":"regrasp"|"look_again"}도 사용할 수 있습니다.'''


def system_prompt(condition, rid, *, cap_window=12, cap_robot=6, seed=0):
    if rid not in ROBOTS:
        raise ContractViolation('unknown S4 robot')
    parts = pk.prompt_parts(study_spec(condition), rid, seed=seed,
                            cap_window=cap_window, cap_robot=cap_robot)
    departure = ('r3의 own_command_history에 S4_DEPARTURE_PENDING이 있으면, '
                 '집게 HIGH 자세를 발행한 뒤 운반 출발 결정을 기다리는 상태입니다. '
                 '이는 실제 파지 성공 판정이 아닙니다. continue로 출발을 허가할 수 있습니다. '
                 'pending 이전에 요청된 답이나 10 SIM초 뒤 도착한 답은 출발에 쓰이지 않습니다.')
    return '\n\n'.join((HEAD.format(rid=rid), parts['channel'],
                        PAIR_BEHAVIOUR if rid in PAIR else departure,
                        pk.KO_OUTPUT_HEAD, ACTION, pk.KO_SOURCES,
                        parts['messages'], pk.KO_SEPARATION, parts['language']))


@lru_cache(maxsize=32)
def fixed_prompt_tokens(cap_window, cap_robot, seed=0):
    return max(pk.count_tokens(system_prompt(c, r, cap_window=cap_window,
                                            cap_robot=cap_robot, seed=seed))
               for c in MODEL_CONDITIONS for r in ROBOTS)


@dataclass(frozen=True)
class Inputs:
    base: pk.StudyInputs
    arm: str
    own_belief: dict | None = None
    decision_window: dict | None = None

    def __post_init__(self):
        if self.base.condition != study_spec(self.arm) or self.base.robot_id not in ROBOTS:
            raise ContractViolation('S4 arm/robot differs from the validated study payload')
        if self.base.robot_id in PAIR:
            errors = belief_violations(self.own_belief)
            errors += window_violations(self.decision_window, self.base.sim_time_s)
            if errors:
                raise ContractViolation('; '.join(errors))
        elif self.own_belief is not None or self.decision_window is not None:
            raise ContractViolation('r3 has no pair estimate or decision window')
        object.__setattr__(self, 'own_belief', pk.freeze(self.own_belief))
        object.__setattr__(self, 'decision_window', pk.freeze(self.decision_window))

    def __getattr__(self, name):
        return getattr(self.base, name)

    def payload_dict(self):
        payload = self.base.payload_dict()
        payload['schema'] = VERSION
        if self.robot_id in PAIR:
            payload.update(own_belief=pk.thaw(self.own_belief), decision_window=pk.thaw(self.decision_window))
        return payload

    @property
    def payload(self):
        return pk.freeze(self.payload_dict())

    @property
    def payload_sha256(self):
        return digest(self.payload_dict())


def build_request(inputs, *, window=None):
    # Revalidate every base field/image and let the established builder handle
    # the delivered inbox and dialogue budget. Rebuild hashes after extension.
    request = pk.build_request(inputs.base, window=window)
    Inputs(inputs.base, inputs.arm, pk.thaw(inputs.own_belief), pk.thaw(inputs.decision_window))
    body = json.loads(request['messages'][1]['content'])
    body.update(inputs.payload_dict())
    caps = body.get(pk.WINDOW_KEY, {})
    total, per_actor = caps.get('max_utterances', 12), caps.get('max_your_utterances', 6)
    system = system_prompt(inputs.arm, inputs.robot_id, cap_window=total, cap_robot=per_actor, seed=inputs.base.seed or 0)
    user = json.dumps(body, sort_keys=True, ensure_ascii=False)
    request.update(schema=VERSION, condition=inputs.arm, prompt_version=PROMPT_VERSION,
                   payload_schema=VERSION, input_sha256=inputs.payload_sha256,
                   messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}])
    request['request_sha256'] = pk.request_digest_from_refs(system, user, request['image_refs'])
    request['tokens'] = pk.request_tokens(system, user, request['images'])
    request['billed_tokens'] = billing.billed_tokens(request['tokens'],
                                                    system_billed=fixed_prompt_tokens(total, per_actor, inputs.base.seed or 0))
    return request
