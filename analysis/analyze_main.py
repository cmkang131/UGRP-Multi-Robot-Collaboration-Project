#!/usr/bin/env python3
"""Main-experiment analysis (standard library only; offline; no simulation, no LLM calls).

Pre-registered analysis of prereg/PREREG.md sections 2-4 and 7, plus the body tables of the design review:
cell table (arm x scene x structure x rep), scene-level paired exact sign tests with Holm,
bootstrap CI over scenes, shortfall decomposition against the oracle-plan baseline,
plan-failure vs physical-failure split, and condition (ablation / full-information / ...) comparisons.

  analyze_main.py --runs DIR [--runs DIR ...] --scenes F [--scenes F ...] [--brain ROOT ...]
                  [--manifest CSV ...] --name NAME [--interim] [--reps N] [--main-group mainA]

Run folders: a batch results folder (index.csv + <run_id>/{team.json,out-rK,brain/,meta.json}, see
batch/collect.py) or a legacy evidence-style folder (t<0|1|2>-<scene>-<bundle>/team.json, brain
records under --brain ROOT/<name>/). Output: out/<NAME>/{summary.md,cells.csv,tests.json}.
"""
import argparse
import csv
import itertools
import json
import math
import random
import re
import sys
import tempfile
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import median

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import causes  # noqa: E402
import compare  # noqa: E402

SEED = 2026111522          # PREREG section 4 (DS/DESIGN-STRENGTHEN.md:38)
BOOTS = 10000
ALPHA = 0.05
STRUCTS = ("T0", "T1", "T2")
MODES = ("zero", "drop", "one")
MODE_TEXT = {"zero": "실패 칸 = 0 (기본, PREREG 7절)", "drop": "실패 칸 제외 (민감도)", "one": "실패 칸 = 1 (민감도)"}
# 메시지 벌점 점수 SP (PREREG 2절): SP = max(0, C - lambda * max(0, M - 2R)). 사용자 문구의 "S" 이며, 물리 성공 S 와 구분하려고 SP 로 쓴다.
PENALTY_ALLOWANCE = 2          # 로봇당 허용 메시지 수. 허용 = 2R
PENALTY_LAMBDAS = {"SP05": Fraction(1, 20), "SP02": Fraction(1, 50), "SP10": Fraction(1, 10)}   # SP02 = 기본(2026-11-16 09:4x 메인, 사용자 위임), 나머지 민감도
PENALTY_PRIMARY = "SP02"
METRICS = ("C", "G", "S") + tuple(PENALTY_LAMBDAS)
METRIC_TEXT = {"C": "계획 덮임 C (주)", "G": "근거 있는 덮임 G (보조)", "S": "물리 성공 S (보조)",
               "SP05": "메시지 벌점 점수 SP, λ=0.05 (민감도)", "SP02": "메시지 벌점 점수 SP, λ=0.02 (주, 통신 비용 반영)",
               "SP10": "메시지 벌점 점수 SP, λ=0.10 (민감도)"}
CONTRASTS = (("T0", "T1"), ("T0", "T2"))
# 2026-11-16 03:1x KST (PREREG 4절): the verdict on SP is the scene-level mean difference with its scene-bootstrap 95% interval;
# the exact sign test stays the verdict for C only (it measures a message-count threshold for SP, REVIEW-3 section 4).
CI_VERDICT_METRICS = tuple(PENALTY_LAMBDAS)
CAUSE_ROWS = ("no_info_T0", "ignored", "late", "not_sent", "guess_wrong", "dropped_needed", "other", "fault")
CAUSE_TEXT = {"no_info_T0": "정보 없음(T0)", "ignored": "받고 무시", "late": "늦게 도착", "not_sent": "안 보냄",
              "guess_wrong": "추측 틀림", "dropped_needed": "필요한 상자 내려놓음", "other": "기타", "fault": "고장/미완료(꼬리표 없음)"}
GROUNDED_CLASSES = ("message_grounded", "own_only")
# 내려놓음(put_down) 분류 열(칸별 개수). causes.classify_put_downs: decoy / duplicate / lost(own_order, team_only, unknown) / 색 불명
PUT_COLUMNS = ("put_decoy", "put_duplicate", "put_lost_own", "put_lost_team", "put_lost_unknown", "put_unknown")
COMMON_ARGS = "--robot-tags --overhead --regrasp-max 1"
ORACLE = "ORACLE"


# ------------------------------------------------------------------ statistics
def penalized(cover, messages, robots, lam):
    """SP = max(0, C - lam * max(0, M - 2R)), exact (Fraction). messages is None -> None (unknown, never read as 0)."""
    if cover is None or messages is None:
        return None
    return max(Fraction(0), cover - Fraction(lam) * max(0, messages - PENALTY_ALLOWANCE * robots))


def sign_test_p(k, m):
    """Two-sided exact sign test: k positives among m non-tied scenes. m=0 -> 1."""
    if m == 0:
        return 1.0
    tail = sum(math.comb(m, i) for i in range(min(k, m - k) + 1))
    return min(1.0, 2 * tail / 2 ** m)


def holm(pvalues, alpha=ALPHA):
    """Holm step-down. Smallest p is compared with alpha/n, then alpha/(n-1), ...; stops at the first miss.
    reject uses p <= threshold (same as adjusted p <= alpha)."""
    n = len(pvalues)
    order = sorted(range(n), key=lambda i: (pvalues[i], i))
    out, running, stopped = [None] * n, 0.0, False
    for rank, i in enumerate(order):
        threshold = alpha / (n - rank)
        running = max(running, min(1.0, (n - rank) * pvalues[i]))
        reject = (not stopped) and pvalues[i] <= threshold
        stopped = stopped or not reject
        out[i] = {"p": pvalues[i], "adj_p": running, "threshold": threshold, "reject": reject}
    return out


def percentile(sorted_values, q):
    """Linear interpolation between order statistics (numpy default): position q*(n-1)."""
    if not sorted_values:
        return None
    position = q * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


_CI_CACHE = {}


def bootstrap_ci(values, boots=BOOTS, seed=SEED, level=0.95):
    """Percentile CI of the mean; scenes resampled with replacement. Callers pass values ordered by scene id.
    A fresh Random(seed) per call, so a result never depends on which other tests ran first."""
    n = len(values)
    if n == 0:
        return None
    key = (tuple(values), boots, seed, level)
    if key not in _CI_CACHE:
        rng = random.Random(seed)
        means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(boots))
        tail = (1 - level) / 2
        _CI_CACHE[key] = (percentile(means, tail), percentile(means, 1 - tail))
    return _CI_CACHE[key]


def paired(first, second, boots=BOOTS, seed=SEED, with_ci=True):
    """D = second - first per scene (dict scene -> Fraction). Ties (D = 0) drop out of the sign test only."""
    scenes = sorted(set(first) & set(second))
    diffs = [second[s] - first[s] for s in scenes]
    pos, neg = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    out = {"n_scenes": len(scenes), "pos": pos, "neg": neg, "tie": len(diffs) - pos - neg, "m": pos + neg,
           "p": sign_test_p(pos, pos + neg), "mean_D": None, "ci95": None,
           "scenes": [[s, float(first[s]), float(second[s]), float(d)] for s, d in zip(scenes, diffs)]}
    if diffs:
        out["mean_D"] = float(sum(diffs) / len(diffs))
        if with_ci:
            out["ci95"] = bootstrap_ci([float(d) for d in diffs], boots, seed)
    return out


def ci_verdict(ci):
    """Reads the scene-bootstrap 95% interval of the mean difference D (later structure minus earlier)."""
    if not ci:
        return "NA"
    if ci[0] > 0:
        return "높음 (구간이 0 위)"
    if ci[1] < 0:
        return "낮음 (구간이 0 아래)"
    return "구분 안 됨 (구간이 0 포함)"


def mean_difference_at(terms_first, terms_second, lam):
    """Mean over the common scenes of (second - first); a term is (C, excess): SP = max(0, C - lam * excess), exact (Fraction)."""
    scenes = sorted(set(terms_first) & set(terms_second))
    if not scenes:
        return None, 0

    def scene_mean(terms):
        return sum(max(Fraction(0), c - lam * e) for c, e in terms) / len(terms)
    return sum(scene_mean(terms_second[s]) - scene_mean(terms_first[s]) for s in scenes) / len(scenes), len(scenes)


def breakeven_lambda(terms_first, terms_second):
    """Break-even lambda*: the lambda at which the scene-mean SP of `second` equals that of `first` (T0 has no excess, so SP = C).
    SP has a floor at 0, so the mean difference f(lam) is piecewise linear and non-increasing; it is solved exactly on the
    breakpoints lam = C/excess. Returns (status, lambda, D at lambda 0, n scenes):
      none      f stays above 0 at every lambda (the covered cells stay inside the allowance, or enough C): no break-even
      at_zero   f(0) <= 0: `second` is not above `first` even without any penalty (lambda* = 0)
      value     lambda* > 0."""
    f0, n = mean_difference_at(terms_first, terms_second, Fraction(0))
    if f0 is None:
        return "NA", None, None, 0
    if f0 <= 0:
        return "at_zero", Fraction(0), f0, n
    points = sorted({Fraction(c) / e for terms in (terms_first, terms_second) for rows in terms.values() for c, e in rows
                     if e > 0 and c > 0})
    previous, f_previous = Fraction(0), f0
    for point in points:
        f_point, _ = mean_difference_at(terms_first, terms_second, point)
        if f_point <= 0:
            return "value", previous + f_previous * (point - previous) / (f_previous - f_point), f0, n
        previous, f_previous = point, f_point
    return "none", None, f0, n


