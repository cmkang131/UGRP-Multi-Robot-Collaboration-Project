"""Stored-input contracts only. No MuJoCo backend, native window or renderer."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import self_map_integration as sm
from harness import self_map_executor as ex
from harness import selfmap4_geometry as g
from scripts import run_self_map_diagnostic as run
from test_self_map_integration import fixture_mapper, receive
from test_self_map_executor import Sweep, step


def test_profile_default_off_and_no_static_input_in_legacy():
    assert sm.Options().recovery_profile == 'off'
    with pytest.raises(ValueError, match='UNKNOWN_SELF_MAP_RECOVERY'):
        sm.Options(recovery_profile='on')
    with pytest.raises(ValueError, match='REQUIRES_SELFMAP4'):
        sm.make_mapper(robot_id='r1', options=sm.Options(self_map_integration=sm.OPTION), static_map={})
    b = run.bundle('a'*40, 93530, 30)
    assert not b['supplied_map_to_controller'] and 'recovery_profile' not in b['options']
    b = run.bundle('a'*40, 93530, 30, recovery_profile=g.PROFILE)
    assert b['supplied_map_to_controller'] and b['execution_bundle_id'] == g.PROFILE
    assert b['authored_static_map_sha256'] == hashlib.sha256(g.MAP_PATH.read_bytes()).hexdigest()


def test_static_input_excludes_camera_spawn_and_evaluator_fields(tmp_path):
    source = json.loads(g.MAP_PATH.read_text())
    source.update(spawn=[42, 99, 1], robot_pose=[9, 8, 7], evaluator={'success': True})
    p = tmp_path/'static.json'; p.write_text(json.dumps(source))
    mapped, _ = g.static_input(p)
    assert set(mapped) == {'map_id', 'version', 'frame', 'bounds_m', 'obstacles', 'regions', 'passages'}
    assert 'top_cameras' not in mapped
    from harness.self_map_input_audit import InputAudit
    audit = InputAudit('r3')
    audit.static_map(mapped, 'a'*64)
    assert audit.snapshot()['authored_static_map_inputs'] == 1
    with pytest.raises(ValueError, match='STATIC_GEOMETRY_ALLOWLIST'):
        audit.static_map(dict(mapped, robot_pose=[1,2,3]), 'a'*64)


def test_line_fit_removes_bad_end_columns_and_does_not_bridge_corner():
    points = np.c_[np.linspace(-.8, .8, 30), np.ones(30)]
    points[0, 1] = 1.3; points[-1, 1] = .6
    fitted = g.robust_segment(points)
    assert fitted is not None
    np.testing.assert_allclose(fitted[:, 1], 1., atol=1e-9)
    assert max(abs(fitted[:, 0])) < .8
    assert g.robust_segment(points[:5]) is None


def test_plane_flow_never_invents_motion_across_gap_pan_or_missing_texture(monkeypatch):
    from harness import e2e_rgb_vo
    flow = g.PlaneFlow(); rgb = np.zeros((480, 640, 3), np.uint8)
    monkeypatch.setattr(e2e_rgb_vo, 'ground_pair', lambda *a, **kw: pytest.fail('invalid pair tracked'))
    for t, servo in [(0., {6:1500}), (2., {6:1500}), (2.1, {6:1750})]:
        d, q, r = flow.step(rgb, servo, t, True, np.array([.1, 0, 0]), np.eye(3))
        assert r['status'] == 'unavailable_pair'
        np.testing.assert_array_equal(d, [.1, 0, 0])


def test_plane_flow_reuses_homography_and_existing_fusion(monkeypatch):
    from harness import e2e_rgb_vo
    calls = []
    def pair(*a, **kw):
        calls.append(kw)
        return dict(status='measured', delta=[.01, 0, 0], covariance=(np.eye(3)*1e-4).tolist())
    monkeypatch.setattr(e2e_rgb_vo, 'ground_pair', pair)
    flow = g.PlaneFlow(); rgb = np.zeros((480, 640, 3), np.uint8)
    flow.step(rgb, {6:1500}, 0., True, np.zeros(3), np.eye(3)*.01)
    d, _, r = flow.step(rgb, {6:1500}, .1, True, np.array([.1, 0, 0]), np.eye(3)*.01)
    assert calls == [dict(vo_floor_mask='homography_v1')]
    assert d[0] < .02 and r['status'] == 'measured'


def test_static_registration_parallel_lines_and_wrong_hue_cannot_certify_pose():
    from harness.own_map_amcl_vendor.landmarks import MapFeatures
    static, _ = g.static_input(); reg = object.__new__(g.StaticRegistration)
    reg.pf = SimpleNamespace(landmark_map=MapFeatures(static))
    edges = [e for e in reg.pf.landmark_map.edges if e['region'] == 'zone_A']
    def feature(e):
        return dict(kind='floor_line', hue=e['hue'], endpoints=[e['a'], e['b']], normal=e['normal'])
    assert not reg.geometry_supported(dict(features=[feature(edges[0])]*4), [0, 0, 0])[0]
    assert reg.geometry_supported(dict(features=[feature(e) for e in edges[:2]]), [0, 0, 0])[0]
    assert not reg.geometry_supported(dict(features=[feature(e) for e in edges[:2]]), [0, 2.5, 0])[0]


def test_bounds_require_rgb_registration_not_an_assumed_identity():
    reg = object.__new__(g.StaticRegistration)
    reg.static = {'bounds_m': [0, 2, 0, 2]}; reg.map_from_own = None
    assert reg.contains([[-20, -20]], .1).all()
    reg.map_from_own = np.zeros(3)
    assert reg.contains([[1, 1], [-1, 1], [20, 1]], .1).tolist() == [True, False, False]
    grid = sm.PoseGrid('r1', .1, reg)
    r = grid.insert(frame_id=1, pose=[0, 0, 0], camera=[.2, .2],
                    segments=[[[2.3, .5], [2.3, 1.5]]], floor_xy=[[.8, .8]])
    assert r['outside_cells_rejected'] > 0
    assert reg.contains(list(grid.navigation.odds), .1).all()
    assert not grid.navigation.wall_frames  # no artificial wall at the clipped boundary


def test_rebuild_budget_cooldown_keeps_confirmed_map_atomic(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    mapper.options = replace(mapper.options, pose_rebuild='refit_history_v1')
    receive(mapper, 1); receive(mapper, 2)
    before = copy.deepcopy(mapper.grid.navigation.odds)
    mapper.recovery = True
    monkeypatch.setattr(mapper.slam, '_fit', lambda *a: (None, [], {}))
    mapper.rebuild_required = True
    assert not mapper.rebuild(3)['committed']
    assert mapper.rebuild(4)['deferred']
    assert not mapper.rebuild(23)['committed']
    assert mapper.rebuild(100)['deferred']
    assert len(mapper.rebuilds) == 2 and mapper.rebuild_required
    assert mapper.grid.navigation.odds == before


def test_static_frame_correction_cannot_be_certified_by_old_orb_self_fit(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    mapper.options = replace(mapper.options, pose_rebuild='refit_history_v1')
    receive(mapper, 1)
    before = copy.deepcopy(mapper.grid.navigation.odds)
    mapper.recovery = True; mapper.rebuild_required = True
    mapper.rebuild_cause = 'static_frame_correction'
    r = mapper.rebuild(3)
    assert not r['committed'] and r['reason'] == 'static_history_not_independently_refitted'
    assert mapper.rebuild_required and mapper.grid.navigation.odds == before


def test_failed_rebuilds_do_not_restart_pan_and_full_sweep_is_reached(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    # Drive the real executor with fixed RGB-independent trace rows, as a liveness
    # counterexample. Do not mutate the mapper's observation implementation.
    mapper.options = replace(mapper.options, recovery_profile=g.PROFILE)
    def trace(**kw):
        t = kw['t']
        return dict(pose=[0,0,0], complete=False, stop_reason=None,
            completion_blockers=['pose_revision_requires_rebuild'], map_updated=False,
            insertion_blockers=['pose_uncertain', 'pose_revision_requires_rebuild'],
            rebuild_count=int(t/5.4), rebuild_commits=0)
    monkeypatch.setattr(mapper, 'receive', trace)
    c = ex.SelfMapExecutor('r1', mapper=mapper, sweep=Sweep(), cap_s=100)
    c.initial_sweep_complete = True
    pans = []
    for i in range(1, 12):
        command, _ = step(c, i, float(i))
        if command['kind'] == 'look': pans.append(command['pan_pulse'])
    assert pans == list(ex.PANS)
    assert c.stage == 'select'
    assert not any(e.get('cause') == 'pose_map_revision' for e in c.events)


def test_no_candidate_uses_bounded_relocalization_and_never_completes(monkeypatch):
    mapper, state = fixture_mapper(monkeypatch)
    mapper.options = replace(mapper.options, recovery_profile=g.PROFILE)
    c = ex.SelfMapExecutor('r1', mapper=mapper, sweep=Sweep(), cap_s=100)
    c.stage = 'select'; state['blank'] = True
    step(c, 1, 1.)
    assert c.recovery_started == 1. and c.recovery_attempts == 1
    assert c.events[-1]['reason'] == 'selfmap4_relocalization'
    c.look(6.4, 'pose_map_revision')
    assert c.recovery_started == 1.
    command, trace = step(c, 2, 21.)
    assert command['kind'] == 'hold' and c.done
    assert trace['executor_stop_reason'] == 'selfmap4_relocalization_exhausted'
    assert not trace['complete']


def test_runner_audits_static_input_and_classifies_exhaustion_as_host_error(tmp_path):
    from test_self_map_executor import RecordingPlant, controller_factory
    def exhausted(**kw):
        controller = controller_factory(**kw)
        controller.recovery_started = kw['start_time']-20.
        return controller
    b = run.bundle('a'*40, 93530, 1., recovery_profile=g.PROFILE)
    result = run.acquire(tmp_path/'exhausted', b, RecordingPlant, controller_factory=exhausted)
    assert result['status'] == 'HOST_ERROR' and not result['complete']
    assert result['stop_reason'] == 'selfmap4_relocalization_exhausted'
    assert result['input_audit']['authored_static_map_inputs'] == 1
    assert result['input_audit']['top_rgb_frames'] == 0
    assert RecordingPlant.instances[-1].closed


def test_pr507_global_localizer_source_is_pinned():
    p = Path(__file__).resolve().parents[1]/'harness/e2e_static_rgb_localizer.py'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == '3aaab50ec6f389ca7a17aa7c8f401157c141750aea2274a96e93685e2ca6351d'
