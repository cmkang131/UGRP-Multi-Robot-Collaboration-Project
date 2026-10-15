"""GCP2 ffmpeg overview+r1+r2(N/A) video and 2Hz/10Hz frame strips."""
import argparse
import json
import math
from pathlib import Path
import subprocess

from harness.grasp_act_data import read_rows, read_json, sha256, write_json
from scripts.analyze_grasp_act_act16a import require_cpu, existing


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--teacher',action='store_true');a=p.parse_args();host=require_cpu()
    a.output.mkdir(parents=True,exist_ok=False)
    if a.teacher:
        own=a.run/'review-own-10hz'
        index=read_json(a.run/'review-own-index.json')
        origin=index[0]['t'];n=len(index)
        commands=read_rows(existing(a.run/'teacher-commands.jsonl'))
        event=next((r['t'] for r in commands if r['phase']=='done'),commands[-1]['t'])
        result=read_json(existing(a.run/'result.json'))
    else:
        own=a.run/'rgb/r1'
        index=read_rows(a.run/'student-inputs.jsonl');origin=index[0]['t'];n=len(index)
        result=read_json(a.run/'summary.json')
        event=next(iter(result['done_times'].values()),index[-1]['t'])
    top=a.run/'review-top-10hz'
    if len(list(own.glob('*.jpg')))!=n or len(list(top.glob('*.jpg')))!=n:
        raise ValueError('full 10Hz review frames required; no duplicated observations')
    composite=a.output/'composite-10hz';composite.mkdir()
    argv=[]
    def run(cmd):
        argv.append(cmd);subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    # All timestamps in strips/video are world SIM seconds, not 3x video time.
    filt=(f'[0:v]scale=320:240[top];[1:v]scale=320:240[own];'
          f'[top][own]hstack=inputs=2,pad=960:240:0:0:black,setpts=PTS+{origin}/TB,'
          "drawtext=text='EVAL OVERVIEW':x=8:y=8:fontsize=15:fontcolor=white:box=1:boxcolor=black@0.6,"
          "drawtext=text='r1 OWN RGB':x=328:y=8:fontsize=15:fontcolor=white:box=1:boxcolor=black@0.6,"
          "drawtext=text='r2 NOT ACTIVE (SOLO)':x=652:y=95:fontsize=16:fontcolor=white,"
          "drawtext=text='SIM %{pts\\:flt}':x=652:y=125:fontsize=17:fontcolor=white[out]")
    run(['ffmpeg','-hide_banner','-loglevel','error','-threads','1',
         '-framerate','10','-i',str(top/'%06d.jpg'),'-framerate','10','-i',str(own/'%06d.jpg'),
         '-filter_complex_threads','1','-filter_complex',filt,'-map','[out]',
         '-frames:v',str(n),'-vsync','0','-q:v','4',str(composite/'%06d.jpg')])
    # ffmpeg image numbering starts at 1. Montage source starts follow that.
    video=a.output/'review-3x.mp4'
    run(['ffmpeg','-hide_banner','-loglevel','error','-threads','1','-framerate','10','-i',str(composite/'%06d.jpg'),
         '-vf','setpts=PTS/3,fps=30','-c:v','libx264','-preset','fast','-crf','28',
         '-maxrate','1M','-bufsize','2M','-pix_fmt','yuv420p','-movflags','+faststart',str(video)])
    if video.stat().st_size>8_000_000:raise ValueError('review movie exceeds user 8 MB limit')
    pages=[]
    # User-specified rates/page layout are evidence presentation, not acceptance constants.
    for label,start,stop,stride in [('whole-2hz',0,n,5),
                                   ('pre-event-10hz',max(0,round((event-10-origin)*10)),min(n,round((event-origin)*10)+1),1)]:
        chosen=list(range(start,stop,stride))
        for page in range(math.ceil(len(chosen)/20)):
            selection=chosen[page*20:(page+1)*20]
            path=a.output/f'{label}-{page:02d}.jpg'
            filt=f'select=not(mod(n\\,{stride})),scale=640:160,tile=4x5:nb_frames={len(selection)}:padding=2:margin=2'
            run(['ffmpeg','-hide_banner','-loglevel','error','-threads','1','-framerate','10','-start_number',str(selection[0]+1),
                 '-i',str(composite/'%06d.jpg'),'-vf',filt,'-frames:v','1','-q:v','3',str(path)])
            pages.append({'path':str(path),'sha256':sha256(path),'sampling':label,
                          'sim_times':[origin+i*.1 for i in selection],'unique_source_frames':len(selection)})
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
    write_json(a.output/'analysis.json',dict(host=host,source_run=str(a.run),teacher=a.teacher,
        camera_scope='one robot; r2 is N/A, no peer RGB fabricated; overview evaluation only',
        start_sim_t=origin,last_sim_t=origin+(n-1)*.1,event_sim_t=event,
        source_frames_10hz=n,source_own_sha256={p.name:sha256(p) for p in own.glob('*.jpg')},
        result=result,video=dict(path=str(video),bytes=video.stat().st_size,sha256=sha256(video),ffprobe=probe),
        pages=pages,ffmpeg_argv=argv))
    print(json.dumps({'video':str(video),'bytes':video.stat().st_size,'pages':len(pages),'event_sim_t':event}))


if __name__=='__main__':main()
