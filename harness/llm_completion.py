"""Shared LLM completion admission, independent of study/runtime modules.

The installed subscription proxy preserves MAX_TOKENS as length but rewrites
other upstream finish reasons (including SAFETY) to stop. A proxy stop is NOT
verification of upstream STOP. Keep this uncertainty in every pilot manifest.
"""
from __future__ import annotations

import copy
import json
from types import MappingProxyType

# Keep the recorded R9 policy ID: moving code does not change its semantics.
COMPLETION_POLICY = 'ugrp.zone_completion.proxy_stop_and_valid_reply.v1'
PROXY_COMPLETION_LIMITATION = {
    'finish_reason_source': 'proxy_response',
    'upstream_finish_reason_verified': False,
    'proxy_mapping': 'MAX_TOKENS -> length; other reasons including SAFETY -> stop',
    'undetectable_case': 'masked upstream failure with complete valid JSON and no remaining failure signal',
    'success_scope': 'proxy stop + valid study reply, not verified upstream STOP or physical success',
}
REPLY_FIELDS = frozenset(('request_id', 'action', 'decision_sources', 'messages'))


def generated_utterances(raw) -> int:
    """Frozen malformed-reply cost rule, shared with the offline pipeline.

    Count JSON messages, or literal recipients keys in unparseable text. This
    bills produced utterances without accepting or repairing any of them.
    """
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except ValueError:
            return raw.count('"recipients"')
    if isinstance(value, dict) and isinstance(value.get('messages'), list):
        return len(value['messages'])
    return 0


def completion_record(value):
    """JSON-owned copy, including a frozen CallReply's completion metadata."""
    if value is None:
        return None
    return {k: list(v) if isinstance(v, tuple) else copy.deepcopy(v) for k, v in value.items()}


def freeze_completion(value):
    if value is None:
        return None
    return MappingProxyType({k: tuple(v) if isinstance(v, list) else v
                             for k, v in completion_record(value).items()})


def assess_completion(body, *, study_json=False):
    reasons = []
    choice = {}
    choices = body.get('choices') if isinstance(body, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        reasons.append('missing_or_ambiguous_choice')
    else:
        choice = choices[0]
    raw_reason = choice.get('finish_reason')
    reason = raw_reason if isinstance(raw_reason, str) else None
    if reason != 'stop':
        reasons.append('finish_reason_not_stop')
    message = choice.get('message')
    message = message if isinstance(message, dict) else {}
    text = message.get('content')
    if not isinstance(text, str) or not text.strip():
        reasons.append('empty_or_missing_content')
    # Optional failure signals are not used to infer success. Never repair a
    # refusal/tool response into a text decision just because it says stop.
    for name in ('refusal', 'tool_calls', 'function_call'):
        if message.get(name):
            reasons.append('message_' + name)
    if isinstance(body, dict) and body.get('error'):
        reasons.append('response_error')
    upstream = []

    def signals(node):
        if not isinstance(node, dict):
            return
        for name in ('finishReason', 'upstream_finish_reason'):
            if name in node:
                reported = node[name]
                upstream.append(reported if isinstance(reported, str) else 'invalid')
                if reported not in ('STOP', 'stop'):
                    reasons.append('reported_upstream_non_stop')
        feedback = node.get('promptFeedback') or node.get('prompt_feedback')
        if isinstance(feedback, dict) and (feedback.get('blockReason') or feedback.get('block_reason')):
            reasons.append('prompt_blocked')
        ratings = node.get('safetyRatings') or node.get('safety_ratings')
        if isinstance(ratings, list) and any(isinstance(r, dict) and r.get('blocked') is True for r in ratings):
            reasons.append('safety_blocked')

    for node in (body, choice, message):
        signals(node)
    if isinstance(body, dict):
        response = body.get('response', body)
        signals(response)
        if isinstance(response, dict) and isinstance(response.get('candidates'), list):
            for candidate in response['candidates']:
                signals(candidate)
    if study_json and isinstance(text, str) and text.strip():
        try:
            value = json.loads(text)  # complete JSON only; no fenced/truncated salvage
            if not isinstance(value, dict) or set(value) != REPLY_FIELDS:
                reasons.append('study_reply_fields_missing_or_extra')
        except (ValueError, TypeError):
            reasons.append('study_reply_incomplete_or_non_json')
    return {'policy': COMPLETION_POLICY, 'finish_reason': reason,
            'finish_reason_source': 'proxy_response', 'upstream_finish_reason_verified': False,
            'reported_upstream_finish_reasons': upstream,
            'normal_completion': not reasons, 'rejection_reasons': sorted(set(reasons))}


def normal_completion(completion):
    """Fail closed for legacy/missing/mismatched records, even status='ok'."""
    return (isinstance(completion, (dict, MappingProxyType))
            and completion.get('policy') == COMPLETION_POLICY
            and completion.get('finish_reason') == 'stop'
            and completion.get('normal_completion') is True
            and completion.get('rejection_reasons') in ([], ()))


def successful_call(call):
    return call.get('status') == 'ok' and normal_completion((call.get('cost_terms') or {}).get('completion'))


def completion_aggregate(calls):
    reasons = {}
    unknown = rejected = 0
    for call in calls:
        completion = (call.get('cost_terms') or {}).get('completion')
        reason = completion.get('finish_reason') if isinstance(completion, dict) else None
        label = reason if isinstance(reason, str) else 'unknown'
        reasons[label] = reasons.get(label, 0) + 1
        unknown += completion is None
        rejected += completion is not None and not normal_completion(completion)
    return {'policy': COMPLETION_POLICY, 'finish_reasons': reasons,
            'successful_calls': sum(successful_call(c) for c in calls),
            'rejected_completions': rejected, 'completion_unknown_calls': unknown,
            'upstream_finish_reason_verified_calls': 0,
            'limitation': dict(PROXY_COMPLETION_LIMITATION)}
