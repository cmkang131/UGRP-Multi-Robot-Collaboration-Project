"""Versioned, opt-in demo scenes. Existing scenes and hardware stay unchanged."""
import hashlib
import xml.etree.ElementTree as ET
from sim.zone_scenario_scene import ScenarioFinalV3Scene
from sim.render_profile import install
from sim.final_pair_highpose_nearclip import wrap
from sim import masterpi_camera_review_v3 as camera
from sim.s2_servo_stiffness import transform_xml as stiffness

COLORS={'teal':(.02,.95,.60,1.),'blue':(.02,.02,.95,1.)}
COLOR_PROFILE='grasp_act_teal_blue_v1'


def colors(xml,option):
    if option=='off':return xml
    if option!=COLOR_PROFILE:raise ValueError('unknown end appearance profile')
    tree=ET.fromstring(xml)
    for suffix,end in (('band_neg','teal'),('band_pos','blue')):
        found=tree.findall(f".//geom[@name='cargo_beam_1__{suffix}']")
        if len(found)!=1:raise ValueError('one original beam band required')
        found[0].set('rgba',' '.join(map(str,COLORS[end])))
    return ET.tostring(tree,encoding='unicode')


def make_scene(plan):
    scene=wrap(install(ScenarioFinalV3Scene.from_scenario(plan['scenario_id'],plan['seed'],
        cargo_scene_version=plan.get('cargo_scene_version','catalogue_v1')),'floor_light_v1'))
    scene.config['setup_only']['spawns']=plan['spawns']
    original=scene.robot_transform
    def transform(xml,**kwargs):
        before=camera.transform_xml(original(xml,**kwargs),profile_id=camera.PROFILE_ID)
        for rid in ('r1','r2','r3'):before=stiffness(before,servo_stiffness='real_v1',robot_id=rid)
        after=colors(before,plan['end_color_scene'])
        scene.manifest['grasp_act_scene']={'version':'grasp_act_scene_v1','colors':plan['end_color_scene'],
            'parent_xml_sha256':hashlib.sha256(before.encode()).hexdigest(),
            'scene_xml_sha256':hashlib.sha256(after.encode()).hexdigest(),
            'appearance_only':'existing beam bands RGBA; no geometry, mass, contact or camera changes'}
        return after
    scene.robot_transform=transform
    return scene
