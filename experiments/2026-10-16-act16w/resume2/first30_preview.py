"""Own-RGB first30 operational preview; live world has no closed overview yet.

Not a failure/success replay. Original JPEGs, full2Hz sheets and final10s10Hz
sheets are distinct from a3x review movie retained only on gcp2.
"""
import argparse
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
from act16w_runtime import require_gcp2,frozen_source,sha256
B=Path('/home/ugrp/ugrp-sim')


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();host=require_gcp2();source=frozen_source(ROOT)
    group=B/'runs/act16w-resume2-data-r2/group-03';rgb=group/'capture/world-000/capture'
    if not (group/'first30.json').exists():raise ValueError('completed first30 receipt required')
    raw=(group/'controller/world-000/teacher-commands.jsonl').read_bytes().splitlines();commands=[json.loads(x) for x in raw[:300]]
    if len(commands)!=300 or any(abs(c['t']-commands[0]['t']-i*.1)>1e-5 for i,c in enumerate(commands)):raise ValueError('exact300 native control observations required')
    if not (rgb/'000299.jpg').exists():raise ValueError('complete first30 JPEG prefix required')
    a.out.mkdir(parents=True,exist_ok=False);lease=B/'leases/act16w-first30-preview.json';now=datetime.now(timezone.utc)
    with lease.open('x') as f:json.dump(dict(task='act16w-first30-preview',pid=os.getpid(),start=now.isoformat(),expected_end=(now+timedelta(minutes=3)).isoformat(),concurrency=0,scope='ffmpeg CPU postprocessing only'),f)
    def run(args):subprocess.run(['ffmpeg','-hide_banner','-loglevel','error',*args],check=True)
    def stamp(start,size):return rf"drawtext=text='r1 seed86825 SIM %{{eif\:(n+{start})/10\:d}}.%{{eif\:mod(n+{start}\,10)\:d}}s':x=4:y=4:fontsize={size}:fontcolor=white:box=1:boxcolor=black"
    try:
        run(['-framerate','10','-start_number','0','-i',str(rgb/'%06d.jpg'),'-vf','scale=320:240,'+stamp(0,16)+",select='not(mod(n,5))',tile=4x5",'-frames:v','3','-q:v','3',str(a.out/'full-2hz-%02d.jpg')])
        run(['-framerate','10','-start_number','200','-i',str(rgb/'%06d.jpg'),'-vf','scale=320:240,'+stamp(200,16)+',tile=4x5','-frames:v','5','-q:v','3',str(a.out/'tail10s-10hz-%02d.jpg')])
        movie=a.out/'own-rgb-first30-3x.mp4'
        run(['-framerate','10','-start_number','0','-i',str(rgb/'%06d.jpg'),'-vf',stamp(0,20)+',setpts=PTS/3','-frames:v','300','-r','30','-c:v','libx264','-preset','fast','-crf','28','-pix_fmt','yuv420p',str(movie)])
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(movie)],text=True))
        if movie.stat().st_size>8*1024*1024:raise ValueError('review movie exceeds user8MiB ceiling')
        report=dict(status='complete',host=host,source_sha=source,scope='live first30 own-r1 operational preview only; no overview, solo r2 inactive; not full-run/failure/success proof',seed=86825,elapsed_SIM_s=[0,29.9],full_sample_Hz=2,tail_sample_Hz=10,tail_elapsed_SIM_s=[20,29.9],speed=3,command_prefix_sha256=hashlib.sha256(b'\n'.join(raw[:300])+b'\n').hexdigest(),raw_rgb=str(rgb),first30=json.loads((group/'first30.json').read_text()),ffprobe=probe,files={p.name:dict(bytes=p.stat().st_size,sha256=sha256(p)) for p in a.out.iterdir() if p.is_file()})
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status='complete',raw=str(a.out),movie_bytes=movie.stat().st_size)))
    finally:lease.unlink(missing_ok=True)


if __name__=='__main__':main()
