"""RGB/AST-only tests, no simulation, rendering, credentials or model calls."""
import hashlib,json
import numpy as np
import pytest
from harness import warp7_perception as p


def test_disabled_is_default_and_bad_profile_is_rejected(monkeypatch):
    monkeypatch.delenv(p.ENV,raising=False)
    assert not p.enabled()
    monkeypatch.setenv(p.ENV,'unknown')
    with pytest.raises(ValueError,match='UNKNOWN'):p.enabled()


def test_paint_mask_requires_exact_calibration_hash_and_rgb_only(tmp_path,monkeypatch):
    path=tmp_path/'cal.json'
    path.write_text(json.dumps(dict(profile='warp7_rendered_hsv_v1',paint={'B':dict(low=[110,119,153],high=[113,140,175])})))
    monkeypatch.setenv(p.ENV,'rendered_hsv_v1');monkeypatch.setenv('UGRP_WARP7_CALIBRATION',str(path))
    monkeypatch.setenv('UGRP_WARP7_CALIBRATION_SHA256','wrong')
    with pytest.raises(ValueError,match='HASH'):p.paint_mask(np.zeros((1,1,3),np.uint8),'B')
    monkeypatch.setenv('UGRP_WARP7_CALIBRATION_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    import cv2
    hsv=np.array([[[112,129,166],[0,0,0],[108,71,159],[0,0,0],[103,48,37],[0,0,0],[133,83,110]]],np.uint8)
    assert p.paint_mask(cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR),'B').tolist()==[[True,False,False,False,False,False,False]]


def test_install_keeps_default_function_and_floor_geometry(monkeypatch):
    from harness import floor_goal
    from sim import destination_visual_acquire as d,solo_carry_to_zone as c
    a,b,f=floor_goal.detect_floor,d.floor_patch,c.CarryToZone.place_visible
    memory=floor_goal.FloorGoalMemory.detector
    monkeypatch.setenv(p.ENV,'off');p.install()
    assert floor_goal.detect_floor is a and d.floor_patch is b
    monkeypatch.setenv(p.ENV,'rendered_hsv_v1')
    try:
        p.install()
        assert floor_goal.detect_floor._warp7_original is a
        assert 'floor_intersections' in floor_goal.detect_floor.__code__.co_names
        assert 'floor_connection' in str(floor_goal.detect_floor.__code__.co_consts)
        assert 'SLOT_MAX_RANGE_M' in d.floor_patch.__code__.co_names
        assert c.CarryToZone.place_visible._warp7_original is f
    finally:
        floor_goal.detect_floor=a;floor_goal.FloorGoalMemory.detector=staticmethod(memory)
        d.floor_patch=b;c.CarryToZone.place_visible=f
