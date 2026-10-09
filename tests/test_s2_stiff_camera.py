import copy
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from harness import s2_stiff_camera_calibration as m
from harness.zone_final_pair_camera import floor_camera
from test_s2_extrinsic_calibration import samples
from test_solo_cyan_v106 import static, cal, FakePose, FakeVision


def test_surveyed_targets_recover_ground_normal_and_height_without_robot_pose():
    rows, origin, axes = samples()
    fitted = m.fit(rows)
    np.testing.assert_allclose(fitted['ground_normal_optical'], axes[2], atol=1e-8)
    assert fitted['height_m'] == pytest.approx(origin[2], abs=1e-8)
    old, _ = m.target.fit(rows)
    # Runtime horizontal position and yaw stay fixed, independent of target XY.
    old['origin_m'][0] += .15
    updated = floor_camera(m.corrected_record(old, fitted))
    np.testing.assert_allclose(updated['rotation'], axes, atol=1e-8)
    np.testing.assert_allclose(updated['origin_m'], origin+[.15,0,0], atol=1e-8)
    for row in rows:
        row['object_points_floor_m'] = (np.asarray(row['object_points_floor_m'])+[8,-4,0]).tolist()
    moved = m.fit(rows)
    np.testing.assert_allclose(moved['ground_normal_optical'], fitted['ground_normal_optical'], atol=1e-8)
    assert moved['height_m'] == pytest.approx(fitted['height_m'], abs=1e-8)


def test_coverage_and_incomplete_or_wrong_plant_refused():
    from scripts.capture_s2_stiff_camera import poses
    keys = {m.target.key(p) for p in poses()}
    assert len(keys) == 22
    assert {m.target.key(p) for _, p in m.target.poses()} <= keys
    marker = object()
    assert m.apply(marker, {}, camera_pitch='off') is marker
    with pytest.raises(ValueError, match='explicit real_v1'):
        m.apply(marker, {}, camera_pitch=m.OPTION)
    with pytest.raises(ValueError, match='complete RGB'):
        m.apply(marker, {}, camera_pitch=m.OPTION, servo_stiffness='real_v1')
    # Exact read-only vendor copy from PR405, no simulator import required.
    p = Path('sim/s2_servo_stiffness.py')
    expected = Path('experiments/2026-10-06-s2-realism/stiff-camera-criteria.json')
    assert hashlib.sha256(p.read_bytes()).hexdigest() == json.loads(expected.read_text())['stiffness_source_sha256']


def test_default_off_preserves_controller_commands_and_record_bytes(static, cal):
    from harness.zone_solo_cyan_augmented_start import Runtime as Previous
    Wrapped = m.runtime_class(Previous)
    rs = [cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),
              vision_factory=FakeVision, **kw) for cls,kw in
          [(Previous,{}),(Wrapped,{}),(Wrapped,dict(camera_pitch='off'))]]
    try:
        for r in rs: r.initial_commands(0.,{'r3':{1:2000,3:740,4:2320,5:1320,6:1500}})
        for t in (1.,1.05,1.65):
            commands = [r.step(t) for r in rs]
            assert len({json.dumps(x).encode() for x in commands}) == 1
            for r, issued in zip(rs,commands):
                for rid, cmd in issued: r.on_command(rid,t,cmd)
        assert len({json.dumps(r.record()).encode() for r in rs}) == 1
    finally:
        for r in rs: r.close()
