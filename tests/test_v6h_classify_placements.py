"""Saved-record arithmetic only: no physics, worker, model or shared lock."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "v6h_classify_under_test",
    ROOT / "experiments/2026-09-30-pair-v6h-carry/analysis/classify_placements.py")
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)


def leg(k, **overrides):
    value = {"leg": k, "recorded": True, "start_sim_s": 10. * k, "end_sim_s": 10. * k + 5.,
             "lift_m": .05, "tilt_deg": 1., "jaws": {"r1": [True, True], "r2": [True, True]},
             "end_error_m": .01, "leg_error_m": .01}
    value.update(overrides)
    return value


def row(cell="A", seed=941, **overrides):
    value = {"case_id": f"chain@policy:teacher:{cell}:s{seed}", "stage": "chain", "cell": cell, "seed": seed,
             "stop_sim_s": 20., "chain": {"legs": [leg(0), leg(1)], "first_failure": None}}
    value.update(overrides)
    return value


def episode(start=1., end=2., pen=.004):
    return {"t_first": start, "t_last": end, "max_pen_m": pen, "who": "beam"}


def classify(r=None, episodes=(), trace=None):
    return cp.classify_case(r or row(), {"wall_contact": {"episodes": list(episodes)}},
                            trace if trace is not None else [{"t": 0., "tilt_deg": 1.}, {"t": 20., "tilt_deg": 1.}])


def test_clean_and_contact_recovered_include_handover_contact():
    assert classify()["class"] == "PASS_CLEAN"
    # Between L0 and L1: still not clean, even though no leg window contains it.
    assert classify(episodes=[episode(7., 8.)])["class"] == "PASS_CONTACT_RECOVERED"


@pytest.mark.parametrize("start,end", [(12., 13.), (9., 10.), (15., 17.), (9., 17.)])
def test_failed_recorded_leg_with_overlap_is_blocked(start, end):
    r = row()
    r["chain"]["legs"][1]["end_error_m"] = .11
    assert classify(r, [episode(start, end, .005)])["class"] == "BLOCKED_BY_CONTACT"


@pytest.mark.parametrize("start,end", [(7., 8.), (15.001, 16.), (1., 2.)])
def test_contact_outside_failed_leg_does_not_make_blocked(start, end):
    r = row()
    r["chain"]["legs"][1]["end_error_m"] = .11
    assert classify(r, [episode(start, end)])["class"] == "FAIL"


def aborted_guard_case():
    r = row()
    r["chain"]["legs"][1] = {"leg": 1, "recorded": False, "start_sim_s": 10., "end_sim_s": None}
    r["chain"]["first_failure"] = {"phase": "carry", "leg": 1, "sim_s": 13., "code": "COLLISION_GUARD"}
    return r


def test_guard_stop_requires_actual_contact_and_uses_failure_time():
    r = aborted_guard_case()
    result = classify(r, [episode(12., 13.)])
    assert result["class"] == "BLOCKED_BY_CONTACT"
    assert result["first_failure"]["code"] == "COLLISION_GUARD"
    assert result["legs"]["L1"]["window_sim_s"] == (10., 13.)
    assert result["legs"]["L1"]["window_source"] == "first_failure_sim_s"
    assert classify(r)["class"] == "FAIL"
    assert classify(r, [episode(13.001, 14.)])["class"] == "FAIL"


def test_incomplete_leg_fallback_is_explicit_and_unstarted_leg_has_no_window():
    r = aborted_guard_case()
    r["chain"]["first_failure"] = None
    assert classify(r)["legs"]["L1"]["window_source"] == "stop_sim_s"
    del r["stop_sim_s"]
    assert classify(r)["legs"]["L1"]["window_source"] == "last_trace_sim_s"
    r["chain"]["legs"][1]["start_sim_s"] = None
    out = classify(r, [episode(12., 13.)])
    assert out["class"] == "FAIL"
    assert out["legs"]["L1"]["window_sim_s"] is None


@pytest.mark.parametrize("t", [2., 7., 12., 18.])
def test_whole_chain_tilt_hard_limit_covers_legs_setdown_and_regrasp(t):
    r = row()
    r["chain"]["legs"][1]["end_error_m"] = .11
    out = classify(r, trace=[{"t": 0., "tilt_deg": 1.}, {"t": t, "tilt_deg": 15.01}])
    assert out["class"] == "FAIL_HARD_LIMIT"
    assert out["hard_limit_chain"]["violated"] is True


@pytest.mark.parametrize("start,end", [(7., 8.), (18., 19.), (30., 31.)])
def test_whole_chain_penetration_wins_over_pass_fail_or_blocked(start, end):
    for r in (row(), aborted_guard_case()):
        assert classify(r, [episode(start, end, .00501)])["class"] == "FAIL_HARD_LIMIT"


def test_exact_hard_thresholds_are_inclusive_safe_and_shared_predicate_is_used(monkeypatch):
    out = classify(episodes=[episode(pen=.005)], trace=[{"t": 20., "tilt_deg": 15.}])
    assert out["class"] == "PASS_CONTACT_RECOVERED"
    seen = []

    def shared(episodes, tilt):
        seen.append((episodes, tilt))
        return True

    monkeypatch.setattr(cp.ca, "hard_limit_violated", shared)
    assert classify()["class"] == "FAIL_HARD_LIMIT"
    assert seen == [([], 1.)]


def test_setdown_standard_checks_are_not_added_to_the_two_leg_criterion():
    r = row()
    r["chain"]["setdown"] = {"reached": False, "checks": {"rest": False}}
    assert classify(r)["class"] == "PASS_CLEAN"


@pytest.mark.parametrize("trace", [[], [{"t": 20.}], [{"t": 20., "tilt_deg": float("nan")}],
                                 [{"t": float("inf"), "tilt_deg": 1.}]])
def test_missing_or_nonfinite_trace_never_yields_clean_pass(trace):
    with pytest.raises(cp.EvidenceError):
        classify(trace=trace)


def test_missing_tracker_is_not_assumed_zero_and_input_records_are_unchanged():
    r = row()
    saved = copy.deepcopy(r)
    with pytest.raises(cp.EvidenceError, match="wall-contact"):
        cp.classify_case(r, {}, [{"t": 20., "tilt_deg": 1.}])
    classify(r)
    assert r == saved


def test_primary_seed_is_separate_from_all_seed_and_any_seed_counts():
    other = row(seed=943)
    other["chain"]["legs"][1]["end_error_m"] = .11
    placements, s = cp.summarize([classify(), classify(other)])
    assert placements[0]["class"] == "PASS_CLEAN"
    assert (s["pass_placements"], s["placements_all_recorded_seeds_pass"], s["placements_any_recorded_seed_pass"]) == (1, 0, 1)
    assert s["n_placements"] == 1
    assert s["criterion"]["verdict"] == "NOT_EVALUABLE"
    _, missing = cp.summarize([classify(other)])
    assert missing["unclassified_placements"] == ["A"]
    assert missing["wilson95_primary_classified"] is None


def test_duplicate_seed_is_rejected_instead_of_merging_different_policies():
    with pytest.raises(cp.EvidenceError, match="duplicate placement/seed"):
        cp.summarize([classify(), classify()])


def cohort_cases(passed=48):
    cases = []
    for k in range(60):
        r = row(cell=f"P{k}")
        if k >= passed:
            r["chain"]["legs"][1]["end_error_m"] = .11
        cases.append(classify(r))
    return cases


def test_observed_criterion_48_of_60_and_safety_veto_even_for_auxiliary_seed():
    cases = cohort_cases()
    _, s = cp.summarize(cases)
    assert s["criterion"]["verdict"] == "PASS_OBSERVED_CRITERION"
    assert s["wilson95_primary_classified"] == pytest.approx((.682179539, .881716103), abs=1e-9)
    _, below = cp.summarize(cohort_cases(47))
    assert below["criterion"]["verdict"] == "FAIL_OBSERVED_CRITERION"
    cases.append(classify(row(cell="P59", seed=943), [episode(7., 8., .006)]))
    _, veto = cp.summarize(cases)
    assert veto["pass_placements"] == 48
    assert veto["criterion"]["verdict"] == "FAIL_OBSERVED_CRITERION"
    assert veto["hard_limit_chain_cases"] == 1


def test_binomial_tail_matches_small_exact_case_and_draft_probabilities():
    assert cp.binomial_tail(.5, 3, 2) == .5
    assert cp.binomial_tail(.7) == pytest.approx(.057, abs=.001)
    assert cp.binomial_tail(.75) == pytest.approx(.232, abs=.001)
    assert cp.binomial_tail(.85) == pytest.approx(.894, abs=.001)
    assert cp.binomial_tail(.75) < cp.binomial_tail(.80) < cp.binomial_tail(.85)


def raw_fixture(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    r = row()
    (root / "cases.jsonl").write_text(json.dumps(r) + "\n")
    (root / "manifest.json").write_text(json.dumps({"state": "completed", "source_changed": False,
                                                   "source": {"source_sha": "fixture"}}))
    directory = cp.ca.dra.case_dir(root, r["case_id"])
    (directory / "eval_only").mkdir(parents=True)
    (directory / "result.json").write_text(json.dumps({"wall_contact": {"episodes": []}}))
    (directory / "eval_only/trace.jsonl").write_text(json.dumps({"t": 20., "tilt_deg": 1.}) + "\n")
    return root


def test_saved_raw_cli_writes_json_txt_and_refuses_overwrite(tmp_path, capsys):
    raw = raw_fixture(tmp_path)
    before = cp.sha256(raw / "cases.jsonl")
    output = tmp_path / "out"
    assert cp.main(["--output", str(output), f"fixture={raw}"]) == 0
    report = json.loads((output / "fixture.json").read_text())
    assert report["summary"]["pass_placements"] == 1
    assert report["input_sha256"]["cases.jsonl"] == before == cp.sha256(raw / "cases.jsonl")
    assert "Wilson 95%" in (output / "fixture.txt").read_text()
    assert "p=0.8:" in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        cp.main(["--output", str(output), f"fixture={raw}"])
    assert error.value.code == 2


def test_host_error_is_unclassified_not_an_ordinary_fail_or_a_pass(tmp_path):
    raw = raw_fixture(tmp_path)
    host = row(cell="HOST")
    del host["chain"]
    host["category"] = "HOST_ERROR:worker_exit_-15"
    with (raw / "cases.jsonl").open("a") as stream:
        stream.write(json.dumps(host) + "\n")
    report = cp.analyse("host", raw)
    assert report["summary"]["n_placements"] == 2
    assert report["summary"]["n_classified_primary"] == 1
    assert report["summary"]["unclassified_placements"] == ["HOST"]
    assert report["summary"]["counts"]["FAIL"] == 0
    assert report["summary"]["criterion"]["verdict"] == "NOT_EVALUABLE"


@pytest.mark.parametrize("state,changed", [("running", False), ("completed", True), ("completed", None)])
def test_unfinished_or_changed_source_manifest_cannot_declare_observed_pass(tmp_path, state, changed):
    raw = raw_fixture(tmp_path)
    (raw / "manifest.json").write_text(json.dumps({"state": state, "source_changed": changed}))
    report = cp.analyse("unfinished", raw)
    assert report["summary"]["criterion"]["verdict"] == "NOT_EVALUABLE"
    assert "evidence_blocker" in report["summary"]["criterion"]


def test_cli_cannot_write_inside_read_only_raw(tmp_path):
    raw = raw_fixture(tmp_path)
    with pytest.raises(SystemExit) as error:
        cp.main(["--output", str(raw / "new_results"), f"fixture={raw}"])
    assert error.value.code == 2
    assert not (raw / "new_results").exists()


def test_ci_registration_contains_the_new_module():
    from scripts import run_ci_tests
    assert "tests/test_v6h_classify_placements.py" in run_ci_tests.collect_test_files(ROOT, run_ci_tests.TEST_PATTERNS)
