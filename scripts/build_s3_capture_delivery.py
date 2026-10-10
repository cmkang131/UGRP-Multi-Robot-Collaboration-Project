"""Saved-RGB-only diagnostic videos and derived TensorBoard views; no simulation."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import cv2
import numpy as np


def video(raw,out,rid):
    frames=[[json.loads(s) for s in (raw/f'robots/{r}/frames.jsonl').read_text().splitlines()] for r in ('r1','r2','r3')]
    if len({len(f) for f in frames})!=1:raise ValueError('unsynchronized own-camera rows')
    path=out/'execution.mp4'
    proc=subprocess.Popen([shutil.which('ffmpeg'),'-v','error','-f','rawvideo','-pixel_format','bgr24',
        '-video_size','1920x480','-framerate','20','-i','-','-an','-c:v','libx264','-threads','1',
        '-preset','veryfast','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],stdin=subprocess.PIPE)
    for triple in zip(*frames):
        imgs=[]
        for camera,frame in zip(('r1','r2','r3'),triple):
            image=cv2.imread(str(raw/frame['path']))
            if image is None:raise ValueError('missing saved RGB')
            cv2.putText(image,f'{camera} | target {rid} | eval-only open loop | SIM {frame["sim_time"]:.2f} | 4x',
                (8,25),cv2.FONT_HERSHEY_SIMPLEX,.42,(255,255,255),1)
            imgs.append(image)
        proc.stdin.write(np.hstack(imgs).tobytes())
    proc.stdin.close()
    if proc.wait()!=0:raise RuntimeError('ffmpeg failed')
    cap=cv2.VideoCapture(str(path));ok,first=cap.read();n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);cap.release()
    if not ok or n!=len(frames[0]) or fps!=20.:raise ValueError('video decode/count/rate mismatch')
    cv2.imwrite(str(out/'first-frame.jpg'),first)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),frames=n,fps=fps,
        duration_s=n/fps,playback=4,source='saved nominal own RGB at5Hz; no rendered replay; evaluation-only open-loop grasp')


def main():
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--summary',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('Oracle x86 postprocessing only')
    s=json.loads(a.summary.read_text());a.output.mkdir(parents=True,exist_ok=False)
    source=dict(path=str(a.summary.resolve()),sha256=hashlib.sha256(a.summary.read_bytes()).hexdigest())
    common=dict(schema='ugrp.s3_capture_derived_view.v1',derived_view_only=True,host='oracle-x86',
        source_sha=s['runs'][0]['source_sha'],clock='SIM',model_calls=0,offline_source=source,
        offline_scalar_scope='Evaluation-only open-loop capture grid / pulse system identification; not closed-loop alignment, delivery or real robot success')
    for rid,robot in s['robots'].items():
        out=a.output/rid;out.mkdir();raw=a.cohort/f's3fix14-capture-{rid}-yaw1-r1/raw/trial-12'
        v=video(raw,out,rid)
        scalars={f'offline/{k}':robot[k] for k in ('n','grasp_n','lift_n','capture_n')}
        scalars.update({'offline/host_errors':robot['causes'].get('HOST_ERROR',0),
            'offline/physical_stops':robot['causes'].get('PHYSICAL_STOP',0),
            'offline/profile_admissible':int(robot['selection']['admissible'])})
        value=dict(common,seed=14201,case=rid,policy='open-loop capture grid75; partner nominal',status='COMPLETED_DIAGNOSTIC',
            sim_s=sum(t.get('sim_s',0) for t in robot['trials']),wall_s=sum(t['wall_s'] for t in robot['trials']),
            offline_scalars=scalars,video=v,hparam_metrics=['offline/capture_n','offline/n','offline/profile_admissible','result/wall_s'])
        (out/'result.json').write_text(json.dumps(value,indent=2)+'\n')
    for level in (15,20,25,35):
        out=a.output/f'pulse-{level}';out.mkdir();points=[x for x in s['pulses'] if abs(x['speed'])==level]
        scalars={}
        for row in points:
            prefix='offline/'+row['axis']+('_positive' if row['speed']>0 else '_negative')
            for k in ('n','median','max_abs_step','spread','conservative_step_bound'):scalars[prefix+'/'+k]=row[k]
        scalars['offline/hardware_admissible']=int(level==35)
        value=dict(common,case=f'wheel-{level}',policy='fixed100ms pulse; six setups; hardware floor35',
            status='COMPLETED_DIAGNOSTIC',offline_scalars=scalars,hparam_metrics=['offline/hardware_admissible'])
        (out/'result.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(dict(views=7,videos=3)))


if __name__=='__main__':raise SystemExit(main())
