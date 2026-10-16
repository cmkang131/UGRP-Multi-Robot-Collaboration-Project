"""One finite, headless follow-up of capture-r4; never a recurring monitor."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

BASE=Path('/home/ugrp/ugrp-sim');RUN=BASE/'runs/mapbuild2'
SOURCE=BASE/'src/mapbuild2-analysis';VISION=BASE/'src/5974a181a'
PYTHON=BASE/'runs/simalt3/warp-env/bin/python'


def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')


def call(cmd):
    with (RUN/'postprocess.log').open('a') as log:
        subprocess.run(list(map(str,cmd)),cwd=SOURCE,env={**os.environ,'PYTHONPATH':str(SOURCE),
            'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'},stdout=log,stderr=subprocess.STDOUT,check=True)


def main():
    lease=BASE/'leases/mapbuild2-post.json'
    with lease.open('x') as f:json.dump(dict(task='mapbuild2-post',pid=os.getpid(),concurrency=0,gpu_shared=True,
        start=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='after finite capture-r4 + analysis/playback'),f)
    try:
        while not (RUN/'capture-r4-exit.json').exists():time.sleep(20)
        if json.loads((RUN/'capture-r4-exit.json').read_text())['exit_code']!=0:raise ValueError('CAPTURE_NOT_COMPLETE')
        raw=RUN/'capture-r4';analysis=RUN/'analysis-r1'
        table=raw/'rejection-table.json'
        if not table.is_file():raise ValueError('CAPTURE_FUNNEL_REQUIRED')
        dump(RUN/'analysis-r1-queue.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip(),
            rejection_table=str(table),input=str(raw),output=str(analysis)))
        call([PYTHON,'-m','scripts.mapbuild2_analyze','--input',raw,'--output',analysis])
        mapping=RUN/'map-r1'
        table=analysis/'rejection-table.json'
        if not table.is_file():raise ValueError('TRACKING_FUNNEL_REQUIRED')
        dump(RUN/'map-r1-queue.json',dict(rejection_table=str(table),input=str(raw),output=str(mapping),diagnostic_only=True))
        call([PYTHON,SOURCE/'scripts/mapbuild2_map.py','--execute','--input',raw,
            '--trajectory',analysis/'orange-columns-fast7-trajectory.json','--vision-source',VISION,'--output',mapping])
        # Original reset fixture SE(2), evaluator only. This acquisition source
        # predates first_origin serialization; reproduce its exact initializer.
        code="from scripts.probe_scene_tex2 import wall_views; import json; from scripts.generate_scene_textures import MAPS; print(json.dumps(wall_views(json.loads(MAPS[0].read_text()))[0]['xyyaw']))"
        origin=json.loads(subprocess.check_output([str(PYTHON),'-c',code],cwd=VISION,text=True,
            env={**os.environ,'PYTHONPATH':str(VISION),'MUJOCO_GL':'osmesa'}))
        for prediction in mapping.glob('*-predicted.json'):
            call([PYTHON,'-m','scripts.mapbuild2_map_eval','--predicted',prediction,'--static-map',
                VISION/'maps/zones_final_v3/zone_hardmaps1_h1_final_v3.json','--origin',*origin,'--output',prediction.with_name(prediction.stem+'-score.json')])
        playback=RUN/'playback-r1';playback.mkdir(exist_ok=False)
        receipts=[]
        for case in ('drive-off','high-off','drive-on_v1'):
            folder=playback/case;folder.mkdir()
            ins=[]
            for camera in ('overview','r1','r2'):ins+=['-framerate','10','-i',str(raw/case/(camera+'-%04d.jpg'))]
            video=folder/'review-3x.mp4'
            call(['ffmpeg','-nostdin','-loglevel','error',*ins,'-filter_complex',
                '[0:v][1:v][2:v]hstack=inputs=3,setpts=PTS/3[v]','-map','[v]','-an','-c:v','libx264','-crf','28','-pix_fmt','yuv420p','-threads','1',video])
            for camera in ('overview','r1','r2'):
                for name,filter_ in [('whole-2hz',r'select=not(mod(n\,5)),scale=320:240,tile=3x3'),
                                      ('terminal-10hz','scale=320:240,tile=7x6')]:
                    call(['ffmpeg','-nostdin','-loglevel','error','-framerate','10','-i',raw/case/(camera+'-%04d.jpg'),
                        '-vf',filter_,'-frames:v','1','-threads','1',folder/(camera+'-'+name+'.jpg')])
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
            if video.stat().st_size>8*1024**2:raise ValueError('VIDEO_8MIB_LIMIT')
            receipts.append(dict(case=case,sim_range=[0,4],video_probe=probe,files={p.name:dict(bytes=p.stat().st_size,
                sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in folder.iterdir()}))
        dump(playback/'receipts.json',receipts)
        dump(RUN/'postprocess-exit.json',dict(status='COMPLETE',source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()))
    except BaseException as exc:
        dump(RUN/'postprocess-exit.json',dict(status='ERROR',reason=repr(exc)))
        raise
    finally:
        if lease.exists() and json.loads(lease.read_text()).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