# ------------------------------------------------------------------ scenes
def read_json(path):
    try:
        return compare.read_json(path)
    except (OSError, ValueError):
        return None


def load_scenes(paths):
    scenes = {}
    for path in paths:
        data = read_json(path)
        if not isinstance(data, dict) or "scenes" not in data:
            raise SystemExit("scene file unreadable: %s" % path)
        for scene in data["scenes"]:
            if scene["id"] in scenes and scenes[scene["id"]] != scene:
                raise SystemExit("scene id %s appears in two scene files with different content" % scene["id"])
            scenes[scene["id"]] = scene
    return scenes


def scene_type(scene_id, scene):
    """L/C/X/D/RND from type_code; K2/K3/L3 coop ids; scenes18b ids by leading letters."""
    if scene and scene.get("type_code"):
        return scene["type_code"]
    match = re.fullmatch(r"([A-Z])(\d)\d\d", scene_id or "")
    if match:
        return match[1] + match[2]
    match = re.match(r"[A-Z]+", scene_id or "")
    return match[0] if match else "unknown"


def scene_from_name(name, known):
    """Hyphenated ids (L2-01) never go through compare.py's [^-]+ regex. Longest known id as a whole token wins.
    Returns (scene or None, ambiguous)."""
    text = re.sub(r"^(?:t[012]|oracle|fixed)-", "", name).replace("_", "-")
    hits = []
    for scene_id in known:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(scene_id.replace("_", "-")) + r"(?![A-Za-z0-9])"
        if re.search(pattern, text):
            hits.append(scene_id)
    if not hits:
        return None, False
    longest = max(len(h) for h in hits)
    best = [h for h in hits if len(h) == longest]
    return best[0], len(best) > 1


# ------------------------------------------------------------------ run discovery
def split_attempt(name):
    match = re.fullmatch(r"(.+?)-(?:rr|retry)(\d+)", name)
    return (match[1], int(match[2])) if match else (name, 0)


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as stream:
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(stream)]


def legacy_parts(name, scene_ids):
    """(structure, bundle, scene) for names like t1-C01-h, t0-L2-01-c1, oracle-C01. The bundle is the code/batch
    letter after the scene token ('x' when there is none)."""
    match = re.match(r"(t[012]|oracle)-", name)
    structure = ORACLE if name.startswith("oracle-") else (match[1].upper() if match else "UNKNOWN")
    scene, _ = scene_from_name(name, scene_ids)
    rest = name[match.end():] if match else name
    if scene:
        rest = re.sub(r"(?<![A-Za-z0-9])" + re.escape(scene).replace("\\-", "[-_]") + r"(?![A-Za-z0-9])", "", rest, count=1)
    bundle = re.search(r"([A-Za-z]+)\d*$", rest.strip("-_"))
    return structure, (bundle[1] if bundle else "x"), scene


def gather(roots, manifest, scene_ids, oracle_groups):
    """Planned runs (manifest / index.csv) plus any run folder found. -> list of entry dicts."""
    found = defaultdict(list)
    for root in roots:
        for child in sorted(Path(root).iterdir()):
            if child.is_dir() and child.name not in ("compare", "brain") and not child.name.startswith("."):
                base, attempt = split_attempt(child.name)
                found[base].append((attempt, child, Path(root)))
    planned = {}
    for root in roots:
        if (Path(root) / "index.csv").exists():
            for row in read_csv(Path(root) / "index.csv"):
                planned.setdefault(row["run_id"], {}).update(index_status=row.get("status", ""),
                                                             index_warn=row.get("warnings", ""),
                                                             **{k: v for k, v in row.items() if v and k not in ("status", "warnings")})
    for row in manifest:
        planned.setdefault(row["run_id"], {}).update({k: v for k, v in row.items() if v})
    entries = []
    for run_id, row in sorted(planned.items()):
        attempts = sorted(found.get(run_id, []), key=lambda a: a[0])
        meta = {}
        if attempts:
            meta = read_json(attempts[-1][1] / "meta.json") or {}
        merged = dict(meta, **row)
        if "team" not in merged or "group" not in merged:
            raise SystemExit("planned run %s has no group/team (give --manifest or an index.csv)" % run_id)
        structure = ORACLE if merged["group"] in oracle_groups else merged["team"]
        entries.append(dict(run_id=run_id, group=merged["group"], structure=structure, scene=merged.get("scene_id") or None,
                            scene_src="manifest" if merged.get("scene_id") else "", rep=int(merged["rep"]) if merged.get("rep") else None,
                            row=merged, attempts=attempts, index_status=merged.get("index_status", ""),
                            index_warn=merged.get("index_warn", ""), planned=True))
    for base, attempts in sorted(found.items()):
        if base in planned:
            continue
        structure, bundle, scene = legacy_parts(base, scene_ids)
        entries.append(dict(run_id=base, group="legacy-" + bundle, structure=structure, scene=scene,
                            scene_src="name" if scene else "", rep=None, row={}, attempts=sorted(attempts, key=lambda a: a[0]),
                            index_status="", index_warn="", planned=False))
    return entries


def arm_labels(entries, main_group):
    """Condition label = group (+ extra args / model / robots / leader that differ from the reference arm)."""
    reference = next((e for e in entries if e["planned"] and e["group"] == main_group), None)

    def tokens(row):
        return (row.get("vm_args", "") + " " + row.get("server_args", "")).split()
    base = set(tokens(reference["row"])) if reference else set(COMMON_ARGS.split())
    ref_row = reference["row"] if reference else {}
    for entry in entries:
        row, extras = entry["row"], []
        if entry["planned"]:
            extras = [t for t in tokens(row) if t not in base]
            for key in ("model", "robots", "leader"):
                if row.get(key) and ref_row.get(key) and row[key] != ref_row[key]:
                    extras.append("%s=%s" % (key, row[key]))
            if row.get("condition"):
                extras.append(row["condition"])
        entry["arm"] = entry["group"] + (" [" + " ".join(extras) + "]" if extras else "")
    planned = [e for e in entries if e["planned"]]
    lacking = [e["run_id"] for e in planned if "vm_args" not in e["row"]]
    if lacking and len(lacking) < len(planned):
        raise SystemExit("planned runs without vm_args (index.csv rows carry none; give --manifest so every run's condition "
                         "is known): %s" % lacking[:5])
    main_arms = sorted({e["arm"] for e in entries if e["group"] == main_group})
    if len(main_arms) > 1:
        raise SystemExit("main group %s maps to several arms %s: its rows differ in args/model/robots/leader" % (main_group, main_arms))


# ------------------------------------------------------------------ one run folder -> cell fields
def halt_kind(text):
    """(is_fault, label). Robot/instance call caps are results; everything else that halted a robot is a fault."""
    low = str(text).lower()
    if "robot call cap reached" in low:
        return False, "cap_end"
    if "per-instance call cap reached" in low:
        return False, "cap_end_instance"   # not named in PREREG; read as the 300-call hard cap (result), see summary
    if "campaign attempt cap reached" in low:
        return True, "campaign_attempt_cap"  # not named in PREREG; read as a spend/attempt guard (fault), see summary
    return True, "fault"


def read_brain(path, brain_dir, team):
    if brain_dir and (brain_dir / "brain-record.json").exists():
        data = read_json(brain_dir / "brain-record.json")
        if isinstance(data, dict):
            return data
    brain = (team or {}).get("brain", {})
    if isinstance(brain, str):
        try:
            brain = json.loads(brain)
        except ValueError:
            brain = {}
    return brain if isinstance(brain, dict) else {}


FIRST_UNRESOLVED = "first assignment unresolved; not scored"   # compare.analyze_run warning text
COMPOUND_WARNINGS = (FIRST_UNRESOLVED, "invalid external brain; using embedded record",
                     "scene unavailable; planning not scored")   # compare.py warnings that contain "; " themselves


def split_warnings(text):
    """compare.analyze_run joins its warnings with "; ", and three of them contain "; ". Split without cutting those."""
    for number, phrase in enumerate(COMPOUND_WARNINGS):
        text = text.replace(phrase, "\0%d\0" % number)
    parts = [w for w in text.split("; ") if w]
    return [re.sub("\0(\\d+)\0", lambda m: COMPOUND_WARNINGS[int(m[1])], w) for w in parts]


