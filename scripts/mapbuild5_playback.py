"""Headless ffmpeg review: three cameras, whole2Hz and terminal10Hz sheets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def make(root, output, *, end_frame=400):
    output.mkdir(parents=True,exist_ok=False);commands=[]
    def run(args):
        command=list(map(str,args));commands.append(command);subprocess.run(command,check=True)
    common=['ffmpeg','-nostdin','-loglevel','error']
    inputs=[]
    for camera in ('overview','r1','r2'):
        inputs+=['-framerate','30','-i',root/(camera+'-%04d.jpg')]
    video=output/'review-3x.mp4'
    run([*common,*inputs,'-filter_complex',
        '[0:v]scale=320:240[a];[1:v]scale=320:240[b];[2:v]scale=320:240[c];[a][b][c]hstack=inputs=3[v]',
        '-map','[v]','-frames:v',end_frame+1,'-an','-c:v','libx264','-crf','28','-threads','1',
        '-pix_fmt','yuv420p',video])
    if video.stat().st_size>8*1024**2:raise ValueError('VIDEO_EXCEEDS_8MIB')
    # 10s pages at2Hz, and2s pages at10Hz. All raw sampled indices are kept
    # in receipts; the final page pads only its empty tile slots.
    pages=[]
    for kind,starts,step,width in [('whole2hz',range(0,end_frame+1,100),5,100),
                                  ('terminal10hz',range(max(0,end_frame-100),end_frame+1,20),1,20)]:
        for start in starts:
            stop=min(end_frame,start+width-1)
            for camera in ('overview','r1','r2'):
                path=output/f'{kind}-{start:04d}-{camera}.jpg'
                selected=f"between(n\\,{start}\\,{stop})*not(mod(n-{start}\\,{step}))"
                run([*common,'-framerate','10','-i',root/(camera+'-%04d.jpg'),'-vf',
                     f'select={selected},scale=320:240,tile=5x4','-frames:v','1','-threads','1',path])
                pages.append(dict(file=path.name,frame_indices=list(range(start,stop+1,step)),camera=camera))
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
    result=dict(raw=str(root),sim_range=[0,end_frame/10],speed=3,ffprobe=probe,pages=pages,reproduction=commands,
                files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                       for p in output.iterdir() if p.is_file()})
    (output/'receipts.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--end-frame',type=int,default=400);a=p.parse_args();make(a.input,a.output,end_frame=a.end_frame)
