"""System prompt of the two-robot pair-carry LLM layer (viability test; the instruction text is Korean).

The zone-study prompt (``harness.zone_study_prompts_ko``) is written for THREE
robots: its role line says "세 로봇 r1, r2, r3", its language block lists r3 and its
behaviour block tells a robot to ``wait`` when unsafe. The pair carry has two
robots and a destructive ``wait``/``release`` (they abort the carry), so this
module builds a pair-specific prompt and REUSES every block that is count-agnostic
(output head, decision sources, separation, no-message block).

User decision 2026-10-03 ("걍 한국어 조건 뺴주라"): there is NO language requirement any more.
The three study blocks that imposed one (the ``peer_ko`` channel slots, the ``messages`` schema
with ``"한국어 발화"`` and the ``KO_LANGUAGE`` rule) are replaced by pair-owned text that says the
message language is free (English is fine). The instruction text itself stays Korean because it
is the reused study text; only the requirement on the robots' messages is gone. The study's
``language_report`` still runs on every message as a RECORD (never a gate, never a rewrite).

Everything in the prompt is identical in the ``no_comm`` and ``peer_nl`` arms
except the channel / messages blocks, as in the study.
"""
from __future__ import annotations

import hashlib
import json

from harness import zone_study_prompts_ko as pk
from harness import zone_study_protocol as zp

PROMPT_VERSION = 'ugrp.pair_llm_prompts_ko.v3'
PAIR_ROBOTS = ('r1', 'r2')
PAIR_ROLES = {'r1': 'end_neg', 'r2': 'end_pos'}
PAIR_CONDITIONS = ('no_comm', 'peer_nl')
#: The sealed study protocol registers its open free-text peer channel under the name ``peer_ko``
#: (topology ``mesh``, encoding ``free_ko``). The pair arm is called ``peer_nl`` (natural language, no
#: language rule). Every call into the sealed study code (``zp.spec``, ``zp.Transport``, ``zp.validate_reply``,
#: ``zc.condition``) goes through this ONE table; the pair's own records, bundle, CLI, prompt and payload
#: carry the pair name. The study spec only supplies topology / caps / encoding; its language check is a
#: flag, never a gate (``Transport.send`` delivers and flags a message whatever its language).
STUDY_SPEC = {'no_comm': 'no_comm', 'peer_nl': 'peer_ko'}
#: SIM seconds both claims must be within (``PairTeam.rendezvous_timeout_s``). A fixed rule
#: of the task, stated identically in every arm.
RENDEZVOUS_S = 5

KO_PAIR_HEAD = '''당신은 로봇 {rid}입니다. 로봇 r1, r2는 한 팀의 동등한 동료입니다. 당신의 역할 이름은 {role}이고, \
동료 {partner}의 역할 이름은 {partner_role}입니다. 역할은 로봇마다 고정되어 있습니다.

목표:
order_sheet의 주문은 로봇 두 대가 함께 들어야 하는 물건입니다. 지정된 destination_zone(A, B, C)으로 두 로봇이 \
함께 운반하십시오. 안전하게 완료한 운반을 우선하고, 추론·발화 대기를 포함한 SIM 시간을 줄이십시오.

매 호출 제공되는 static_map, 정적 지도 그림 1장, order_sheet는 초기 계획 정보입니다.
현재 위치, 현재 물건 상태, 운반 완료를 보장하지 않습니다.
현재 상황의 근거는 자기 wrist RGB 1장, own_commands, own_belief, own_status와
이 조건에서 실제로 받은 수신 메시지뿐입니다.
공용 TOP 카메라, 동료 로봇의 영상·명령 기록, 시뮬레이터 상태, 정답 좌표,
성공·완료 판정은 제공되지 않습니다.
명령을 보냈다는 사실을 실제 이동·파지·운반 성공으로 간주하지 마십시오.
보이지 않거나 식별할 수 없으면 unknown으로 두십시오.'''

