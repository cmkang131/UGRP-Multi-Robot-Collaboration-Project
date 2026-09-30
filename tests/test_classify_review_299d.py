"""Fourth independent review of PR #299 at 58dc07e7 (offline JSON only).

Run this file on the archived PR tree. Only the checked-in public acceptance
projection and synthetic admission records are used. No raw lookup or writes.
Counterexamples are strict xfails; --runxfail must expose AssertionError only.
"""
import copy
import importlib.util
import json
import math
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "review_299d_public_builders", Path(__file__).with_name("test_v6h_recorder_contract.py"))
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)
cp = contract.cp
ROBOTS = ("r1", "r2")


def metrics(data, leg=1):
    """Independent reconstruction of the producer's two distance criteria."""
    raw = data["result"]["chain_raw"]
    start = max((raw[r]["leg_start"][str(leg)] for r in ROBOTS), key=lambda s: s["sim_s"])
    end = max((raw[r]["leg_end"][str(leg)] for r in ROBOTS), key=lambda s: s["sim_s"])
    route = data["case"]["route"]
    return {
        "end_error_m": math.dist(end["gt"]["beam_xyz"][:2], route[leg + 1]),
        "leg_error_m": abs(math.dist(start["gt"]["beam_xyz"][:2], end["gt"]["beam_xyz"][:2])
                           - math.dist(route[leg], route[leg + 1])),
    }


@pytest.mark.parametrize("order", ["original", "robot_mapping", "leg_list"])
def test_public_record_and_semantically_unordered_containers_remain_valid(order):
    data, context = contract.public_record()
    for key, value in metrics(data).items():
        assert value == pytest.approx(data["row"]["chain"]["legs"][1][key], abs=1e-12)
    if order == "robot_mapping":
        data["result"]["chain_raw"] = dict(reversed(list(data["result"]["chain_raw"].items())))
    elif order == "leg_list":
        data["row"]["chain"]["legs"].reverse()
        data["result"]["row"] = copy.deepcopy(data["row"])
    before = cp.value_hash(data)
    out = contract.adjudicate(data, context)
    assert out["class"] == "PASS_CLEAN" and out["evidence_valid"], out
    assert cp.value_hash(data) == before


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="299d R1: recorded source beam positions do not constrain derived distance checks")
@pytest.mark.parametrize("boundary", ["leg_end", "leg_start"])
def test_source_distance_failure_cannot_be_hidden_by_pass_summary(boundary):
    data, context = contract.public_record()
    # Mutate a copy, not the public fixture or raw. Both robots' source snapshots
    # disagree with the stored passing distance. Existing timestamps are kept.
    for rid in ROBOTS:
        data["result"]["chain_raw"][rid][boundary]["1"]["gt"]["beam_xyz"][0] += 1.
    source = metrics(data)
    assert source["leg_error_m"] > .1
    if boundary == "leg_end":
        assert source["end_error_m"] > .1
    out = contract.adjudicate(data, context)
    assert out["class"] not in cp.PASS, {"source_metrics": source, "class": out["class"],
                                       "issues": out["hard_limit_chain"]["evidence_issues"]}


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="299d R2: recorded leg does not require both source starts")
@pytest.mark.parametrize("robot,leg", [(r, k) for r in ROBOTS for k in (0, 1)])
def test_recorded_leg_requires_the_producers_start_witnesses(robot, leg):
    data, context = contract.public_record()
    del data["result"]["chain_raw"][robot]["leg_start"][str(leg)]
    reconstructed = cp.ca.pcp.chain_legs(data["case"]["route"], data["result"]["chain_raw"])
    assert reconstructed[leg]["recorded"] is False
    out = contract.adjudicate(data, context)
    assert out["class"] not in cp.PASS, {"class": out["class"],
                                       "issues": out["hard_limit_chain"]["evidence_issues"]}


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="299d R2: source boundary chronology is not validated")
@pytest.mark.parametrize("kind", ["start_after_end", "negative_earlier_end", "stop_after_trace"])
def test_reordered_source_boundaries_cannot_pass(kind):
    data, context = contract.public_record()
    raw = data["result"]["chain_raw"]
    if kind == "start_after_end":
        for rid in ROBOTS:
            snap = raw[rid]["leg_start"]["1"]
            snap["sim_s"] = data["row"]["chain"]["legs"][1]["end_sim_s"] + 1.
            snap["gt"]["t"] = snap["sim_s"]
    elif kind == "negative_earlier_end":
        rid = min(ROBOTS, key=lambda r: raw[r]["leg_end"]["1"]["sim_s"])
        snap = raw[rid]["leg_end"]["1"]
        snap["sim_s"] = snap["gt"]["t"] = -1.
    else:
        data["result"]["gt_at_stop"]["t"] = data["trace"][-1]["t"] + 100.
    out = contract.adjudicate(data, context)
    assert out["class"] not in cp.PASS, {"kind": kind, "class": out["class"],
                                       "issues": out["hard_limit_chain"]["evidence_issues"]}


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="299d R1: registered reader admits a source-distance contradiction")
def test_registered_reader_does_not_count_source_distance_contradiction(tmp_path):
    raw, seal, _ = contract.registered_fixture(tmp_path)
    clean = cp.analyse("registered-clean", raw, sealed_manifest=seal)
    assert clean["summary"]["pass_placements"] == 1
    cid = seal["cases"][0]["attempts"][0]["case_id"]
    result_path = cp.ca.dra.case_dir(raw, cid) / "result.json"
    result = json.loads(result_path.read_text())
    for rid in ROBOTS:
        result["chain_raw"][rid]["leg_end"]["1"]["gt"]["beam_xyz"][0] += 1.
    contract.base.write_json(result_path, result)
    out = cp.analyse("registered-contradiction", raw, sealed_manifest=seal)
    assert out["summary"]["pass_placements"] == 0, out["summary"]


def test_trace_order_and_existing_source_contradiction_checks_remain_closed():
    data, context = contract.public_record()
    data["trace"][10], data["trace"][11] = data["trace"][11], data["trace"][10]
    assert contract.adjudicate(data, context)["state"] == "INVALID"
    data, context = contract.public_record()
    end = data["result"]["chain_raw"]["r1"]["leg_end"]["1"]
    end["gt"]["tilt_deg"] = 16.
    out = contract.adjudicate(data, context)
    assert out["class"] == "FAIL_HARD_LIMIT" and out["hard_limit_chain"]["violated"]
