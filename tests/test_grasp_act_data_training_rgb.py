"""Admission evidence for training RGB in grasp_act_data.convert.

Covers _training_rgb_ok: legacy stamped results, explicit false, and the
pairact warp-teacher shape (no stamp) which must present in-recording
evidence and fail closed when any piece is missing.
"""
from pathlib import Path

from harness.grasp_act_data import _training_rgb_ok


def _make_raw(root: Path, robots=("r1", "r2"), frames=True) -> Path:
    raw = root / "raw"
    for robot in robots:
        d = raw / "rgb" / robot
        d.mkdir(parents=True, exist_ok=True)
        if frames:
            (d / "frame-000001.jpg").write_bytes(b"x")
    return raw


def _pairact_result():
    return {
        "recording_mode": "training",
        "observation_sampling": {"rgb_size": [640, 480], "rgb_hz": 10},
    }


def test_stamped_true_accepted_without_evidence(tmp_path):
    result = {"training_rgb": True}
    assert _training_rgb_ok(result, tmp_path / "raw") is True


def test_stamped_false_always_rejected(tmp_path):
    raw = _make_raw(tmp_path)
    result = _pairact_result()
    result["training_rgb"] = False
    assert _training_rgb_ok(result, raw) is False


def test_unstamped_pairact_with_full_evidence_accepted(tmp_path):
    raw = _make_raw(tmp_path)
    assert _training_rgb_ok(_pairact_result(), raw) is True


def test_unstamped_missing_rgb_dir_rejected(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    assert _training_rgb_ok(_pairact_result(), raw) is False


def test_unstamped_empty_robot_dir_rejected(tmp_path):
    raw = _make_raw(tmp_path, robots=("r1",))
    (raw / "rgb" / "r2").mkdir(parents=True)
    assert _training_rgb_ok(_pairact_result(), raw) is False


def test_unstamped_no_frames_rejected(tmp_path):
    raw = _make_raw(tmp_path, frames=False)
    assert _training_rgb_ok(_pairact_result(), raw) is False


def test_unstamped_wrong_mode_rejected(tmp_path):
    raw = _make_raw(tmp_path)
    result = _pairact_result()
    result["recording_mode"] = "evaluation"
    assert _training_rgb_ok(result, raw) is False


def test_unstamped_missing_sampling_block_rejected(tmp_path):
    raw = _make_raw(tmp_path)
    result = _pairact_result()
    del result["observation_sampling"]
    assert _training_rgb_ok(result, raw) is False
