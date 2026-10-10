"""Offline upstream integration and a false-positive counterexample to restart scoring."""
import copy
import json
import hashlib
import pytest
from tests.test_pair_llm_s4_host import no_external_work
from harness.s4_pair_handshake import ACTIVE_PHASE_HEARTBEAT
from scripts import run_s4_pair_live8 as run, submit_s4_live8 as submit
from scripts.evaluate_s4_live8 import restart_metrics


def test_two_seeds_and_upstream_options_with_legacy_default_off(capsys):
    release=json.loads((run.ROOT/run.RECORD/'release.json').read_text())
    assert len(release['s3_file_sha256'])>=100
    for p,h in release['s3_file_sha256'].items():assert hashlib.sha256((run.ROOT/p).read_bytes()).hexdigest()==h
    for seed in (601,602):
        b=run.bundle('a'*40,'no_comm',seed,ACTIVE_PHASE_HEARTBEAT)
        assert b['seed']==seed and b['provider_seeds']=={'r1':seed,'r2':seed+1,'r3':seed+2}
        assert b['case_cap_s']==120 and b['setdown']['option']=='canonical_floor_v1'
        assert b['integer_carry']['option']=='integer_ticks_v1' and b['stage_origin']['option']=='public_stage_origin_v1'
    assert run.bundle('a'*40,'no_comm')['carry_lease_renewal']=='off'
    jobs=submit.commands('a'*40);assert len(jobs)==len({n for n,_ in jobs})==8
    assert {int(a[a.index('--seed')+1]) for _,a in jobs}=={601,602}
    assert run.main(['--expected-source-sha','a'*40,'--output','/tmp/no-write','--condition','no_comm',
        '--seed','602','--relay-receipt','/tmp/no-read'])==0
    assert json.loads(capsys.readouterr().out)['carry_lease_renewal']=='off'


def data():
    ss=[dict(t=.9,robots={r:dict(state='lower',seg=0) for r in ('r1','r2')})];cc=[];tt=[];ee=[]
    for t in [round(1+i*.05,8) for i in range(11)]+[2.,3.,3.05]:
        floor=t<2;xy=0 if t<=3 else .03
        ss.append(dict(t=t,robots={r:dict(state='cp_open' if floor else 'carry',seg=int(not floor)) for r in ('r1','r2')}))
        geoms=['floor'] if floor else [r+'__'+s+'_finger' for r in ('r1','r2') for s in ('left','right')]
        cc.append(dict(t=t,contacts=[dict(geom1='cargo_beam_1',geom2=g) for g in geoms]))
        tt.append(dict(t=t,items={'beam_1':dict(x=xy,y=0,z=.016 if floor else .1,speed=0)}))
        ee.append(dict(t=t,robots={r:dict(grip_epoch=1 if floor else 2,seg=0 if floor else 1) for r in ('r1','r2')}))
    permit=dict(epoch=2001,at=2.5,go_calls={r:'go-'+r for r in ('r1','r2')},ack_calls={r:'ack-'+r for r in ('r1','r2')})
    hs=dict(permits=[permit],decisions=[dict(robot_id=r,call_id=p+r,accepted=True,
        action=dict(choice=choice,epoch=2001)) for r in ('r1','r2') for p,choice in [('go-','go'),('ack-','ack_go')]])
    commands=[dict(robot_id=r,t=3.,pair_permit=permit,action=dict(kind='mecanum',forward=35,left=0)) for r in ('r1','r2')]
    inputs={r:[dict(sim_s=1.8,phase='align',sha256='a'*64)] for r in ('r1','r2')}
    return [ss,cc,tt,ee,hs,commands,inputs,0.]


def test_restart_requires_release_own_frames_contacts_fresh_epoch_and_commands():
    args=data();v=restart_metrics(*args)
    assert all(v[k]['n']==1 for k in ('reobserve','regrasp','fresh_go_ack','fresh_go_ack_continue'))
    assert v['fresh_go_ack_continue']['additional_distance_m']==pytest.approx(.03)
    for index,value in [(5,[]),(6,{}),(4,dict(permits=[],decisions=[]))]:
        changed=copy.deepcopy(args);changed[index]=value
        assert restart_metrics(*changed)['fresh_go_ack_continue']['n']==0
    changed=copy.deepcopy(args)
    for e in changed[3]:
        for r in e['robots'].values():r['grip_epoch']=1
    assert restart_metrics(*changed)['regrasp']['n']==0
    changed=copy.deepcopy(args);changed[1][-1]['contacts']=[]
    assert restart_metrics(*changed)['fresh_go_ack_continue']['n']==0
    changed=copy.deepcopy(args);changed[0]=changed[0][1:]
    assert restart_metrics(*changed)['release_start_t'] is None


def test_upstream_adapters_fix_real_command_floor_check_and_integer_windows(tmp_path,monkeypatch):
    from tests.test_s3_alignment_ownership import fixture
    from harness.zone_s3_setdown import attach
    from harness.zone_s3_integer_carry import PulseWindows
    from harness.zone_pair_highpose import lower_path
    p=fixture(tmp_path,monkeypatch)
    try:
        ep=p.eps['r1'];ctl=ep.controller;floor=lower_path()[-1][0]
        ctl.grasp_pose={**floor,6:1540};ctl.grip_epoch=ctl.grip_closed_epoch=1;ctl.pose_anchors={}
        ctl._monitor_transit=lambda now:True;ctl.look=lambda now:dict(frame_id=1,sha256='a'*64,image=b'')
        attach(ep,'canonical_floor_v1');ctl._start_transit('lower',lower_path(),1.)
        ctl.transit.complete=lambda now:True
        for sid,v in {**floor,1:1500}.items():
            p.issue('r1',dict(kind='look',pan_pulse=v) if sid==6 else dict(kind='arm',servo_id=sid,pulse=v),20.)
        ctl.arm.events.clear();ctl.arm.until=20.;ctl._lower(20.,True)
        assert ctl.floor_return_verified and ctl.state=='wait_open' and ctl.failure is None
        windows=PulseWindows([(i*.1,i*.1+.05,dict(forward=35)) for i in range(12)])
        fired=[windows.select(i*.05)[0] for i in range(24)]
        assert [i for i in fired if i is not None]==list(range(12))
    finally:p.runtime.close()
