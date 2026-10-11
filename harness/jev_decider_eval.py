"""Offline evaluation of Jev / Gemma / a rule as the ACTION decider on the frozen suite (2026-10-11).

No simulation. Same text state and same option list for every policy. Jev is called through its choice API
(request shape as ``harness.jev_motion.jev_request``); Gemma through OpenRouter (paid google/gemma-4-31b-it, DeepInfra pinned).
Keys are read from the macOS keychain into memory only and never written, logged or put in argv.
Agreement with Gemma is a descriptive number only; the label sets in ``jev_decider_suite`` are the criterion.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harness.jev_decider_suite import BUDGET_XY_M, EPOCH_WINDOW_S, FAMILIES, structural_admissible

JEV_URL = 'https://api.typesafe.ai/v1/systemone'
JEV_MODEL = 'jev-1.13.0'
GEMMA_MODEL = 'google/gemma-4-31b-it'
GEMMA_ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
CALL_CAP = 1500
REPRESENTATIONS = ('raw', 'semantic')

OPTION_TEXT = {
    'continue': 'Do nothing new this turn: keep exploring/mapping or hold position and wait. Use it when evidence is missing or the next protocol step is not available to you.',
    'claim': 'Claim order-5 for your own role (only after the route is approved).',
    'approve_route': 'Approve the received route proposal (only robot r2, only a proposal actually delivered to you).',
    'GO': 'Send GO for the current epoch key: you state that your own grip is ready (needs your own RGB to show the grip).',
    'ACK': 'Send ACK: you confirm the peer GO you can see (needs your own GO already sent and the peer GO visible).',
    'set_down': 'Put the beam down here for an own-RGB position re-look before carrying on.',
    'regrasp': 'Pick the beam up again now (new grip epoch) and continue the carry.',
    'look_again': 'Do one more own-RGB re-look from the set-down position before regrasping.',
}
INSTRUCTIONS = {
    'dialogue': ('You are one of two robots (r1=end_neg, r2=end_pos) carrying one long beam to destination B; r3 is idle. '
        'Choose the single next protocol action from the options. Use only the state: your own wrist RGB summary, your own commands, '
        'your own map summary and peer reports that were actually delivered. An estimate or issued command is not success. '
        'Until a route exists, continue while your own camera mapper explores. r1 proposes a route; r2 must have received that exact '
        'proposal before approve_route; both claim only after approval. GO and ACK use the exact current epoch key only, while it is '
        'open; GO requires your own RGB supporting the grip; ACK requires your GO and the current peer GO. Never reuse a previous '
        'epoch or repeat a vote already sent. When unsure, continue.'),
    'carry': ('You are carrying one end of a long beam with a partner along a planned route and are at a carry stop. '
        'Choose continue (carry the next segment) or set_down (put the beam down for an own-RGB position re-look). A set-down is a '
        'verified re-observation, never an unconditional release: use it only when a re-look boundary reason is listed. Use only the state.'),
    'postlook': ('You have set the beam down and just did an own-RGB position re-look. Choose regrasp (pick up and continue) if the re-look '
        'gave a usable position fix; look_again only if the fix failed and a re-look is still allowed at this stop. Use only the state.'),
}
SEMANTIC_NOTE = (' The state lists contract predicates computed by code from the same observations; peer reports are quoted verbatim.')


def options_for(family):
    return {k: OPTION_TEXT[k] for k in FAMILIES[family]}


def _sigma(state):
    return state['own_map']['pose_sigma_m']


def raw_state(case_state, family):
    """Raw-ish fields as in the E2E request (no derived predicates, no categorical grip flag)."""
    s = {k: v for k, v in case_state.items() if k != 'own_rgb_grip'}
    return s


def semantic_state(case_state, family):
    s = case_state
    peers = [dict(sender=p['sender'], text=p['text']) for p in s['peer_reports']]
    if family == 'carry':
        return dict(robot=s['robot_id'], role=s['role'], boundary_reasons_listed=s['carry_stop']['boundary_reasons'],
                    a_relook_boundary_is_listed=bool(s['carry_stop']['boundary_reasons']), segment=s['carry_stop']['segment'],
                    of_segments=s['carry_stop']['of_segments'], own_rgb_summary=s['own_rgb_summary'], peer_reports=peers)
    if family == 'postlook':
        r = s['relook_result']
        return dict(robot=s['robot_id'], own_rgb_fix=r['own_rgb_fix'], fix_error_estimate_m=r['pose_sigma_m'], fix_budget_m=r['dr_budget_m'],
                    fix_within_budget=r['pose_sigma_m'] <= r['dr_budget_m'], relooks_left_at_this_stop=r['relooks_left_this_stop'],
                    note=r['note'], peer_reports=peers)
    d = s['dialogue']
    age = s['epoch_age_s']
    grip = s.get('own_rgb_grip', 'unknown')
    return dict(robot=s['robot_id'], role=s['role'], is_carrier=s['role'] != 'idle', may_approve_routes=s['role'] == 'end_pos',
                can_send_messages=bool(s['can_send_to']), B_seen_in_own_rgb=s['own_map']['B_seen_in_own_rgb'],
                own_route_ready_to_propose=s['own_route_proposal'] is not None,
                route_proposal_delivered=d['proposal_message_id'] is not None, route_approved=d['approved'],
                own_claim_made=d['own_claim'], epoch_key_open=d['key'] is not None, epoch_seconds_since_open=age,
                epoch_window_s=EPOCH_WINDOW_S, epoch_window_open=bool(d['key'] is not None and age is not None and age <= EPOCH_WINDOW_S),
                own_GO_sent=d['own_go_sent'], peer_GO_visible=d['peer_go_ref'] is not None, own_ACK_sent=d['own_ack_sent'],
                transport_already_admitted=d['transport_admitted'],
                own_rgb_supports_grip={'holding': 'yes', 'not_visible': 'no (beam not visible)', 'slipping': 'no (grip slipping)',
                                       'none': 'not carrying', 'unknown': 'unknown'}[grip],
                own_rgb_summary=s['own_rgb_summary'], own_commands=s['own_command_history'], peer_reports=peers)


def render(case, representation):
    fam = case['family']
    return (raw_state if representation == 'raw' else semantic_state)(case['state'], fam)


def instructions(family, representation):
    return INSTRUCTIONS[family] + (SEMANTIC_NOTE if representation == 'semantic' else '')


# ---------------------------------------------------------------------------------------- rule baseline
def rule_action(state, family):
    """Structural rule that ignores peer text (so it cannot follow message-sensitivity pairs by design)."""
    adm = structural_admissible(state, family)
    order = {'dialogue': ('ACK', 'GO', 'claim', 'approve_route', 'continue'), 'carry': ('set_down', 'continue'),
             'postlook': ('regrasp', 'look_again')}[family]
    if family == 'postlook':
        r = state['relook_result']
        return 'regrasp' if r['pose_sigma_m'] <= BUDGET_XY_M or not r['relooks_left_this_stop'] else 'look_again'
    return next(a for a in order if a in adm)


# ---------------------------------------------------------------------------------------- requests / parsers
def jev_body(case, representation):
    fam = case['family']
    return {'model': JEV_MODEL, 'state': render(case, representation),
            'questions': {'action': {'type': 'choice', 'instructions': instructions(fam, representation),
                                     'criteria': options_for(fam)}}}


def parse_jev(body, family):
    a = body['answers']['action']
    p = a['probabilities']
    opts = options_for(family)
    if a['type'] != 'choice' or a['choice'] not in opts or set(p) != set(opts):
        raise ValueError('invalid_jev_options')
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in [*p.values(), a['confidence']]):
        raise ValueError('invalid_jev_probability')
    return a['choice'], float(a['confidence']), {k: float(v) for k, v in p.items()}


def gemma_body(case, representation):
    fam = case['family']
    system = (instructions(fam, representation) + '\nReturn only a JSON object with one key "action" whose value is exactly one of these '
              'choices, with its meaning: ' + json.dumps(options_for(fam)))
    return {'model': GEMMA_MODEL, 'messages': [{'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(render(case, representation), sort_keys=True)}],
            'temperature': .2, 'max_tokens': 200, 'response_format': {'type': 'json_object'},
            'usage': {'include': True}, 'provider': {'order': ['DeepInfra'], 'allow_fallbacks': False}}


def parse_gemma(body, family):
    raw = body['choices'][0]['message']['content'].strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[1].rsplit('```', 1)[0]
    a = json.loads(raw)
    if set(a) != {'action'} or a['action'] not in options_for(family):
        raise ValueError('invalid_gemma_action')
    return a['action']


# ---------------------------------------------------------------------------------------- transport
def keychain(service, account):
    r = subprocess.run(['security', 'find-generic-password', '-s', service, '-a', account, '-w'], capture_output=True, timeout=15)
    if r.returncode or not r.stdout.strip():
        raise ValueError('key_needed:' + service)
    return r.stdout.decode().strip()


def http_post(url, body, key, timeout=60):
    from harness.model_http import post
    return post(body, url, key, timeout)


class Runner:
    def __init__(self, raw_dir, *, jev_key, gemma_key, post=http_post, cap=CALL_CAP, sleep=time.sleep):
        self.dir = Path(raw_dir)
        (self.dir / 'raw').mkdir(parents=True, exist_ok=True)
        self.keys = {'jev': jev_key, 'gemma': gemma_key}
        self.post, self.cap, self.sleep = post, cap, sleep
        self.journal = self.dir / 'calls.jsonl'
        self.done = {}
        if self.journal.exists():
            for line in self.journal.read_text().splitlines():
                row = json.loads(line)
                self.done[row['call_id']] = row
        self.http_attempts = sum(len(r['attempts']) for r in self.done.values())

    def _scrub(self, text):
        for k in self.keys.values():
            if k:
                text = text.replace(k, '[REDACTED]')
        return text

    def call(self, policy, representation, case, repeat):
        call_id = f'{policy}.{representation}.{case["id"]}.r{repeat}'
        if call_id in self.done:
            return self.done[call_id]
        fam = case['family']
        body = jev_body(case, representation) if policy == 'jev' else gemma_body(case, representation)
        url, key = (JEV_URL, self.keys['jev']) if policy == 'jev' else (GEMMA_ENDPOINT, self.keys['gemma'])
        attempts, result = [], None
        for n in range(3):
            if self.http_attempts >= self.cap:
                attempts.append(dict(status='budget_cap_reached'))
                break
            self.http_attempts += 1
            result = self.post(url, body, key)
            attempts.append({k: result.get(k) for k in ('status', 'http_status', 'latency_s', 'error_type')})
            if result.get('status') == 'ok' or result.get('http_status') not in (429, 500, 502, 503, 504):
                break
            self.sleep(2.0 * (n + 1))
        row = dict(call_id=call_id, policy=policy, representation=representation, case_id=case['id'], repeat=repeat,
                   request=json.loads(self._scrub(json.dumps(body))), attempts=attempts, status='error', choice=None,
                   confidence=None, probabilities=None, latency_s=None, usage=None, cost=None, error=None)
        raw = self._scrub(result.get('raw_response') or '') if result else ''
        row['response_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
        row['request_sha256'] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        row['latency_s'] = result.get('latency_s') if result else None
        (self.dir / 'raw' / (call_id + '.response.txt')).write_text(raw)
        if result and result.get('status') == 'ok':
            try:
                if policy == 'jev':
                    row['choice'], row['confidence'], row['probabilities'] = parse_jev(result['body'], fam)
                    row['usage'] = result['body'].get('usage')
                else:
                    row['choice'] = parse_gemma(result['body'], fam)
                    u = result['body'].get('usage') or {}
                    row['usage'] = {k: u.get(k) for k in ('prompt_tokens', 'completion_tokens')}
                    row['cost'] = u.get('cost')
                    row['provider'] = result['body'].get('provider')
                row['status'] = 'ok'
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                row['status'], row['error'] = 'invalid_output', type(exc).__name__ + ':' + str(exc)[:80]
        else:
            row['error'] = (result or {}).get('status') or 'no_call'
            if result and result.get('http_status'):
                row['error'] += f':{result["http_status"]}'
        with open(self.journal, 'a') as f:
            f.write(json.dumps(row, sort_keys=True) + '\n')
        self.done[call_id] = row
        return row

    def run(self, jobs, workers=6):
        with ThreadPoolExecutor(workers) as pool:
            return list(pool.map(lambda j: self.call(*j), jobs))


# ---------------------------------------------------------------------------------------- metrics
def _pct(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, max(0, math.ceil(q * len(v)) - 1))] if v else None


def _auc(pos, neg):
    if not pos or not neg:
        return None
    wins = sum((p > n) + .5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def analyze(rows, cases, rule_rows=None):
    """rows: call rows of ONE policy+representation. Denominators count every attempted call (invalid/error = not acceptable)."""
    by_id = {c['id']: c for c in cases}
    rows = [r for r in rows if r['case_id'] in by_id]
    labelled = [r for r in rows if not by_id[r['case_id']]['ambiguous']]
    ok = lambda r: r['status'] == 'ok' and r['choice'] in by_id[r['case_id']]['acceptable']
    out = dict(n_calls=len(rows), n_errors=sum(r['status'] != 'ok' for r in rows),
               acceptable_labelled=[sum(ok(r) for r in labelled), len(labelled)])
    out['by_decision_point'] = {}
    for dp in sorted({c['decision_point'] for c in cases}):
        sub = [r for r in labelled if by_id[r['case_id']]['decision_point'] == dp]
        if sub:
            out['by_decision_point'][dp] = [sum(ok(r) for r in sub), len(sub)]
    out['by_label_basis'] = {}
    for b in ('hard_contract', 'inferred_from_contract'):
        sub = [r for r in labelled if by_id[r['case_id']]['label_basis'] == b]
        out['by_label_basis'][b] = [sum(ok(r) for r in sub), len(sub)]
    multi = [r for r in labelled if by_id[r['case_id']]['n_structurally_admissible'] >= 2]
    single = [r for r in labelled if by_id[r['case_id']]['n_structurally_admissible'] < 2]
    out['among_ge2_structurally_admissible'] = [sum(ok(r) for r in multi), len(multi)]
    out['among_single_structural_candidate'] = [sum(ok(r) for r in single), len(single)]
    valid = lambda r: r['status'] == 'ok' and (r['choice'] in by_id[r['case_id']]['acceptable']
                                              or r['choice'] in by_id[r['case_id']]['structurally_admissible'])
    out['contract_valid_or_hold'] = [sum(valid(r) for r in rows), len(rows)]
    amb = [r for r in rows if by_id[r['case_id']]['ambiguous'] and r['status'] == 'ok']
    out['ambiguous_choice_counts'] = {}
    for r in amb:
        out['ambiguous_choice_counts'][r['choice']] = out['ambiguous_choice_counts'].get(r['choice'], 0) + 1
    # stability across repeats
    per = {}
    for r in rows:
        per.setdefault(r['case_id'], []).append(r['choice'] if r['status'] == 'ok' else None)
    full = [v for v in per.values() if len(v) >= 2]
    out['stable_cases'] = [sum(len(set(v)) == 1 and v[0] is not None for v in full), len(full)]
    # message sensitivity pairs, repeat-matched
    sens = {'change': [0, 0], 'no_change': [0, 0]}
    for c in cases:
        if not c['pair'] or c['pair']['expect'] not in sens:
            continue
        base = by_id[c['pair']['base']]
        for r in [x for x in rows if x['case_id'] == c['id']]:
            b = next((x for x in rows if x['case_id'] == base['id'] and x['repeat'] == r['repeat']), None)
            if b is None or b['status'] != 'ok' or r['status'] != 'ok':
                sens[c['pair']['expect']][1] += 1
                continue
            sens[c['pair']['expect']][1] += 1
            if c['pair']['expect'] == 'change':
                sens['change'][0] += int(r['choice'] != b['choice'] and r['choice'] in c['acceptable'])
            else:
                sens['no_change'][0] += int(r['choice'] == b['choice'])
    out['sensitivity'] = sens
    lat = [r['latency_s'] for r in rows if r['latency_s'] is not None]
    out['latency_s'] = dict(median=statistics.median(lat) if lat else None, p90=_pct(lat, .9), n=len(lat))
    costs = [r['cost'] for r in rows if r.get('cost') is not None]
    out['cost_usd'] = dict(total=sum(costs), n_with_cost=len(costs), n_calls=len(rows))
    toks = [(r['usage'] or {}) for r in rows if r.get('usage')]
    out['tokens'] = dict(input=sum((t.get('input_tokens') or t.get('prompt_tokens') or 0) for t in toks),
                         output=sum((t.get('output_tokens') or t.get('completion_tokens') or 0) for t in toks), n_with_usage=len(toks))
    conf = [r for r in rows if r.get('confidence') is not None]
    if conf:
        bins = [(0, .5), (.5, .8), (.8, .95), (.95, 1.0001)]
        cal = []
        for lo, hi in bins:
            sub = [r for r in conf if lo <= r['confidence'] < hi and not by_id[r['case_id']]['ambiguous']]
            cal.append(dict(bin=[lo, min(hi, 1.0)], n=len(sub), acceptable=sum(ok(r) for r in sub)))
        out['calibration_bins'] = cal
        right = [r['confidence'] for r in labelled if r['status'] == 'ok' and ok(r)]
        wrong = [r['confidence'] for r in labelled if r['status'] == 'ok' and not ok(r)]
        out['confidence'] = dict(mean_right=statistics.mean(right) if right else None, n_right=len(right),
                                 mean_wrong=statistics.mean(wrong) if wrong else None, n_wrong=len(wrong),
                                 auroc_right_vs_wrong=_auc(right, wrong))
        a = [r['confidence'] for r in conf if by_id[r['case_id']]['ambiguous']]
        n = [r['confidence'] for r in conf if not by_id[r['case_id']]['ambiguous']]
        out['confidence_ambiguous_vs_not'] = dict(mean_ambiguous=statistics.mean(a) if a else None, n_ambiguous=len(a),
                                                  mean_other=statistics.mean(n) if n else None, n_other=len(n),
                                                  auroc_other_higher=_auc(n, a))
    return out


# ---------------------------------------------------------------------------------------- real stored E2E states
def real_state_from_request(user):
    """Text projection of one stored E2E request (no image, no hashes of images). Descriptive only; no label."""
    cov = user['own_map_summary']['pose']['covariance']
    a, b, d = cov[0][0], cov[0][1], cov[1][1]
    lam = (a + d) / 2 + math.sqrt(((a - d) / 2) ** 2 + b * b)
    dl = user['dialogue']
    return dict(robot_id=user['robot_id'], role=user['task']['fixed_roles'][user['robot_id']], condition=user['condition'],
                can_send_to=user['channel']['can_send_to'], sim_time_s=user['sim_time_s'],
                own_map=dict(B_seen_in_own_rgb=user['own_map_summary']['goal'] is not None, pose_sigma_m=round(math.sqrt(max(lam, 0)), 4)),
                own_route_proposal=user['own_route_proposal'] and dict(route_hash=user['own_route_proposal'].get('route_hash')),
                dialogue={k: dl[k] for k in ('proposal_message_id', 'route_hash', 'approved', 'own_claim', 'key', 'own_go_sent',
                                              'own_ack_sent', 'peer_go_ref', 'transport_admitted')},
                epoch_age_s=None, own_rgb_summary='own wrist RGB: image not included in this text conversion',
                own_rgb_grip='unknown', own_command_history=[str(c)[:80] for c in user['own_command_history']],
                peer_reports=[dict(sender=p['sender'], created_at_sim_s=p['created_at_sim_s'], message_id=p['message_id'],
                                   text=(p.get('body') or {}).get('text') or json.dumps(p.get('body'))[:200]) for p in user['peer_reports']])
