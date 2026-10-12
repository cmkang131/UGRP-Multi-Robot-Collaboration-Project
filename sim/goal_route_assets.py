"""P1 visuals derived from the same registered map as ZoneScene physics.

Offline generation/validation only; no MuJoCo model, steps or renderer.
The existing tape_v1 layout, seed, scale, contrast and generator are unchanged.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from sim import wall_texture as tape
from sim.zone_arena import _geom
from sim.research_dispatch_arena import digest
from sim import goal_route_continuous as previous
from harness.active_camera import bind

OPTION='map_definition_v1'
ASSETS=Path(__file__).resolve().parents[1]/'experiments/2026-10-09-goal-route-preflight/assets'


def geometry(static):
    root=ET.Element('mujoco');world=ET.SubElement(root,'worldbody')
    for w in static['obstacles']:
        if w.get('kind')=='wall':
            _geom(world,w['id'],w['center_m'],w['half_extents_m'],w['height_m'],'.23 .28 .33 1')
    return tape.walls_from_xml(ET.tostring(root,encoding='unicode'))


def directory(static,root=ASSETS):return Path(root)/digest(geometry(static))


def generate(static,root=ASSETS):
    dest=directory(static,root)
    tape.generate_assets(geometry(static),dest)
    (dest/'source.json').write_text(json.dumps(dict(map_id=static['map_id'],map_sha256=digest(static),
        geometry_sha256=digest(geometry(static)),generator='sim.wall_texture.generate_assets',
        seed=tape.SEED,profile=tape.PROFILE_ID),indent=2)+'\n')
    return dest


def _layout_equal(actual,expected,numeric='off',path=()):
    """Only procedural patch vertices may differ by platform libm rounding.

    Geometry, PNG digests, lengths and all other metadata remain exact. This
    does not regenerate assets or change the XML used by physics/rendering.
    """
    if numeric not in ('off','libm_ulps_v1'):raise ValueError('UNKNOWN_ASSET_NUMERIC')
    if numeric=='off':return actual==expected
    if type(actual) is not type(expected):return False
    if isinstance(actual,dict):
        return actual.keys()==expected.keys() and all(_layout_equal(actual[k],expected[k],numeric,path+(k,)) for k in actual)
    if isinstance(actual,list):
        return len(actual)==len(expected) and all(_layout_equal(a,b,numeric,path+(i,)) for i,(a,b) in enumerate(zip(actual,expected)))
    vertex=(len(path)==7 and path[0]=='faces' and path[2]=='patches' and path[4]=='vertices_m')
    if vertex and isinstance(actual,float):
        return math.isfinite(actual) and math.isfinite(expected) and math.isclose(actual,expected,rel_tol=0.,abs_tol=4*max(math.ulp(actual),math.ulp(expected)))
    return actual==expected


def validate(static,assets,xml=None,*,asset_numeric='off'):
    assets=Path(assets);walls=geometry(static)
    source=json.loads((assets/'source.json').read_text());record=json.loads((assets/'layout.json').read_text())
    if source['map_sha256']!=digest(static) or source['geometry_sha256']!=digest(walls):raise ValueError('P1_ASSET_MAP_MISMATCH')
    expected=json.loads(json.dumps(tape.layout(walls)));actual=copy.deepcopy(record)
    for face in actual['faces']:face.pop('png_sha256')
    if not _layout_equal(actual,expected,asset_numeric):raise ValueError('P1_ASSET_LAYOUT_MISMATCH')
    if xml is not None and tape.walls_from_xml(xml)!=walls:raise ValueError('P1_XML_MAP_MISMATCH')
    for face in record['faces']:
        if tape.sha(assets/(face['id']+'.png'))!=face['png_sha256']:raise ValueError('P1_ASSET_PNG_MISMATCH')
    return dict(**source,walls=len(walls),faces=len(record['faces']),layout_sha256=tape.sha(assets/'layout.json'))


def decorate(xml,static,*,wall_assets='off',assets=None,asset_numeric='off'):
    if wall_assets=='off':return xml
    if wall_assets!=OPTION:raise ValueError('UNKNOWN_WALL_ASSETS')
    assets=directory(static) if assets is None else Path(assets)
    validate(static,assets,xml,asset_numeric=asset_numeric)
    return tape.transform_xml(xml,wall_texture='tape_v1',assets=assets)


def make_scene(bundle,seed):
    if bundle['options'].get('wall_assets','off')=='off':return previous.make_scene(bundle,seed)
    if bundle['options']['wall_assets']!=OPTION:raise ValueError('UNKNOWN_WALL_ASSETS')
    if bundle['options']['wall_texture']!='tape_v1':raise ValueError('P1_EXPECTS_TAPE_V1')
    untextured=copy.deepcopy(bundle);untextured['options']['wall_texture']='off'
    scene=previous.make_scene(untextured,seed);original=scene.transform
    static=scene.config['static_map']
    scene.transform=lambda xml:decorate(original(xml),static,wall_assets=OPTION,asset_numeric=bundle['options'].get('wall_asset_numeric','off'))
    return scene


def xml_preflight(bundle,seed):
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.masterpi_drive_friction_v7 import transform_xml,DriveParameters
    from sim.zone_cargo_contact import apply
    scene=make_scene(bundle,seed)
    xml=apply(scene.transform(build_multi_robot_xml()),'cargo_noslip_v1')
    xml=scene.robot_transform(xml)
    xml=transform_xml(xml,DriveParameters(),'mesh','off')
    receipt=validate(scene.config['static_map'],directory(scene.config['static_map']),xml,asset_numeric=bundle['options'].get('wall_asset_numeric','off'))
    root=ET.fromstring(xml)
    assert len(root.findall("worldbody/geom[@contype='0'][@conaffinity='0'][@mass='0']"))>=receipt['faces']
    receipt.update(seed=seed,xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),physics_steps=0,
                   validation='full offline XML transform; actual runtime transform rechecks same map/assets')
    return receipt,xml


class PhysicsBackend(previous.PhysicsBackend):
    _initialize=bind(previous.Base.__init__,make_scene=make_scene)
