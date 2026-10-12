"""Offline saved-frame audit only; no simulator construction, provider or truth input."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np

from harness.active_camera import SEARCH
from harness.e2e_rgb_vo import VOFusion, image_mask, floor_mask, _servo_key
from harness.self_pulse_rotation import RotationPulseOdometry
from scripts.replay_e2e_vo import rows

CASES = [('e2e14-a-s61001-r2', 'r2'), ('e2e14-a-s61002-r2', 'r1'),
         ('e2e14-a-s61003-r2', 'r2'), ('e2e14-a-s61004-r2', 'r1')]


def audit(raw_root, image_root):
    results=[];hashes={};details=[]
    for run,rid in CASES:
        raw=raw_root/run/'raw';base=raw/'robots'/rid
        frames=rows(base/'frames.jsonl');origin=frames[0]['sim_time']
        commands=[{**r,'t':round(r['t']-origin,8)} for r in rows(base/'commands.jsonl')
                  if r['t']>=origin-1e-6]
        for name in ('frames.jsonl.zst','commands.jsonl'):
            p=base/name;hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        if list(raw.glob('robots/*/inputs/range.jsonl*')):
            raise ValueError('New range evidence found: implement real reading replay, do not ignore it')
        drivers={};fusions={};active={}
        for key,fallback in (('v2','pulse_gate'),('us','ultrasonic')):
            d=RotationPulseOdometry();d.command(dict(t=0.,kind='initial_servo_command',pulses=SEARCH))
            drivers[key]=d;fusions[key]=VOFusion(d,fallback=fallback);active[key]=False
            d.motion_filter=(lambda k:lambda delta,q:fusions[k].motion_filter(delta,q) if active[k] else (delta,q))(key)
        cursor=0;count=0;equal=0;status=Counter();last=None;command_kinds=Counter()
        for frame in frames:
            t=round(frame['sim_time']-origin,8)
            while cursor<len(commands) and commands[cursor]['t']<t-1e-8:
                command=commands[cursor];cursor+=1;command_kinds[command['kind']]+=1
                for key in drivers:
                    fusions[key].command(command);drivers[key].command(command)
            p=image_root/run/'raw'/frame['path'];result={}
            if p.exists():
                data=p.read_bytes();sha=hashlib.sha256(data).hexdigest()
                if sha!=frame['sha256']:raise ValueError('IMAGE_HASH_MISMATCH')
                hashes[str(p)]=sha
                rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
                servo={int(k):v for k,v in frame['commanded_servo'].items()}
                for key,f in fusions.items():
                    result[key]=f.observe(t=t,frame_id=frame['frame_id'],rgb=rgb,servo=servo,sha256=sha)
                count+=1;status[result['us']['status']]+=1
                details.append(dict(run=run,robot=rid,frame_id=frame['frame_id'],t=t,
                    **{k:{name:r.get(name) for name in ('status','fusion','command_delta','fused_delta','tracks','ultrasonic')}
                       for k,r in result.items()}))
                last=(rgb,servo,frame['frame_id'])
            else:
                for f in fusions.values():f.skip(t)
            for key,d in drivers.items():
                active[key]=True;d.advance(t);active[key]=False;fusions[key].finish_interval()
            if p.exists():
                equal+=int(drivers['v2'].pose==drivers['us'].pose and
                           np.array_equal(drivers['v2'].covariance,drivers['us'].covariance) and
                           result['v2']['fusion']==result['us']['fusion'])
        rgb,servo,frame_id=last
        mask=image_mask(rgb,servo)>0;static=floor_mask(_servo_key(servo))>0
        # Manually inspected common upper-wall ROI in these four saved RGBs.
        # Conservative visual annotation; no simulator segmentation or pose.
        roi=np.zeros((480,640),bool);roi[110:170,100:540]=True
        pts=cv2.goodFeaturesToTrack(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),maxCorners=120,
            qualityLevel=.01,minDistance=10,mask=(mask*255).astype(np.uint8),blockSize=7)
        nroi=0 if pts is None else sum(100<=x<540 and 110<=y<170 for x,y in pts[:,0])
        results.append(dict(run=run,robot=rid,saved_frames=count,fallback_equal=equal,vo_status=dict(status),
            command_kinds=dict(command_kinds),range_history_files=0,us_zero=fusions['us'].counts['us_zero'],
            mask=dict(frame_id=frame_id,image_shape=list(rgb.shape),static_mask_px=int(static.sum()),
                image_mask_px=int(mask.sum()),wall_roi_xyxy=[100,110,540,170],wall_roi_px=int(roi.sum()),
                admitted_wall_roi_px=int((roi&mask).sum()),admitted_fraction=float((roi&mask).sum()/mask.sum()),
                corners=None if pts is None else len(pts),wall_roi_corners=int(nroi))))
    return results,hashes,details


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True)
    p.add_argument('--image-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();cv2.setNumThreads(1)
    results,hashes,details=audit(a.raw_root,a.image_root)
    a.output.mkdir(exist_ok=True,parents=True)
    out=dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
             simulation=False,model_calls=0,ultrasonic_replay='unavailable: no recorded ranges',
             n=sum(r['fallback_equal'] for r in results),N=sum(r['saved_frames'] for r in results),
             cases=results,scope='fixed issued-command replay; v2 fallback equivalence, not ZUPT accuracy or E2E success')
    (a.output/'offline-audit.json').write_text(json.dumps(out,indent=1)+'\n')
    (a.output/'input-hashes.json').write_text(json.dumps(hashes,indent=1)+'\n')
    data=json.dumps(details).encode()+b'\n'
    target=a.output/'replay-detail.json.zst'
    subprocess.run(['zstd','-q','-f','-o',str(target)],input=data,check=True)
    assert subprocess.check_output(['zstd','-dc',str(target)])==data
    print(json.dumps(out,indent=1))


if __name__=='__main__':main()
