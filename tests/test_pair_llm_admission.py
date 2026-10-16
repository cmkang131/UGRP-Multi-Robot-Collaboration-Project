"""Admission refusals occur before a case/backend/model starts; no external calls."""
import copy
import json

import pytest

from harness import pair_llm_admission as admission
from harness import pair_llm_contract as contract
from harness import pair_llm_live as live
from harness.zone_main_budget import MainStudyBudget
from tests.pair_llm_admission_fakes import SOURCE, complete_rule, measured_no_comm, peer_receipt, RESULT
from tests.pair_llm_fakes import offline_only  # noqa: F401


@pytest.fixture
def budget(tmp_path):
    b = MainStudyBudget.create(tmp_path/'budget.sqlite')
    b.register_cohort('c', token_cap=1100000, unknown_usage_charge_tokens=12000, prereg_sha256='p'*64, source={})
    return b


def begin(budget, condition, **kw):
    return admission.begin_case(budget, 'c', condition=condition, seed=911, source_sha=SOURCE, **kw)


@pytest.mark.parametrize('cap', [1, 300000, 2200000, None, True])
def test_cap_must_match_registration_even_on_direct_live_path(tmp_path, cap):
    b = MainStudyBudget.create(tmp_path/'cap.sqlite')
    # None is accepted by the generic ledger but never by the pair execution path.
    b.register_cohort('c', token_cap=1 if cap is True else cap, unknown_usage_charge_tokens=12000,
                      prereg_sha256='p'*64, source={})
    with pytest.raises(admission.AdmissionRefused, match='COHORT_CAP_MISMATCH'):
        live.run_pair_live(tmp_path/'not_started', condition='no_comm', seed=911, cap_s=1,
                           profile={}, budget=b, cohort_id='c', backend_factory=lambda *a: pytest.fail('backend'),
                           calibration=None, calibration_sha=None, source_sha=SOURCE)
    assert not (tmp_path/'not_started').exists() and b.requests() == []


@pytest.mark.parametrize('condition', ['no_comm', 'peer_nl'])
def test_cannot_skip_rule_or_no_comm(budget, condition):
    kw = {'peer_measurement': peer_receipt()} if condition == 'peer_nl' else {}
    with pytest.raises(admission.AdmissionRefused, match='COHORT_ORDER_VIOLATION'):
        begin(budget, condition, **kw)
    complete_rule(budget, 'c')
    if condition == 'peer_nl':
        with pytest.raises(admission.AdmissionRefused, match='COHORT_ORDER_VIOLATION'):
            begin(budget, condition, **kw)


def test_running_duplicate_failed_and_wrong_source_cases_are_refused(budget):
    begin(budget, 'rule')
    with pytest.raises(admission.AdmissionRefused, match='COHORT_ORDER_VIOLATION'):
        begin(budget, 'no_comm')
    admission.finish_case(budget, 'c', condition='rule', result=RESULT)
    with pytest.raises(admission.AdmissionRefused, match='COHORT_ORDER_VIOLATION'):
        begin(budget, 'rule')
    with pytest.raises(admission.AdmissionRefused, match='COHORT_SOURCE_MISMATCH'):
        admission.begin_case(budget, 'c', condition='no_comm', seed=912, source_sha=SOURCE)
    begin(budget, 'no_comm')
    admission.finish_case(budget, 'c', condition='no_comm', result={'status': 'HOST_ERROR'})
    with pytest.raises(admission.AdmissionRefused, match='COHORT_ORDER_VIOLATION'):
        begin(budget, 'peer_nl', peer_measurement=peer_receipt())


def test_failed_rule_blocks_model_cases(budget):
    complete_rule(budget, 'c', success=False)
    with pytest.raises(admission.AdmissionRefused, match='RULE_BASELINE_FAILED'):
        begin(budget, 'no_comm')


@pytest.mark.parametrize('measurement', [None, {'pairs': []}])
def test_peer_requires_recountable_increment(budget, measurement):
    complete_rule(budget, 'c')
    measured_no_comm(budget, 'c')
    with pytest.raises(admission.AdmissionRefused, match='PEER_MEASUREMENT_REQUIRED'):
        begin(budget, 'peer_nl', peer_measurement=measurement)


def test_peer_increment_rejects_falsified_token_counts():
    receipt = copy.deepcopy(peer_receipt())
    receipt['pairs'][0]['peer_nl']['tokens']['user'] -= 1
    with pytest.raises(admission.AdmissionRefused, match='PEER_MEASUREMENT_INVALID'):
        admission.measured_increment(receipt)


def test_peer_requires_known_provider_usage(budget):
    complete_rule(budget, 'c')
    measured_no_comm(budget, 'c', known=False)
    with pytest.raises(admission.AdmissionRefused, match='NO_COMM_MEASUREMENT_REQUIRED'):
        begin(budget, 'peer_nl', peer_measurement=peer_receipt())


