#!/usr/bin/env python3
"""Burst probe and endpoint catalog for planner LLM alternatives (2026-10-16 llmalt).

Reproduces the 2026-10-14 planner provider probe method:
- 40 stored real planner requests (first 40 of off-calls.jsonl) + 1 stored own-RGB jpg
- Sent at ~40 calls/min (1 submit every 1.5 s, 6 workers, temperature=0, max_tokens=300)
- Provider tag pinned, allow_fallbacks=False
- Reads OpenRouter API key only in-process from macOS Keychain (never printed or saved)
- Checks balance >= $1.50 before starting and enforces hard total spend cap <= $1.00
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import datetime
import hashlib
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
SRC_CALLS = Path(
    "/Users/changmin/projects/ugrp-wt/e2e18-planner/outputs/task-planner-ling-vl-main-20261013/off-calls.jsonl"
)
STORED_GEMMA_ZST = Path(
    "/Users/changmin/projects/ugrp-wt/e2e18-planner/outputs/task-planner-gemma-json-20261014/off-calls.jsonl.zst"
)
IMG_PATH = Path(
    "/Users/changmin/projects/ugrp-wt/e2e18-planner/outputs/task-planner-ling-vl-image/r80-r1-00000.jpg"
)

N_CALLS = 40
WORKERS = 6
SPACING_S = 1.5
MIN_BALANCE_USD = 1.50
MAX_SPEND_USD = 1.00

# r4 Gemma planner reference ledger medians (AGENTS.md: 3,556 calls, prompt med 4,917, compl med 61, cache ratio 26%)
R4_PROMPT_MED = 4917
R4_COMPL_MED = 61
R4_CACHE_RATIO = 0.26

CATALOG_MODELS = [
    "google/gemma-4-31b-it",
    "google/gemma-4-26b-a4b-it",
    "google/gemma-3-27b-it",
    "google/gemma-3-12b-it",
    "mistralai/mistral-small-3.2-24b-instruct",
    "mistralai/mistral-small-3.1-24b-instruct",
    "qwen/qwen3-vl-30b-a3b-instruct",
    "qwen/qwen3-vl-235b-a22b-instruct",
    "qwen/qwen3-vl-8b-instruct",
    "qwen/qwen3.5-35b-a3b",
    "qwen/qwen3.6-35b-a3b",
    "qwen/qwen3.5-9b",
    "meta-llama/llama-4-scout",
    "meta-llama/llama-4-maverick",
    "inclusionai/ling-3.0-flash-vl",
    "deepseek/deepseek-v4.1-flash",
    "nvidia/nemotron-3.5-super-vl",
    "z-ai/glm-4.6v",
]

# Baseline + 6 top candidates to measure at ~40 calls/min
PROBE_TARGETS = [
    {
        "role": "baseline_now",
        "model": "google/gemma-4-31b-it",
        "tag": "deepinfra/turbo",
        "provider_name": "DeepInfra",
        "quantization": "fp4",
    },
    {
        "role": "candidate_a1",
        "model": "google/gemma-4-31b-it",
        "tag": "coreweave/fp4",
        "provider_name": "CoreWeave",
        "quantization": "fp4",
    },
    {
        "role": "candidate_a2",
        "model": "google/gemma-4-31b-it",
        "tag": "chutes/fp4",
        "provider_name": "Chutes",
        "quantization": "fp4",
    },
    {
        "role": "candidate_a3",
        "model": "google/gemma-4-31b-it",
        "tag": "parasail/fp8",
        "provider_name": "Parasail",
        "quantization": "fp8",
    },
    {
        "role": "candidate_b1",
        "model": "google/gemma-4-26b-a4b-it",
        "tag": "nextbit/bf16",
        "provider_name": "NextBit",
        "quantization": "bf16",
    },
    {
        "role": "candidate_b2",
        "model": "mistralai/mistral-small-3.2-24b-instruct",
        "tag": "deepinfra/fp8",
        "provider_name": "DeepInfra",
        "quantization": "fp8",
    },
    {
        "role": "candidate_b3",
        "model": "meta-llama/llama-4-scout",
        "tag": "deepinfra/fp8",
        "provider_name": "DeepInfra",
        "quantization": "fp8",
    },
]


def read_key() -> str:
    res = subprocess.run(
        ["security", "find-generic-password", "-s", "ugrp-openrouter", "-a", "openrouter", "-w"],
        capture_output=True,
        text=True,
        check=True,
    )
    key = res.stdout.strip()
    if not key:
        raise RuntimeError("Empty OpenRouter key from Keychain")
    return key


def check_balance(key: str) -> dict:
    out = {}
    for name, path in [("credits", "/api/v1/credits"), ("key", "/api/v1/key")]:
        req = urllib.request.Request(
            "https://openrouter.ai" + path,
            headers={"Authorization": "Bearer " + key},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r).get("data", {})
        out[name] = {
            k: v
            for k, v in data.items()
            if k not in ("label", "key", "hash", "creator_user_id", "workspace_id", "organization_id")
        }
    credits_rem = float(out["credits"]["total_credits"]) - float(out["credits"]["total_usage"])
    key_rem = float(out["key"]["limit_remaining"])
    out["credits_remaining_usd"] = round(credits_rem, 6)
    out["key_remaining_usd"] = round(key_rem, 6)
    return out


def probe_image_filter(key: str, model_id: str, img_data_url: str) -> dict:
    body = {
        "model": model_id,
        "max_tokens": 1,
        "provider": {"order": ["__nonexistent_provider_probe__"], "allow_fallbacks": False},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "ping"},
                    {"type": "image_url", "image_url": {"url": img_data_url}},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=20)
        return {"raw_message": "unexpected_200", "image_removed": [], "image_supported": []}
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf8", "replace")).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        img_removed = []
        img_supported = []
        if "Every candidate endpoint was removed during routing:" in msg:
            part = msg.split("Every candidate endpoint was removed during routing:", 1)[1].strip().rstrip(".")
            for clause in part.split(";"):
                clause = clause.strip()
                if clause.startswith("Filter by Image Support removed "):
                    items = clause.replace("Filter by Image Support removed ", "").split(",")
                    img_removed = [x.strip() for x in items if x.strip()]
                elif clause.startswith("Filter by Fallback removed "):
                    items = clause.replace("Filter by Fallback removed ", "").split(",")
                    img_supported = [x.strip() for x in items if x.strip()]
        return {
            "http_status": e.code,
            "raw_message": msg,
            "image_removed_tags": img_removed,
            "image_supported_tags": img_supported,
        }


def build_catalog(key: str, img_data_url: str) -> dict:
    models_out = []
    for mid in CATALOG_MODELS:
        with urllib.request.urlopen(f"https://openrouter.ai/api/v1/models/{mid}/endpoints", timeout=30) as r:
            data = json.load(r)["data"]
        filt = probe_image_filter(key, mid, img_data_url)
        removed_set = set(filt.get("image_removed_tags", []))
        supported_set = set(filt.get("image_supported_tags", []))
        eps_out = []
        for ep in data.get("endpoints", []):
            p = ep.get("pricing") or {}
            pr = round(float(p.get("prompt") or 0) * 1e6, 6)
            co = round(float(p.get("completion") or 0) * 1e6, 6)
            ca = round(float(p["input_cache_read"]) * 1e6, 6) if p.get("input_cache_read") is not None else None
            tag = ep.get("tag")
            sp = ep.get("supported_parameters") or []
            if tag in removed_set:
                img_ok = False
            elif tag in supported_set:
                img_ok = True
            else:
                img_ok = None
            # Calculate reference r4 call cost (4917 prompt, 61 completion)
            cost_r4_no_cache = (R4_PROMPT_MED * pr + R4_COMPL_MED * co) / 1e6
            eff_cache_price = ca if ca is not None else pr
            cost_r4_26pct_cache = (
                R4_PROMPT_MED * ((1.0 - R4_CACHE_RATIO) * pr + R4_CACHE_RATIO * eff_cache_price)
                + R4_COMPL_MED * co
            ) / 1e6
            eps_out.append(
                {
                    "provider_name": ep.get("provider_name"),
                    "tag": tag,
                    "quantization": ep.get("quantization"),
                    "context_length": ep.get("context_length"),
                    "max_completion_tokens": ep.get("max_completion_tokens"),
                    "status": ep.get("status"),
                    "uptime_last_30m": ep.get("uptime_last_30m"),
                    "supports_implicit_caching": ep.get("supports_implicit_caching"),
                    "supports_response_format": "response_format" in sp,
                    "supports_structured_outputs": "structured_outputs" in sp,
                    "supports_image_routing": img_ok,
                    "usd_per_million": {
                        "prompt": pr,
                        "completion": co,
                        "input_cache_read": ca,
                    },
                    "r4_ledger_est_usd_per_call": {
                        "no_cache": round(cost_r4_no_cache, 7),
                        "cache_26pct": round(cost_r4_26pct_cache, 7),
                    },
                }
            )
        models_out.append(
            {
                "id": mid,
                "name": data.get("name"),
                "context_length": data.get("context_length"),
                "image_routing_probe": filt,
                "endpoints": eps_out,
            }
        )
    return {
        "schema": "ugrp.llmalt_endpoints_catalog.v1",
        "fetched_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "r4_reference_tokens": {
            "prompt_median": R4_PROMPT_MED,
            "completion_median": R4_COMPL_MED,
            "cache_ratio": R4_CACHE_RATIO,
        },
        "models": models_out,
    }


def parse_json_decision(txt: str):
    if not txt:
        return False, None
    try:
        s = txt[txt.index("{") : txt.rindex("}") + 1]
        obj = json.loads(s)
        if isinstance(obj, dict) and isinstance(obj.get("act"), str) and obj.get("act"):
            return True, obj
        return False, None
    except Exception:
        return False, None


def call_one(key: str, model: str, tag: str, req_idx: int, item: dict, img_data_url: str, img_sha256: str, ep_price: dict) -> dict:
    q = item["request"]
    user_text = json.dumps(q["input"])
    req_sha256 = hashlib.sha256(
        json.dumps({"system": q["system"], "input": q["input"], "image_sha256": img_sha256}, sort_keys=True).encode()
    ).hexdigest()
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 300,
        "usage": {"include": True},
        "provider": {"order": [tag], "allow_fallbacks": False},
        "messages": [
            {"role": "system", "content": q["system"]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": img_data_url}},
                ],
            },
        ],
    }
    r = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        raw_bytes = urllib.request.urlopen(r, timeout=60).read()
        wall = time.time() - t0
        d = json.loads(raw_bytes)
        msg = (d.get("choices") or [{}])[0].get("message") or {}
        txt = msg.get("content") or ""
        valid, parsed = parse_json_decision(txt)
        u = d.get("usage") or {}
        ptok = int(u.get("prompt_tokens") or 0)
        otok = int(u.get("completion_tokens") or 0)
        ctok = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        rtok = int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        rep_cost = float(u.get("cost") or 0.0)
        pr_rate = ep_price["prompt"]
        co_rate = ep_price["completion"]
        ca_rate = ep_price["input_cache_read"] if ep_price["input_cache_read"] is not None else pr_rate
        formula_cost = ((ptok - ctok) * pr_rate + ctok * ca_rate + otok * co_rate) / 1e6
        return {
            "req_index": req_idx,
            "case_id": item["case_id"],
            "condition": item["condition"],
            "domain": item["domain"],
            "request_sha256": req_sha256,
            "image_sha256": img_sha256,
            "status": 200,
            "wall_s": round(wall, 4),
            "over_8s": wall > 8.0,
            "valid_json": valid,
            "parsed_act": parsed.get("act") if parsed else None,
            "parsed_args": parsed.get("args") if parsed else None,
            "parsed_message": parsed.get("message") if parsed else None,
            "parsed_reason": parsed.get("reason") if parsed else None,
            "raw_text": txt,
            "prompt_tokens": ptok,
            "completion_tokens": otok,
            "cached_tokens": ctok,
            "reasoning_tokens": rtok,
            "reported_cost_usd": round(rep_cost, 8),
            "formula_cost_usd": round(formula_cost, 8),
            "provider_returned": d.get("provider"),
            "model_returned": d.get("model"),
        }
    except urllib.error.HTTPError as e:
        wall = time.time() - t0
        err_txt = e.read()[:400].decode("utf8", "replace")
        return {
            "req_index": req_idx,
            "case_id": item["case_id"],
            "condition": item["condition"],
            "domain": item["domain"],
            "request_sha256": req_sha256,
            "image_sha256": img_sha256,
            "status": e.code,
            "wall_s": round(wall, 4),
            "over_8s": wall > 8.0,
            "valid_json": False,
            "parsed_act": None,
            "parsed_args": None,
            "parsed_message": None,
            "parsed_reason": None,
            "raw_text": None,
            "error_body": err_txt,
            "prompt_tokens": None,
            "completion_tokens": None,
            "cached_tokens": None,
            "reasoning_tokens": None,
            "reported_cost_usd": 0.0,
            "formula_cost_usd": 0.0,
            "provider_returned": None,
            "model_returned": None,
        }
    except Exception as e:
        wall = time.time() - t0
        return {
            "req_index": req_idx,
            "case_id": item["case_id"],
            "condition": item["condition"],
            "domain": item["domain"],
            "request_sha256": req_sha256,
            "image_sha256": img_sha256,
            "status": "ERR",
            "wall_s": round(wall, 4),
            "over_8s": wall > 8.0,
            "valid_json": False,
            "parsed_act": None,
            "parsed_args": None,
            "parsed_message": None,
            "parsed_reason": None,
            "raw_text": None,
            "error_body": repr(e)[:300],
            "prompt_tokens": None,
            "completion_tokens": None,
            "cached_tokens": None,
            "reasoning_tokens": None,
            "reported_cost_usd": 0.0,
            "formula_cost_usd": 0.0,
            "provider_returned": None,
            "model_returned": None,
        }


def main() -> int:
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    key = read_key()
    bal_before = check_balance(key)
    print("Balance before:", json.dumps(bal_before), flush=True)
    if bal_before["credits_remaining_usd"] < MIN_BALANCE_USD or bal_before["key_remaining_usd"] < MIN_BALANCE_USD:
        raise RuntimeError(f"OpenRouter balance below ${MIN_BALANCE_USD}: {bal_before}")

    img_bytes = IMG_PATH.read_bytes()
    img_sha256 = hashlib.sha256(img_bytes).hexdigest()
    img_data_url = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()

    src_sha256 = hashlib.sha256(SRC_CALLS.read_bytes()).hexdigest()
    stored_gemma_sha256 = hashlib.sha256(STORED_GEMMA_ZST.read_bytes()).hexdigest()

    reqs = []
    with SRC_CALLS.open() as f:
        for line in f:
            row = json.loads(line)
            reqs.append(
                {
                    "case_id": row["case_id"],
                    "condition": row["condition"],
                    "domain": row["domain"],
                    "rule_choice": row.get("rule_choice"),
                    "request": row["audit"][0]["request"],
                }
            )
            if len(reqs) == N_CALLS:
                break

    zst_out = subprocess.check_output(["zstd", "-dc", str(STORED_GEMMA_ZST)]).decode()
    stored_gemma_rows = [json.loads(l) for l in zst_out.splitlines() if l.strip()][:N_CALLS]
    stored_gemma_acts = []
    for a, b in zip(reqs, stored_gemma_rows):
        if a["case_id"] != b["case_id"] or a["condition"] != b["condition"]:
            raise RuntimeError("Mismatch between off-calls.jsonl and stored Gemma JSON ledger")
        dec = b["audit"][0].get("decision") or {}
        stored_gemma_acts.append(dec.get("act"))

    print("Building endpoints catalog...", flush=True)
    catalog = build_catalog(key, img_data_url)
    (EXP_DIR / "endpoints_catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")

    # Lookup official pricing from catalog
    price_map = {}
    for m in catalog["models"]:
        for ep in m["endpoints"]:
            price_map[(m["id"], ep["tag"])] = ep["usd_per_million"]

    raw_path = EXP_DIR / "raw_responses.jsonl"
    all_target_rows = {}
    cum_spend = 0.0

    with raw_path.open("w") as rf:
        for t in PROBE_TARGETS:
            if cum_spend >= MAX_SPEND_USD:
                raise RuntimeError(f"Hard spend cap ${MAX_SPEND_USD} reached: {cum_spend}")
            model = t["model"]
            tag = t["tag"]
            ep_price = price_map[(model, tag)]
            print(f"Probing {model} @ {tag} (40 calls at 1.5s spacing)...", flush=True)
            t_start = time.time()
            futs = []
            with cf.ThreadPoolExecutor(WORKERS) as ex:
                for idx, item in enumerate(reqs):
                    futs.append(ex.submit(call_one, key, model, tag, idx, item, img_data_url, img_sha256, ep_price))
                    if idx < len(reqs) - 1:
                        time.sleep(SPACING_S)
                res = [fut.result() for fut in futs]
            elapsed_batch = time.time() - t_start
            for r in res:
                row_out = {
                    "role": t["role"],
                    "model": model,
                    "provider_tag": tag,
                    "provider_name": t["provider_name"],
                    "quantization": t["quantization"],
                    **r,
                }
                rf.write(json.dumps(row_out, ensure_ascii=False) + "\n")
            rf.flush()
            batch_cost = sum(x["reported_cost_usd"] for x in res)
            cum_spend += batch_cost
            all_target_rows[(model, tag)] = (t, ep_price, res, elapsed_batch)
            ok_cnt = sum(x["status"] == 200 for x in res)
            valid_cnt = sum(x["valid_json"] for x in res)
            c429 = sum(x["status"] == 429 for x in res)
            print(
                f"  -> done in {elapsed_batch:.1f}s: ok={ok_cnt}/40 valid={valid_cnt}/40 429={c429} cost=${batch_cost:.5f} cum=${cum_spend:.5f}",
                flush=True,
            )

    bal_after = check_balance(key)
    print("Balance after:", json.dumps(bal_after), flush=True)

    # Extract live baseline acts (google/gemma-4-31b-it @ deepinfra/turbo)
    base_res = all_target_rows[("google/gemma-4-31b-it", "deepinfra/turbo")][2]
    live_gemma_acts = [x["parsed_act"] for x in base_res]

    results_summary = []
    for (model, tag), (t, ep_price, res, elapsed_batch) in all_target_rows.items():
        oks = [x for x in res if x["status"] == 200]
        valids = [x for x in oks if x["valid_json"]]
        walls = [x["wall_s"] for x in oks]
        over8 = sum(1 for x in oks if x["over_8s"])
        c429 = sum(1 for x in res if x["status"] == 429)
        other_err = sum(1 for x in res if x["status"] not in (200, 429))

        tot_prompt = sum(x["prompt_tokens"] or 0 for x in oks)
        tot_cached = sum(x["cached_tokens"] or 0 for x in oks)
        tot_compl = sum(x["completion_tokens"] or 0 for x in oks)
        rep_cost_total = sum(x["reported_cost_usd"] for x in oks)
        form_cost_total = sum(x["formula_cost_usd"] for x in oks)

        match_live_act = sum(
            1
            for i, x in enumerate(res)
            if x["valid_json"] and live_gemma_acts[i] is not None and x["parsed_act"] == live_gemma_acts[i]
        )
        match_stored_act = sum(
            1
            for i, x in enumerate(res)
            if x["valid_json"] and stored_gemma_acts[i] is not None and x["parsed_act"] == stored_gemma_acts[i]
        )

        pr = ep_price["prompt"]
        co = ep_price["completion"]
        ca = ep_price["input_cache_read"] if ep_price["input_cache_read"] is not None else pr
        r4_cost_0cache = (R4_PROMPT_MED * pr + R4_COMPL_MED * co) / 1e6
        r4_cost_26cache = (
            R4_PROMPT_MED * ((1.0 - R4_CACHE_RATIO) * pr + R4_CACHE_RATIO * ca) + R4_COMPL_MED * co
        ) / 1e6

        s = {
            "role": t["role"],
            "model": model,
            "provider_name": t["provider_name"],
            "provider_tag": tag,
            "quantization": t["quantization"],
            "official_usd_per_million": ep_price,
            "n": len(res),
            "ok_http200": len(oks),
            "valid_json_act": len(valids),
            "http429": c429,
            "other_err": other_err,
            "latency_med_s": round(statistics.median(walls), 2) if walls else None,
            "latency_p90_s": round( sorted(walls)[int(0.9 * (len(walls) - 1))], 2) if walls else None,
            "latency_max_s": round(max(walls), 2) if walls else None,
            "over_8s_count": over8,
            "prompt_tokens_med": statistics.median([x["prompt_tokens"] for x in oks]) if oks else None,
            "completion_tokens_med": statistics.median([x["completion_tokens"] for x in oks]) if oks else None,
            "cache_ratio": round(tot_cached / max(1, tot_prompt), 4) if oks else 0.0,
            "probe_total_reported_cost_usd": round(rep_cost_total, 6),
            "probe_reported_cost_per_ok_call_usd": round(rep_cost_total / len(oks), 6) if oks else None,
            "probe_formula_cost_per_ok_call_usd": round(form_cost_total / len(oks), 6) if oks else None,
            "r4_ledger_formula_cost_per_call_usd": {
                "no_cache_4917in_61out": round(r4_cost_0cache, 6),
                "cache_26pct_4917in_61out": round(r4_cost_26cache, 6),
            },
            "act_agreement_vs_gemma31b_deepinfra_live_img": {
                "matched": match_live_act,
                "total": N_CALLS,
                "ratio": round(match_live_act / N_CALLS, 4),
                "note": "act field agreement only; NOT task accuracy",
            },
            "act_agreement_vs_gemma31b_deepinfra_stored_v405": {
                "matched": match_stored_act,
                "total": N_CALLS,
                "ratio": round(match_stored_act / N_CALLS, 4),
                "note": "act field agreement only; NOT task accuracy",
            },
            "err_sample": next((x.get("error_body") for x in res if x["status"] != 200), None),
        }
        results_summary.append(s)

    # Also compute old vs new baseline for Gemma 4 31B @ DeepInfra
    old_pr, old_co, old_ca = 0.09, 0.34, 0.05
    new_pr, new_co, new_ca = 0.135, 0.51, 0.075
    gemma_price_comparison = {
        "model": "google/gemma-4-31b-it",
        "provider_tag": "deepinfra/turbo",
        "quantization": "fp4",
        "old_usd_per_million": {"prompt": old_pr, "completion": old_co, "input_cache_read": old_ca},
        "new_usd_per_million": {"prompt": new_pr, "completion": new_co, "input_cache_read": new_ca},
        "r4_ledger_4917in_61out_0pct_cache": {
            "old_usd_per_call": round((R4_PROMPT_MED * old_pr + R4_COMPL_MED * old_co) / 1e6, 6),
            "new_usd_per_call": round((R4_PROMPT_MED * new_pr + R4_COMPL_MED * new_co) / 1e6, 6),
        },
        "r4_ledger_4917in_61out_26pct_cache": {
            "old_usd_per_call": round(
                (R4_PROMPT_MED * ((1 - R4_CACHE_RATIO) * old_pr + R4_CACHE_RATIO * old_ca) + R4_COMPL_MED * old_co)
                / 1e6,
                6,
            ),
            "new_usd_per_call": round(
                (R4_PROMPT_MED * ((1 - R4_CACHE_RATIO) * new_pr + R4_CACHE_RATIO * new_ca) + R4_COMPL_MED * new_co)
                / 1e6,
                6,
            ),
        },
    }

    summary_doc = {
        "schema": "ugrp.experiment_summary.v1",
        "id": "2026-10-16-llmalt",
        "date": "2026-10-16",
        "purpose": "Measure open-weight vision LLM alternatives after Gemma 4 31B @DeepInfra +50% price increase alert (prompt 0.09->0.135, completion 0.34->0.51, cache 0.05->0.075 $/M). Measurement and recommendation only; configs/model_endpoints.json unchanged.",
        "host": "Mac (OpenRouter API calls only; no simulation, physics, rendering, or GUI)",
        "method": "Reproduced 2026-10-14 rate_probe.py: first 40 stored planner requests from outputs/task-planner-ling-vl-main-20261013/off-calls.jsonl + 1 stored own-RGB jpg (r80-r1-00000.jpg), 1 submit every 1.5 s (~40/min), 6 workers, temperature=0, max_tokens=300, provider tag pinned, allow_fallbacks=False. valid_json_act = response parses as JSON with non-empty act field. act_agreement compares chosen act against Gemma 4 31B @DeepInfra (NOT task accuracy).",
        "inputs": {
            "requests_source": str(SRC_CALLS),
            "requests_source_sha256": src_sha256,
            "stored_gemma_reference": str(STORED_GEMMA_ZST),
            "stored_gemma_reference_sha256": stored_gemma_sha256,
            "image_source": str(IMG_PATH),
            "image_sha256": img_sha256,
            "image_bytes": len(img_bytes),
        },
        "balance_check": {
            "min_required_usd": MIN_BALANCE_USD,
            "max_spend_cap_usd": MAX_SPEND_USD,
            "before": bal_before,
            "after": bal_after,
            "total_probe_reported_cost_usd": round(cum_spend, 6),
        },
        "gemma_31b_deepinfra_price_increase_impact": gemma_price_comparison,
        "results": results_summary,
    }
    (EXP_DIR / "summary.json").write_text(json.dumps(summary_doc, indent=2, ensure_ascii=False) + "\n")
    print("Wrote summary.json and raw_responses.jsonl successfully.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
