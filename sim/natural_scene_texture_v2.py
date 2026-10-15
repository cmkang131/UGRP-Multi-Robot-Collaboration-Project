"""Pinned natural surface dressing; XML only, no simulator/controller imports.

Independent v2 assets; reuse admitted wall geometry, not tape marks. Each cube face has
its own SHA-seeded PNG. Existing wall geometry is retained (materials only).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from sim.wall_texture import walls_from_xml

PROFILE = 'walls_floor_textured_v2'
ASSETS = Path(__file__).resolve().parent / 'assets' / PROFILE
TEXTURE_DIR = Path('sim/assets') / PROFILE  # relative to the repository scene root
MANIFEST_SHA256 = 'ea58773c500dd9bc5dbf3ede4edf5419535c306d3f9c3c11de935a5089af9858'
FLOOR_SIZE = (8., 8., .1)


def wall_key(name, size):
    return name + '_' + '_'.join(str(round(float(v)*10000)) for v in size)


# MuJoCo cube faces: right/left X, up/down Y, front/back Z.
CUBE_FACES = (('fileright', 1, 2), ('fileleft', 1, 2), ('fileup', 0, 2),
              ('filedown', 0, 2), ('filefront', 0, 1), ('fileback', 0, 1))


def manifest(assets=ASSETS):
    path = Path(assets) / 'manifest.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError('natural texture manifest hash mismatch')
    return json.loads(raw)


def checked_file(key, record, assets):
    entry = record['images'][key]
    path = Path(assets) / entry['file']
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError(f'natural texture asset hash mismatch: {key}')
    return path.resolve()


def apply(root, *, assets=ASSETS):
    """Apply after floor_light_v1 lights; refuse unknown geometry or other dressing."""
    if any(g.get('name', '').startswith(('tape_v1_', 'natural_v1_', 'natural_v2_')) for g in root.iter()):
        raise ValueError('natural texture cannot be combined with another wall dressing')
    walls = walls_from_xml(ET.tostring(root, encoding='unicode'))
    floor = root.find("worldbody/geom[@name='floor']")
    if (floor is None or floor.get('type') != 'plane' or floor.get('material') != 'groundmat'
            or tuple(map(float, floor.get('size', '').split())) != FLOOR_SIZE):
        raise ValueError('natural texture requires the standard 16 x 16 m zone floor')
    asset = root.find('asset')
    if asset is None:
        raise ValueError('natural texture needs scene assets')
    ground = asset.find("texture[@name='ground']")
    material = asset.find("material[@name='groundmat']")
    if ground is None or material is None:
        raise ValueError('natural texture needs ground and groundmat')
    record = manifest(assets)
    checked_file('floor', record, assets)
    # from_xml_string resolves relative directories from the scene's cwd.
    # Keep the repository root as that base (also when exporting scene XML).
    compiler = root.find('compiler')
    if compiler is None:
        compiler = ET.Element('compiler')
        root.insert(0, compiler)
    if compiler.get('texturedir') or compiler.get('assetdir') or any(
            t.get(a) for t in asset.findall('texture') for a in ('file', *(f[0] for f in CUBE_FACES))):
        raise ValueError('natural texture requires an unambiguous repository scene asset root')
    compiler.set('texturedir', TEXTURE_DIR.as_posix())
    ground.attrib.clear()
    ground.attrib.update(name='ground', type='2d', file=record['images']['floor']['file'])
    # No repeat within the bounded scene. Preserve the collision floor itself.
    # Cube faces are authored for the unit box. MuJoCo classic render_gl3.c
    # multiplies TexGen by geom size when texuniform=true, switching faces on
    # thin boxes and stretching the texture radially; false keeps each face.
    # Reference: google-deepmind/mujoco tag 3.12.0, src/render/classic/render_gl3.c.
    material.attrib.update(texture='ground', texrepeat='1 1', texuniform='false',
                           rgba='1 1 1 1', specular='0', shininess='0', reflectance='0')
    for wall in walls:
        key = wall_key(wall['name'], wall['size'])
        if key not in record['walls']:
            raise ValueError(f'no pinned natural texture for wall: {key}')
        name = 'natural_v2_' + wall['name']
        faces = {}
        for attr, k in record['walls'][key].items():
            checked_file(k, record, assets)
            faces[attr] = record['images'][k]['file']
        ET.SubElement(asset, 'texture', name=name+'_tex', type='cube', **faces)
        ET.SubElement(asset, 'material', name=name+'_mat', texture=name+'_tex',
                      texuniform='false', rgba='1 1 1 1', emission='0',
                      specular='0', shininess='0', reflectance='0')
        geom = root.find(f"worldbody/geom[@name='{wall['name']}']")
        geom.set('material', name+'_mat')
        geom.set('rgba', '1 1 1 1')
    return root


def verify_model(model):
    """Compiled model binding checks for the future GCP gate; no renderer."""
    import mujoco
    import numpy as np
    record = manifest()
    checked = []
    for i in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or ''
        if name != 'floor' and not name.startswith('zone_wall_'):
            continue
        mid = int(model.geom_matid[i])
        expected = 'ground' if name == 'floor' else 'natural_v2_'+name+'_tex'
        if mid < 0:
            raise RuntimeError(f'natural surface lacks a material: {name}')
        tids = [int(t) for t in np.asarray(model.mat_texid[mid]).reshape(-1) if t >= 0]
        matches = [t for t in tids if mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_TEXTURE, t) == expected]
        if len(matches) != 1 or not np.array_equal(model.mat_texrepeat[mid], [1, 1]):
            raise RuntimeError(f'natural surface has wrong texture/repetition: {name}')
        if bool(model.mat_texuniform[mid]):
            raise RuntimeError(f'natural surface has wrong mapping: {name}')
        tid = matches[0]
        keys = ['floor'] if name == 'floor' else list(record['walls'][wall_key(name, model.geom_size[i])].values())
        from PIL import Image
        expected_pixels = np.concatenate([np.asarray(Image.open(checked_file(k, record, ASSETS)).convert('RGB')).reshape(-1, 3) for k in keys])
        start = int(model.tex_adr[tid]); count = int(model.tex_width[tid]*model.tex_height[tid]*model.tex_nchannel[tid])
        actual = np.asarray(model.tex_data[start:start+count]).reshape(-1, int(model.tex_nchannel[tid]))
        # Cube face order/PNG orientation vary; compare exact channel histograms.
        if actual.shape != expected_pixels.shape or any(not np.array_equal(np.bincount(actual[:,c], minlength=256),
                np.bincount(expected_pixels[:,c], minlength=256)) for c in range(3)):
            raise RuntimeError(f'natural surface pixels differ: {name}')
        checked.append(name)
    if 'floor' not in checked or len(checked) < 2:
        raise RuntimeError('compiled model lacks natural floor/walls')
    return {'manifest_sha256': MANIFEST_SHA256, 'checked_surfaces': checked,
            'pixel_check': 'exact channel histograms; face orientation requires GCP image review'}
