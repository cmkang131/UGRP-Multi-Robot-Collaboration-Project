"""XML/ABI tests only; no model, physics or renderer."""
import xml.etree.ElementTree as ET
import pytest
from sim import scene_contrast_v5 as v5
from sim.render_profile_selection import for_name
from scripts.generate_scene_textures import MAPS
from tests.test_natural_scene_texture import scene_xml

@pytest.mark.parametrize('name',list(v5.PROFILES))
@pytest.mark.parametrize('map_path',MAPS,ids=lambda p:p.stem)
def test_wall_only(name,map_path):
    before=ET.fromstring(for_name('floor_light_textured_v1').apply_xml(scene_xml(map_path),'floor_light_textured_v1'))
    after=ET.fromstring(for_name(name).apply_xml(scene_xml(map_path),name))
    a,b=list(before.find('worldbody').iter()),list(after.find('worldbody').iter())
    assert len(a)==len(b)
    for x,y in zip(a,b):
        aa,bb=dict(x.attrib),dict(y.attrib)
        if x.get('name','').startswith('zone_wall_'):
            for k in ('material','rgba'):aa.pop(k,None);bb.pop(k,None)
        assert (x.tag,aa)==(y.tag,bb)
    for tag in ('option','actuator','compiler'):
        assert ET.tostring(before.find(tag))==ET.tostring(after.find(tag))
    for tag,key in [('texture','ground'),('material','groundmat')]:
        assert ET.tostring(before.find(f'asset/{tag}[@name="{key}"]'))==ET.tostring(after.find(f'asset/{tag}[@name="{key}"]'))
    assert v5.profile_record(name)['default']=='off'

def test_default_unchanged():
    assert for_name(None).resolve(None) is None
    with pytest.raises(ValueError):v5.resolve(None)

@pytest.mark.parametrize('name',list(v5.PROFILES))
def test_nearclip_binding(name):
    from sim.final_pair_highpose_nearclip import wrap
    class Scene:
        def transform(self,xml):
            self.manifest={}
            return xml
    scene=wrap(v5.install(Scene(),name))
    scene.transform(scene_xml())
    assert scene.manifest['render_nearclip']['base_profile']==name

def calibration_for_test(profile='walls_floor_contrast_v5_violet175'):
    import cv2,numpy as np
    colours=np.uint8([[[150,150,150],[175,31,146]]])
    lab=cv2.cvtColor(colours,cv2.COLOR_BGR2LAB)[0].astype(float)
    axis=lab[1,1:]-lab[0,1:];axis/=np.linalg.norm(axis)
    return {'schema':'ugrp.scene_colour_calibration.v1','scene_profile':profile,'scene_sha256':v5.profile_record(profile)['sha256'],
            'axis_ab':axis.tolist(),'split':float(np.mean(lab[:,1:]@axis)),
            'lab':{s:{'p00':row.tolist(),'p100':row.tolist()} for s,row in zip(('floor','wall'),lab)}}

def test_colour_mask_abstains_on_cargo_and_requires_explicit_scene():
    import numpy as np
    from harness.scene_colour_boundary import ColourBoundaryState,surface_masks
    cal=calibration_for_test()
    state=ColourBoundaryState(cal['scene_profile'],cal)
    pixels=np.uint8([[[150,150,150],[175,31,146],[0,0,255],[255,255,0],[0,255,255],[0,255,0]]])
    masks,_=surface_masks(pixels,state.calibration)
    assert masks['floor'].tolist()==[[True,False,False,False,False,False]]
    assert masks['wall'].tolist()==[[False,True,False,False,False,False]]
    with pytest.raises(ValueError):ColourBoundaryState('floor_light_textured_v1',cal)
    with pytest.raises(ValueError):ColourBoundaryState('walls_floor_contrast_v5_violet150',cal)

def test_off_path_delegates_without_new_processing():
    from harness.wall_contact_detector import detect
    class Frozen:
        def detect(self,*args,**kwargs):
            assert kwargs==dict(params={'x':1},loaded=False)
            return 'original'
    assert detect(Frozen(),'rgb','cm',params={'x':1})=='original'
    with pytest.raises(ValueError):
        detect(Frozen(),'rgb','cm',params={},wall_detector='scene_colour_transition_v1')

def test_transition_preserves_abi_and_does_not_fill_orange_occlusion():
    import numpy as np
    from harness.active_wall_vision import modules
    from harness.active_camera import transform
    from harness.scene_colour_boundary import ColourBoundaryState,detect
    from scripts.zone_teacher import FOLDED
    mp,hfw,_=modules()
    origin,rotation=transform(FOLDED)
    cm=mp.ColumnModel(tuple(sorted(FOLDED.items())),0.,mp.column_positions(96,2),camera_transform=(origin,rotation))
    # Synthetic pinhole plate, no rendering. Floor at bottom, violet above.
    im=np.full((480,640,3),[150,150,150],dtype=np.uint8);im[:300]=[175,31,146]
    state=ColourBoundaryState('walls_floor_contrast_v5_violet175',calibration_for_test())
    result=detect(hfw,im,cm,params={},loaded=False,state=state)
    assert set(result)=={'vb','vt','h','h_lb','c','s','r','b'}
    assert all(v.shape==(96,3) for v in result.values())
    valid=np.isfinite(result['vb'][:,0])
    assert valid.sum()>80
    assert np.allclose(result['vb'][valid,0],299.)
    im[200:450,280:360]=[0,120,255]
    masked=detect(hfw,im,cm,params={},loaded=False,state=state)
    inside=(cm.columns>280)&(cm.columns<360)
    assert np.isnan(masked['vb'][inside]).all()
    assert state.last_result['interpolated_missing_columns']==0

def test_low_amplitude_assets_preserve_v1_spatial_variation():
    import hashlib,json,numpy as np
    from PIL import Image
    from pathlib import Path
    from sim import natural_scene_texture as v1
    root=Path(v5.__file__).parent/'assets/scene_contrast_v5'
    assert hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()==v5.TEXTURE_MANIFEST_SHA256
    manifest=json.loads((root/'manifest.json').read_text())
    record=v1.manifest()
    original={v['file']:v1.checked_file(k,record,v1.ASSETS) for k,v in record['images'].items() if k!='floor'}
    for key,digest in manifest['images'].items():
        assert hashlib.sha256((root/key).read_bytes()).hexdigest()==digest
        name,file=key.split('/',1)
        old=np.asarray(Image.open(original[file])).astype(int)
        new=np.asarray(Image.open(root/key)).astype(int)
        assert np.array_equal(new,np.array(v5.PROFILES[name]['rgb'])+old-84)
