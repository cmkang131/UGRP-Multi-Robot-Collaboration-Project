"""Pure integration/admission/scoring tests; no model request or physics."""
from types import SimpleNamespace
import copy
import json
import pytest
from scripts import run_s4_pair_live5 as run
from scripts import submit_s4_live5 as submit
from scripts.evaluate_s4_live5 import first_carry_window,contact_carry


def test_frozen_release_and_all_four_bundles_share_control_source():
    r=run.validate_release();assert r['s3_source_sha'].startswith('60eaf042')
    bundles=[run.bundle('a'*40,c) for c in run.live.stage.CONDITIONS]
    for b in bundles:
        assert b['case']=='pair' and b['seed']==601 and b['case_cap_s']==90
        assert b['execution_bundle_id']==run.BUNDLE_ID and b['synchronized_carry']['params']['go_ack_settle_s']==.2
        assert b['s3_release']==r and b['no_scripted_claims']
    assert len({json.dumps(b['controller_config'],sort_keys=True) for b in bundles})==1
    assert len(submit.commands('a'*40))==4
    assert run.Extension('/tmp/raw').components()[:2]==(run.pair.Link,run.pair.Host)


def test_admission_stacks_same_s3_modules_then_starts_own_stage(monkeypatch):
    from harness import zone_s3_alignment_entry as entry,zone_s3_coarse_fine as cf,zone_s3_synchronized_carry as carry
    calls=[]
    monkeypatch.setattr(entry,'attach_endpoint',lambda ep,**k:calls.append(('entry',k)))
    monkeypatch.setattr(cf,'attach_endpoint',lambda ep,opt,**k:calls.append(('cf',opt,k)))
    monkeypatch.setattr(carry,'attach',lambda ep,opt:calls.append(('carry',opt)))
    ctl=SimpleNamespace(claims={},driver=SimpleNamespace(outcome=None),set=lambda *a,**k:calls.append(('set',a,k)))
    ep=SimpleNamespace(controller=ctl,own=SimpleNamespace(last_report=SimpleNamespace(x_m=1,y_m=2,yaw_rad=.3,std_xy_m=.1)))
    run.admit('r1',ep,10.)
    assert [c[0] for c in calls]==['entry','cf','carry','set']
    assert calls[1][2]['planner'] is carry.joint_plan and calls[1][2]['refinements'].enabled
    assert ctl.driver.outcome=='arrived' and 'not student arrival' in ctl.claims['at_prestation']['source']
    assert calls[-1][1]==('align_start',10.)


def health(t=10,frames=20):
    return dict(sim_s=t,frames=frames,model_calls=3,status='RUNNING',robots={r:dict(commands=50,arm_delta_m=.1,
        servo_ids=[1,3,4,5],state='pregrasp_descend') for r in ('r1','r2')})


def test_early_check_requires_both_motion_and_advancing_frames():
    a=health(2,2);b=health();assert submit.healthy(b)
    c=copy.deepcopy(b);c['robots']['r2']['arm_delta_m']=0;assert not submit.healthy(c)
    clock=[0.];reads=iter([a,b]);names=['job'];
    def read(names):return {'job':dict(health=next(reads),exit=None,log_exceptions=[])}
    result=submit.initial_checks(names,'a'*40,read=read,clock=lambda:clock[0],wait=lambda s:clock.__setitem__(0,clock[0]+s))
    assert result['job']['status']=='PASS' and result['job']['checked_after_s']==10


def test_exception_stops_only_bad_job_and_preserves_failure():
    stopped=[]
    result=submit.initial_checks(['bad'],'a'*40,read=lambda ns:{'bad':dict(health=None,exit='1',log_exceptions=['Traceback'])},
        terminate=lambda n,s,r:stopped.append(n),clock=lambda:0.)
    assert result['bad']['status']=='FAIL' and stopped==['bad']


def test_lowering_excursion_never_counts_as_first_carry_and_all_four_fingers_required():
    def state(t,s):return dict(t=t,robots={r:dict(state=s,seg=0) for r in ('r1','r2')})
    window=first_carry_window([state(1,'wait_carry'),state(2,'carry'),state(3,'carry'),state(4,'refix_decide'),state(5,'lower')])
    assert window==(2,4)
    truth=[dict(t=t,items={'beam_1':dict(x=x,y=0,z=.1)}) for t,x in ((2,0),(3,.01),(5,.5))]
    cs=[dict(t=t,contacts=[dict(geom1='cargo_beam_1_geom',geom2=r+'__'+side+'_finger') for r in ('r1','r2') for side in ('left','right')]) for t in (2,3,5)]
    assert contact_carry(cs,truth,window)['n']==0
    truth[1]['items']['beam_1']['x']=.025
    assert contact_carry(cs,truth,window)['n']==1
    cs[1]['contacts'].pop();assert contact_carry(cs,truth,window)['n']==0
