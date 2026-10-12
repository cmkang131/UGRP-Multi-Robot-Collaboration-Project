"""Join existing own-RGB detections/commands with write-only evaluation motion."""
import argparse,bisect,csv,json,math
from collections import Counter
from pathlib import Path
import numpy as np
from harness.zone_s3_pair_alignment import project
from harness.zone_final_pair_vision import GRASP_RADIUS_M
from harness.zone_solo_cyan_path_heading import command_reason

def rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
def wrap(v):return math.atan2(math.sin(v),math.cos(v))
def pixel_error(config,servo,grip):
    import cv2
    from harness.s2_stiff_camera_calibration import corrected_record
    from harness.zone_final_pair_camera import floor_camera
    from harness.vision_pose_source_final import camera_key
    key=camera_key({int(k):v for k,v in servo.items()})
    original=config['extrinsic_calibration']['camera_models']['unloaded'][key]
    camera=floor_camera(corrected_record(original,config['stiff_camera_table']['poses'][key]))
    points=np.array([[*grip,.032],[GRASP_RADIUS_M,0.,.032]])
    optical=(points-np.asarray(camera['origin_m']))@np.asarray(camera['rotation'])
    k=np.asarray(config['extrinsic_calibration']['intrinsics_K']);d=np.asarray(config['extrinsic_calibration']['fisheye_D'])
    pixels=cv2.fisheye.projectPoints(optical.reshape(1,2,3),np.zeros(3),np.zeros(3),k,d)[0].reshape(2,2)
    return (pixels[0]-pixels[1]).tolist(),pixels.tolist()

def analyze(raw,report,out):
    out.mkdir(parents=True,exist_ok=False)
    saved=json.loads(report.read_text()); b=json.loads((raw/'bundle.json').read_text())
    profiles=b['controller_config']['pulse_calibration']['profiles']; summary={}
    for rid in ('r1','r2'):
        events=[e for e in saved['stages'][rid]['pair_events'] if e['event']=='beam_obs']
        commands=rows(raw/f'robots/{rid}/commands.jsonl');ct=[r['t'] for r in commands]
        truth=rows(raw/f'eval_only/{rid}/trajectory.jsonl');tt=[r['t'] for r in truth]
        frames=rows(raw/f'robots/{rid}/frames.jsonl');ft=[r['sim_time'] for r in frames]
        table=[]
        for i,e in enumerate(events):
            t=e['sim_s'];end=events[i+1]['sim_s'] if i+1<len(events) else min(t+.4,tt[-1])
            issued=commands[bisect.bisect_left(ct,t-1e-8):bisect.bisect_left(ct,end-1e-8)]
            active=[c for c in issued if c['kind']=='mecanum' and any(c.get(a,0) for a in ('forward','left','turn'))]
            p0=truth[max(0,bisect.bisect_right(tt,t+1e-8)-1)];p1=truth[max(0,bisect.bisect_right(tt,end+1e-8)-1)]
            d=np.array(p1['robot_xyz_m'][:2])-p0['robot_xyz_m'][:2];a=p0['robot_yaw_rad'];c,s=math.cos(a),math.sin(a)
            errors=[e['grip_base_m'][0]-GRASP_RADIUS_M,e['grip_base_m'][1],e['axis_heading_rad']] if e['visible'] else None
            proposal,profile,score=project(profiles,errors) if errors else (None,None,{})
            f=frames[max(0,bisect.bisect_right(ft,t+1e-8)-1)]
            table.append(dict(t=t,frame=f['path'],frame_sha256=f['sha256'],visible=e['visible'],reason=e['reason'],posture=e.get('posture'),
                ex_m=errors[0] if errors else None,ey_m=errors[1] if errors else None,ea_rad=errors[2] if errors else None,
                phase=score.get('phase'),commands=active,replayed_proposal=proposal,goal_distance_m=score.get('goal_distance_m'),
                delta_forward_m=c*d[0]+s*d[1],delta_left_m=-s*d[0]+c*d[1],delta_yaw_rad=wrap(p1['robot_yaw_rad']-a),
                pixel_error_status='inverse projection of saved own-RGB fitted grip and fixed target through same static calibration',
                pixel_error_xy=pixel_error(b['controller_config'],f['commanded_servo'],e['grip_base_m'])[0] if errors else None,eval_only=True))
        (out/f'{rid}-frames.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in table))
        close=[r for r in table if r['goal_distance_m'] is not None and r['goal_distance_m']<=.1]
        stationary=[r for r in close if not r['commands']]
        summary[rid]=dict(observations=len(table),detected=sum(r['visible'] for r in table),phases=dict(Counter(r['phase'] for r in table)),
            final10cm=len(close),stationary_final10cm=len(stationary),last=table[-1],
            turn_sign_changes=sum(a['commands'] and b['commands'] and a['commands'][0].get('turn',0)*b['commands'][0].get('turn',0)<0 for a,b in zip(close,close[1:])),
            near_yaw_range_rad=[min(r['ea_rad'] for r in close),max(r['ea_rad'] for r in close)],
            xyz_tolerance_hit=sum(abs(r['ex_m'])<=.003 and abs(r['ey_m'])<=.003 for r in close),
            all_tolerance_hit=sum(abs(r['ex_m'])<=.003 and abs(r['ey_m'])<=.003 and abs(r['ea_rad'])<=.035 for r in close))
    summary['r3']=dict(alignment_entered=False,reason='v152 recorded localizer states contain no align')
    summary['vocabulary']={k:dict(delta=p['mean_delta'],contract=command_reason(dict(kind='mecanum',forward=p['u'] if p['axis']=='forward' else 0.,left=p['u'] if p['axis']=='left' else 0.,turn=p['u'] if p['axis']=='turn' else 0.,duration_s=p['duration_s']))) for k,p in profiles.items() if not p['loaded']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();analyze(a.raw,a.report,a.output)