def evaluate(path, entry, scenes, brain_roots, tmp, counter):
    """Fields of one attempt: state ok / plan_na / failed / in_progress (+ values)."""
    path = Path(path)
    out = evaluate_stub()
    try:
        team = json.loads((path / "team.json").read_text(encoding="utf-8"))
        if not isinstance(team, dict):
            raise ValueError("not an object")
    except OSError:
        out["reason"] = "team.json missing"
        return out
    except ValueError as error:
        out["reason"] = "team.json invalid: %s" % error
        return out
    out["team_scene"] = team.get("scene")
    status = team.get("status", "unknown")
    if status == "running":
        out.update(state="in_progress", reason="team.json status running")
        return out
    if status != "complete":
        out["reason"] = "team.json status %s" % status
        return out
    if any(team.get(k) is None for k in ("correct_boxes", "required_boxes", "wrong_place_boxes", "end_s")):
        out["reason"] = "complete team.json lacks result fields"
        return out
    out["complete"] = True
    brain_dir = None
    for candidate in [path / "brain"] + [Path(r) / path.name for r in brain_roots]:
        if (candidate / "brain-record.json").exists() or (candidate / "llm-calls.jsonl").exists():
            brain_dir = candidate
            break
    brain = read_brain(path, brain_dir, team)
    structure = entry["structure"]
    if brain.get("kind") == "fixed_plan" and structure in STRUCTS:
        structure = "FIXED"
    out["structure"] = structure
    prefix = structure.lower() if structure in STRUCTS else ("oracle" if structure == ORACLE else "fixed")
    scene_id = team.get("scene") or "legacy"
    alias = "%s-%s-%d" % (prefix, re.sub(r"[^A-Za-z0-9_]", "_", scene_id), next(counter))
    (tmp / "runs").mkdir(exist_ok=True)
    (tmp / "brain").mkdir(exist_ok=True)
    (tmp / "runs" / alias).symlink_to(path.resolve())
    if brain_dir:
        (tmp / "brain" / alias).symlink_to(brain_dir.resolve())
    row = compare.analyze_run(tmp / "runs" / alias, scenes, tmp / "brain", None)
    if row["excluded"]:
        out.update(complete=False, reason=row["excluded"])
        return out
    out["warnings"] = split_warnings(row["warnings"])
    # compare.py warns when the FIRST pick has no resolvable colour (e.g. an explicit `finish` option). The first-plan quadrant is a
    # reported-only side mark (PREREG 2), no table here uses it, and a reference-plan run has no first pick at all. Counted, not listed.
    out["first_unresolved"] = FIRST_UNRESOLVED in out["warnings"]
    out["warnings"] = [w for w in out["warnings"] if w != FIRST_UNRESOLVED]
    out.update(raw_C=row["plan_cover"], raw_S=bool(row["physical_success"]), end_s=row["end_s"], messages=row["messages"],
               llm_calls=row["llm_calls"], cost_usd=row["cost_usd"], quadrant=row["quadrant"])
    halts = {r: v for r, v in (brain.get("halted_by_robot") or {}).items() if v}
    if brain.get("halted"):
        halts.setdefault("*", brain["halted"])
    kinds = {r: halt_kind(v) for r, v in halts.items()}
    out["halt"] = "; ".join("%s:%s" % (r, halts[r]) for r in sorted(halts))
    out["cap_end"] = ",".join(sorted({k[1] for k in kinds.values() if not k[0]}))
    faults = sorted({"%s(%s)" % (halts[r], kinds[r][1]) for r in kinds if kinds[r][0]})
    if faults:
        out.update(state="failed", reason="halted: " + ", ".join(faults))
        return out
    out["S"] = int(out["raw_S"])
    if structure not in STRUCTS:
        out["first_unresolved"] = None                      # reference/fixed plan: no first pick exists
    if out["raw_C"] is None:
        why = "scene %s not in scene files" % scene_id if scenes.get(scene_id) is None else "a robot has no recorded choice"
        out.update(state="plan_na", reason=why)
        return out
    out.update(state="ok", C=int(out["raw_C"]), G=out["raw_C"] and 1 or 0, G_strict=0, guess_with_msg=0)
    robots = team.get("robots") or ["r1", "r2"]
    out["n_robots"] = len(robots)
    out["M"] = row["messages"]
    if out["M"] is None and structure in (ORACLE, "FIXED"):
        out["M"] = 0                                       # 정답 계획·고정 계획은 메시지 구조가 없다
    if out["M"] is None:
        out["warnings"].append("message count unknown: SP not scored")
    else:
        per_robot = [row.get("messages_" + r) for r in robots]
        out["M_max_robot"] = max((n for n in per_robot if n is not None), default=None)
    for key, lam in PENALTY_LAMBDAS.items():
        out[key] = penalized(out["C"], out["M"], out["n_robots"], lam)
    if structure in STRUCTS:
        try:
            result = causes.analyze_causes(tmp / "runs" / alias, scenes, tmp / "brain", None)
            out["tags"], out["primary"] = result["tags"], result["primary"]
            out["success_class"] = result["success_class"]
            if out["C"] and result["success_class"] == "guess_correct":
                out["G"] = 0                                    # task wording: only guess hits are removed
            if out["C"] and result["success_class"] in GROUNDED_CLASSES:
                out["G_strict"] = 1
            finals = {}
            for event in result["events"]:
                if event["kind"] == "destination":
                    finals[event["rid"]] = event
            out["guess_with_msg"] = sum(e["label"] == "guess" and e["n_received"] > 0 for e in finals.values())
            out.update(cap_reached=result["cap_reached"], cap_n=len(result["cap_robots"]) if result["cap_reached"] is not None else None,
                       msg_decision=result["msg_via_decision"], msg_chance=result["msg_via_chance"], cap=result["cap"],
                       planner=result["planner"])
            out["warnings"].extend(result["msg_warnings"])
            if result["msg_via_chance"] is not None and not str(result["planner"] or "").startswith("brain-v3"):
                out["warnings"].append("planner %s is older than brain-v3: `via` marks are not trusted" % result["planner"])
            tally = Counter((p["kind"], p["knew"] if p["kind"] == "lost" else None) for p in result["put_downs"])
            out.update(put_decoy=tally[("decoy", None)], put_duplicate=tally[("duplicate", None)],
                       put_lost_own=tally[("lost", "own_order")], put_lost_team=tally[("lost", "team_only")],
                       put_lost_unknown=tally[("lost", "unknown")], put_unknown=tally[("unknown", None)])
        except Exception as error:  # a malformed record must not stop a 600-run analysis; it is listed
            out["warnings"].append("causes failed: %s: %s" % (type(error).__name__, error))
            out["success_class"] = "error" if out["C"] else ""
            out["primary"] = "" if out["C"] else "other"
            out["G"] = 0
    return out


# ------------------------------------------------------------------ cells
def find_exit_file(folder, root):
    """exit-<name>.json of the last attempt. collect.py keeps it inside results/<run_id>/ (name = meta.json `source_name`, which is
    `<run_id>-retryN` after a retry); a legacy evidence folder keeps it next to the run folder, in the root."""
    folder, root = Path(folder), Path(root)
    names = [folder.name]
    source = (read_json(folder / "meta.json") or {}).get("source_name")
    if source:
        names.insert(0, source)
    for base in (folder, root):
        for name in names:
            if (base / ("exit-%s.json" % name)).exists():
                return base / ("exit-%s.json" % name)
    found = sorted(folder.glob("exit-*.json"))
    return found[-1] if found else None


def build_cells(args, scenes):
    manifest = [row for path in (args.manifest or []) for row in read_csv(path)]
    entries = gather(args.runs, manifest, list(scenes), set(args.oracle_group))
    arm_labels(entries, args.main_group)
    cells, counter = [], itertools.count(1)
    with tempfile.TemporaryDirectory(dir=HERE) as tmp_name:
        tmp = Path(tmp_name)
        for entry in entries:
            warnings, chosen, final = [], None, None
            used = None
            for attempt, path, root in entry["attempts"]:
                result = evaluate(path, entry, scenes, args.brain, tmp, counter)
                if chosen is None:
                    chosen, used = result, (attempt, path)
                elif chosen["state"] in ("failed", "in_progress"):  # PREREG 7: a rerun replaces the first only if that was a fault
                    # (a first attempt left "running" by a killed launcher counts as a fault, issue triage 11/16)
                    chosen, used = result, (attempt, path)
                else:
                    warnings.append("attempt %s ignored: earlier attempt was not a fault" % path.name)
            if chosen is None:
                status = entry["index_status"]
                if status in ("failed",):
                    chosen = dict(evaluate_stub(), state="failed", reason="dispatch failed (index): " + entry["index_warn"])
                else:
                    chosen = dict(evaluate_stub(), state="in_progress",
                                  reason="not started / running (index %s)" % (status or "none"))
            else:
                final = used[1]
            chosen["warnings"] = list(chosen["warnings"]) + warnings
            exit_path = find_exit_file(entry["attempts"][-1][1], entry["attempts"][-1][2]) if entry["attempts"] else None
            exit_code = (read_json(exit_path) or {}).get("exit_code") if exit_path else None
            if exit_code not in (None, 0):
                chosen["warnings"].append("VM exit_code %s" % exit_code)
            cell = dict(chosen, arm=entry["arm"], group=entry["group"], run_id=entry["run_id"], rep=entry["rep"],
                        attempts=max(len(entry["attempts"]), int(entry["row"].get("attempts") or 0)) or None,
                        source=str(final) if final else "",
                        manifest_scene=entry["scene"] if entry["scene_src"] == "manifest" else None)
            cell["structure"] = chosen.get("structure") or entry["structure"]
            # scene: manifest first (design cell), then team.json, then the run name against known ids
            scene, src = entry["scene"], entry["scene_src"]
            if chosen.get("team_scene") and chosen["team_scene"] != "legacy":
                if scene and src == "manifest" and chosen["team_scene"] != scene and chosen["state"] in ("ok", "plan_na"):
                    cell.update(state="failed", C=None, G=None, G_strict=None, S=None, **{k: None for k in PENALTY_LAMBDAS},
                                reason="scene mismatch: manifest %s, team.json %s" % (scene, chosen["team_scene"]))
                if src != "manifest":
                    scene, src = chosen["team_scene"], "team.json"
            if not scene:
                scene, ambiguous = scene_from_name(entry["run_id"], list(scenes))
                src = "name" + (" (ambiguous)" if ambiguous else "") if scene else "unknown"
            cell.update(scene=scene or "unknown", scene_src=src)
            cell["scene_type"] = scene_type(scene, scenes.get(scene))
            cell["control"] = bool((scenes.get(scene) or {}).get("control"))
            cells.append(cell)
    assign_reps(cells, args.reps)
    check_duplicates(cells)
    return cells


