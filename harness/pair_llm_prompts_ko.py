"""Korean system prompt of the two-robot pair-carry LLM layer (viability test).

The zone-study prompt (``harness.zone_study_prompts_ko``) is written for THREE
robots: its role line says "세 로봇 r1, r2, r3", its language block lists r3 and its
behaviour block tells a robot to ``wait`` when unsafe. The pair carry has two
robots and a destructive ``wait``/``release`` (they abort the carry), so this
module builds a pair-specific prompt and REUSES every block that is count-agnostic
(output head, decision sources, separation, channel block, no-message block).

Two blocks are derived from the study constants by replacing the robot list, so
the Korean rule stays the study's own text (``KO_LANGUAGE``) and the language check
stays ``zone_study_protocol.language_report`` (hangul ratio >= 0.9, a non-Korean
message is delivered and flagged, never blocked).

Everything in the prompt is identical in the ``no_comm`` and ``peer_ko`` arms
except the channel / messages / language blocks, as in the study.
"""
from __future__ import annotations

import hashlib
import json

from harness import zone_study_prompts_ko as pk
from harness import zone_study_protocol as zp

PROMPT_VERSION = 'ugrp.pair_llm_prompts_ko.v1'
PAIR_ROBOTS = ('r1', 'r2')
PAIR_ROLES = {'r1': 'end_neg', 'r2': 'end_pos'}
PAIR_CONDITIONS = ('no_comm', 'peer_ko')
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
현재 상황의 근거는 자기 wrist RGB 1장, own_commands, own_belief와
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
각 로봇은 자기 행동을 스스로 결정합니다.''' % {'window': RENDEZVOUS_S}

KO_PAIR_ACTION = '''- action: 당신 자신의 행동 하나입니다. 다음 중 하나를 씁니다.
  {"kind": "claim", "order_id": order_sheet의 order_id, "role": order_sheet.kinds의 roles 중 당신의 역할 이름,
   "destination_zone": order_sheet의 destination_zone}
  {"kind": "continue"}
  {"kind": "wait"}
  {"kind": "release", "order_id": 놓아줄 order_id}'''


def _pair_only(text: str) -> str:
    """The study text with its robot list narrowed to the pair (a literal rewrite, no new prose)."""
    out = text.replace('"r1"|"r2"|"r3"', '"r1"|"r2"').replace('(r1, r2, r3)', '(r1, r2)')
    assert 'r3' not in out and '세 로봇' not in out, 'a study text still names three robots'
    return out


#: The study's own Korean-language rule and message schema, narrowed to two robots.
KO_PAIR_LANGUAGE = _pair_only(pk.KO_LANGUAGE)
KO_PAIR_MESSAGES = _pair_only(pk.KO_MESSAGES_KO).replace('__CHARS__', str(zp.PROMPT_TEXT_CHARS))
#: Blocks reused unchanged: they say nothing about the number of robots.
_REUSED = {'output': pk.KO_OUTPUT_HEAD, 'sources': pk.KO_SOURCES, 'separation': pk.KO_SEPARATION,
           'messages_none': pk.KO_MESSAGES_NONE}


def partner_of(rid: str) -> str:
    if rid not in PAIR_ROBOTS:
        raise zp.ProtocolError(f'unknown pair robot {rid!r}; the pair is {PAIR_ROBOTS}')
    return next(r for r in PAIR_ROBOTS if r != rid)


def prompt_parts(condition: str, rid: str, *, cap_window=None, cap_robot=None) -> dict:
    """The system prompt as named blocks (same names and order as the study prompt)."""
    if condition not in PAIR_CONDITIONS:
        raise zp.ProtocolError(f'{condition!r} is not a pair LLM condition {PAIR_CONDITIONS}; '
                               'the rule arm makes no model call')
    spec = zp.spec(condition)
    partner = partner_of(rid)
    head = KO_PAIR_HEAD.format(rid=rid, role=PAIR_ROLES[rid], partner=partner,
                               partner_role=PAIR_ROLES[partner])
    return {'head': head,
            'channel': pk._channel_block(condition, 'peer', spec=spec, cap_window=cap_window,
                                         cap_robot=cap_robot),
            'behaviour': KO_PAIR_BEHAVIOUR,
            'output': _REUSED['output'].strip('\n'),
            'action': KO_PAIR_ACTION,
            'sources': _REUSED['sources'].strip('\n'),
            'messages': (KO_PAIR_MESSAGES if spec.channel_open else _REUSED['messages_none']).strip('\n'),
            'separation': _REUSED['separation'].strip('\n'),
            'language': KO_PAIR_LANGUAGE.strip('\n')}


def system_prompt(condition: str, rid: str, *, cap_window=None, cap_robot=None) -> str:
    parts = prompt_parts(condition, rid, cap_window=cap_window, cap_robot=cap_robot)
    text = '\n\n'.join(parts[name] for name in pk.PROMPT_BLOCKS)
    return text


def fixed_prompt_reference_tokens() -> int:
    """Billed fixed-prompt size: the largest pair system prompt (``FIXED_PROMPT_POLICY``).

    The ``peer_ko`` prompt is longer than the ``no_comm`` one (message schema, language block); billing
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


__all__ = ['PROMPT_VERSION', 'PAIR_ROBOTS', 'PAIR_ROLES', 'PAIR_CONDITIONS', 'RENDEZVOUS_S', 'partner_of',
           'prompt_parts', 'system_prompt', 'fixed_prompt_reference_tokens', 'prompt_template_sha256']
