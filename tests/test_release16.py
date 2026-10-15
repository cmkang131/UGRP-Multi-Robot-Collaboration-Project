"""Perception and clock-only integration. No simulator or renderer is created."""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from harness.vision_loc_protocol import load_vis3
from sim import release14, release15, release16 as new
from scripts import run_grasp_act_release as runner
from tests.test_grasp_act_release_run import fake_backend
from tests.test_release_regrasp import stripe, teachers


def split_beam():
    im = stripe(288)
    im[180:300,208:368] = [153,242,5]
    return im


def test_band_split_is_one_object_with_one_mask_and_line():
    im = split_beam()
    assert release15.line_features(im,'teal')['reason']=='shaft_ambiguous'
    f = new.line_features(im,'teal')
    assert f['valid'] and f['line'] is not None and f['fov_safe']
    assert abs(f['slope_error'])<1e-5
    mask,_=new.object_mask(im,'teal')
    assert f['mask_sha256']==hashlib.sha256(mask.tobytes()).hexdigest()
    assert f['pixels']==mask.sum()
    assert release15.line_features(im,'teal')['reason']=='shaft_ambiguous'  # legacy untouched


def test_collinear_components_merge_but_parallel_objects_do_not():
    im = stripe(288)
    im[200:260] = 60
    f = new.line_features(im,'teal')
    assert f['valid'] and f['merged_components']==1 and f['line'] is not None
    im = np.full((480,640,3),60,np.uint8)
    im[90:380,100:180]=[5,220,150];im[90:380,430:510]=[5,220,150]
    f = new.line_features(im,'teal')
    assert not f['valid'] and f['reason']=='beam_ambiguous' and not f['points']


def test_small_jpeg_seam_and_distant_collinear_object():
    im=split_beam();im[179:181]=60
    f=new.line_features(im,'teal')
    assert f['valid'] and f['line'] is not None
    im=stripe(288);im[170:310]=60
    f=new.line_features(im,'teal')
    assert not f['valid'] and f['reason']=='beam_ambiguous'


def test_ransac_does_not_turn_large_non_line_into_valid_direction():
    rows=np.array([(y,288.+.05*y+(70 if 170<y<270 else 0),80) for y in range(96,384,4)])
    assert new.fit_rows(rows) is None
    rows=np.array([(y,288.+.05*y+(30 if y in (180,220) else 0),80) for y in range(96,384,4)])
    fit=new.fit_rows(rows)
    assert fit is not None and fit['slope']==pytest.approx(.05)
    assert fit==new.fit_rows(rows)


def test_blank_and_partner_band_never_supply_a_line():
    im=np.full((480,640,3),60,np.uint8)
    im[96:384,210:365]=[242,5,5]
    assert not new.line_features(im,'teal')['valid']
    assert not new.line_features(None,'teal')['valid']
    assert not new.line_features(im.astype(float),'teal')['valid']


def test_saved_failures_native_jpeg_regression():
    root=Path(__file__).parent/'fixtures/release16'
    records=json.loads((root/'manifest.json').read_text())
    for record in records:
        path=root/record['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
        im=load_vis3()[0].mp.undistort(cv2.imread(str(path)))
        old=release15.line_features(im,record['end']);f=new.line_features(im,record['end'])
        assert old['reason']==record['old_reason']
        assert f['valid']==record['new_valid']
        if record['new_valid']:
            assert f['line'] is not None
            step=new.line_step(f,__import__('sim.lookaround_localization',fromlist=['Camera']).Camera(),
                {int(k):v for k,v in record['pwm'].items()},clearance=lambda *a:True)
            assert step['kind']==record['new_branch']
        else:
            assert not f['points'] and f['line'] is None


def test_timeout_and_motion_policy_are_release15_exact():
    assert new.LineAlign.tick is release15.LineAlign.tick
    assert new.line_step is release15.line_step
    assert new.map_motion_clear is release15.map_motion_clear
    ts=teachers();a=new.LineAlign(ts['r1'],0.,camera=None,undistort=lambda f:f,
        wheel_command=lambda *a:None,clearance=lambda *a:True)
    def schedule(rid,seq,now):
        for _,pwm in seq:ts[rid].pwm.update(pwm)
    assert a.tick(0.,lambda *a:None,schedule)=='pending'
    assert a.tick(2.6,lambda *a:None,schedule)=='pending'
    assert a.tick(3.4,lambda *a:None,schedule)=='pending'
    assert a.tick(3.6,lambda *a:None,schedule)=='failed'
    assert a.failure=='release16_shaft_unobserved_1s'


@pytest.mark.parametrize('option,value', [('own_pose_source','truth'),('held_object','visible_v0'),('pose_anchor','legacy_truth_v0')])
def test_truth_options_rejected_before_backend(tmp_path,monkeypatch,option,value):
    plan=json.loads((runner.ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/release15-diagnostic-plan.json').read_text())
    options={**plan['execution_profile'],'release_profile':new.PROFILE,option:value}
    with pytest.raises(ValueError,match='unsafe configuration'):
        runner.run(plan['episodes'][0],tmp_path/'out',**options)
    assert not (tmp_path/'out').exists()


def test_training_still_rejected():
    with pytest.raises(ValueError,match='training RGB unavailable'):
        new.validate(new.PROFILE,True,new.SAFE,{'end_color_scene':'grasp_act_teal_blue_v1'})


def test_real_runner_uses_new_pixels_then_lift_ack(tmp_path,fake_backend,monkeypatch):
    from tests import test_release15 as old_test
    # Same actual scheduler/map/pixel lift regression, newly selected profile.
    monkeypatch.setattr(old_test,'new',new)
    old_test.test_runner_real_map_near_wall_and_actual_pixel_barrier(tmp_path,fake_backend,monkeypatch)


def test_detached_blue_zone_and_end_face_use_object_visibility_not_false_axis():
    root=Path(__file__).parent/'fixtures/release16'
    for rec in json.loads((root/'extra-manifest.json').read_text()):
        path=root/rec['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==rec['sha256']
        im=cv2.imread(str(path))
        if im.shape[:2]==(240,320):im=cv2.resize(im,(640,480),interpolation=cv2.INTER_LINEAR)
        f=new.line_features(load_vis3()[0].mp.undistort(im),rec['end'])
        assert f['valid'] and f['reason']==rec['expected_reason'] and f['points']
        assert f['line'] is None
        if rec['end']=='blue':assert f['detached_band_components']>0
