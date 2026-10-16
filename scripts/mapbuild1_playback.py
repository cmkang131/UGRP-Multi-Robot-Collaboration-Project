"""Headless remote ffmpeg review: exact2Hz strips, full10Hz strips, 3x video."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sequences',nargs='+',required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);receipts=[]
    for sequence in a.sequences:
        if sequence not in ('drive-forward','drive-lateral','drive-turn','high-forward','high-lateral','high-turn'):
            raise ValueError('RECORDED_SEQUENCE_REQUIRED')
        src=a.input/sequence/'%04d.jpg';dest=a.output/sequence;dest.mkdir()
        base=['ffmpeg','-nostdin','-loglevel','error','-framerate','10','-i',str(src)]
        label="drawtext=text='frame %{n}':x=5:y=5:fontsize=24:fontcolor=red:box=1:boxcolor=white@0.8"
        for name,filter_ in [('whole-2hz.png',label+r',select=not(mod(n\,5)),scale=320:240,tile=3x3'),
                              ('terminal-10hz.png',label+',scale=320:240,tile=7x6')]:
            subprocess.run(base+['-vf',filter_,'-frames:v','1','-threads','1',str(dest/name)],check=True)
        video=dest/'review-3x.mp4'
        subprocess.run(base+['-vf','setpts=PTS/3','-an','-c:v','libx264','-crf','28','-pix_fmt','yuv420p','-threads','1',str(video)],check=True)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)],text=True))
        receipts.append(dict(sequence=sequence,t_sim=[0,4],whole_frames=list(range(0,41,5)),
            terminal_frames=list(range(41)),video_probe=probe,
            files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in dest.iterdir()}))
    (a.output/'receipts.json').write_text(json.dumps(dict(overview='not_recorded; kinematic own-r1 only',r2='not_recorded',records=receipts),indent=2)+'\n')


if __name__=='__main__':main()
