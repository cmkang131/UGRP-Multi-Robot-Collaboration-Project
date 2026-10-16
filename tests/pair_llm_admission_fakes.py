"""Explicit fake predecessor receipts, exercising the production admission API."""
from functools import lru_cache

from harness import pair_llm_admission as admission
from harness import pair_llm_contract as contract
from harness import pair_llm_inputs as inputs
from harness import zone_study_prompts_ko as prompts
from tests.pair_llm_fakes import make_inputs

RESULT = {'status': 'COLLECTED_UNQUALIFIED', 'protocol_complete': True,
          'failure_class': None, 'metrics': {'success': True}}
SOURCE = '0' * 40


@lru_cache(maxsize=1)
def peer_receipt():
    pair = {}
    for condition in ('no_comm', 'peer_nl'):
        bundled, _, _ = make_inputs(condition)
        kwargs = {'window': {'window_id': 'window_test'}} if condition == 'peer_nl' else {}
        pair[condition] = prompts.archive_request(inputs.build_request(bundled, **kwargs))
    return {'pairs': [pair]}


def complete_rule(budget, cohort, *, success=True):
    admission.begin_case(budget, cohort, condition='rule', seed=911, source_sha=SOURCE)
    admission.finish_case(budget, cohort, condition='rule', result={**RESULT, 'metrics': {'success': success}})


def measured_no_comm(budget, cohort, *, tokens=3170, known=True):
    admission.begin_case(budget, cohort, condition='no_comm', seed=911, source_sha=SOURCE)
    key = 'fixture-no_comm#a1'
    budget.start_run(key, cohort_id=cohort, bundle_id=contract.BUNDLE_ID, bundle_sha256='0'*64,
                     record={'condition': 'no_comm'})
    row = budget.record_request(key, {'call_id': 'fixture-only'})
    usage = {'prompt_tokens': tokens, 'completion_tokens': 0, 'total_tokens': tokens} if known else None
    budget.settle_request(row['id'], status='response_received', provider_usage=usage)
    budget.finish_run(key, status='finished')
    admission.finish_case(budget, cohort, condition='no_comm', result=RESULT, attempts=[{'run_key': key}])
