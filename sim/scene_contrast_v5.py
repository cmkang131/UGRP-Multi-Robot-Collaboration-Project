"""Explicit violet wall / unchanged v1 floor. Visual-only, default off."""
from __future__ import annotations
import hashlib
import json
import xml.etree.ElementTree as ET
from sim import render_profile as base
from sim import natural_scene_texture as v1
from sim import neutral_pickup_floor
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
    # 2026-10-18 nav gate: same indigo wall paint and the same published wall
    # textures (assets alias), but the pickup floor overlay is repainted
    # neutral (sim/neutral_pickup_floor.py) and light_scale raises the
    # noshadow_bright_v1 light colours from 0.30 to 0.70, so the floor is not
    # V~90.  sim/render_profile.py is byte-pinned by the p03 provider and is
    # deliberately not edited; the extra scale is applied here.
    # New name on purpose: the v5 profile stays frozen and reproducible.
    'walls_floor_contrast_v6_indigo110_s80_neutral_start': {
        'rgb':[90,75,110],'hsv':[133,81,110],'pattern':'v1_common_mode',
        'assets':'walls_floor_contrast_v5_indigo110_s80',
        'light_scale':0.70,'pickup':'neutral_grid_v1'},
    'walls_floor_contrast_v5_indigo125_s65': {'rgb':[107,93,125],'hsv':[133,65,125],'pattern':'v1_common_mode'},
    'walls_floor_contrast_v5_indigo100_flat': {'rgb':[54,18,100],'hsv':[133,209,100]},
}

TEXTURE_MANIFEST_SHA256='cf447537efe9fd66a01e18aa9f414dcabd8273f662d8dc4c96773bd2c9c96757'

def _base_light_scale():
    """The light scale noshadow_bright_v1 actually applies (one source of truth)."""
    for op in base.PROFILES['noshadow_bright_v1']['xml_ops']:
        if op['op']=='light_color_scale': return float(op['value'])
    raise ValueError('noshadow_bright_v1 lacks a light_color_scale op')

def _scale_lights(root,factor):
    """Multiply diffuse/ambient/specular of every <light> on top of noshadow_bright_v1."""
    for light in root.iter('light'):
        for key,default in base.LIGHT_COLOR_DEFAULTS.items():
            values=[float(v) for v in light.get(key).split()] if light.get(key) is not None else list(default)
            light.set(key,' '.join(f'{v*factor:.6g}' for v in values))

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
    if 'assets' in PROFILES[name]:
        spec['texture_asset_profile']=PROFILES[name]['assets']
    if 'light_scale' in PROFILES[name]:
        spec['base_render_profile']='noshadow_bright_v1'
        spec['light_scale']=float(PROFILES[name]['light_scale'])
        spec['light_scale_factor_vs_base']=round(float(PROFILES[name]['light_scale'])/_base_light_scale(),9)
    if PROFILES[name].get('pickup')=='neutral_grid_v1':
        spec['pickup_paint']=neutral_pickup_floor.record()
    return {**spec,'sha256':hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()}

def apply_xml(xml,name,*,extension=False):
    resolve(name)
    spec=PROFILES[name]
    root=ET.fromstring(base.apply_xml(xml,'noshadow_bright_v1'))
    if 'light_scale' in spec:
        _scale_lights(root,float(spec['light_scale'])/_base_light_scale())
    v1.apply(root,extension=extension)
    asset=root.find('asset')
    asset_profile=spec.get('assets',name)
    for geom in root.findall('worldbody/geom'):
        if not geom.get('name','').startswith('zone_wall_'): continue
        material='contrast_v5_'+geom.get('name')
        rgba=' '.join(str(c/255) for c in spec['rgb'])+' 1'
        attrs=dict(name=material,rgba=rgba,specular='0',shininess='0',reflectance='0')
        if spec.get('pattern'):
            old=asset.find(f"material[@name='{geom.get('material')}']")
            tex=asset.find(f"texture[@name='{old.get('texture')}']")
            import json
            record=json.loads((Path(__file__).parent/'assets/scene_contrast_v5/manifest.json').read_text())
            if extension:record['images'].update(v1.extension_manifest()['colour_images'])
            for a in ('fileright','fileleft','fileup','filedown','filefront','fileback'):
                file=tex.get(a);key=asset_profile+'/'+file
                path=Path(__file__).parent/'assets/scene_contrast_v5'/key
                if hashlib.sha256(path.read_bytes()).hexdigest()!=record['images'][key]:raise ValueError('v5 texture hash mismatch')
                tex.set(a,'../scene_contrast_v5/'+key)
            attrs.update(texture=old.get('texture'),texuniform='false',rgba='1 1 1 1')
        ET.SubElement(asset,'material',**attrs)
        geom.set('material',material); geom.set('rgba',attrs['rgba'])
    if spec.get('pickup')=='neutral_grid_v1':
        neutral_pickup_floor.apply_root(root)
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
    spec=PROFILES[resolve(name)]
    audit=base.verify_model(model,'noshadow_bright_v1')
    floor=model.geom('floor'); material=model.mat(int(model.geom_matid[floor.id]))
    tid=next(int(t) for t in np.asarray(material.texid).reshape(-1) if t>=0)
    n=int(model.tex_width[tid]*model.tex_height[tid]*model.tex_nchannel[tid]); start=int(model.tex_adr[tid])
    pixels=np.asarray(model.tex_data[start:start+n]).reshape(-1,3)
    original=np.asarray(Image.open(v1.checked_file('floor',v1.manifest(),v1.ASSETS)).convert('RGB')).reshape(-1,3)
    if pixels.shape!=original.shape or any(not np.array_equal(np.bincount(pixels[:,c],minlength=256),np.bincount(original[:,c],minlength=256)) for c in range(3)):
        raise RuntimeError('v5 floor differs from v1')
    walls=[model.geom(i) for i in range(model.ngeom) if model.geom(i).name.startswith('zone_wall_')]
    expected=np.asarray(([1.,1.,1.,1.] if spec.get('pattern') else [c/255 for c in spec['rgb']]+[1.]),dtype=model.geom_rgba.dtype)
    if not walls or any(not model.mat(int(model.geom_matid[g.id])).name.startswith('contrast_v5_') or not np.array_equal(model.geom_rgba[g.id],expected) for g in walls):
        raise RuntimeError('v5 wall binding mismatch')
    neutral=None
    if spec.get('pickup')=='neutral_grid_v1':
        tiles=[model.geom(i) for i in range(model.ngeom) if model.geom(i).name.startswith('zone_pickup_tile_')]
        pickup=[model.geom(i) for i in range(model.ngeom) if model.geom(i).name=='zone_pickup']
        if pickup or len(tiles)!=neutral_pickup_floor.TILES:
            raise RuntimeError(f'neutral pickup paint mismatch: removed={len(pickup)} tiles={len(tiles)}')
        if any(not np.allclose(np.asarray(model.geom_rgba[g.id])[:3],np.asarray(model.geom_rgba[g.id])[0])
               or float(model.geom_rgba[g.id][3])!=1. for g in tiles):
            raise RuntimeError('neutral pickup paint is not grey/opaque')
        neutral={'removed':0,'tiles':len(tiles),'saturation':0.}
    record={**audit,'contrast':profile_record(name),'floor_v1_histogram_exact':True,'checked_walls':len(walls)}
    if neutral is not None: record['neutral_pickup']=neutral
    return record
