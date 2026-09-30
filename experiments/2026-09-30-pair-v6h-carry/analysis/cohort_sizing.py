#!/usr/bin/env python3
"""UNSEALED draft: PR #286 endpoint-model prediction and exact binomial sizing.

Eval-only saved records; no workers, physics, plant refitting or model calls.
--capture reads 68 existing cB/rB/sB case/result pairs into a small audit input.
Subsequent --check uses that committed input and checks byte-identical outputs.
Run with OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1, using the existing venv.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODEL_DIR = ROOT / "experiments/2026-09-30-l1-axial-offset"
MODEL = MODEL_DIR / "analysis/predict_pass.py"
PLACEMENTS = HERE.parent / "placements_confirmatory_DRAFT.json"
SAVED = HERE / "sizing_20260930"
RAW = Path("/Users/changmin/projects/ugrp/outputs")
DRAWS, RNG_SEED = 3000, 20261001
ALPHA = .025  # lower endpoint of a two-sided exact 95% interval


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def capture():
    """Same X/Y observations as predict_pass.training; no least-squares plant fit."""
    manifest_path = MODEL_DIR / "results/raw_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    observations, sources = [], {}
    for label in ("cB", "rB", "sB"):
        cohort = RAW / manifest[label]["dir"]
        cases_path = cohort / "cases.jsonl"
        assert sha(cases_path) == manifest[label]["cases_jsonl_sha256"]
        sources[str(cases_path)] = sha(cases_path)
        for row in map(json.loads, cases_path.read_text().splitlines()):
            cid = row["case_id"].replace("@", "_").replace(":", "_").replace("/", "_")
            case_path, result_path = cohort / "cases" / cid / "case.json", cohort / "cases" / cid / "result.json"
            case, result = json.loads(case_path.read_text()), json.loads(result_path.read_text())
            legs = result["row"]["chain"]["legs"][:2]  # same L0/L1 slice as extract_legs.one_case
            assert len(legs) == 2 and all(leg["recorded"] for leg in legs)
            signed_y_mm = []
            for k in (0, 1):
                ends = [result["chain_raw"][rid]["leg_end"][str(k)] for rid in ("r1", "r2")]
                snap = max(ends, key=lambda end: end["sim_s"])
                signed_y_mm.append(1000 * (snap["gt"]["beam_xyz"][1] - .05))
            observations.append({"label": label, "cell": row["cell"], "seed": row["seed"],
                                 "case_id": row["case_id"], "beam_place": case["beam_xyyaw"],
                                 "signed_y_mm_L0_L1": signed_y_mm})
            sources[str(case_path)], sources[str(result_path)] = sha(case_path), sha(result_path)
    assert len(observations) == 68
    return {"scope": "eval_only: exact saved endpoint observations used by PR #286; not controller inputs",
            "manifest_sha256": sha(manifest_path), "raw_input_sha256": sources, "observations": observations}


def binomial_pmf(n, p):
    """Exact binomial recurrence in floating point, starting at the mode (no normal approximation)."""
    if p == 0:
        return [1.] + [0.] * n
    if p == 1:
        return [0.] * n + [1.]
    mode = int((n + 1) * p)
    values = [0.] * (n + 1)
    values[mode] = math.exp(math.lgamma(n + 1) - math.lgamma(mode + 1) - math.lgamma(n - mode + 1)
                            + mode * math.log(p) + (n - mode) * math.log1p(-p))
    for k in range(mode, n):
        values[k + 1] = values[k] * (n - k) / (k + 1) * p / (1 - p)
    for k in range(mode, 0, -1):
        values[k - 1] = values[k] * k / (n - k + 1) * (1 - p) / p
    assert abs(math.fsum(values) - 1.) < 1e-10
    return values


def tail(n, p, k):
    return math.fsum(binomial_pmf(n, p)[k:])


def mc_interval(successes, draws, alpha=.05):
    """Exact binomial interval for IID simulator draws, conditional on this model.

    This measures Monte Carlo sampling error, NOT model transfer or real risk.
    """
    if not 0 <= successes <= draws or draws <= 0:
        raise ValueError("invalid Monte Carlo counts")

    def inverse(k, target):
        lo, hi = 0., 1.
        for _ in range(60):
            mid = (lo + hi) / 2
            if tail(draws, mid, k) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = inverse(successes, alpha / 2) if successes else 0.
    upper = inverse(successes + 1, 1 - alpha / 2) if successes < draws else 1.
    lower_one_sided = inverse(successes, alpha) if successes else 0.
    prob = successes / draws
    return {"draws": draws, "gate_success_draws": successes, "gate_failure_draws": draws - successes,
            "plugin_mcse": math.sqrt(prob * (1 - prob) / draws),
            "gate_probability_exact95": [lower, upper],
            "gate_failure_probability_upper_one_sided95": 1 - lower_one_sided,
            "scope": "Monte Carlo sampling error conditional on model; not model transfer or physical safety risk"}


def critical_count(n):
    values, cumulative, minimum = binomial_pmf(n, .80), 0., n + 1
    for k in range(n, -1, -1):
        cumulative += values[k]
        if cumulative > ALPHA:
            break
        minimum = k
    return minimum


def minimum_n(p, target=.90):
    best_prior = 0.
    for n in range(1, 2001):
        k = critical_count(n)
        power = tail(n, p, k)
        if power >= target:
            assert best_prior < target
            return {"true_p": p, "target_power": target, "N": n, "minimum_pass": k,
                    "exact_power": power, "null_tail_p080": tail(n, .80, k),
                    "maximum_power_at_any_smaller_N": best_prior}
        best_prior = max(best_prior, power)
    raise ValueError("no N <= 2000 satisfies the specified power")


def checks():
    for p in (.65, .70, .75, .80, .85, .88, .90):
        for k in (48, 54, 55):
            direct = math.fsum(math.comb(60, j) * p**j * (1 - p)**(60 - j) for j in range(k, 61))
            assert abs(tail(60, p, k) - direct) < 1e-12
    assert critical_count(60) == 55  # 54/60 is insufficient for the exact lower bound too
    assert tail(60, .80, 54) > ALPHA >= tail(60, .80, 55)


def calculate(training):
    checks()
    spec = importlib.util.spec_from_file_location("pr286_predict", MODEL)
    pp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pp)
    observations = training["observations"]
    X = np.array([[1., math.degrees(r["beam_place"][2]), 1000 * (r["beam_place"][1] - .05)] for r in observations])
    Y = np.array([r["signed_y_mm_L0_L1"] for r in observations])
    keys = pp.unit_keys(observations)
    assert len(keys) == 68 and len(set(keys)) == 34
    b0, b1, residual = pp.fit_cross(X, Y[:, 0], Y[:, 1])
    # Independent published-model check: exactly the saved PR #286 fit.
    published_path = MODEL_DIR / "results/predict_pass.json"
    published = json.loads(published_path.read_text())["cross_model"]
    assert np.allclose(b0, published["L0"], atol=1e-10, rtol=0)
    assert np.allclose(b1, published["L1"], atol=1e-10, rtol=0)
    assert np.allclose(residual.std(0), published["resid_sd_mm"], atol=1e-10, rtol=0)
    placements = json.loads(PLACEMENTS.read_text())
    assert len(placements) == 60
    sx = np.array([pp.pm.sheet_of(p["x"]) for p in placements])
    dx = np.array([p["x"] for p in placements]) - sx
    feats = np.array([[1., p["yaw_deg"], 1000 * (p["y"] - .05)] for p in placements])
    variants = {"P0_without_axial_lag": next(v for v in pp.VARIANTS if v.startswith("P0 ")),
                "P1b_with_axial_lag": next(v for v in pp.VARIANTS if v.startswith("P1b "))}
    model_results, previous = {}, None
    for name, scale in (("P0_without_axial_lag", 1.), ("P1b_with_axial_lag", 1.),
                        ("P1b_lateral_x1.5", 1.5), ("P1b_lateral_x2", 2.)):
        variant = variants["P0_without_axial_lag" if name.startswith("P0") else "P1b_with_axial_lag"]
        along = pp.along_table(variant, sx, dx)
        # Same seed/draws across scenarios: paired sensitivity, monotonic count check.
        counts, probabilities = pp.simulate(along, feats, X, Y[:, 0], Y[:, 1], keys, DRAWS,
                                           np.random.default_rng(RNG_SEED), cross_scale=scale)
        if name.startswith("P1b"):
            if previous is not None:
                assert np.all(counts <= previous)
            previous = counts
        model_results[name] = {"lateral_error_scale": scale, "expected_pass_count": float(counts.mean()),
                               "expected_pass_fraction": float(counts.mean() / 60),
                               "P_ge_48": float((counts >= 48).mean()), "P_ge_55": float((counts >= 55).mean()),
                               "gate_mc_standard_error": {str(k): float(math.sqrt((counts >= k).mean() * (1 - (counts >= k).mean()) / DRAWS)) for k in (48, 55)},
                               "gate_mc_intervals": {str(k): mc_interval(int((counts >= k).sum()), DRAWS) for k in (48, 55)},
                               "count_p05_p50_p95": np.percentile(counts, [5, 50, 95]).tolist(),
                               "per_placement_pass_prob": dict(zip([p["name"] for p in placements], probabilities.tolist()))}
    return {"scope": "DRAFT: count criteria only; contact, sigma gates, setdown and hard-limit success not modeled",
            "input_sha256": {str(p.relative_to(ROOT)): sha(p) for p in (MODEL, MODEL.parent / "plant_model.py", PLACEMENTS, published_path,
                             MODEL_DIR / "results/raw_manifest.json", SAVED / "training_inputs.json")},
            "method": {"draws": DRAWS, "rng_seed": RNG_SEED, "bootstrap_unit": "placement (34), not PF seed (68 cases)",
                       "uncertainty": "shared tick phase, placement-bootstrap fit, paired L0/L1 residual bootstrap; P55 computed from counts",
                       "population_test": "Hypothetical IID design only (current placement draws are dependent): H0 p<=0.80; exact binomial tail <=0.025 (two-sided exact 95% lower confidence endpoint); power target 0.90"},
            "training": {"cases": 68, "placements": 34, "L0_coefficients": b0.tolist(), "L1_coefficients": b1.tolist(),
                         "residual_sd_mm": residual.std(0).tolist()},
            "model_scenarios": model_results,
            "constant_p_sensitivity": {str(p): {"expected_pass_count": 60 * p, "P_ge_48": tail(60, p, 48), "P_ge_55": tail(60, p, 55)} for p in (.88, .80)},
            "wilson95_lower_29_of_29": 29 / (29 + 1.96**2),
            "population_sizing": [minimum_n(p) for p in (.88, .85, .90)],
            "checks": "binomial recurrence vs direct combinatorial sum <1e-12; 54/60 fails exact lower-bound gate, 55/60 passes; published fit reproduced <1e-10; lateral scaling monotonic; all smaller N searched"}


def report(result):
    lines = ["# 확증 코호트 수치 확인 (DRAFT, 2026-09-30)", "",
             "기존 기록만 사용한 조건부 예측이다. 물리·모델 호출·봉인·등록 0회. 기본은 60곳, 관측 기준 48/60이다.", "",
             "| 조건 | 기대 통과 수 / 60 | P(≥48/60) | P(≥55/60) |", "|---|---:|---:|---:|"]
    for name, item in {**result["model_scenarios"], **{f"constant p={p} (exact binomial)": v for p, v in result["constant_p_sensitivity"].items()}}.items():
        lines.append(f"| {name} | {item['expected_pass_count']:.3f} | {item['P_ge_48']:.6f} | {item['P_ge_55']:.6f} |")
    lines += ["", "모형 행: PR #286 simulate를 3,000회, 시드 20261001로 조건마다 재시작했다(짝지은 민감도). 독립 동일확률 이항으로 평균 통과율을 대입하지 않았다.",
              "기존 모형의 ≥54 출력 대신 ≥55를 원래 통과 수에서 계산했다. 횡 오차 배율은 평균과 잔차를 함께 배율 조정한다.",
              "p=0.88/0.80 행: 모든 배치의 참 통과확률이 같은 독립 이항이라는 검증되지 않은 설계 가정이며 실제 참값의 추정/보장은 아니다.",
              f"29/29의 Wilson 95% 하한(z=1.96)은 {result['wilson95_lower_29_of_29']:.9f}; 명목 하한이다. 29 구성은 26개 좌표/20개 근접 연결 묶음이고, p=0.88의 보수성은 보증되지 않았다.", "",
              "| 모집단 주장 설계의 참 p 가정 | 최소 N | 최소 통과 수 | 정확 검정력 | p=0.80에서 꼬리 확률 | 모든 더 작은 N의 최대 검정력 |", "|---|---:|---:|---:|---:|---:|"]
    for item in result["population_sizing"]:
        lines.append(f"| {item['true_p']} | {item['N']} | {item['minimum_pass']} | {item['exact_power']:.6f} | {item['null_tail_p080']:.6f} | {item['maximum_power_at_any_smaller_N']:.6f} |")
    lines += ["", "현재 생성기는 앞서 채택한 배치와 근접한 추첨도 거부해 독립 동일분포 추출이 아니다. 현재 Wilson/이항 수치는 명목 구간과 설계 민감도로만 읽는다.",
              "MC 구간은 모형에 조건부인 모의 추출 오차다. 실제 안전 위험이나 모형 전이 오차 구간이 아니다.",
              "| 모형 | 문턱 | 성공/실패 draw | 모형 내부 확률의 정확 95% 구간 | 실패 확률 단측 95% 상한 |",
              "|---|---:|---:|---:|---:|"]
    for name, item in result["model_scenarios"].items():
        for k, mc in item["gate_mc_intervals"].items():
            lo, hi = mc["gate_probability_exact95"]
            lines.append(f"| {name} | {k} | {mc['gate_success_draws']}/{mc['gate_failure_draws']} | [{lo:.6f}, {hi:.6f}] | {mc['gate_failure_probability_upper_one_sided95']:.6f} |")
    lines += ["", "권장(별도 결정): 참 p=0.88, 양측 정확 95% 구간의 하한>0.80, 검정력≥90%라면 N=225 및 ≥192/225.",
              "p=0.85를 설계 가정으로 잡으면 N=619 및 ≥515/619. p=0.80에서는 모든 N의 검정력이≤0.025라 표본 수만으로 90%를 얻을 수 없다.",
              "고정된 현재 60곳의 모형 예측을 확대된 모집단 표본의 검정력으로 외삽하지 않는다. 독립·동일분포 배치 설계/대표성은 별도로 확정해야 한다.", "",
              "재현: analysis/cohort_sizing.py --check. 원본 출처·해시는 training_inputs.json, 모형·배치 파일 해시와 계산 검사는 cohort_sizing.json에 기록했다.",
              "원본 물리 코호트 결과는 기존 TensorBoard 키 b_v6h_axial_lag_20260930을 참조하며 이번 수치 설계는 새 실험이 아니어서 변환·재개방하지 않았다."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=HERE / "sizing_review_20260930",
                        help="new outputs; historic sizing_20260930 remains unchanged")
    args = parser.parse_args()
    if args.capture and args.check:
        parser.error("--capture and --check are mutually exclusive")
    started = time.process_time()
    if args.capture:
        captured = capture()
        SAVED.mkdir(exist_ok=False)
        (SAVED / "training_inputs.json").write_text(encoded(captured))
    training = json.loads((SAVED / "training_inputs.json").read_text())
    result = calculate(training)
    if not args.check:
        args.output.mkdir(exist_ok=False, parents=True)
    for name, content in (("cohort_sizing.json", encoded(result)), ("COHORT_SIZING.md", report(result))):
        path = args.output / name
        if args.check:
            assert path.read_text() == content, f"saved output changed: {path}"
        else:
            with path.open("x") as stream:
                stream.write(content)
    print(f"{'CHECK PASS' if args.check else 'WROTE'}: model fit, 60 placements, four model scenarios, two exact sensitivities, minimum N; CPU {time.process_time() - started:.2f}s")


if __name__ == "__main__":
    main()
