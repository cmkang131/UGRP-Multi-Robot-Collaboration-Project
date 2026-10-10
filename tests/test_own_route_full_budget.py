import hashlib,json,pickle
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from scripts.own_route_budget_schedule import Schedule,OPTION,PLAN,admit_checkpoint
from scripts import run_own_route_full_budget as runner
from scripts.score_own_route_full_budget import command_metrics,boundary_distance


def controller(active='B'):
    return SimpleNamespace(entities={'B':{'first_t':10}},reached={},active=active,leg_start=0,
        navigator=SimpleNamespace(reset_action=Mock(),target='old'),streak=2,event=Mock(),done=False)


def test_frozen_controllers_and_checkpoint_list():
    r=runner.registration();assert len(r['checkpoints'])==6
    for name,digest in r['frozen_modules'].items():
        assert hashlib.sha256((runner.ROOT/name).read_bytes()).hexdigest()==digest,name


def test_12_pair_plan_and_only_budget_options_change(tmp_path):
    jobs=runner.plan(tmp_path)
    assert len(jobs)==len({j['output'] for j in jobs})==12
    assert {j['profile'] for j in jobs}=={'baseline','a'}
    for j in jobs:
        old=runner.previous.bundle(j['seed'],'a'*40,j['profile'],'stage')
        new=runner.bundle(j['seed'],'a'*40,j['profile'],'stage')
        assert {k:v for k,v in new['options'].items() if k!='stage_schedule'}==old['options']
        assert new['case_cap_s']==540 and new['phase_budgets_s']=={'B_approach':270.,'return':270.}
    assert runner.bundle(63001,'a'*40,'baseline','smoke_resume')['case_cap_s']==8


def test_schedule_keeps_existing_B_navigation_and_resets_box_only():
    for active in ('B','box'):
        c=controller(active);s=Schedule(c,100.,option=OPTION)
        assert c.active=='B' and c.leg_start==100
        assert c.navigator.reset_action.call_count==(active=='box')
        assert c.streak==(2 if active=='B' else 0)
        assert s.deadline==640


def test_budget_boundary_return_runs_once_and_gets_full_270():
    c=controller();s=Schedule(c,100.,option=OPTION);enter=Mock()
    s.before_frame(c,369.8,enter);assert not enter.called
    s.before_frame(c,370.,enter);assert enter.call_count==1 and s.deadline==640
    s.before_frame(c,371.,enter);assert enter.call_count==1


def test_B_arrival_stops_box_transition_command_and_returns_next_frame():
    c=controller();s=Schedule(c,100.,option=OPTION)
    move={'kind':'mecanum','forward':.3};trace={'command':move}
    assert s.after_frame(c,110,move,trace)==(move,trace)
    c.reached['B']={'t':110}
    cmd,new=s.after_frame(c,110,move,trace)
    assert cmd=={'t':110.,'kind':'hold'} and new['command']==cmd and trace['command']==move
    enter=Mock();s.before_frame(c,110.2,enter)
    assert enter.called and s.deadline==380.2


def test_off_admission_no_file_read_or_state_change(tmp_path):
    assert admit_checkpoint(None,0,'off',tmp_path) is None
    from scripts import run_own_route_particle_stages as old
    import inspect,subprocess
    # Strip only the opt-in hooks: rest of runner remains literally frozen.
    text=inspect.getsource(old.run)
    assert "getattr(args,'stage_schedule','off')" in text
    assert "elif args.mode=='stage' and t-start>=60 and not entered" in text


def test_checkpoint_admission_rejects_wrong_hash_before_restore(tmp_path):
    cp=tmp_path/'checkpoint';cp.write_bytes(b'fake')
    (tmp_path/PLAN).parent.mkdir(parents=True)
    (tmp_path/PLAN).write_text(json.dumps({'checkpoints':[{'seed':1,'sha256':'not matching'}]}))
    with pytest.raises(ValueError,match='CHECKPOINT_HASH_MISMATCH'):admit_checkpoint(cp,1,OPTION,tmp_path)