KO_PAIR_BEHAVIOUR = '''행동 판단:
claim은 이 주문의 운반을 시작해도 좋다는 허가입니다. 허가를 내면 이동·파지·들어올리기·운반·내려놓기는 \
로봇에 이미 있는 고정 절차가 맡고, 당신이 직접 조종하지 않습니다.
운반은 두 로봇이 같은 order_id를 각자 claim하고 두 claim이 약 %(window)d SIM초 안에 이루어질 때 시작됩니다. \
claim의 role은 자기 역할 이름으로, destination_zone은 order_sheet의 값 그대로 씁니다.
운반이 진행되고 있다고 판단되는 동안 기본 행동은 {"kind": "continue"}입니다.
{"kind": "wait"}와 {"kind": "release"}는 진행 중인 작업을 중단시킵니다. 자기 wrist RGB에 위험의 근거가 \
있을 때만 쓰십시오.
자기 wrist RGB에서 대상이 보이지 않아도 order_sheet의 주문이 계획입니다. 보이지 않는다는 이유만으로 \
중단하거나 미루지 마십시오.
같은 자리에서 같은 명령을 반복하지 마십시오.
각 로봇은 자기 행동을 스스로 결정합니다.
own_status는 당신 자신의 로봇 소프트웨어 상태입니다. last_outcome은 당신의 claim 뒤 마지막 결과입니다:
claim_released(허가는 났지만 아직 시작하지 않음), start_refused(로봇이 시작을 거절함, reason에 이유),
claim_rejected(claim이 받아들여지지 않음), pair_job_running(운반 절차 진행 중),
pair_job_ended(절차가 끝남, 운반 성공을 뜻하지 않음), look_around_running, look_around_ended입니다.
since_claim_s는 claim 뒤 지난 SIM초, refusals_since_last_call은 지난 호출 뒤 시작이 거절된 횟수입니다.
start_refused의 reason SELF_UNCERTAIN은 로봇이 자기 위치를 확신하지 못해 시작을 거절했다는 뜻입니다.
{"kind": "look_around"}는 제자리에서 돌며 주변을 둘러보는 동작입니다. 위치를 다시 추정하는 데 도움이 될 수
있지만 보장되지는 않습니다.
own_status를 근거로 쓰면 decision_sources에는 own_commands로 적습니다.''' % {'window': RENDEZVOUS_S}

KO_PAIR_ACTION = '''- action: 당신 자신의 행동 하나입니다. 다음 중 하나를 씁니다.
  {"kind": "claim", "order_id": order_sheet의 order_id, "role": order_sheet.kinds의 roles 중 당신의 역할 이름,
   "destination_zone": order_sheet의 destination_zone}
  {"kind": "continue"}
  {"kind": "wait"}
  {"kind": "release", "order_id": 놓아줄 order_id}
  {"kind": "look_around"}  (제자리에서 돌며 둘러봅니다. 위치를 다시 추정하는 데 도움이 될 수 있습니다. 실행 중인 작업이 없을 때만 시작됩니다)'''


def _pair_only(text: str) -> str:
    """The study text with its robot list narrowed to the pair (a literal rewrite, no new prose)."""
    out = text.replace('"r1"|"r2"|"r3"', '"r1"|"r2"').replace('(r1, r2, r3)', '(r1, r2)')
    assert 'r3' not in out and '세 로봇' not in out, 'a study text still names three robots'
    return out


#: Channel slots. ``no_comm`` is the study's own closed-channel text. ``peer_nl`` keeps the study's
#: recipients / budget / separation text and drops every language word of the ``peer_ko`` slot.
PAIR_CHANNEL_SLOTS = {
    'no_comm': pk.KO_CHANNEL_SLOTS['no_comm'],
    'peer_nl': {
        'headline': '동료에게 자연어로 관측·의도·질문·요청·양보·정정을 전달할 수 있습니다. 메시지의 언어는 '
                    '정해져 있지 않습니다(영어도 됩니다).',
        'form': '본문은 자유 문장 한 개입니다.',
        'recipients': pk.KO_CHANNEL_SLOTS['peer_ko']['recipients'],
        'budget': pk.KO_CHANNEL_SLOTS['peer_ko']['budget'],
        'separation': pk.KO_CHANNEL_SLOTS['peer_ko']['separation'],
    },
}

#: The ``messages`` schema of the open channel: the study's text with the pair robot list and without
#: the ``"한국어 발화"`` requirement.
KO_PAIR_MESSAGES = '''
- messages: 보낼 발화 목록입니다. 각 항목은
  {"recipients": ["r1"|"r2", ...], "text": "자유 문장 한 개", "reply_to": message_id 또는 null}
  입니다. 보낼 말이 없으면 빈 배열 []을 씁니다. text는 __CHARS__자 이내로 씁니다.
  reply_to에는 당신이 실제로 받은 메시지의 message_id만 씁니다.'''

