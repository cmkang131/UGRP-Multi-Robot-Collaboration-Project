import copy,json,math
from pathlib import Path
from types import SimpleNamespace
import pytest
from harness.zone_s3_setdown import attach,lower_path,OPTIONS
from harness.zone_pair_highpose import lower_path as legacy_path
from sim.s3_setdown import supported_lower


def test_off_preserves_objects_and_old_path():
 marker=object();assert attach(marker) is marker
 p=legacy_path();assert lower_path(p,'off')==p
 with pytest.raises(ValueError):lower_path(p,'unknown')


@pytest.mark.parametrize('option',OPTIONS)
def test_saved_floor_pan_mismatch_through_real_assertion(tmp_path,monkeypatch,option):
 from tests.test_s3_alignment_ownership import fixture
 p=fixture(tmp_path,monkeypatch)
 try:
  ep=p.eps['r1'];ctl=ep.controller;path=legacy_path();floor=path[-1][0]
  ctl.grasp_pose={**floor,6:1540};saved=copy.deepcopy(ctl.grasp_pose)
  ctl.state='lower';ctl.grip_epoch=ctl.grip_closed_epoch=1;ctl.pose_anchors={}
  ctl._monitor_transit=lambda now:True
  ctl.look=lambda now:dict(frame_id=1,sha256='a'*64,image=b'')
  attach(ep,option);ctl._start_transit('lower',path,1.)
  ctl.transit.complete=lambda now:True
  # Saved c2 lower endpoint: all actual issued joints match canonical path,
  # but pan1500 differs from pickup pan1540. Real runtime floor check follows.
  for sid,v in {**floor,1:1500}.items():
   p.issue('r1',dict(kind='look',pan_pulse=v) if sid==6 else dict(kind='arm',servo_id=sid,pulse=v),20.)
  ctl.arm.events.clear();ctl.arm.until=20.
  ctl._lower(20.,True)
  if option=='off':assert ctl.failure=='FLOOR_POSE_NOT_COMMANDED'
  else:assert ctl.floor_return_verified and ctl.state=='wait_open' and ctl.failure is None
  assert ctl.grasp_pose==saved
 finally:p.runtime.close()


def test_candidate_speed_and_settle_change_only_last_segment():
 p=legacy_path();b=lower_path(p,'slow_final_v1');c=lower_path(p,'settle_floor_v1')
 assert b[:-1]==c[:-1]==p[:-1]
 assert b[-1][0]==c[-1][0]==p[-1][0]
 assert b[-1][1]==2.4 and c[-1][2]==1.2
 assert b[-1][2]==p[-1][2] and c[-1][1]==p[-1][1]


def row():return dict(states={'r1':'lower','r2':'lower'},vertical_speed_m_s=-.08,cargo_tilt_deg=1.42,fingers={'r1':[True,True],'r2':[True,True]},floor_normal_n=0.)


def test_supported_lower_is_evaluation_classification_not_height_only():
 r=row();assert supported_lower(r)
 r['fingers']['r2'][0]=False;assert not supported_lower(r)
 r['floor_normal_n']=.2;assert not supported_lower(r)
 r['states']={'r1':'wait_open','r2':'cp_open'};assert supported_lower(r)
 for key,value in [('vertical_speed_m_s',-.3),('vertical_speed_m_s',float('nan')),('cargo_tilt_deg',10.),('cargo_tilt_deg',float('nan'))]:
  q=row();q[key]=value;assert not supported_lower(q)
 q=row();q['states']['r2']='carry';assert not supported_lower(q)
 q=row();q['fingers']={};assert not supported_lower(q)


def test_live_check_requires_real_motion_progress_and_normal_commands(tmp_path):
 from scripts.run_s3_setdown_cohort import inspect
 (tmp_path/'PID').write_text('123\n');(tmp_path/'raw').mkdir()
 origin=dict(base_xyz_m=[0,0,0],finger_xyz_m=[0,0,.03],issued={})
 end={**origin,'finger_xyz_m':[0,0,.1]}
 rows=[dict(t=2.35,frame_count=1,states={'r1':'align','r2':'align'},robots={'r1':origin,'r2':origin}),dict(t=20.35,frame_count=360,states={'r1':'lift','r2':'lift'},robots={'r1':end,'r2':end})]
 (tmp_path/'raw/progress.jsonl').write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
 assert inspect(tmp_path)['healthy']
 rows[-1]['frame_count']=1
 (tmp_path/'raw/progress.jsonl').write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
 assert not inspect(tmp_path)['healthy'] and (tmp_path/'STOP_REQUEST').exists()


def test_manifest_defaults_and_frozen_ten_case_design():
 from scripts.run_s3_setdown import bundle,BUNDLE_ID
 from scripts.run_s3_setdown_cohort import PLAN,commands
 b=bundle('0'*40,'pair',2);assert b['setdown']['option']=='off' and b['setdown']['eval_supervisor']=='legacy'
 assert b['execution_bundle_id']==BUNDLE_ID
 plan=json.loads(PLAN.read_text());runs=commands(plan,'0'*40);assert len(runs)==10
 assert len({r['name'] for r,_ in runs})==10
 assert all(r['seed']==14201+r['condition'] for r,_ in runs)
 for option in OPTIONS:assert {r['condition'] for r,_ in runs if r['option']==option and r['condition'] in (2,5)}=={2,5}
