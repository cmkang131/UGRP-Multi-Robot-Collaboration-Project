"""Owned L4 replay: evaluation overview + actual r1 RGB; no stepping.

Derived from warp3 make_student_playback-87076dc3e.py; native camera
recordings remain untouched. Reframing applies only to evaluation overview.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

from act16w_runtime import require_gcp2, frozen_source, sha256
ROOT = Path(__file__).resolve().parents[1]
HOST = require_gcp2(training=True)
SOURCE = frozen_source(ROOT)
os.environ['MUJOCO_GL']='osmesa';os.environ['LP_NUM_THREADS']='1'
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import mujoco


def read_json(path):
    path=Path(path)
    if not path.exists():path=Path(str(path)+'.zst')
    raw=subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else path.read_bytes()
    return json.loads(raw)


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--world',type=int,required=True)
    p.add_argument('--compiled-references',type=Path,help='exact native geometry inventory for reconstructed evaluation overview')
    p.add_argument('--qualified-source',type=Path,help='frozen source containing simalt_compiled_compat')
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=False)
    world=a.run/f'world-{a.world:03d}';state_path=a.run/f'world-{a.world:03d}-states.npz'
    actor_owner=(a.run/'RUN_META.json').exists() and (world/'states.npz').exists()
    if actor_owner:state_path=world/'states.npz'
    if not state_path.exists() and a.world==0:state_path=a.run/'world0-states.npz'
    state=np.load(state_path)
    index={int(t):i for i,t in enumerate(state['ticks'])}
    m=mujoco.MjModel.from_xml_string((world/'scene.xml').read_text());d=mujoco.MjData(m)
    geometry=None
    if a.compiled_references:
        if not a.qualified_source:raise ValueError('compiled references require their frozen qualified source')
        qualified_sha=frozen_source(a.qualified_source)
        references=read_json(a.compiled_references)
        reference=references[sha256(world/'scene.xml')]
        sys.path.insert(0,str(a.qualified_source/'scripts'))
        from simalt_compiled_compat import apply_geometry
        apply_geometry(m,world/'scene.xml',Path(reference['geometry']))
        geometry=dict(inventory=str(a.compiled_references),inventory_sha256=sha256(a.compiled_references),
            geometry_file=reference['geometry'],geometry_sha256=sha256(reference['geometry']),qualified_source_sha=qualified_sha,
            scope='compiled geometry applied only to saved-state evaluation overview; recorded own RGB unchanged')
    summary=read_json(a.run/('RUN_META.json' if actor_owner else 'summary.json'));camera=summary['camera'];cid=m.camera('r1__robot_cam').id
    m.cam_pos[cid]=camera['mount_pos'];m.cam_quat[cid]=camera['mount_quat']
    # Review camera only: fit actual r1/target geometry across the whole replay.
    # The source overview clipped starts outside its fixed rectangle. Actor RGB
    # remains the original recorded bytes and its camera is never reframed.
    plan=read_json(world/'plan.json')
    if actor_owner:
        # Exact solo scene body naming; fail if the recorded model differs.
        target='cargo_'+plan['item_id'];m.body(target)
    else:
        scene=read_json(world/'scene.json')
        target=scene['box_replicas'][plan['item_id']]['body_name']
    roots=[m.body_rootid[m.body(name).id] for name in ('r1__robot',target)]
    gids=np.flatnonzero(np.isin(m.body_rootid[m.geom_bodyid],roots)&np.isin(m.geom_group,[0,1,2,3]))
    paths=[path for path in sorted((world/'review-own').glob('*.jpg')) if int(path.stem) in index]
    if not paths:raise ValueError('no review frames/states')
    low=np.full(3,np.inf);high=-low
    for path in paths:
        i=index[int(path.stem)];d.qpos[:]=state['qpos'][i]
        mujoco.mj_kinematics(m,d)
        xyz=d.geom_xpos[gids];radius=m.geom_rbound[gids,None]
        low=np.minimum(low,(xyz-radius).min(axis=0));high=np.maximum(high,(xyz+radius).max(axis=0))
    top=m.camera('cctv_top').id
    if m.cam_bodyid[top]!=0:raise ValueError('evaluation overview must be world-fixed')
    original_overview=dict(pos=m.cam_pos[top].tolist(),quat=m.cam_quat[top].tolist())
    tan_v=math.tan(math.radians(float(m.cam_fovy[top]))/2);tan_h=tan_v*320/240
    half=(high-low)/2;centre=(high+low)/2
    # One output-pixel border on each side, derived from320x240 view geometry.
    height=float(high[2]+max(half[0]/tan_h*320/318,half[1]/tan_v*240/238))
    m.cam_pos[top]=[centre[0],centre[1],height];m.cam_quat[top]=[1.,0.,0.,0.]
    overview=dict(original=original_overview,pos=m.cam_pos[top].tolist(),quat=m.cam_quat[top].tolist(),
        geometry_bounds=[low.tolist(),high.tolist()],basis='full recorded r1+target geom bounding spheres, existing fovy/aspect and one output-pixel border')
    renderer=mujoco.Renderer(m,height=240,width=320)
    tops=out/'overview';tops.mkdir();own=out/'own';own.mkdir()
    selected=[]
    for path in paths:
        tick=int(path.stem)
        if tick not in index:continue
        i=index[tick];d.qpos[:]=state['qpos'][i];d.qvel[:]=state['qvel'][i]
        mujoco.mj_kinematics(m,d);mujoco.mj_camlight(m,d)
        # World-fixed camera transforms may already be cached in MjData.
        # Only this reconstructed evaluation camera receives the new extrinsic.
        d.cam_xpos[top]=m.cam_pos[top];d.cam_xmat[top]=np.eye(3).reshape(-1)
        renderer.update_scene(d,camera='cctv_top')
        n=len(selected);frame=Image.fromarray(renderer.render())
        ImageDraw.Draw(frame).text((4,220),f'SIM {tick/10:.1f}s',font=ImageFont.load_default(size=16),fill='white',stroke_width=1,stroke_fill='black')
        frame.save(tops/f'{n:05d}.png')
        (own/f'{n:05d}.jpg').write_bytes(path.read_bytes());selected.append(tick)
    renderer.close()
    if not selected:raise ValueError('no review frames/states')
    step=np.diff(selected);hz=10/float(np.median(step)) if len(step) else 2.
    if len(step) and not np.all(step==5):raise ValueError('review timeline must be actual2Hz')
    composed=out/'frames';composed.mkdir()
    filters="[0:v]drawtext=text='overview - reframed evaluation only':x=4:y=4:fontsize=12:fontcolor=white[a];[1:v]scale=320:240,drawtext=text='r1 recorded own RGB':x=4:y=4:fontsize=14:fontcolor=white[b];color=c=0x202020:s=320x240:r=2,drawtext=text='r2 N/A - solo r1 task':x=8:y=110:fontsize=18:fontcolor=white[c];[a][b][c]hstack=inputs=3:shortest=1[v]"
    subprocess.run(['ffmpeg','-y','-loglevel','error','-threads','1','-filter_complex_threads','1','-framerate',str(hz),'-i',str(tops/'%05d.png'),
        '-framerate',str(hz),'-i',str(own/'%05d.jpg'),'-filter_complex',filters,'-map','[v]',
        '-frames:v',str(len(selected)),str(composed/'%05d.jpg')],check=True)
    video=out/'playback-3x.mp4'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate',str(hz*3),'-start_number','1','-i',str(composed/'%05d.jpg'),
        '-c:v','libx264','-crf','30','-pix_fmt','yuv420p',str(video)],check=True)
    for start in range(0,len(selected),18):
        subprocess.run(['ffmpeg','-y','-loglevel','error','-start_number',str(start+1),'-i',str(composed/'%05d.jpg'),
            '-vf','scale=720:180,tile=3x6','-frames:v','1',str(out/f'full-2hz-{start//18:02d}.jpg')],check=True)
    ring=sorted((world/('last10s' if actor_owner else 'failure-rgb-buffer')).glob('*.jpg'))
    for start in range(0,len(ring),20):
        subset=out/f'ring-{start//20:02d}';subset.mkdir()
        for i,path in enumerate(ring[start:start+20]):(subset/f'{i:03d}.jpg').write_bytes(path.read_bytes())
        subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(subset/'%03d.jpg'),
            '-vf',f"scale=320:240,drawtext=text='SIM {int(ring[start].stem)/10:.1f} + %{{n}}/10s':x=4:y=4:fontsize=15:fontcolor=white:box=1:boxcolor=black@0.7,tile=5x4",'-frames:v','1',str(out/f'last10s-10hz-{start//20:02d}.jpg')],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(video)]))
    if video.stat().st_size>8_000_000:raise ValueError('video exceeds8MB limit')
    (out/'playback-meta.json').write_text(json.dumps(dict(run=str(a.run),world=a.world,sim_range=[selected[0]/10,selected[-1]/10],
        postprocessor_sha256=sha256(Path(__file__)), source_sha=SOURCE, host=HOST,
        source_state=dict(path=str(state_path),sha256=sha256(state_path)),
        source_scene=dict(path=str(world/'scene.xml'),sha256=sha256(world/'scene.xml')),
        full_2hz_frames=len(selected),terminal_10hz_frames=len(ring),video_bytes=video.stat().st_size,ffprobe=probe,overview=overview,compiled_geometry=geometry,
        scope='overview reframed for full recorded r1/target geometry using evaluation states only; r1 own RGB is actual and unchanged, r2 not an actor; no native physics step'),indent=2)+'\n')


if __name__=='__main__':
    lease = Path('/home/ugrp/ugrp-sim/leases')/f'act16w-playback-{os.getpid()}.json'
    with lease.open('x') as stream:
        json.dump(dict(task='act16w-playback',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),
            expected_end='finite saved timeline and final10SIM seconds; no wall cap',concurrency=0),stream)
    try:
        main()
    finally:
        if json.loads(lease.read_text()).get('pid') == os.getpid():
            lease.unlink()
