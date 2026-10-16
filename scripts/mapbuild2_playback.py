"""GCP2-only headless 3x overview/r1/r2 playback and 2/10Hz strips."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or not platform.node().startswith(('ugrp-act-l4-gcp2','ugrp-sim-gcp2')):
        raise ValueError('GCP2_ONLY_NO_MAC_GUI')
    a.output.mkdir(parents=True,exist_ok=False);receipts=[]
    for case in ('drive-off','high-off','drive-on_v1'):
        folder=a.output/case;folder.mkdir();inputs=[]
        for camera in ('overview','r1','r2'):
            inputs+=['-framerate','10','-i',str(a.input/case/(camera+'-%04d.jpg'))]
        video=folder/'review-3x.mp4'
        subprocess.run(['ffmpeg','-nostdin','-loglevel','error',*inputs,'-filter_complex',
            '[0:v][1:v][2:v]hstack=inputs=3,setpts=PTS/3[v]','-map','[v]','-an','-r','30',
            '-c:v','libx264','-crf','28','-pix_fmt','yuv420p','-threads','1',str(video)],check=True)
        label="drawtext=text='frame %{n}':x=5:y=5:fontsize=24:fontcolor=red:box=1:boxcolor=white@0.8"
        for camera in ('overview','r1','r2'):
            for name,filter_ in [('whole-2hz',r'select=not(mod(n\,5)),scale=320:240,tile=3x3'),
                                  ('terminal-10hz','scale=320:240,tile=7x6')]:
                subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-framerate','10','-i',
                    str(a.input/case/(camera+'-%04d.jpg')),'-vf',label+','+filter_,'-frames:v','1','-threads','1',
                    str(folder/(camera+'-'+name+'.jpg'))],check=True)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
        if video.stat().st_size>8*1024**2:raise ValueError('VIDEO_8MIB_LIMIT')
        if int(probe['streams'][0]['nb_frames'])!=41:raise ValueError('ALL_RECORDED_FRAMES_REQUIRED')
        receipts.append(dict(case=case,sim_range=[0,4],frames=41,whole_frames=list(range(0,41,5)),
            terminal_frames=list(range(41)),video_probe=probe,files={p.name:dict(bytes=p.stat().st_size,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in folder.iterdir()}))
    (a.output/'receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')


if __name__=='__main__':main()
