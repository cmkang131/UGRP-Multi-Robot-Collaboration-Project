#!/usr/bin/env python3
"""P2 실행 목록과 사전등록 표를 만들고 대조한다. 시뮬레이터나 모델을 호출하지 않는다.

  python3 tools/make_phase2.py --write
  python3 tools/make_phase2.py --check PREREG-PHASE2.md PREREG-PHASE2-APPENDIX.md

계획서 12판(2026-11-19): 로봇 3대만, 여러 번 나르기(C), 동적 주문 공개. 맵 15개 x 정보 조건 2개(공유 = 전원에게 공개, 국소 = 팀장이 아닌 한 로봇에게만 공개) x 구조 3개(P, L-open, L-star)
= 본 실행 90회. 장면은 mapgen 의 공개 장면 P2R_N03_Sxx(reveal_p2.py: 5aa9e19 장면에서 주문 지식, 공개 블록, 공개 인지 정답 계획만 바꾼 것), 실행층은 exec_config.json 의 커밋(--order-reveal 포함)이다.
맵 확인 전에는 통과 순번(K01-K15)만 쓴다. 동결할 맵의 판정표가 생기면 --gate-results FILE.csv (scene,verdict; scene 은 P2R_N03_Sxx)를
--write와 --check에 같이 준다. 20261121-door/gate-verdicts-aa008ea.csv 가 있으면 인자가 없어도 그 파일을 쓴다(--no-gate-results 로 끈다).
정답 계획이 없는 시드(reveal_manifest.json 의 no_reveal_plan_seeds)는 맵 확인에서 탈락으로 센다.
--measure는 1차 기록의 재집계다.
"""
import argparse
import ast
import csv
import glob
import hashlib
import io
import json
import os
import random
import re
import shlex
import statistics as st
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

sys.dont_write_bytecode = True
LS = Path(__file__).resolve().parents[1]
CW = LS.parent
MAN = LS / "manifests"
MAPGEN = CW / "20261117-phase2-mapgen"
CATALOG = MAPGEN / "manifest.json"
CATALOG_SHA = "a5f279e8e788bbc1bfebde8fbc0bc0f9042844d15824b85897c248fbf852b0d4"       # manifest.json of mapgen 5aa9e19
GATE_VERDICTS = CW / "20261121-door/gate-verdicts-aa008ea.csv"       # (scene,verdict) rows of the aa008ea map gate on the P2R scenes with the reveal-aware reference plan (byte-identical to 20261121-final/gate-verdicts.csv from a58dad1)
REVEAL_MANIFEST = MAPGEN / "reveal_manifest.json"
REVEAL_MANIFEST_SHA = "95cf5e575158d84071e44a53441505d936ea1d5c76220ed89568c58d1d18db84"   # sha256 of mapgen reveal_manifest.json at e374572 (the 35 P2R scenes, leader, recipient, T_reveal)
REVEAL_PY = MAPGEN / "reveal_p2.py"
VM_SCENES = Path(os.environ.get("BOXNET_IMAGE_SCENES", "scenes"))
COST_CELLS = CW / "20261115-compare-analysis/out/main3-v38-final-20261117/cells.csv"
OPT_TREE = CW / "20261118-exec-opt/student-opt"
EXEC = json.loads((Path(__file__).resolve().parent / "exec_config.json").read_text(encoding="utf-8"))   # executor commit and option list: the one place to update
EXEC_COMMIT = EXEC["commit"]       # phase2/exec-opt at the time of the last edit of exec_config.json; the option declarations are read from this commit, not from the worktree
DOCS = (LS / "PREREG-PHASE2.md", LS / "PREREG-PHASE2-APPENDIX.md")
FILES = {"main": "phase2-main.csv", "pilot": "phase2-pilot.csv"}
GROUPS = {"main": "p2core", "pilot": "p2pilot"}
SIZES = (3,)             # plan v11: three robots only. The mapgen catalog still holds 6- and 9-robot files (CATALOG_SIZES); they are not used
CATALOG_SIZES = (3, 6)   # sizes whose catalog entries are validated by read_catalog (the gate tool make_gate_manifest.py reads both)
N_ROBOTS = 3
MAX_SEED = 60            # plan v11 candidates are seeds 1-60; the committed catalog holds 1-40 (24 main + 16 reserve), 41-60 are not generated yet
CAP_S = EXEC["cap_s"]    # simulated-time cap (mapgen MULTI.md: 7 of 80 oracle plans exceed 900 s, the longest 949.9 s)
WALL_CAP_S = EXEC["wall_cap_s"]
SIM_SECONDS = (925, CAP_S)   # cost table lengths: the median completion of the reveal-aware reference plans (35 maps: 925 s) and the cap
SLOTS = 15
INFOS = ("shared", "local")                  # shared (control) = the two new orders and the rule go to all three robots; local (treatment) = to ONE robot that is not the leader
INFO_TAG = {"shared": "SHR", "local": "LOC"}
ORDER_REVEAL = {"shared": "all", "local": "recipient"}     # run_team_carry.py --order-reveal
LEADER_REP = 1                                # the election seed of a map is fixed by its scene (reveal.leader_seed = elect_seed(scene id, 1)): the same for every row of the map, pilot rounds too
MAIN_REP = 2                                  # 2026-11-22 (task 7, user decision "A"): restart all 90 main runs after checkpoint stop of -r1 (runs/p2f-main-a, excluded); suffix -r2 avoids collisions while keeping LEADER_REP = 1 unchanged
CLOUD_RATE = {3: Decimal("0.1728")}       # USD per hour: Cloud Run job 2 vCPU/6 GiB (CPU 0.000018 USD/vCPU-s, memory 0.000002 USD/GiB-s)
WALL_PER_SIM = {3: Decimal("6")}          # wall s per simulated s: plan v11 uses the VM measurement of 5.6-7 for the speed switches (about 2 h per 1,200 s run); a final oracle smoke replaces it
ARMS = ("P", "L-open", "L-star")           # P = equal team (T1); L-open = assigning leader, anyone may talk to anyone (T2); L-star = L-open plus members talk to the leader only
ARM_TAG = {"P": "P", "L-open": "LOPEN", "L-star": "LSTAR"}
TEAM = {"P": "T1", "L-open": "T2", "L-star": "T2"}
ROTATIONS = tuple(ARMS[i:] + ARMS[:i] for i in range(3))     # Latin square over three structures: each structure in each position of the run order
CELLS = tuple((info, arm) for info in INFOS for arm in ARMS)          # the six cells of a map
PILOT_ROUNDS = (          # one map (K01) x six cells per batch (6 runs), at most 6 batches (the third added 2026-11-21 18:31 KST by the user's decision, after batches 1 and 2; batches 4, 5 and 6 under the 2026-11-21 22:37 KST user approval, after batches 3, 4 and 5). The order inside a batch: info block order and structure rotation differ between the batches
    tuple((info, arm) for info in ("shared", "local") for arm in ("P", "L-open", "L-star")),
    tuple((info, arm) for info in ("local", "shared") for arm in ("L-open", "L-star", "P")),
    tuple((info, arm) for info in ("shared", "local") for arm in ("L-star", "P", "L-open")),
    tuple((info, arm) for info in ("local", "shared") for arm in ("P", "L-star", "L-open")),        # batch 4 added 2026-11-21 22:37 KST by the user's approval, after batch 3 (door deadlocks of batch 3, 20261121-door)
    tuple((info, arm) for info in ("shared", "local") for arm in ("L-open", "P", "L-star")),        # batch 5 added 2026-11-22 KST under the 2026-11-21 22:37 KST user approval, after batch 4 (P-shared retreat-into-sign11 scoring defect and L-star duplicate-request-id 400, 20261121-door)
    tuple((info, arm) for info in ("local", "shared") for arm in ("L-star", "L-open", "P")),        # batch 6 added 2026-11-22 KST under the 2026-11-21 22:37 KST user approval, after batch 5 (dropped-ledger ghost points blocking the door in L-star shared and P-local, 20261121-door)
)
COLUMNS = ("run_id", "group", "scene_file", "scene_id", "team", "rep", "robots", "leader",
           "model", "vm_args", "server_args", "sha", "vmrun", "seed", "arm", "slot",
           "pilot_round", "selected", "map_seed", "scene_sha256")
