"""Finite saved-RGB feature replay only. Does not import a physics backend or read eval_only."""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
import cv2
import numpy as np
from harness.self_map_closed_loop import own_measurement
from harness.self_map_landmark_sensor import Sensor
from harness.own_map_amcl_vendor.landmarks import MapFeatures


def read_lines(path):
    if not path.exists():path=Path(str(path)+'.zst')
    data=subprocess.check_output(['zstd','-qdc',str(path)]).decode() if path.suffix=='.zst' else path.read_text()
    return [json.loads(line) for line in data.splitlines() if line]


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--static-map',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cap-frames',type=int,default=0)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    static=json.loads(a.static_map.read_text());mapped=MapFeatures(static);counts={};started=time.monotonic()
    for rid in ('r1','r2'):
        frames=read_lines(a.raw/f'robots/{rid}/frames.jsonl');lookup={f['sha256']:f for f in frames}
        own=read_lines(a.raw/f'robots/{rid}/ownmap.jsonl');sensor=Sensor(mapped.hues);last_servo=None;changed=None;count=0
        with (a.output/f'{rid}.jsonl').open('w') as out:
            for o in own[:a.cap_frames or len(own)]:
                f=lookup[o['sha256']];servo={int(k):int(v) for k,v in f['commanded_servo'].items()};t=float(o['t'])
                if servo!=last_servo:changed=t;last_servo=servo
                settled=t-changed>=(2.25 if servo.get(1,2000)<=1600 else .25)-1e-8
                points=[];features=[]
                if settled:
                    image_path=a.raw/f['path'];data=image_path.read_bytes()
                    # Source frame SHA records encoded JPEG bytes.
                    if hashlib.sha256(data).hexdigest()!=f['sha256']:raise ValueError('OWN_RGB_SHA256_MISMATCH')
                    bgr=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
                    if bgr is None:raise ValueError('OWN_RGB_DECODE_FAILED')
                    measurement=own_measurement(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),servo)
                    points=measurement['points'];features=sensor.measure(bgr,servo,measurement)
                    if len(points)>60:points=[points[i] for i in np.linspace(0,len(points)-1,60,dtype=int)]
                row=dict(robot_id=rid,t=t,physical_t=f['sim_time'],frame_id=o['frame_id'],sha256=o['sha256'],servo=servo,settled=settled,points=points,features=features,command_delta=o['stall_odometry']['command_delta'],fused_delta=o['stall_odometry'].get('applied_delta',o['stall_odometry']['fused_delta']))
                out.write(json.dumps(row,separators=(',',':'))+'\n');count+=1
                if count%50==0:
                    out.flush();print(json.dumps(dict(robot=rid,frames=count,t=t,wall_s=time.monotonic()-started)),flush=True)
        counts[rid]=count
    manifest=dict(source_raw=str(a.raw),static_map=str(a.static_map),static_map_sha256=hashlib.sha256(a.static_map.read_bytes()).hexdigest(),frames=counts,wall_s=time.monotonic()-started,scope='own RGB, commanded servo and command-derived increments only; no physics or eval input',files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in a.output.glob('*.jsonl')})
    (a.output/'summary.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest),flush=True)

if __name__=='__main__':main()
