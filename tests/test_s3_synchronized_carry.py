import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from harness import zone_s3_coarse_fine as cf
from harness.zone_s3_synchronized_carry import joint_plan,pulse_schedule,attach,OPTION
from harness.zone_s3_alignment_ownership import ALL
from tests.test_s3_coarse_fine import profiles
from tests.test_s3_alignment_ownership import fixture


def test_c3_joint_pan_uses_same_bounds_and_feasible_descent():
    g=[.1902041570698441,.032672933876623504];h=.38273033759855446
    old=cf.plan(g,h,'r2');p=joint_plan(g,h,'r2')
    assert old['pan']==1672 and not old['ready']
    assert p['ready'] and p['pan']>=1676
    assert p['halfwidths']==old['halfwidths']==[.018,.003,.112]
    cf.postures(p)
    assert joint_plan([.24,0.],0.,'r3')==cf.plan([.24,0.],0.,'r3')


def test_c3_outer_servo_waits_for_owned_pan_and_two_frames():
    g=[.1902041570698441,.032672933876623504];h=.38273033759855446
    s=cf.Servo('r2',profiles(),ALL,joint_plan)
    obs=lambda t,f:dict(sim_time=t,frame_id=f,sha256='a'*64)
    mode,pan=s.observe(1.,obs(1.,1),{6:1500},g,h)
    assert mode=='pan'
    assert s.observe(1.8,obs(1.8,2),{6:pan},g,h)[0]=='wait'
    assert s.observe(1.9,obs(1.9,3),{6:pan},g,h)[0]=='ready'


def test_virtual_leader_mirrors_same_clock_count_and_allows_crab():
    for route in ([[1.3,.05],[1.4518,.05]],[[1.3,.05],[1.3,.75]]):
        cs=[]
        for rid in ('r1','r2'):
            ctl=SimpleNamespace(rid=rid,seg=0,v3_plan={'route':route},claims={},log=lambda *a,**k:None)
            schedule,dt=pulse_schedule(ctl,10.,profiles());cs.append(schedule)
            assert dt>=.1 and all(c['turn']==0 for _,_,c in schedule)
            if route[0][0]!=route[1][0]:assert len(schedule)==13 and dt==.1
            else:assert dt==.65 and schedule[0][2]['left']
        assert [x[:2] for x in cs[0]]==[x[:2] for x in cs[1]]
        assert all(all(a[2][k]==-b[2][k] for k in ('forward','left','turn')) for a,b in zip(*cs))
    marker=object();assert attach(marker) is marker


def test_actual_pair_port_contract_and_go_guard(tmp_path,monkeypatch):
    from sim.s3_synchronized_carry import CarryPulsePort
    from harness.zone_s3_coupled_motion import authorized
    p=fixture(tmp_path,monkeypatch)
    try:
        for rid,ep in p.eps.items():
            attach(ep,OPTION);ctl=ep.controller
            ctl.state='carry';ctl.seg=0;ctl.schedule=ctl.door_schedule(10.)
            p.issue(rid,dict(kind='arm',servo_id=1,pulse=1500),9.)
            p.host.ports[rid]=CarryPulsePort(p.host.world,rid,coupled=lambda:True,allow_reverse=True,
                allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
            cmd=ctl.schedule[0][2]
            ctl.port.apply(dict(kind='mecanum',**cmd,duration_s=.15),10.)
            issued=p.drain(ep,10.)
            assert ctl.schedule[0][0]==pytest.approx(10.2)
            assert issued[-1]['duration_s']==.1 and abs(issued[-1]['forward'])==.35
            assert any(abs(x)==.35 for x in p.robots[rid].motors)
            p.host.ports[rid].tick(10.1)
            assert p.robots[rid].motors==(0.,)*4
        # Native port does not admit individual loaded rotation or mixed axes.
        port=p.host.ports['r1']
        with pytest.raises(ValueError):port.apply(dict(kind='mecanum',forward=0.,left=0.,turn=.35,duration_s=.1),11.)
        with pytest.raises(ValueError):port.apply(dict(kind='mecanum',forward=.35,left=.65,turn=0.,duration_s=.1),11.)
    finally:p.runtime.close()


def test_manifest_and_defaults():
    from scripts.run_s3_synchronized_carry import bundle
    from scripts.run_s3_synchronized_carry_cohort import PLAN,commands
    b=bundle('0'*40,'pair',0)
    assert b['synchronized_carry']['option']=='off' and b['joint_pan']=='off'
    assert len(commands(json.loads(PLAN.read_text()),'0'*40))==10


def test_outer_ticks_publish_carry_before_first_pulse(tmp_path,monkeypatch):
    from scripts.run_m2_pair import M2Student
    from sim.s3_synchronized_carry import CarryPulsePort
    from harness.zone_s3_coupled_motion import authorized
    p=fixture(tmp_path,monkeypatch)
    try:
        for rid,ep in p.eps.items():
            attach(ep,OPTION);ctl=ep.controller
            p.issue(rid,dict(kind='arm',servo_id=1,pulse=1500),9.)
            ctl.state='carry';ctl.seg=0;ctl.schedule=ctl.door_schedule(10.)
            ctl.next_look=float('inf');ep.status.grant=('carry_go_0',10.)
            ep.own.pose.localizer.pose.provider.loc._pf.load.loaded=True # synthetic commanded-grasp checkpoint
            ep.status.tick('carry_go_0',10.05) # benign GO heartbeat overwrites its original stamp
            p.host.ports[rid]=CarryPulsePort(p.host.world,rid,coupled=lambda:True,
                allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
        assert not authorized(p.eps['r1'],10.1) # real previous failure before peer carry publication
        for t in (10.1,10.2):
            p.refresh(t)
            for rid,ep in p.eps.items():
                M2Student.tick(ep.controller,t)
                issued=p.drain(ep,t)
                moving=[a for a in issued if a.get('kind')=='mecanum' and a.get('forward')]
                if t==10.1:assert not moving
                else:
                    assert authorized(ep,t), (ep.status.channel.partner_view(rid,t),ep.status.grant,ctl.state)
                    assert len(moving)==1 and moving[0]['duration_s']==.1
        # The fix is a shared start delay, not relaxed authorization.
        p.eps['r2'].status.tick('abort',10.3)
        assert not authorized(p.eps['r1'],10.3)
    finally:p.runtime.close()
