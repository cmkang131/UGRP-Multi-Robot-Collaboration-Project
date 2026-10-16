"""Static (no physics stepping) floor / detection / texture check for the floor-colour profile (``floor_light_v1``).

Same recorded A/B states as ``calibrate_brightness.py`` (mjSTATE_INTEGRATION checkpoints, ``mj_forward`` only). For each
candidate profile it renders the robots' own camera through the real port path (fisheye + JPEG q82) and, with a
segmentation render remapped by the same fisheye map, measures per-object pixels: floor (floor + the zone marking
overlays lying on it), cargo bar (beam), dark grip bands, wall tags, walls. Candidate profiles are registered at run time
from ``--candidates`` (name -> [light_scale, [rgb1, rgb2] | null]); ``shadows_v1`` / ``noshadow_v1`` /
``noshadow_bright_v1`` / ``floor_light_v1`` are the real registered profiles.

  python experiments/2026-09-29-render-profile/static_frames/calibrate_floor.py <ab_raw_root> <out.json> [--states a,b] [--candidates JSON]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import cv2
import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))
import calibrate_brightness as cb  # noqa: E402
from harness import owncam_pair_beam_v2 as b2  # noqa: E402
from harness.zone_pair_vision import _valid  # noqa: E402
from sim import render_profile as rp  # noqa: E402

BASE_OPS=[{'op':'light_castshadow','value':'false'},{'op':'material_reflectance','value':'0'},{'op':'light_cutoff','value':'180'}]
def register(name,k,floor=None):
    ops=list(BASE_OPS)+[{'op':'light_color_scale','value':str(k)}]
    if floor: ops.append({'op':'texture_rgb','texture':'ground','rgb1':floor[0],'rgb2':floor[1]})
    rp.PROFILES[name]={'summary':'exploration','xml_ops':ops}
def classify(m):
    cls=np.zeros(m.ngeom,dtype=np.int8) # 0 other,1 floor,2 beam,3 tag,4 wall
    for g in range(m.ngeom):
        n=mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,g) or ''
        if n=='floor' or (n.startswith('zone_') and not n.startswith('zone_wall')): cls[g]=1
        elif n.endswith('__bar'): cls[g]=2
        elif '__band_' in n: cls[g]=5
        elif n.startswith('tag_'): cls[g]=3
        elif n.startswith('zone_wall'): cls[g]=4
    return cls
def render_seg(host,rid):
    w=host.world; r=w.robot(rid)
    def go():
        with w.physics_lock, w.render_lock:
                r._sync_real_camera_mount()
                rend=w.renderer
                rend.update_scene(w.data,camera=r._n('robot_cam'),scene_option=r._robot_sensor_scene_option)
                ideal=rend.render().copy()
                rend.enable_segmentation_rendering()
                rend.update_scene(w.data,camera=r._n('robot_cam'),scene_option=r._robot_sensor_scene_option)
                seg=rend.render().copy(); rend.disable_segmentation_rendering()
        return ideal,seg,r._robot_fisheye_map
    return w._render_executor.submit(go).result()

def analyze(host,rid,cls):
    ideal,seg,(mx,my)=render_seg(host,rid)
    frame=cv2.remap(ideal,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    ok,buf=cv2.imencode('.jpg',cv2.cvtColor(frame,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,82]); bgr=cv2.imdecode(buf,cv2.IMREAD_COLOR)
    rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
    gid=cv2.remap(seg[...,0].astype(np.float32),mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=-1)
    typ=cv2.remap(seg[...,1].astype(np.float32),mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=-1)
    gid=np.where(typ==5,gid,-1).astype(int)
    c=np.where(gid>=0,cls[np.clip(gid,0,None)],-1)
    valid=_valid()
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV); V=hsv[...,2].astype(float)
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    out={'gate':cb.stats(rgb)}
    fl=(c==1)&valid; bd_=(c==5)&valid; bm=(c==2)&valid; tg=(c==3)&valid; wl=(c==4)&valid
    def vs(mask):
        return None if mask.sum()<20 else {'n':int(mask.sum()),'meanV':float(V[mask].mean()),'p10V':float(np.percentile(V[mask],10)),'sat':float((V[mask]>=250).mean())}
    out['band']=vs(bd_); out['floor']=vs(fl); out['beam']=vs(bm); out['wall']=vs(wl)
    out['tag']=None if tg.sum()<20 else {'n':int(tg.sum()),'contrast_p95_p5':float(np.percentile(V[tg],95)-np.percentile(V[tg],5))}
    mask=b2.beam_colour_mask(bgr)&valid
    out['beam_detect']={'beam_px':int(bm.sum()),'mask_px':int(mask.sum()),'mask_on_beam':int((mask&bm).sum()),'mask_on_floor':int((mask&fl).sum()),
                        'mask_on_other':int((mask&~bm&~fl).sum())}
    if fl.sum()>=200:
        er=cv2.erode(fl.astype(np.uint8),np.ones((7,7),np.uint8)).astype(bool)
        gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3); gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)
        grad=np.hypot(gx,gy)
        pts=cv2.goodFeaturesToTrack(gray,maxCorners=1000,qualityLevel=0.01,minDistance=6,mask=er.astype(np.uint8)*255)
        gf=gray[er].astype(float)
        out['floor_tex']={'n_eroded':int(er.sum()),'grad_mean':float(grad[er].mean()),'grad_p90':float(np.percentile(grad[er],90)),
                          'corners':0 if pts is None else int(len(pts)),'gray_p90_p10':float(np.percentile(gf,90)-np.percentile(gf,10)),
                          'gray_rel_contrast':float((np.percentile(gf,90)-np.percentile(gf,10))/max(np.percentile(gf,90)+np.percentile(gf,10),1))}
    else: out['floor_tex']=None
    return out


REAL = ('shadows_v1', 'noshadow_v1', 'noshadow_bright_v1', 'floor_light_v1')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('raw_root')
    ap.add_argument('out')
    ap.add_argument('--states', default='')
    ap.add_argument('--candidates', default='{}')
    args = ap.parse_args()
    root = Path(args.raw_root)
    cands = {n: None for n in REAL}
    for name, (k, floor) in json.loads(args.candidates).items():
        register(name, k, floor)
        cands[name] = name
    keep = [s for s in args.states.split(',') if s]
    states = [s for s in cb.STATES if not keep or s[0] in keep]
    out = {}
    for name in cands:
        prof = None if name == 'shadows_v1' else name
        for label, run, case_dir, ck in states:
            with tempfile.TemporaryDirectory() as tmp:
                host = cb.build_host(root, run, case_dir, Path(tmp), render_profile=prof)
                m, d = host.world.model, host.world.data
                arr = np.load(root / run / 'cases' / case_dir / 'checkpoints' / f'{ck}.npz')['mj_state_integration']
                mujoco.mj_setState(m, d, arr, mujoco.mjtState.mjSTATE_INTEGRATION)
                mujoco.mj_forward(m, d)
                cls = classify(m)
                for rid in ('r1', 'r2'):
                    out[f'{name}|{label}|{rid}'] = analyze(host, rid, cls)
                host.world.close()
        print(name, 'done', flush=True)
    Path(args.out).write_text(json.dumps({'mujoco': mujoco.__version__, 'rows': out}, indent=1))


if __name__ == '__main__':
    main()
