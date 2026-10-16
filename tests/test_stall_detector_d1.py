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
    assert r.status == "INSUFFICIENT_COVERAGE" and r.alarm_times_s
    assert not r.sufficient_coverage  # preserve alarms without qualifying observation


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


@pytest.mark.parametrize("end,seed,valid,total", [
    (60., 93001, 223, 284), (60., 93002, 224, 284), (60., 93003, 231, 284),
    (90., 93001, 349, 434), (90., 93002, 341, 434), (90., 93003, 350, 434),
])
def test_timestamp_jitter_below_95_percent_is_observation_failure(monkeypatch, end, seed, valid, total):
    # Constant valid scores isolate timestamp selection; no frames or physics.
    monkeypatch.setattr(d1, "measure_frames", lambda *args: d1.Measurement(1., 0., 1., (10, 469)))
    ts = np.arange(int(end * 10) + 1) / 10
    shifted = np.round(ts + np.random.default_rng(seed).choice([-.1, .1], len(ts)), 8)
    order = np.lexsort((np.arange(len(ts)), shifted))
    shifted = shifted[order]
    shifted = shifted[np.r_[True, np.diff(shifted) > 0]]
    r = d1.detect([None] * len(shifted), shifted, [d1.CommandInterval(0., end)])[0]
    checks = [c for c in r.checks if c.scheduled_s > 3. + 1e-9]
    assert (sum(c.measurement is not None for c in checks), len(checks)) == (valid, total)
    assert r.status == "INSUFFICIENT_COVERAGE"
    assert r.valid_check_fraction == pytest.approx(valid / total)
    assert not r.alarm_times_s


def test_preregistration_requires_exact_30_and_predata_freeze():
    text = (HERE / "PREREG_DRAFT.md").read_text()
    assert "정확히 **5종×6=30개**" in text
    assert "INCOMPLETE" in text
    assert "실제 정체 ≥24" not in text
    assert "예: 24건이면" not in text
    assert "주 **(ratio=0.4, k=2)**, 보조 **(0.5, 3)**" in text
    assert "사후 선택 금지" in text
    assert "사전 제한 범위 가설은 이번 초안에 없음" in text
    assert "95% 관측 관문을 AND로 요구" in text


