"""Read-only adapter for the REGISTERED 4c6b439f recorder, not a new writer.

No simulation imports, raw writes, invented completeness receipt or inference
of unmeasured contact cadence. The public acceptance writer is byte-identical.
"""
import hashlib
import json
import re

RECORDER_PATH = "scripts/run_pair_stage_probes.py"
RECORDER_SHA256 = "531c420696ccb4c7d53fbfd17d1b96f3851730fd1f6881951b3c0892edc97c63"
REGISTERED_SCHEMA = "ugrp.zone_pair_v6h_confirmatory.DRAFT.v1"
NAME = "recorder_v4c6b_to_classifier_v1"
NOT_RECORDED = "not_recorded"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def source_identity(manifest):
    # The native driver and the public acceptance wrapper's actual spellings.
    source = manifest.get("source")
    if isinstance(source, dict):
        sha = source.get("source_sha")
        files = source.get("execution_tree", {}).get("files")
    else:
        sha = manifest.get("source_sha")
        files = manifest.get("source_fingerprint", {}).get("files")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha) or not isinstance(files, list):
        raise ValueError("recorder: missing recorded source SHA/file inventory")
    hashes = {f["path"]: f["sha256"] for f in files}
    if (len(hashes) != len(files) or any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes.values())
            or hashes.get(RECORDER_PATH) != RECORDER_SHA256):
        raise ValueError("recorder: unrecognized or contradictory producer fingerprint")
    return {"source_sha": sha, "source_files_sha256": hashes}


def adapt(row, result, trace, *, manifest, case, registration=None):
    """Project actual provenance and observed coverage into a separate value.

    `registration` is the externally hash-pinned registered plan, when present.
    Passing public acceptance provenance verifies FORMAT ONLY, not admission.
    """
    identity = source_identity(manifest)
    if manifest.get("source_changed") is not False:
        raise ValueError("recorder: source_changed is not false")
    if result.get("row") != row:
        raise ValueError("recorder: result.row differs from cases row")
    for key in ("case_id", "cell", "seed", "stage"):
        if case.get(key) != row.get(key) or result.get(key) != row.get(key):
            raise ValueError("recorder: case/result/row identity mismatch: " + key)
    if case.get("contact_track") is not True or case.get("pf_track") is not True or case.get("chain_stop_leg") != 1:
        raise ValueError("recorder: required recorded tracking/stop configuration differs")
    # These fields ARE written by this producer when the corresponding leg is
    # completed. chain_legs requires BOTH robots' start AND end witnesses.
    for leg in row.get("chain", {}).get("legs", []):
        if leg.get("recorded"):
            for robot in ("r1", "r2"):
                for boundary in ("leg_start", "leg_end"):
                    endpoint = result["chain_raw"][robot][boundary][str(leg["leg"])]
                    if not isinstance(endpoint.get("gt"), dict) or not {"t", "beam_xyz", "lift_m", "tilt_deg", "jaws"} <= endpoint["gt"].keys():
                        raise ValueError("recorder: incomplete recorded " + boundary + " GT")
    if not result.get("host_error") and case.get("teacher_held") is True:
        if not isinstance(result.get("teacher", {}).get("gt_after_lift"), dict) or not isinstance(result.get("gt_at_entry"), dict):
            raise ValueError("recorder: missing recorded teacher/entry witnesses")
    identity.update(policy_id=case.get("policy_id", NOT_RECORDED),
                    bundle_id=NOT_RECORDED, registration_run_id=case.get("registration_run_id", NOT_RECORDED))
    receipt = case.get("registration")
    if registration is not None:
        if registration.get("schema") != REGISTERED_SCHEMA or registration.get("sealed") is not True:
            raise ValueError("recorder: unsealed or unsupported registration")
        source_sha = registration.get("execution_source_sha") or (registration.get("execution_authorization") or {}).get("source_sha")
        if source_sha is not None and source_sha != identity["source_sha"]:
            raise ValueError("recorder: execution_source_sha differs from manifest")
        pinned = registration["v6_contract"]["source_sha256"]
        if any(identity["source_files_sha256"].get(p) != h for p, h in pinned.items()):
            raise ValueError("recorder: execution files differ from registered source contract")
        if not isinstance(receipt, dict) or any(receipt.get(k) != expected for k, expected in (
            ("expected_source_sha", identity["source_sha"]),
            ("registration_sha256", registration["registration_sha256"]),
            ("run_id", case.get("registration_run_id")),
        )):
            raise ValueError("recorder: registration receipt/source/run mismatch")
        if manifest.get("registration") != receipt:
            raise ValueError("recorder: manifest/case registration receipts differ")
        frozen = next((c for c in registration["cases"] if c["registration_run_id"] == case.get("registration_run_id")), None)
        # run_case writes labels in case.json; they are not worker settings.
        if frozen is None or {k: v for k, v in case.items() if k not in ("registration", "labels")} != {
                k: v for k, v in frozen.items() if k != "labels"}:
            raise ValueError("recorder: worker settings differ from registered case")
        identity["bundle_id"] = registration["execution_bundle_id"]
    elif receipt is not None or "registration_run_id" in case:
        raise ValueError("recorder: registered case requires its pinned registration")
    wall = result.get("wall_contact") or {}
    times = [s["t"] for s in trace]
    return {"adapter": NAME, "producer_sha256": RECORDER_SHA256,
            "admission": "registered" if registration is not None else "public_format_validation_only",
            "identity": identity,
            "coverage": {"basis": "observed_trace_timestamps_and_length",
                         "start_sim_s": times[0] if times else None,
                         "end_sim_s": times[-1] if times else None, "trace_count": len(times),
                         "max_observed_gap_s": max((b - a for a, b in zip(times, times[1:])), default=None),
                         "acquisition_start_sim_s": NOT_RECORDED, "acquisition_end_sim_s": NOT_RECORDED},
            "wall_contact": {"basis": "recorded_episodes_and_positive_contact_steps",
                             "episode_count": len(wall.get("episodes", [])), "contact_steps": wall.get("steps", NOT_RECORDED),
                             "start_sim_s": NOT_RECORDED, "end_sim_s": NOT_RECORDED,
                             "sample_count": NOT_RECORDED, "sample_period_s": NOT_RECORDED, "max_gap_s": NOT_RECORDED},
            "record_time_evidence_sha256": result.get("evidence_sha256", NOT_RECORDED)}


