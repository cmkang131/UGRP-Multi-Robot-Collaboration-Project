"""Pure XML/PNG regressions; never load MuJoCo, render or step physics."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import pytest

from sim import natural_scene_texture as texture, render_profile as rp
from scripts.generate_scene_textures import MAPS, texture as generate_texture

ROOT=Path(__file__).resolve().parents[1]


def scene_xml(map_path=MAPS[0]):
    """XML-only fixture from each actual map; all other domains have sentinels."""
    d=json.loads(map_path.read_text())
    root=ET.fromstring('<mujoco><option timestep=".00025"/><asset>'
        '<texture name="ground" type="2d" builtin="checker" width="256" height="256" rgb1=".2 .22 .24" rgb2=".27 .29 .31"/>'
        '<material name="groundmat" texture="ground" texrepeat="14 14" reflectance=".035"/>'
        '</asset><worldbody><light pos="0 0 2" diffuse="1 1 1"/>'
        '<geom name="floor" type="plane" size="8 8 .1" material="groundmat" friction="1 .1 .01"/>'
        '<geom name="zone_A" type="box" rgba=".9 .3 .1 1"/>'
        '<body name="robot"><camera name="own" fovy="60" pos=".1 0 .2"/>'
        '<geom name="arm" rgba=".95 .6 .03 1"/><geom name="box" rgba="0 1 1 1"/></body>'
        '</worldbody><actuator><motor name="drive" gear="3"/></actuator></mujoco>')
    for w in d['obstacles']:
        ET.SubElement(root.find('worldbody'),'geom',name='zone_'+w['id'],type='box',
            pos=' '.join(map(str,[*w['center_m'],w['height_m']/2])),
            size=' '.join(map(str,[*w['half_extents_m'],w['height_m']/2])),
            rgba='.23 .28 .33 1',contype='1',conaffinity='3',mass='0')
    return ET.tostring(root,encoding='unicode')


@pytest.mark.parametrize('map_path',MAPS,ids=lambda p:p.stem)
def test_material_only_change_for_every_supported_map(map_path):
    source=scene_xml(map_path)
    base=ET.fromstring(rp.apply_xml(source,'floor_light_v1'))
    out=ET.fromstring(rp.apply_xml(source,texture.PROFILE))
    for tag in ('option','actuator'):
        assert ET.tostring(base.find(tag))==ET.tostring(out.find(tag))
    assert len(list(base.iter('geom')))==len(list(out.iter('geom')))
    for a,b in zip(base.find('worldbody').iter(),out.find('worldbody').iter()):
        aa,bb=dict(a.attrib),dict(b.attrib)
        if a.get('name','').startswith('zone_wall_'):
            for k in ('rgba','material'): aa.pop(k,None);bb.pop(k,None)
            assert b.get('material').startswith('natural_v1_')
        assert (a.tag,aa)==(b.tag,bb)
    ground=out.find("asset/material[@name='groundmat']")
    assert ground.get('texrepeat')=='1 1' and ground.get('texuniform')=='false'
    assert out.find("asset/texture[@name='ground']").get('builtin') is None
    walls=out.findall("asset/texture[@type='cube']")
    assert len(walls)==len(json.loads(map_path.read_text())['obstacles'])
    files=[t.get(attr) for t in walls for attr,_,_ in texture.CUBE_FACES]
    assert len(files)==len(set(files))


def test_defaults_and_original_profile_hashes_stay_unchanged():
    source=scene_xml()
    assert rp.apply_xml(source,None) is source
    assert rp.apply_xml(source,'shadows_v1') is source
    assert rp.profile_sha256('floor_light_v1')=='e3ea8aebc473f99def92fa368f8aaa11e5872dc5b2a8ec8ba9a308641d2b6ec5'
    assert rp.profile_record(texture.PROFILE)['xml_ops'][-1]['manifest_sha256']==texture.MANIFEST_SHA256


def test_scene_record_binds_profile_and_both_xml_hashes():
    class Scene:
        def transform(self,xml): self.manifest={};return xml
    s=rp.install(Scene(),texture.PROFILE);out=s.transform(scene_xml())
    assert s.manifest['render_profile']['scene_xml_sha256_after_profile']==hashlib.sha256(out.encode()).hexdigest()
    assert s.manifest['render_profile']['name']==texture.PROFILE


def test_corrupt_assets_and_changed_geometry_fail_closed(tmp_path):
    (tmp_path/'manifest.json').write_bytes((texture.ASSETS/'manifest.json').read_bytes())
    (tmp_path/'floor.png').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='asset hash mismatch'):
        texture.apply(ET.fromstring(scene_xml()),assets=tmp_path)
    (tmp_path/'manifest.json').write_text('{}')
    with pytest.raises(ValueError,match='manifest hash mismatch'): texture.manifest(tmp_path)
    with pytest.raises(ValueError,match='16 x 16'):
        rp.apply_xml(scene_xml().replace('8 8 .1','3 3 .1'),texture.PROFILE)
    with pytest.raises(ValueError,match='another wall dressing'):
        rp.apply_xml(rp.apply_xml(scene_xml(),texture.PROFILE),texture.PROFILE)
    with pytest.raises(ValueError,match='no pinned'):
        rp.apply_xml(scene_xml().replace('zone_wall_north','zone_wall_unknown'),texture.PROFILE)


def test_pinned_pixels_remain_neutral_and_avoid_dark_white_gates():
    m=texture.manifest()
    hashes=[]
    for key,entry in m['images'].items():
        p=texture.checked_file(key,m,texture.ASSETS);hashes.append(entry['sha256'])
        rgb=np.asarray(Image.open(p).convert('RGB'))
        assert np.array_equal(rgb[:,:,0],rgb[:,:,1]) and np.array_equal(rgb[:,:,1],rgb[:,:,2])
        assert rgb.min()>60 and rgb.max()<225
    assert len(hashes)==len(set(hashes))


def test_generator_seed_is_stable_and_surface_specific():
    a=np.asarray(generate_texture('test',128,96))
    assert np.array_equal(a,np.asarray(generate_texture('test',128,96)))
    assert not np.array_equal(a,np.asarray(generate_texture('other',128,96)))


def test_repetition_measure_distinguishes_checker_and_blank():
    from scripts.audit_scene_textures import features
    y,x=np.indices((512,512));checker=np.where((x//32+y//32)%2,158,92).astype(np.uint8)
    c=features(checker);flat=features(np.full((512,512),146,np.uint8))
    assert c['highpass_ncc_lags_32_64_128_256_max']>.95
    assert c['duplicate_32px_patch_fraction']>.95
    assert flat['orb_count']==0


def test_measured_color_ranges_have_zero_overlap():
    d=json.loads((ROOT/'experiments/2026-10-15-scene-floor-texture/offline-audit.json').read_text())
    assert len(d['color_ranges'])>50
    assert all(r[k]['hits']==0 for r in d['color_ranges'] for k in ('floor','walls'))
    assert all(r['sha256']==texture.manifest()['images'][r['key']]['sha256'] for r in json.loads((ROOT/'experiments/2026-10-15-scene-floor-texture/image-metrics.json').read_text()))


def test_nearclip_accepts_textured_profile_and_records_actual_parent():
    from sim import final_pair_highpose_nearclip as near
    class Scene:
        def transform(self,xml): self.manifest={};return xml
    s=near.wrap(rp.install(Scene(),texture.PROFILE))
    root=ET.fromstring(s.transform(scene_xml()))
    assert root.find('visual/map').get('znear')==near.ZNEAR_REL
    r=s.manifest['render_nearclip']
    assert r['base_profile']==texture.PROFILE
    assert r['sha256']!=near.record()['sha256']


def test_queue_is_unapproved_not_ready_and_has_six_views_per_map():
    from scripts.make_scene_texture_plan import plan
    d=plan('a'*40)
    def check(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k.startswith('ready') or k in ('approved','execute','enabled'): assert v is False
                check(v)
        elif isinstance(value,list):
            for v in value:check(v)
    check(d)
    assert len(d['static_gate']['maps'])==4
    assert all(len(m['viewpoints'])==6 for m in d['static_gate']['maps'])
    assert d['static_gate']['total_frames']==48


def test_profile_path_is_simulator_free_in_fresh_process():
    import subprocess
    program = """
import importlib.abc, sys, runpy
class NoSimulator(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'mujoco':
            raise AssertionError('offline path imported MuJoCo')
sys.meta_path.insert(0, NoSimulator())
ns=runpy.run_path('tests/test_natural_scene_texture.py')
from sim.render_profile import apply_xml
apply_xml(ns['scene_xml'](), 'floor_light_textured_v1')
from scripts.make_scene_texture_plan import plan
plan('a'*40)
"""
    r=subprocess.run([sys.executable,'-c',program],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
