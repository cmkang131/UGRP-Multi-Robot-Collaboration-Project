"""Saved-record arithmetic only: no physics, worker, model or shared lock."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ("r1", "r2")
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


def dense_trace(end=20.):
    return [{"t": i * .05, "tilt_deg": 1.} for i in range(round(end / .05) + 1)]


def classify(r=None, episodes=(), trace=None):
    return cp.classify_case(r or row(), {"wall_contact": {"episodes": list(episodes)}},
                            trace if trace is not None else dense_trace())


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
    trace = dense_trace()
    trace[round(t / .05)]["tilt_deg"] = 15.01
    out = classify(r, trace=trace)
    assert out["class"] == "FAIL_HARD_LIMIT"
    assert out["hard_limit_chain"]["violated"] is True


@pytest.mark.parametrize("start,end", [(7., 8.), (18., 19.), (30., 31.)])
def test_whole_chain_penetration_wins_over_pass_fail_or_blocked(start, end):
    for r in (row(), aborted_guard_case()):
        assert classify(r, [episode(start, end, .00501)])["class"] == "FAIL_HARD_LIMIT"


def test_exact_hard_thresholds_are_inclusive_safe_and_shared_predicate_is_used(monkeypatch):
    trace = dense_trace()
    trace[-1]["tilt_deg"] = 15.
    out = classify(episodes=[episode(pen=.005)], trace=trace)
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
    assert s["criterion"]["verdict"] == "NOT_EVALUABLE"  # no seal; historical endpoints only
    assert s["wilson95_primary_classified"] == pytest.approx((.682179539, .881716103), abs=1e-9)
    _, below = cp.summarize(cohort_cases(47))
    assert below["criterion"]["verdict"] == "NOT_EVALUABLE"
    cases.append(classify(row(cell="P59", seed=943), [episode(7., 8., .006)]))
    _, veto = cp.summarize(cases)
    assert veto["pass_placements"] == 48
    assert veto["criterion"]["verdict"] == "NOT_EVALUABLE"
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
    (directory / "eval_only/trace.jsonl").write_text("".join(json.dumps(s) + "\n" for s in dense_trace()))
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

# Review #294 regressions. Fixtures supply real sampling windows, not two points.
@pytest.mark.parametrize('mutation', ['one_row', 'cut_tail', 'cut_head', 'gap', 'reverse', 'duplicate'])
def test_truncated_or_unordered_trace_is_rejected(mutation):
    trace = dense_trace()
    if mutation == 'one_row': trace = trace[:1]
    if mutation == 'cut_tail': trace = trace[:100]
    if mutation == 'cut_head': trace = trace[250:]
    if mutation == 'gap': del trace[100]
    if mutation == 'reverse': trace.reverse()
    if mutation == 'duplicate': trace.insert(100, trace[100])
    with pytest.raises(cp.EvidenceError):
        classify(trace=trace)


@pytest.mark.parametrize('jaws', [{}, {'r1': [True, True]}, {'r1': [], 'r2': []},
                                  {'r1': [1, 1], 'r2': [True, True]}])
def test_missing_or_nonboolean_jaws_cannot_pass(jaws):
    r = row()
    r['chain']['legs'][1]['jaws'] = jaws
    with pytest.raises(cp.EvidenceError, match='jaws'):
        classify(r)


@pytest.mark.parametrize('field,value', [('lift_m', float('inf')), ('end_error_m', -.01),
                                         ('tilt_deg', 181.), ('leg_error_m', float('nan'))])
def test_invalid_leg_metrics_cannot_pass(field, value):
    r = row()
    r['chain']['legs'][1][field] = value
    with pytest.raises(cp.EvidenceError):
        classify(r)


def test_null_failures_mean_no_failure_and_nonnull_failure_vetoes_good_endpoints():
    r = row()
    result = {'wall_contact': {'episodes': []}, 'failures': {'r1': None, 'r2': None}}
    assert cp.classify_case(r, result, dense_trace())['class'] == 'PASS_CLEAN'
    result['failures']['r1'] = {'phase': 'handover', 'code': 'SETDOWN_FAILED'}
    assert cp.classify_case(r, result, dense_trace())['class'] == 'FAIL'
    result['failures']['r1'] = {'phase': 'carry', 'leg': 1, 'code': 'COLLISION_GUARD', 'sim_s': 12.}
    result['wall_contact']['episodes'] = [episode(11., 12.)]
    assert cp.classify_case(r, result, dense_trace())['class'] == 'BLOCKED_BY_CONTACT'
    r['chain']['first_failure'] = {'phase': 'setdown', 'code': 'REST_FAILED'}
    result['failures'] = {'r1': None, 'r2': None}
    assert cp.classify_case(r, result, dense_trace())['class'] == 'FAIL'


def full_evidence(cell='C01', seed=941):
    r = row(cell, seed)
    r['stop_sim_s'] = 15.
    r['final_states'] = {'r1': 'wait_lower', 'r2': 'wait_lower'}
    r['category'] = 'STAGE_BUDGET_EXHAUSTED'  # historic wrapper category, not real timeout
    r['chain']['restaging_between_legs'] = False
    trace = dense_trace(15.)
    for s in trace:
        released = 6. <= s['t'] <= 8.
        s['lift_m'] = 0. if released else .05
        s['jaws'] = {rid: [not released] * 2 for rid in ROBOTS}
    res = {'wall_contact': {'episodes': [], 'coverage': {'start_sim_s': 0., 'end_sim_s': 15.,
            'max_gap_s': .05, 'sample_period_s': .05, 'sample_count': 301}},
           'evaluation_coverage': {'start_sim_s': 0., 'end_sim_s': 15., 'trace_count': 301},
           'failures': {'r1': None, 'r2': None}, 'final_states': r['final_states'],
           'termination': {'outcome': 'STUDY_LAYER_DONE', 'sim_s': 15.}}
    return r, res, trace


def test_confirmatory_handover_and_L1_end_are_separate_from_destination_setdown():
    r, res, trace = full_evidence()
    r['chain']['setdown'] = {'reached': False, 'checks': {'rest': False, 'released': False}}
    out = cp.classify_case(r, res, trace, confirmatory=True)
    assert out['class'] == 'PASS_CLEAN'
    assert out['handover']['rest_release'] and out['handover']['regrasp_lift']
    assert out['end_window']['intended_L1_stop']
    assert out['end_window']['destination_setdown_evaluated'] is False
    for s in trace:
        s['jaws'] = {rid: [True, True] for rid in ROBOTS}
    assert cp.classify_case(r, res, trace, confirmatory=True)['class'] == 'FAIL'


@pytest.mark.parametrize('field', ['coverage', 'count', 'wall_gap', 'late_end', 'regrasp', 'restaging', 'end_state'])
def test_confirmatory_missing_coverage_handover_or_wrong_end_never_passes(field):
    r, res, trace = full_evidence()
    if field == 'coverage': del res['wall_contact']['coverage']
    if field == 'count': res['evaluation_coverage']['trace_count'] -= 1
    if field == 'wall_gap': res['wall_contact']['coverage']['max_gap_s'] = .1
    if field == 'late_end': res['evaluation_coverage']['end_sim_s'] = 14.
    if field == 'regrasp':
        for s in trace:
            if s['t'] >= 9.9: s['jaws'] = {rid: [False, False] for rid in ROBOTS}
        assert cp.classify_case(r, res, trace, confirmatory=True)['class'] == 'FAIL'
        return
    if field == 'restaging': r['chain']['restaging_between_legs'] = True
    if field == 'end_state': r['final_states'] = {'r1': 'failed', 'r2': 'wait_lower'}
    with pytest.raises(cp.EvidenceError):
        cp.classify_case(r, res, trace, confirmatory=True)


def test_actual_timeout_cannot_be_relabelled_from_good_endpoints():
    r, res, trace = full_evidence()
    res['termination']['outcome'] = 'BUDGET_EXHAUSTED'
    assert cp.classify_case(r, res, trace)['class'] == 'FAIL'
    with pytest.raises(cp.EvidenceError):
        cp.classify_case(r, res, trace, confirmatory=True)


def seal_fixture(tmp_path, retries=False):
    raw = tmp_path / 'confirmatory'
    raw.mkdir()
    identity = {'source_sha': 'a' * 40, 'policy_id': 'b-v6h1', 'bundle_id': 'v83',
                'source_files_sha256': {'harness/controller.py': 'b' * 64}}
    placements = [{'name': f'C{i:02d}', 'x': 1., 'y': .05, 'yaw_deg': 0., 'prior': 'hR2_01', 'sheet': 'coarse'}
                  for i in range(1, 61)]
    specs, entries, rows = [], [], []
    for p in placements:
        for seed in ((941, 943) if int(p['name'][1:]) <= 12 else (941,)):
            r, res, trace = full_evidence(p['name'], seed)
            spec = {'case_id': r['case_id'], 'cell': p['name'], 'seed': seed, 'stage': 'chain',
                    'beam_xyyaw': [1., .05, 0.], 'prior': {rid: {'mean': [0., 0., 0.]} for rid in ROBOTS},
                    'prior_id': 'hR2_01', 'coarse_order_sheet': {'beam_xyyaw': [1., 0., 0.]},
                    'policy_id': identity['policy_id'], 'bundle_id': identity['bundle_id'],
                    'source_sha': identity['source_sha'], 'chain_stop_leg': 1}
            specs.append(spec)
            d = cp.ca.dra.case_dir(raw, r['case_id'])
            (d / 'eval_only').mkdir(parents=True)
            (d / 'case.json').write_text(json.dumps(spec))
            res.update(execution_identity=identity, row=r)
            (d / 'result.json').write_text(json.dumps(res))
            (d / 'eval_only/trace.jsonl').write_text(''.join(json.dumps(s) + '\n' for s in trace))
            entry = {'placement': p['name'], 'seed': seed, 'placement_sha256': cp.value_hash(p),
                     'prior_sha256': cp.value_hash(spec['prior']), 'attempts': [
                         {'case_id': r['case_id'], 'replaces': None, 'case_sha256': cp.sha256(d / 'case.json')}]}
            if retries and not entries:
                retry = dict(spec, case_id=spec['case_id'] + ':retry1')
                rd = cp.ca.dra.case_dir(raw, retry['case_id'])
                rd.mkdir(parents=True)
                (rd / 'case.json').write_text(json.dumps(retry))
                entry['attempts'].append({'case_id': retry['case_id'], 'replaces': spec['case_id'],
                                           'case_sha256': cp.sha256(rd / 'case.json')})
            entries.append(entry)
            rows.append(r)
    manifest = {'state': 'completed', 'source_changed': False, 'execution_identity': identity,
                'source': {'source_sha': identity['source_sha'], 'execution_tree': {
                    'files': [{'path': k, 'sha256': v} for k, v in identity['source_files_sha256'].items()]}}}
    (raw / 'cases.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (raw / 'manifest.json').write_text(json.dumps(manifest))
    place_path, plan_path = tmp_path / 'placements.json', tmp_path / 'plan.json'
    place_path.write_text(json.dumps(placements))
    plan_path.write_text(json.dumps({'execution_identity': identity, 'cases': specs}))
    seal = {'schema': 'ugrp.v6h_confirmatory.v1', 'state': 'sealed', 'primary_seed': 941, 'secondary_seed': 943,
            'evaluation_protocol': cp.EVALUATION_PROTOCOL, 'execution_identity': identity, 'placements_file': place_path.name, 'placements_sha256': cp.sha256(place_path),
            'plan_file': plan_path.name, 'plan_sha256': cp.sha256(plan_path), 'cases': entries}
    path = tmp_path / 'seal.json'
    path.write_text(json.dumps(seal))
    return raw, path, rows, manifest


def test_seal_exact_60_plus_12_and_pinned_hash(tmp_path):
    raw, path, rows, manifest = seal_fixture(tmp_path)
    seal = cp.load_sealed_manifest(path, cp.sha256(path))
    assert len(cp.select_confirmatory_rows(rows, raw, manifest, seal)) == 72
    with pytest.raises(cp.EvidenceError, match='hash'):
        cp.load_sealed_manifest(path, '0' * 64)
    with pytest.raises(cp.EvidenceError, match='originals'):
        cp.select_confirmatory_rows([r for r in rows if r['seed'] == 941], raw, manifest, seal)
    changed = copy.deepcopy(rows)
    changed[0]['cell'] = 'P0'
    with pytest.raises(cp.EvidenceError): cp.select_confirmatory_rows(changed, raw, manifest, seal)
    changed = copy.deepcopy(manifest)
    changed['source']['execution_tree']['files'][0]['sha256'] = 'c' * 64
    with pytest.raises(cp.EvidenceError, match='file hashes'):
        cp.select_confirmatory_rows(rows, raw, changed, seal)
    spec_path = cp.ca.dra.case_dir(raw, rows[0]['case_id']) / 'case.json'
    spec_path.write_text(spec_path.read_text() + ' ')
    with pytest.raises(cp.EvidenceError, match='hash/contents'):
        cp.select_confirmatory_rows(rows, raw, manifest, seal)


@pytest.mark.parametrize('mutation', ['placement', 'prior', 'policy', 'bundle', 'source', 'extra_plan_case', 'missing_aux'])
def test_sealed_plan_differences_are_rejected(tmp_path, mutation):
    raw, path, rows, manifest = seal_fixture(tmp_path)
    seal = json.loads(path.read_text())
    plan_path = tmp_path / 'plan.json'
    plan = json.loads(plan_path.read_text())
    if mutation == 'placement': plan['cases'][0]['beam_xyyaw'][0] += .001
    if mutation == 'prior': plan['cases'][0]['prior']['r1']['mean'][0] += .001
    if mutation == 'policy': plan['cases'][0]['policy_id'] = 'other'
    if mutation == 'bundle': plan['cases'][0]['bundle_id'] = 'v84'
    if mutation == 'source': plan['cases'][0]['source_sha'] = 'c' * 40
    if mutation == 'extra_plan_case': plan['cases'].append(plan['cases'][0])
    if mutation == 'missing_aux': seal['cases'] = [c for c in seal['cases'] if c['seed'] == 941]
    plan_path.write_text(json.dumps(plan))
    seal['plan_sha256'] = cp.sha256(plan_path)
    path.write_text(json.dumps(seal))
    with pytest.raises(cp.EvidenceError): cp.load_sealed_manifest(path, cp.sha256(path))


def test_only_linked_predeclared_host_retry_is_selected_once(tmp_path):
    raw, path, rows, manifest = seal_fixture(tmp_path, retries=True)
    seal = cp.load_sealed_manifest(path, cp.sha256(path))
    retry = dict(rows[0], case_id=seal['cases'][0]['attempts'][1]['case_id'])
    with pytest.raises(cp.EvidenceError, match='only HOST_ERROR'):
        cp.select_confirmatory_rows(rows + [retry], raw, manifest, seal)
    rows[0]['category'] = 'HOST_ERROR:worker_exit_-15'
    selected = cp.select_confirmatory_rows(rows + [retry], raw, manifest, seal)
    assert len(selected) == 72 and rows[0]['case_id'] not in {r['case_id'] for r in selected}
    assert retry['case_id'] in {r['case_id'] for r in selected}
    with pytest.raises(cp.EvidenceError): cp.select_confirmatory_rows(rows + [retry, retry], raw, manifest, seal)


def test_sealed_A_48_of_60_and_auxiliary_hard_veto(tmp_path):
    raw, path, rows, manifest = seal_fixture(tmp_path)
    seal = cp.load_sealed_manifest(path, cp.sha256(path))
    cases = []
    for r in rows:
        rr, res, trace = full_evidence(r['cell'], r['seed'])
        if r['seed'] == 941 and int(r['cell'][1:]) > 48:
            rr['chain']['legs'][1]['end_error_m'] = .11
        cases.append(cp.classify_case(rr, res, trace, confirmatory=True))
    _, s = cp.summarize(cases, sealed_manifest=seal)
    assert s['criterion']['verdict'] == 'PASS_OBSERVED_CRITERION'
    assert s['pass_placements'] == 48
    auxiliary = next(c for c in cases if c['seed'] == 943)
    auxiliary['hard_limit_chain']['violated'] = True
    _, s = cp.summarize(cases, sealed_manifest=seal)
    assert s['criterion']['verdict'] == 'FAIL_OBSERVED_CRITERION' and s['pass_placements'] == 48


def pf_sample(t=5., yaw=0.):
    trace = {'t': t, 'robots': {rid: [0., 0., 0.] for rid in ROBOTS},
             'pf': {rid: {'t': t, 'initialized': True, 'x': 0., 'y': 0., 'yaw': yaw,
                         'cov': [[.01, 0., 0.], [0., .01, 0.], [0., 0., .01]]} for rid in ROBOTS}}
    return trace


@pytest.mark.parametrize('mutation', ['stale_row', 'stale_posterior', 'missing_robot', 'negative_cov',
                                     'indefinite_cov', 'nan_cov', 'asymmetric_cov', 'future_posterior'])
def test_sigma_rejects_stale_missing_and_invalid_evidence(mutation):
    trace = pf_sample()
    endpoint = 5.
    if mutation == 'stale_row': endpoint = 105.
    if mutation == 'stale_posterior': trace['pf']['r1']['t'] = 4.
    if mutation == 'missing_robot': del trace['pf']['r1']
    if mutation == 'negative_cov': trace['pf']['r1']['cov'][0][0] = -.01
    if mutation == 'indefinite_cov': trace['pf']['r1']['cov'][0][1] = trace['pf']['r1']['cov'][1][0] = .1
    if mutation == 'nan_cov': trace['pf']['r1']['cov'][0][0] = float('nan')
    if mutation == 'asymmetric_cov': trace['pf']['r1']['cov'][0][1] = .001
    if mutation == 'future_posterior': trace['pf']['r1']['t'] = 5.1
    assert cp.ga.signed_error([trace], endpoint, 'r1') is None


def test_sigma_time_boundary_and_yaw_wrap():
    trace = pf_sample(yaw=2 * 3.141592653589793 - .01)
    value = cp.ga.signed_error([trace], 5.3, 'r1')
    assert value['e'][2] == pytest.approx(-.01)
    assert value['sample_age_s'] == pytest.approx(.3)
    assert cp.ga.signed_error([trace], 5.30001, 'r1') is None
    assert cp.ga.signed_error([trace], 4.99, 'r1') is None


def sigma_classified(cell='C01', seed=941):
    r, res, trace = full_evidence(cell, seed)
    case = cp.classify_case(r, res, trace, confirmatory=True)
    case['sigma'] = cp.sigma_case(r, [pf_sample(5.), pf_sample(15.)])
    return case


def test_sigma_missing_pair_is_not_observed_but_unreached_is_separate():
    a = sigma_classified()
    a['sigma']['L1']['signed']['r2'] = None
    b = sigma_classified('C02')
    b['sigma']['L1'] = {'reached': False, 'signed': {}}
    s = cp.summarize_sigma([a, b])
    assert s['verdict'] == 'NOT_EVALUABLE'
    assert s['legs']['L1']['missing_pf_placements'] == ['C01']
    assert s['legs']['L1']['unreached_placements'] == ['C02']
    assert s['legs']['L1']['n_observed_placements'] == 0
    pairs = [{'unit': 'C01', 'legs': {1: {'reached': True, 'signed': a['sigma']['L1']['signed']}}}]
    pc = cp.ga.placement_coverage(pairs, 1, ['C01'])
    assert pc['n_observed_placements'] == 0 and pc['evidence_verdict'] == 'NOT_EVALUABLE'


def test_sigma_primary_robot_weighting_auxiliary_is_separate_and_six_tests_AND():
    cases = [sigma_classified('C01'), sigma_classified('C02'), sigma_classified('C01', 943)]
    cases[2]['sigma']['L1']['signed']['r1']['z2'] = [100., 100., 100.]
    s = cp.summarize_sigma(cases)
    assert s['verdict'] == 'PASS'
    assert s['legs']['L1']['n_samples'] == 4
    assert s['legs']['L1']['mean_z2_xyyaw'] == [0., 0., 0.]
    assert s['secondary_seed_943']['L1']['verdict'] == 'FAIL'
    cases[0]['sigma']['L0']['signed']['r1']['z2'] = [6., 0., 0.]
    s = cp.summarize_sigma(cases)
    assert s['verdict'] == 'FAIL'
    assert s['legs']['L0']['mean_z2_xyyaw'][0] == 1.5
    assert s['legs']['L0']['axis_pass_xyyaw'] == [False, True, True]


def test_confirmatory_cli_missing_pf_blocks_full_verdict(tmp_path):
    raw, path, rows, manifest = seal_fixture(tmp_path)
    output = tmp_path / 'reports'
    assert cp.main(['--output', str(output), '--sealed-manifest', str(path),
                    '--sealed-manifest-sha256', cp.sha256(path), f'confirm={raw}']) == 0
    s = json.loads((output / 'confirm.json').read_text())['summary']
    assert s['criterion']['verdict'] == 'PASS_OBSERVED_CRITERION'
    assert s['sigma_criterion_B']['verdict'] == 'NOT_EVALUABLE'
    assert s['full_verdict'] == 'NOT_EVALUABLE'


def test_3000_of_3000_mc_has_nonzero_interval_uncertainty():
    spec = importlib.util.spec_from_file_location('v6h_mc',
        ROOT / 'experiments/2026-09-30-pair-v6h-carry/analysis/cohort_sizing.py')
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    value = mc.mc_interval(3000, 3000)
    assert value['plugin_mcse'] == 0.
    assert value['gate_success_draws'] == 3000 and value['gate_failure_draws'] == 0
    assert value['gate_probability_exact95'][0] == pytest.approx(.025 ** (1 / 3000))
    assert value['gate_probability_exact95'][1] == 1.
    assert value['gate_failure_probability_upper_one_sided95'] == pytest.approx(1 - .05 ** (1 / 3000))
    opposite = mc.mc_interval(0, 3000)
    assert opposite['gate_probability_exact95'][0] == 0.
    assert opposite['gate_probability_exact95'][1] == pytest.approx(1 - .025 ** (1 / 3000))
    assert mc.mc_interval(5, 10)['gate_probability_exact95'] == pytest.approx([.187086028, .812913972])


def test_current_draw_rejects_previous_confirmatory_draw_and_is_not_iid(monkeypatch):
    spec = importlib.util.spec_from_file_location('v6h_draw',
        ROOT / 'experiments/2026-09-30-pair-v6h-carry/make_confirmatory_placements.py')
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    class RNG:
        values = iter([1., .05, 0., 1., .05, 0., 1.05, .05, 0.])
        def uniform(self, *args): return next(self.values)
        def integers(self, n): return 0
    monkeypatch.setattr(gen.np.random, 'default_rng', lambda seed: RNG())
    monkeypatch.setattr(gen, 'N', 2)
    monkeypatch.setattr(gen, 'used', lambda: [])
    monkeypatch.setattr(gen, 'hr2_ids', lambda: ['hR2_01'])
    assert [r['x'] for r in gen.draw()] == [1., 1.05]


def test_confirmatory_complete_pf_produces_separate_A_B_and_full_pass(tmp_path):
    raw, path, rows, manifest = seal_fixture(tmp_path)
    for r in rows:
        d = cp.ca.dra.case_dir(raw, r['case_id'])
        trace_path = d / 'eval_only/trace.jsonl'
        trace = [json.loads(s) for s in trace_path.read_text().splitlines()]
        for s in trace:
            if s['t'] in (5., 15.):
                pf = pf_sample(s['t'])
                s.update(pf=pf['pf'], robots=pf['robots'])
        trace_path.write_text(''.join(json.dumps(s) + '\n' for s in trace))
    report = cp.analyse('complete', raw, sealed_manifest=cp.load_sealed_manifest(path, cp.sha256(path)))
    s = report['summary']
    assert s['criterion']['verdict'] == 'PASS_OBSERVED_CRITERION'
    assert s['sigma_criterion_B']['verdict'] == 'PASS'
    assert s['full_verdict'] == 'PASS_A_B_SAFETY'
    assert s['sigma_criterion_B']['legs']['L0']['n_samples'] == 120
    assert s['sigma_criterion_B']['secondary_seed_943']['L0']['n_samples'] == 24
