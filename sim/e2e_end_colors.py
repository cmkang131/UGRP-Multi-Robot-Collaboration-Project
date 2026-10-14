"""User-authorized appearance-only scene option; OFF is byte-identical."""
import hashlib
import xml.etree.ElementTree as ET
from harness.e2e_end_colors import PROFILE,COLORS,record


def transform_xml(xml,option='off'):
    if option=='off':return xml
    if option!=PROFILE:raise ValueError('UNKNOWN_END_COLOR_SCENE')
    root=ET.fromstring(xml)
    for suffix,color in [('band_neg','teal'),('band_pos','blue')]:
        geoms=root.findall(f".//geom[@name='cargo_beam_1__{suffix}']")
        if len(geoms)!=1:raise ValueError('EXACTLY_ONE_EXISTING_BEAM_BAND_REQUIRED:'+suffix)
        geoms[0].set('rgba',' '.join(map(str,COLORS[color]['rgba'])))
    return ET.tostring(root,encoding='unicode')


def install(scene,option='off'):
    if option=='off':return scene
    if option!=PROFILE:raise ValueError('UNKNOWN_END_COLOR_SCENE')
    original=scene.transform
    def transform(xml):
        before=original(xml);after=transform_xml(before,option)
        scene.manifest['end_colors']={**record(),
            'parent_scene_xml_sha256':hashlib.sha256(before.encode()).hexdigest(),
            'scene_xml_sha256':hashlib.sha256(after.encode()).hexdigest(),
            'parent_static_map_sha256':scene.config['setup_only']['scenario']['map_file_sha256']}
        parent=scene.manifest['end_colors']['parent_static_map_sha256']
        scene.manifest['end_colors']['map_sha256']=hashlib.sha256((parent+record()['sha256']).encode()).hexdigest()
        scene.manifest['scene_xml_sha256']=hashlib.sha256(after.encode()).hexdigest()
        return after
    scene.transform=transform
    return scene