def evaluate_stub():
    return dict(state="failed", reason="", complete=False, raw_C=None, raw_S=None, C=None, G=None, G_strict=None,
                guess_with_msg=None, first_unresolved=None, S=None, end_s=None, messages=None, llm_calls=None, cost_usd=None, success_class="", primary="", tags=[], cap_end="", halt="",
                warnings=[], team_scene=None, structure=None, quadrant=None, n_robots=None, M=None, M_max_robot=None,
                cap_reached=None, cap_n=None, msg_decision=None, msg_chance=None, cap=None, planner=None,
                **{k: None for k in PENALTY_LAMBDAS}, **{k: None for k in PUT_COLUMNS})


def assign_reps(cells, reps):
    """Legacy folders have no rep column: ordinal within (arm, scene, structure), sorted by run name."""
    groups = defaultdict(list)
    for cell in cells:
        if cell["rep"] is None:
            groups[(cell["arm"], cell["scene"], cell["structure"])].append(cell)
    for items in groups.values():
        for number, cell in enumerate(sorted(items, key=lambda c: c["run_id"]), 1):
            cell["rep"] = number
    if reps:   # planned grid for legacy folders: pad missing reps of every observed (arm, scene, structure)
        seen = {(c["arm"], c["scene"], c["structure"]): c for c in cells if c["structure"] in STRUCTS and c["scene"] != "unknown"}
        present = {(c["arm"], c["scene"], c["structure"], c["rep"]) for c in cells}
        for (arm, scene, structure), model in sorted(seen.items()):
            for rep in range(1, reps + 1):
                if (arm, scene, structure, rep) not in present:
                    cell = dict(evaluate_stub(), state="in_progress", reason="planned (--reps %d), no run folder" % reps,
                                arm=arm, group=model["group"], run_id="", rep=rep, attempts=None, source="",
                                manifest_scene=None, structure=structure, scene=scene, scene_src=model["scene_src"],
                                scene_type=model["scene_type"], control=model["control"])
                    cells.append(cell)


def check_duplicates(cells):
    keys = Counter((c["arm"], c["scene"], c["structure"], c["rep"]) for c in cells)
    dup = [k for k, n in keys.items() if n > 1]
    if dup:
        raise SystemExit("duplicate cell keys (arm, scene, structure, rep), not averaging: %s" % dup[:5])


# ------------------------------------------------------------------ scoring
class Book:
    """Cell values under a failure mode. interim: in-progress/not-started cells leave every mode."""

    def __init__(self, cells, interim=False, plan_na="exclude"):
        self.cells, self.interim, self.plan_na = cells, interim, plan_na

    def value(self, cell, metric, mode):
        state = cell["state"]
        if state == "in_progress":
            if self.interim:
                return None
            state = "failed"
        if state == "plan_na":
            if metric == "S":
                return cell["S"]
            if self.plan_na != "failure":
                return None
            state = "failed"
        if state == "failed":
            return {"zero": 0, "drop": None, "one": 1}[mode]
        return cell[metric]

    def scene_means(self, structure, metric, mode, arm=None, scenes=None):
        """{scene: Fraction mean over the cells of that scene}; failed cells count in the denominator (mode zero/one)."""
        values = defaultdict(list)
        for cell in self.cells:
            if cell["structure"] != structure or (arm is not None and cell["arm"] != arm) or cell["scene"] == "unknown":
                continue
            if scenes is not None and cell["scene"] not in scenes:
                continue
            value = self.value(cell, metric, mode)
            if value is not None:
                values[cell["scene"]].append(value)
        return {s: Fraction(sum(v), len(v)) for s, v in values.items()}

    def penalty_terms(self, structure, mode, arm=None, scenes=None):
        """{scene: [(C, excess), ...]} for the break-even solve. A scored cell contributes (C, max(0, M - 2R)); a failed / in-progress
        cell contributes its mode constant (excess 0); a cell whose M is unknown leaves out (as in scene_means)."""
        terms = defaultdict(list)
        for cell in self.cells:
            if cell["structure"] != structure or (arm is not None and cell["arm"] != arm) or cell["scene"] == "unknown":
                continue
            if scenes is not None and cell["scene"] not in scenes:
                continue
            if cell["state"] == "ok":
                if cell["C"] is not None and cell["M"] is not None:
                    terms[cell["scene"]].append((Fraction(cell["C"]), max(0, cell["M"] - PENALTY_ALLOWANCE * cell["n_robots"])))
            else:
                value = self.value(cell, PENALTY_PRIMARY, mode)
                if value is not None:
                    terms[cell["scene"]].append((Fraction(value), 0))
        return terms

    def cause_partition(self, structure, arm):
        """Shares of (1 - mean C) by primary cause, mode zero; sums exactly to 1 - mean over scenes."""
        by_scene = defaultdict(list)
        for cell in self.cells:
            if cell["structure"] == structure and cell["arm"] == arm and cell["scene"] != "unknown":
                value = self.value(cell, "C", "zero")
                if value is not None:
                    by_scene[cell["scene"]].append((value, cell))
        tally = {name: Fraction(0) for name in CAUSE_ROWS}
        for items in by_scene.values():
            for value, cell in items:
                if value == 0:
                    ok = cell["state"] == "ok"
                    name = (cell["primary"] if cell["primary"] in CAUSE_ROWS else "other") if ok else "fault"
                    tally[name] += Fraction(1, len(items))
        n = len(by_scene)
        return n, {k: v / n for k, v in tally.items()} if n else {k: Fraction(0) for k in tally}


def mean(values):
    return sum(values) / len(values) if values else None


def pct(value, signed=False):
    if value is None:
        return "NA"
    return ("%+.1f" if signed else "%.1f") % (100 * float(value))


def ratio(num, den):
    return "%d/%d" % (num, den)


# ------------------------------------------------------------------ tests
def run_tests(book, cells, scenes, args):
    arms = sorted({c["arm"] for c in cells if c["structure"] in STRUCTS})
    tests, by_type = [], []
    for arm in arms:
        for metric in METRICS:
            for mode in MODES:
                for variant in ("all", "no_control"):
                    keep = None if variant == "all" else {s for s, sc in scenes.items() if not sc.get("control")}
                    sets = {s: book.scene_means(s, metric, mode, arm, keep) for s in STRUCTS}
                    if variant == "no_control":   # only when this arm really has control scenes
                        full = {s: book.scene_means(s, metric, mode, arm) for s in STRUCTS}
                        if all(set(full[s]) == set(sets[s]) for s in STRUCTS):
                            continue
                    family = []
                    for first, second in CONTRASTS:
                        if sets[first] and sets[second]:
                            result = paired(sets[first], sets[second], args.boots, args.seed)
                            family.append(dict(result, arm=arm, contrast="%s->%s" % (first, second), metric=metric,
                                               mode=mode, variant=variant, primary=arm == args.main_group))
                    for test, decision in zip(family, holm([t["p"] for t in family])):
                        test.update(holm_adj_p=decision["adj_p"], holm_threshold=decision["threshold"],
                                    holm_reject=decision["reject"], family_size=len(family),
                                    ci_verdict=ci_verdict(test["ci95"]),
                                    verdict_basis="ci" if metric in CI_VERDICT_METRICS else "sign_holm")
                    tests.extend(family)
                    if sets["T1"] and sets["T2"]:
                        d = paired(sets["T1"], sets["T2"], with_ci=False)
                        tests.append(dict(d, arm=arm, contrast="T1->T2 (descriptive only)", metric=metric, mode=mode,
                                          variant=variant, primary=False, p=None, ci95=None, descriptive=True))
            if metric == PENALTY_PRIMARY:
                for first, second in CONTRASTS:
                    status, lam, f0, n = breakeven_lambda(book.penalty_terms(first, "zero", arm), book.penalty_terms(second, "zero", arm))
                    tests.append(dict(arm=arm, contrast="%s->%s" % (first, second), metric="SP_BE", mode="zero", variant="all",
                                      primary=arm == args.main_group, kind="breakeven", status=status, n_scenes=n,
                                      breakeven_lambda=None if lam is None else float(lam),
                                      breakeven_lambda_exact=None if lam is None else str(lam),
                                      mean_D_at_zero=None if f0 is None else float(f0)))
            for first, second in CONTRASTS:
                sets = {s: book.scene_means(s, metric, "zero", arm) for s in (first, second)}
                scene_ids = sorted(set(sets[first]) & set(sets[second]))
                for kind in sorted({scene_type(s, scenes.get(s)) for s in scene_ids}):
                    diffs = [sets[second][s] - sets[first][s] for s in scene_ids if scene_type(s, scenes.get(s)) == kind]
                    by_type.append(dict(arm=arm, contrast="%s->%s" % (first, second), metric=metric, mode="zero",
                                        scene_type=kind, n_scenes=len(diffs), mean_D=float(mean(diffs))))
    return tests, by_type


