"""Explicit violet wall / unchanged v1 floor. Visual-only, default off."""
from __future__ import annotations
import hashlib
import json
import xml.etree.ElementTree as ET
from sim import render_profile as base
from sim import natural_scene_texture as v1
from pathlib import Path

# Authored appearances, NOT detector acceptance thresholds. R1 violet collided
# with existing C paint after rendering. R2 indigo uses nominal H133 and lower V;
# rendered/JPEG legacy overlaps are measured, never inferred from nominal HSV.
PROFILES = {
    'walls_floor_contrast_v5_violet150': {'rgb': [121,26,150], 'hsv': [143,210,150]},
    'walls_floor_contrast_v5_violet175': {'rgb': [146,31,175], 'hsv': [144,210,175]},
    'walls_floor_contrast_v5_violet195': {'rgb': [168,34,195], 'hsv': [145,210,195]},
    'walls_floor_contrast_v5_indigo100': {'rgb':[54,18,100],'hsv':[133,209,100],'pattern':'v1_common_mode'},
    'walls_floor_contrast_v5_indigo85': {'rgb':[46,15,85],'hsv':[133,210,85],'pattern':'v1_common_mode'},
    'walls_floor_contrast_v5_indigo110_s80': {'rgb':[90,75,110],'hsv':[133,81,110],'pattern':'v1_common_mode'},
    'walls_floor_contrast_v5_indigo125_s65': {'rgb':[107,93,125],'hsv':[133,65,125],'pattern':'v1_common_mode'},
    'walls_floor_contrast_v5_indigo100_flat': {'rgb':[54,18,100],'hsv':[133,209,100]},
}

TEXTURE_MANIFEST_SHA256='cf447537efe9fd66a01e18aa9f414dcabd8273f662d8dc4c96773bd2c9c96757'

def resolve(name):
    if name not in PROFILES: raise ValueError('explicit v5 scene required: '+str(name))
    return name

def profile_record(name):
    spec = {'schema':'ugrp.scene_contrast.v5','name':resolve(name),'wall':PROFILES[name],
            'floor_manifest_sha256':v1.MANIFEST_SHA256,'wall_pattern':PROFILES[name].get('pattern','none'),
            'required_camera_quality':'no_mip_v1','changes_physics':False,'default':'off'}
    if PROFILES[name].get('pattern'):
        raw=(Path(__file__).parent/'assets/scene_contrast_v5/manifest.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=TEXTURE_MANIFEST_SHA256:raise ValueError('v5 texture manifest hash mismatch')
        spec['texture_manifest_sha256']=TEXTURE_MANIFEST_SHA256
    return {**spec,'sha256':hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()}

def apply_xml(xml,name,*,extension=False):
    resolve(name)
    root=ET.fromstring(base.apply_xml(xml,'noshadow_bright_v1'))
    v1.apply(root,extension=extension)
    asset=root.find('asset')
    for geom in root.findall('worldbody/geom'):
        if not geom.get('name','').startswith('zone_wall_'): continue
        material='contrast_v5_'+geom.get('name')
        rgba=' '.join(str(c/255) for c in PROFILES[name]['rgb'])+' 1'
        attrs=dict(name=material,rgba=rgba,specular='0',shininess='0',reflectance='0')
        if PROFILES[name].get('pattern'):
            old=asset.find(f"material[@name='{geom.get('material')}']")
            tex=asset.find(f"texture[@name='{old.get('texture')}']")
            import json
            record=json.loads((Path(__file__).parent/'assets/scene_contrast_v5/manifest.json').read_text())
            if extension:record['images'].update(v1.extension_manifest()['colour_images'])
            for a in ('fileright','fileleft','fileup','filedown','filefront','fileback'):
                file=tex.get(a);key=name+'/'+file
                path=Path(__file__).parent/'assets/scene_contrast_v5'/key
                if hashlib.sha256(path.read_bytes()).hexdigest()!=record['images'][key]:raise ValueError('v5 texture hash mismatch')
                tex.set(a,'../scene_contrast_v5/'+key)
            attrs.update(texture=old.get('texture'),texuniform='false',rgba='1 1 1 1')
        ET.SubElement(asset,'material',**attrs)
        geom.set('material',material); geom.set('rgba',attrs['rgba'])
    return ET.tostring(root,encoding='unicode')

def install(scene,name,*,extension=False):
    resolve(name)
    if getattr(scene,'_render_profile_name',None) is not None: raise ValueError('scene already dressed')
    inner=scene.transform
    def transform(xml):
        before=inner(xml); after=apply_xml(before,name,extension=extension)
        scene.manifest['render_profile']={**profile_record(name),
            'scene_xml_sha256_before_profile':hashlib.sha256(before.encode()).hexdigest(),
            'scene_xml_sha256_after_profile':hashlib.sha256(after.encode()).hexdigest()}
        return after
    scene.transform=transform; scene._render_profile_name=name
    return scene

def verify_model(model,name):
    # Reuse v4's exact floor histogram check with an explicitly renamed binding;
    # keep this implementation independent so older v4 profile results are frozen.
    import numpy as np
    from PIL import Image
    audit=base.verify_model(model,'noshadow_bright_v1')
    floor=model.geom('floor'); material=model.mat(int(model.geom_matid[floor.id]))
    tid=next(int(t) for t in np.asarray(material.texid).reshape(-1) if t>=0)
    n=int(model.tex_width[tid]*model.tex_height[tid]*model.tex_nchannel[tid]); start=int(model.tex_adr[tid])
    pixels=np.asarray(model.tex_data[start:start+n]).reshape(-1,3)
    original=np.asarray(Image.open(v1.checked_file('floor',v1.manifest(),v1.ASSETS)).convert('RGB')).reshape(-1,3)
    if pixels.shape!=original.shape or any(not np.array_equal(np.bincount(pixels[:,c],minlength=256),np.bincount(original[:,c],minlength=256)) for c in range(3)):
        raise RuntimeError('v5 floor differs from v1')
    walls=[model.geom(i) for i in range(model.ngeom) if model.geom(i).name.startswith('zone_wall_')]
    expected=np.asarray(([1.,1.,1.,1.] if PROFILES[resolve(name)].get('pattern') else [c/255 for c in PROFILES[name]['rgb']]+[1.]),dtype=model.geom_rgba.dtype)
    if not walls or any(not model.mat(int(model.geom_matid[g.id])).name.startswith('contrast_v5_') or not np.array_equal(model.geom_rgba[g.id],expected) for g in walls):
        raise RuntimeError('v5 wall binding mismatch')
    return {**audit,'contrast':profile_record(name),'floor_v1_histogram_exact':True,'checked_walls':len(walls)}
