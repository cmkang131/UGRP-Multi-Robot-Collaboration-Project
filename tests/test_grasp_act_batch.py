"""Supervisor control flow with fake subprocesses; no simulation or network."""
import json
import hashlib
import shutil
import subprocess
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
    clock=[0];schedule={};killed=[];real_popen=subprocess.Popen
    class Process:
        def __init__(self,command,**kwargs):
            self.index=int(command[command.index('--episode')+1])
            self.raw=Path(command[command.index('--out')+1]);self.raw.mkdir()
            self.pid=100+self.index;self.code=None
        def poll(self):
            at,result,code=schedule[self.index]
            if self.code is None and clock[0]>=at:
                batch.write(self.raw/'result.json',result)
                if result.get('_fixture_compressed'):
                    compressed_fixture(self.raw/'result.json')
                self.code=code
            return self.code
        def wait(self,timeout=None):
            assert self.poll() is not None
            return self.code
    def kill(proc,*args):
        if proc.poll() is None:
            killed.append(proc.index);proc.code=130
            batch.write(proc.raw/'result.json',{'status':'interrupted'})
    monkeypatch.setattr(batch.subprocess,'Popen',lambda command,**kw:
                        Process(command,**kw) if '--episode' in command else real_popen(command,**kw))
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


@pytest.mark.parametrize('recovery',['approach_recovery_v1','approach_recovery_v2','progress_view_recovery_v3'])
def test_nominal_handoff_toggle_reaches_each_teacher_child(tmp_path,fake_children,recovery):
    fake_children[0].update({0:(0,HANDOFF,0),1:(1,SUCCESS,0)})
    rows,reason,killed=run_wave(tmp_path,fake_children,nominal_blocked_handoff='nominal_blocked_handoff_v1',
                               approach_progress='approach_progress_v1',approach_recovery=recovery,
                               approach_coordination='off',handoff_observation='visible_handoff_v1')
    assert reason is None and killed==[]
    for i in (0,1):
        command=json.loads((tmp_path/f'wave/episode-{i:03d}/PROCESS.json').read_text())['command']
        assert command[command.index('--nominal-blocked-handoff')+1]=='nominal_blocked_handoff_v1'
        assert command[command.index('--approach-progress')+1]=='approach_progress_v1'
        assert command[command.index('--approach-recovery')+1]==recovery
        assert command[command.index('--handoff-observation')+1]=='visible_handoff_v1'
    summary=batch.summarize(rows,40)
    assert (summary['n'],summary['N'],summary['planned_N'],summary['approach_handoff_n'])==(1,2,40,1)


def test_search19_toggles_reach_each_child_and_result(tmp_path,fake_children):
    from sim.grasp_act_search19 import MODES
    fake_children[0].update({0:(0,SUCCESS,0)})
    rows,reason,killed=run_wave(tmp_path,fake_children,**MODES)
    assert reason is None and killed==[]
    command=json.loads((tmp_path/'wave/episode-000/PROCESS.json').read_text())['command']
    for key,mode in MODES.items():
        assert command[command.index('--'+key.replace('_','-'))+1]==mode


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


def test_diagnostic18_limits_concurrency_and_carries_failure_causes_across_waves(tmp_path,monkeypatch):
    calls=[];stop=batch.FailureStop('repeated_cause_v1')
    def wave(root,plan,indices,cap,**kw):
        calls.append((root.name,list(indices)))
        assert kw['failure_stop'] is stop and len(indices)<=15
        failed=kw['failure_stop'].observe(indices[-1],failure())
        return [{'index':i} for i in indices], 'PHYSICAL_TEACHER_FAILURE' if failed else None
    monkeypatch.setattr(batch,'wave',wave)
    rows,reason=batch.diagnostic_waves(tmp_path,tmp_path/'plan.json',list(range(18)),60.,
                                      concurrency=15,failure_stop=stop)
    assert calls==[('diagnostic',list(range(15))),('diagnostic-015',[15,16,17])]
    assert len(rows)==18 and reason=='PHYSICAL_TEACHER_FAILURE'
    assert stop.diagnostic()['causes'][0]['episode_indices']==[14,17]
    calls.clear();stop=batch.FailureStop('repeated_cause_v1');stop.observe(99,failure())
    rows,reason=batch.diagnostic_waves(tmp_path,tmp_path/'plan.json',list(range(18)),60.,
                                      concurrency=15,failure_stop=stop)
    assert len(calls)==1 and len(rows)==15 and reason=='PHYSICAL_TEACHER_FAILURE'