def condition_rows(book, cells, args):
    """Every non-reference arm against the reference arm on the same scenes. A condition arm is paired with the
    reference's same structure; a full-information arm with every reference structure (T0, T1, T2)."""
    arms = sorted({c["arm"] for c in cells if c["structure"] in STRUCTS})
    ref = args.main_group if args.main_group in arms else None
    rows = []
    for arm in arms:
        if arm == ref or ref is None:
            continue
        full = arm.split(" [")[0] == args.fullinfo_group
        for structure in STRUCTS:
            for ref_structure in (STRUCTS if full else (structure,)):
                for metric in ("C", "G"):
                    first = book.scene_means(ref_structure, metric, "zero", ref)
                    second = book.scene_means(structure, metric, "zero", arm)
                    if second:
                        result = paired(first, second, args.boots, args.seed)
                        rows.append(dict(result, arm=arm, reference=ref, structure=structure, ref_structure=ref_structure,
                                         metric=metric, kind="fullinfo" if full else "condition", n_arm_scenes=len(second)))
    return ref, rows


# ------------------------------------------------------------------ rendering
def md(headers, rows):
    return compare.markdown(headers, rows)


def render(cells, scenes, book, tests, by_type, ref, cond, args, inputs):
    text = ["# 본 실험 분석 (analyze_main.py)\n"]
    if args.note:
        text.append("**" + args.note + "**\n")
    interim = "예. 진행 중·미시작 칸을 모든 모드에서 뺐다(중간 점검용)." if args.interim else "아니오. 진행 중·미시작 칸은 실패와 같이 센다."
    text.append("입력: %s\n\n장면 파일 %d개(장면 %d개). 시드 %d, 부트스트랩 %d회. 중간 점검 모드(--interim): %s  PlanNA 처리: %s.\n"
                % (", ".join(inputs), len(args.scenes), len(scenes), args.seed, args.boots, interim, args.plan_na))
    text.append("""## 읽는 법과 정의
- 칸(cell) = 팔(arm: 그룹 + 조건 인자) × 장면 × 구조 × 반복. 같은 칸이 둘이면 평균하지 않고 오류로 멈춘다. 장면은 매니페스트(있으면), 없으면 `team.json` 의 scene, 그것도 없으면 실행 이름에서 알려진 장면 ID 를 통째 토큰으로 찾는다(하이픈 ID 안전).
- 장면 점수 = 그 장면 반복들의 평균(정확한 분수). 검정 단위는 장면이고, 팔마다 따로 한다. 설계·무작위·3대·두 번째 모델 팔은 합치지 않는다(PREREG 4절).
- **실패 모드**: `zero`(기본) 실패·미완료 칸을 C=0, S=0 으로 평균 분모에 넣음 / `drop` 실패 칸을 뺌 / `one` 실패 칸을 C=1(S=1). 실패 칸 = team.json 이 없거나 complete 가 아님, 결과 필드 결측, 로봇이 예외·예산·(아래 표시한) 가드로 멈춤, 매니페스트 장면과 team.json 장면이 다름. 재실행(`-rrN`, `-retryN`)은 앞 실행이 고장일 때만 칸 값을 대신한다.
- **compare.py 와의 차이**: compare.py:119-125 는 team.json 이 complete 가 아니거나 결과 필드가 없는 실행을 `excluded` 로 두고 모든 분모(`n/N`)에서 뺀다. 이 스크립트의 `drop` 모드가 그 동작에 가깝다. 기본 `zero` 는 그 칸을 분모에 두고 0 으로 센다. 또 compare.py 는 `halted_by_robot` 의 예외·예산 정지를 보지 않는다(여기서는 고장 칸). 아래 칸 현황 표의 "compare.py 식 n/N" 열이 compare.py 규칙을 그대로 적용한 값이다.
- **근거 있는 덮임 G**(과제 문구 그대로): C=1 이고 causes.py 의 `success_class` 가 `guess_correct`(추측 적중)가 아닌 칸. `other_or_unknown` 은 G=1 로 두고, 더 엄격한 `G_strict`(= `message_grounded` 또는 `own_only` 만)를 `cells.csv` 와 칸 현황 표의 개수로 함께 낸다. 통신이 계획을 날랐다는 증거는 `message_grounded` 뿐이다.
- **G 의 알려진 한계**: `guess_correct` 는 causes.py 의 문장 분류에 달려 있다. 2026-11-15 규칙 수정 뒤에는 받은 메시지에서 나온 (색, 표식) 짝이 1인칭 보고(예 "I'll handle the blue box to sign12")이든 지시든 사실 표든 목적지 결정과 같으면 `message` 로 센다(다른 색·다른 표식·부정문·제3 로봇 배정은 근거 아님, 1인칭 짝은 충돌로도 세지 않음). 그래도 메시지에 짝이 없거나 말과 다른 곳을 고르면 `guess` 로 남으므로, 칸 현황 표에 "추측 적중 중 메시지 수신 뒤 결정" 개수를 계속 따로 적는다. 이 개수가 0 이 아니면 G 는 T1/T2 의 통신 효과를 낮게 잡을 수 있다.
- **메시지 벌점 점수 SP**(PREREG 2절, 사용자 문구의 "S", 물리 성공 S 와 구분하려고 SP): SP = max(0, C − λ × max(0, M − 2R)). C = 위 계획 덮임(0/1), M = 그 실행에서 모든 로봇이 보낸 메시지 봉투 수(`brain-record.json` 의 `messages`, 없으면 team 결정의 `sent`; 이동 중 기회로 보낸 것도 포함), R = `team.json` 의 로봇 수(허용 2R). 기본 λ=0.02(`SP02`), 민감도 λ=0.05(`SP05`), 0.10(`SP10`). 정확한 분수로 계산한다. T0 는 M=0 이라 SP=C. 메시지 기록이 없어 M 을 모르는 완료 칸은 SP 를 NA 로 두고 평균에서 뺀다(0 으로 읽지 않는다. 정답·고정 계획 실행은 M=0). 실패 칸은 C 와 같은 모드 규칙(0 / 제외 / 1)을 따른다. **SP 의 판정은 부호 검정이 아니라 장면 단위 평균 D 와 장면 부트스트랩 95% 구간이다**(2026-11-16 03:1x KST 변경, 재생 표를 본 뒤의 제안이며 본 실험 결과가 아니다). 부호 검정은 D 의 부호만 보므로, 늘 덮는 장면에서도 메시지가 허용을 넘는지 여부로 부호가 정해진다. 부호 검정·Holm 값은 `tests.json` 에 그대로 남기고 2절 SP 표에는 "참고" 열로만 적는다. 손익분기 λ* 는 2c 표.
- **멈춤 문구**: `Robot call cap reached` 는 결과(`cap_end`). PREREG 에 없는 `Per-instance call cap reached` 는 실행당 300 호출 하드 상한이라 보고 결과로 읽고(`cap_end_instance`), `Campaign attempt cap reached` 는 지출·시도 가드라 보고 고장으로 읽었다. 이 두 해석은 이 스크립트의 가정이다.
""")
    text.append(cell_status(cells, book))
    text.append(main_tests(tests, args))
    text.append(penalty_table(cells, book))
    text.append(breakeven_table(tests))
    text.append(cap_table(cells))
    text.append(type_table(by_type, args))
    text.append(shortfall(cells, book, scenes, args))
    text.append(split_table(cells, book, args))
    text.append(put_down_table(cells))
    text.append(secondary_table(cells))
    text.append(condition_section(ref, cond, args))
    text.append(lists(cells))
    return "\n".join(text)


