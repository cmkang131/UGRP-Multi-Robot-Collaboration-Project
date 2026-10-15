from types import SimpleNamespace
from harness.reloc11_timing import Timings


def test_wrapper_preserves_result_exception_and_can_be_restored():
    import pytest
    class Source:
        def step(self, value):
            if value < 0:
                raise ValueError('negative')
            return {'value': value}
    source = Source()
    original = source.step
    timing = Timings()
    restore = timing.wrap(source, 'step', 'pf')
    assert source.step(3) == {'value': 3}
    with pytest.raises(ValueError, match='negative'):
        source.step(-1)
    restore()
    assert source.step == original
    result = timing.snapshot(SimpleNamespace(registration=SimpleNamespace(pf=SimpleNamespace(n=2000))))
    assert result['calls'] == {'pf': 2}
    assert result['seconds']['pf'] >= 0 and result['pf_particles'] == 2000


def test_timing_bundle_is_default_off_and_does_not_change_control_options():
    from scripts.run_self_map_diagnostic import bundle
    old = bundle('a'*40, 93571, 90)
    assert old == bundle('a'*40,93571,90,reloc11_low_contrast_v1=False,reloc11_wall_field_v1=False)
    assert old == bundle('a'*40, 93571, 90, reloc11_timing_v1=False)
    timed = bundle('a'*40, 93571, 90, reloc11_timing_v1=True)
    assert timed['options'].pop('reloc11_timing_v1') is True
    assert timed == old


def test_half_rate_keeps_every_selected_frame_and_terminal_time(tmp_path):
    from scripts.run_self_map_diagnostic import bundle, acquire
    from test_self_map_executor import RecordingPlant, controller_factory
    old = bundle('a'*40, 93571, 1.)
    assert old == bundle('a'*40, 93571, 1., reloc11_half_rate_v1=False)
    b = bundle('a'*40, 93571, 1., reloc11_half_rate_v1=True)
    assert b['capture_s'] == .2 and b['recording']['own_rgb_hz'] == 5
    result = acquire(tmp_path/'5hz', b, RecordingPlant, controller_factory=controller_factory)
    assert result['status'] == 'RECORDED' and result['stop_reason'] == 'sim_time_cap'
    assert result['frames'] == result['input_audit']['own_rgb_frames'] == 6
    assert result['rgb_ledger_verified'] and RecordingPlant.instances[-1].now == 2.3
    assert result['invisible_measurements'] == result['held_world_reads'] == 0


def test_wall_field_uses_static_structure_without_color_weight_or_weaker_gate():
    import numpy as np
    from harness.selfmap4_geometry import static_input, StaticRegistration
    from harness.active_camera import SEARCH
    static,_ = static_input()
    a = StaticRegistration(static)
    b = StaticRegistration(static,reloc11_wall_field_v1=False)
    c = StaticRegistration(static,reloc11_wall_field_v1=True)
    assert a.pf.sensor_landmarks == b.pf.sensor_landmarks == 'floor_zones_doors_v1'
    assert c.pf.sensor_landmarks == 'off' and c.pf.n == 2000
    np.testing.assert_array_equal(a.pf.px,b.pf.px)
    np.testing.assert_array_equal(a.pf.px,c.pf.px)
    d = StaticRegistration(static,reloc11_wall_field_v1=True)
    packet=dict(t=0.,points=[[1,0],[1,.2]],delta=[0,0,0],servo=SEARCH)
    c.pf.step(**packet,features=[{'kind':'unused_color'}])
    d.pf.step(**packet,features=[])
    np.testing.assert_array_equal(c.pf.px,d.pf.px)
    np.testing.assert_array_equal(c.pf.logw,d.pf.logw)
    assert c.map_from_own is None and c.confirmations == []
    assert c.geometry_supported(dict(features=[]),[0,0,0])[0] is False


def test_low_contrast_extract_adds_corners_without_changing_match_gates(monkeypatch):
    import cv2
    import numpy as np
    from harness import e2e_rgb_vo as vo
    from harness.natural_floor_slam import extract, Options
    from harness.reloc11_features import extract as low
    image=np.full((480,640,3),120,np.uint8)
    for x in range(40,600,30):
        for y in range(40,440,30):
            cv2.rectangle(image,(x,y),(x+13,y+13),(135,135,135),-1)
    monkeypatch.setattr(vo,'image_mask',lambda *a:np.full((480,640),255,np.uint8))
    monkeypatch.setattr(vo,'ground',lambda servo,uv:(uv/1000.,np.ones(len(uv))))
    before=extract(image,{},frame_id=1,t=1.,sha256='a'*64)
    after=low(image,{},frame_id=1,t=1.,sha256='a'*64)
    assert len(after.points_body)>len(before.points_body)
    assert after.sha256==before.sha256 and after.descriptors.shape==(len(after.points_body),32)
    assert (Options().min_matches,Options().min_inliers,Options().global_min_inliers)==(8,6,12)


def test_carry_queue_cannot_inherit_smooth_success_or_enabled_flags():
    from scripts.prepare_reloc11_carry_queue import prepare
    q=prepare(dict(runs_enabled=True,operator_work_complete=True,tested_execution_source_sha='b'*40,
        coordinator_approval={},execution_stages=[],runs=[dict(name='solo-carry-x',command=['--plan','old.json'],
        operator_outcome='ROTATION_PASS',operator_retrieval_verified=True,approved=True)]),'a'*40)
    assert q['status']=='BLOCKED' and q['runs_enabled'] is False
    assert 'operator_work_complete' not in q and 'tested_execution_source_sha' not in q
    assert not any(k.startswith('operator') for k in q['runs'][0])
    assert q['runs'][0]['approved'] is False
