import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from harness.zone_s3_integer_carry import OPTION,PulseWindows,attach,tick
from harness.zone_s3_synchronized_carry import pulse_schedule,attach as attach_old,OPTION as OLD
from tests.test_s3_coarse_fine import profiles

@pytest.mark.parametrize('go',[28.1,28.6,29.1,29.6,30.1,30.6])
def test_saved_clock_boundaries_issue_exactly12_and_keep100ms(go):
 ctl=SimpleNamespace(rid='r1',seg=0,v3_plan={'route':[[1.3,.05],[1.4518,.05]]},claims={},log=lambda *a,**kw:None)
 schedule,duration=pulse_schedule(ctl,go,profiles());windows=PulseWindows(schedule)
 old=[];new=[]
 for n in range(tick(go),tick(schedule[-1][1])+1,2):
  now=n/20
  cmd=next((c for a,b,c in schedule if a<=now<b),None)
  if cmd and cmd['forward']:old.append(now)
  i,c=windows.select(now)
  if c and c['forward']:new.append(now)
  assert windows.select(now)==(None,None) # repeated outer tick cannot restart motor
 assert len(old)>12 and len(new)==12 and duration==.1
 assert all(b-a==pytest.approx(.2) for a,b in zip(new,new[1:]))
 assert all(isinstance(a,int) and isinstance(b,int) for a,b,c in windows.windows)


def test_lateral650ms_command_sent_once_and_zero_once():
 schedule=[(10.,10.65,{'forward':0.,'left':.65,'turn':0.}),(10.8,10.9,{'forward':0.,'left':0.,'turn':0.})]
 w=PulseWindows(schedule);issued=[]
 for n in range(200,220):
  i,c=w.select(n/20)
  if c is not None:issued.append((i,c))
 assert [i for i,c in issued]==[0,1]
 assert issued[0][1]['left']==.65


def test_real_controller_monitor_and_motor_stub_path_kept(tmp_path,monkeypatch):
 from tests.test_s3_alignment_ownership import fixture
 from sim.s3_synchronized_carry import CarryPulsePort
 p=fixture(tmp_path,monkeypatch)
 try:
  for rid,ep in p.eps.items():
   attach_old(ep,OLD);attach(ep,OPTION);ctl=ep.controller
   ctl.state='carry';ctl.seg=0;ctl.next_look=float('inf')
   # Registered first stage in actual controller route, with actual port drain.
   ctl.schedule=ctl.door_schedule(29.1)
   p.issue(rid,dict(kind='arm',servo_id=1,pulse=1500),28.)
   p.host.ports[rid]=CarryPulsePort(p.host.world,rid,coupled=lambda:True,allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
   ctl._carry(29.3,True);first=p.drain(ep,29.3)
   assert any(x.get('duration_s')==.1 and x.get('forward') for x in first)
   ctl._carry(29.4,True);assert not any(x.get('forward') for x in p.drain(ep,29.4))
   assert len(ctl.schedule)==13
   ctl._carry(31.85,True);assert ctl.state=='wait_lower'
 finally:p.runtime.close()


def test_off_identity_invalid_clock_and_twenty_case_manifest():
 marker=object();assert attach(marker) is marker
 with pytest.raises(ValueError):tick(float('nan'))
 with pytest.raises(ValueError):tick(10.01)
 from scripts.run_s3_integer_carry import bundle,BUNDLE_ID
 from scripts.run_s3_integer_carry_cohort import PLAN,commands
 b=bundle('0'*40,'pair',0);assert b['integer_carry']['option']=='off' and b['setdown']['option']=='canonical_floor_v1'
 assert b['execution_bundle_id']==BUNDLE_ID
 runs=commands(json.loads(PLAN.read_text()),'0'*40);assert len(runs)==20 and len({r['name'] for r,_ in runs})==20
 for o in ('off',OPTION):
  assert {r['condition'] for r,_ in runs if r['case']=='pair' and r['option']==o}==set(range(6))
  assert {r['condition'] for r,_ in runs if r['case']=='cyan' and r['option']==o}=={0,3,4,5}


def test_multi_route_factory_preserves_source_plan_and_rejects_diagonal(monkeypatch):
 from scripts.run_s3_integer_carry import route_plan
 from harness import pair_passage_plan as passage
 from harness import map_goto
 monkeypatch.setattr(map_goto,'authored_obstacles',lambda _:[])
 monkeypatch.setattr(map_goto,'interior_bounds',lambda _:[[-5,5],[-5,5]])
 monkeypatch.setattr(passage,'_sweep_blocker',lambda *a:(None,None))
 source={'route':[[0,0],[1,0]],'checkpoint_segments':{'before_door':1}}
 old=copy.deepcopy(source);route=[[1.3,.05],[1.4518,.05],[1.4518,.21694529519717285]]
 out=route_plan(source,{},route)
 assert out['route']==route and source==old and out['route'] is not route
 with pytest.raises(ValueError):route_plan(source,{},[[0,0],[1,1]])


def test_multi_route_intermediate_release_is_not_final_stop():
 from scripts.run_s3_integer_carry import release_completes_probe
 ctl=SimpleNamespace(seg=0,segments=[.1518,.1669])
 assert release_completes_probe(ctl,{})
 assert not release_completes_probe(ctl,{'registered_route':[[0,0],[.1518,0],[.1518,.1669]]})
 ctl.seg=1
 assert release_completes_probe(ctl,{'registered_route':[[0,0],[.1518,0],[.1518,.1669]]})


def test_identical_retry_preserves_twenty_conditions_and_uses_new_names():
 from scripts.run_s3_integer_carry_cohort import PLAN,commands
 plan=json.loads(PLAN.read_text());first=commands(plan,'0'*40);retry=commands(plan,'0'*40,3)
 assert len(first)==len(retry)==20
 for (a,ac),(b,bc) in zip(first,retry):
  assert {k:a[k] for k in ('case','condition','seed','option')}=={k:b[k] for k in ('case','condition','seed','option')}
  assert a['name'].endswith('-r1') and b['name'].endswith('-r3')
  assert ac[ac.index('--integer-carry')+1]==bc[bc.index('--integer-carry')+1]
