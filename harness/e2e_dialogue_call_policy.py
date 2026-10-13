"""Opt-in event admission and bounded prompts; no evaluator or peer-private input."""
import copy
import hashlib
import json
import re

OPTION = 'event_v1'
VERSIONS = {f'e2e18-v{v}': v + 9 for v in range(352, 356)}
PARAMETERS = dict(observation_interval_sim_s=15., history_n=8, dialogue_n=6,
                  prompt_utf8_bytes=14000, prompt_text_tokens=4500)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def reports(body):
    rows = list(body.get('peer_reports') or [])
    pinned = body.get('active_route_report')
    return ([pinned] if pinned else []) + rows


# Only recognized filler is discarded. Unknown language/detail is retained;
# this is an auditable lexical filter, not an LLM claim of semantic equivalence.
FILLER = set('i am we are the a an my our your is it and for to of on in at with still '
             'currently now continue continuing holding hold waiting wait awaiting ready '
             'protocol updates update state current stabilize stabilise stabilizing '
             'maintaining position observation observing unchanged new information '
             'understood acknowledged okay ok thanks thank you confirm confirmed '
             'will keep remain remaining stable monitoring own camera view'.split())
DANGER = re.compile(r'\b(?:please|must) (?:wait|hold)\b|\b(slipp\w*|dropp\w*|danger|stop|stuck|blocked|uncertain|lost)\b|미끄|낙하|위험|정지|이탈', re.I)


def fact(report):
    body = report.get('body') or {}
    if body.get('contract'):
        return ('protocol', digest(body['contract']))
    if report.get('encoding') == 'schema':
        value = {k: v for k, v in body.items() if k not in ('observed_at_sim_s', 'reply_to')}
        return ('danger' if value.get('state') == 'blocked' else 'fact', digest(value))
    text = body.get('text', '')
    if re.fullmatch(r'(?:i have )?no new (?:information|observations?|updates?)[.! ]*', text.lower().strip()):
        return None
    words = re.findall(r'[\w]+', text.lower())
    if not words or all(w in FILLER for w in words):
        return None
    # Preserve negation, numbers and directions. Do not infer GO from prose:
    # accepted protocol references come exclusively from dialogue.view.
    value = ' '.join(w for w in words if w not in FILLER)
    return ('danger' if DANGER.search(text) else 'fact', value)


