"""Saved-image and synthetic regressions only; no MuJoCo, PF rollout or model."""
import copy
import hashlib
import inspect
import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from harness import opencv_wall_observation as ow
from harness import vision_loc_protocol as vp
from harness import zone_pair_highpose_opencv_exact as exact
from harness.vision_loc_client import FrameRejected, WorkerFailure
from scripts.diagnose_owncam_robot_mask import FIXTURE, evaluate, obs_bytes


def synthetic():
    real, _ = vp.load_vis3()
    scan = SimpleNamespace(columns=np.array([100, 200, 300]),
                           vb=np.full((3, 1), 250.), vt=np.full((3, 1), 100.))
    proxy = SimpleNamespace(mp=SimpleNamespace(undistort=lambda image: image,
        detect_boundaries=lambda *args: scan), EDGE=real.EDGE, ColumnObs=real.ColumnObs)
    image = np.full((480, 640, 3), 100, np.uint8)
    # Orange below the candidate wall band; a grey robot centre between the parts.
    orange = cv2.cvtColor(np.uint8([[[15, 220, 200]]]), cv2.COLOR_HSV2BGR)[0, 0]
    image[320:350, 180:190] = orange
    image[320:350, 210:220] = orange
    return proxy, image


def test_legacy_function_source_stays_exact_for_existing_acceleration():
    assert hashlib.sha256(inspect.getsource(ow.observations).encode()).hexdigest() == exact.PINNED[
        'opencv_wall_observation.observations']


def test_off_does_not_compute_mask_or_change_observation_bytes(monkeypatch):
    vl, image = synthetic()
    original = ow.observations(vl, image, None)
    monkeypatch.setattr(ow, 'robot_occluded_columns', lambda _: pytest.fail('off computed mask'))
    assert obs_bytes(ow.masked_observations(vl, image, None)) == obs_bytes(original)
    observer = ow.OpenCVObserver(vl, lambda: None)
    assert obs_bytes(observer.observe(image)) == obs_bytes(original)
    assert observer.record() == {'backend': 'opencv_classical_wall_band_v1', 'learned_segmentation': False,
        'model_calls': 0, 'frames': 1, 'closed': False, 'opencv_version': cv2.__version__,
        'detector': ow.DETECTOR, 'own_image_gates': ow.LEGACY}


def test_withheld_columns_clear_both_edges_without_fabrication_or_input_mutation():
    vl, image = synthetic()
    saved = image.copy()
    base = ow.observations(vl, image, None)
    observer = ow.OpenCVObserver(vl, lambda: None, robot_mask=ow.ROBOT_MASK)
    result = observer.observe(image)
    assert result.informative.tolist() == [True, False, True]
    for key in vp.OBS_KEYS:
        a, b = getattr(base, key), getattr(result, key)
        assert a[[0, 2]].tobytes() == b[[0, 2]].tobytes()
        assert b[1] == 0 if key.endswith('kind') else np.isnan(b[1])
    assert np.array_equal(image, saved)
    assert base.informative.all()
    record = observer.record()
    assert record['robot_mask']['input'] == 'own_rgb_only'
    record['robot_mask']['config']['hsv_lower'][0] = 99
    assert ow.ROBOT_MASK_CONFIG['hsv_lower'][0] == 5


@pytest.mark.parametrize('value', ['on', False, True, 'orange_columns_v2'])
def test_unknown_options_rejected_before_observation(value, monkeypatch):
    monkeypatch.setattr(ow, 'observations', lambda *args: pytest.fail('unknown option ran observer'))
    with pytest.raises(ValueError, match='unknown robot_mask'):
        ow.masked_observations(None, None, None, robot_mask=value)
    with pytest.raises(ValueError, match='unknown robot_mask'):
        ow.OpenCVObserver(None, None, robot_mask=value)


def test_frame_rejection_and_closed_worker_contract_stays_in_force():
    vl, image = synthetic()
    observer = ow.OpenCVObserver(vl, lambda: None, robot_mask=ow.ROBOT_MASK)
    with pytest.raises(FrameRejected):
        observer.observe(image[:100])
    assert observer.calls == 0
    observer.close()
    with pytest.raises(WorkerFailure, match='closed'):
        observer.observe(image)


def test_no_colour_and_large_dark_gaps_are_explicit_limits():
    grey = np.full((480, 640, 3), 100, np.uint8)
    assert not ow.robot_occluded_columns(grey).any()
    # Two isolated orange objects do not mask the entire region between them.
    grey[300:320, 10:20] = [0, 100, 255]
    grey[300:320, 600:610] = [0, 100, 255]
    mask = ow.robot_occluded_columns(grey)
    assert mask[15] and mask[605] and not mask[300] and not mask[0] and not mask[-1]


def test_mask_does_not_mutate_a_memoized_legacy_observation(monkeypatch):
    vl, image = synthetic()
    base = ow.observations(vl, image, None)
    raw = obs_bytes(base)
    monkeypatch.setattr(ow, 'observations', lambda *args: base)
    masked = ow.masked_observations(vl, image, None, robot_mask=ow.ROBOT_MASK)
    assert masked.informative.tolist() == [True, False, True]
    assert obs_bytes(base) == raw


def test_real_saved_frames_reproduce_false_edges_and_cost():
    result = evaluate()
    peers, controls = (result['groups'][k] for k in ('peer_visible', 'no_peer_visible'))
    assert result['all_off_byte_identical']
    assert peers['frames'] == 7 and controls['frames'] == 9
    assert peers['frames_with_false_before'] == 3
    assert peers['peer_false_before'] == 4 and peers['peer_false_after'] == 0
    # Removing non-peer edges is a real cost, not silently counted as improvement.
    assert peers['removed_not_labelled_peer'] == 19
    assert controls['before_columns'] == controls['after_columns'] == 293


def test_exact_acceleration_remains_compatible_with_the_opt_in():
    expected = evaluate()
    record = {}
    undo = exact.install(record)
    try:
        assert record['opencv_exact']['installed']
        # evaluate records a source fingerprint, which is unavailable on a memo
        # object; compare observations directly for every recorded frame instead.
        from harness import own_image_gates
        from harness.vision_pose_source_final import measured_column_model
        vl, _ = vp.load_vis3()
        gates = own_image_gates.load()['values']
        rows = json.loads(FIXTURE.read_text())['frames']
        for f, want in zip(rows, expected['frames']):
            bgr = cv2.imread(str(FIXTURE.parent/f['file']))
            camera = measured_column_model(vl.mp, f['camera_record'], vl.mp.column_positions(96, 2))
            for option, key in ((None, 'off_sha256'), (ow.ROBOT_MASK, 'after_sha256')):
                obs = ow.masked_observations(vl, bgr, camera, gates, robot_mask=option)
                assert hashlib.sha256(obs_bytes(obs)).hexdigest() == want[key]
    finally:
        undo()


def test_diagnostic_rejects_changed_input_before_scoring(tmp_path):
    doc = copy.deepcopy(json.loads(FIXTURE.read_text()))
    doc['frames'] = [doc['frames'][0]]
    doc['frames'][0]['file'] = str(FIXTURE.parent/doc['frames'][0]['file'])
    doc['frames'][0]['sha256'] = '0'*64
    manifest = tmp_path/'manifest.json'
    manifest.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='frame hash mismatch'):
        evaluate(manifest)
