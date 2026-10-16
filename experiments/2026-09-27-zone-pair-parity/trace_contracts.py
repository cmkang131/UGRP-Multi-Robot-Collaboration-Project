"""Direct necessary input predicates on saved M2 traces. No pose reconstruction."""
import argparse
import base64
from pathlib import Path
from types import SimpleNamespace as NS
import sys

import replay as r


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    sys.meta_path.insert(0,r.FrozenPairs(r.V5))
    from harness.zone_pair_vision import valid_frame
    from harness.zone_pair_guards import PairCommandGuard
    from scripts import run_m2_pair as m2
    out={'schema':'ugrp.pair_trace_input_contracts.v1','judge_ref':r.V5,
         'scope':'necessary v5 preclose predicates at original M2 close command; no inserted RGB or pose',
         'runs':[]}
    for parent in ('zone-m2-pair-20260926','zone-m2-pair-kiro-20260926'):
        for result in sorted((r.RAW/parent).rglob('result.json')):
            if 'tensorboard' in str(result):continue
            meta=r.read(result)
            if meta.get('evaluation_only',{}).get('success_gt') is not True:continue
            root=result.parent
            frames=r.rows(root/'inputs.jsonl'); cmds=r.rows(root/'commands.jsonl')
            rec={'id':str(root.relative_to(r.RAW)),'robots':{}}
            for rid in ('r1','r2'):
                servo={}; close=[]
                for c in cmds:
                    if c['robot']!=rid:continue
                    if c['kind']=='initial_servo_command':servo={int(k):v for k,v in c['pulses'].items()}
                    if c['kind']=='arm' and c['servo_id']==1 and c['pulse']<servo.get(1,2000):
                        # first decreasing PWM of each close; remaining interpolation is not another grasp.
                        if servo.get(1)==2000:
                            fs=[f for f in frames if f['robot']==rid and round(f['sim_time'],4)<=c['t']]
                            f=fs[-1];blob=(root/'inputs'/f['file']).read_bytes()
                            assert r.sha(root/'inputs'/f['file'])==f['sha256']
                            obs={'image':base64.b64encode(blob).decode(),'robot_id':rid,'camera':'robot_cam',
                                 'frame_id':int(Path(f['file']).stem.split('-')[-1]),'sim_time':f['sim_time'],
                                 'sha256':f['sha256'],'actuator_state':{'servo_pulses':f['own_pose_commands']}}
                            same=PairCommandGuard._same_camera_commands(NS(ep=NS(own=NS(servo=servo))),obs)
                            valid=valid_frame(obs,rid,c['t'])
                            close.append({'command_s':c['t'],'last_saved_frame_s':f['sim_time'],
                                'frame_id':obs['frame_id'],'sha256':f['sha256'],
                                'age_s':c['t']-f['sim_time'],'valid_frame':valid,'same_camera_pwm':same,
                                'necessary_preclose_input_pass':bool(valid and same),
                                'saved_frame_m2_grip_view':m2.grip_view_m2(obs['image']),
                                'qualification':'rejects literal trace reuse; production PairTeam asks for new RGB, which is absent here'})
                    if c['kind']=='arm':servo[int(c['servo_id'])]=c['pulse']
                    if c['kind']=='look':servo[6]=c['pan_pulse']
                rec['robots'][rid]={'close_attempts':close}
            out['runs'].append(rec)
    r.write(a.output,out)


if __name__=='__main__':main()
