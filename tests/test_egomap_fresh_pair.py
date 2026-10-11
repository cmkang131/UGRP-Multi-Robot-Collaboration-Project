import copy
import json
from scripts import run_egomap_fresh_pair as m


def test_same_seed_full_bundles_differ_only_in_registered_toggles(tmp_path):
    plan = m.jobs(tmp_path, [12,13,14,15])
    assert len(plan)==12 and len({r['output'] for r in plan})==12
    for seed in m.SEEDS:
        a=m.bundle(seed,'off','a'*40);b=m.bundle(seed,'on','a'*40)
        assert a['case_cap_s']==b['case_cap_s']==810.
        assert a['stage_diagnostic'] is False
        for value in (a,b):
            del value['execution_bundle_id']
            for key in ('rgb_reconfirmation','covariance_inflation','fresh_home'):
                del value['options'][key]
        assert a==b
    for a,b in zip(plan[::2],plan[1::2]):
        assert a['seed']==b['seed'] and a['condition']!=b['condition']


def test_full_denominators_and_all_host_errors_preserved(tmp_path):
    plan=m.jobs(tmp_path,[12,13])
    for r in plan:r['status']='HOST_ERROR_TASK_DEADLINE_NOT_STARTED'
    summary=m.summarize(plan,tmp_path)
    assert len(summary['host_errors'])==12
    assert len(summary['prior_egomap71']['host_errors'])==12
    for g in summary['conditions'].values():
        assert g['measured']==0 and g['completed']==0 and g['host_errors']==6
        assert g['false_B']['registered_run_denominator']==6
        assert g['false_return']['declaration_denominator']==0


def test_partial_host_error_keeps_measured_events_separate_from_complete(monkeypatch,tmp_path):
    folder=tmp_path/'r';folder.mkdir()
    (folder/'result.json').write_text(json.dumps(dict(status='HOST_ERROR',start_sim_s=1.,wall_s=5)))
    monkeypatch.setattr(m,'score',lambda _:dict(samples=5,sim_s=1,commands=5,stage='return',
        returned=False,B_arrived=True,return_stage_entered=True,
        declarations=[dict(kind='goal_reached',valid=True),dict(kind='return_start_declared',valid=False)]))
    plan=[dict(name='r',seed=63001,condition='on',status='HOST_ERROR',pid=3,output=str(folder))]
    s=m.summarize(plan,tmp_path);g=s['conditions']['on']
    assert g['false_return']['count']==1 and g['false_return']['declaration_denominator']==1
    assert g['false_B']['count']==0 and g['completed']==0 and g['measured']==1
    assert len(s['host_errors'])==1