def cell_status(cells, book):
    rows = []
    for arm, structure in sorted({(c["arm"], c["structure"]) for c in cells}):
        group = [c for c in cells if c["arm"] == arm and c["structure"] == structure]
        n = Counter(c["state"] for c in group)
        complete = [c for c in group if c["complete"] and c["raw_C"] is not None]
        cover = sum(bool(c["raw_C"]) for c in complete)
        ok = [c for c in group if c["state"] == "ok"]
        classes = Counter(c["success_class"] for c in ok if c["C"])
        zero = book.scene_means(structure, "C", "zero", arm)
        drop = book.scene_means(structure, "C", "drop", arm)
        rows.append([arm, structure, len(group), n["ok"], n["plan_na"], n["failed"], n["in_progress"],
                     sum(1 for c in group if c["cap_end"]), ratio(cover, len(complete)),
                     pct(mean(list(zero.values()))), pct(mean(list(drop.values()))), len(zero), len(drop),
                     classes["guess_correct"], sum(1 for c in ok if c["C"] and c["success_class"] == "guess_correct"
                                                   and c["guess_with_msg"]),
                     classes["message_grounded"], classes["own_only"], classes["other_or_unknown"] + classes["error"],
                     sum(c["G"] or 0 for c in ok), sum(c["G_strict"] or 0 for c in ok)])
    head = ["arm", "구조", "칸", "ok", "계획 NA", "고장/실패", "진행·미시작", "cap_end", "compare.py 식 C n/N",
            "C 평균% (zero)", "C 평균% (drop)", "장면 n (zero)", "장면 n (drop)", "C=1 추측 적중",
            "추측 적중 중 메시지 수신 뒤 결정", "C=1 메시지 근거", "C=1 자기 주문만", "C=1 불명", "G=1 칸", "G_strict=1 칸"]
    return ("## 1. 칸 현황 (분모 설명)\n계획 NA = team.json 은 complete 인데 계획을 못 매긴 칸(사유는 맨 아래 표). "
            "compare.py 식 n/N 은 complete 칸만 센 값이다. `C 평균%` 는 장면 평균의 평균(%)이다.\n\n" + md(head, rows))


def fmt_ci(ci):
    return "NA" if not ci else "[%s, %s]" % (pct(ci[0], True), pct(ci[1], True))


def main_tests(tests, args):
    text = ["## 2. 주 검정 (T0 대 T1, T0 대 T2)\n"
            "D = (후자 − 전자) 장면 점수. **C(와 G·S)의 판정 = 양측 정확 부호 검정(동점 장면 제외) + Holm 보정.** "
            "**SP 의 판정 = 장면 단위 평균 D 와 장면 복원추출 부트스트랩 %d회의 백분위 95%% 구간**(구간이 0 을 빼면 차이, 0 을 포함하면 구분 안 됨; "
            "두 대조 사이 보정 없음). SP 의 부호 검정 p 는 참고로만 적는다: 부호가 통신 이득이 아니라 메시지 수가 허용을 넘는지로 정해지기 때문이다"
            "(REVIEW-3 4절, PREREG 4절 2026-11-16 03:1x KST 변경). H1·H2(PREREG 1절)는 설계 조작이 먹혔는지 확인하는 검정이다. "
            "T1 대 T2 는 평균 차이만 낸다.\n" % args.boots]
    head = ["arm", "대비", "대조 제외", "n 장면", "+/−/=", "평균 D (pp)", "95% CI (pp)", "p", "Holm 보정 p", "Holm .05 기각"]
    head_sp = ["arm", "대비", "대조 제외", "n 장면", "+/−/=", "평균 D (pp)", "95% CI (pp)", "판정 (구간)", "부호 검정 p (참고)"]
    for metric, modes in (("C", MODES), ("G", ("zero",)), ("S", ("zero",)), (PENALTY_PRIMARY, MODES), ("SP05", ("zero",)),
                          ("SP10", ("zero",))):
        for mode in modes:
            rows = []
            for t in tests:
                if t["metric"] != metric or t["mode"] != mode:
                    continue
                base = [t["arm"] + (" (주)" if t["primary"] else ""), t["contrast"],
                        "예" if t["variant"] == "no_control" else "아니오", t["n_scenes"],
                        "%d/%d/%d" % (t["pos"], t["neg"], t["tie"]), pct(t["mean_D"], True), fmt_ci(t["ci95"])]
                if metric in CI_VERDICT_METRICS:
                    rows.append(base + [t.get("ci_verdict", "NA"), "NA" if t["p"] is None else "%.3g" % t["p"]])
                else:
                    rows.append(base + ["NA" if t["p"] is None else "%.3g" % t["p"],
                                        "NA" if t.get("holm_adj_p") is None else "%.3g" % t["holm_adj_p"],
                                        "NA" if t.get("holm_reject") is None else ("예" if t["holm_reject"] else "아니오")])
            text.append("### %s, %s\n" % (METRIC_TEXT[metric], MODE_TEXT[mode]))
            text.append(md(head_sp if metric in CI_VERDICT_METRICS else head, rows) if rows else "자료 없음.\n")
    return "\n".join(text)


def penalty_table(cells, book):
    """2b: message counts and the penalty score by arm x structure (zero mode scene means)."""
    rows = []
    for arm, structure in sorted({(c["arm"], c["structure"]) for c in cells if c["structure"] in STRUCTS}):
        group = [c for c in cells if c["arm"] == arm and c["structure"] == structure]
        known = [c for c in group if c["state"] == "ok" and c["M"] is not None]
        unknown = sum(c["state"] == "ok" and c["M"] is None for c in group)
        counts = [c["M"] for c in known]
        over = sum(c["M"] > PENALTY_ALLOWANCE * c["n_robots"] for c in known)
        peak = max((c["M_max_robot"] for c in known if c["M_max_robot"] is not None), default=None)
        means = {m: book.scene_means(structure, m, "zero", arm) for m in ("C",) + tuple(PENALTY_LAMBDAS)}
        rows.append([arm, structure, len(group), len(known), unknown, "NA" if not counts else "%.2f" % mean(counts),
                     "NA" if not counts else compare.display(median(counts)), "NA" if not counts else max(counts),
                     ratio(over, len(known)), "NA" if peak is None else peak]
                    + [pct(mean(list(means[m].values()))) for m in ("C",) + tuple(PENALTY_LAMBDAS)])
    head = ["arm", "구조", "칸", "M 있는 완료 칸", "M 모름(SP 에서 뺌)", "M 평균", "M 중앙값", "M 최대", "허용(2R) 초과 칸", "로봇당 최대 M",
            "C 평균%", "SP05 평균%", "SP02 평균%", "SP10 평균%"]
    return ("## 2b. 메시지 수 M 과 벌점 점수 SP (zero 모드, 장면 평균의 평균)\nM = 한 실행에서 모든 로봇이 보낸 봉투 수. 허용 = 2R(2대면 4개). "
            "로봇당 상한 8 은 구현이 막는 값이라 `로봇당 최대 M` 이 8 을 넘으면 기록이나 구현을 의심한다. SP 평균은 같은 칸끼리면 C 평균보다 높을 수 없다(M 을 몰라 SP 에서 뺀 칸이 있으면 어긋날 수 있다).\n\n"
            + md(head, rows))


def breakeven_table(tests):
    """2c: the lambda at which T1 / T2 reach the same scene-mean SP as T0 (zero mode)."""
    rows = []
    for t in tests:
        if t.get("kind") != "breakeven":
            continue
        shown = {"value": "%.4f" % t["breakeven_lambda"] if t["breakeven_lambda"] is not None else "NA",
                 "at_zero": "0 (λ=0 에서도 T0 이하)", "none": "없음 (어떤 λ 에서도 T0 보다 높음)", "NA": "NA"}[t["status"]]
        rows.append([t["arm"] + (" (주)" if t["primary"] else ""), t["contrast"], t["n_scenes"], pct(t["mean_D_at_zero"], True), shown])
    return ("## 2c. 손익분기 λ* (SP 평균이 T0 와 같아지는 λ, zero 모드)\nλ=0(C 와 같음)에서의 평균 D 와, T1(또는 T2)의 장면 평균 SP 가 T0 의 장면 평균 SP(= C)까지 "
            "내려오는 λ. SP 는 0 아래로 내려가지 않으므로 바닥을 반영해 정확한 분수로 푼다. 사전 지정 λ=0.02 는 이 값보다 위인지 아래인지로 읽는다. "
            "실제 비용(끝난 시각, 호출 수, USD)은 5b 표에 나란히 있다.\n\n"
            + (md(["arm", "대비", "n 장면", "λ=0 평균 D (pp)", "손익분기 λ*"], rows) if rows else "자료 없음.\n"))


def cap_table(cells):
    """2d: analysis-only labels (2026-11-16): messages by origin (via) and robots that reached the per-robot cap."""
    rows = []
    for arm, structure in sorted({(c["arm"], c["structure"]) for c in cells if c["structure"] in ("T1", "T2")}):
        ok = [c for c in cells if c["arm"] == arm and c["structure"] == structure and c["state"] == "ok"]
        known = [c for c in ok if c["cap_reached"] is not None]
        capped = [c for c in known if c["cap_reached"]]
        via = [c for c in ok if c["msg_chance"] is not None]
        failing = [c for c in ok if c["C"] == 0]
        rows.append([arm, structure, len(ok), len(known), len(ok) - len(known), len(capped), sum(c["cap_n"] for c in capped),
                     sum(c["msg_decision"] for c in via), sum(c["msg_chance"] for c in via), len(via),
                     sum("not_sent_cap" in c["tags"] for c in failing), len(failing)])
    return ("## 2d. 메시지 상한 도달과 메시지 출처 (분석 전용 꼬리표, 2026-11-16)\n"
            "`상한 도달 칸` = 한 로봇이라도 기록의 `max_messages_per_robot` 개를 다 보낸 칸(기록에 상한 값이 없으면 NA 로 두고 0 으로 읽지 않는다). "
            "`결정/기회` = 메시지 기록의 `via`(기회 = 결정 사이 답장, 키 없음 = 결정·보고 지점에서 행동과 함께 보냄, 사전 교환 포함)로 센 봉투 수. brain-v3 이전 계획기는 `via` 를 안 써서 "
            "기회 메시지도 결정으로 읽히고, 그런 칸은 경고에 올라간다. `not_sent_cap` = 안 보냄 칸 중 필요한 사실을 가진 팀원이 그 로봇의 최종 결정 "
            "시각 전에 상한에 이미 닿은 칸(안 보냄의 일부, 대표 원인 분할에는 영향 없음).\n\n"
            + md(["arm", "구조", "ok 칸", "상한 값 있는 칸", "상한 값 없음(NA)", "상한 도달 칸", "상한 닿은 로봇 수", "메시지 결정", "메시지 기회",
                  "via 읽은 칸", "not_sent_cap 칸", "C=0 칸"], rows))


