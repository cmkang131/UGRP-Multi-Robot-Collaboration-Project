"""Post-run evaluation only. No truth or result is supplied to a controller.

Stall denominator is the UNGATED replay of actual issued commands for both
conditions; using the candidate's gated displacement would conceal stalls.
"""
from pathlib import Path
from collections import Counter
import argparse
import bisect
import hashlib
import json
import math
import statistics
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))
from harness.self_pulse_rotation import RotationPulseOdometry
from harness.active_camera import SEARCH


def read(path):
    if path.exists(): return path.read_bytes()
    if Path(str(path)+'.zst').exists():
        return subprocess.check_output(['zstd', '-dc', str(path)+'.zst'])
    return None


def rows(path):
    data=read(path)
    return [json.loads(x) for x in data.splitlines() if x] if data else []


def stats(values):
    return dict(n=len(values), max=max(values,default=None),
                median=statistics.median(values) if values else None)


def jumps(poses):
    ds=[math.dist(a[:2],b[:2]) for a,b in zip(poses,poses[1:])]
    return dict(**stats(ds), over_5cm=sum(x>.05 for x in ds),over_20cm=sum(x>.20 for x in ds))


def evaluate(run, horizon=None):
    output={};detail=[]
    contacts=rows(run/'raw/eval_only/contacts.jsonl');contact_ts=[x['t'] for x in contacts]
    for rid in ('r1','r2'):
        raw=run/'raw';own=rows(raw/f'robots/{rid}/ownmap.jsonl')
        frames=rows(raw/f'robots/{rid}/frames.jsonl');truth=rows(raw/f'eval_only/{rid}/trajectory.jsonl')
        if not own or not frames or not truth:
            output[rid]={'status':'MISSING_EVALUATION_INPUT','frames':len(frames)};continue
        origin=frames[0]['sim_time'];by_id={x['frame_id']:x for x in own}
        commands=[{**r,'t':round(r['t']-origin,8)} for r in rows(raw/f'robots/{rid}/commands.jsonl')
                  if r['t']>=origin-1e-6 and r['kind'] in ('mecanum','drive','hold','stop','arm','look')]
        predictor=RotationPulseOdometry();predictor.command(dict(t=0.,kind='initial_servo_command',pulses=SEARCH))
        cursor=0;predictions=[]
        for frame in frames:
            t=round(frame['sim_time']-origin,8)
            if horizon is not None and t>horizon+1e-8: break
            if frame['frame_id'] not in by_id:continue
            row=by_id[frame['frame_id']];assert row['sha256']==frame['sha256']
            while cursor<len(commands) and commands[cursor]['t']<t-1e-8:
                predictor.command(commands[cursor]);cursor+=1
            predictor.advance(t)
            predictions.append(dict(t=t,absolute_t=frame['sim_time'],nominal=list(predictor.pose),row=row))
            while cursor<len(commands) and commands[cursor]['t']<=t+1e-8:
                predictor.command(commands[cursor]);cursor+=1
        # Truth is read into scoring only after all command predictions exist.
        ts=[x['t'] for x in truth]
        base=min(truth,key=lambda x:abs(x['t']-origin));assert abs(base['t']-origin)<1e-6
        c,s=math.cos(base['robot_yaw_rad']),math.sin(base['robot_yaw_rad'])
        for p in predictions:
            idx=min(bisect.bisect_left(ts,p['absolute_t']),len(ts)-1)
            idx=min((idx,max(0,idx-1)),key=lambda i:abs(ts[i]-p['absolute_t']))
            assert abs(ts[idx]-p['absolute_t'])<1e-6
            gt=truth[idx];dx,dy=[gt['robot_xyz_m'][i]-base['robot_xyz_m'][i] for i in (0,1)]
            p['actual']=[c*dx+s*dy,-s*dx+c*dy];p['gt_index']=idx
            pc=p['row']['pose_continuity']
            for kind in ('map','control'):
                p[kind]=pc[kind+'_pose'];p[kind+'_error_m']=math.dist(p['actual'],p[kind][:2])
        intervals=[];segments=[];gate_segments=[]
        for i,(a,b) in enumerate(zip(predictions,predictions[1:])):
            expected=math.dist(a['nominal'][:2],b['nominal'][:2])
            actual=sum(math.dist(x['robot_xyz_m'][:2],y['robot_xyz_m'][:2]) for x,y in
                       zip(truth[a['gt_index']:b['gt_index']],truth[a['gt_index']+1:b['gt_index']+1]))
            trans=expected>=.005;stall=trans and actual<.2*expected
            flow=b['row'].get('stall_odometry') or {};gated=bool(flow.get('translation_gated'))
            other=set()
            for row in contacts[bisect.bisect_left(contact_ts,a['absolute_t']):bisect.bisect_right(contact_ts,b['absolute_t'])]:
                for hit in row['contacts']:
                    gs=[hit['geom1'],hit['geom2']]
                    if sum(g.startswith(rid+'__') for g in gs)==1:
                        other.update(g for g in gs if not g.startswith(rid+'__') and g!='floor')
            item=dict(t0=a['t'],t1=b['t'],dt=b['t']-a['t'],expected_m=expected,actual_path_m=actual,
                      translating=trans,stalled=stall,gated=gated,contacts=sorted(other),
                      map_error_m=b['map_error_m'],control_error_m=b['control_error_m'],
                      map_error_change_m=b['map_error_m']-a['map_error_m'],
                      control_error_change_m=b['control_error_m']-a['control_error_m'],
                      flow_status=flow.get('status'),median_px=flow.get('median_px'),
                      mean_abs_diff=flow.get('mean_abs_diff'),recovery=flow.get('recovery'))
            intervals.append(item)
            for yes,ss in ((stall,segments),(gated,gate_segments)):
                if yes:
                    if not ss or ss[-1]['last_index']!=i-1:ss.append(dict(first_index=i,last_index=i,t0=a['t'],t1=b['t'],duration_s=0.))
                    ss[-1].update(last_index=i,t1=b['t'],duration_s=ss[-1]['duration_s']+item['dt'])
        for seg in segments:
            part=intervals[seg['first_index']:seg['last_index']+1]
            for key in ('expected_m','actual_path_m','map_error_change_m','control_error_change_m'):
                seg[key]=sum(x[key] for x in part)
            seg['contacts']=sorted({g for x in part for g in x['contacts']})
        stalled=[x for x in intervals if x['stalled']];trans=[x for x in intervals if x['translating']]
        flows=[p['row'].get('stall_odometry') or {} for p in predictions]
        moving=[x for x in intervals if x['translating'] and x['actual_path_m']>=.8*x['expected_m']]
        output[rid]=dict(status='SCORED',frames=len(predictions),sim_s=predictions[-1]['t'],
            independent_ungated_command_replay=True,translation_intervals=len(trans),
            stalled_intervals=len(stalled),stall_fraction=len(stalled)/max(1,len(trans)),
            stall_segments=len(segments),stall_duration_s=sum(x['dt'] for x in stalled),
            issued_during_stall_m=sum(x['expected_m'] for x in stalled),
            actual_path_during_stall_m=sum(x['actual_path_m'] for x in stalled),
            map_error_change_during_stall_m=sum(x['map_error_change_m'] for x in stalled),
            control_error_change_during_stall_m=sum(x['control_error_change_m'] for x in stalled),
            longest_stalls=sorted(segments,key=lambda x:x['duration_s'],reverse=True)[:5],
            map_error_m=stats([p['map_error_m'] for p in predictions]),
            control_error_m=stats([p['control_error_m'] for p in predictions]),
            map_frame_jump_m=jumps([p['map'] for p in predictions]),
            control_frame_jump_m=jumps([p['control'] for p in predictions]),
            gated_frames=sum(x['gated'] for x in intervals),gate_segments=len(gate_segments),
            gated_duration_s=sum(x['dt'] for x in intervals if x['gated']),
            gated_stall_intervals=sum(x['gated'] for x in stalled),
            gated_moving_intervals=sum(x['gated'] for x in moving),moving_intervals=len(moving),
            flow_status_counts=dict(Counter(x.get('status','off') for x in flows)),
            recovery_counts=dict(Counter(x.get('recovery','off') for x in flows)),
            recovery_events=[e for x in flows for e in x.get('recovery_events',[])],
            rgb_during_stall={k:stats([x[k] for x in stalled if x[k] is not None]) for k in ('median_px','mean_abs_diff')},
            rgb_during_motion={k:stats([x[k] for x in moving if x[k] is not None]) for k in ('median_px','mean_abs_diff')},
            baseline_off_replay_max_abs_error=max(abs(p['nominal'][i]-p['control'][i]) for p in predictions for i in range(3))
                if not any(flows) else None)
        detail.extend(dict(run=run.name,robot=rid,**x) for x in intervals)
    return output,detail


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--horizon',type=float);args=parser.parse_args()
    score,detail=evaluate(args.run,args.horizon)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'evaluation.json').write_text(json.dumps(score,indent=2)+'\n')
    raw=(json.dumps(detail,indent=2)+'\n').encode();p=args.output/'intervals.json.zst'
    subprocess.run(['zstd','-q','-o',str(p)],input=raw,check=True)
    assert subprocess.check_output(['zstd','-dc',str(p)])==raw
    print(json.dumps({r:{k:v for k,v in x.items() if k in ('status','stall_duration_s','map_error_m','control_error_m','gated_frames')} for r,x in score.items()}))
