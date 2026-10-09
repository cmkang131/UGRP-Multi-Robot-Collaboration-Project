import json
from pathlib import Path
import pytest
from scripts.run_teach_return_dev import bundle,SEEDS,queue_receipt,S2_ACQUIRED
from scripts.replay_teach_return_transition import restore_graph
from harness.own_teach_capture import TeachGraph
from test_own_traversal_graph import sample
from test_own_teach_capture import observed,confirmed


def test_new_seeds_change_only_cohort_metadata_and_random_seed():
    from scripts.run_teach_capture import bundle as previous
    before=previous(49002,'a'*40)
    changed={'execution_bundle_id','check','case','preregistration','admission','task'}
    for s in SEEDS:
        b=bundle(s,'a'*40)
        assert {k:v for k,v in b.items() if k not in changed}=={k:v for k,v in before.items() if k not in changed}
        assert dict(b['task'],seed=49002)==before['task']
        assert b['schedule']==dict(explore_s=360.,suffix_cap_s=270.,relocalize_dev_timeout_s=60.)
    with pytest.raises(ValueError):bundle(49002,'a'*40)


def test_queue_does_not_start_in_gap_before_S3():
    s2=dict(branch='codex/s2-realism',purpose='s2v59 DEV',acquired_unix=S2_ACQUIRED,released_unix=S2_ACQUIRED+1)
    s3=dict(branch='codex/s3-three-robot-host',purpose='S3 smoke',acquired_unix=S2_ACQUIRED+2,released_unix=S2_ACQUIRED+3)
    with pytest.raises(ValueError,match='S2V59'):queue_receipt([])
    with pytest.raises(ValueError,match='S3_SMOKE'):queue_receipt([s2])
    with pytest.raises(ValueError,match='S3_SMOKE'):queue_receipt([s2,dict(s3,acquired_unix=S2_ACQUIRED-1)])
    with pytest.raises(ValueError,match='S3_SMOKE'):queue_receipt([s2,dict(s3,stale_release=True)])
    assert queue_receipt([s2,s3])==dict(s2=s2,s3=s3)


def test_restore_retained_prefix_and_real_match():
    g=TeachGraph('r3');g.observe(sample(1),confirmed(1,1),[observed(1)])
    g.observe(sample(2,.31,status='recover_backup'));g.seal()
    r=restore_graph(json.loads(json.dumps(g.snapshot())))
    assert r.snapshot()==g.snapshot() and r.route(r.anchor)==g.route(g.anchor)
    assert r.match(sample(3))['status']=='accepted'
    bad=g.snapshot();bad['sealed']=False
    with pytest.raises(AssertionError):restore_graph(bad)


def test_standard_workflow_is_registered():
    from sim.workflow_manager import plan
    p=plan(Path(__file__).parents[1],'own-teach-return-dev',['--seed','54001','--output','/tmp/no-physics','--expected-source-sha','a'*40])
    assert 'scripts.run_teach_return_dev' in p['command']


def test_report_keeps_host_errors_in_denominator_and_counts_calls_once():
    import importlib.util
    path=Path(__file__).parents[1]/'experiments/2026-10-09-teach-return-dev/code/report.py'
    spec=importlib.util.spec_from_file_location('eg54_score',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    r=[dict(seed=s,started=True,arrived=i==0,false_declarations=0,gate=i==0,final_xy_m=None if i==3 else float(i),
        match_attempts=0 if i==3 else 2,match_accepted=1 if i==0 else 0,over_3sigma=None,
        failure_class='HOST_ERROR' if i==3 else 'success' if i==0 else 'entry_localization',
        contacts=dict(wall=dict(episodes=0),robot=dict(episodes=0))) for i,s in enumerate(SEEDS)]
    out=m.summarize(r)
    assert out['arrivals_new']==1 and out['physical_attempts_new']==4 and out['total_attempts_with_prior']==6
    assert out['end_error_samples']==3 and out['end_error_median_m']==1 and out['end_error_max_m']==2
    assert out['match_accepted']==1 and out['match_attempts']==6 and out['match_success_fraction']==pytest.approx(1/6)
    assert out['failure_classes']['HOST_ERROR']==1 and out['prior_HOST_ERROR']==2


def test_preflight_requires_the_frozen_offline_proof(tmp_path,monkeypatch):
    import hashlib
    import scripts.run_teach_return_dev as m
    monkeypatch.setattr(m,'EXP',tmp_path);monkeypatch.setattr(m,'RAW',tmp_path)
    monkeypatch.setattr(m.old.base,'verify_source',lambda s:{})
    p=tmp_path/'offline-transition/result.json';p.parent.mkdir()
    p.write_text(json.dumps(dict(passed=True,errors=0,repeat_entered=True,gt_inputs=0)))
    (tmp_path/'freeze.json').write_text(json.dumps(dict(files={},offline_transition_sha256=hashlib.sha256(p.read_bytes()).hexdigest())))
    assert m.preflight('source')['nice']==0
    p.write_text(p.read_text()+'\n')
    with pytest.raises(AssertionError,match='OFFLINE_GATE_CHANGED'):m.preflight('source')