#: Literal tokens stay literal (this is the study's literal list); no message-language rule.
KO_PAIR_LITERALS = '''
표기: 메시지 본문의 언어는 정해져 있지 않습니다. 로봇 ID(r1, r2), 구역 문자(A, B, C),
order_id와 item_id, passage ID, 물건 kind, role 이름, JSON 키와 값(null, true, false),
enum 값은 번역하거나 바꾸지 않고 주어진 그대로 씁니다.'''
assert 'r3' not in KO_PAIR_MESSAGES and 'r3' not in KO_PAIR_LITERALS and '한국어' not in KO_PAIR_MESSAGES
#: Blocks reused unchanged: they say nothing about the number of robots or about a language.
_REUSED = {'output': pk.KO_OUTPUT_HEAD, 'sources': pk.KO_SOURCES, 'separation': pk.KO_SEPARATION,
           'messages_none': pk.KO_MESSAGES_NONE}


def study_spec(condition: str) -> str:
    """The sealed study's condition name for a pair arm (the single translation point)."""
    if condition not in STUDY_SPEC:
        raise zp.ProtocolError(f'{condition!r} is not a pair LLM condition {PAIR_CONDITIONS}')
    return STUDY_SPEC[condition]


def _channel_block(condition: str, spec, *, cap_window=None, cap_robot=None) -> str:
    slots = PAIR_CHANNEL_SLOTS[condition]
    values = {'cap_window': spec.max_window_utterances if cap_window is None else cap_window,
              'cap_robot': spec.max_robot_utterances if cap_robot is None else cap_robot}
    return pk.KO_CHANNEL_TEMPLATE.format(**{name: text.format(**values) for name, text in slots.items()})


def partner_of(rid: str) -> str:
    if rid not in PAIR_ROBOTS:
        raise zp.ProtocolError(f'unknown pair robot {rid!r}; the pair is {PAIR_ROBOTS}')
    return next(r for r in PAIR_ROBOTS if r != rid)


def prompt_parts(condition: str, rid: str, *, cap_window=None, cap_robot=None) -> dict:
    """The system prompt as named blocks (same names and order as the study prompt)."""
    if condition not in PAIR_CONDITIONS:
        raise zp.ProtocolError(f'{condition!r} is not a pair LLM condition {PAIR_CONDITIONS}; '
                               'the rule arm makes no model call')
    spec = zp.spec(study_spec(condition))
    partner = partner_of(rid)
    head = KO_PAIR_HEAD.format(rid=rid, role=PAIR_ROLES[rid], partner=partner,
                               partner_role=PAIR_ROLES[partner])
    return {'head': head,
            'channel': _channel_block(condition, spec, cap_window=cap_window, cap_robot=cap_robot),
            'behaviour': KO_PAIR_BEHAVIOUR,
            'output': _REUSED['output'].strip('\n'),
            'action': KO_PAIR_ACTION,
            'sources': _REUSED['sources'].strip('\n'),
            'messages': (KO_PAIR_MESSAGES if spec.channel_open else _REUSED['messages_none']).strip('\n'),
            'separation': _REUSED['separation'].strip('\n'),
            'language': KO_PAIR_LITERALS.strip('\n')}


def system_prompt(condition: str, rid: str, *, cap_window=None, cap_robot=None) -> str:
    parts = prompt_parts(condition, rid, cap_window=cap_window, cap_robot=cap_robot)
    text = '\n\n'.join(parts[name] for name in pk.PROMPT_BLOCKS)
    return text


def fixed_prompt_reference_tokens() -> int:
    """Billed fixed-prompt size: the largest pair system prompt (``FIXED_PROMPT_POLICY``).

    The ``peer_nl`` prompt is longer than the ``no_comm`` one (message schema); billing
    the actual length would charge that description as if it were dialogue, so every arm is billed the
    same fixed size and only the variable part (payload, inbox, window) is billed as counted.
    """
    return max(pk.count_tokens(system_prompt(name, rid)) for name in PAIR_CONDITIONS for rid in PAIR_ROBOTS)


def prompt_template_sha256() -> str:
    """Digest of every arm's system prompt text (the prompt template identity of the bundle)."""
    value = {'version': PROMPT_VERSION,
             'prompts': {name: {rid: system_prompt(name, rid) for rid in PAIR_ROBOTS}
                         for name in PAIR_CONDITIONS}}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


__all__ = ['PROMPT_VERSION', 'PAIR_ROBOTS', 'PAIR_ROLES', 'PAIR_CONDITIONS', 'STUDY_SPEC', 'RENDEZVOUS_S',
           'study_spec', 'partner_of',
           'prompt_parts', 'system_prompt', 'fixed_prompt_reference_tokens', 'prompt_template_sha256']
