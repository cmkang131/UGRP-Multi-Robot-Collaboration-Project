"""Original-GCP5 ffmpeg review artifacts; no physics, rendering or GUI.

Own r1/r2 only: recorder has no overview/TOP stream. All frames at 2Hz in
30-SIM-second sheets, terminal 10 SIM seconds at 10Hz, 4x video <=8 MiB.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('ORIGINAL_GCP5_ONLY')
    a.output.mkdir(exist_ok=False);own=json.loads((a.input/'own.json').read_text())['frames'];count=len(own)
    if not count:raise ValueError('NO_RECORDED_FRAMES')
    def call(cmd):subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
    def inputs(start=0):
        out=['ffmpeg','-v','error']
        for rid in ('r1','r2'):
            out+=['-itsoffset',str(start/10),'-framerate','10','-start_number',str(start),'-i',str(a.input/'own-rgb'/f'{rid}-%05d.jpg')]
        return out
    def sheet(start,cells,columns,hz,name):
        # Timestamp before selection retains the original SIM sample time.
        f="[0:v][1:v]hstack=inputs=2,scale=320:120,drawtext=text='SIM %{pts\\:flt}':fontcolor=white:box=1:boxcolor=black:fontsize=12:x=2:y=2"
        if hz==2:f+=",select='not(mod(n,5))'"
        f+=f',tile={columns}x{(cells+columns-1)//columns}'
        call(inputs(start)+['-filter_complex',f,'-frames:v','1',str(a.output/name)])
    for start in range(0,count,300):sheet(start,60,5,2,f'full-2hz-{start:05d}.jpg')
    terminal=max(0,count-101);sheet(terminal,min(101,count),10,10,'terminal-10hz.jpg')
    duration=(count-1)/40
    # 8 MiB is the user's artifact size budget, not a behavior threshold.
    bitrate=min(400000,int(8*1024**2*8/max(duration,1)/1.2))
    f="[0:v][1:v]hstack=inputs=2,scale=640:240,drawtext=text='SIM %{pts\\:flt}':fontcolor=white:box=1:boxcolor=black:fontsize=14:x=2:y=2,setpts=PTS/4"
    video=a.output/'own-r1-r2-4x.mp4'
    call(inputs()+['-filter_complex',f,'-r','10','-c:v','libx264','-preset','fast','-b:v',str(bitrate),'-maxrate',str(bitrate),'-bufsize',str(2*bitrate),'-pix_fmt','yuv420p','-movflags','+faststart',str(video)])
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(video)],text=True))
    if video.stat().st_size>8*1024**2:raise ValueError('VIDEO_EXCEEDS_8MIB')
    sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [a.input/'own.json',a.input/'SHA256SUMS.json',Path(__file__)]}
    artifacts={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in a.output.iterdir() if p.is_file()}
    (a.output/'manifest.json').write_text(json.dumps(dict(source=str(a.input),input_sha256=sources,frames=count,
        full_review_hz=2,terminal_review_hz=10,terminal_start_sim_s=terminal/10,video_speed=4,overview='not recorded; own r1/r2 only',
        artifacts=artifacts,ffprobe=probe),indent=2)+'\n')
    print(json.dumps(dict(frames=count,artifacts=len(artifacts),video_bytes=video.stat().st_size)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('input','output'):p.add_argument('--'+n,type=Path,required=True)
    main(p.parse_args())