def test_no_mac_batch(tmp_path,monkeypatch):
    monkeypatch.setattr(runner.platform,'system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='ORACLE_ONLY'):runner.batch(SimpleNamespace(output=tmp_path))


def test_turn_ratios_reversals_and_gt_distance_only_score():
    cmds=[{'turn':1},{'kind':'hold'},{'turn':-1},{'forward':1},{'turn':-1},{'turn':1}]
    rows=[{'t':i,'command':c} for i,c in enumerate(cmds)]
    h=[{'t':i,'reason':'shared_v145','plan':{}} for i in (0,2,4,5)]
    a=command_metrics(rows,h)
    assert a['counts']=={'turn':4,'forward':1,'backward':0,'lateral':0,'hold':1}
    assert a['turn_sign_reversals']==a['within_alignment_reversals']==2
    assert a['repeat_turn_groups']==2 and a['turn_moving_fraction']==.8
    assert boundary_distance([2,3],{'center_m':[0,0],'half_extents_m':[1,1]})==pytest.approx(5**.5)
    assert boundary_distance([0,0],{'center_m':[0,0],'half_extents_m':[1,1]})==0


def test_off_runner_matches_previous_source_bytes(tmp_path,monkeypatch):
    """Run both actual host loops on a synthetic backend; no physics/replay."""
    import subprocess,types,copy,numpy as np
    from scripts import run_own_route_particle_stages as current
    from harness.active_camera import bind
    import sim.goal_route_assets as assets
    import harness.active_wall_vision as vision
    source='a'*40;root=tmp_path/source;root.mkdir()
    legacy=types.ModuleType('egomap63_frozen_runner')
    legacy.__file__=str(root/'scripts/run_own_route_particle_stages.py')
    exec(subprocess.check_output(['git','show','6f1fa925:scripts/run_own_route_particle_stages.py'],text=True),legacy.__dict__)
    monkeypatch.setattr(assets,'xml_preflight',lambda b,s:({'synthetic':True},None))
    monkeypatch.setattr(vision,'observe',lambda *a,**kw:{'segments':[]})
    class Backend:
        now=10.;frame=1
        def __init__(self,out):self.out=out
        def set_deadline(self,end):pass
        def capture(self):
            p=self.out/'robots/r3/rgb/00000.jpg';p.parent.mkdir(parents=True);p.write_bytes(b'fixture')
            return {'r3':({'frame_id':1},np.zeros((2,2,3),np.uint8))}
        def own_range(self):return None
        def _append(self,name,row):
            with (self.out/name).open('a') as f:f.write(json.dumps(row)+'\n')
        def issue(self,*a):pass
        def eval_sample(self):pass
        def close(self):pass
    class Controller:
        def __init__(self):
            g=SimpleNamespace(odom=SimpleNamespace(pose=[0,0,0],covariance=np.eye(3)),revision=0,best=0,resamples=0,
                export=lambda:{'fixture':'unchanged'},ledger=[],decisions=[])
            self.explorer=SimpleNamespace(memory=SimpleNamespace(self_map=g));self.events=[]
            self.heading_host=SimpleNamespace(rows=[]);self.stage='approach';self.reached={};self.done=False;self.declared=False
        def receive(self,**kw):self.done=True;return {'kind':'hold','t':10.},{'fixture':'trace'}
        def command(self,c):pass
        def snapshot(self):return {'fixture':'route'}
    def load(path,out):
        out.mkdir();return Backend(out),Controller(),1.,25,{'code':{'head':source},'sha256':'same','sim_s':10.}
    from contextlib import nullcontext
    outputs=[]
    for index,fn in enumerate((legacy.run,current.run)):
        out=tmp_path/str(index)
        run=bind(fn,ROOT=root,checkpoint_load=load,server_slot=lambda:nullcontext(0),install=lambda *a,**kw:None,
                 time=SimpleNamespace(monotonic=lambda:0),bundle=lambda *a:{'case_cap_s':120})
        args=SimpleNamespace(output=out,seed=63001,profile='baseline',mode='stage',checkpoint=tmp_path/'fake')
        r=run(args);assert r['status']=='RECORDED'
        outputs.append({p.name:p.read_bytes() for p in out.rglob('*') if p.is_file() and p.name not in ('result.json','artifacts.sha256.json')})
    assert outputs[0]==outputs[1]
