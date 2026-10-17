"""Create own-camera review media on GCP5; no native renderer or GUI."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    a.output.mkdir(parents=True,exist_ok=False)
    rgb=a.input/'own-rgb';frames=sorted(rgb.glob('r1-*.jpg'));last=int(frames[-1].stem.split('-')[-1]);commands=[]
    # Original self RGB only. No TOP is recorded in these cohorts.
    pair=f'[0:v]scale=320:240[l];[1:v]scale=320:240[r];[l][r]hstack,drawtext=text=SIM_%{{pts\\:hms}}:fontcolor=white:fontsize=16'
    def run(command):
        subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);commands.append(command)
    for first,end,hz,label in [(0,last,2,'full'),(max(0,last-100),last,10,'terminal')]:
        for start in range(first,end+1,300 if hz==2 else 100):
            finish=min(end,start+(295 if hz==2 else 99));count=(finish-start)//(10//hz)+1
            command=['ffmpeg','-y','-loglevel','error','-threads','1','-framerate','10','-start_number',str(start),'-i',str(rgb/'r1-%05d.jpg'),'-framerate','10','-start_number',str(start),'-i',str(rgb/'r2-%05d.jpg'),'-filter_complex',pair+f',select=not(mod(n\\,{10//hz})),tile=5x{(count+4)//5}', '-frames:v','1',str(a.output/f'{label}-{start:05d}-{finish:05d}.jpg')]
            run(command)
    run(['ffmpeg','-y','-loglevel','error','-threads','1','-framerate','10','-i',str(rgb/'r1-%05d.jpg'),'-framerate','10','-i',str(rgb/'r2-%05d.jpg'),'-filter_complex',pair+',setpts=PTS/4','-c:v','libx264','-crf','30','-pix_fmt','yuv420p',str(a.output/'own-r1-r2-4x.mp4')])
    probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(a.output/'own-r1-r2-4x.mp4')]))
    files={f.name:dict(bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in a.output.iterdir()}
    if files['own-r1-r2-4x.mp4']['bytes']>8*1024**2:raise ValueError('VIDEO_OVER_8MIB')
    (a.output/'manifest.json').write_text(json.dumps(dict(raw=str(a.input),frames=len(frames),hz=10,commands=commands,files=files,ffprobe=probe),indent=2))


if __name__=='__main__':main()
