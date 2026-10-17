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


def test_gate_is_disjoint_and_held_after_exact_six(tmp_path,monkeypatch):
    import scripts.queue_beampair6 as q
    root=Path(__file__).resolve().parents[1]
    source='a'*40
    monkeypatch.setattr(q,'frozen',lambda source,path:(root/path).read_bytes())
    short=json.loads((root/q.SHORT).read_bytes())['episodes']
    report=dict(N=6,n=6,cap_end_N=0,runs=[dict(seed=e['seed'],adapter_sha=source,strict_success=True) for e in short])
    evidence=tmp_path/'summary.json';evidence.write_text(json.dumps(report))
    (tmp_path/'setup-funnel.json').write_bytes((EXP/'setup-funnel.json').read_bytes())
    template=dict(name='old',command=['python3','remote','--host','gcp1','--per-run-mb','128','--plan','old-plan','--episode','0','--rendezvous','old-mode','old'])
    monkeypatch.setattr(q,'previous',lambda *a,**k:dict(source_hashes={},runs=[template]))
    table=tmp_path/'rejection_table.json';table.write_text('{}')
    value=q.build(source,evidence,table)
    assert value['status']=='HOLD_SCENE' and not any(value[k] for k in ('ready','approved','submitted','scene_approved'))
    assert value['max_parallel']==16 and value['project_id']=='ugrp-sim-b-1014'
    assert len(value['runs'])==40 and {r['seed'] for r in value['runs']}==set(range(8318700,8318740))
    assert value['runs'][0]['seed']==8318726
    assert value['setup_validity']=='beampair_gate_valid_v2' and value['wall_layer']=='beampair_wall_clear_v1'
    assert all(r['command'][r['command'].index('--plan')+1]==q.PLAN for r in value['runs'])
    report['runs'][0]['strict_success']=False;evidence.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='all six'):q.build(source,evidence,table)