VM_ARGS = "%s --cap-s %d --wall-cap-s %d" % (EXEC["vm_options"], CAP_S, WALL_CAP_S)
LLM_ONLY = EXEC.get("llm_only_options", "")       # options of the main and pilot rows (LLM planner) that a fixed-plan map-gate row cannot take: --empty-park needs --order-reveal (run_team_carry.py), the gate rows have none. 2026-11-21
CALL_CEILING = 450        # plan v11: LLM calls per run (150 per robot x 3, the --max-calls default); brain.llm.HARD_EPISODE_CALLS (600) is the hard limit above it
FREE = ("--parser-fix --merge-calls --options-v2 --temperature 0.7 --talk free "
        "--no-message-budget --say-fix-s 1.45 --say-per-char-s 0.0036 --msg-delay-s 2 "
        "--read-fix-s 0.7 --read-per-char-s 0.0018 --multi-carry")
LEADER = "--leader-election --leader-authority --leader-bind --hold-s 75"     # L-open; L-star adds --leader-route star
STAR = "--leader-route star"
MODEL = "z-ai/glm-5.3-flash"
# The frozen planner's election regression imports these two fixture paths.
SRC = {"L3": CW / "20261116-scenes3/scenes3_main.json", "S3": CW / "20261117-precedence/scenes_s3.json"}


def elect_seed(scene_id, rep):
    return zlib.crc32(f"elect|{scene_id}|{rep}".encode()) % (2 ** 31)


def elect(scene, seed):
    counts = {rid: len(set(orders)) for rid, orders in scene["knows"].items()}
    top = max(counts.values())
    tied = sorted(rid for rid, count in counts.items() if count == top)
    return tied[seed % len(tied)], counts, len(tied) > 1


def require(test, message):
    if not test:
        raise ValueError(message)


def read_catalog():
    raw = CATALOG.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == CATALOG_SHA, "mapgen 5aa9e19의 manifest.json 해시 불일치")
    doc = json.loads(raw)
    entries = {}
    for key, seeds in (("scenes", range(1, 25)), ("reserve_scenes", range(25, 41))):
        rows = doc[key]
        require(sorted((r["n"], r["seed"]) for r in rows) == [(n, s) for n in CATALOG_SIZES for s in seeds],
                f"생성기 {key}의 규모·시드 목록 불일치")
        for r in rows:
            sid = f"P2_N{r['n']:02d}_S{r['seed']:02d}"
            require(r["scene_id"] == sid and r["status"] == "ok", f"생성 기록 불일치 {sid}")
            entries[sid] = r
    return entries


