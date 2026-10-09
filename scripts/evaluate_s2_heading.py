"""Post-run heading comparison and 4x video from saved files; never controller input."""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np

from scripts.replay_s2_heading import command_time
from scripts.run_final_environment_checks import write


def read_rows(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def intervals(record, final_time):
    states=[e for e in record['events'] if e['event']=='state']
    return [(e['t'], states[i+1]['t'] if i+1<len(states) else final_time)
            for i,e in enumerate(states) if e['state']=='carry']


def contact_summary(rows, mask):
    durations=[max(0.,rows[i+1]['t']-r['t']) if i+1<len(rows) else 0 for i,r in enumerate(rows)]
    return dict(samples=sum(mask),sampled_s=sum(d for d,m in zip(durations,mask) if m),
        episodes=sum(m and (i==0 or not mask[i-1]) for i,m in enumerate(mask)))


def motion_metrics(truth):
    """Evaluation-only finite-difference velocity; frozen reporting threshold."""
    t=np.array([r['t'] for r in truth]);dt=np.diff(t)
    xy=np.array([r['robot_xyz_m'][:2] for r in truth]);v=np.diff(xy,axis=0)/dt[:,None]
    yaw=np.unwrap([r['robot_yaw_rad'] for r in truth]);yaw=(yaw[:-1]+yaw[1:])/2
    speed=np.linalg.norm(v,axis=1);moving=speed>=.01
    angle=(np.arctan2(v[:,1],v[:,0])-yaw+math.pi)%(2*math.pi)-math.pi
    lateral=-np.sin(yaw)*v[:,0]+np.cos(yaw)*v[:,1]
    elapsed=float(dt[moving].sum());distance=float((speed[moving]*dt[moving]).sum())
    return dict(min_speed_m_s=.01,moving_s=elapsed,path_m=distance,
        direction_within_20deg_fraction=float(dt[moving&(abs(angle)<=math.radians(20))].sum()/elapsed) if elapsed else None,
        lateral_speed_fraction=float((abs(lateral[moving])*dt[moving]).sum()/distance) if distance else None,
        definition='actual velocity vs midpoint chassis yaw, time fraction within +/-20deg; integral abs(body lateral velocity) / integral speed; speed>=0.01m/s; GT evaluation only')


def score(raw):
    raw=Path(raw)
    result=json.loads((raw/'result.json').read_text())
    record=json.loads((raw/'student_record.json').read_text())
    truth=read_rows(raw/'eval_only/trajectory.jsonl')
    walls=read_rows(raw/'eval_only/wall-contacts.jsonl')
    all_contacts=read_rows(raw/'eval_only/contacts.jsonl')
    times=np.array([r['t'] for r in truth])
    if len(times)<2 or np.any(np.diff(times)<=0):
        raise ValueError('missing/nonmonotonic evaluation trajectory')
    carry=intervals(record,times[-1])
    yaw=np.unwrap([math.atan2(np.asarray(r['cyan_rotation']).reshape(3,3)[1,0],
                             np.asarray(r['cyan_rotation']).reshape(3,3)[0,0]) for r in truth])
    robot=np.unwrap([r['robot_yaw_rad'] for r in truth])
    angles=[]
    for start,end in carry:
        idx=(times>=start)&(times<end)
        if not idx.any():continue
        a=yaw[idx];relative=np.unwrap(a-robot[idx])
        angles.append(dict(start_s=start,end_s=end,
            box_yaw_range_deg=float(np.degrees(np.ptp(a))),
            box_max_abs_from_carry_start_deg=float(np.degrees(np.max(abs(a-a[0])))),
            relative_box_robot_yaw_range_deg=float(np.degrees(np.ptp(relative))),
            relative_max_abs_from_carry_start_deg=float(np.degrees(np.max(abs(relative-relative[0]))))))
    contacts={}
    for category in ('body','wheel','finger','cargo','any'):
        mask=[bool(r['contacts']) if category=='any' else any(c['category']==category for c in r['contacts']) for r in walls]
        contacts[category]=contact_summary(walls,mask)
    def robot_pair(c):
        a,b=c['geom1'].split('__')[0],c['geom2'].split('__')[0]
        return a!=b and 'r3' in (a,b) and a in ('r1','r2','r3') and b in ('r1','r2','r3')
    peers=contact_summary(all_contacts,[any(robot_pair(c) for c in r['contacts']) for r in all_contacts])
    static=json.loads((raw/'inputs/static_map.json').read_text())
    door=next(p for p in static['passages'] if p['id']=='door_1')
    x,y=door['center_m']; half_width=door.get('width_m',.5)/2
    crossings={}
    for key,label in (('robot_xyz_m','robot'),('cyan_xyz_m','cargo')):
        before=False;crossed=[]
        for r in truth:
            px,py=r[key][:2]
            if px < x-.025:before=True
            if before and px > x+.025:
                crossed.append(dict(t=r['t'],y_m=py,within_opening=abs(py-y)<=half_width))
                before=False
        crossings[label]=dict(crossings=crossed,passed_center=any(e['within_opening'] for e in crossed),
            definition='center crossed divider west-to-east within authored opening; full clearance assessed separately by contact logs')
    active=[]
    for e in record.get('active_localization',{}).get('events',[]):
        end=e.get('completed_t',e['t']+e['action']['added_s'])
        idx=(times>=e['t'])&(times<=end)
        a=robot[idx]
        if len(a):active.append(dict(start_s=e['t'],end_s=end,max_abs_deg=float(np.degrees(max(abs(a-a[0]))))))
    return dict(seed=result['seed'],raw=str(raw),source_sha=result['source_sha'],
        condition=record.get('heading_mode',{}).get('option','off_v141'),
        success=result['evaluation']['success'],evaluation=result['evaluation'],
        status=result['status'],failure=result.get('failure') or record.get('failure'),
        commands=command_time(record['commands'],times[-1]),carry_angles=angles,
        wall_contacts=contacts,robot_contacts=peers,motion=motion_metrics(truth),door=crossings,active_observations=active,
        active_actual_90deg_exceeded=any(a['max_abs_deg']>90 for a in active),
        wall_per_sim=result['wall_per_sim'],wall_s=result['wall_s'],sim_s=result['total_sim_s'],
        commands_issued=result['commands_issued'],model_calls=result['model_calls'],
        carry_visibility=result.get('posthoc_evaluation',{}).get('actual_visibility'),
        provenance={str(p.relative_to(raw)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (raw/'result.json',raw/'student_record.json',raw/'eval_only/trajectory.jsonl',raw/'eval_only/wall-contacts.jsonl',raw/'eval_only/contacts.jsonl')},
        scope='post-run evaluation only; simulated plant, no hardware success claim')


def video(raw, output):
    """Recorded wrist on left; orthographic saved ground-truth path on right."""
    if output.exists():raise ValueError('preserve existing video')
    frames=read_rows(raw/'robots/r3/frames.jsonl')
    truth=read_rows(raw/'eval_only/trajectory.jsonl')
    times=np.array([r['t'] for r in truth])
    static=json.loads((raw/'inputs/static_map.json').read_text())
    width,height=640,480
    def point(xy):return tuple(np.rint([(xy[0]+1.2)/6.8*width,(1.6-xy[1])/4.9*height]).astype(int))
    background=np.full((height,width,3),245,np.uint8)
    for obstacle in static['obstacles']:
        c=np.array(obstacle['center_m']);h=np.array(obstacle['half_extents_m'])
        cv2.rectangle(background,point(c-h),point(c+h),(70,70,70),-1)
    for region in static['regions'].values():
        c=np.array(region['center_m']);h=np.array(region['half_extents_m'])
        cv2.rectangle(background,point(c-h),point(c+h),(170,190,170),1)
    output.parent.mkdir(parents=True,exist_ok=True)
    process=subprocess.Popen(['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','bgr24',
        '-s','1280x480','-r','20','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast',
        '-crf','24','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],stdin=subprocess.PIPE)
    selected=[];rgb_times=np.array([f['sim_time'] for f in frames]);last=0
    trail=[]
    try:
        # 0.2 SIM seconds per 20fps video frame = exactly 4x, even for missing RGB.
        for t in np.arange(rgb_times[0],rgb_times[-1]+1e-6,.2):
            i=max(0,int(np.searchsorted(rgb_times,t,side='right')-1));f=frames[i]
            data=(raw/f['path']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=f['sha256']:raise ValueError('RGB source hash mismatch')
            rgb=cv2.imdecode(np.frombuffer(data,np.uint8),1)
            j=max(0,int(np.searchsorted(times,t,side='right')-1));q=truth[j]
            trail.extend(point(r['robot_xyz_m'][:2]) for r in truth[last:j+1]);last=j+1
            top=background.copy()
            if len(trail)>1:cv2.polylines(top,[np.array(trail)],False,(210,110,30),2)
            p=point(q['robot_xyz_m'][:2]);yaw=q['robot_yaw_rad']
            cv2.circle(top,p,7,(210,110,30),-1)
            cv2.arrowedLine(top,p,point(np.array(q['robot_xyz_m'][:2])+.3*np.array([math.cos(yaw),math.sin(yaw)])),(20,20,200),2)
            cv2.circle(top,point(q['cyan_xyz_m'][:2]),5,(210,180,0),-1)
            cv2.putText(top,'EVAL ONLY: actual robot / cargo path',(12,24),cv2.FONT_HERSHEY_SIMPLEX,.58,(20,20,20),1)
            canvas=np.hstack([rgb,top])
            cv2.putText(canvas,f'SIM {t:.1f}s | 4x | saved wrist RGB',(10,465),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,255,255),2)
            process.stdin.write(canvas.tobytes());selected.append(dict(t=float(t),path=f['path'],sha256=f['sha256']))
    finally:
        process.stdin.close()
        code=process.wait()
    if code:raise RuntimeError('ffmpeg failed')
    subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
        'format=duration:stream=width,height,r_frame_rate,nb_frames','-of','json',str(output)]))
    write(output.with_suffix('.json'),dict(path=str(output),speed=4,output_frames=len(selected),
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),full_decode=True,probe=probe,
        source_frames=selected,right_panel='saved evaluation trajectory, not a controller observation'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--video',type=Path)
    a=p.parse_args()
    if a.output.exists():raise ValueError('preserve prior report')
    write(a.output,score(a.source))
    if a.video:video(a.source,a.video)


if __name__=='__main__':main()
