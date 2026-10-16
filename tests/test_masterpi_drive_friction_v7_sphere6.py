import copy
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import numpy as np
import pytest

mujoco = pytest.importorskip('mujoco')
from sim import masterpi_drive_friction_v7 as v7
from sim.masterpi_drive_friction_v6 import transform_xml as v6_xml
from sim.masterpi_drive_friction_v2 import ASSETS as FUJI_ASSETS
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.masterpi_robot_models import v3_robot_xml_transform

SCALE = .065/.205


@pytest.fixture(scope='module')
def base_xml():
    return v3_robot_xml_transform({})(build_multi_robot_xml({}))


def test_default_is_mesh_and_byte_identical_to_previous_v7(base_xml):
    p = v7.DriveParameters()
    default = v7.transform_xml(base_xml, p)
    assert default == v7.transform_xml(base_xml, p, 'mesh')
    expected = ET.fromstring(v6_xml(base_xml, p))
    expected.find("custom/text[@name='drive_profile']").set('data', v7.PROFILE)
    assert default == ET.tostring(expected, encoding='unicode')
    assert 'roller_collision' not in default
    assert v7.option_record('mesh') == {}


def test_unknown_roller_collision_is_rejected(base_xml):
    with pytest.raises(ValueError):
        v7.transform_xml(base_xml, v7.DriveParameters(), 'sphere12')


def test_sphere6_layout_is_tiago_values_scaled_65_over_205():
    layout = v7.sphere6_layout()
    tiago = [(-.02, .01185), (-.012, .0126), (-.005, .0129), (.005, .0129), (.012, .0126), (.02, .01185)]
    assert len(layout) == 6
    for (x, r), (tx, tr) in zip(layout, tiago):
        assert x == pytest.approx(tx*SCALE) and r == pytest.approx(tr*SCALE)
    # symmetric about the roller centre, all inside the 56 mm * scale FUJI barrel length
    assert [x for x, _ in layout] == pytest.approx([-x for x, _ in layout[::-1]])
    assert max(abs(x)+r for x, r in layout) < .03*SCALE*1.2


def test_sphere_radii_follow_fuji_barrel_profile():
    """Each sphere radius equals the FUJI STL radial extent at its centre (confirms metres and axis)."""
    raw = (FUJI_ASSETS/'fuji_roller.stl').read_bytes()
    n = struct.unpack('<I', raw[80:84])[0]
    tri = np.frombuffer(raw[84:84+50*n], dtype=np.dtype([('n', '<3f4'), ('v', '<9f4'), ('a', '<u2')]))
    vertex = tri['v'].reshape(-1, 3).astype(float)
    radial = np.hypot(vertex[:, 1], vertex[:, 2])
    stations = np.unique(np.round(vertex[:, 0], 6))
    envelope = np.array([radial[np.abs(vertex[:, 0]-s) < 1e-6].max() for s in stations])
    for x, r in v7.sphere6_layout():
        assert r/SCALE == pytest.approx(np.interp(x/SCALE, stations, envelope), rel=.03)


def test_sphere6_xml_replaces_only_the_roller_collider(base_xml):
    p = v7.DriveParameters()
    mesh_xml = v7.transform_xml(base_xml, p)
    sphere_xml = v7.transform_xml(base_xml, p, 'sphere6_v1')
    mesh, sphere = ET.fromstring(mesh_xml), ET.fromstring(sphere_xml)
    mesh_geoms = [g for g in mesh.iter('geom') if g.get('type') == 'mesh' and g.get('mesh') == 'fuji_roller_v2']
    assert mesh_geoms and len(mesh_geoms) % 36 == 0
    assert not [g for g in sphere.iter('geom') if g.get('mesh') == 'fuji_roller_v2']
    assert sphere.find("asset/mesh[@name='fuji_roller_v2']") is None
    assert sphere.find("custom/text[@name='roller_collision']").get('data') == 'sphere6_v1'
    spheres = [g for g in sphere.iter('geom') if '_roller_' in g.get('name', '') and g.get('type') == 'sphere']
    assert len(spheres) == 6*len(mesh_geoms)
    sample = next(g for g in spheres if g.get('name').endswith('_contact_s2'))
    reference = next(g for g in mesh_geoms if g.get('name') == sample.get('name')[:-3])
    for key in ('contype', 'conaffinity', 'condim', 'priority', 'friction', 'group', 'mass', 'rgba'):
        assert sample.get(key) == reference.get(key)
    assert reference.get('contype') == '2' and reference.get('conaffinity') == '1'
    x, r = v7.sphere6_layout()[2]
    assert np.fromstring(sample.get('pos'), sep=' ') == pytest.approx([x, 0, 0])
    assert float(sample.get('size')) == pytest.approx(r)
    # same bodies, hinges, excludes and actuators
    for tag in ('body', 'joint', 'exclude', 'motor', 'velocity', 'position'):
        assert len(list(mesh.iter(tag))) == len(list(sphere.iter(tag)))


def test_sphere6_model_keeps_dynamics_and_drops_contact_cost(base_xml):
    p = v7.DriveParameters()
    a = mujoco.MjModel.from_xml_string(v7.transform_xml(base_xml, p))
    b = mujoco.MjModel.from_xml_string(v7.transform_xml(base_xml, p, 'sphere6_v1'))
    for attr in ('nbody', 'njnt', 'nv', 'nu', 'neq'):
        assert getattr(a, attr) == getattr(b, attr)
    assert b.nmesh == a.nmesh-1  # only the FUJI roller mesh asset is dropped
    assert a.body_mass.sum() == pytest.approx(b.body_mass.sum())
    np.testing.assert_allclose(a.body_inertia, b.body_inertia)
    np.testing.assert_allclose(a.dof_damping, b.dof_damping)
    roller = int((a.geom_dataid == mujoco.mj_name2id(a, mujoco.mjtObj.mjOBJ_MESH, 'fuji_roller_v2')).sum())
    assert roller and b.ngeom == a.ngeom+5*roller
    assert int((b.geom_type == mujoco.mjtGeom.mjGEOM_MESH).sum()) == int((a.geom_type == mujoco.mjtGeom.mjGEOM_MESH).sum())-roller


def test_option_record_names_sources_and_unconfirmed():
    record = v7.option_record('sphere6_v1')
    assert record['roller_collision'] == 'sphere6_v1'
    assert record['roller_collision_source']['commit'] == '812ef55cdca2502dec6044ecddb08991ff41982d'
    assert 'arXiv:2510.10273' in record['roller_collision_paper']
    assert record['roller_collision_unconfirmed']
    unsigned = {k: v for k, v in record.items() if k != 'roller_collision_sha256'}
    import hashlib
    assert record['roller_collision_sha256'] == hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest()


def test_default_drive_record_is_unchanged_by_the_option_code():
    p = v7.DriveParameters()
    assert p.record() == v7.DriveParameters().record()
    assert 'roller_collision' not in p.record()


def test_new_workflow_is_registered_and_plans_without_running():
    from sim.workflow_manager import plan
    root = Path(__file__).resolve().parents[1]
    q = plan(root, 'masterpi-v7-roller-approx-probe', ['--expected-source-sha', '0'*40, '--phase', 'profile'])
    assert '--phase' in q['command'] and not q['execution_started']
