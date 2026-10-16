"""Default-off native visual semantics on MJWarp ray-traced RGB.

Two source differences, not fitted RGB/gamma constants:
* GL_SPOT_CUTOFF=180 disables spotlight exponent (POINT semantics).
* MuJoCo classic render_gl3.c1364-1389 draws transparent geoms in both
  distance orders, using authored alpha and no transparent depth writes.
Pinned MJWarp renders nonzero alpha as an opaque first hit. Re-rendering each
transparent layer with all opaque occluders preserves that visibility, and
then performs the native blend orders. Physics model/state are not changed.
All geometry/segmentation in this module remains renderer-internal.
"""
from __future__ import annotations
import numpy as np
from scripts.warp9_profile import phase


def texture_after_lighting_factory():
    """Private generated kernel; never edits the installed/shared MJWarp files.

    Classic GL_MODULATE multiplies the texture by clamped lit primary colour.
    Pinned MJWarp multiplies base colour by texture before lighting/clamping.
    The exact three source substitutions are checked before compilation.
    """
    import hashlib,inspect
    from pathlib import Path
    import importlib
    module=importlib.import_module('mujoco_warp._src.render')
    source=inspect.getsource(module._build_megakernel)
    replacements=[('    base_color = wp.vec3(color[0], color[1], color[2])',
        '    base_color = wp.vec3(color[0], color[1], color[2])\n    texture_color = wp.vec3(1.0, 1.0, 1.0)'),
        ('          base_color = wp.cw_mul(base_color, tex_color)','          texture_color = tex_color'),
        ('    if wp.static(has_splats):\n      hit_color = splat_color + hit_color * splat_transmittance',
         '    hit_color = wp.cw_mul(hit_color, texture_color)\n    if wp.static(has_splats):\n      hit_color = splat_color + hit_color * splat_transmittance')]
    for before,after in replacements:
        if source.count(before)!=1:raise ValueError('pinned MJWarp texture modulation source changed')
        source=source.replace(before,after)
    sha=hashlib.sha256(source.encode()).hexdigest()
    path=Path('/home/ugrp/ugrp-sim/runs/warp5/generated-shaders')/(sha+'.py');path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_text()!=source:raise ValueError('generated shader collision')
    if not path.exists():path.write_text(source)
    namespace=module.__dict__.copy();exec(compile(source,str(path),'exec'),namespace)
    return namespace['_build_megakernel'],dict(path=str(path),sha256=sha,edits=len(replacements),
        original_factory_sha256=hashlib.sha256(inspect.getsource(module._build_megakernel).encode()).hexdigest())


def rgba_values(model):
    rgba=model.geom_rgba.copy()
    for i,mid in enumerate(model.geom_matid):
        if mid>=0 and np.array_equal(rgba[i],[.5,.5,.5,1.]):rgba[i]=model.mat_rgba[mid]
    return rgba


def blend_native(opaque,layers,alpha,order):
    """Native front/back then back/front geom order, independently per world."""
    out=opaque.astype(float).copy()
    for indices in (order,order[:,::-1]):
        for rank in range(indices.shape[1]):
            for w,j in enumerate(indices[:,rank]):
                colour,mask=layers[j];a=alpha[j]
                out[w][mask[w]]=a*colour[w][mask[w]]+(1-a)*out[w][mask[w]]
    return out


