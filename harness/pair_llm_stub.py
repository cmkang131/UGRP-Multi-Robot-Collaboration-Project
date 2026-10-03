"""Stub models for the pair LLM plumbing tests. NO network, NO provider, NO key.

A stub is a function ``respond(system_text, user_text) -> reply text`` behind
``harness.zone_send_ledger.FixtureWire``, so every stub reply still travels the real chain
(``GeminiProxyCompleter`` -> ``SendLedger`` -> wire -> ``finish_call``). The stub sees exactly the bytes the
proxy would see (the system text and the user JSON), never the host.

``cooperative`` is a deterministic script, not a model: the first call of a robot claims the order sheet's
pair order with its own fixed role, every later call says ``continue``; in ``peer_ko`` the first call also
greets the partner in Korean and the first call after a delivered message answers it. It is used to prove
plumbing (routing, gating, ledger, cost, language flags) and is never a result about any model.
``scripted`` replays an explicit per-(robot, call index) table for the failure-mode tests.
"""
from __future__ import annotations

import json

from harness.pair_llm_prompts_ko import PAIR_ROBOTS, PAIR_ROLES, partner_of

STUB_MODEL_ID = 'stub-pair-llm-v1'
STUB_URL = 'stub://pair-llm-no-network'
STUB_SETTINGS = {'model': STUB_MODEL_ID, 'url': STUB_URL, 'max_tokens': 1400, 'temperature': 0.0,
                 'reasoning_effort': 'none', 'timeout': 45.0}


def reply_json(request_id, action, messages=(), sources=('order_sheet',)) -> str:
    return json.dumps({'request_id': request_id, 'action': action, 'decision_sources': list(sources),
                       'messages': [dict(m) for m in messages]}, ensure_ascii=False)


def claim_action(rid, order) -> dict:
    return {'kind': 'claim', 'order_id': order['order_id'], 'role': PAIR_ROLES[rid],
            'destination_zone': order['destination_zone']}


def greeting(rid, order) -> str:
    return (f'{order["order_id"]}를 {order["destination_zone"]} 구역으로 함께 옮기겠습니다. '
            f'저는 {PAIR_ROLES[rid]} 쪽을 맡겠습니다.')


def answer(rid) -> str:
    return f'알겠습니다. {partner_of(rid)}와 같은 시간에 시작하겠습니다.'


class StubModel:
    """``respond`` callable with a per-robot call counter and a log of what it saw (the wire text only)."""

    def __init__(self, policy):
        self.policy = policy
        self.calls = {r: 0 for r in PAIR_ROBOTS}
        self.seen = []

    def __call__(self, system_text, user_text):
        body = json.loads(user_text)
        rid = body['robot_id']
        index = self.calls[rid]
        self.calls[rid] += 1
        self.seen.append({'robot_id': rid, 'index': index, 'request_id': body['request_id'],
                          'keys': sorted(body), 'inbox': len(body.get('inbox', ()))})
        reply = self.policy(rid, index, body, system_text)
        if isinstance(reply, str):
            return reply
        action, messages = reply
        sources = ['order_sheet'] + (['message'] if body.get('inbox') else [])
        return reply_json(body['request_id'], action, messages, sources)


def cooperative(rid, index, body, system_text):
    order = body['order_sheet']['orders'][0]
    open_channel = body['channel']['can_send_to'] != []
    messages = []
    if open_channel:
        partner = partner_of(rid)
        if index == 0:
            messages.append({'recipients': [partner], 'reply_to': None, 'text': greeting(rid, order)})
        elif body.get('inbox') and index == 1:
            messages.append({'recipients': [partner], 'reply_to': body['inbox'][-1]['message_id'],
                             'text': answer(rid)})
    action = claim_action(rid, order) if index == 0 else {'kind': 'continue'}
    return action, messages


def scripted(table, default=cooperative):
    """``table[(robot_id, call_index)]`` is a reply text, an ``(action, messages)`` pair or a callable."""
    def policy(rid, index, body, system_text):
        item = table.get((rid, index))
        if item is None:
            return default(rid, index, body, system_text)
        return item(rid, index, body, system_text) if callable(item) else item
    return policy


def cooperative_model() -> StubModel:
    return StubModel(cooperative)


__all__ = ['STUB_MODEL_ID', 'STUB_URL', 'STUB_SETTINGS', 'reply_json', 'claim_action', 'greeting', 'answer',
           'StubModel', 'cooperative', 'scripted', 'cooperative_model']
