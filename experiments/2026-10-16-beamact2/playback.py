"""GCP2 ffmpeg review artifacts only: 3x video, 2Hz full strips, 10Hz tail."""
import argparse
import json
from pathlib import Path
import subprocess

from harness.grasp_act_data import read_json, sha256, write_json
from scripts.beamact1_runtime import require_gcp2


def ff(args):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-threads','1',*args],check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();require_gcp2(training=False)
    a.output.mkdir(parents=True,exist_ok=False)
    rows=read_json(a.run/'review/manifest.json')
    for name in ('overview','r1','r2'):(a.output/name).mkdir()
    for i,row in enumerate(rows):
        paths=dict(overview=row['overview'],**row['own'])
        for name,path in paths.items():
            (a.output/name/f'{i:06d}.jpg').symlink_to(a.run/'review'/path)
    inputs=[]
    for name in ('overview','r1','r2'):
        inputs+=['-framerate','2','-i',str(a.output/name/'%06d.jpg')]
    graph=';'.join(f'[{i}:v]scale=320:240,setsar=1[x{i}]' for i in range(3))
    graph+=';[x0][x1][x2]hstack=inputs=3,drawtext=text=\'SIM %{pts\\:hms}\':x=4:y=4:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6'
    video=a.output/'playback-3x.mp4'
    ff([*inputs,'-filter_complex_threads','1','-filter_complex',graph+',setpts=PTS/3[v]',
        '-map','[v]','-r','6','-an','-c:v','libx264','-crf','28','-preset','fast','-movflags','+faststart',str(video)])
    if video.stat().st_size>8*1024**2:raise ValueError('video exceeds8MiB')
    # The 3x video contains every original2Hz SIM frame. At6fps its strips
    # recover the complete2Hz SIM sequence, not a sparse overview selection.
    ff(['-i',str(video),'-vf','fps=6,scale=480:120,tile=4x6:padding=2:margin=2',
        '-vsync','vfr','-q:v','3',str(a.output/'full-2hz-%02d.jpg')])
    tail=read_json(a.run/'failure-tail/manifest.json')
    frames={r:[] for r in ('r1','r2')}
    for item in tail['frames']:frames[item['robot']].append(item)
    if frames['r1']:
        for rid in frames:
            dest=a.output/('tail-'+rid);dest.mkdir()
            for i,item in enumerate(frames[rid]):(dest/f'{i:06d}.jpg').symlink_to(a.run/'failure-tail'/item['path'])
        ff(['-framerate','10','-i',str(a.output/'tail-r1/%06d.jpg'),'-framerate','10',
            '-i',str(a.output/'tail-r2/%06d.jpg'),'-filter_complex_threads','1','-filter_complex',
            '[0:v]scale=240:180,setsar=1[a];[1:v]scale=240:180,setsar=1[b];[a][b]hstack=inputs=2,tile=5x5:padding=2:margin=2[v]',
            '-map','[v]','-vsync','vfr','-q:v','3',str(a.output/'tail-10hz-%02d.jpg')])
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
    write_json(a.output/'playback.json',dict(raw=str(a.run),full_sim_range_s=[rows[0]['sim_s'],rows[-1]['sim_s']],
        full_hz=2,playback_speed=3,tail_hz=10,
        tail_sim_range=[tail['frames'][0]['t'],tail['frames'][-1]['t']] if tail['frames'] else None,
        ffprobe=probe,files={f.name:dict(bytes=f.stat().st_size,sha256=sha256(f))
            for f in a.output.iterdir() if f.is_file() and not f.is_symlink()}))


if __name__=='__main__':main()
