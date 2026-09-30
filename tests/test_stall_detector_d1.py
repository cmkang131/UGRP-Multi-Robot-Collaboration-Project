"""Bounded NumPy-only D1 checks; no physics, renderer, model or raw video replay."""
import ast
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "experiments/2026-09-30-stall-detector-d1"
RESEARCH = ROOT / "experiments/2026-09-30-stall-detection-research"
spec = importlib.util.spec_from_file_location("d1_detector", HERE / "d1_detector.py")
d1 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = d1
spec.loader.exec_module(d1)


def sequence(stop_at=None, noise=0., exposure=0., seed=93001, end=8.):
    """Moving brightness pattern, then frozen; no GT enters detect()."""
    ts = np.arange(int(end * 10) + 1) / 10
    progress = ts if stop_at is None else np.minimum(ts, stop_at)
    stripe = np.where(np.arange(640) // 16 % 2, 1., -1.)
    # Broadcast when clean to avoid allocating 81 full frames per unit test.
    frames = np.broadcast_to((25 + .8 * progress[:, None, None] * stripe[None, None, :]).astype(np.float32),
                             (len(ts), 480, 640))
    if noise or exposure:
        rng = np.random.default_rng(seed)
        frames = np.clip(np.rint(frames * (1 + rng.normal(0, exposure, (len(ts), 1, 1)))
                                 + rng.normal(0, noise, frames.shape)), 0, 255).astype(np.uint8)
    return frames, ts


def replay(frames, ts, parameters=d1.PRIMARY):
    return d1.detect(frames, ts, [d1.CommandInterval(0., 8., "own-command")], parameters)[0]


def test_signed_block_difference_removes_uniform_offset_without_uint8_underflow():
    a = np.full((32, 32), 30, dtype=np.uint8)
    b = a.copy()
    b[:, :16] += 5
    b[:, 16:] -= 5
    assert d1.block_mean_difference(a, b) == 5.
    assert d1.block_mean_difference(a, a - 20) == 0.
    assert d1.block_mean_difference(b, a) == 5.


def test_blocks_discard_remainders_and_are_pixels_not_resized_grid():
    a, b = np.zeros((33, 35)), np.zeros((33, 35))
    b[:32, :16] = 2
    b[:32, 16:32] = -2
    b[32, :] = 999
    b[:, 32:] = 999
    assert d1.block_mean_difference(a, b) == 2.


def test_dark_roi_matches_research_row_rule_and_excludes_black_and_bright():
    a = np.full((480, 640), 100.)
    a[50:430] = 25.
    assert d1.dark_central_roi(a, a) == (60, 419)
    for gray in (0., 3., 60., 255.):
        invalid = np.full_like(a, gray)
        assert d1.measure_frames(invalid, invalid, invalid) is None
    a[50:430, 200:224] = 100.  # exactly 90%, whereas the rule is strictly >90%
    assert d1.dark_central_roi(a, a) is None


def test_rgb_order_and_noise_floor_clamping():
    a = np.broadcast_to(np.array([30, 20, 10], dtype=np.uint8), (480, 640, 3))
    gray = d1._gray(a)
    assert np.all(gray == 22)  # RGB luminance, not BGR
    base = np.full((480, 640), 25.)
    stripes = np.broadcast_to(np.where(np.arange(640) // 16 % 2, 1., -1.), base.shape)
    m = d1.measure_frames(base, base + stripes, base - stripes)
    assert m.short_score > m.long_score and m.score == 0.


@pytest.mark.parametrize("parameters", [d1.PRIMARY, d1.SECONDARY])
def test_moving_then_frozen_detected_after_reference_and_expected_streak(parameters):
    frames, ts = sequence(stop_at=5.)
    r = replay(frames, ts, parameters)
    assert r.status == "EVALUATED"
    # ROI starts at column 100 (four pixels into a stripe); each 16px block
    # averages +/-0.5. 27 blocks are unbalanced by one, then globally centered.
    assert r.reference == pytest.approx(.8 * np.sqrt(.99) * .5 * (1 - 1 / 27**2), abs=1e-6)
    # Partially frozen 1s windows can cross the ratio before becoming identical.
    assert r.alarm_times_s[0] == pytest.approx(6.)
    assert r.alarm_times_s[0] - 5. <= 3.
    assert all(c.state == "REFERENCE" for c in r.checks if c.scheduled_s <= 3.)


@pytest.mark.parametrize("parameters", [d1.PRIMARY, d1.SECONDARY])
def test_moving_control_has_no_alarm(parameters):
    frames, ts = sequence()
    r = replay(frames, ts, parameters)
    assert r.status == "EVALUATED" and not r.alarm_times_s


@pytest.mark.parametrize("signal_scale", [.02, .10, .25])
def test_low_visual_change_controls_are_not_discarded_by_speed_filter(signal_scale):
    frames, ts = sequence()
    frames = 25. + (frames - 25.) * signal_scale
    r = replay(frames, ts)
    assert r.status == "EVALUATED" and r.reference > 0. and not r.alarm_times_s


@pytest.mark.parametrize("noise,exposure", [(1., 0.), (2., 0.), (1., .01)])
def test_noisy_and_exposure_jitter_sequences_preserve_synthetic_detection(noise, exposure):
    # One independent per-pixel noise realization per frame, reused by all checks.
    frames, ts = sequence(stop_at=5., noise=noise, exposure=exposure)
    for parameters in (d1.PRIMARY, d1.SECONDARY):
        r = replay(frames, ts, parameters)
        assert r.status == "EVALUATED" and r.alarm_times_s
        assert 5. <= r.alarm_times_s[0] <= 8.
    frames, ts = sequence(noise=noise, exposure=exposure)
    assert not replay(frames, ts).alarm_times_s


def test_global_additive_exposure_is_removed_but_pattern_motion_remains():
    frames, ts = sequence(stop_at=5.)
    offsets = (np.arange(len(ts)) % 3 - 1) * 2
    jittered = frames + offsets[:, None, None]
    a, b = replay(frames, ts), replay(jittered, ts)
    assert b.reference == pytest.approx(a.reference, abs=1e-6)
    assert a.alarm_times_s == b.alarm_times_s


def test_start_blockage_is_unknown_not_reported_as_progress():
    frames, ts = sequence(stop_at=0.)
    r = replay(frames, ts)
    assert r.status == "INSUFFICIENT_SIGNAL" and r.reference == 0.
    assert not r.alarm_times_s
    assert "NO_STALL_SUSPECT" not in {c.state for c in r.checks}


def test_short_command_and_missing_reference_are_retained():
    frames, ts = sequence()
    r = d1.detect(frames, ts, [d1.CommandInterval(0, 4.9)])[0]
    assert r.status == "UNSUPPORTED_SHORT_COMMAND"
    keep = ts >= 4.
    r = replay(frames[keep], ts[keep])
    assert r.status == "INSUFFICIENT_REFERENCE" and not r.alarm_times_s
    r = d1.detect([], [], [d1.CommandInterval(0, 8)])[0]
    assert r.status == "INSUFFICIENT_REFERENCE"


def test_missing_check_breaks_consecutive_streak():
    frames, ts = sequence(stop_at=5.)
    keep = ~np.isin(np.round(ts, 1), [5.9, 6.0])
    r = replay(frames[keep], ts[keep])
    gap = next(c for c in r.checks if c.scheduled_s == pytest.approx(6.0))
    assert gap.state == "MISSING_FRAME" and gap.consecutive == 0
    assert r.alarm_times_s[0] == pytest.approx(6.4)


def test_invalid_roi_breaks_consecutive_streak():
    frames, ts = sequence(stop_at=5.)
    frames = list(frames)
    frames[60] = np.full((480, 640), 100, dtype=np.uint8)
    r = replay(frames, ts)
    assert next(c for c in r.checks if c.scheduled_s == pytest.approx(6.0)).state == "INVALID_ROI"
    assert r.alarm_times_s[0] == pytest.approx(6.4)


def test_frame_selection_is_causal_and_tolerates_timestamp_jitter():
    frames, ts = sequence(stop_at=5.)
    r = replay(frames, ts + .04)
    assert all(c.frame_s is None or c.frame_s <= c.scheduled_s + 1e-9 for c in r.checks)
    assert r.status == "EVALUATED" and r.alarm_times_s
    # A genuine +-one-frame timestamp perturbation; dedup deterministically.
    jitter = np.random.default_rng(93003).choice([-.1, .1], len(ts))
    order = np.lexsort((np.arange(len(ts)), np.round(ts + jitter, 8)))
    shifted = np.round((ts + jitter)[order], 8)
    keep = np.r_[True, np.diff(shifted) > 0]
    r = replay(frames[order[keep]], shifted[keep])
    assert r.status == "EVALUATED" and r.alarm_times_s


def test_reference_resets_at_each_command_even_after_an_alarm():
    ts = np.arange(101) / 10
    progress = np.where(ts <= 5., np.minimum(ts, 3.5), 3.5 + 2 * (ts - 5.))
    stripe = np.where(np.arange(640) // 16 % 2, 1., -1.)
    frames = np.broadcast_to((25 + .8 * progress[:, None, None] * stripe).astype(np.float32), (len(ts), 480, 640))
    a, b = d1.detect(frames, ts, [d1.CommandInterval(0, 5), d1.CommandInterval(5, 10)])
    assert a.alarm_times_s and not b.alarm_times_s
    assert b.reference == pytest.approx(2 * a.reference, abs=1e-6)


def test_threshold_is_strict_and_is_k_checks_not_k_seconds(monkeypatch):
    # Exercise equality and streak independently of floating grayscale arithmetic.
    frames, ts = sequence()
    def measured(a, b, p):
        t = (float(b[0, 16]) - 25.) / .8
        score = 1. if t <= 3.01 else .4 if t <= 4.01 else .39
        return d1.Measurement(score, 0., score, (10, 469))
    monkeypatch.setattr(d1, "measure_frames", measured)
    r = replay(frames, ts)
    assert not [t for t in r.alarm_times_s if t <= 4.]
    assert r.alarm_times_s[0] == pytest.approx(4.4)


@pytest.mark.parametrize("ratio,k", [(0., 2), (1., 2), (float("nan"), 2), (.4, 0), (.4, True), (.4, 1.5)])
def test_invalid_parameters_fail(ratio, k):
    with pytest.raises(ValueError):
        d1.Parameters(ratio, k)


def test_invalid_timestamps_intervals_frames_fail_without_simulator():
    frames, ts = sequence()
    with pytest.raises(ValueError, match="timestamps"):
        replay(frames, ts[::-1])
    with pytest.raises(ValueError, match="timestamps"):
        replay(frames, ts[:-1])
    with pytest.raises(ValueError, match="ordered"):
        d1.detect(frames, ts, [d1.CommandInterval(0, 6), d1.CommandInterval(5, 8)])
    with pytest.raises(ValueError, match="interval"):
        d1.CommandInterval(2, 2)
    with pytest.raises(ValueError, match="480x640"):
        d1.measure_frames(np.zeros((32, 32)), np.zeros((32, 32)), np.zeros((32, 32)))
    with pytest.raises(ValueError, match="finite"):
        d1.measure_frames(frames[0], frames[0] * np.nan, frames[0])


@pytest.mark.parametrize("ratio,k,median_latency", [(.4, 2, 1.6), (.5, 3, 1.2)])
def test_saved_small_research_tables_reproduce_clean_summary_only(ratio, k, median_latency):
    # Tables contain decisions/latencies, NOT frames or f(t) traces. Recompute
    # their aggregates without inventing D1 input or importing legacy sim code.
    table = json.loads((RESEARCH / f"results/stall_detector_offline_r{ratio}_k{k}.json").read_text())
    rows, summary = table["per_run"], table["summary"]
    stalled = [r for r in rows if r["stall_onset"] is not None]
    moving = [r for r in rows if r["stall_onset"] is None]
    detected = [r for r in stalled if r["latency_s"] is not None]
    expected = summary["f_clean"]
    assert summary["ratio"] == ratio and summary["K"] == k
    assert len(rows) == summary["n_runs"] == 108
    assert len(stalled) == expected["stall_runs"] == 18
    assert len({r["case"] for r in stalled}) == expected["stall_cases"] == 9
    assert len(detected) == expected["stall_detected"] == 18
    assert len(moving) == expected["nonstall_runs"] == 90
    assert sum(r["n_flags"] > 0 for r in moving) == expected["nonstall_runs_with_flag"] == 0
    assert sum(r["n_test"] for r in moving) == expected["test_windows_nonstall"] == 5742
    assert sum(r["n_flags"] for r in moving) == expected["flagged_windows_total_nonstall"] == 0
    assert np.median([r["latency_s"] for r in detected]) == pytest.approx(median_latency)
    assert expected["latency_median_s"] == pytest.approx(median_latency)
    assert max(r["latency_s"] for r in detected) == expected["latency_max_s"]
    assert all(r["first_flag"] - r["stall_onset"] == pytest.approx(r["latency_s"]) for r in detected)


def test_reference_import_boundary_and_ci_registration():
    tree = ast.parse((HERE / "d1_detector.py").read_text())
    imports = [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
    imports += [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert set(imports) <= {"__future__", "dataclasses", "typing", "numpy"}
    from scripts import run_ci_tests as runner
    files = runner.collect_test_files(ROOT, runner.TEST_PATTERNS)
    assert files.count("tests/test_stall_detector_d1.py") == 1
    runner.validate_shards(files, runner.shard_test_files(files, 8))
