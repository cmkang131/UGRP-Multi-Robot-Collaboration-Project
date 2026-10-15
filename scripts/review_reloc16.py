"""gcp2 ffmpeg-only playback/filmstrips; UI apps are never launched."""
import argparse,json,platform,subprocess,hashlib
from pathlib import Path


def ff(args):subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','1',*args],check=True)


def make(run,out):
    if not platform.node().startswith('ugrp-sim-gcp2'):raise RuntimeError('gcp2 only')
    manifest=json.loads((run/'raw/playback/manifest.json').read_text());frames=manifest['frames']
    out.mkdir(parents=True,exist_ok=False);inputs=[]
    for camera in ('overview','r1','r2','r3'):
        # 2Hz saved source at8fps => SIM4x. No motion interpolation.
        inputs+=['-framerate','8','-pattern_type','glob','-i',str(run/'raw/playback'/('*-'+camera+'.jpg'))]
    graph=';'.join(f'[{i}:v]scale=160:120,setsar=1[s{i}]' for i in range(4))+';[s0][s1][s2][s3]hstack=inputs=4[v]'
    ff([*inputs,'-filter_complex_threads','1','-filter_complex',graph,'-map','[v]','-c:v','libx264','-preset','fast','-crf','27','-pix_fmt','yuv420p',str(out/'playback-4x.mp4')])
    # Whole run at2Hz, 8x8=64 saved exposures per plate (32 SIM seconds).
    ff([*inputs,'-filter_complex_threads','1','-filter_complex',graph+';[v]tile=8x8:nb_frames=64:padding=1:margin=1[strip]',
        '-map','[strip]','-fps_mode','passthrough','-q:v','3',str(out/'whole-%02d.jpg')])
    failure=run/'raw/failure-rgb/manifest.json'
    if failure.exists():
        rec=json.loads(failure.read_text());camera=rec['frames'][0]['camera'] if rec['frames'] else None
        if rec['frames']:
            ff(['-framerate','10','-i',str(failure.parent/'%04d.jpg'),'-vf','scale=160:120,tile=10x5:nb_frames=50:padding=1:margin=1',
                '-fps_mode','passthrough','-q:v','3',str(out/'last10-10hz-%02d.jpg')])
    else:rec={};camera=None
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size:stream=width,height,r_frame_rate','-of','json',str(out/'playback-4x.mp4')]))
    assert (out/'playback-4x.mp4').stat().st_size<=8*1024**2
    record=dict(run=run.name,original_playback_manifest=str(run/'raw/playback/manifest.json'),
        source_frame_N=len(frames),whole_sim_range=[frames[0]['t'],frames[-1]['t']] if frames else None,
        whole_hz=2,video_sim_speed=4,video_interpolated=False,last10_source_hz=rec.get('hz'),last10_camera=camera,
        last10_range=[rec['frames'][0]['t'],rec['frames'][-1]['t']] if rec.get('frames') else None,
        probe=probe,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.glob('*') if p.is_file()},
        scope='ffprobe verified; direct filmstrip review is separately documented')
    (out/'review-manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();make(a.run,a.output)