def type_table(by_type, args):
    rows = [[b["arm"], b["contrast"], b["metric"], b["scene_type"], b["n_scenes"], pct(b["mean_D"], True)]
            for b in by_type if b["metric"] == "C"]
    return ("## 3. 유형별 평균 D (C, zero 모드, 기술 통계. 유형 단위 일반화는 하지 않는다)\n"
            + (md(["arm", "대비", "지표", "장면 유형", "n 장면", "평균 D (pp)"], rows) if rows else "자료 없음.\n"))


def shortfall(cells, book, scenes, args):
    text = ["## 4. 부족분: 정답 계획 기준선 대비와 원인 꼬리표별 몫"]
    oracle = book.scene_means(ORACLE, "C", "zero")
    oracle_s = book.scene_means(ORACLE, "S", "zero")
    n_oracle = sum(1 for c in cells if c["structure"] == ORACLE)
    n_oracle_ok = sum(1 for c in cells if c["structure"] == ORACLE and c["state"] == "ok")
    text.append("기준선(정답 계획 고정 실행) 칸 %d개(완료 %d): C 평균 %s%%, S 평균 %s%% (장면 %d개). %s\n"
                % (n_oracle, n_oracle_ok, pct(mean(list(oracle.values()))), pct(mean(list(oracle_s.values()))), len(oracle),
                   "" if n_oracle else "**기준선 칸 없음: 이 입력에서는 기준선 대비 열이 NA 다(확인 안 됨).**"))
    rows, share = [], []
    for arm, structure in sorted({(c["arm"], c["structure"]) for c in cells if c["structure"] in STRUCTS}):
        c_means = book.scene_means(structure, "C", "zero", arm)
        s_means = book.scene_means(structure, "S", "zero", arm)
        common = sorted(set(c_means) & set(oracle))
        common_s = sorted(set(s_means) & set(oracle_s))
        gap_c = mean([oracle[s] - c_means[s] for s in common])
        gap_s = mean([oracle_s[s] - s_means[s] for s in common_s])
        rows.append([arm, structure, len(c_means), pct(mean(list(c_means.values()))), len(common), pct(gap_c),
                     len(s_means), pct(mean(list(s_means.values()))), len(common_s), pct(gap_s)])
        n, parts = book.cause_partition(structure, arm)
        total = sum(parts.values())
        share.append([arm, structure, n, pct(total)] + [pct(parts[k]) for k in CAUSE_ROWS])
    text.append("### 4a. 정답 계획 대비 (zero 모드, 같은 장면만)\n")
    text.append(md(["arm", "구조", "장면 n(C)", "C 평균%", "기준선과 겹친 장면", "C 부족분 pp", "장면 n(S)", "S 평균%",
                    "겹친 장면(S)", "S 부족분 pp"], rows))
    text.append("\n### 4b. C 부족분(100 − C 평균, pp)을 대표 원인 꼬리표로 나눈 몫 (합이 부족분과 같다)\n"
                "대표 꼬리표 우선순위: 정보 없음(T0) > 받고 무시 > 늦게 도착 > 안 보냄 > 추측 틀림 > 필요한 상자 내려놓음 > 기타. "
                "고장·미완료 칸은 꼬리표가 없어 별도 행이다. 한 칸의 몫은 장면 안 반복 수로 나눈 값이다.\n")
    text.append(md(["arm", "구조", "장면 n", "부족분 pp"] + [CAUSE_TEXT[k] + " pp" for k in CAUSE_ROWS], share))
    tag_rows = []
    for arm, structure in sorted({(c["arm"], c["structure"]) for c in cells if c["structure"] in STRUCTS}):
        failing = [c for c in cells if c["arm"] == arm and c["structure"] == structure and c["state"] == "ok" and c["C"] == 0]
        tag_rows.append([arm, structure, len(failing)] + [sum(t in c["tags"] for c in failing)
                                                         for t in ("not_sent", "late", "ignored", "guess_wrong", "no_info_T0", "dropped_needed", "other",
                                                                   "not_sent_cap")])
    text.append("\n### 4c. 복수 꼬리표 칸 수 (C=0 이고 완료된 칸. 한 칸에 꼬리표가 여럿일 수 있음)\n")
    text.append(md(["arm", "구조", "C=0 칸", "안 보냄", "늦게 도착", "받고 무시", "추측 틀림", "정보 없음(T0)", "필요한 상자 내려놓음", "기타", "안 보냄 중 상한(not_sent_cap)"], tag_rows))
    return "\n".join(text)


def split_table(cells, book, args):
    rows = []
    for arm, structure in sorted({(c["arm"], c["structure"]) for c in cells}):
        group = [c for c in cells if c["arm"] == arm and c["structure"] == structure]
        ok = [c for c in group if c["state"] == "ok"]
        quad = Counter((c["C"], c["S"]) for c in ok)
        p1 = [c for c in ok if c["C"] == 1]
        p0 = [c for c in ok if c["C"] == 0]
        rows.append([arm, structure, len(group), quad[(1, 1)], quad[(1, 0)], quad[(0, 1)], quad[(0, 0)],
                     sum(c["state"] == "plan_na" for c in group), sum(c["state"] in ("failed", "in_progress") for c in group),
                     ratio(sum(c["S"] == 0 for c in p1), len(p1)) if structure != ORACLE else ratio(sum(c["S"] == 0 for c in ok), len(ok)),
                     ratio(sum(c["S"] == 1 for c in p0), len(p0))])
    return ("## 5. 계획 실패와 물리 실패 분리 (칸 수)\nP1/S0 = 계획은 맞고 물리에서 실패, P0/S1 = 계획은 틀렸는데 물리 성공. "
            "기준선(ORACLE) 행의 `P1 중 S=0` 열은 정답 계획에서도 생기는 실행층 실패율(ok 칸 전체 대비)이다.\n\n"
            + md(["arm", "구조", "칸", "P1/S1", "P1/S0", "P0/S1", "P0/S0", "계획 NA", "고장·미완료", "P1 중 S=0", "P0 중 S=1"], rows))


def put_down_table(cells):
    """5c: put-downs (choices dest 'put_down') by kind. Only ok T0/T1/T2 cells have a classification."""
    rows = []
    for arm, structure in sorted({(c["arm"], c["structure"]) for c in cells if c["structure"] in STRUCTS}):
        ok = [c for c in cells if c["arm"] == arm and c["structure"] == structure and c["state"] == "ok"]
        scored = [c for c in ok if c["put_decoy"] is not None]
        holding = [c for c in scored if sum(c[k] for k in PUT_COLUMNS)]
        rows.append([arm, structure, len(ok), len(scored), len(holding), sum(sum(c[k] for k in PUT_COLUMNS) for c in scored)]
                    + [sum(c[k] for c in scored) for k in PUT_COLUMNS]
                    + [ratio(sum(c["C"] == 1 for c in holding), len(holding))])
    head = ["arm", "구조", "ok 칸", "분류된 칸", "내려놓은 칸", "내려놓음 수", "decoy(그 색 주문 없음)", "중복(주문 있고 이미 충족)",
            "손실, 그 로봇이 아는 주문", "손실, 팀원만 아는 주문", "손실, 누가 아는지 불명", "색 불명", "내려놓은 칸 중 C=1"]
    return ("## 5c. 내려놓기(put_down) 분류 (실행 수가 아니라 내려놓음 수, 칸 수는 따로)\n"
            "계획 덮임 C 는 `(색, put_down)` 쌍을 빈 배정으로 센다(주문 없는 상자를 집었다 내려놓아도 그 자체로 틀린 계획이 아니다). "
            "여기서 따로 센다: decoy = 그 색 주문이 장면에 없음, 중복 = 주문이 있고 마지막 계획에서 이미 충족, 손실 = 주문이 있는데 미충족"
            "(한 미충족 주문은 내려놓음 하나에만 매긴다, 로봇 번호 순). 손실은 원인 분해에 꼬리표 `dropped_needed` 로도 들어간다.\n\n"
            + md(head, rows))


