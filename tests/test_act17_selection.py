import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import act17_selection as m


def fixture_report():
    return dict(complete=True,cohort='act17-v7-native',split='validation',teacher_actions_executed=0,policy_privileged_inputs=0,
        rows=[dict(candidate=c,seed=i,task_success=True) for c in ['M','F','S'] for i in range(8)],
        candidates={c:dict(n=8,N=8) for c in ['M','F','S']},models={c:dict(sha256=c.lower()*64) for c in ['M','F','S']})


def test_final_requires_all_three_complete_exact_val8_comparisons():
    report=fixture_report();report['rows'].pop()
    with pytest.raises(ValueError,match='exact M/F/S'):
        m.completed_validation(report,dict(validation8_seeds=list(range(8))))


def test_fixed_preoutcome_tie_and_evidence_hash_are_enforced(tmp_path):
    path=tmp_path/'validation.json';path.write_text(json.dumps(fixture_report()))
    selection=dict(validation_report=str(path),validation_report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        candidate='F',frozen_before_final=True,checkpoint_sha256='f'*64,validation_n=8,validation_N=8,completed_candidates=['M','F','S'])
    protocol=dict(validation8_seeds=list(range(8)))
    assert m.validate_final_selection(selection,protocol,'f'*64)=='F'
    other={**selection,'candidate':'M','checkpoint_sha256':'m'*64}
    with pytest.raises(ValueError,match='fixed selection'):
        m.validate_final_selection(other,protocol,'m'*64)
    path.write_text(path.read_text()+' ')
    with pytest.raises(ValueError,match='evidence changed'):
        m.validate_final_selection(selection,protocol,'f'*64)
