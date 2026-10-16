"""GCP-only representative own-camera video; preserve first-success originals."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def review(run,out):
    if sys.platform!='linux':raise RuntimeError('review rendering on GCP only')
    from PIL import Image,ImageDraw
    source=(run/'SOURCE_SHA').read_text().strip()
    episode=run/'probe/diagnostic/episode-000';raw=episode/'raw'
    out.mkdir(parents=True,exist_ok=False);frames=out/'frames';frames.mkdir()
    names=sorted(p.name for p in (raw/'eval-own/r1').glob('*.jpg'))
    evidence=[]
    for i,name in enumerate(names):
        canvas=Image.new('RGB',(640,264));draw=ImageDraw.Draw(canvas)
        for k,rid in enumerate(('r1','r2')):
            path=raw/'eval-own'/rid/name
            canvas.paste(Image.open(path),(320*k,0))
            draw.text((320*k+5,245),f'{rid} SIM {int(Path(name).stem)/10:g}',fill='white')
            evidence.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                elapsed_sim_s=int(Path(name).stem)/10,robot=rid))
        canvas.save(frames/f'review-{i:06d}.jpg',quality=90)
    video=out/f'beampair2-{source[:8]}-8318604.mp4'
    command=['ffmpeg','-hide_banner','-loglevel','error','-framerate','1','-i',str(frames/'review-%06d.jpg'),
        '-c:v','libx264','-pix_fmt','yuv420p','-r','10',str(video)]
    subprocess.run(command,check=True)
    probe=subprocess.check_output(['ffprobe','-v','error','-count_frames','-select_streams','v:0',
        '-show_entries','stream=nb_read_frames,width,height,duration','-of','json',str(video)],text=True)
    # A new descendant metadata record promotes the first success without
    # replacing any original metadata/hash list. Both raw and adapter survive.
    metadata=dict(schema='ugrp.run-meta.v1',**{'class':'milestone'},pr=522,
        branch='claude/beam-pair-teacher',sha=source,batch=run.name,
        keep=['raw','adapter'],reason='version first successful failed-seed regression; representative data')
    meta=episode/'RUN_META.json'
    if meta.exists():raise ValueError('preservation metadata already exists')
    meta.write_text(json.dumps(metadata,indent=2)+'\n')
    result=dict(source_sha=source,dependency_sha='26f84d0f0ada1c33473c83cca2d3415ce51bd247',
        raw=str(raw),video=str(video),video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
        video_bytes=video.stat().st_size,command=command,ffprobe=json.loads(probe),
        preservation_metadata=str(meta),preservation_metadata_sha256=hashlib.sha256(meta.read_bytes()).hexdigest(),
        frames=evidence,scope='own r1/r2 review at1Hz; no TOP, no training RGB; original SHA256SUMS unchanged; new preservation metadata hashed separately')
    (out/'representative.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='frames'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();review(a.run,a.out)
