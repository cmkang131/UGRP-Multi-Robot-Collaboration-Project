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
# The committed metadata identifies a thin driver calling this same worker.
# These pins identify that format/run, not a preregistration or an outcome.
BLINDED_SCHEMA = "v6h1-confirm-blinded.manifest.v1"
BLINDED_PLAN_SCHEMA = "v6h1-confirm-blinded.plan.v1"
BLINDED_SOURCE_SHA = "4c6b439f3f7c9a147c901f8b260a1e214d4eb396"
BLINDED_DRIVER_SHA256 = "7a35229e431409904dffec27b5e9572f290cd900f0595c8e0babc5ef92cf3e56"
BLINDED_PLAN_SHA256 = "d627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026"
BLINDED_ADMISSION = ("unsealed_stage_probe (no --prereg; prereg_v6h.json not yet sealed); "
                     "cases byte-equal to build_prereg_v6h.build() cases minus registration_run_id")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def blinded_run_identity(manifest, plan, plan_sha256):
    """Validate committed run metadata without following any recorded raw path.

    The caller pins the manifest bytes and checks plan/commands file bytes.
    No file inventory, registration receipt or acquisition coverage is invented.
    """
    source, raw = manifest["source"], manifest["raw"]
    if (manifest.get("schema") != BLINDED_SCHEMA or manifest.get("blinded") is not True
            or source.get("head_sha") != BLINDED_SOURCE_SHA
            or source.get("source_changed_during_run") is not False
            or source.get("git_status_porcelain_at_start") != ""
            or source.get("git_status_porcelain_at_end_clean") is not True
            or raw.get("driver_py_sha256") != BLINDED_DRIVER_SHA256):
        raise ValueError("recorder: unsupported blinded driver/source identity")
    if (plan.get("schema") != BLINDED_PLAN_SCHEMA or plan.get("source_sha") != source["head_sha"]
            or plan.get("source_status_porcelain") != ""
            or plan_sha256 != raw.get("plan_json_sha256") or plan_sha256 != BLINDED_PLAN_SHA256):
        raise ValueError("recorder: blinded plan source/hash mismatch")
    if manifest.get("admission") != BLINDED_ADMISSION or plan.get("admission") != BLINDED_ADMISSION:
        raise ValueError("recorder: blinded admission must remain unsealed_stage_probe")
    if manifest.get("policy") != "b-v6h1" or plan.get("policy") != "b-v6h1":
        raise ValueError("recorder: blinded policy mismatch")
    expected = {"clock": "SIM", "weld": False, "model_calls": 0, "render_profile": "floor_light_v1",
                "chain_stop_leg": 1, "pf_track": True, "contact_track": True,
                "stage_sim_budget_s": 800.0, "case_timeout_wall_s": 1500.0,
                "workers": 4, "omp_threads": 1}
    for key, value in expected.items():
        plan_key = "stage_budget_s" if key == "stage_sim_budget_s" else key
        if (manifest["run"].get(key) != value or plan.get(plan_key) != value
                or isinstance(value, bool) and (manifest["run"][key] is not value or plan[plan_key] is not value)):
            raise ValueError("recorder: blinded run/plan configuration mismatch: " + key)
    specs, records = plan["cases"], manifest["cases"]
    pairs = {(f"C{i:02d}", seed) for i in range(1, 61) for seed in ((941, 943) if i <= 12 else (941,))}
    if (len(specs) != 72 or len(records) != 72
            or len({c["case_id"] for c in specs}) != 72 or len({c["case_id"] for c in records}) != 72
            or {(c["cell"], c["seed"]) for c in specs} != pairs
            or {c["case_id"] for c in records} != {c["case_id"] for c in specs}
            or manifest.get("completion") != {"finished": 72} or manifest.get("reruns") != 0
            or manifest.get("first_pass_not_finished") != [] or raw.get("cases_dirs") != 72):
        raise ValueError("recorder: blinded run requires the complete 60+12 identity inventory")
    by_id = {c["case_id"]: c for c in specs}
    for record in records:
        case = by_id[record["case_id"]]
        directory = "cases/" + re.sub(r"[^A-Za-z0-9_.-]+", "_", case["case_id"])
        if (any(record[k] != case[k] for k in ("cell", "seed"))
                or record.get("case_dir") != directory or record.get("commands_json") != directory + "/commands.json"
                or record.get("role") != ("confirmatory_primary" if case["seed"] == 941 else "sensitivity_first12")
                or record.get("attempt") != 1 or record.get("status") != "finished"
                or record.get("worker_exit") != 0 or record.get("result_json_present") is not True
                or not isinstance(record.get("commands_json_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["commands_json_sha256"])):
            raise ValueError("recorder: blinded case identity/path/command hash mismatch")
    for key in ("cases_jsonl_sha256", "plan_json_sha256", "driver_py_sha256"):
        if not isinstance(raw.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", raw[key]):
            raise ValueError("recorder: missing blinded artifact hash: " + key)
    return {"source_sha": source["head_sha"], "driver_sha256": raw["driver_py_sha256"],
            "plan_sha256": plan_sha256, "policy_id": plan["policy"],
            "bundle_id": NOT_RECORDED, "registration_run_id": NOT_RECORDED}


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


def adapt(row, result, trace, *, manifest, case, registration=None,
          run_plan=None, plan_sha256=None, commands_sha256=None):
    """Project actual provenance and observed coverage into a separate value.

    `registration` is the externally hash-pinned registered plan, when present.
    Passing public acceptance provenance verifies FORMAT ONLY, not admission.
    """
    blinded = manifest.get("schema") == BLINDED_SCHEMA
    if blinded:
        identity = blinded_run_identity(manifest, run_plan, plan_sha256)
        if registration is not None or "registration" in case or "registration_run_id" in case:
            raise ValueError("recorder: unsealed blinded run has no registration receipt")
        planned = next((c for c in run_plan["cases"] if c["case_id"] == case.get("case_id")), None)
        if planned is None or {k: v for k, v in case.items() if k != "labels"} != planned:
            raise ValueError("recorder: blinded worker settings differ from pinned plan")
        recorded = next(c for c in manifest["cases"] if c["case_id"] == case["case_id"])
        if commands_sha256 != recorded["commands_json_sha256"]:
            raise ValueError("recorder: blinded commands hash mismatch")
        identity["commands_sha256"] = commands_sha256
    else:
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
    if not blinded:
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
            "admission": "unsealed_stage_probe" if blinded else "registered" if registration is not None else "public_format_validation_only",
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
