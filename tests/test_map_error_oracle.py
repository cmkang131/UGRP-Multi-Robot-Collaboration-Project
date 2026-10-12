"""Evaluation isolation, geometric visibility and attribution conservation."""
import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT/'experiments/2026-10-05-ego-wall-map-probe/code/map_error_oracle.py'
spec = importlib.util.spec_from_file_location('map_error_oracle', PATH)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def test_relative_gt_keeps_start_grid_anchor():
    origin = np.array([1., 2., math.pi/2])
    pose = np.array([2., 4., 1.])
    local = np.array([[.3, .8], [2., -1.]])
    np.testing.assert_allclose(e.transform(e.transform(local, e.relative_pose(pose, origin)), origin), e.transform(local, pose))
    np.testing.assert_allclose(e.relative_pose(origin, origin), [0., 0., 0.])


def test_attribution_order_and_mixed_band():
    np.testing.assert_equal(e.attribution(.12, .1, 1), [0, 0, 0, 1,0])
    np.testing.assert_equal(e.attribution(.4, .1, 0), [0, 1, 0, 0,0])
    np.testing.assert_equal(e.attribution(.4, .3, 1), [1, 0, 0, 0,0])
    np.testing.assert_equal(e.attribution(.4, .3, 0), [0, 0, 1, 0,0])
    np.testing.assert_allclose(e.attribution(.4, .3, 2/3), [2/3, 0, 1/3, 0,0])


def test_unavailable_band_is_unresolved_not_nonwall():
    np.testing.assert_equal(e.attribution(.4, .3, None), [0,0,0,0,1])


def test_logodds_attribution_survives_misses_and_saturation():
    v, mass = -2., np.zeros(5)
    for inc, label in [(1., [1,0,0,0,0]), (2., [0,1,0,0,0]), (1., [1,0,0,0,0]),
                       (-.5, None), (9., [0,0,1,0,0]), (-9., None), (4., [0,0,0,1,0])]:
        nxt = np.clip(v+inc, -2, 3.5)
        mass = e.update_support(v, nxt, mass, label)
        assert mass.sum() == pytest.approx(max(0, nxt))
        assert (mass >= 0).all()
        v = nxt
    np.testing.assert_allclose(mass, [0,0,0,2,0])


def test_sampling_audit_matches_original_with_weights():
    class Evidence:
        def fraction(self, frame, p):
            return .5
    rows = [{'frame_id': i, 't': float(i), 'pose': [i*.13, .07, i*.11], 'camera': [.16,0.],
             'segments': [[[2., -.8],[2., .8]], [[1.,1.],[2.,1.]]], 'insertion_weight': w}
            for i,w in enumerate([1., .3, .7, .2, 1.])]
    rects = np.array([[3.,0.,.1,2.]])
    truth = {r['t']: np.zeros(3) for r in rows}
    grid, breakdown, records = e.audited_grid('r1', rows, truth, np.zeros(3), rects, Evidence())
    original = e.OdomGrid('r1')
    hit, miss = original.hit, original.miss
    for r in rows:
        original.hit, original.miss = hit*r['insertion_weight'], miss*r['insertion_weight']
        original.insert(e.transform([r['camera']], r['pose'])[0], [e.transform(s, r['pose']) for s in r['segments']])
    assert grid.export()['cells'] == original.export()['cells']
    assert sum(breakdown['cell_equivalents'].values()) == pytest.approx(len(records))


def test_geometry_only_occlusion_backside_and_fov(tmp_path, monkeypatch):
    mj = pytest.importorskip('mujoco')
    def forbidden(*a, **kw):
        raise AssertionError('dynamics/rendering forbidden')
    for name in ('mj_step','mj_forward','mj_fwdPosition','Renderer'):
        monkeypatch.setattr(mj, name, forbidden)
    xml = tmp_path/'geometry.xml'
    xml.write_text('''<mujoco><worldbody>
      <geom name="zone_wall_test" type="box" pos="2 0 .2" size=".1 2 .2"/>
      <geom name="object" type="box" pos="1 0 .2" size=".1 .1 .2"/>
      <body pos="0 0 0"><freejoint/><geom size=".01" pos="0 0 -2"/></body>
    </worldbody></mujoco>''')
    geometry = e.SavedGeometry(xml)
    geometry.at(geometry.model.qpos0.copy())
    origin = np.array([0., 0., .2])
    rotation = np.array([[0,0,1],[-1,0,0],[0,-1,0]])
    targets = np.array([[1.9,0,.2], [1.9,.5,.2], [2.1,.5,.2], [1.9,1.9,.2]])
    np.testing.assert_equal(e.visible_targets(geometry, origin, rotation, targets), [False,True,False,False])
    directions = targets-origin
    ds, ids = geometry.rays(origin, directions)
    for i,d in enumerate(directions):
        gid = np.empty(1, np.int32)
        single = mj.mj_ray(geometry.model, geometry.data, origin, d/np.linalg.norm(d), geometry.mask, True, -1, gid)
        assert single == pytest.approx(ds[i])
        assert gid[0] == ids[i]
    assert geometry.data.time == 0.
    np.testing.assert_equal(geometry.data.qpos, geometry.model.qpos0)


def test_real_source_endpoint_projection_roundtrip():
    # Archived first admitted contact, independent of current recording access.
    import markerless_probe as mp
    import wall_probe as wp
    servo = {1:2000, 3:1072, 4:2400, 5:1482, 6:1500}
    cm = mp.column_model(servo, wp.detector_bias(servo, False, True), mp.column_positions(96,2))
    point = np.array([1.946934360270112, .7987464172875189, 0.])
    optical = (point-(cm.origin+[.0482,0,0]))@cm._rot
    uv = optical[:2]/optical[2]*[mp.FX,mp.FY]+[mp.CX,mp.CY]
    np.testing.assert_allclose(uv, [10,139], atol=.03)


def test_behind_camera_range_is_recorded_without_raycast():
    class Geometry:
        def at(self, qpos):
            pass
        def rays(self, *args):
            raise AssertionError('behind-camera point must not cast a forward ray')
    frames = {133: {'commanded_servo': {1:2000, 3:1072, 4:2400, 5:1482, 6:2300}}}
    evidence = e.Evidence(Geometry(), frames, {133: {'t': 0.}}, {0.: {'qpos': []}})
    value = evidence.fraction(133, np.array([-1.0433787162409256, -1.8397370861755797]))
    assert value == 1.
    assert evidence.records[0]['reason'] == 'behind_camera_projection'
    assert evidence.records[0]['optical_depth_m'] == pytest.approx(-2.08816532)


def test_visibility_keeps_front_face_when_bin_representative_is_back_face():
    rects = np.array([[0.,1.45,1.,.025]])
    representatives = e.base.wall_samples(rects)
    surfaces, groups = e.wall_surfaces(rects)
    front = np.isclose(surfaces[:,1], 1.425)
    visible = e.visible_groups(front, groups, len(representatives))
    # The historical denominator deduplicated both faces and kept the back.
    assert any(visible & np.isclose(representatives[:,1],1.475))
    assert len(set(groups)) == len(representatives)
    assert np.array_equal(np.floor(surfaces/.1).astype(int), np.floor(representatives[groups]/.1).astype(int))
