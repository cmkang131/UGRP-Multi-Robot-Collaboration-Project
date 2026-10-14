"""Supervisor control flow with fake subprocesses; no simulation or network."""
import json
from pathlib import Path
import pytest
from scripts import run_grasp_act_batch as batch


def failure(reason='no_stable_joint_hold_3s',phase='complete'):
    return {'status':'complete','physical_success':False,
            'teachers':{rid:{'outcome':reason,'phase':phase} for rid in ('r1','r2')}}


SUCCESS={'status':'complete','physical_success':True,
         'teachers':{rid:{'outcome':'success','phase':'complete'} for rid in ('r1','r2')}}
HANDOFF={'status':'complete','physical_success':False,'approach_handoff':True,
         'teachers':{'r1':{'outcome':'approach_blocked_handoff','phase':'approach'},
                     'r2':{'outcome':'peer_approach_handoff','phase':'ready'}}}


def test_repeated_cause_counts_episodes_not_robots_or_polls():
    stop=batch.FailureStop('repeated_cause_v1')
    for _ in range(5):assert not stop.observe(0,failure())
    assert not stop.observe(1,failure(phase='pick'))
    assert not stop.observe(2,failure('phase_timeout'))
    assert not stop.observe(3,HANDOFF)
    assert not stop.observe(4,{'status':'interrupted','physical_success':False})
    assert stop.observe(5,failure())
    assert next(c for c in stop.diagnostic()['causes'] if c['N']==2)['episode_indices']==[0,5]
    assert batch.FailureStop().observe(0,failure())


def test_handoff_with_independent_failure_is_counted():
    stop=batch.FailureStop('repeated_cause_v1')
    mixed={**HANDOFF,'teachers':{**HANDOFF['teachers'],'r2':{'outcome':'phase_timeout','phase':'align'}}}
    assert not stop.observe(0,mixed)
    assert stop.observe(1,failure('phase_timeout','align'))
    assert stop.diagnostic()['causes']==[{'reason':'phase_timeout','phase':'align','episode_indices':[0,1],'N':2}]


@pytest.fixture
def fake_children(monkeypatch):
    import scripts.remote_run_finish as finish
    clock=[0];schedule={};killed=[]
    class Process:
        def __init__(self,command,**kwargs):
            self.index=int(command[command.index('--episode')+1])
            self.raw=Path(command[command.index('--out')+1]);self.raw.mkdir()
            self.pid=100+self.index;self.code=None
        def poll(self):
            at,result,code=schedule[self.index]
            if self.code is None and clock[0]>=at:
                batch.write(self.raw/'result.json',result);self.code=code
            return self.code
        def wait(self,timeout=None):
            assert self.poll() is not None
            return self.code
    def kill(proc,*args):
        if proc.poll() is None:
            killed.append(proc.index);proc.code=130
            batch.write(proc.raw/'result.json',{'status':'interrupted'})
    monkeypatch.setattr(batch.subprocess,'Popen',Process)
    monkeypatch.setattr(batch,'kill_group',kill)
    monkeypatch.setattr(batch.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(batch.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+1))
    monkeypatch.setattr(finish,'collect',lambda *args:None)
    return schedule,killed


def run_wave(tmp_path,fake_children,scope='repeated_cause_v1',**kwargs):
    schedule,killed=fake_children
    rows,reason=batch.wave(tmp_path/'wave',tmp_path/'plan.json',sorted(schedule),60.,
                           probe=False,limit=3.5,failure_stop=batch.FailureStop(scope),**kwargs)
    return rows,reason,killed


def test_first_failure_leaves_other_episode_running(tmp_path,fake_children):
    fake_children[0].update({0:(0,failure(),0),1:(2,SUCCESS,0),2:(1,HANDOFF,0)})
    rows,reason,killed=run_wave(tmp_path,fake_children)
    assert reason is None and killed==[]
    summary=batch.summarize(rows,3)
    assert (summary['n'],summary['N'],summary['interrupted'])==(1,3,0)
    assert summary['clean_handoff_rate']==summary['approach_handoff_rate']==1/3


def test_nominal_handoff_toggle_reaches_each_teacher_child(tmp_path,fake_children):
    fake_children[0].update({0:(0,HANDOFF,0),1:(1,SUCCESS,0)})
    rows,reason,killed=run_wave(tmp_path,fake_children,nominal_blocked_handoff='nominal_blocked_handoff_v1',
                               approach_progress='approach_progress_v1')
    assert reason is None and killed==[]
    for i in (0,1):
        command=json.loads((tmp_path/f'wave/episode-{i:03d}/PROCESS.json').read_text())['command']
        assert command[command.index('--nominal-blocked-handoff')+1]=='nominal_blocked_handoff_v1'
        assert command[command.index('--approach-progress')+1]=='approach_progress_v1'
    summary=batch.summarize(rows,40)
    assert (summary['n'],summary['N'],summary['planned_N'],summary['approach_handoff_n'])==(1,2,40,1)


def test_second_shared_failure_stops_only_unfinished_children(tmp_path,fake_children):
    fake_children[0].update({0:(0,failure(),0),1:(1,failure(),0),2:(3,SUCCESS,0)})
    rows,reason,killed=run_wave(tmp_path,fake_children)
    assert reason=='PHYSICAL_TEACHER_FAILURE' and killed==[2]
    summary=batch.summarize(rows,3)
    assert (summary['N'],summary['interrupted'])==(2,1)
    stop=json.loads((tmp_path/'wave/SUPERVISOR_STOP.json').read_text())
    assert stop['failure_stop']['causes'][0]['episode_indices']==[0,1]


def test_distinct_causes_do_not_cancel_healthy_episode(tmp_path,fake_children):
    fake_children[0].update({0:(0,failure(),0),1:(0,failure(phase='pick'),0),2:(2,SUCCESS,0)})
    rows,reason,killed=run_wave(tmp_path,fake_children)
    assert reason is None and killed==[] and len(rows)==3


def test_final_poll_and_cross_wave_failure_are_not_missed(tmp_path,fake_children):
    schedule,killed=fake_children
    stop=batch.FailureStop('repeated_cause_v1')
    for index in (0,1):
        schedule[index]=(0,failure(),0)
        rows,reason=batch.wave(tmp_path/f'wave{index}',tmp_path/'plan.json',[index],60.,
                               probe=False,limit=3.5,failure_stop=stop)
        assert reason==('PHYSICAL_TEACHER_FAILURE' if index else None)
    assert killed==[]


def test_default_scope_keeps_first_failure_stop(tmp_path,fake_children):
    fake_children[0].update({0:(0,failure(),0),1:(2,SUCCESS,0)})
    _,reason,killed=run_wave(tmp_path,fake_children,scope='first_failure')
    assert reason=='PHYSICAL_TEACHER_FAILURE' and killed==[1]


def test_host_error_still_stops_immediately(tmp_path,fake_children):
    fake_children[0].update({0:(0,{'status':'HOST_ERROR'},7),1:(2,SUCCESS,0)})
    _,reason,killed=run_wave(tmp_path,fake_children)
    assert reason=='CHILD_HOST_ERROR' and killed==[1]


def test_repeated_policy_cannot_be_bypassed(tmp_path,fake_children):
    with pytest.raises(ValueError,match='cannot bypass'):
        run_wave(tmp_path,fake_children,complete_frozen_cohort=True)
