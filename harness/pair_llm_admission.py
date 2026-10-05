"""Durable, serialized case admission for the v100 viability cohort (design 9.6).

Own table in the existing budget database; no change to the sealed study ledger.
A crash leaves a running admission and blocks subsequent cases. A host retry is
inside the admitted case, through the existing run_attempts rule.
"""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction

from harness import pair_llm_contract as contract
from harness import pair_llm_decisions as limits
from harness import pair_llm_billing as billing
from harness import zone_study_prompts_ko as prompts
from harness.pair_llm_prompts_ko import PROMPT_VERSION
from harness.zone_main_budget import canonical

ORDER = ('rule', 'no_comm', 'peer_nl')


class AdmissionRefused(ValueError):
    def __init__(self, label, detail):
        self.failure_label = label
        super().__init__(f'{label}: {detail}')


def check_cap(cap):
    if type(cap) is not int or cap != limits.COHORT_TOKEN_CAP:
        raise AdmissionRefused('COHORT_CAP_MISMATCH', f'cohort cap must equal {limits.COHORT_TOKEN_CAP}')


def measured_increment(receipt):
    """Recount paired archived requests, rather than trusting a supplied token scalar.

    The maximum observed text increment is an estimate, not a provider guarantee.
    Images are identical in count/charge; no provider image measurement is claimed.
    """
    if (not isinstance(receipt, dict) or set(receipt) != {'pairs'} or
            not isinstance(receipt['pairs'], list) or not receipt['pairs']):
        raise AdmissionRefused('PEER_MEASUREMENT_REQUIRED', 'nonempty paired request measurement required')
    increments = []
    for pair in receipt['pairs']:
        if not isinstance(pair, dict) or set(pair) != {'no_comm', 'peer_nl'}:
            raise AdmissionRefused('PEER_MEASUREMENT_INVALID', 'each pair needs both conditions')
        counts = {}
        for condition, row in pair.items():
            if not isinstance(row, dict):
                raise AdmissionRefused('PEER_MEASUREMENT_INVALID', 'archived request must be an object')
            problems = prompts.verify_archived_request(row) + billing.billing_problems(
                row, require=billing.IMAGE_BILLING_VERSION)
            if (problems or json.loads(row['user']).get('condition') != condition or
                    row.get('prompt_version') != PROMPT_VERSION):
                raise AdmissionRefused('PEER_MEASUREMENT_INVALID', f'{condition}: {problems}')
            counts[condition] = row['tokens']['system'] + row['tokens']['user']
        if pair['no_comm']['billed_tokens']['images'] != pair['peer_nl']['billed_tokens']['images']:
            raise AdmissionRefused('PEER_MEASUREMENT_INVALID', 'image counts differ')
        increments.append(max(0, counts['peer_nl'] - counts['no_comm']))
    return {'tokens_per_call': max(increments), 'sample_pairs': len(increments),
            'sha256': hashlib.sha256(canonical(receipt).encode()).hexdigest(),
            'method': 'maximum paired local request text increment; provider usage measured separately'}


def _table(db):
    db.execute('CREATE TABLE IF NOT EXISTS pair_llm_admissions '
               '(cohort_id TEXT NOT NULL, condition TEXT NOT NULL, record TEXT NOT NULL, '
               'PRIMARY KEY(cohort_id, condition))')