@pytest.mark.parametrize('margin', [-1, 0, 1])
def test_peer_gate_exact_boundary_uses_measured_no_comm_and_increment(budget, margin):
    complete_rule(budget, 'c')
    measured_no_comm(budget, 'c', tokens=5000)
    receipt = peer_receipt()
    delta = admission.measured_increment(receipt)['tokens_per_call']
    required = (115*72*(5000+delta)+99)//100
    charged = 1100000 - required - margin - 5000
    budget.start_run('other-cost', cohort_id='c', bundle_id='fixture', bundle_sha256='a'*64, record={})
    row = budget.record_request('other-cost', {})
    budget.settle_request(row['id'], status='response_received',
                          provider_usage={'prompt_tokens': charged, 'completion_tokens': 0, 'total_tokens': charged})
    budget.finish_run('other-cost', status='finished')
    if margin < 0:
        with pytest.raises(admission.AdmissionRefused, match='PEER_TOKEN_GATE'):
            begin(budget, 'peer_nl', peer_measurement=receipt)
    else:
        row = begin(budget, 'peer_nl', peer_measurement=receipt)
        assert row['required_tokens'] == required
        assert row['remaining_tokens_at_start'] == required+margin
        assert row['no_comm_measurement']['tokens'] == 5000
        assert row['ordinal'] == 3


def test_cli_rejects_review_cap_counterexample():
    from scripts import run_pair_llm as cli
    args = cli.parser().parse_args(['--condition','peer_nl','--expected-source-sha',SOURCE,'--output','/tmp/unused',
        '--execute','--live','--proxy-pid','123','--budget-db','/tmp/unused.sqlite','--cohort-id','c',
        '--cohort-token-cap','2200000','--synthetic-plumbing-calibration'])
    with pytest.raises(admission.AdmissionRefused, match='COHORT_CAP_MISMATCH'):
        cli.check_live_args(args)


@pytest.mark.parametrize('condition', ['no_comm', 'peer_nl'])
def test_direct_live_path_refuses_out_of_order_before_backend_or_wire(tmp_path, budget, condition):
    with pytest.raises(admission.AdmissionRefused, match='COHORT_ORDER_VIOLATION'):
        live.run_pair_live(tmp_path/'not_started', condition=condition, seed=911, cap_s=1,
                           profile={}, budget=budget, cohort_id='c', calibration=None, calibration_sha=None,
                           source_sha=SOURCE, peer_measurement=peer_receipt(),
                           backend_factory=lambda *a: pytest.fail('backend started'),
                           wire=lambda *a, **kw: pytest.fail('wire called'))
    assert not (tmp_path/'not_started').exists() and budget.requests() == []


def test_peer_receipt_must_use_current_prompt_version():
    receipt = copy.deepcopy(peer_receipt())
    receipt['pairs'][0]['peer_nl']['prompt_version'] = 'old'
    with pytest.raises(admission.AdmissionRefused, match='PEER_MEASUREMENT_INVALID'):
        admission.measured_increment(receipt)


def test_rule_cli_accepts_cohort_parameters_for_read_only_plan(tmp_path, capsys):
    from scripts import run_pair_llm as cli
    assert cli.main(['--condition', 'rule', '--expected-source-sha', SOURCE, '--output', str(tmp_path/'unused'),
        '--budget-db', str(tmp_path/'budget.sqlite'), '--cohort-id', 'c', '--cohort-token-cap', '1100000',
        '--create-budget', '--synthetic-plumbing-calibration']) == 0
    assert json.loads(capsys.readouterr().out)['execution_started'] is False
    assert not (tmp_path/'budget.sqlite').exists()


def test_dev_single_arm_admits_no_comm_alone_and_only_no_comm(budget):
    row = begin(budget, 'no_comm', dev_single_arm=True)
    assert row['dev_single_arm'] is True and row['ordinal'] == 1
    with pytest.raises(admission.AdmissionRefused, match='COHORT_ORDER_VIOLATION'):
        begin(budget, 'peer_nl', peer_measurement=peer_receipt(), dev_single_arm=True)


def test_dev_single_arm_needs_the_dev_pilot_admission(tmp_path, budget):
    from harness import pair_llm_live as live
    with pytest.raises(ValueError, match='DEV pilot'):
        live.run_pair_live(tmp_path, condition='no_comm', seed=911, cap_s=10., profile={}, budget=budget,
                           cohort_id='c', backend_factory=lambda *a: pytest.fail('backend'), calibration=None,
                           calibration_sha=None, source_sha=SOURCE, dev_single_arm=True)