def reveal_module():
    """mapgen reveal_p2.py (read only), loaded by path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("reveal_p2", REVEAL_PY)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(MAPGEN))
    spec.loader.exec_module(module)
    return module


def read_reveal_catalog():
    """The P2R scenes of mapgen reveal_manifest.json: {scene id: entry}; the seeds without a reveal-aware reference plan are listed in no_plan."""
    raw = REVEAL_MANIFEST.read_bytes()
    if not REVEAL_MANIFEST_SHA.startswith("TODO"):
        require(hashlib.sha256(raw).hexdigest() == REVEAL_MANIFEST_SHA, "mapgen reveal_manifest.json 해시 불일치")
    doc = json.loads(raw)
    entries = {r["scene_id"]: r for r in doc["scenes"]}
    require(len(entries) == len(doc["scenes"]) and doc["n_robots"] == N_ROBOTS, "공개 장면 목록 형식 불일치")
    require(sorted(set(r["seed"] for r in doc["scenes"]) | set(doc["no_reveal_plan_seeds"])) == list(range(1, 41)), "공개 장면 목록의 시드가 1–40을 덮지 않습니다")
    return entries, set(doc["no_reveal_plan_seeds"])


def selected_maps(catalog, gate_path, no_plan=()):
    """Maps by pass order: the first SLOTS seeds (in seed order) whose gate verdict is PASS. {(n, slot): reveal catalog entry}. The gate runs the P2R scenes with the reveal-aware reference plan
    (a map gate on the source scene does not transfer: the plan is another). A seed without a reveal-aware plan (no_plan) has no P2R scene and counts as FAIL; it needs no verdict row."""
    if gate_path is None:
        return {}
    with gate_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        require({"scene", "verdict"} <= set(rows.fieldnames or []), "맵 판정표에 scene,verdict가 필요합니다")
        verdicts = {}
        for row in rows:
            sid, verdict = row["scene"], row["verdict"]
            require(sid in catalog and sid not in verdicts and verdict in ("PASS", "FAIL"),
                    f"판정표의 장면·중복·판정값을 확인하세요 {sid!r} {verdict!r} (장면은 P2R_N03_Sxx)")
            verdicts[sid] = verdict
    selected = {}
    for n in SIZES:
        slot = 0
        for seed in range(1, MAX_SEED + 1):
            if seed in no_plan:
                continue                                  # no reveal-aware plan: fails by construction
            sid = f"P2R_N{n:02d}_S{seed:02d}"
            require(sid in catalog, f"{sid}가 생성 목록에 없습니다. 계획서 후보는 시드 1–{MAX_SEED}이고 생성 목록은 1–40이므로 생성기로 더 만들어야 합니다 (통과 {slot}개)")
            require(sid in verdicts, f"{sid} 판정 누락. 뒤 시드로 건너뛸 수 없습니다")
            if verdicts[sid] == "PASS":
                slot += 1
                selected[n, slot] = catalog[sid]
                if slot == SLOTS:
                    break
        require(slot == SLOTS, f"{n}대 시드 {MAX_SEED}까지 통과 {slot}개. 선정 보류")
    return selected


def make_row(stage, slot, arm, info, selected, pilot_round=0):
    n = N_ROBOTS
    key = f"N{n:02d}-K{slot:02d}"
    entry = selected.get((n, slot))
    sid = entry["scene_id"] if entry else f"TODO-P2R_N{n:02d}_K{slot:02d}"
    scene_path = Path(entry["file"]) if entry else Path("scenes_reveal") / f"{sid}.json"
    rep = (pilot_round + 1) if stage == "pilot" else MAIN_REP
    args = shlex.split(FREE) + ["--scene-file", str(MAPGEN / scene_path), "--scene-id", sid, "--order-reveal", "--score-rule"]
    # The leader is fixed first, per map: one election seed for L-open and L-star (and every repetition) = the scene's reveal.leader_seed. The recipient of the local condition is chosen by the scene
    # among the robots that are not that leader, and is the same robot number in all three structures (P too) and both conditions.
    if arm != "P":
        args += shlex.split(LEADER) + ["--leader-seed", str(elect_seed(sid, LEADER_REP))]
    if arm == "L-star":
        args += shlex.split(STAR)
    return dict(run_id=f"P2-{stage.upper()}-{key}-{ARM_TAG[arm]}-{INFO_TAG[info]}-r{rep}", group=GROUPS[stage],
                scene_file=str(VM_SCENES / scene_path.name), scene_id=sid,
                team=TEAM[arm], rep=str(rep),
                robots=",".join(f"r{i}" for i in range(1, n + 1)), leader="r1", model=MODEL,
                vm_args=f"{VM_ARGS} --order-reveal {ORDER_REVEAL[info]}" + (f" {LLM_ONLY}" if LLM_ONLY else ""), server_args=shlex.join(args), sha=EXEC_COMMIT,
                vmrun="run_team_v38.sh", seed="90721", arm=arm, slot=str(slot),
                pilot_round=str(pilot_round) if pilot_round else "", selected="yes" if entry else "pending",
                map_seed=str(entry["seed"]) if entry else "", scene_sha256=entry["sha256"] if entry else "")


def info_of(row):
    return next(i for i in INFOS if row["run_id"].split("-")[-2] == INFO_TAG[i])


def build(selected):
    """Main list: 15 maps x 2 information conditions x 3 structures = 90. The six runs of a map form two blocks of three (one per information condition), each a cyclic rotation of
    (P, L-open, L-star); both blocks of a map use the same rotation. The rotations are dealt to the maps 5 each and the information block that comes first 8 / 7 (shared first 8 times, local first 7 times;
    15 maps cannot be split evenly); the map order is shuffled; seed 20261119."""
    rng = random.Random(20261119)
    rotation_of = [i % 3 for i in range(SLOTS)]
    rng.shuffle(rotation_of)
    first_info = [INFOS[i % 2] for i in range(SLOTS)]
    rng.shuffle(first_info)
    slots = list(range(1, SLOTS + 1))
    rng.shuffle(slots)
    main = []
    for slot in slots:
        order = (first_info[slot - 1], INFOS[1 - INFOS.index(first_info[slot - 1])])
        for info in order:
            for arm in ROTATIONS[rotation_of[slot - 1]]:
                main.append(make_row("main", slot, arm, info, selected))
    pilot = [make_row("pilot", 1, arm, info, selected, rnd) for rnd, cells in enumerate(PILOT_ROUNDS, 1) for info, arm in cells]
    return {"main": main, "pilot": pilot}


def replace_text(path, content):
    if path.exists() and path.read_bytes() == content.encode():
        return
    with NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", newline="", delete=False) as tmp:
        tmp.write(content)
    output = Path(tmp.name)
    output.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o644)
    output.replace(path)


def csv_text(rows, columns=COLUMNS):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def runs_block(data):
    counts = Counter((stage, info_of(r), r["arm"]) for stage, rows in data.items() for r in rows)
    lines = ["|목록|정보 조건|P|L-open|L-star|행 수|", "|---|---|---:|---:|---:|---:|"]
    for stage, label in (("main", f"본 실행(맵 {SLOTS}개)"), ("pilot", "시험 최대(맵 1개)")):
        for info, name in (("shared", "공유(전원에게 공개)"), ("local", "국소(팀장이 아닌 한 로봇에게만 공개)")):
            per = [counts[stage, info, arm] for arm in ARMS]
            lines.append(f"|{label}|{name}|" + "|".join(str(v) for v in per) + f"|{sum(per)}|")
    lines += [f"|**본 실행 합계**|||||**{len(data['main'])}**|", f"|시험 자리 합계|||||최대 {len(data['pilot'])}|"]
    return "\n".join(lines)


def pilot_block(rows):
    rounds = defaultdict(list)
    for row in rows:
        rounds[int(row["pilot_round"])].append(f"{INFO_TAG[info_of(row)]}-{row['arm']}")
    lines = ["|시험 묶음|여섯 실행을 준비하는 순서 (맵 1개 x 정보 2조건 x 구조 3개; SHR = 공유, LOC = 국소)|", "|---:|---|"]
    lines.extend(f"|{rnd}|{', '.join(cells)}|" for rnd, cells in sorted(rounds.items()))
    return "\n".join(lines)


def rounded(value, places):
    return f"{value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP):.{places}f}"


def cost_block(data):
    # the column titles come from SIM_SECONDS (they were hard-coded 800 / 1,200 and mislabelled the 925 s / cap columns; 2026-11-21)
    lines = ["|대수·실행 환경|단가(USD/시간)|벽초/시뮬초|" + "|".join(f"{t:,} 시뮬초 벽시간(h)|{t:,}초 비용(USD/회)" for t in SIM_SECONDS) + "|",
             "|---|---:|---:|---:|---:|---:|---:|"]
    cost = {}
    shape = {3: "2 vCPU·6 GiB"}
    for n in SIZES:
        hours = [WALL_PER_SIM[n] * t / 3600 for t in SIM_SECONDS]
        cost[n] = [h * CLOUD_RATE[n] for h in hours]
        lines.append(f"|{n}대 · Cloud Run {shape[n]}|{CLOUD_RATE[n]}|{WALL_PER_SIM[n]}|" +
                     "|".join(v for h in hours for v in (rounded(h, 2), rounded(h * CLOUD_RATE[n], 2))) + "|")
    lines += [""]
    for stage, label in (("main", f"본 실행 {len(data['main'])}회"), ("pilot", f"시험 {len(data['pilot'])}자리를 모두 쓸 때")):
        counts = Counter(len(r["robots"].split(",")) for r in data[stage])
        total = [sum(counts[n] * cost[n][i] for n in SIZES) for i in (0, 1)]
        lines.append(f"- {label}의 컴퓨팅 비용은 모두 {SIM_SECONDS[0]}초면 {rounded(total[0], 2)}달러, "
                     f"모두 {SIM_SECONDS[1]:,}초면 {rounded(total[1], 2)}달러다.")
    return "\n".join(lines)


def llm_block():
    lines = ["|1차 main3 구조|실행|LLM 호출|기록 비용 합(USD)|USD/실행|", "|---|---:|---:|---:|---:|"]
    with COST_CELLS.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["group"] == "main3" and r["structure"] in ("T1", "T2")]
    for label, subset in (("T1", [r for r in rows if r["structure"] == "T1"]),
                          ("T2", [r for r in rows if r["structure"] == "T2"]), ("합계", rows)):
        require(subset and all(r["state"] == "ok" and r["cost_usd"] and r["llm_calls"] for r in subset),
                f"{label}의 1차 호출 비용 기록 누락")
        calls = sum(int(r["llm_calls"]) for r in subset)
        cost = sum(Decimal(r["cost_usd"]) for r in subset)
        lines.append(f"|{label}|{len(subset)}|{calls:,}|{rounded(cost, 6)}|{rounded(cost / len(subset), 6)}|")
    return "\n".join(lines)


def exec_block():
    return (f"- 실행층 커밋: `{EXEC_COMMIT}` (`{EXEC['branch']}`)\n- 실행층 공통 옵션: `{VM_ARGS}`, 공유 조건은 `--order-reveal all`, 국소 조건은 `--order-reveal recipient`를 더한다."
            + (f" LLM 행(본 실행·시험)에는 맵 확인 행에 없는 `{LLM_ONLY}`도 더한다(공개 모드가 필요한 옵션)." if LLM_ONLY else "") + "\n"
            f"- 계획기 공통 옵션: `{FREE} --order-reveal --score-rule`\n"
            f"- P: `--team T1`. L-open: `--team T2 {LEADER} --leader-seed S`. L-star: L-open 옵션에 `{STAR}`를 더한다. S는 한 맵의 L-open과 L-star에서(두 정보 조건에서도, 반복에서도) 같고 장면의 `reveal.leader_seed`와 같다.")


def blocks(data):
    return {"RUNS": runs_block(data), "COST": cost_block(data), "LLM": llm_block(),
            "PILOT": pilot_block(data["pilot"]), "EXEC": exec_block()}


def doc_tables(paths, tables, fill=False):
    texts = {p: p.read_text(encoding="utf-8") for p in paths}
    if len(texts) == 1:
        filename = next(iter(texts)).name
        if filename == DOCS[0].name:
            tables = {name: table for name, table in tables.items() if name != "PILOT"}
        elif filename == DOCS[1].name:
            tables = {"PILOT": tables["PILOT"]}
    for name, expected in tables.items():
        begin, end = f"<!-- {name}-BEGIN -->", f"<!-- {name}-END -->"
        owners = [p for p, txt in texts.items() if begin in txt or end in txt]
        require(len(owners) == 1, f"문서 블록 {name}이 없거나 여러 문서에 있습니다")
        p = owners[0]
        txt = texts[p]
        require(txt.count(begin) == txt.count(end) == 1 and txt.index(begin) < txt.index(end), f"{name} 표식 오류")
        before, tail = txt.split(begin)
        old, after = tail.split(end)
        if fill:
            texts[p] = before + begin + "\n" + expected + "\n" + end + after
        else:
            require(old == "\n" + expected + "\n", f"{p.name}의 {name} 표와 재계산 불일치")
    if fill:
        for p, txt in texts.items():
            replace_text(p, txt)
    return tables.keys()


def measure():
    ev = CW / "20261115-batch/evidence/physical"
    el, ot, it, oc = [], [], [], []
    team_el = defaultdict(list)
    for f in glob.glob(str(ev / "M3-*/llm-calls.jsonl")):
        team = f.split("/")[-2].split("-")[2]
        for line in open(f):
            j = json.loads(line)
            if j.get("event") == "finish" and j.get("status") == "ok" and j.get("output_tokens") and j.get("input_tokens"):
                el.append(j["elapsed_s"]); ot.append(j["output_tokens"]); it.append(j["input_tokens"]); oc.append(j["output_chars"])
                team_el[team].append(j["elapsed_s"])
    X = [[1.0, o, i] for o, i in zip(ot, it)]
    A = [[sum(r[i] * r[j] for r in X) for j in range(3)] for i in range(3)]
    b = [sum(r[i] * y for r, y in zip(X, el)) for i in range(3)]
    for i in range(3):
        p = A[i][i]
        A[i] = [x / p for x in A[i]]
        b[i] /= p
        for r in range(3):
            if r != i:
                f = A[r][i]
                A[r] = [x - f * y for x, y in zip(A[r], A[i])]
                b[r] -= f * b[i]
    lens = []
    for f in glob.glob(str(ev / "M3-*-T[12]-r*/brain-record.json")):
        for m in json.load(open(f)).get("messages") or []:
            lens.append(len(m.get("text") or ""))
    lens.sort()
    q = lambda p, v: v[int(p * (len(v) - 1))]
    print("calls %d | elapsed median %.2f p90 %.2f | OLS const %.3f s, %.4f s/output token, %.2e s/input token | chars/token %.2f" %
          (len(el), st.median(el), q(.9, sorted(el)), b[0], b[1], b[2], sum(oc) / sum(ot)))
    for t in sorted(team_el):
        print("  %s n=%d median %.2f" % (t, len(team_el[t]), st.median(team_el[t])))
    print("messages %d | chars median %d mean %.0f p90 %d p99 %d" % (len(lens), st.median(lens), st.mean(lens), q(.9, lens), q(.99, lens)))




def check_catalog(catalog, planner):
    """Validate the candidate files of the sizes this experiment uses (SIZES). The 6-robot files stay in the catalog but are not used."""
    used = {sid: e for sid, e in catalog.items() if e["n"] in SIZES}
    for sid, entry in used.items():
        path = MAPGEN / entry["file"]
        require(hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], f"{sid} 장면 해시 불일치")
        scene = planner.load_scene(path, sid)
        robots = {f"r{i}" for i in range(1, entry["n"] + 1)}
        orders = {o["id"] for o in scene["orders"]}
        require(scene["n_robots"] == entry["n"] and scene["seed"] == entry["seed"] and
                set(scene["knows"]) == robots and len(orders) == 5 * entry["n"] // 3 and
                len(scene["boxes"]) == len(orders) and
                all(set(known) == orders for known in scene["knows"].values()), f"{sid} 주문 공유 불일치")
        rules = scene["constraints"]
        require(len(rules) == entry["n"] // 3 and entry["doors"] == entry["n"] // 3 and
                all(set(rule["known_by"]) == robots for rule in rules) and
                set(planner.scene_rules(path, sid)) == robots, f"{sid} 순서 규칙 또는 문 수 불일치")
    seeds = sorted(e["seed"] for e in used.values())
    print(f"OK  P2 3대 후보 {len(used)}개(시드 {seeds[0]}–{seeds[-1]}) 파일 해시, 상자·주문 5개, 전원의 주문·규칙 대조 (맵 통과 판정은 별도). "
          f"계획서 11판의 후보는 시드 1–{MAX_SEED}이며 {seeds[-1] + 1}–{MAX_SEED}는 생성 목록에 없음(확인 안 됨)")


def check_reveal_catalog(reveal_catalog, no_plan, planner):
    """Validate the P2R scenes (mapgen reveal_p2.py): file hash, the scene checker (the source scene passes check_p2, the scene equals it except for the reveal changes, the reveal-aware reference plan is
    recomputed), nobody is told the rule at the start, three initial orders for every robot, the planner reads the two hidden orders, the leader is fixed first by the map's election seed and the
    recipient is another robot."""
    reveal = reveal_module()
    for sid, entry in reveal_catalog.items():
        path = MAPGEN / entry["file"]
        require(hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], f"{sid} 장면 해시 불일치")
        scene = planner.load_scene(path, sid)
        errors = reveal.check_scene(scene)
        require(not errors, f"{sid} 공개 장면 검사 실패: {errors[:2]}")
        block, robots = scene["reveal"], [r["rid"] for r in scene["robots"]]
        require(robots == ["r1", "r2", "r3"] and all(len(k) == 3 for k in scene["knows"].values()) and
                len({tuple(k) for k in scene["knows"].values()}) == 1 and len(scene["orders"]) == 5 and len(scene["boxes"]) == 5, f"{sid} 처음 주문 3개 공유 불일치")
        require(planner.scene_rules(path, sid) == {} and len(planner.scene_reveal_orders(path, sid)) == 2, f"{sid} 시작 때 규칙이 알려지거나 공개 주문을 읽지 못함")
        require(block["leader_seed"] == elect_seed(sid, LEADER_REP) == entry["leader_seed"] and block["leader"] == elect(scene, block["leader_seed"])[0] == entry["leader"]
                and block["recipient"] != block["leader"] and block["recipient"] == entry["recipient"], f"{sid} 팀장·받는 로봇 불일치")
    for seed in no_plan:
        require(f"P2R_N03_S{seed:02d}" not in reveal_catalog, f"시드 {seed}는 정답 계획이 없는데 공개 장면이 있습니다")
    pairs = Counter((e["leader"], e["recipient"]) for e in reveal_catalog.values())
    print(f"OK  공개 장면 {len(reveal_catalog)}개(정답 계획 없는 시드 {sorted(no_plan)}): 파일 해시, 장면 검사, 시작 때 규칙 비공개·처음 주문 3개, 팀장 시드·받는 로봇(팀장 제외) 대조. "
          f"(팀장, 받는 로봇) 조합 {len(pairs)}가지")


def option_names():
    """Option names the pinned executor commit declares (AST walk over add_argument calls; the physical runner is neither imported nor started)."""
    names = set()
    for file in ("scripts/run_team_carry.py", "harness/exec_opt.py"):
        source = subprocess.run(["git", "-C", str(OPT_TREE), "show", f"{EXEC_COMMIT}:{file}"], capture_output=True, text=True, check=True).stdout
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_argument":
                names.update(arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
    return names


def check_rows(data, planner, reveal_catalog):
    rows = data["main"] + data["pilot"]
    ids = {r["run_id"] for r in rows}
    require(len(ids) == len(rows), "실행 ID 중복")
    for path in MAN.glob("*.csv"):
        if path.name not in FILES.values():
            with path.open(encoding="utf-8", newline="") as f:
                require(not ids.intersection(r["run_id"] for r in csv.DictReader(f)), f"{path.name}과 ID 중복")
    require(all(len(r["robots"].split(",")) == N_ROBOTS for r in rows), "3대가 아닌 행이 있습니다")
    groups = defaultdict(list)
    for r in data["main"]:
        groups[int(r["slot"])].append(r)
    require(set(groups) == set(range(1, SLOTS + 1)), f"통과 순번 1–{SLOTS} 불일치")
    same = ("scene_id", "scene_file", "scene_sha256", "map_seed", "seed", "rep", "model", "sha", "robots", "leader")
    strip = lambda text: " ".join(re.sub(r"--order-reveal \S+", "", text).split())
    for slot, six in groups.items():
        require(sorted((info_of(r), r["arm"]) for r in six) == sorted(CELLS) and all(six[0][v] == t[v] for t in six for v in same) and
                len({strip(t["vm_args"]) for t in six}) == 1, f"순번 {slot} 장면 묶음 불일치 (여섯 칸, 같은 장면·시드·옵션)")
        require(all(shlex.split(t["vm_args"])[shlex.split(t["vm_args"]).index("--order-reveal") + 1] == ORDER_REVEAL[info_of(t)] for t in six),
                f"순번 {slot}: 정보 조건과 --order-reveal 값이 맞지 않습니다")
        leader_seeds = {tokens[tokens.index("--leader-seed") + 1] for tokens in (shlex.split(r["server_args"]) for r in six if r["arm"] != "P")}
        require(len(leader_seeds) == 1 and leader_seeds == {str(elect_seed(six[0]["scene_id"], LEADER_REP))},
                f"순번 {slot}: 팀장 시드가 L-open·L-star·두 정보 조건에서 같지 않거나 장면 시드와 다릅니다")
        entry = reveal_catalog.get(six[0]["scene_id"])
        if entry:
            require(leader_seeds == {str(entry["leader_seed"])} and entry["recipient"] != entry["leader"], f"순번 {slot}: 장면의 팀장 시드나 받는 로봇이 다릅니다")
    # Latin square of structures: the two blocks of a map (one per information condition) have the same rotation; each structure takes each block position exactly SLOTS/3 times.
    # The information condition that comes first: 15 maps cannot be split evenly, so 8 / 7.
    positions, first = Counter(), Counter()
    for slot in groups:
        by_order = [r for r in data["main"] if int(r["slot"]) == slot]           # list order is the run order of that map
        require([r["arm"] for r in by_order[:3]] == [r["arm"] for r in by_order[3:]] and len({info_of(r) for r in by_order[:3]}) == 1 and
                len({info_of(r) for r in by_order[3:]}) == 1 and info_of(by_order[0]) != info_of(by_order[3]), f"순번 {slot}: 실행 순서가 정보 조건 두 묶음이 아닙니다")
        first[info_of(by_order[0])] += 1
        for pos, r in enumerate(by_order):
            positions[pos % 3, r["arm"]] += 1
    require(all(positions[pos, arm] == 2 * (SLOTS // 3) for pos in range(3) for arm in ARMS) and sorted(first.values()) == [SLOTS // 2, SLOTS - SLOTS // 2],
            f"구조 실행 순서가 라틴 방진으로 균형 잡히지 않았거나 먼저 도는 정보 조건이 {first}입니다 {dict(positions)}")
    rounds = range(1, len(PILOT_ROUNDS) + 1)
    require(Counter(r["pilot_round"] for r in data["pilot"]) == {str(i): 6 for i in rounds} and
            all(sorted((info_of(r), r["arm"]) for r in data["pilot"] if r["pilot_round"] == str(i)) == sorted(CELLS) for i in rounds), "시험 묶음 불일치 (맵 1개 x 여섯 칸, 최대 %d묶음)" % len(PILOT_ROUNDS))
    require(all(int(r["slot"]) == 1 for r in data["pilot"]) and len({r["scene_id"] for r in data["pilot"]}) == 1, "시험은 맵 1개(K01)여야 합니다")
    print(f"OK  본 실행 {len(data['main'])}행 ({SLOTS}맵 x 정보 2조건 x 구조 3개), 맵 안 여섯 행의 장면·시드·옵션 일치, 팀장 시드 한 맵에서 같음(L-open·L-star·두 조건), 정보 조건 블록 두 개, "
          f"구조 순서 라틴 방진(블록 안 위치별 구조당 {2 * (SLOTS // 3)}회, 두 블록 합), 먼저 도는 정보 조건 {dict(first)}, 시험 {len(data['pilot'])}행(맵 1개 x 여섯 칸 x 최대 {len(PILOT_ROUNDS)}묶음), 실행 ID {len(rows)}개 고유")

    names = option_names()
    for r in rows:
        tokens = shlex.split(r["vm_args"])
        flags = {s for s in tokens if s.startswith("--")}
        require(flags <= names and "--physics-dt-ms" not in flags and "--fixed" not in flags and
                set(EXEC["required_flags"]) <= flags and "--order-reveal" in names and
                tokens[tokens.index("--regrasp-max") + 1] == "1" and tokens[tokens.index("--cap-s") + 1] == str(CAP_S)
                and tokens[tokens.index("--render-segments") + 1] == "12" and tokens[tokens.index("--overhead-every") + 1] == "10"
                and int(tokens[tokens.index("--wall-cap-s") + 1]) == WALL_CAP_S and r["sha"] == EXEC_COMMIT,
                f"{r['run_id']} 실행층 옵션 불일치")
        args = planner.parse_args(["--team", r["team"], "--robots", r["robots"], "--leader", r["leader"],
                                   "--model", r["model"], "--port", "1", "--log-dir", "."] + shlex.split(r["server_args"]))
        leader = r["arm"] != "P"
        require(r["team"] == TEAM[r["arm"]] and args.talk == "free" and args.no_message_budget and args.say_fix_s == 1.45 and
                args.say_per_char_s == 0.0036 and args.leader_authority == leader and args.leader_bind == leader and
                args.leader_election == leader and args.hold_s == 75 and ("--hold-s" in shlex.split(r["server_args"])) == leader and
                args.leader_route == ("star" if r["arm"] == "L-star" else None) and
                args.leader_seed == (elect_seed(r["scene_id"], LEADER_REP) if leader else None) and args.order_reveal and args.score_rule and
                args.multi_carry and args.max_input_bytes is None and not args.map_doors and
                args.scene_id == r["scene_id"] and args.scene_file.name == Path(r["scene_file"]).name and
                planner.run_ceiling(args.max_calls, N_ROBOTS) == CALL_CEILING,
                f"{r['run_id']} 계획기 조건 불일치")
    print(f"OK  {len(rows)}행 계획기 인자 파싱(P: T1, L-open: T2 + 선출·권한·구속·대기 75초, L-star: L-open + --leader-route star, --multi-carry, --order-reveal, --score-rule, "
          f"실행당 호출 상한 {CALL_CEILING}), 실행층 옵션 선언(--order-reveal 포함)을 {EXEC_COMMIT[:7]}에서 대조, 물리 옵션 없음")


def check(data, catalog, reveal_catalog, no_plan, docs, final=False):
    sys.path.insert(0, str(CW / "20261115-batch"))
    sys.path.insert(0, str(LS / "link"))
    import brain_server
    import dispatch

    require({p.name for p in MAN.glob("phase2-*.csv")} == set(FILES.values()), "활성 phase2 CSV 목록 불일치")
    saved = {}
    for stage, name in FILES.items():
        path = MAN / name
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            require(reader.fieldnames == list(COLUMNS), f"{name} 열 불일치")
            saved[stage] = list(reader)
        require(saved[stage] == data[stage], f"{name}와 새로 만든 목록 불일치")
        # Only this format check knows the two P2 groups. load_manifest reads CSV; it dispatches no jobs.
        with patch.object(dispatch, "ALL_GROUPS", (*dispatch.ALL_GROUPS, *GROUPS.values())):
            require(len(dispatch.load_manifest(path)) == len(data[stage]), f"{name} 배치 형식 오류")
            if final:      # scenes picked by the gate: no placeholder may be left, a real run must load
                require(len(dispatch.load_manifest(path, real=True)) == len(data[stage]), f"{name}에 동결 전 표시가 남았습니다")
            else:
                try:
                    dispatch.load_manifest(path, real=True)
                except ValueError as exc:
                    require("placeholder" in str(exc), f"{name} 동결 전 표시 이외의 오류 {exc}")
                else:
                    raise ValueError(f"{name}에 동결 전 표시가 없습니다")
        print(f"OK  {name} {len(data[stage])}행 재생성 일치, 배치 형식 통과, " + ("장면 확정(자리표시 없음)" if final else "미동결 표시 확인"))
    check_rows(saved, brain_server, reveal_catalog)
    check_catalog(catalog, brain_server)
    check_reveal_catalog(reveal_catalog, no_plan, brain_server)
    checked = doc_tables(docs, blocks(saved))
    print(f"OK  문서 {' / '.join(checked)} 표와 CSV·비용 계산 일치")
    print("ALL OK")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--write", action="store_true")
    p.add_argument("--blocks", action="store_true")
    p.add_argument("--fill-doc", type=Path, nargs="+")
    p.add_argument("--check", type=Path, nargs="*", help="기본값은 사전등록 본문과 부록")
    p.add_argument("--measure", action="store_true")
    p.add_argument("--gate-results", type=Path, help="맵 확인 판정표 CSV (scene,verdict; scene 은 P2R_N03_Sxx); 없으면 20261121-door/gate-verdicts-aa008ea.csv 가 있을 때 그것")
    p.add_argument("--no-gate-results", action="store_true", help="판정표 없이 자리표시 목록을 만든다")
    args = p.parse_args()
    if args.measure:
        measure()
    if not (args.write or args.blocks or args.fill_doc or args.check is not None):
        if not args.measure:
            p.print_help()
        return
    catalog = read_catalog()
    reveal_catalog, no_plan = read_reveal_catalog()
    gate = None if args.no_gate_results else (args.gate_results or (GATE_VERDICTS if GATE_VERDICTS.exists() else None))
    if gate is not None:
        print(f"맵 판정표 {gate}")
    chosen = selected_maps(reveal_catalog, gate, no_plan)
    data = build(chosen)
    if args.write:
        for stage, rows in data.items():
            replace_text(MAN / FILES[stage], csv_text(rows))
            print(f"{FILES[stage]} {len(rows)}행")
    if args.blocks:
        for name, table in blocks(data).items():
            print(f"<!-- {name}-BEGIN -->\n{table}\n<!-- {name}-END -->")
    if args.fill_doc:
        doc_tables(args.fill_doc, blocks(data), fill=True)
    if args.check is not None:
        check(data, catalog, reveal_catalog, no_plan, args.check or DOCS, final=bool(chosen))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"FAIL  {error}")
