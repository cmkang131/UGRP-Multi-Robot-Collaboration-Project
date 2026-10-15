"""CPU gcp2-only review of available actor RGB after probe finalization error.

The failed close lost the qpos/ring archive. Missing overview/r2 and the final
0.8s frame are explicitly marked, never reconstructed from commands.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from simalt_host import gcp2_identity


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('raw','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();host=gcp2_identity()
    if host['instance']!='ugrp-sim-gcp2':p.error('analysis remains on CPU gcp2')
    a.out.mkdir(parents=True,exist_ok=False)
    import cv2
    import numpy as np
    reports=[]
    for i in (0,1):
        folder=a.out/f'world-{i:03d}';folder.mkdir()
        actual=sorted((a.raw/f'probe-r3/inputs/world-{i:03d}/generation-001/rgb/r1').glob('*.jpg'))
        if len(actual)!=8:raise ValueError('expected8 saved ACT input frames; no filling missing RGB')
        frames=[]
        for k,path in enumerate(actual):
            frame=np.zeros((240,960,3),np.uint8)
            frame[:,320:640]=cv2.resize(cv2.imread(str(path)),(320,240))
            for x,label in ((5,'overview NOT RECORDED'),(325,'r1 actual Warp RGB'),(645,'r2 NOT RECORDED')):
                cv2.putText(frame,label,(x,18),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
            cv2.putText(frame,f'SIM {k/10:.1f}s | available actor input; probe HOST_ERROR, no task verdict',(5,232),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
            cv2.imwrite(str(folder/f'{k:03d}.jpg'),frame);frames.append(frame)
        whole=[0,5,7]
        cv2.imwrite(str(folder/'whole-2hz.jpg'),np.concatenate([frames[k] for k in whole],axis=0))
        cv2.imwrite(str(folder/'available-10hz.jpg'),np.concatenate(frames,axis=0))
        video=folder/'review-2x.mp4'
        subprocess.run(['ffmpeg','-loglevel','error','-threads','1','-framerate','20','-i',str(folder/'%03d.jpg'),'-vf','fps=30','-c:v','libx264','-crf','26','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],check=True)
        if video.stat().st_size>8*1024**2:raise ValueError('video exceeds8MiB')
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,width,height','-of','json',str(video)],text=True))
        reports.append(dict(world=i,sim_range=[0.,.7],available_frames=8,whole_2hz_indices=whole,ten_hz_indices=list(range(8)),video=probe))
    (a.out/'review-summary.json').write_text(json.dumps(dict(host=host,worlds=reports,
        data_gap='probe-r3 finalization TypeError lost0.8s last frame, qpos NPZ and circular ring; overview/r2 unavailable',
        completed_successes_available=0,completed_evaluation_failures_available=0,
        cause_claim='no policy failure cause claimed; backend timing and initialization only'),indent=2)+'\n')


if __name__=='__main__':main()