def normalize_registration(plan, placements):
    """Translate the registered builder's sealed schema without editing it.

    All admission slots come from runs/cases, including absent primary records.
    No hypothetical runtime execution_identity, bundle_id or prior_id required.
    """
    if (plan.get("schema") != REGISTERED_SCHEMA or plan.get("sealed") is not True
            or plan.get("registration_revision") != "v6h" or plan.get("status") not in ("DRAFT", "REGISTERED")):
        raise ValueError("require sealed registered v6h plan")
    if plan.get("registration_sha256") != digest({k: v for k, v in plan.items() if k not in ("registration_sha256", "execution_authorization")}):
        raise ValueError("registered plan payload hash mismatch")
    cfg = plan["confirmatory_plan"]
    if (cfg["primary_seed"] != 941 or cfg["sensitivity_seed"] != 943 or cfg["sensitivity_n"] != 12
            or cfg["default_A"]["pass_at_least"] != 48 or cfg["default_A"]["n_placements"] != 60
            or cfg["operation"]["chain_stop_leg"] != 1 or cfg["operation"]["policy"] != "b-v6h1"
            or cfg["operation"]["pf_track"] is not True or cfg["operation"]["contact_track"] is not True
            or cfg["operation"]["enospc"] != "HOST_ERROR"
            or plan["v6_contract"]["source_sha256"].get(RECORDER_PATH) != RECORDER_SHA256):
        raise ValueError("unsupported registered scientific/recorder contract")
    names = [p["name"] for p in placements]
    if len(names) != 60 or set(names) != {f"C{i:02d}" for i in range(1, 61)}:
        raise ValueError("registered placements require C01..C60")
    pairs = {(p["name"], s) for p in placements for s in ((941, 943) if int(p["name"][1:]) <= 12 else (941,))}
    runs = plan["runs"]
    if (len(runs) != 72 or len({r["id"] for r in runs}) != 72
            or {(r["placement"]["name"], r["seed"]) for r in runs} != pairs):
        raise ValueError("registered runs require exactly 60+12 slots")
    specs = plan["cases"]
    by_run = {c["registration_run_id"]: c for c in specs}
    if len(specs) != 72 or len(by_run) != 72 or len({c["case_id"] for c in specs}) != 72:
        raise ValueError("registered cases require 72 unique identities")
    entries = []
    by_name = {p["name"]: p for p in placements}
    for run in runs:
        c = by_run[run["id"]]
        p = run["placement"]
        if (p != by_name[p["name"]] or c["cell"] != p["name"] or c["seed"] != run["seed"]
                or c["pair_policy"] != run["pair_policy"] or run["pair_policy"] != "b-v6h1"
                or c["chain_stop_leg"] != 1):
            raise ValueError("registered placement/run/case mismatch")
        entries.append({"placement": p["name"], "seed": run["seed"], "attempts": [{"case_id": c["case_id"], "replaces": None}]})
    return {"schema": REGISTERED_SCHEMA, "state": "sealed", "primary_seed": 941, "secondary_seed": 943,
            "cases": entries, "_registered": plan, "_plan_specs": {c["case_id"]: c for c in specs},
            "_attempts": {e["attempts"][0]["case_id"]: (e, 0) for e in entries},
            "_originals": {e["attempts"][0]["case_id"]: e for e in entries}}
