import json
from pathlib import Path

from scripts import run_egomap_reconfirmation as runner


def test_import_relocation_preserves_suffix_and_does_not_mutate_manifest():
    old = '/home/ubuntu/ugrp-sim/src/' + 'a'*40
    table = {'sys_path':[old, old+'/experiments/probe', '/usr/lib/python3'],
             'modules':{'probe':old+'/experiments/probe/code.py'}}
    changed = runner.relocate_imports(table)
    assert changed['modules']['probe'] == str(runner.ROOT/'experiments/probe/code.py')
    assert changed['sys_path'][0] == str(runner.ROOT)
    assert changed['sys_path'][2] == '/usr/lib/python3'
    assert table['sys_path'][0] == old


def test_missing_and_unstarted_trials_are_host_errors_with_fixed_denominator(tmp_path):
    plan = [dict(seed=s,condition=c,name=f'{s}-{c}',output=str(tmp_path/f'{s}-{c}'),
                 status='HOST_ERROR_TASK_DEADLINE_NOT_STARTED')
            for s in range(63001,63007) for c in ('off','on')]
    result = runner.summarize(plan,tmp_path)
    assert len(result['host_errors']) == 12
    for group in result['conditions'].values():
        assert group['measured'] == 0
        assert group['host_errors'] == 6
        assert group['false_B']['run_denominator'] == 6
        assert group['false_return']['measured_run_denominator'] == 0
        assert group['false_B']['declaration_denominator'] == 0


def test_counts_false_declarations_and_distinguishes_host_failure(monkeypatch,tmp_path):
    from scripts import score_own_route_full_budget
    def score(path):
        return dict(samples=7,declarations=[{'kind':'return_start_declared','valid':False},
                                          {'kind':'goal_reached','valid':True}],
                    returned=False,B_arrived=True,command_audit={'commands':7})
    monkeypatch.setattr(score_own_route_full_budget,'score',score)
    folder=tmp_path/'run';folder.mkdir()
    (folder/'result.json').write_text(json.dumps(dict(start_sim_s=1,status='RECORDED',wall_s=3)))
    result=runner.summarize([dict(seed=63001,condition='off',output=str(folder),status='RECORDED',pid=1)],tmp_path)
    group=result['conditions']['off']
    assert group['false_return']==dict(count=1,run_denominator=6,measured_run_denominator=1,declaration_denominator=1)
    assert group['false_B']['count']==0
    assert group['true_B']==1
    assert not result['host_errors']


def test_truncated_result_is_host_error_and_does_not_break_summary(tmp_path):
    folder=tmp_path/'broken';folder.mkdir()
    (folder/'result.json').write_text('{"status":')
    report=runner.summarize([dict(seed=63001,condition='off',output=str(folder),status='RECORDED')],tmp_path)
    assert report['runs'][0]['status']=='HOST_ERROR_MALFORMED_RESULT'
    assert report['conditions']['off']['host_errors']==1
    assert (folder/'result.json').read_text()=='{"status":'
