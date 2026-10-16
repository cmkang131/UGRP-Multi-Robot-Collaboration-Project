"""gcp2-only pair review: reconstructed evaluator top + original r1/r2 JPEG.

No physics step, contact reconstruction, GUI, or extra controller observation.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess


def main():
    if platform.system()!='Linux':raise RuntimeError('gcp2 rendering only')
    os.environ['MUJOCO_GL']='osmesa';os.environ['LP_NUM_THREADS']='1'
    import numpy as np
    import mujoco
    from PIL import Image,ImageDraw
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--world',type=int,default=0)
    p.add_argument('--asset-root',type=Path,required=True,help='exact backend scene asset checkout; XML paths are relative')
    a=p.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=False)
    os.chdir(a.asset_root)
    world=a.run/f'world-{a.world:03d}';summary=json.loads((a.run/'summary.json').read_text())
    state=np.load(a.run/f'world-{a.world:03d}-states.npz')
    index={int(t):i for i,t in enumerate(state['ticks'])}
    origin=float(summary['native_initialization_only_sim_s'][a.world])
    model=mujoco.MjModel.from_xml_string((world/'raw/scene.xml').read_text());data=mujoco.MjData(model)
    roots=[model.body_rootid[model.body(name).id] for name in ('r1__robot','r2__robot','cargo_beam_1')]
    gids=np.flatnonzero(np.isin(model.body_rootid[model.geom_bodyid],roots)&np.isin(model.geom_group,[0,1,2,3]))
    low=np.full(3,np.inf);high=-low
    for q in state['qpos']:
        data.qpos[:]=q;mujoco.mj_kinematics(model,data)
        xyz=data.geom_xpos[gids];radius=model.geom_rbound[gids,None]
        low=np.minimum(low,(xyz-radius).min(axis=0));high=np.maximum(high,(xyz+radius).max(axis=0))
    cid=model.camera('cctv_top').id;tan_v=math.tan(math.radians(float(model.cam_fovy[cid]))/2)
    half=(high-low)/2;centre=(high+low)/2
    model.cam_pos[cid]=[centre[0],centre[1],high[2]+max(half[0]/(tan_v*4/3)*320/318,half[1]/tan_v*240/238)]
    model.cam_quat[cid]=[1.,0.,0.,0.]
    renderer=mujoco.Renderer(model,height=240,width=320)

    def compose(world_t,images):
        tick=round(world_t*10)
        if tick not in index:raise ValueError('missing exact saved evaluator state at '+str(world_t))
        i=index[tick];data.qpos[:]=state['qpos'][i];data.qvel[:]=state['qvel'][i]
        mujoco.mj_kinematics(model,data);mujoco.mj_camlight(model,data)
        data.cam_xpos[cid]=model.cam_pos[cid];data.cam_xmat[cid]=np.eye(3).reshape(-1)
        renderer.update_scene(data,camera='cctv_top')
        canvas=Image.new('RGB',(960,270),(20,20,20))
        canvas.paste(Image.fromarray(renderer.render()),(0,30))
        for k,rid in enumerate(('r1','r2'),1):
            canvas.paste(Image.open(images[rid]).convert('RGB').resize((320,240)),(k*320,30))
        draw=ImageDraw.Draw(canvas)
        draw.text((4,5),f'world {world_t:.1f}s / +{world_t-origin:.1f} SIM | eval top',fill='white')
        for k,rid in enumerate(('r1','r2'),1):draw.text((k*320+4,5),rid+' original own RGB',fill='white')
        return canvas

    def sheet(paths,prefix):
        for start in range(0,len(paths),18):
            part=paths[start:start+18]
            canvas=Image.new('RGB',(960*3,270*6),(30,30,30))
            for j,path in enumerate(part):canvas.paste(Image.open(path),((j%3)*960,(j//3)*270))
            canvas.resize((1920,1080)).save(out/f'{prefix}-{start//18:02d}.jpg',quality=88)

    full=out/'full';full.mkdir();paths=[];times=[]
    for f in sorted((world/'review-2hz/r1').glob('*.jpg')):
        t=origin+int(f.stem)/10
        images={rid:world/'review-2hz'/rid/f.name for rid in ('r1','r2')}
        if not all(q.is_file() for q in images.values()):raise ValueError('paired own RGB missing')
        image=compose(t,images);target=full/f'{len(paths):05d}.jpg';image.save(target,quality=86)
        paths.append(target);times.append(t)
    if not paths:raise ValueError('no actual 2Hz frames')
    sheet(paths,'full-2hz')
    tail_rows=json.loads((world/'tail-10hz.json').read_text());tail=out/'tail';tail.mkdir();tail_paths=[]
    for row in tail_rows:
        target=tail/f'{len(tail_paths):05d}.jpg'
        compose(row['world_t'],{k:Path(v) for k,v in row['files'].items()}).save(target,quality=86)
        tail_paths.append(target)
    sheet(tail_paths,'last10s-10hz')
    native=out/'native-six';native.mkdir()
    # Six actual recorded times over the available terminal interval; no upsample.
    picks=np.linspace(0,len(tail_rows)-1,min(6,len(tail_rows)),dtype=int)
    for j,i in enumerate(picks):
        for rid,path in tail_rows[i]['files'].items():(native/f'{j:02d}-{rid}.jpg').write_bytes(Path(path).read_bytes())
    renderer.close()
    video=out/'playback-3x.mp4'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate','6','-i',str(full/'%05d.jpg'),
        '-c:v','libx264','-crf','30','-pix_fmt','yuv420p',str(video)],check=True)
    if video.stat().st_size>8_000_000:raise ValueError('video exceeds8MB')
    probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(video)]))
    meta=dict(run=str(a.run),world=a.world,sim_world_range=[times[0],times[-1]],
        mujoco=mujoco.__version__,asset_root=str(a.asset_root),
        sim_relative_range=[times[0]-origin,times[-1]-origin],full_2hz_frames=len(paths),
        terminal_10hz_frames=len(tail_rows),native_six_times=[tail_rows[i]['world_t'] for i in picks],
        video_bytes=video.stat().st_size,video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),ffprobe=probe,
        scope='HOST_ERROR/interrupted diagnostic, not physical failure; own RGB original, top reconstructed with evaluator-only kinematics; no physics step',
        postprocessor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'playback-meta.json').write_text(json.dumps(meta,indent=2)+'\n')


if __name__=='__main__':main()
