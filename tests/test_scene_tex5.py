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
