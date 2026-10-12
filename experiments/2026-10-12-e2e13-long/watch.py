"""Finite read-only progress/initial health; only initial HOST_ERROR or wall cap stops."""
from pathlib import Path
import datetime, hashlib, json, math, os, signal, subprocess, sys, time

SOURCE=Path(sys.argv[1]);sys.path.insert(0,str(SOURCE))
from scripts.evaluate_e2e8 import inspect, rows
from harness.e2e_result_writer import write
ROOT=Path.home()/'ugrp-sim'
NAMES=sys.argv[2:]
checked=set();done=set();last={};stopped=set();success_seen=set()


def obj(path):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return {}


def last_row(path):
    if not path.exists():return {}
    with path.open('rb') as stream:
        stream.seek(0,2);stream.seek(max(0,stream.tell()-262144));lines=stream.read().splitlines()
    for line in reversed(lines):
        try:return json.loads(line)
        except json.JSONDecodeError:pass
    return {}


def boundary_values(raw,rid):
    # Saved own RGB/issued servo only. Never feeds a value back to the run.
    import cv2,numpy as np
    from harness.e2e_rgb_gate import boundary
    from harness.active_camera import goal_camera
    from harness.floor_goal_self_mask import body_envelopes,project_envelopes
    frame=last_row(raw/f'robots/{rid}/frames.jsonl');own=last_row(raw/f'robots/{rid}/ownmap.jsonl')
    if not frame or not own:return {'status':'missing_frame'}
    if frame['frame_id']!=own['frame_id']:
        frame=next((r for r in reversed(rows(raw/f'robots/{rid}/frames.jsonl')) if r['frame_id']==own['frame_id']),{})
    if not frame or frame['sha256']!=own['sha256']:return {'status':'frame_pair_not_ready'}
    path=raw/frame['path'];image=cv2.imread(str(path))
    if image is None:return {'status':'missing_image'}
    rgb=cv2.cvtColor(image,cv2.COLOR_BGR2RGB);servo={int(k):v for k,v in frame['commanded_servo'].items()}
    h,w=rgb.shape[:2];origin,axes=goal_camera(servo,'camera_v3')
    mask=project_envelopes(body_envelopes(servo,'camera_v3'),origin,axes,w,h)
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);blue=cv2.inRange(hsv,(90,70,35),(135,255,255));blue[mask]=0
    contours,_=cv2.findContours(blue,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);candidates=[]
    for contour in sorted(contours,key=cv2.contourArea,reverse=True)[:4]:
        area=float(cv2.contourArea(contour));quad=cv2.approxPolyDP(contour,.02*cv2.arcLength(contour,True),True).reshape(-1,2)
        region=np.zeros((h,w),np.uint8);cv2.fillPoly(region,[quad],255)
        inner=cv2.erode(region,np.ones((5,5),np.uint8))!=0
        white=((hsv[:,:,1]<55)&(hsv[:,:,2]>180)&inner).astype(np.uint8)
        _,_,stats,_=cv2.connectedComponentsWithStats(white)
        candidates.append(dict(area_px2=area,vertices=len(quad),convex=bool(cv2.isContourConvex(quad)),
            image_clipped=bool(quad[:,0].min()<=2 or quad[:,1].min()<=2 or quad[:,0].max()>=w-3 or quad[:,1].max()>=h-3),
            self_mask_overlap=bool(np.any(mask&(cv2.dilate(region,np.ones((5,5),np.uint8))!=0))),
            white_islands_ge9px=int(sum(v[cv2.CC_STAT_AREA]>=9 for v in stats[1:]))))
    return dict(status='saved_rgb_evaluation',frame_id=frame['frame_id'],sim_s=frame['sim_time'],
        frame_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),complete_boundary=boundary(rgb,servo,own['pose_own_m']),
        candidates=candidates,thresholds=dict(min_area_px2=100,vertices=4,white_islands=3),feedback_to_controller=False)


def snapshot(run):
    raw=run/'raw';p=obj(raw/'e2e-progress.json');meta=obj(run/'RUN_META.json')
    value=dict(run=run.name,unix=time.time(),elapsed_since_submit_s=time.time()-meta['started_unix'],
        progress=p,stage_milestones=obj(raw/'stage-milestones.json'),boundary={},evaluation_only=True)
    for rid in ('r1','r2'):
        try:value['boundary'][rid]=boundary_values(raw,rid)
        except Exception as exc:value['boundary'][rid]={'error':type(exc).__name__+':'+str(exc)}
    return value


