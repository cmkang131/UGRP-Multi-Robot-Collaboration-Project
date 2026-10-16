"""Nonphysical prior-window, immutable submap and unknown-global-frame contracts."""
import numpy as np
import pytest
from harness.selfmap_map_correction import SelfMapCorrection,OPTION
from harness.self_map_csm import CorrelativeMatcher,CSMOptions

STATIC=dict(bounds_m=[-2,2,-2,2],obstacles=[dict(id='wall_a',center_m=[0,2],half_extents_m=[2,.02])])
SCAN=dict(segments=[[[.2,1],[1.2,1]],[[1.2,1],[1.2,.3]]],camera=[0,0])


def test_prior_window_never_expands_to_an_unearned_global_anchor():
    m=CorrelativeMatcher();P=np.diag([.02**2,.03**2,.01**2]);points=np.array([[x,1] for x in np.linspace(.2,1.2,12)])
    r=m.match([0,0,0],P,points,[0,0],SCAN['segments'],np.zeros((3,3)),prior_window=np.sqrt(np.diag(P)))
    np.testing.assert_allclose(r['search_window'],[.02,.03,.01]);assert r['candidates']==27
    assert np.all(np.abs(r['delta'])<=np.sqrt(np.diag(P))+1e-10)
    with pytest.raises(ValueError):m.match([0,0,0],P,points,[0,0],SCAN['segments'],P,prior_window=[0,.1,.1])


def test_off_and_unregistered_global_are_explicit():
    m=SelfMapCorrection(STATIC)
    m.step(0,0,[0,0,0],np.zeros((3,3)),dict(status='bootstrap'),SCAN)
    assert m.frames==[] and m.static_from_own is None
    assert m.initialize_static()['static_from_own'] is None


def test_current_scan_is_absent_from_reference_and_rejection_does_not_poison_map(monkeypatch):
    m=SelfMapCorrection(STATIC,option=OPTION)
    _,first=m.step(0,0,[0,0,0],np.zeros((3,3)),dict(status='bootstrap'),SCAN)
    assert first['inserted'] and not first['accepted']
    old=np.asarray(m.frames[0]['world_segments']).copy()
    def reject(points,camera,reference,anchor):
        np.testing.assert_array_equal(reference,old)
        return dict(status='rejected',reason='ambiguous_modes',pose=m.pose.tolist(),candidates=27)
    monkeypatch.setattr(m,'_match',reject)
    _,event=m.step(1,1,[.1,0,0],np.diag([.01]*3),dict(status='unknown'),SCAN)
    assert not event['accepted'] and not event['inserted']
    np.testing.assert_array_equal(m.frames[0]['world_segments'],old)
    assert m.static_from_own is None and 'ambiguous_modes' in event['reason']


def test_prediction_covariance_rotates_once_and_never_reads_pose_labels():
    m=SelfMapCorrection(STATIC)
    m.pose=np.array([0,0,np.pi/2])
    p,e=m.step(0,0,[.1,0,0],np.diag([.04,.01,.09]),dict(status='unknown'),dict(segments=[],camera=[0,0]))
    np.testing.assert_allclose(p,[0,.1,np.pi/2],atol=1e-15)
    np.testing.assert_allclose(m.covariance,np.diag([.01,.04,.09]),atol=1e-15)


def test_observations_correct_an_injected_command_error_without_truth_input():
    m=SelfMapCorrection(STATIC,option=OPTION)
    m.step(0,0,[0,0,0],np.zeros((3,3)),dict(status='bootstrap'),SCAN)
    # Unmoved sensor still sees the SAME corner. A deliberately erroneous
    # .1m command prior must be corrected by its immutable past map alone.
    p,e=m.step(1,1,[.1,0,0],np.diag([.04,.04,.01]),dict(status='unknown'),SCAN)
    assert e['accepted'] and e['selected']=='self_submap'
    assert np.linalg.norm(p[:2])<.1 and m.static_from_own is None


def test_zero_command_noise_does_not_discard_observed_passive_motion():
    m=SelfMapCorrection(STATIC)
    p,e=m.step(0,0,[0,0,0],np.zeros((3,3)),dict(status='measured',delta=[.01,0,0],covariance=np.diag([.001]*3)),dict(segments=[],camera=[0,0]))
    np.testing.assert_allclose(p,[.01,0,0]);assert e['fusion']=='vo_replaced'
    np.testing.assert_allclose(m.covariance,np.diag([.001]*3))