class Renderer:
    def __init__(self,model,wm,wd,cameras,*,enabled=False,samples_per_pixel=1,texture_after_lighting=False,profile=None):
        import mujoco_warp as mjw,warp as wp
        self.m,self.wm,self.wd,self.wp,self.mjw=model,wm,wd,wp,mjw
        self.cameras=cameras;self.enabled=enabled;self.n=int(wd.nworld)
        self.warp9_profile=profile
        self.rc=mjw.create_render_context(model,nworld=self.n,cam_res=[c[2] for c in cameras],
            render_rgb=True,render_depth=False,render_seg=True,use_textures=True,use_shadows=True,
            enabled_geom_groups=[0,1,2,3],cam_active=[c[1] for c in cameras],samples_per_pixel=samples_per_pixel)
        shader=None
        if texture_after_lighting:
            if not enabled:raise ValueError('texture correction requires explicit native visual profile')
            factory,shader=texture_after_lighting_factory();self.rc._megakernel=factory(wm,self.rc)
        rgba=rgba_values(model)
        # Native's .995 transparent-list criterion, not a detector threshold.
        self.ids=np.flatnonzero((rgba[:,3]>0)&(rgba[:,3]<.995)&(model.geom_group<4))
        self.alpha=rgba[self.ids,3]
        self.point_ids=np.flatnonzero((model.light_type==0)&(model.light_cutoff==180))
        self.audit=dict(profile='warp5_native_visual_v2' if texture_after_lighting else 'warp5_native_visual_v1' if enabled else 'off',
            transparent_geom_ids=self.ids.tolist(),authored_alpha=self.alpha.tolist(),
            point180_ids=self.point_ids.tolist(),samples_per_pixel=samples_per_pixel,
            actor_segmentation_reads=0,physics_changes=0,generated_shader=shader,
            basis='OpenGL180 cutoff and classic renderer two-order authored-alpha blending; no RGB fit')

    def _capture(self):
        wp,mjw=self.wp,self.mjw
        with phase(self,'render_refit_gpu',device=True):
            mjw.refit_bvh(self.wm,self.wd,self.rc);mjw.render(self.wm,self.wd,self.rc)
        values={}
        for k,(rid,_,(w,h)) in enumerate(self.cameras):
            with phase(self,'render_allocate'):
                rgb=wp.zeros((self.n,h,w),dtype=wp.vec3);seg=wp.zeros((self.n,h,w),dtype=wp.vec2i)
            with phase(self,'render_extract_gpu',device=True):
                mjw.get_rgb(self.rc,k,rgb);mjw.get_segmentation(self.rc,k,seg)
            with phase(self,'render_existing_sync',explicit_syncs=1):
                wp.synchronize()
            with phase(self,'render_d2h',nbytes=self.n*h*w*20,implicit_syncs=2):
                rgb_cpu,seg_cpu=rgb.numpy(),seg.numpy()
            with phase(self,'render_cpu_convert'):
                values[rid]=(rgb_cpu.astype(float)*255,seg_cpu)
        return values

    def readback(self,array,name):
        if self.warp9_profile:return self.warp9_profile.numpy(array,name=name)
        return array.numpy()

    def upload(self,array,value):
        with phase(self,'render_model_h2d',device=True,nbytes=value.nbytes):
            self.wp.copy(array,self.wp.array(value,dtype=array.dtype))

    def render(self):
        wp,mjw=self.wp,self.mjw
        with phase(self,'render_kinematics_gpu',device=True):
            mjw.kinematics(self.wm,self.wd);mjw.camlight(self.wm,self.wd)
        original_type=self.readback(self.wm.light_type,'render_model_d2h')
        original_rgba=self.readback(self.wm.geom_rgba,'render_model_d2h')
        try:
            if self.enabled:
                # MJWarp's SPOT=0/DIRECTIONAL=1/POINT=2; copied from the pinned
                # compute_lighting branch and MuJoCo mjtLightType enum.
                lights=original_type.copy();lights[:,self.point_ids]=2
                self.upload(self.wm.light_type,lights)
            front=self._capture()
            if not self.enabled or not len(self.ids):return front
            hidden=original_rgba.copy();hidden[:,self.ids,3]=0
            self.upload(self.wm.geom_rgba,hidden)
            opaque=self._capture();layers={rid:[] for rid,_,_ in self.cameras}
            for gid in self.ids:
                one=hidden.copy();one[:,gid]=original_rgba[:,gid]
                self.upload(self.wm.geom_rgba,one)
                value=self._capture()
                for rid,_,_ in self.cameras:
                    rgb,seg=value[rid];layers[rid].append((rgb,seg[...,0]==gid))
            positions=self.readback(self.wd.geom_xpos,'render_sort_d2h')[:,self.ids]
            cameras=self.readback(self.wd.cam_xpos,'render_sort_d2h')
            result={}
            for rid,name,_ in self.cameras:
                cid=self.m.camera(name).id
                distances=np.linalg.norm(positions-cameras[:,cid,None],axis=2)-self.m.geom_rbound[self.ids]
                order=np.argsort(distances,axis=1,kind='stable')
                with phase(self,'render_blend_cpu'):
                    result[rid]=(blend_native(opaque[rid][0],layers[rid],self.alpha,order),front[rid][1])
            return result
        finally:
            self.upload(self.wm.light_type,original_type)
            self.upload(self.wm.geom_rgba,original_rgba)
