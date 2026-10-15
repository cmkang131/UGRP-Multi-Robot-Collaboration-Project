"""Replay the saved 77981 release prefix; explicitly account for missing obs.

fd724191 did not save per-tick release observations. Its per-phase all-zero
visible counters uniquely imply empty scans/band/peer fields for all 8 ticks.
This inference is recorded, never filled with evaluation geometry.
"""
import json
from pathlib import Path
from crate13_replay import RAW,NAMES,rows,js
from harness.grasp_act_input_audit import new_input_audit,sourced
from sim.crate_release_teacher import CrateReleaseTeacher
from sim.grasp_act_release_teacher import PairReleaseCode
from sim.crate_inspection_return import reverse_lift,inspection_choice

def replay():
 raw=RAW/NAMES[2]/'raw';res=js(raw/'result.json');audit=new_input_audit(True,'issued');ts={};paths={};labs={}
 for rid in ('r1','r2'):
  counts=res['release_teachers'][rid]['visible_counts_by_phase']
  assert all(c[k]==0 for c in counts.values() for k in ('destination','end_area','own_band','partner'))
  seq=rows(raw/f'teacher-{rid}.jsonl');i=next(i for i,c in enumerate(seq) if c['teacher_phase']=='closed');j=next(i for i,c in enumerate(seq) if c['skill']=='release')
  labs[rid]=seq[j:];paths[rid]=reverse_lift(seq[i]['applied_command']['pwm'],seq[j]['pwm'],[c['applied_command'] for c in seq[i:j]])
  ts[rid]=CrateReleaseTeacher(rid,res['prefix']['assigned'][rid],seq[j]['pwm'],handoff_pose_estimate=None,zone_rect=(0,0,1,1),input_audit=audit,reach_mode='pad_window_v2')
 code=PairReleaseCode(tuple(ts),channel='fixed_signals_v1',input_audit=audit);matches=0;start=labs['r1'][0]['t'];phase='look';since=start
 for i,row in enumerate(labs['r1']):
  now=row['t']
  for rid,t in ts.items():
   t.phase=phase;t.perceive(sourced({'scan':[],'band':None,'own_band_visible':False,'partner_visible':False},'visible_teacher_measurement','issued_commands','known_shape'),now)
  if now-start>=.6:
   for rid,t in ts.items():t.report(now,'look');code.post(rid,t.fixed_message('look',now),now)
   phase='await_look';since=now
  for rid,t in ts.items():
   exp=labs[rid][i]
   assert t.last_report==exp['report'] and phase==exp['teacher_phase']
   assert all(v==0 for v in exp['wheels']) and {str(k):v for k,v in t.pwm.items()}==exp['pwm']
   matches+=1
 now=res['code_decisions'][0]['t'];code.deliver(now);assert code.ready('look',since)
 decision=code.decide(now,require_seen=False);assert decision==res['code_decisions'][0]
 new=inspection_choice(decision,paths,used=False,after_visible=False)
 assert new=='return_to_pickup_for_observation'
 return {'run':NAMES[2],'release_matching_robot_ticks':matches,'matching_fixed_decisions':1,
  'original_release_observations_saved':False,'input_reconstruction':'all-zero per-phase counters uniquely imply 8 empty own observations per robot; no GT used',
  'old_branch':'release_fixed_signal_insufficient','new_branch':new,'first_branch_t':now,
  'reverse_paths':paths,'new_destination_signal':False,'input_audit':audit,'scope':'prefix only; reverse physical response and subsequent camera observations UNVERIFIED'}
if __name__=='__main__':
 out=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/crate13-audit/release-replay.json');v=replay();out.write_text(json.dumps(v,indent=2)+'\n');print({k:v[k] for k in ('release_matching_robot_ticks','matching_fixed_decisions','new_branch','first_branch_t')})