def compressed_fixture(path,*,keep_plain=False,pack_manifest=False):
    """Real zstd bytes with the production writer's two SHA-256 fields."""
    if not shutil.which('zstd'):pytest.skip('zstd CLI required')
    data=path.read_bytes()
    compressed=subprocess.check_output(['zstd','-q','-c'],input=data)
    Path(str(path)+'.zst').write_bytes(compressed)
    if not keep_plain:path.unlink()
    entry={'sha256':hashlib.sha256(compressed).hexdigest(),
           'decoded_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(compressed)}
    manifest=path.parent/'manifest.json'
    batch.write(manifest,{path.name+'.zst':entry})
    if pack_manifest:
        manifest_data=manifest.read_bytes()
        packed=subprocess.check_output(['zstd','-q','-c'],input=manifest_data)
        Path(str(manifest)+'.zst').write_bytes(packed);manifest.unlink()
        proof={'sha256':hashlib.sha256(packed).hexdigest(),
               'decoded_sha256':hashlib.sha256(manifest_data).hexdigest()}
        batch.write(path.parent/'manifest-compression.json',proof)
    return entry


def test_compressed_complete_exit0_keeps_full_denominator(tmp_path,fake_children):
    fake_children[0].update({0:(0,{**SUCCESS,'_fixture_compressed':True},0),
                            1:(1,{**HANDOFF,'_fixture_compressed':True},0),
                            2:(2,SUCCESS,0)})
    rows,reason,killed=run_wave(tmp_path,fake_children)
    summary=batch.summarize(rows,3)
    assert reason is None and killed==[]
    assert (summary['n'],summary['N'],summary['host_errors'],summary['interrupted'])==(2,3,0,0)
    for row in rows[:2]:
        path=Path(row['raw'])/'result.json'
        proof=json.loads((path.parent/'manifest.json').read_text())['result.json.zst']
        assert not path.exists() and row['status']=='complete' and row['exit']==0
        assert row['result_sha256']==proof['decoded_sha256']
        assert row['result_compressed_sha256']==proof['sha256']


def test_compressed_repeated_cause_stops_only_unfinished_children(tmp_path,fake_children):
    fake_children[0].update({0:(0,{**failure(),'_fixture_compressed':True},0),
                            1:(1,{**failure(),'_fixture_compressed':True},0),
                            2:(3,SUCCESS,0)})
    rows,reason,killed=run_wave(tmp_path,fake_children)
    assert reason=='PHYSICAL_TEACHER_FAILURE' and killed==[2]
    summary=batch.summarize(rows,3)
    assert (summary['N'],summary['host_errors'],summary['interrupted'])==(2,0,1)
    stop=json.loads((tmp_path/'wave/SUPERVISOR_STOP.json').read_text())
    assert stop['failure_stop']['causes'][0]['episode_indices']==[0,1]


@pytest.mark.parametrize('pack_manifest',[False,True])
def test_both_result_representations_must_match(tmp_path,pack_manifest):
    path=tmp_path/'result.json';batch.write(path,SUCCESS)
    compressed_fixture(path,keep_plain=True,pack_manifest=pack_manifest)
    assert batch.read(path,finalized=True)['status']=='complete'
    assert batch.read(Path(str(path)+'.zst'),finalized=True)['status']=='complete'
    batch.write(path,HANDOFF)
    result=batch.read(path,finalized=True)
    assert result['status']=='HOST_ERROR' and 'disagree' in result['error']


@pytest.mark.parametrize('field',['sha256','decoded_sha256'])
def test_compressed_result_rejects_bad_hash(tmp_path,field):
    path=tmp_path/'result.json';batch.write(path,SUCCESS)
    compressed_fixture(path)
    manifest=tmp_path/'manifest.json';value=json.loads(manifest.read_text())
    value['result.json.zst'][field]='0'*64;batch.write(manifest,value)
    result=batch.read(path,finalized=True)
    assert result['status']=='HOST_ERROR' and 'sha256 mismatch' in result['error']


def test_compression_proof_is_pending_until_child_exits(tmp_path):
    path=tmp_path/'result.json';batch.write(path,SUCCESS)
    compressed_fixture(path);(tmp_path/'manifest.json').unlink()
    assert batch.read(path)['status']=='complete'
    result=batch.read(path,finalized=True)
    assert result['status']=='HOST_ERROR' and 'missing manifest proof' in result['error']
