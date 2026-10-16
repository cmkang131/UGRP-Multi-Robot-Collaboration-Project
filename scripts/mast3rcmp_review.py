"""Own-camera review artifacts on the source VM; never launches a GUI.

The recording is sampled at its declared 10 Hz: all 2 Hz frames plus every
frame of the last 10 SIM seconds. The video retains all frames at 3x speed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np


def review(prepared, output):
    prepared, output = Path(prepared), Path(output)
    receipt=json.loads((prepared/'input-receipt.json').read_text())
    frames=receipt['frames']
    output.mkdir(exist_ok=False)
    for name,indices in [('all-2hz',range(0,len(frames),5)),
            ('last10s-10hz',[i for i,f in enumerate(frames) if f['t_sim_s']>=frames[-1]['t_sim_s']-10])]:
        tiles=[]
        for i in indices:
            f=frames[i]
            image=cv2.imread(f['path'])
            tile=cv2.resize(image,(160,120),interpolation=cv2.INTER_AREA)
            cv2.putText(tile,f"{i} / {f['t_sim_s']:.1f}s",(3,14),0,.4,(0,255,255),1)
            tiles.append(tile)
        columns=9
        mosaic=np.zeros(((len(tiles)+columns-1)//columns*120,columns*160,3),np.uint8)
        for j,tile in enumerate(tiles):mosaic[j//columns*120:(j//columns+1)*120,j%columns*160:(j%columns+1)*160]=tile
        cv2.imwrite(str(output/(name+'.jpg')),mosaic)
    command=['ffmpeg','-nostdin','-hide_banner','-loglevel','error',
        '-framerate','10','-i',str(prepared/'rgb/%08d.png'),'-vf','setpts=PTS/3',
        '-r','30','-c:v','libx264','-crf','25','-pix_fmt','yuv420p',str(output/'own-3x.mp4')]
    subprocess.run(command,check=True)
    probe=subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output/'own-3x.mp4')])
    (output/'ffprobe.json').write_bytes(probe)
    result=dict(frames=len(frames),all_2hz_frames=len(range(0,len(frames),5)),
        final10s_frames=sum(f['t_sim_s']>=frames[-1]['t_sim_s']-10 for f in frames),
        input_receipt_sha256=hashlib.sha256((prepared/'input-receipt.json').read_bytes()).hexdigest(),
        commands=[command],gui_launches=0,truth_reads=0,
        files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in output.iterdir()})
    (output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();review(a.prepared,a.output)