def begin_case(budget, cohort_id, *, condition, seed, source_sha, peer_measurement=None, dev_single_arm=False):
    """``dev_single_arm``: DEV pilot only (10/5 user: run one LLM arm alone); no_comm without the rule-first order."""
    if dev_single_arm and condition != 'no_comm':
        raise AdmissionRefused('COHORT_ORDER_VIOLATION', 'dev single arm is no_comm only')
    if condition not in ORDER:
        raise AdmissionRefused('COHORT_ORDER_VIOLATION', 'unknown condition')
    cohort = budget.cohort(cohort_id)
    check_cap(cohort['token_cap'])
    increment = measured_increment(peer_measurement) if condition == 'peer_nl' else None
    with budget._connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _table(db)
        previous = [json.loads(r[0]) for r in db.execute(
            'SELECT record FROM pair_llm_admissions WHERE cohort_id=? ORDER BY rowid', (cohort_id,))]
        expected = [] if dev_single_arm else list(ORDER[:ORDER.index(condition)])
        if [r['condition'] for r in previous] != expected or any(r['status'] != 'completed' for r in previous):
            raise AdmissionRefused('COHORT_ORDER_VIOLATION', 'complete rule -> no_comm -> peer_nl, once per cohort')
        if any(r['seed'] != seed or r['source_sha'] != source_sha for r in previous):
            raise AdmissionRefused('COHORT_SOURCE_MISMATCH', 'all cases must use the same seed and frozen source')
        if previous and previous[0].get('rule_success') is not True:
            raise AdmissionRefused('RULE_BASELINE_FAILED', 'rule did not succeed; no LLM case may start')
        usage = budget._usage(db, cohort)
        remaining = cohort['token_cap'] - usage['charged_tokens']
        if remaining <= 0 or usage['pending_requests']:
            raise AdmissionRefused('COHORT_TOKEN_GATE', f'no available settled budget: remaining={remaining}')
        required, measurement = None, None
        if condition == 'peer_nl':
            measurement = previous[-1].get('measurement')
            if not measurement or not measurement['calls'] or measurement['unknown_calls']:
                raise AdmissionRefused('NO_COMM_MEASUREMENT_REQUIRED', 'complete provider usage is required')
            # Integer ceiling, including the exact >= boundary (no float rounding in the gate).
            estimate = Fraction(115, 100) * limits.CALLS_TOTAL * (
                Fraction(measurement['tokens'], measurement['calls']) + increment['tokens_per_call'])
            required = -(-estimate.numerator // estimate.denominator)
            if remaining < required:
                raise AdmissionRefused('PEER_TOKEN_GATE', f'remaining={remaining} < required={required}')
        row = {'condition': condition, 'seed': seed, 'source_sha': source_sha, 'status': 'running',
               'cohort_id': cohort_id, 'bundle_id': contract.BUNDLE_ID, 'ordinal': len(previous) + 1,
               'remaining_tokens_at_start': remaining, 'required_tokens': required,
               'no_comm_measurement': measurement, 'peer_increment': increment, 'dev_single_arm': bool(dev_single_arm)}
        db.execute('INSERT INTO pair_llm_admissions VALUES (?,?,?)', (cohort_id, condition, canonical(row)))
    return row


def finish_case(budget, cohort_id, *, condition, result, attempts=()):
    """Store completion and derive M2 from settled provider rows, never an operator average."""
    requests = []
    for attempt in attempts:
        run = budget.run(attempt['run_key'])
        if run['cohort_id'] != cohort_id or run['condition'] != condition or run['status'] == 'running':
            raise AdmissionRefused('COHORT_RECEIPT_INVALID', 'attempt does not belong to this completed case')
        requests.extend(budget.requests(attempt['run_key']))
    completed = bool(result and result.get('protocol_complete') is True and
                     result.get('failure_class') is None and result.get('status') == 'COLLECTED_UNQUALIFIED')
    measurement = {'calls': len(requests), 'tokens': sum(r.get('total_tokens') or 0 for r in requests),
                   'unknown_calls': sum(not r['usage_known'] for r in requests),
                   'request_ids': [r['id'] for r in requests]}
    with budget._connect() as db:
        db.execute('BEGIN IMMEDIATE')
        raw = db.execute('SELECT record FROM pair_llm_admissions WHERE cohort_id=? AND condition=?',
                         (cohort_id, condition)).fetchone()
        row = json.loads(raw[0])
        if row['status'] != 'running':
            raise AdmissionRefused('COHORT_RECEIPT_INVALID', 'completion is immutable')
        row.update(status='completed' if completed else 'failed', measurement=measurement,
                   rule_success=bool((result or {}).get('metrics', {}).get('success')) if condition == 'rule' else None)
        db.execute('UPDATE pair_llm_admissions SET record=? WHERE cohort_id=? AND condition=?',
                   (canonical(row), cohort_id, condition))
    return row