def evaluation():
    spec = importlib.util.spec_from_file_location("d1_evaluation", HERE / "d1_evaluation.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def labeled_result(alarm_times=(), invalid_times=(), end=8.):
    # GT labels are passed ONLY to the separate evaluator, never detect().
    checks = tuple(d1.Check(float(t), float(t),
                           None if any(abs(t - v) < 1e-9 for v in invalid_times) else
                           d1.Measurement(1., 0., 1., (10, 469)),
                           "STALL_SUSPECT" if any(abs(t - v) < 1e-9 for v in alarm_times) else
                           "NO_STALL_SUSPECT") for t in np.arange(1., end, .2))
    return d1.IntervalResult(d1.CommandInterval(0., end), d1.PRIMARY, 1., "EVALUATED", checks)


def test_alarm_after_recovery_is_false_alarm_not_detection():
    r = labeled_result(alarm_times=(6.4,))
    # A sole GT STALL window [4,5); the next check records recovery.
    labels = ["STALL" if abs(c.scheduled_s - 5.) < 1e-9 else "MOVING" for c in r.checks]
    s = evaluation().score_interval(r, labels)
    assert len(s.events) == 1 and s.events[0].alarm_s is None
    assert s.events[0].start_s == pytest.approx(4.)
    assert s.events[0].end_s == pytest.approx(5.2)
    assert s.false_alarm_times_s == pytest.approx((6.4,))
    assert s.unmatched_alarm_times_s == pytest.approx((6.4,))


@pytest.mark.parametrize("missing,expected", [(2, "EVALUATED"), (3, "INSUFFICIENT_COVERAGE")])
def test_exact_95_percent_boundary_keeps_all_scheduled_checks(monkeypatch, missing, expected):
    ts = np.arange(113) / 10
    missing_times = [3.2 + .2 * n for n in range(missing)]
    def measure(a, b, p):
        return None if any(abs(b - t) < 1e-9 for t in missing_times) else d1.Measurement(1., 0., 1., (10, 469))
    monkeypatch.setattr(d1, "measure_frames", measure)
    r = d1.detect(ts, ts, [d1.CommandInterval(0., 11.2)])[0]
    assert len(r.detection_checks) == 40
    assert r.valid_check_fraction == pytest.approx((40 - missing) / 40)
    assert r.status == expected
    assert r.sufficient_coverage == (missing == 2)


@pytest.mark.parametrize("counts,expected", [
    ((6, 6, 6, 6, 6), "COMPLETE"), ((6, 6, 6, 6, 0), "INCOMPLETE"),
    ((6, 6, 6, 6, 5), "INCOMPLETE"), ((7, 6, 6, 6, 5), "INCOMPLETE"),
    ((7, 6, 6, 6, 6), "INCOMPLETE"),
])
def test_cohort_count_gate_requires_all_five_kinds_and_exact_30(counts, expected):
    e = evaluation()
    kinds = [kind for kind, count in zip(e.STALL_KINDS, counts) for _ in range(count)]
    assert e.stall_cohort_status(kinds) == expected


def test_other_closes_event_and_later_event_cannot_rescue_first_miss():
    r = labeled_result(alarm_times=(5., 6.4, 6.6))
    labels = ["STALL" if 4. - 1e-9 <= c.scheduled_s < 5. - 1e-9 or
              6. - 1e-9 <= c.scheduled_s < 7. - 1e-9 else
              "OTHER" if abs(c.scheduled_s - 5.) < 1e-9 else "MOVING" for c in r.checks]
    s = evaluation().score_interval(r, labels)
    assert len(s.events) == 2
    assert s.events[0].end_s == pytest.approx(5.) and s.events[0].alarm_s is None
    assert s.events[1].alarm_s == pytest.approx(6.4)
    assert s.events[1].latency_s == pytest.approx(1.4)
    assert s.unmatched_alarm_times_s == pytest.approx((5.,))
    assert not s.false_alarm_times_s and s.other_checks == 1


def test_early_false_alarm_is_retained_when_later_alarm_matches_event():
    r = labeled_result(alarm_times=(3.4, 4.4, 4.6, 5.))
    labels = ["STALL" if 4. - 1e-9 <= c.scheduled_s < 5. - 1e-9 else "MOVING" for c in r.checks]
    s = evaluation().score_interval(r, labels)
    assert s.events[0].start_s == pytest.approx(3.)
    assert s.events[0].alarm_s == pytest.approx(4.4)
    assert s.events[0].latency_s == pytest.approx(1.4)
    assert s.false_alarm_times_s == pytest.approx((3.4, 5.))


def test_event_persisting_to_command_end_and_no_cross_command_matching():
    r = labeled_result(alarm_times=(7.8,))
    labels = ["STALL" if c.scheduled_s >= 4. - 1e-9 else "MOVING" for c in r.checks]
    s = evaluation().score_interval(r, labels)
    assert s.events[0].end_s == 8. and s.events[0].alarm_s == pytest.approx(7.8)
    assert not s.unmatched_alarm_times_s
    r = labeled_result(alarm_times=(6.4,))
    s = evaluation().score_interval(r, ["MOVING"] * len(r.checks))
    assert not s.events and s.false_alarm_times_s == pytest.approx((6.4,))


def test_missing_images_remain_in_moving_denominator_and_block_zero_alarm_pass():
    r = labeled_result(invalid_times=(4., 5.))
    s = evaluation().score_interval(r, ["MOVING"] * len(r.checks))
    assert s.moving_checks == 24 and not s.false_alarm_times_s
    assert s.observation_status == "INSUFFICIENT_COVERAGE" and not s.moving_control_pass
    s = evaluation().score_interval(labeled_result(), ["MOVING"] * len(r.checks))
    assert s.moving_control_pass


def test_coverage_failure_keeps_raw_alarm_but_scores_stall_as_miss():
    r = labeled_result(alarm_times=(6.4,), invalid_times=(4., 5.))
    labels = ["STALL" if c.scheduled_s >= 6. - 1e-9 else "MOVING" for c in r.checks]
    s = evaluation().score_interval(r, labels)
    assert r.alarm_times_s == pytest.approx((6.4,))
    assert s.events[0].alarm_s is None and s.events[0].latency_s is None
    assert s.unmatched_alarm_times_s == pytest.approx((6.4,))


def test_incomplete_gt_labels_check_grid_and_unknown_mechanisms_are_rejected():
    e, r = evaluation(), labeled_result()
    with pytest.raises(ValueError, match="every scheduled check"):
        e.score_interval(r, ["MOVING"] * (len(r.checks) - 1))
    with pytest.raises(ValueError, match="every scheduled check"):
        e.score_interval(r, ["MISSING_GT"] * len(r.checks))
    truncated = d1.IntervalResult(r.command, r.parameters, r.reference, r.status, r.checks[:-1])
    with pytest.raises(ValueError, match="complete scheduled check grid"):
        e.score_interval(truncated, ["MOVING"] * len(truncated.checks))
    with pytest.raises(ValueError, match="unknown stall mechanism"):
        e.stall_cohort_status(["unknown"])
    labels = ["OTHER"] + ["MOVING"] * (len(r.checks) - 1)
    assert not e.score_interval(r, labels).moving_control_pass


def test_primary_secondary_order_and_statistics_are_rederived():
    from statistics import NormalDist
    assert (d1.PRIMARY.ratio, d1.PRIMARY.consecutive) == (.4, 2)
    assert (d1.SECONDARY.ratio, d1.SECONDARY.consecutive) == (.5, 3)
    z = NormalDist().inv_cdf(.975)
    for x, n, expected in ((22, 24, 74.1512), (27, 30, 74.3789), (24, 30, 62.6943)):
        p = x / n
        lower = (p + z*z/(2*n) - z * (p*(1-p)/n + z*z/(4*n*n))**.5) / (1+z*z/n)
        assert lower * 100 == pytest.approx(expected, abs=.00005)
    assert 24 / 30 == .8
    assert (1 - .05**(1 / 60)) * 100 == pytest.approx(4.870291, abs=.0000005)
