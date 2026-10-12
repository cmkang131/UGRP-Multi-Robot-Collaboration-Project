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


def test_fresh_schedule_waits_for_own_B_then_reuses_fixed_leg_budget(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    c=SimpleNamespace(entities={},reached={},active=None,leg_start=0,streak=0,events=[],done=False,
        navigator=SimpleNamespace(reset_action=Mock(),target=None))
    c.event=lambda t,reason,**kw:c.events.append(dict(t=t,reason=reason,**kw))
    c.receive=lambda **kw:({'kind':'hold'},{'t':kw['t']})
    entered=[]
    monkeypatch.setattr(m.fresh.old,'enter_return',lambda c,t:entered.append(t))
    m.install_fresh_schedule(c)
    _,trace=c.receive(t=10)
    assert trace['fresh_task_schedule']['B_approach_start'] is None
    c.entities['B']={'first_t':12}
    _,trace=c.receive(t=12.2)
    assert trace['fresh_task_schedule']['B_approach_start']==12.2 and c.active=='B'
    assert c.events[-1]['checkpoint_source'] is None
    c.receive(t=282.2)
    assert entered==[282.2]
    c.receive(t=282.4)
    assert entered==[282.2]


def test_fresh_schedule_suppresses_box_command_after_B_declaration(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    c=SimpleNamespace(entities={'B':{'first_t':1}},reached={},active='B',leg_start=0,streak=0,events=[],done=False,
        navigator=SimpleNamespace(reset_action=Mock(),target=None))
    c.event=lambda t,reason,**kw:c.events.append(dict(t=t,reason=reason,**kw))
    def receive(**kw):
        c.reached['B']={'t':kw['t']}
        command={'kind':'mecanum','forward':.3}
        return command,{'command':command}
    c.receive=receive
    m.install_fresh_schedule(c)
    cmd,trace=c.receive(t=2.)
    assert cmd=={'t':2.,'kind':'hold'} and trace['command']==cmd
