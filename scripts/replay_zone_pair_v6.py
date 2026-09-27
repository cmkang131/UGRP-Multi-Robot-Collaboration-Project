#!/usr/bin/env python3
"""Conditional component replay of saved own inputs; never a physical replay.

Each endpoint starts from one explicitly recorded checkpoint. The first new
command/view/required receipt ends its replay as unknown. Later recorded
frames are not fed to the counterfactual controller. dev13/14 regression
checkpoints are independent fixtures, not a continuation of that replay.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from harness.owncam_pose_source import PoseReport
from harness.zone_pair_relative import RelativeBeamTrack
from harness.zone_pair_global import GlobalEnvelope, GlobalPairSweepGuard
from harness.zone_own_guards import SweepGuard
from harness.zone_pair_v6_policy import EXECUTION_BUNDLE_ID


class ReplayBoundary:
    def __init__(self):
        self.divergence=None
    def compare(self, now, recorded, proposed):
        if self.divergence is not None:
            raise RuntimeError('cannot consume old observations after a new branch')
        if recorded!=proposed:
            self.divergence={'sim_s':now,'recorded':recorded,'proposed':proposed,'after_branch':'unknown'}
        return self.divergence is None


class Reader:
    def __init__(self):self.hashes={}
    def bytes(self,path):
        path=Path(path)
        if 'eval_only' in path.parts or path.name=='result.json':
            raise ValueError('evaluation input forbidden in control replay')
        blob=path.read_bytes();self.hashes[str(path)]={'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob)}
        return blob
    def json(self,path):return json.loads(self.bytes(path))
    def rows(self,path):return [json.loads(s) for s in self.bytes(path).splitlines() if s]


def report(row):
    r=row['report'];xyz=r.get('xyyaw')
    return PoseReport(t_est=r['t_est'],initialized=r['initialized'],
        x_m=xyz[0] if xyz else float('nan'),y_m=xyz[1] if xyz else float('nan'),yaw_rad=xyz[2] if xyz else float('nan'),
        std_xy_m=r.get('std_xy_m') or float('inf'),std_yaw_rad=r.get('std_yaw_rad') or float('inf'),
        last_fix_t=r.get('last_fix_t'),fix_age_s=r.get('fix_age_s'),observation_quality=r.get('observation_quality'))


def component(obs,servo,*,pose=None,static=None,geometry=None,role=None):
    now=obs['sim_time'];relative=RelativeBeamTrack().observe(obs,servo,0,now=now)
    global_result={'clear':False,'reason':'GLOBAL_REPORT_NOT_SAVED','clearance_m':None}
    if pose is not None:
        envelope=GlobalEnvelope()
        p=envelope.pose(pose,now)
        if geometry is not None:
            guard=GlobalPairSweepGuard(SweepGuard(static),geometry,role)
            global_result=guard.certificate(servo,p,relative.beam())
    return {'relative':relative.as_dict(),'relative_ready':relative.ready(now),'global_safety':global_result}


def replay_recovery(obs, servo, pose, static, geometry, role, started_at):
    """Run production relook state transition at a recorded checkpoint.

    Missing posterior particles are explicit: view proposals use a spread of
    the saved own pose report. This does not reconstruct the historical PF.
    The fake provider has no tag IDs/counts and no mechanism to create a fix.
    """
    import numpy as np
    from harness.owncam_observability_v6 import geometry_score
    from harness.zone_pair_align import PairAlignRelook, ranked_look_pans
    from harness.zone_pair_v6_policy import pair_policy
    from harness.zone_own_guards import OwnPose
    from scripts.zone_teacher import ArmSequence
    now=obs['sim_time'];commands=[];events=[]
    class ReportOnlyProvider:
        def __init__(self):self.loc=object()
        def expected_observability(self,p,pan,static_map):
            hypotheses=np.array([[p.x,p.y,p.yaw],[p.x+p.std_xy,p.y,p.yaw+p.std_yaw],
                                  [p.x-p.std_xy,p.y,p.yaw-p.std_yaw]])
            return geometry_score(hypotheses,pan,static_map)
        def begin_observation(self,t,pwm,*,lost=False):return not lost
    class Base:
        def set(self,state,t,**detail):self.state=state
    class Replay(PairAlignRelook,Base):
        def look(self,t):return obs
        def fail(self,reason,t):self.state='failed';self.failure=reason
        def log(self,rid,event,t,**detail):events.append({'event':event,'sim_s':t,**detail})
    provider=ReportOnlyProvider();prior=provider.loc
    provider.begin_observation(now,servo)
    port=NS(apply=lambda cmd,t:commands.append(cmd),own=NS(last_report=pose,pose=provider,servo=servo,gate=NS(ok=True)))
    ctl=Replay();ctl.port=port;ctl.driver=NS(loc=provider.loc);ctl.rid=obs['robot_id']
    ctl.policy=pair_policy('b-only');ctl.state='align_relook';ctl.failure=None
    ctl.arm=ArmSequence(port,servo);ctl.arm.until=now;ctl.align_resume_name='p45'
    ctl.align_look_started_at=started_at
    guard=GlobalPairSweepGuard(SweepGuard(static),geometry,role)
    choices=ranked_look_pans(static,pose,servo,guard,provider,recovery_v6=True)
    ctl.align_pans=[r['pan'] for r in choices[:3]]
    ctl._align_relook(now,True)
    return {'state':ctl.state,'failure':ctl.failure,'events':events,'queued_pwm_count':len(ctl.arm.events),
            'first_queued_pwm':ctl.arm.events[0] if ctl.arm.events else None,
            'posterior_preserved':provider.loc is prior,'candidates':choices,
            'scope':'production state machine; report-only geometric proposal provider; no new fix fabricated'}


def replay_dev(raw,read):
    out=[]
    for number in range(5,15):
        run=f'dev{number:02d}'
        paths=sorted(raw.glob(f'zone-pair-dev-v*/{run}/pair_records.json'))
        if len(paths)!=1:
            out.append({'id':run,'status':'missing_or_ambiguous','paths':[str(p) for p in paths]});continue
        root=paths[0].parent;pair=read.json(paths[0])[0]
        robots=read.json(root/'robots.json');static=read.json(root/'inputs/static.json')['map']
        commands=read.rows(root/'commands.jsonl')
        record={'id':run,'raw':str(root),'robots':{}}
        for rid in ('r1','r2'):
            inputs=pair['robots'][rid]['inputs']
            first=next((r for r in inputs if r['phase'] in ('align','align_relook')),None)
            if first is None:
                record['robots'][rid]={'after_branch':'unknown','reason':'no_saved_align_checkpoint'};continue
            f=next(f for f in robots[rid]['frames'] if f['frame_id']==first['frame_id'])
            obs=read.json(root/'inputs'/rid/f"{f['frame']:05d}.json")
            blob=read.bytes(root/obs['image_file']);assert hashlib.sha256(blob).hexdigest()==obs['sha256']
            obs['image']=base64.b64encode(blob).decode()
            servo={int(k):v for k,v in obs['actuator_state']['servo_pulses'].items()}
            values=component(obs,servo,pose=report(f),static=static,geometry=pair['plan']['beam_geometry'],
                             role='end_neg' if rid=='r1' else 'end_pos')
            trigger=next((e for e in pair['robots'][rid]['events'] if e['event']=='align_relook_trigger'
                          and e['sim_s']<=obs['sim_time']),None)
            recovery=replay_recovery(obs,servo,report(f),static,pair['plan']['beam_geometry'],
                                     'end_neg' if rid=='r1' else 'end_pos',
                                     trigger['sim_s'] if trigger else obs['sim_time'])
            # Archived accepted=true is not promoted into a v6 fix receipt.
            boundary=ReplayBoundary()
            boundary.compare(obs['sim_time'],'legacy recorded controller continuation',
                             'hold: v6 requires new relative/global evidence')
            next_motion=next((c for c in commands if c.get('robot_id')==rid and c['t']>=obs['sim_time']
                              and c['kind'] in ('drive','mecanum','arm','look')),None)
            record['robots'][rid]={**values,'checkpoint':{'frame_id':obs['frame_id'],'sha256':obs['sha256'],
                    'sim_s':obs['sim_time'],'recorded_phase':first['phase']},'boundary':boundary.divergence,
                    'next_recorded_motion':next_motion,'counterfactual_complete':None,
                    'recovery':recovery}
        out.append(record)
    return out


def replay_m2(raw,index,read):
    rows=read.json(index)['runs'];out=[]
    for entry in rows:
        root=raw/entry['id'];frames=read.rows(root/'inputs.jsonl')
        robots={}
        for rid in ('r1','r2'):
            f=next((f for f in frames if f['robot']==rid and f.get('state')=='align'),None)
            if f is None:
                robots[rid]={'after_branch':'unknown','reason':'no_align_input'};continue
            blob=read.bytes(root/'inputs'/f['file']);assert hashlib.sha256(blob).hexdigest()==f['sha256']
            servo={int(k):v for k,v in f['own_pose_commands'].items()}
            obs={'robot_id':rid,'frame_id':int(Path(f['file']).stem.split('-')[-1]),'sim_time':f['sim_time'],
                 'sha256':f['sha256'],'image':base64.b64encode(blob).decode(),
                 'actuator_state':{'servo_pulses':servo}}
            values=component(obs,servo)
            boundary=ReplayBoundary();boundary.compare(obs['sim_time'],'M2 continuation','hold: new global receipt required')
            robots[rid]={**values,'boundary':boundary.divergence,'counterfactual_complete':None,
                         'recovery':'no common posterior/fix receipt in archived M2 input; unknown'}
        out.append({'id':entry['id'],'selection':'previously selected M2 success diagnostic set; not holdout',
                    'robots':robots})
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True)
    p.add_argument('--m2-index',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();read=Reader()
    result={'schema':'zone_pair_v6_component_replay.v1','execution_bundle_id':EXECUTION_BUNDLE_ID,
            'source_base':'f87921dc52f7a3f12d41b4bc6ab5c30227890e8e','candidate_source':'uncommitted',
            'scope':'conditional component replay at saved checkpoints, not full PF/RNG or episode replay',
            'physics_steps':0,'model_calls':0,'evaluation_inputs':0,
            'dev':replay_dev(args.raw_root,read),'m2':replay_m2(args.raw_root,args.m2_index,read),
            'success':None,'after_new_branch':'unknown','source_files':read.hashes}
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({'dev_runs':len(result['dev']),'m2_runs':len(result['m2']),'source_files':len(read.hashes),
                      'after_new_branch':'unknown'}))


if __name__=='__main__':main()
