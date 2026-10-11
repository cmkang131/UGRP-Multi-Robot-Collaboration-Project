"""Fixed saved own RGB + actual issued commands, no simulator/model execution.

Selected windows only: missing frames retain command prediction and reset image
history. GT is read exclusively after the two predictions have been produced.
This replays the command estimator, not the RBPF/maps/navigation counterfactual.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import cv2
import numpy as np
from harness.e2e_stall_odometry import Detector, Backup, alpha_extra
from harness.self_pulse_rotation import RotationPulseOdometry
from harness.active_camera import SEARCH
from scripts.diagnose_e2e_stall import rows


def replay(raw, images, mode='rgb_gate_v1'):
    result={};all_rows=[]
    for rid in ('r1','r2'):
        own=rows(raw/f'robots/{rid}/ownmap.jsonl');frames=rows(raw/f'robots/{rid}/frames.jsonl')
        origin=frames[0]['sim_time']
        commands=[{**r,'t':round(r['t']-origin,8)} for r in rows(raw/f'robots/{rid}/commands.jsonl')
                  if r['kind'] in ('mecanum','drive','hold','stop') and r['t']>=origin-1e-6]
        off=RotationPulseOdometry();on=RotationPulseOdometry()
        for driver in (off,on):driver.command(dict(t=0.,kind='initial_servo_command',pulses=SEARCH))
        detector=Detector(off,mode);backup=Backup();gate=False
        on.motion_filter=lambda delta,variance:(np.zeros(3) if gate else delta,variance)
        cursor=0;predictions=[];observed=[];max_match=0.
        for frame,prior in zip(frames,own):
            t=round(frame['sim_time']-origin,8)
            while cursor<len(commands) and commands[cursor]['t']<t-1e-8:
                cmd=commands[cursor];detector.command(cmd);off.command(cmd);on.command(cmd);cursor+=1
            f=images/frame['path']
            gate=False;flow=None
            if f.exists():
                data=f.read_bytes();assert hashlib.sha256(data).hexdigest()==frame['sha256']
                rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
                flow=detector.observe(t=t,frame_id=frame['frame_id'],rgb=rgb,servo=SEARCH,sha256=frame['sha256'])
                gate=detector.suppressed;observed.append(flow)
            else:
                detector.frames.clear();detector.stationary_since=None;detector.streak=0
                detector.nominal.advance(t);detector.last_nominal=np.asarray(detector.nominal.pose)
            off.advance(t);on.advance(t);gate=False
            max_match=max(max_match,float(np.max(abs(np.asarray(off.pose)-prior['pose_continuity']['control_pose']))))
            recovery=backup.update(t,on.pose,flow['stationary_duration_s']) if flow else 'not_observed'
            predictions.append(dict(t=t,off=list(off.pose),gate=list(on.pose),has_image=f.exists(),
                                    image_path=str(f) if f.exists() else None,flow=flow,recovery_proposal=recovery))
            while cursor<len(commands) and commands[cursor]['t']<=t+1e-8:
                cmd=commands[cursor];detector.command(cmd);off.command(cmd);on.command(cmd);cursor+=1
        # Evaluation-only coordinate alignment; not provided to either estimator.
        truth=rows(raw/f'eval_only/{rid}/trajectory.jsonl');by_t={round(r['t']-origin,8):r for r in truth}
        first=by_t[0.];yaw=first['robot_yaw_rad'];c,s=math.cos(yaw),math.sin(yaw)
        for r in predictions:
            gt=by_t[r['t']];dx,dy=np.asarray(gt['robot_xyz_m'][:2])-first['robot_xyz_m'][:2]
            xy=[c*dx+s*dy,-s*dx+c*dy]
            r['evaluation_actual_own_xy']=xy
            for key in ('off','gate'):r[key+'_error_m']=math.dist(r[key][:2],xy)
        windows=[];current=[]
        for r in predictions+[dict(has_image=False)]:
            if r['has_image']:current.append(r)
            elif current:
                start=current[0]
                def local_error(x,key):
                    return math.dist(np.asarray(x[key][:2])-start[key][:2],np.asarray(x['evaluation_actual_own_xy'])-start['evaluation_actual_own_xy'])
                windows.append(dict(start_s=start['t'],end_s=current[-1]['t'],frames=len(current),
                    gated=sum(bool((x['flow'] or {}).get('stationary')) for x in current),
                    off_endpoint_increment_error_m=local_error(current[-1],'off'),
                    gate_endpoint_increment_error_m=local_error(current[-1],'gate')))
                current=[]
        result[rid]=dict(total_frames=len(frames),saved_images_replayed=len(observed),
            exact_off_reproduction_max_abs_error=max_match,flow_counts=dict(Counter(r['status'] for r in observed)),
            gated_frames=sum(r['stationary'] for r in observed),windows=windows,
            global_command_error={key:dict(max_m=max(r[key+'_error_m'] for r in predictions),
                median_m=statistics.median(r[key+'_error_m'] for r in predictions),final_m=predictions[-1][key+'_error_m']) for key in ('off','gate')},
            candidates=dict(off='saved issued-command prediction',gate='zero current increment on own RGB stationary view',
                gate_noise='same fixed mean; AMCL nominal alpha .2 -> 2 Q only',
                gate_noise_recovery='same fixed commands; backup proposals unexecuted'),
            proposed_backup_frames=sum(r['recovery_proposal']=='backup' for r in predictions))
        all_rows += [dict(robot=rid,**r) for r in predictions]
    return result,all_rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--images',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=('rgb_gate_v1','rgb_pulse_gate_v1'),default='rgb_gate_v1')
    a=p.parse_args();cv2.setNumThreads(1);result,detail=replay(a.raw,a.images,a.mode)
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    import subprocess
    raw=(json.dumps(detail,indent=2)+'\n').encode();path=a.output/'replay.json.zst'
    subprocess.run(['zstd','-q','-o',str(path)],input=raw,check=True)
    assert subprocess.check_output(['zstd','-dc',str(path)])==raw
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
