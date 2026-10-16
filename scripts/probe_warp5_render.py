"""Finite gcp2-L4 static 88-pose audit, no physics or controller truth input.

Uses the unchanged scene-tex5 authored fixtures and production camera. CPU and
MJWarp are separate cohorts at identical qpos. Segmentation is scoring only.
No detector acceptance constants are fitted by this program.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, platform, subprocess, sys, time
from pathlib import Path
import cv2
import numpy as np

PROFILE = 'walls_floor_contrast_v5_indigo110_s80'


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False, default=lambda x: x.item() if isinstance(x,np.generic) else x.tolist())+'\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_metrics(image, pwm, masks, calibration, after):
    from scripts.probe_scene_tex3 import measure, semantic
    from scripts.score_scene_tex5 import signal
    from scripts.audit_scene_tex5_colours import counts
    from harness.scene_colour_boundary import ColourBoundaryState
    from harness.e2e_stall_odometry import flow_pair
    # Image-only functions receive no simulator object/pose/segmentation.
    return dict(orb=measure(image,masks), semantic=semantic(image,pwm),
                colours=counts(image,pwm),
                boundary=signal(image,after,pwm,masks,ColourBoundaryState(PROFILE,calibration)),
                rgb_stall_static=flow_pair(cv2.cvtColor(image,cv2.COLOR_BGR2RGB),cv2.cvtColor(image,cv2.COLOR_BGR2RGB)),
                rgb_stall_one_pixel_yaw=flow_pair(cv2.cvtColor(image,cv2.COLOR_BGR2RGB),cv2.cvtColor(after,cv2.COLOR_BGR2RGB)))


def encode(image):
    from PIL import Image
    b=io.BytesIO();Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).save(b,format='JPEG',quality=82)
    return b.getvalue(),cv2.imdecode(np.frombuffer(b.getvalue(),np.uint8),cv2.IMREAD_COLOR)


def run(args):
    import mujoco, mujoco_warp as mjw, warp as wp
    from scripts import probe_scene_tex2 as old, probe_scene_tex3 as probe
    from scripts.generate_scene_textures import MAPS
    from scripts.simalt_physics_compare import unused_efm
    from sim import camera_render_quality as quality
    from sim.masterpi_camera_profile import raw_fisheye_remap,CAMERA_FX_PX
    old.validate_source(args.source_sha)
    wp.init();cv2.setNumThreads(1)
    args.output.mkdir(parents=True,exist_ok=False)
    calibration=json.loads(args.calibration.read_text())
    mx,my=raw_fisheye_remap(640,480)
    rows=[];errors=[]
    command=[sys.executable,'-m','scripts.probe_warp5_render',*sys.argv[1:]]
    meta=dict(source_sha=args.source_sha,host=platform.node(),mujoco=mujoco.__version__,
              mjwarp=getattr(mjw,'__version__','unversioned'),physics_steps=0,model_calls=0,
              scene=PROFILE,quality='no_mip_v1',rgb=[640,480],shared_load=True,
              calibration_sha256=digest(args.calibration),calibration=str(args.calibration),
              renderer_options=dict(samples_per_pixel=args.samples_per_pixel,use_shadows=True,use_textures=True,warp5_native_visual_v1=args.warp5_native_visual_v1),
              reproduction=command,pool_with_cpu=False,segmentation='evaluation only')
    write(args.output/'meta.json',meta)
    try:
      for map_path in MAPS:
        model,scene,hardware,xml,audit=old.build_model(map_path,PROFILE)
        width,height=quality.configure_model(model,'no_mip_v1')
        renderer=mujoco.Renderer(model,height,width)
        quality.configure_context(renderer,model,'no_mip_v1')
        groups=old.geometry_groups(model,scene)
        fixtures=[]
        data=mujoco.MjData(model)
        for vi,view in enumerate(old.wall_views(json.loads(map_path.read_text()))):
          for pose in old.poses_for_view(vi):
            pwm,setup=old.fixture(model,data,scene,view,pose,hardware)
            fixtures.append(dict(view=vi,pose=pose,pwm=pwm,qpos=data.qpos.copy(),qvel=data.qvel.copy()))
        n=len(fixtures)
        wm=mjw.put_model(model)
        # Workspace capacity comes from the authored fixture's actual contacts
        # and constraints; this is allocation, never a detector/physics gate.
        ncon=1 << (max(32,int(data.ncon))-1).bit_length()
        njmax=1 << (max(256,int(data.nefc))-1).bit_length()
        with unused_efm(model,data):wd=mjw.put_data(model,data,nworld=n,nconmax=ncon,njmax=njmax)
        from scripts.warp5_render import Renderer
        rc=Renderer(model,wm,wd,[(r,r+'__robot_cam',(640,480)) for r in old.ROBOTS],
              enabled=args.warp5_native_visual_v1,samples_per_pixel=args.samples_per_pixel)
        write(args.output/(map_path.stem+'-render-compat.json'),rc.audit)
        base=np.stack([f['qpos'] for f in fixtures])
        def render(qpos):
            wp.copy(wd.qpos,wp.array(qpos,dtype=wd.qpos.dtype))
            return {rid:(np.clip(value[0],0,255).astype(np.uint8),value[1]) for rid,value in rc.render().items()}
        before=render(base)
        # Same single raw-camera pixel yaw increment as scene-tex5, eval only.
        for rid in old.ROBOTS:
          bid=model.body(rid+'__robot').id;adr=int(model.jnt_qposadr[int(model.body_jntadr[bid])])
          after_q=base.copy();c,s=np.cos(np.arctan(1/CAMERA_FX_PX)/2),np.sin(np.arctan(1/CAMERA_FX_PX)/2)
          for q in after_q:
            w,x,y,z=q[adr+3:adr+7];q[adr+3:adr+7]=[c*w-s*z,c*x-s*y,c*y+s*x,c*z+s*w]
          after=render(after_q)[rid][0]
          for i,f in enumerate(fixtures):
            stem=f'{map_path.stem}--view{f["view"]}--{f["pose"]}--{rid}'
            data.qpos[:]=f['qpos'];data.qvel[:]=f['qvel'];mujoco.mj_forward(model,data)
            cpu,cmasks,_=probe.capture(renderer,model,data,rid,groups,'no_mip_v1')
            data.qpos[:]=after_q[i];mujoco.mj_forward(model,data)
            cpu_next,_,_=probe.capture(renderer,model,data,rid,groups,'no_mip_v1')
            image,ids=before[rid][0][i],before[rid][1][i]
            image=cv2.cvtColor(cv2.remap(image,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT),cv2.COLOR_RGB2BGR)
            nxt=cv2.cvtColor(cv2.remap(after[i],mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT),cv2.COLOR_RGB2BGR)
            ids=np.where(ids[...,1]==int(mujoco.mjtObj.mjOBJ_GEOM),ids[...,0],-1).astype(np.float32)
            ids=cv2.remap(ids,mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=-1).astype(int)
            masks={k:np.isin(ids,list(v)) for k,v in groups.items()}
            row=dict(case=stem,map=map_path.stem,pose=f['pose'],robot=rid,pwm=f['pwm'],
                     qpos_sha256=old._array_digest(f['qpos']),metrics={})
            for backend,first,next_image,mm in [('cpu',cpu['final'],cpu_next['final'],cmasks['final']),('mjwarp',image,nxt,masks)]:
                raw,jpeg=encode(first);_,next_jpeg=encode(next_image)
                (args.output/(stem+'--'+backend+'.jpg')).write_bytes(raw)
                for surface in ('floor','wall'):
                    cv2.imwrite(str(args.output/(stem+'--'+backend+'--mask-'+surface+'.png')),mm[surface].astype(np.uint8)*255)
                row['metrics'][backend]=runtime_metrics(jpeg,f['pwm'],mm,calibration,next_jpeg)
            row['rgb_mae']=float(np.abs(cpu['final'].astype(float)-image).mean())
            write(args.output/(stem+'.json'),row);rows.append(row)
            print(stem,flush=True)
        renderer.close()
        del rc,wd,wm,before,after
    except BaseException as exc:
        import traceback
        errors.append(dict(category='HOST_ERROR',reason=repr(exc),blocked_object='static_render_audit',minimum_gap_m=None,gap_scope='not_applicable',traceback=traceback.format_exc()))
        raise
    finally:
        write(args.output/'index.json',[r['case'] for r in rows])
        write(args.output/'rejection-table.json',dict(stages=[dict(stage='planned',cumulative_pass_n=88,rejected_n=0),dict(stage='rendered_and_analysed',cumulative_pass_n=len(rows),rejected_n=88-len(rows))],errors=errors,raw=str(args.output),reproduction=command))
        write(args.output/'summary.json',dict(**meta,frames=len(rows),status='MEASURED' if len(rows)==88 and not errors else 'HOST_ERROR',errors=errors))
        write(args.output/'SHA256SUMS.json',{p.name:digest(p) for p in args.output.iterdir() if p.is_file()})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-sha',required=True);p.add_argument('--calibration',type=Path,required=True)
    p.add_argument('--samples-per-pixel',type=int,default=1);p.add_argument('--execute',action='store_true')
    p.add_argument('--warp5-native-visual-v1',action='store_true')
    a=p.parse_args()
    if not a.execute or platform.system()!='Linux' or not platform.node().startswith('ugrp-act-l4-gcp2'):
        p.error('explicit gcp2 L4 execution required')
    run(a)


if __name__=='__main__':main()
