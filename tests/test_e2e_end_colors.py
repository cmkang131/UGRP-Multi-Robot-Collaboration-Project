import copy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import cv2
import numpy as np
import pytest
from harness import e2e_end_colors as c
from sim.e2e_end_colors import transform_xml


def test_scene_only_existing_band_rgba_changes_and_off_identical():
    from sim.zone_cargo import add_cargo_xml,instances
    xml='<mujoco><worldbody/></mujoco>'
    xml,_=add_cargo_xml(xml,instances([dict(item_id='beam_1',kind='long_beam',pose=[0,0,0])]),mirror_pairs=False)
    assert transform_xml(xml)==xml
    changed=transform_xml(xml,c.PROFILE)
    before,after=ET.fromstring(xml),ET.fromstring(changed)
    differences=[]
    for a,b in zip(before.iter(),after.iter()):
        assert a.tag==b.tag
        for key in set(a.attrib)|set(b.attrib):
            if a.get(key)!=b.get(key):differences.append((a.get('name'),key))
    assert differences==[('cargo_beam_1__band_neg','rgba'),('cargo_beam_1__band_pos','rgba')]
    assert hashlib.sha256(changed.encode()).digest()!=hashlib.sha256(xml.encode()).digest()


def test_palette_excludes_all_existing_cargo_and_floor_colors():
    from sim.zone_cargo import CATALOGUE
    from sim.zone_arena import COLORS
    palette=list(COLORS.values())+[x.rgba for x in CATALOGUE.values()]
    palette += ['.95 .45 .10 .30','.20 .40 .95 .30','.70 .20 .85 .30','.54 .56 .58 1']
    image=np.array([[list(reversed([round(float(v)*255) for v in row.split()[:3]])) for row in palette]],np.uint8)
    for color in c.COLORS:assert not c.mask(image,color).any()
    for color,spec in c.COLORS.items():
        pixel=np.array([[list(reversed([round(x*255) for x in spec['rgba'][:3]]))]],np.uint8)
        assert c.mask(pixel,color).all()
        assert not c.mask(pixel, next(x for x in c.COLORS if x!=color)).any()


def test_saved_black_band_is_not_assigned_color():
    from harness.owncam_view import base_rays
    root=Path('tests/fixtures/owncam_pair_v2');records=json.loads((root/'frames.json').read_text())
    for name,row in records.items():
        raw=(root/name).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row['sha256']
        for color in c.COLORS:
            assert not c.observe(raw,row['own_pose_commands'],color,base_rays).get('end_visible')


@pytest.mark.parametrize('color',c.COLORS)
def test_synthetic_color_mutation_of_saved_band(color):
    # Synthetic positive unit fixture, NOT physical or changed-scene evidence.
    from harness.owncam_view import base_rays
    from harness import owncam_pair_beam_v2 as v2
    root=Path('tests/fixtures/owncam_pair_v2');name='p45_611_r1_00073.jpg'
    servo=json.loads((root/'frames.json').read_text())[name]['own_pose_commands']
    frame=cv2.imread(str(root/name));b=v2.observe_beam(frame,servo)
    assert b['end_visible']
    origin,rays,x,y,valid=base_rays(servo,1)
    down=rays[:,2]<-1e-6
    scales=np.where(down,(.032-origin[2])/np.where(down,rays[:,2],-1),np.nan)
    points=origin[:2]+scales[:,None]*rays[:,:2]
    hue=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    dark=(hue[...,2]<70)&(hue[...,1]<80)
    band=valid&down&(np.linalg.norm(points-np.array(b['grip_base_m']),axis=1)<.026)
    band=band.reshape(480,640)&dark
    assert band.sum()>50
    frame[band]=[round(v*255) for v in c.COLORS[color]['rgba'][:3]][::-1]
    found=c.observe(frame,servo,color,base_rays)
    assert found['end_visible'],found
    assert np.linalg.norm(np.array(found['grip_base_m'])-b['grip_base_m'])<.012
    assert not c.observe(frame,servo,next(x for x in c.COLORS if x!=color),base_rays)['end_visible']


def test_off_no_mutation_and_install_discards_black_history():
    t=SimpleNamespace();c.install(t);assert vars(t)=={}
    t=SimpleNamespace(robots={r:SimpleNamespace(beam={'old':1},last_beam={},grasp_track={}) for r in c.ORDER},approach={'r1':{},'r2':{}},event=lambda *a,**k:None)
    c.install(t,'remember_v1')
    assert t.approach=={}
    assert all(r.beam is None and r.grasp_track is None for r in t.robots.values())


def test_station_uses_color_observation_not_robot_id_or_B():
    def robot():return SimpleNamespace(beam=dict(rgb={'t_sim':5.},grip_base_m=[.4,0],axis_heading_rad=0,pose_own_m=[.67,0,0]),goal=SimpleNamespace(explorer=SimpleNamespace(local_pose=[0,0,0])))
    t=SimpleNamespace(end_colors='remember_v1',robots={r:robot() for r in c.ORDER})
    states=[]
    for rid in c.ORDER:
        s={};active,action=c.step(t,rid,5.,s);assert active and action is None;states.append(s)
    assert np.array_equal(states[0]['station'],states[1]['station'])
    assert states[0]['basis']['rule']!=states[1]['basis']['rule']


def test_anchor_preserves_only_center_for_search_never_restored_end(monkeypatch):
    old=dict(pose_own_m=[1,2,2.4],grip_base_m=[.2,0],rgb=dict(t_sim=4,frame_id=1))
    robots={rid:SimpleNamespace(beam=copy.deepcopy(old),last_beam=None,grasp_track=None) for rid in c.ORDER}
    tr=SimpleNamespace(robots=robots,approach={},event=lambda *a,**k:None)
    c.install(tr,'anchor_v2')
    for r in robots.values():
        assert r.beam is None and r.last_beam is None
        assert set(r.color_search_anchor)=={'pose_own_m','rgb'}
        assert r.color_search_anchor['pose_own_m']==[1,2,0.]
    def acquire(t,rid,now,state,target):
        assert target is None
        assert 'grip_base_m' not in t.robots[rid].last_beam
        return False,[dict(kind='hold')]
    monkeypatch.setattr('harness.e2e_pregrasp_acquire.acquire',acquire)
    assert c.step(tr,'r1',5.,{})==(True,(False,[dict(kind='hold')]))
    assert robots['r1'].last_beam is None
