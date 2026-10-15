"""Setup-only distribution contract; no physics, render or provider calls."""
import json
from pathlib import Path
import pytest
from scripts.prepare_beampair6 import distribution_k,generate,EXP
from scripts.prepare_beampair1 import prepare,EXP as OLD


def test_v7_minimum_counts_events_and_does_not_accept_a_branch_b_census():
    report=json.loads((EXP/'placement-validity.json').read_bytes())
    assert distribution_k(report)==91
    report['rows'].append(dict(population='v7',ends=dict(blue=dict(free_goal_N=0))))
    with pytest.raises(ValueError,match='infeasible'):distribution_k(report)


def test_default_off_preserves_the_entire_existing_plan_and_funnel(tmp_path):
    prepare(output=tmp_path)
    for name in ('gate-plan.json','setup-funnel.json'):
        assert json.loads((tmp_path/name).read_bytes())==json.loads((OLD/name).read_bytes())


def test_new_generator_never_overwrites_a_previous_plan(tmp_path):
    (tmp_path/'gate-plan.json').write_text('original')
    with pytest.raises(ValueError,match='immutable'):
        generate(8318700,tmp_path,Path('/not-used'),'off')
    assert (tmp_path/'gate-plan.json').read_text()=='original'