def stop(run,reason):
    if run.name in stopped:return
    p=obj(run/'PROCESS.json')
    try:start=Path(f'/proc/{p["pid"]}/stat').read_text().rsplit(')',1)[1].split()[19]
    except (FileNotFoundError,KeyError):return
    if p['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip() and p['start']==start:
        write(run/'HEALTH_STOP.json',dict(reason=reason,unix=time.time(),pid=p['pid']))
        os.kill(p['pid'],signal.SIGINT);stopped.add(run.name)


deadline=time.time()+7.5*3600
while len(done)<len(NAMES) and time.time()<deadline:
    for name in NAMES:
        run=ROOT/'runs'/name
        if name in done or not (run/'RUN_META.json').exists():continue
        age=time.time()-obj(run/'RUN_META.json')['started_unix'];ended=(run/'EXIT').exists()
        result=obj(run/'raw/result.json')
        if name not in success_seen and result.get('finalization_complete') and all(result.get(k)
                for k in ('LLM_operated','own_map_completed','start_to_finish_transport')):
            write(ROOT/(name+'-THREE_CONDITIONS.json'),dict(run=name,unix=time.time(),result=result))
            success_seen.add(name)
            print(json.dumps(dict(run=name,three_conditions=True,sim_s=result.get('sim_s'),wall_s=result.get('wall_s'))),flush=True)
        if name not in checked and (age>=240 or ended):
            try:
                h=inspect(run/'raw');h['checks'].pop('deepinfra_normal',None)
                h['checks']['normal_model_response']=any(r['normal'] for r in h['responses'])
                h['checks']['model_response_accepted']=h['progress'].get('first_model_response',False)
                h['checks']['translation_command']=all(any(abs(c.get('forward',0))+abs(c.get('left',0))>0
                    for c in rows(run/f'raw/robots/{rid}/commands.jsonl')) for rid in ('r1','r2'))
                h['recent_commands']={rid:[{k:c.get(k) for k in ('t','kind','forward','left','turn','duration_s')}
                    for c in rows(run/f'raw/robots/{rid}/commands.jsonl')[-50:]] for rid in ('r1','r2')}
                h['checks']['recent_translation_command']=all(any(abs(c.get('forward') or 0)+abs(c.get('left') or 0)>0
                    for c in recent) for recent in h['recent_commands'].values())
                h.update(passed=all(h['checks'].values()),elapsed_since_submit_s=age,unix=time.time())
                write(run/'initial-health.json',h);checked.add(name)
                if not h['passed'] and not ended:stop(run,'INITIAL_OPERATIONAL_HEALTH_FAILED')
                print(json.dumps(dict(run=name,initial_passed=h['passed'],elapsed_s=age,checks=h['checks'])),flush=True)
            except Exception as exc:
                write(run/'HEALTH_INSPECTION_ERROR.json',dict(type=type(exc).__name__,message=str(exc),unix=time.time()))
                if age>=285 and not ended:stop(run,'INITIAL_HEALTH_UNVERIFIED_BY_285S')
        if ended or (age>=240 and time.time()-last.get(name,0)>=1800):
            value=snapshot(run);write(run/('final-health.json' if ended else 'latest-health.json'),value)
            with (ROOT/'e2e13-long-progress.jsonl').open('a') as stream:stream.write(json.dumps(value)+'\n')
            print(json.dumps(dict(run=name,ended=ended,sim_s=value['progress'].get('sim_s'),phase=value['progress'].get('phase'))),flush=True)
            last[name]=time.time()
            if ended:
                result=obj(run/'raw/result.json')
                if name not in success_seen and all(result.get(k) for k in ('LLM_operated','own_map_completed','start_to_finish_transport')):
                    write(ROOT/(name+'-THREE_CONDITIONS.json'),dict(run=name,unix=time.time(),result=result))
                done.add(name)
        if not ended and age>=25200:stop(run,'AUTHORIZED_SEVEN_HOUR_WALL_CAP')
    time.sleep(5)
write(ROOT/'e2e13-long-watch-result.json',dict(completed=sorted(done),expected=NAMES,initial_checked=sorted(checked),stopped=sorted(stopped)))