class Policy:
    def __init__(self):
        self.last = {}
        self.events = []
        self.last_message = {}
        self.sink = None

    def record(self, row):
        self.events.append(row)
        if self.sink is not None:
            self.sink(row)

    def decide(self, actor, now, own, protocol, peer_reports, *, trigger='report'):
        from harness.e2e_own_inputs import scan
        scan(own); scan(protocol); scan(peer_reports)
        own_hash, protocol_hash = digest(own), digest(protocol)
        # Compare fact content, not envelope IDs/ages. Alternating previously
        # seen observations must not create a new fact each turn. Latest danger
        # transitions remain urgent even when that warning occurred earlier.
        facts = set()
        latest = {}
        for report in peer_reports:
            value = fact(report)
            if value is not None:
                facts.add((report['sender'], *value))
                latest[report['sender']] = value
        old = self.last.get(actor)
        changed_facts = facts - (old['facts'] if old else set())
        urgent = any(v[1] in ('protocol', 'danger') for v in changed_facts)
        urgent = urgent or any(v[0] == 'danger' and (old is None or old['latest'].get(k) != v)
                               for k, v in latest.items())
        if old is None:
            reason = 'initial_state'
        elif protocol_hash != old['protocol_hash'] or urgent:
            reason = 'protocol_or_safety_event'
        elif own_hash == old['own_hash'] and not changed_facts:
            reason = 'same_state_no_new_fact'
        elif now - old['at'] < PARAMETERS['observation_interval_sim_s']:
            reason = 'observation_min_interval'
        else:
            reason = 'own_state_changed' if own_hash != old['own_hash'] else 'partner_new_fact'
        admitted = reason not in ('same_state_no_new_fact', 'observation_min_interval')
        due = old['at'] + PARAMETERS['observation_interval_sim_s'] if reason == 'observation_min_interval' else None
        row = dict(actor=actor, sim_s=now, trigger=trigger, admitted=admitted, reason=reason,
                   own_summary_sha256=own_hash, protocol_sha256=protocol_hash, retry_at_sim_s=due)
        self.record(row)
        if admitted:
            self.last[actor] = dict(at=now, own_hash=own_hash, protocol_hash=protocol_hash, facts=facts, latest=latest)
        return row



    def allow_message(self, actor, now, action, message):
        value = fact(dict(body={'contract': message['contract']} if message.get('contract') else
                          message.get('message') or {'text': message.get('text', '')},
                          encoding='schema' if 'message' in message else 'free_en'))
        protocol = action.get('kind') in ('claim', 'approve_route', 'route_vote') or bool(message.get('contract'))
        explicit_wait = bool(re.search(r'\b(?:please|must) (?:wait|hold)\b|대기해|기다려', message.get('text', ''), re.I))
        old = self.last_message.get(actor)
        if protocol or explicit_wait or (value and value[0] == 'danger' and (old is None or old['fact'] != value)):
            reason = 'protocol_or_safety_message'
        elif value is None or (old and old['fact'] == value):
            reason = 'repeated_observation_message'
        elif old and now - old['at'] < PARAMETERS['observation_interval_sim_s']:
            reason = 'observation_message_min_interval'
        else:
            reason = 'new_observation_message'
        admitted = reason in ('protocol_or_safety_message', 'new_observation_message')
        self.record(dict(actor=actor, sim_s=now, event='outgoing_message',
                                admitted=admitted, reason=reason))
        return admitted

    def message_sent(self, actor, now, message):
        value = fact(dict(body={'contract': message['contract']} if message.get('contract') else
                          message.get('message') or {'text': message.get('text', '')},
                          encoding='schema' if 'message' in message else 'free_en'))
        self.last_message[actor] = dict(at=now, fact=value)


