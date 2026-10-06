"""Export fixed robot-only geometry, stripping root world pose and all scene data."""
import itertools
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import numpy as np

from replay import ROOT, dump, sha
from harness.floor_goal_self_mask import rotation


def vector(node, key, default):
    return np.fromstring(node.get(key, default), sep=' ').tolist()


def box(low, high):
    return np.array(list(itertools.product(*zip(low, high))))


def mesh_vertices(node):
    if node.get('vertex'):
        points = np.fromstring(node.get('vertex'), sep=' ').reshape(-1, 3)
    else:
        data = Path(node.get('file')).read_bytes()
        count = struct.unpack_from('<I', data, 80)[0]
        if len(data) != 84+50*count:
            raise ValueError('EXPECTED_BINARY_STL')
        dtype = np.dtype([('normal', '<f4', (3,)), ('vertices', '<f4', (3, 3)), ('attribute', '<u2')])
        points = np.frombuffer(data, dtype, count=count, offset=84)['vertices'].reshape(-1, 3)
    return points*np.array(vector(node, 'scale', '1 1 1'))


def export(scene, robot):
    root = ET.parse(scene).getroot()
    if root.find('compiler').get('angle') != 'radian':
        raise ValueError('GEOMETRY_EXPECTS_RADIANS')
    meshes = {m.get('name'): mesh_vertices(m)
              for m in root.iter('mesh')}
    materials = {m.get('name'): vector(m, 'rgba', '1 1 1 1') for m in root.iter('material')}
    def visit(body, is_root=False):
        name = body.get('name').removeprefix(robot+'__')
        result = {'name': name, 'pos': [0., 0., .0325] if is_root else vector(body, 'pos', '0 0 0'),
                  'envelopes': [], 'children': []}
        if not is_root:
            for attr in ('quat', 'euler'):
                if body.get(attr):
                    result[attr] = vector(body, attr, '')
        joints = body.findall('joint')
        if joints and 'wheel' not in name and 'roller' not in name:
            j = joints[0]
            result['joint'] = {'name': j.get('name').removeprefix(robot+'__'), 'type': j.get('type', 'hinge'),
                               'axis': vector(j, 'axis', '0 0 1'), 'pos': vector(j, 'pos', '0 0 0'),
                               'range': vector(j, 'range', '-100 100')}
        for g in body.findall('geom'):
            rgba = vector(g, 'rgba', ' '.join(str(x) for x in materials.get(g.get('material'), [1, 1, 1, 1])))
            if int(g.get('group', '0')) >= 4 or rgba[3] == 0:
                continue
            kind = g.get('type', 'sphere')
            size = np.fromstring(g.get('size', ''), sep=' ')
            if 'fromto' in g.attrib:
                ends = np.array(vector(g, 'fromto', '')).reshape(2, 3)
                points = box(ends.min(axis=0)-size[0], ends.max(axis=0)+size[0])
            else:
                if kind == 'mesh':
                    mesh = meshes[g.get('mesh')]
                    points = box(mesh.min(axis=0), mesh.max(axis=0))
                else:
                    extent = size if kind == 'box' else ([size[0]]*3 if kind == 'sphere' else [size[0], size[0], size[1]+(size[0] if kind == 'capsule' else 0)])
                    points = box(-np.array(extent), np.array(extent))
                orient = {a: vector(g, a, '') for a in ('quat', 'euler') if a in g.attrib}
                if 'zaxis' in g.attrib:
                    raise ValueError('UNHANDLED_GEOMETRY_ZAXIS')
                points = points @ rotation(orient).T + vector(g, 'pos', '0 0 0')
            result['envelopes'].append({'name': g.get('name', 'unnamed').removeprefix(robot+'__'), 'vertices': points.tolist()})
        result['children'] = [visit(child) for child in body.findall('body')]
        if name.startswith('wheel_') and name.endswith('_body'):
            # Wheel/passive roller positions are unknown: contain their full rotation.
            def fixed_points(node, origin, axes):
                origin = origin+axes @ node['pos']
                axes = axes @ rotation(node)
                points = [np.array(g['vertices']) @ axes.T+origin for g in node['envelopes']]
                for child in node['children']:
                    points += fixed_points(child, origin, axes)
                return points
            points = np.concatenate(fixed_points({**result, 'pos': [0, 0, 0]}, np.zeros(3), np.eye(3)))
            radius = float(np.linalg.norm(points[:, [0, 2]], axis=1).max())
            result['envelopes'] = [{'name': name+'_rotation_envelope', 'vertices': box([-radius, points[:, 1].min(), -radius], [radius, points[:, 1].max(), radius]).tolist()}]
            result['children'] = []
        return result
    return visit(root.find(f'.//body[@name="{robot}__robot"]'), True)


if __name__ == '__main__':
    cases = json.loads((ROOT/'experiments/2026-10-07-mapfree-goal-floor/cases.json').read_text())
    selected = {profile: next(c for c in cases if c['camera_profile'] == profile and (profile != 'camera_v3' or c['id'] == 's1045'))
                for profile in ('legacy', 'camera_v3')}
    sources, profiles = {}, {}
    for profile, case in selected.items():
        path = str(case['episode'])+'/scene.xml'
        profiles[profile] = export(path, case['robot'])
        sources[profile] = {'path': path, 'sha256': sha(path), 'robot': case['robot']}
        sources[profile]['mesh_files'] = {m.get('file'): sha(m.get('file')) for m in ET.parse(path).getroot().iter('mesh') if m.get('file')}
    target = ROOT/'harness/data/floor_goal_self_geometry.json'
    target.parent.mkdir(exist_ok=True)
    dump(target, {'schema': 'robot-only-geometry-v1', 'sources': sources, 'profiles': profiles,
                 'scope': 'Fixed own geometry only. World root position and orientation removed; no B/peer/wall geometry.'})
    print(target, target.stat().st_size)
