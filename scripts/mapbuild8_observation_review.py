"""gcp5 diagnostic scan overlays; no simulation or estimator changes."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import cv2
    import numpy as np
    from harness.e2e_rgb_vo import K,D
    cv2.setNumThreads(1);frames=json.loads((a.input/'own.json').read_text())['frames'];scans=json.loads((a.scans/'scans.json').read_text())
    a.output.mkdir(parents=True,exist_ok=False);mx,my=cv2.fisheye.initUndistortRectifyMap(K,D,np.eye(3),K,(640,480),cv2.CV_32FC1)
    images=[];records=[]
    for i in a.indices:
        f=frames[i];s=scans[i];file=a.input/f['rgb']
        if hashlib.sha256(file.read_bytes()).hexdigest()!=f['sha256']:raise ValueError('RGB_CHANGED')
        im=cv2.remap(cv2.imread(str(file)),mx,my,cv2.INTER_LINEAR)
        for col in s['columns']:
            if col['status']=='hit':cv2.circle(im,(col['column'],round(col['row'])),2,(0,255,255),-1)
        cv2.putText(im,'SIM %.1f - scan contacts (yellow)'%f['t'],(8,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)
        cv2.putText(im,'own PWM '+str(f['servo']),(8,460),cv2.FONT_HERSHEY_SIMPLEX,.35,(255,255,255),1)
        name='scan-%05d.jpg'%i;cv2.imwrite(str(a.output/name),im)
        images.append(im);records.append(dict(index=i,t=f['t'],source_rgb=str(file),source_sha256=f['sha256'],scan_segments=len(s['segments']),qualification=s.get('qualification'),overlay=name))
    while len(images)%2:images.append(np.zeros_like(images[0]))
    sheet=np.vstack([np.hstack(images[k:k+2]) for k in range(0,len(images),2)]);cv2.imwrite(str(a.output/'scan-overlay-sheet.jpg'),sheet)
    (a.output/'receipt.json').write_text(json.dumps(dict(raw=str(a.input),scans=str(a.scans),records=records,reproduction=sys.argv,
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.glob('*.jpg')}),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','scans','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--indices',type=int,nargs='+',required=True);main(p.parse_args())