def compact(body, system):
    """Bound the actual model input; full raw/captured context is untouched."""
    from harness.zone_study_prompts_ko import count_tokens
    b = copy.deepcopy(body)
    window = b.get('dialogue_window')
    if window is not None:
        if 'sent' in window:
            window['sent_count'] = len(window.pop('sent'))
    for key in ('own_command_history', 'own_decision_log'):
        if key in b:
            b[key] = b[key][-8:]
    all_reports = reports(b)
    b.pop('active_route_report', None)
    b['peer_reports'] = all_reports[-6:]
    proposal = b.get('dialogue', {}).get('proposal_message_id')
    # An unapproved route is protocol evidence, not a second dialogue history.
    if proposal and not b['dialogue'].get('approved'):
        pinned = next((r for r in all_reports if r['message_id'] == proposal), None)
        if pinned and pinned not in b['peer_reports']:
            b['active_route_report'] = pinned
    for r in reports(b):
        r['age_sim_s'] = round(b['sim_time_s'] - r['created_at_sim_s'], 3)
        for key in ('schema', 'recipients'):
            r.pop(key, None)
    # Syntax examples duplicate the actual filtered contract/current step.
    b.pop('reply_format_example', None)
    b.pop('decision_feedback', None)  # rejection reason is already in decision log
    b.pop('current_protocol_step', None)
    b.pop('route_contract_example', None)  # retained once in message_element.contract
    if b.get('dialogue', {}).get('approved'):
        b['own_route_proposal'] = None
    if b.get('own_protocol_observation') and b.get('own_state_summary'):
        b['own_state_summary'].pop('grip', None)
        b['own_state_summary'].pop('alignment', None)
    b['dialogue_call_policy'] = OPTION
    system = system.replace('Follow reply_format_example for the JSON structure and choose your action from current evidence.',
                            'Choose your action from current evidence.')
    system = system.replace('route_contract_example', 'action_message_contract.message_element.contract')
    system = system.replace('decision_feedback explains your last rejection.', 'rejected decisions include their reason.')
    system = system.replace('Follow current_protocol_step using the actual current evidence.', 'Use the actual current protocol evidence.')
    system += (' Send no observation-only acknowledgement or repeated status. Empty messages is valid. '
               'peer_reports is the latest six messages with age_sim_s; active_route_report, when present, '
               'is the older actually received proposal still awaiting review. No message is a current vote unless dialogue says so.')
    def size():
        user = json.dumps(b, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return len((system + user).encode()), count_tokens(system) + count_tokens(user)
    # Prefer recent dialogue/protocol over optional old history, then remove
    # oldest non-proposal dialogue. Never truncate a route/identifier or system rule.
    while True:
        nbytes, ntokens = size()
        if nbytes <= PARAMETERS['prompt_utf8_bytes'] and ntokens <= PARAMETERS['prompt_text_tokens']:
            break
        trimmed = False
        for key in ('own_command_history', 'own_decision_log'):
            if b.get(key):
                b[key].pop(0); trimmed = True; break
        if not trimmed:
            for i, r in enumerate(b['peer_reports']):
                if r['message_id'] != proposal:
                    b['peer_reports'].pop(i); trimmed = True; break
        if not trimmed:
            from harness.zone_study_contract import ContractViolation
            raise ContractViolation('EVENT_PROMPT_CAP_REQUIRED_PROTOCOL_TOO_LARGE')
    return b, system



def check_prompt(system, user):
    from harness.zone_study_prompts_ko import count_tokens
    if (len((system + user).encode()) > PARAMETERS['prompt_utf8_bytes']
            or count_tokens(system) + count_tokens(user) > PARAMETERS['prompt_text_tokens']):
        from harness.zone_study_contract import ContractViolation
        raise ContractViolation('EVENT_PROMPT_CAP_EXCEEDED')


def budget_progress(budget, cohort_key, sim_s, output):
    from pathlib import Path
    value = token_health(budget.usage(cohort_key), sim_s)
    if value['warning_before_600']:
        path = Path(output) / 'TOKEN_RATE_WARNING.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(sim_s=sim_s, **value), indent=2) + '\n')
        temporary.replace(path)
    return value


def token_health(usage, sim_s):
    """Budget-accounted tokens include conservative charges for unknown usage."""
    total = usage['charged_tokens']; cap = usage['token_cap']
    rate = total / sim_s if sim_s > 0 else None
    eta = (max(sim_s, cap / rate) if rate and cap is not None else None)
    return dict(cumulative_tokens=total, known_tokens=usage['known_tokens'],
                usage_unknown_requests=usage['usage_unknown_requests'], token_cap=cap,
                tokens_per_sim_s=rate, cap_expected_sim_s=eta,
                warning_before_600=eta is not None and eta < 600.,
                basis='charged_tokens / elapsed SIM; unknown usage retains budget charge')


def compose(bundle, option='off'):
    if option == 'off': return ()
    parent = bundle['execution_bundle_id']; version = VERSIONS.get(parent)
    if option != OPTION or version is None: raise ValueError('EVENT_V1_REQUIRES_V352_TO_V355')
    bundle['dialogue_call_policy_parent'] = parent
    bundle['e2e_options']['dialogue_call_policy'] = option
    bundle['dialogue_call_policy_parameters'] = dict(PARAMETERS)
    bundle.update(execution_bundle_id=f'e2e18-v{version}', schema=f'ugrp.e2e_ownmap_live.v{version}',
                  workflow_version=f'7.{version-107}.0')
    return ('harness/e2e_dialogue_call_policy.py', f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    old = copy.deepcopy(bundle); parent = old.get('dialogue_call_policy_parent')
    if (VERSIONS.get(parent) is None or old['execution_bundle_id'] != f'e2e18-v{VERSIONS[parent]}'
            or old['e2e_options'].get('dialogue_call_policy') != OPTION
            or old.get('dialogue_call_policy_parameters') != PARAMETERS):
        raise ValueError('REGISTERED_DIALOGUE_CALL_POLICY_REQUIRED')
    old['execution_bundle_id'] = old.pop('dialogue_call_policy_parent')
    old.pop('dialogue_call_policy_parameters'); old['e2e_options'].pop('dialogue_call_policy')
    return old