def secondary_table(cells):
    rows = []
    for arm, structure in sorted({(c["arm"], c["structure"]) for c in cells}):
        group = [c for c in cells if c["arm"] == arm and c["structure"] == structure]
        done = [c for c in group if c["state"] in ("ok", "plan_na") and isinstance(c["end_s"], (int, float))]
        won = [c["end_s"] for c in done if c["S"]]

        def total(key):
            known = [c[key] for c in done if c[key] is not None]
            return "%s (%d/%d)" % (compare.display(sum(known)) if known else "NA", len(known), len(done))
        rows.append([arm, structure, len(group), len(done), "%s (n=%d)" % (compare.display(median(won)) if won else "NA", len(won)),
                     "%s (n=%d)" % (compare.display(median([c["end_s"] for c in done])) if done else "NA", len(done)),
                     total("messages"), total("llm_calls"), total("cost_usd")])
    return ("## 5b. 보조 지표 (완료된 칸만, 고장 칸은 시간·호출 NA)\n시간은 `end_s` 중앙값(물리 성공 칸만 / 전체 완료 칸), 메시지는 보낸 봉투 수, "
            "호출·비용은 계획기 기록의 합이다. 괄호는 값이 있는 칸 수/완료 칸 수다.\n\n"
            + md(["arm", "구조", "칸", "완료", "시간 중앙값 성공 s", "시간 중앙값 전체 s", "메시지 합", "LLM 호출 합", "USD 합"], rows))


def condition_section(ref, cond, args):
    if ref is None:
        return ("## 6. 조건 비교 (절제·전체 정보 등)\n기준 팔 `%s` 이 입력에 없어 이 절은 비어 있다(확인 안 됨).\n" % args.main_group)
    text = ["## 6. 조건 비교: 기준 팔 `%s` 과 같은 장면 짝 (zero 모드)\nD = (조건 − 기준). 같은 장면·같은 구조끼리만 짝짓는다. "
            "다중비교 보정 없는 탐색 비교다.\n" % ref]
    head = ["조건 팔", "구조", "기준 팔 구조", "지표", "겹친 장면", "+/−/=", "평균 D (pp)", "95% CI (pp)", "p (보정 없음)"]

    def rows_for(kind):
        return [[r["arm"], r["structure"], r["ref_structure"], r["metric"], r["n_scenes"], "%d/%d/%d" % (r["pos"], r["neg"], r["tie"]),
                 pct(r["mean_D"], True), fmt_ci(r["ci95"]), "%.3g" % r["p"]] for r in cond if r["kind"] == kind]
    text.append("### 6a. 절제·팀장 교대·두 번째 모델 등\n")
    rows = rows_for("condition")
    text.append(md(head, rows) if rows else "해당 팔 없음.\n")
    text.append("\n### 6b. 전체 정보 LLM 대비: 정보 전달로 닫히는 간격\nD = (전체 정보 − 구조). 양수면 전체 정보가 더 잘 덮는다.\n")
    rows = rows_for("fullinfo")
    text.append(md(head, rows) if rows else "전체 정보 팔(`%s`) 없음.\n" % args.fullinfo_group)
    return "\n".join(text)


def lists(cells):
    text = ["## 7. 목록"]
    failed = [[c["arm"], c["scene"], c["structure"], c["rep"], c["run_id"], c["state"], c["reason"], c["attempts"]]
              for c in cells if c["state"] in ("failed", "in_progress")]
    text.append("### 고장·실패·진행 중 칸\n" + md(["arm", "장면", "구조", "rep", "run", "상태", "사유", "시도 수"], failed))
    plan_na = [[c["arm"], c["scene"], c["structure"], c["rep"], c["run_id"], c["reason"]] for c in cells if c["state"] == "plan_na"]
    text.append("\n### 계획 NA 칸 (complete 인데 계획을 못 매김)\n" + md(["arm", "장면", "구조", "rep", "run", "사유"], plan_na))
    caps = [[c["arm"], c["scene"], c["structure"], c["rep"], c["run_id"], c["cap_end"], c["halt"]] for c in cells if c["cap_end"]]
    text.append("\n### 호출 상한 도달 (결과, 재실행 대상 아님)\n" + md(["arm", "장면", "구조", "rep", "run", "분류", "멈춤 문구"], caps))
    warn = [[c["arm"], c["scene"], c["structure"], c["rep"], c["run_id"], "; ".join(c["warnings"])] for c in cells if c["warnings"]]
    text.append("\n### 경고\n" + md(["arm", "장면", "구조", "rep", "run", "경고"], warn))
    scored = [c for c in cells if c["state"] in ("ok", "plan_na") and c["structure"] in STRUCTS]
    text.append("\n첫 배정 불명(첫 선택 색을 못 읽음: `finish` 선택 등. 첫 배정 덮임은 보고용 보조 표지라 이 분석의 어느 표도 안 쓴다): "
                "완료 T0/T1/T2 칸 %d개 중 %d개. 정답·고정 계획 칸은 첫 선택이 없어 해당 없음.\n"
                % (len(scored), sum(bool(c["first_unresolved"]) for c in scored)))
    unknown = [[c["run_id"], c["scene_src"]] for c in cells if c["scene"] == "unknown" or "ambiguous" in c["scene_src"]]
    text.append("\n### 장면을 못 읽었거나 모호한 칸 (검정에서 빠짐)\n" + md(["run", "장면 출처"], unknown))
    return "\n".join(text)


CELL_COLUMNS = ["arm", "group", "scene", "scene_type", "control", "structure", "rep", "run_id", "attempts", "state", "reason",
                "complete", "C", "G", "G_strict", "guess_with_msg", "S", "raw_C", "raw_S", "end_s", "messages", "M", "n_robots", "M_max_robot",
                "cap", "cap_reached", "cap_n", "msg_decision", "msg_chance", "planner",
                *PUT_COLUMNS,
                "SP05", "SP02", "SP10", "llm_calls", "cost_usd", "success_class",
                "primary", "tags", "cap_end", "halt", "quadrant", "first_unresolved", "scene_src", "warnings", "source"]


def write_outputs(out, cells, text, tests, by_type, cond, args, inputs):
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(text, encoding="utf-8")
    with (out / "cells.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CELL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for c in sorted(cells, key=lambda c: (c["arm"], c["structure"], c["scene"], c["rep"])):
            writer.writerow({k: ("|".join(v) if k == "tags" else "; ".join(v) if k == "warnings" else
                              float(v) if isinstance(v, Fraction) else v)
                             for k, v in c.items() if k in CELL_COLUMNS})
    meta = {"inputs": inputs, "seed": args.seed, "boots": args.boots, "alpha": ALPHA, "interim": args.interim,
            "plan_na": args.plan_na, "main_group": args.main_group, "modes": list(MODES), "metrics": list(METRICS),
            "penalty": {"allowance_per_robot": PENALTY_ALLOWANCE, "lambdas": {k: str(v) for k, v in PENALTY_LAMBDAS.items()},
                        "primary": PENALTY_PRIMARY}}
    (out / "tests.json").write_text(json.dumps({"meta": meta, "tests": tests, "by_type": by_type, "conditions": cond},
                                               ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def analyze(args):
    scenes = load_scenes(args.scenes)
    cells = build_cells(args, scenes)
    book = Book(cells, args.interim, args.plan_na)
    tests, by_type = run_tests(book, cells, scenes, args)
    ref, cond = condition_rows(book, cells, args)
    inputs = [str(p) for p in args.runs]
    text = render(cells, scenes, book, tests, by_type, ref, cond, args, inputs)
    return cells, text, tests, by_type, cond, inputs


def parse(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=Path, action="append", required=True)
    parser.add_argument("--scenes", type=Path, action="append", required=True)
    parser.add_argument("--brain", type=Path, action="append", default=[])
    parser.add_argument("--manifest", type=Path, action="append", default=[], help="repeatable; rows are merged by run_id (the main analysis must pass it, PREREG 7; RUNBOOK)")
    parser.add_argument("--name", required=True)
    parser.add_argument("--interim", action="store_true", help="leave in-progress / not-started cells out of every mode")
    parser.add_argument("--plan-na", choices=("exclude", "failure"), default="exclude")
    parser.add_argument("--reps", type=int, default=0, help="legacy folders: planned reps per (arm, scene, structure)")
    parser.add_argument("--main-group", default="mainA")
    parser.add_argument("--fullinfo-group", default="fullinfo")
    parser.add_argument("--oracle-group", action="append", default=["baseline"])
    parser.add_argument("--note", default="", help="free text printed under the title (e.g. 'tool trial, not a result')")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--boots", type=int, default=BOOTS)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    for path in args.runs:
        if not path.is_dir():
            raise SystemExit("runs directory does not exist: %s" % path)
    out = (HERE / "out" / args.name).resolve()
    cells, text, tests, by_type, cond, inputs = analyze(args)
    write_outputs(out, cells, text, tests, by_type, cond, args, inputs)
    states = Counter(c["state"] for c in cells)
    print("cells=%d ok=%d plan_na=%d failed=%d in_progress=%d tests=%d out=%s"
          % (len(cells), states["ok"], states["plan_na"], states["failed"], states["in_progress"], len(tests), out))


if __name__ == "__main__":
    main()
