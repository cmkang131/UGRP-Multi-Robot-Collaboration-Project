#!/usr/bin/env python3
"""Phase-3 run lists: 12 maps x 4 cells x 2 repetitions = 96 rows (manifests/phase3-main.csv) and the four cells once on map S10 (manifests/phase3-check.csv).

  python3 tools/make_phase3.py                                  checks the lists and prints the counts (writes nothing)
  python3 tools/make_phase3.py --write [--plan-format assign|execute]
  python3 tools/make_phase3.py --check [--plan-format assign|execute]     the files on disk are the generated lists

Every row is the phase-2 "shared" condition (executor --order-reveal all, planner --order-reveal) built by make_phase2.make_row. The planner arguments per cell:
  PP  the phase-2 P row (no leader)
  LL  the phase-2 L-open row (leader election, authority, binding, 75 s hold; the leader seed is the scene's reveal.leader_seed)
  LP  LL + --authority-until reveal
  PL  LL + --authority-from reveal
--plan-format execute adds --plan-format execute to LL, LP and PL (not PP). The default, assign, adds nothing.
Scene files: the phase-2 manifest names them under <home>/hybrid/scenes-p2gate; the local source is the mapgen scenes_reveal file, whose sha256 and leader seed are checked here.
The rows are written as make_phase2 writes its rows (same columns); the dispatcher must register the groups p3core and p3chk (as 20261118-cloudrun-p2 does for p2core).

v8 (task T3, PLAN-v8 sections 4 and 5): python3 tools/make_phase3.py --event exchange [--write | --check] writes manifests/phase3v8-main.csv (11 maps S22..S34 x 4 cells x 2 repetitions = 88 rows,
run ids P3V8-Sxx-<CELL>-r<rep>) and manifests/phase3v8-check.csv (S10, 4 cells x 3 repetitions = 12 rows, P3V8CHK-S10-<CELL>-r<rep>). The v7 lists are not touched by it.
  every v8 row: --event exchange (planner), --reveal-trigger holders (executor, vm_args); the executor's scene_file and the planner's --scene-file are <home>/hybrid/scenes-p2gate/P2R_N03_<sid>.json (T6: the image path that build_p2.sh --scenes-dir fills); scene_sha256 is the v8 file's sha256
  LL, LP, PL: no --plan-format argument, as the v7 assign rows (T9: the default for v8 is assign, because the real-model check of the EXECUTE format failed, 0 of 9 answers); --plan-format execute is an explicit option only; plus the switch of LP and PL as in v7
  sha: --exec-sha <40 lowercase hex> gives the executor commit (T7); without it the placeholder PENDING-V8-EXEC-COMMIT stays and --check reports NOT DISPATCHABLE and exits 1.

Use --design v10 --write or --check for the 99 main rows and six S10 checks pinned to the v8 runner inputs.
Use --design v11 for 16 CMAS private-news runs and two S10 checks with a single reveal recipient.
Use --design v11-two-structures to retain V11's superseded four-map DMAS/CMAS list for regression fixtures only.
Use --design v11-budget --budgets N,M --write --check for the private, automatic-relay output-token comparison.
Use --design v11-static-budget --budgets N,M --write --check for the fixed final orders in tools/scenes-v11-static/.
"""
import argparse
import copy
import csv
import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_phase2 as P2                                        # reads exec_config.json; make_row, the option strings, the column list, the reveal catalog

LS = Path(__file__).resolve().parents[1]
MAN = LS / "manifests"
MAIN_FILE = "phase3-main.csv"
CHECK_FILE = "phase3-check.csv"
REFERENCE = "phase2-main.reference.csv"
MAPS = ("S22", "S24", "S25", "S26", "S27", "S29", "S30", "S31", "S32", "S33", "S34", "S36")      # the task's map order (the interim tool takes the first six)
CHECK_MAP = "S10"
CELLS = ("PP", "LL", "LP", "PL")
REPS = (1, 2)
PLAN_FORMATS = ("assign", "execute")
GROUP = {"main": "p3core", "check": "p3chk"}
PREFIX = {"main": "P3", "check": "P3CHK"}
CELL_ARM = {"PP": "P", "LL": "L-open", "LP": "L-open", "PL": "L-open"}            # the make_row structure of each cell (make_row needs a phase-2 arm)
SWITCH = {"LP": ["--authority-until", "reveal"], "PL": ["--authority-from", "reveal"]}
LEADER_CELLS = ("LL", "LP", "PL")


def scene_entry(sid, catalog):
    """The reveal-catalog entry of a scene, after the checks that its local source file exists, has the recorded sha256, and that its reveal block holds the leader seed of
    the catalog and of make_phase2 (elect_seed). Stops with ValueError otherwise; no path is invented."""
    entry = catalog[sid]
    local = P2.MAPGEN / entry["file"]
    if not local.exists():
        raise ValueError(f"scene file missing: {local} (map {sid}); stop and report")
    raw = local.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise ValueError(f"scene file sha256 differs from the reveal catalog: {local}")
    scene = next(s for s in json.loads(raw)["scenes"] if s["id"] == sid)
    seed = int(scene["reveal"]["leader_seed"])
    if seed != int(entry["leader_seed"]) or seed != P2.elect_seed(sid, P2.LEADER_REP):
        raise ValueError(f"leader seed of {sid} differs: reveal block {seed}, catalog {entry['leader_seed']}, elect_seed {P2.elect_seed(sid, P2.LEADER_REP)}")
    return entry


def cell_row(stage, slot, entry, cell, rep, plan_format):
    """One row: make_row (phase 2, shared condition) with the phase-3 identity, the cell's planner arguments and the plan format."""
    sid = entry["scene_id"]
    base = P2.make_row("main", slot, CELL_ARM[cell], "shared", {(P2.N_ROBOTS, slot): entry})         # make_row's stage only sets its own run id and group, both replaced below
    tokens = shlex.split(base["server_args"])
    if cell in LEADER_CELLS and plan_format == "execute":
        tokens += ["--plan-format", "execute"]
    tokens += SWITCH.get(cell, [])
    short = sid.rsplit("_", 1)[1]
    row = dict(base)
    row.update(run_id=f"{PREFIX[stage]}-{short}-{cell}-r{rep}", group=GROUP[stage], arm=cell, slot=str(slot), rep=str(rep), selected="yes", pilot_round="",
               server_args=shlex.join(tokens))
    return row


def build_files(catalog, plan_format="assign"):
    """{file name: rows}. Main: the maps in MAPS order, inside a map repetition 1 (PP, LL, LP, PL) then repetition 2. Check: the four cells once on CHECK_MAP."""
    main = []
    for slot, short in enumerate(MAPS, 1):
        entry = scene_entry(f"P2R_N03_{short}", catalog)
        for rep in REPS:
            for cell in CELLS:
                main.append(cell_row("main", slot, entry, cell, rep, plan_format))
    entry = scene_entry(f"P2R_N03_{CHECK_MAP}", catalog)
    check = [cell_row("check", 1, entry, cell, 1, plan_format) for cell in CELLS]
    return {MAIN_FILE: main, CHECK_FILE: check}


def read_reference():
    with (MAN / REFERENCE).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(P2.COLUMNS):
            raise ValueError("reference manifest columns differ from make_phase2.COLUMNS")
        return list(reader)


def reference_row(rows, arm_tag, info_tag="SHR"):
    """The first phase-2 row of a structure in the shared condition (run ids P2-MAIN-N03-Kxx-<ARM>-SHR-r2)."""
    return next(r for r in rows if r["run_id"].startswith("P2-MAIN-") and f"-{arm_tag}-{info_tag}-" in r["run_id"])


ALLOWED_F2 = {"--scene-file": "scene file", "--scene-id": "scene id", "--leader-seed": "leader seed"}


def token_diff(a, b):
    """The differing tokens of two planner argument strings with the same shape: [(flag, a value, b value)]. A difference outside a value of ALLOWED_F2 raises ValueError."""
    ta, tb = shlex.split(a), shlex.split(b)
    if len(ta) != len(tb) or [t for t in ta if t.startswith("--")] != [t for t in tb if t.startswith("--")]:
        raise ValueError("the argument strings differ in shape")
    out = []
    for i, (x, y) in enumerate(zip(ta, tb)):
        if x == y:
            continue
        flag = ta[i - 1] if i else ""
        if flag not in ALLOWED_F2:
            raise ValueError(f"differs outside the allowed fields: {flag or x!r}: {x!r} vs {y!r}")
        out.append((flag, x, y))
    return out


def without_plan_format(text):
    """The planner arguments without the --plan-format pair (F2 and F3 are about the base condition; F4 checks the pair)."""
    tokens = shlex.split(text)
    at = [i for i in range(len(tokens) - 1) if tokens[i:i + 2] == ["--plan-format", "execute"]]
    if at:
        tokens = tokens[:at[0]] + tokens[at[0] + 2:]
    return shlex.join(tokens)


def check_rows(files, reference):
    """F1 to F3 of the task file (raises ValueError) and the F2 diffs. Returns the report lines."""
    main, check = files[MAIN_FILE], files[CHECK_FILE]
    if len(main) != 96 or len({r["run_id"] for r in main}) != 96:
        raise ValueError("F1: the main list needs 96 rows with unique run ids")
    combos = {(r["scene_id"], r["arm"], r["rep"]) for r in main}
    expected = {(f"P2R_N03_{s}", c, str(k)) for s in MAPS for c in CELLS for k in REPS}
    if combos != expected or len({r["scene_id"] for r in main}) != 12:
        raise ValueError("F1: maps x cells x repetitions are not 12 x 4 x 2")
    if len(check) != 4 or [r["run_id"] for r in check] != [f"P3CHK-{CHECK_MAP}-{c}-r1" for c in CELLS]:
        raise ValueError("the check list needs the four cells once on S10 with run ids P3CHK-S10-<CELL>-r1")
    if set(P2.COLUMNS) != set(main[0]) or list(main[0]) != list(P2.COLUMNS):
        raise ValueError("columns differ from the phase-2 manifest")
    by = {(r["scene_id"], r["arm"], r["rep"]): r for r in main}
    lines = []
    ref_p, ref_l = reference_row(reference, "P"), reference_row(reference, "LOPEN")
    for cell, ref in (("PP", ref_p), ("LL", ref_l)):
        row = by[("P2R_N03_S22", cell, "1")]
        if row["vm_args"] != ref["vm_args"]:
            raise ValueError(f"F2: vm_args of {cell} differ from {ref['run_id']}")
        diff = token_diff(ref["server_args"], without_plan_format(row["server_args"]))
        lines.append(f"F2 {cell} S22 r1 vs {ref['run_id']}: vm_args equal; server_args differ in " + ", ".join(f"{f} {x} -> {y}" for f, x, y in diff))
        if cell == "PP" and any(f == "--leader-seed" for f, _x, _y in diff):
            raise ValueError("F2: a P row carries a leader seed")
    for scene in {r["scene_id"] for r in main}:
        for rep in REPS:
            ll = by[(scene, "LL", str(rep))]
            for cell, extra in (("LP", SWITCH["LP"]), ("PL", SWITCH["PL"])):
                row = by[(scene, cell, str(rep))]
                if any(row[k] != ll[k] for k in P2.COLUMNS if k not in ("run_id", "arm", "server_args")):
                    raise ValueError(f"F3: {cell} differs from LL in a column other than run_id, arm and server_args ({scene} r{rep})")
                if shlex.split(row["server_args"]) != shlex.split(ll["server_args"]) + extra:       # both carry the plan format of their list, if any
                    raise ValueError(f"F3: {cell} is not LL plus {extra} ({scene} r{rep})")
    lines.append("F3 LP and PL differ from LL of the same map and repetition only by the added switch (checked for all 12 maps x 2 repetitions)")
    return lines


def check_plan_format(execute, default):
    """F4: execute adds exactly --plan-format execute to LL, LP and PL and nothing to PP, and changes no other column."""
    for a, b in zip(default, execute):
        if a["run_id"] != b["run_id"]:
            raise ValueError("F4: the lists are not in the same order")
        same_cols = all(a[k] == b[k] for k in P2.COLUMNS if k != "server_args")
        if not same_cols:
            raise ValueError(f"F4: a column other than server_args changed in {a['run_id']}")
        ta, tb = shlex.split(a["server_args"]), shlex.split(b["server_args"])
        if a["arm"] == "PP":
            if ta != tb or "--plan-format" in tb:
                raise ValueError("F4: PP changed")
            continue
        pair = ["--plan-format", "execute"]
        at = [i for i in range(len(tb) - 1) if tb[i:i + 2] == pair]
        if len(at) != 1 or tb.count("--plan-format") != 1 or tb[:at[0]] + tb[at[0] + 2:] != ta:
            raise ValueError(f"F4: {a['run_id']} is not the default plus exactly --plan-format execute")
    return True



# ---- v8 (tasks T3, T6, T7) -----------------------------------------------------------------------------------------------------------------------------------------------------
EVENTS = ("none", "exchange")
V8_MAPS = ("S22", "S24", "S25", "S26", "S27", "S29", "S30", "S31", "S32", "S33", "S34")          # PLAN-v8 section 5 (S36 is a reserve, not listed)
V8_CHECK_MAP = "S10"
V8_MAIN_REPS = (1, 2)
V8_CHECK_REPS = (1, 2, 3)
V8_MAIN_FILE = "phase3v8-main.csv"
V8_CHECK_FILE = "phase3v8-check.csv"
V8_SCENES = LS / "scenes"                                                                          # the v8 scene files (task T1); build_p2.sh --scenes-dir copies them into the image
V8_IMAGE_SCENES = Path(os.environ.get("BOXNET_IMAGE_SCENES", "scenes"))                                        # inside the v8 image (T6): build_p2.sh puts --scenes-dir into hybrid/scenes-p2gate; the executor's scene_file and the planner's --scene-file both name it
V8_PHASE2_SCENES = P2.MAPGEN / "scenes_reveal"                                                     # the phase-2 scene files of the same names: the sha256 guard must differ from them
V8_PLACEHOLDER_SHA = "PENDING-V8-EXEC-COMMIT"                                                      # until --exec-sha gives the executor commit (T7); the dispatcher's real-run check does not refuse it
V8_SHA40 = re.compile(r"[0-9a-f]{40}")                                                             # git's full commit id: 40 lowercase hex characters
V8_GROUP = {"main": "p3v8core", "check": "p3v8chk"}
V8_PREFIX = {"main": "P3V8", "check": "P3V8CHK"}
V8_RULE = ("Change of orders: the order <blue box> to <sign11 zone> is withdrawn. A blue box set down at the sign11 zone no longer counts, unless it had already passed the door when this message arrived. "
           "Rule of this task: the <red box> for the <sign11 zone> must be set down at its zone BEFORE the <blue box> for the <sign12 zone> is set down at its zone. A box set down earlier than that does not count as delivered.")
V8_RELEASE_FLAG = ("--reveal-trigger", "holders")
V8_EVENT_FLAG = ("--event", "exchange")


def v8_scene_entry(sid, catalog):
    """The v8 scene of a map (scenes/P2R_N03_<sid>.json): equal to the original mapgen scene once the two v8 keys are removed from both, the rule sentence is V8_RULE, the reveal block
    withdraws o2 and its leader seed equals the catalog's and elect_seed. Its sha256 is the v8 file's. Stops with ValueError otherwise."""
    entry = catalog[sid]
    local = V8_SCENES / f"P2R_N03_{sid.rsplit('_', 1)[1]}.json"
    if not local.exists():
        raise ValueError(f"v8 scene file missing: {local} (map {sid}); stop and report")
    raw = local.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    original = json.loads((P2.MAPGEN / entry["file"]).read_text(encoding="utf-8"))
    for d in (doc, original):
        d["scenes"][0]["reveal"].pop("rule_sentence", None)
        d["scenes"][0]["reveal"].pop("withdrawn_orders", None)
    if doc != original:
        raise ValueError(f"v8 scene {local} differs from the original mapgen scene outside the two v8 keys")
    reveal = json.loads(raw.decode("utf-8"))["scenes"][0]["reveal"]
    if reveal.get("rule_sentence") != V8_RULE or reveal.get("withdrawn_orders") != ["o2"]:
        raise ValueError(f"v8 scene {local}: rule_sentence or withdrawn_orders is not the v8 one")
    seed = int(reveal["leader_seed"])
    if seed != int(entry["leader_seed"]) or seed != P2.elect_seed(sid, P2.LEADER_REP):
        raise ValueError(f"leader seed of {sid} differs: reveal block {seed}, catalog {entry['leader_seed']}, elect_seed {P2.elect_seed(sid, P2.LEADER_REP)}")
    return dict(entry, local=local, sha256=hashlib.sha256(raw).hexdigest(), leader_seed=seed)


def v8_row(stage, slot, entry, cell, rep, plan_format, sha=V8_PLACEHOLDER_SHA):
    """One v8 row. The planner arguments are the phase-2 ones (make_row: FREE, the scene, the leader of the L cells, the cell's switch) with the image scene path (T6), --event exchange
    and, for the leader cells, --plan-format execute only when plan_format is execute (T9: the default is assign, which adds nothing); vm_args are make_row's with --reveal-trigger holders. scene_file and the planner's --scene-file are the same image path;
    scene_sha256 is the v8 file's sha256 (the guard against the phase-2 scene of the same name); sha is the executor commit (T7) or the placeholder."""
    sid = entry["scene_id"]
    short = sid.rsplit("_", 1)[1]
    image_scene = str(V8_IMAGE_SCENES / f"P2R_N03_{short}.json")
    tokens = shlex.split(P2.FREE) + ["--scene-file", image_scene, "--scene-id", sid, "--order-reveal", "--score-rule"]
    if cell != "PP":
        tokens += shlex.split(P2.LEADER) + ["--leader-seed", str(entry["leader_seed"])]
    tokens += list(V8_EVENT_FLAG)
    if cell in LEADER_CELLS and plan_format == "execute":
        tokens += ["--plan-format", "execute"]
    tokens += SWITCH.get(cell, [])
    vm_args = f"{P2.VM_ARGS} --order-reveal {P2.ORDER_REVEAL['shared']}" + (f" {P2.LLM_ONLY}" if P2.LLM_ONLY else "") + " " + " ".join(V8_RELEASE_FLAG)
    row = {column: "" for column in P2.COLUMNS}
    row.update(run_id=f"{V8_PREFIX[stage]}-{short}-{cell}-r{rep}", group=V8_GROUP[stage], scene_file=image_scene, scene_id=sid,
               team=P2.TEAM[CELL_ARM[cell]], rep=str(rep), robots=",".join(f"r{i}" for i in range(1, P2.N_ROBOTS + 1)), leader="r1", model=P2.MODEL,
               vm_args=vm_args, server_args=shlex.join(tokens), sha=sha, vmrun="run_team_v38.sh", seed="90721", arm=cell, slot=str(slot),
               pilot_round="", selected="yes", map_seed=str(entry["seed"]), scene_sha256=entry["sha256"])
    return row


def build_v8_files(catalog, plan_format="assign", sha=V8_PLACEHOLDER_SHA):
    """{file name: rows}: main = the 11 maps in PLAN-v8 order, inside a map repetition 1 (PP, LL, LP, PL) then repetition 2; check = S10, repetition 1..3 with the four cells."""
    main = []
    for slot, short in enumerate(V8_MAPS, 1):
        entry = v8_scene_entry(f"P2R_N03_{short}", catalog)
        for rep in V8_MAIN_REPS:
            for cell in CELLS:
                main.append(v8_row("main", slot, entry, cell, rep, plan_format, sha))
    entry = v8_scene_entry(f"P2R_N03_{V8_CHECK_MAP}", catalog)
    check = [v8_row("check", 1, entry, cell, rep, plan_format, sha) for rep in V8_CHECK_REPS for cell in CELLS]
    return {V8_MAIN_FILE: main, V8_CHECK_FILE: check}


def without_flag(tokens, flag, value):
    """The token list without the first occurrence of the pair flag value (used for the --event and --plan-format pairs)."""
    for i in range(len(tokens) - 1):
        if tokens[i] == flag and tokens[i + 1] == value:
            return tokens[:i] + tokens[i + 2:]
    return tokens


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_v8(files, reference, plan_format, sha=V8_PLACEHOLDER_SHA):
    """The v8 checks (tasks T3, T6 and PLAN-v8 section 4). Raises ValueError; returns the report lines."""
    main, check = files[V8_MAIN_FILE], files[V8_CHECK_FILE]
    if len(main) != 88 or len({r["run_id"] for r in main}) != 88:
        raise ValueError("V8: the main list needs 88 rows with unique run ids")
    expected_main = [f"P3V8-{s}-{c}-r{k}" for s in V8_MAPS for k in V8_MAIN_REPS for c in CELLS]
    if [r["run_id"] for r in main] != expected_main:
        raise ValueError("V8: the main run ids are not the 11 maps x 2 repetitions x 4 cells in order")
    if len(check) != 12 or [r["run_id"] for r in check] != [f"P3V8CHK-{V8_CHECK_MAP}-{c}-r{k}" for k in V8_CHECK_REPS for c in CELLS]:
        raise ValueError("V8: the check list needs S10, four cells, repetitions 1 to 3 (12 rows) with run ids P3V8CHK-S10-<CELL>-r<rep>")
    ref_p, ref_l = reference_row(reference, "P"), reference_row(reference, "LOPEN")
    for group, rows in (("main", main), ("check", check)):
        for r in rows:
            text = " ".join(str(v) for v in r.values())
            if "20261117-phase2-mapgen" in text:
                raise ValueError(f"V8: {r['run_id']} names the phase-2 mapgen folder")
            if r["sha"] != sha or r["group"] != V8_GROUP[group]:
                raise ValueError(f"V8: {r['run_id']}: sha or group")
            name = f"P2R_N03_{r['scene_id'].rsplit('_', 1)[1]}.json"
            image_scene = str(V8_IMAGE_SCENES / name)
            if r["scene_file"] != image_scene:
                raise ValueError(f"V8: {r['run_id']} scene_file is not the image path {image_scene}")
            tokens = shlex.split(r["server_args"])
            if tokens.count("--event") != 1 or tokens[tokens.index("--event") + 1] != "exchange":
                raise ValueError(f"V8: {r['run_id']} needs --event exchange once")
            if r["vm_args"].count(" ".join(V8_RELEASE_FLAG)) != 1:
                raise ValueError(f"V8: {r['run_id']} needs {' '.join(V8_RELEASE_FLAG)} in vm_args once")
            planner = tokens[tokens.index("--scene-file") + 1]
            if planner != image_scene or Path(planner).name != Path(r["scene_file"]).name:
                raise ValueError(f"V8: {r['run_id']} planner --scene-file is not the image scene of the same name (preflight: same basename as scene_file)")
            if r["scene_sha256"] != sha256_of(V8_SCENES / name):
                raise ValueError(f"V8: {r['run_id']} scene_sha256 is not the sha256 of the v8 file {name}")
            if r["scene_sha256"] == sha256_of(V8_PHASE2_SCENES / name):
                raise ValueError(f"V8: {r['run_id']} scene_sha256 equals the phase-2 file {name}")
            has_pf = ["--plan-format", "execute"] in [tokens[i:i + 2] for i in range(len(tokens) - 1)]
            if plan_format == "execute" and has_pf != (r["arm"] in LEADER_CELLS):
                raise ValueError(f"V8: {r['run_id']} plan format does not follow PLAN-v8 section 4")
            if plan_format == "assign" and has_pf:
                raise ValueError(f"V8: {r['run_id']} has a plan format but the list is assign")
    by = {(r["scene_id"], r["arm"], r["rep"]): r for r in main}
    for s in V8_MAPS:
        for k in V8_MAIN_REPS:
            ll = by[(f"P2R_N03_{s}", "LL", str(k))]
            for cell, extra in (("LP", SWITCH["LP"]), ("PL", SWITCH["PL"])):
                row = by[(f"P2R_N03_{s}", cell, str(k))]
                if shlex.split(row["server_args"]) != shlex.split(ll["server_args"]) + extra:
                    raise ValueError(f"V8: {cell} is not LL plus {extra} ({s} r{k})")
                if any(row[c] != ll[c] for c in P2.COLUMNS if c not in ("run_id", "arm", "server_args")):
                    raise ValueError(f"V8: {cell} differs from LL in a column other than run_id, arm and server_args ({s} r{k})")
    lines = ["V8 the main list: 88 rows, 11 maps in PLAN-v8 order, 4 cells x 2 repetitions; check list: 12 rows (S10, 4 cells x 3 repetitions)"]
    for row, ref, label in ((by[("P2R_N03_S22", "PP", "1")], ref_p, "PP"), (by[("P2R_N03_S22", "LL", "1")], ref_l, "LL")):
        if row["vm_args"] != ref["vm_args"] + " " + " ".join(V8_RELEASE_FLAG):
            raise ValueError(f"V8: vm_args of {label} differ from {ref['run_id']} plus --reveal-trigger holders")
        mine = without_flag(without_flag(shlex.split(row["server_args"]), *V8_EVENT_FLAG), "--plan-format", "execute")
        diff = token_diff(ref["server_args"], shlex.join(mine))
        lines.append(f"V8 {label} S22 r1 vs {ref['run_id']}: vm_args equal plus the reveal trigger; planner args differ only in " + ", ".join(f"{f} {x} -> {y}" for f, x, y in diff)
                     + " (and --event exchange; the plan-format argument of the leader cells is added only with --plan-format execute)")
    lines.append("V8 LP and PL differ from LL only by the added switch; every row has --event exchange, --reveal-trigger holders, the image scene path of its own map, and the v8 scene sha256")
    return lines


def dispatch_status(files):
    """(dispatchable, line): every row of both v8 files must carry a 40-hex executor commit in the sha column. The dispatcher's own real-run check refuses TODO and PLACEHOLDER only,
    so the placeholder would pass it: this status is the guard."""
    rows = files[V8_MAIN_FILE] + files[V8_CHECK_FILE]
    open_rows = [r["run_id"] for r in rows if not V8_SHA40.fullmatch(r["sha"])]
    if open_rows:
        return False, (f"NOT DISPATCHABLE: {len(open_rows)} of {len(rows)} rows have no executor commit (sha {rows[0]['sha']}); pass --exec-sha <40 lowercase hex> "
                       "when the executor commit with --reveal-trigger exists")
    return True, f"DISPATCHABLE: all {len(rows)} rows carry the executor commit {rows[0]['sha']}"


def on_disk_sha():
    """The one executor sha that the v8 files on disk carry (all rows of both files), when it is 40 lowercase hex; None otherwise (a missing file, mixed values, the placeholder)."""
    values = set()
    for name in (V8_MAIN_FILE, V8_CHECK_FILE):
        if not (MAN / name).exists():
            return None
        with (MAN / name).open(encoding="utf-8", newline="") as stream:
            values |= {r["sha"] for r in csv.DictReader(stream)}
    if len(values) == 1 and V8_SHA40.fullmatch(next(iter(values))):
        return next(iter(values))
    return None


def main_v8(a):
    plan_format = a.plan_format or "assign"                      # T9: the v8 default is assign (the v7 rows carry no plan-format argument)
    sha = a.exec_sha
    if sha is None and a.check and not a.write:                  # --check without --exec-sha compares with the commit the files carry (the placeholder if they carry none)
        sha = on_disk_sha()
    sha = sha or V8_PLACEHOLDER_SHA
    catalog, _no_plan = P2.read_reveal_catalog()
    files = build_v8_files(catalog, plan_format, sha)
    for line in check_v8(files, read_reference(), plan_format, sha):
        print("OK  " + line)
    if a.write:
        for name, rows in files.items():
            P2.replace_text(MAN / name, P2.csv_text(rows))
            print(f"wrote {MAN / name} ({len(rows)} rows, plan format {plan_format}, event exchange, sha {sha})")
    if a.check:
        for name, rows in files.items():
            if (MAN / name).read_bytes() != P2.csv_text(rows).encode():
                raise ValueError(f"{name} on disk differs from the generated list")
        print("OK  the v8 files on disk equal the generated lists")
    dispatchable, status = dispatch_status(files)
    print(status)
    return 1 if (a.check and not dispatchable) else 0


V10_CELLS = ("DMAS", "CMAS", "HMAS2")


def build_v10_files():
    """Take runner inputs from the actual v8 manifests. Verify the scene bytes and pinned executor before emitting rows."""
    sha = on_disk_sha()
    if not sha:
        raise ValueError("the two v8 manifests must pin one executor commit")
    files = {}
    for stage, maps, reps, source, group, prefix in (
            ("main", V8_MAPS, (1, 2, 3), V8_MAIN_FILE, "p3v10core", "P3V10"),
            ("check", (V8_CHECK_MAP,), (1, 2), V8_CHECK_FILE, "p3v10chk", "P3V10CHK")):
        with (MAN / source).open(newline="") as stream:
            reference = {r["scene_id"]: r for r in csv.DictReader(stream) if r["arm"] == "PP" and r["rep"] == "1"}
        rows = []
        for slot, short in enumerate(maps, 1):
            sid = f"P2R_N03_{short}"
            base = reference[sid]
            local = V8_SCENES / Path(base["scene_file"]).name
            if sha256_of(local) != base["scene_sha256"] or "--reveal-trigger holders" not in base["vm_args"]:
                raise ValueError(f"{sid}: v8 scene or trigger mismatch")
            common = ["--frameworks", "v10", "--multi-carry", "--order-reveal", "--event", "exchange", "--score-rule",
                      "--scene-file", base["scene_file"], "--scene-id", sid, "--temperature", "0.7", "--msg-delay-s", "0"]
            for rep in reps:
                for cell in V10_CELLS:
                    peer = cell == "DMAS"
                    flags = common + ["--protocol", "peer-roco" if peer else "hub-hmas2"]
                    if cell == "CMAS":
                        flags += ["--hub-rounds", "0"]
                    rows.append(dict(base, run_id=f"{prefix}-{short}-{cell}-r{rep}", group=group, arm=cell,
                                     team="T1" if peer else "T2", rep=str(rep), slot=str(slot), server_args=shlex.join(flags)))
        files[f"phase3v10-{stage}.csv"] = rows
    return files


# V11B supersedes V11's four-map, two-structure list.  The confirmation is
# preregistered as one CMAS pair per map, in this fixed map order.
V11_MAPS = ("S22", "S24", "S25", "S26", "S27", "S29", "S30", "S31")
V11_CELLS = ("CMAS",)
V11_RELAYS = ("none", "choice")
V11_BUDGET_MAPS = ("S22", "S24", "S25", "S26")
V11_BUDGET_CELLS = ("DMAS", "CMAS")
STATIC_SCENES = LS / "tools" / "scenes-v11-static"


def build_private_files(maps, cells, stem="phase3v11", *, budgets=None):
    variants = [(relay, f"--relay {relay}", {}) for relay in V11_RELAYS]
    if budgets is not None:
        variants = [(f"b{n}", f"--relay auto --max-output-tokens {n} --truncation-attempts 3",
                     {"max_output_tokens": str(n)}) for n in budgets]
    files = {}
    for stage, maps, group, prefix in (("main", maps, "p3v11", "P3V11"),
                                       ("check", (V8_CHECK_MAP,), "p3v11chk", "P3V11CHK")):
        if budgets is not None:
            prefix, group = "P3V11B", "p3v11budget" if stage == "main" else "p3v11budgetchk"
        with (MAN / f"phase3v10-{stage}.csv").open(newline="") as stream:
            reference = {(r["scene_id"], r["arm"]): r for r in csv.DictReader(stream) if r["rep"] == "1"}
        rows = []
        for short in maps:
            sid = f"P2R_N03_{short}"
            for cell in cells:
                base = reference[sid, cell]
                local = V8_SCENES / Path(base["scene_file"]).name
                if sha256_of(local) != base["scene_sha256"] or not V8_SHA40.fullmatch(base["sha"]):
                    raise ValueError(f"{sid}: v10 scene or executor pin mismatch")
                scene = next(s for s in json.loads(local.read_bytes())["scenes"] if s["id"] == sid)
                recipient = scene["reveal"]["recipient"]
                robots = base["robots"].split(",")
                if recipient not in robots:
                    raise ValueError(f"{sid}: reveal recipient {recipient} is outside the roster")
                leader = min((r for r in robots if r != recipient), key=lambda r: int(r[1:]))
                vm = shlex.split(base["vm_args"])
                reveal = vm.index("--order-reveal") + 1
                if vm[reveal] != "all" or vm[vm.index("--reveal-trigger") + 1] != "holders":
                    raise ValueError(f"{sid}: unexpected v10 reveal options")
                vm[reveal] = "recipient"
                for suffix, flags, columns in variants:
                    rows.append(dict(base, run_id=f"{prefix}-{short}-{cell}-{suffix}", group=group,
                                     leader=leader, recipient=recipient, vm_args=shlex.join(vm),
                                     server_args=base["server_args"] + f" --news private {flags}", **columns))
        files[f"{stem}-{stage}.csv"] = rows
    return files


def build_v11_files():
    return build_private_files(V11_MAPS, V11_CELLS)


def build_v11_two_structures_files():
    """The original V11 manifest shape, retained only for offline planner
    regression fixtures.  It is not a dispatch target or a preregistered run."""
    return build_private_files(V11_BUDGET_MAPS, V11_BUDGET_CELLS, "phase3v11-two-structures")


def check_budgets(budgets):
    if not budgets or any(type(n) is not int or n < 1 for n in budgets) or len(set(budgets)) != len(budgets):
        raise ValueError("--budgets requires distinct positive integers separated by commas")


def build_v11_budget_files(budgets):
    check_budgets(budgets)
    return build_private_files(V11_BUDGET_MAPS, V11_BUDGET_CELLS, "phase3v11-budget", budgets=budgets)


def fixed_order_scene(source):
    """Project the final demand and the public rule onto the existing map. The old oracle is for five orders."""
    reveal = source["reveal"]
    active = (set(reveal["initial_orders"]) | set(reveal["hidden_orders"])) - set(reveal["withdrawn_orders"])
    orders = [o for o in source["orders"] if o["id"] in active]
    robots = [r["rid"] for r in source["robots"]]
    if {o["id"] for o in orders} != active or any(set(c["orders"]) - active for c in source["constraints"]):
        raise ValueError(f"{source['id']}: inconsistent final orders or precedence")
    scene = {k: v for k, v in source.items() if k not in ("reveal", "oracle_plan", "oracle", "estimate", "gen")}
    return dict(scene, id=source["id"].replace("P2R_", "P2F_", 1), orders=orders,
                knows={r: [o["id"] for o in orders] for r in robots},
                constraints=[dict(c, known_by=robots) for c in source["constraints"]])


def build_v11_static_budget_files(budgets):
    check_budgets(budgets)
    reference = build_v10_files()  # verifies source scene hashes and the executor pin against both v8 manifests
    files = {}
    for stage, maps, group in (("main", V11_BUDGET_MAPS, "p3v11static"), ("check", (V8_CHECK_MAP,), "p3v11staticchk")):
        bases = {(r["scene_id"], r["arm"]): r for r in reference[f"phase3v10-{stage}.csv"] if r["rep"] == "1"}
        rows = []
        for short in maps:
            orig = f"P2R_N03_{short}"
            expected = fixed_order_scene(json.loads((V8_SCENES / f"{orig}.json").read_bytes())["scenes"][0])
            sid = expected["id"]
            local = STATIC_SCENES / f"{sid}.json"
            data = local.read_bytes()
            if json.loads(data)["scenes"] != [expected]:
                raise ValueError(f"{local.name}: does not match the final orders on the source map")
            path = str(V8_IMAGE_SCENES / local.name)
            digest = hashlib.sha256(data).hexdigest()
            for cell in V11_BUDGET_CELLS:
                base = bases[orig, cell]
                vm = without_flag(shlex.split(base["vm_args"]), "--order-reveal", "all")
                vm = without_flag(vm, "--reveal-trigger", "holders")
                for flag in ("--empty-park", "--park-retreat", "--park-door-clear"):
                    vm.remove(flag)
                server = without_flag(shlex.split(base["server_args"]), "--event", "exchange")
                server.remove("--order-reveal")
                server[server.index("--scene-id") + 1] = sid
                server[server.index("--scene-file") + 1] = path
                for n in budgets:
                    flags = [*server, "--static-orders", "--max-output-tokens", str(n), "--truncation-attempts", "3"]
                    rows.append(dict(base, run_id=f"P3V11D-{short}-{cell}-b{n}", group=group, scene_id=sid,
                                     scene_file=path, scene_sha256=digest, vm_args=shlex.join([*vm, "--full-info"]),
                                     server_args=shlex.join(flags), max_output_tokens=str(n)))
        files[f"phase3v11-static-budget-{stage}.csv"] = rows
    return files


def write_static_lists(outputs):
    """Check both destinations first. Publish complete CSVs without replacing another campaign's files."""
    for path, data in outputs.items():
        if path.exists() and path.read_bytes() != data:
            raise ValueError(f"{path} already contains a different manifest")
    for path, data in outputs.items():
        if not path.exists():
            with NamedTemporaryFile(dir=path.parent) as tmp:
                tmp.write(data)
                tmp.flush()
                Path(tmp.name).chmod(0o644)
                try:
                    path.hardlink_to(tmp.name)
                except FileExistsError:
                    pass  # A concurrent writer must have produced the same bytes.
        if path.read_bytes() != data:
            raise ValueError(f"{path} already contains a different manifest")


def main_frameworks(a):
    builders = {"v10": build_v10_files, "v11": build_v11_files, "v11-two-structures": build_v11_two_structures_files}
    columns = P2.COLUMNS if a.design == "v10" else (*P2.COLUMNS, "recipient")
    if a.design == "v11-static-budget":
        files = build_v11_static_budget_files(a.budgets)
        columns = (*P2.COLUMNS, "max_output_tokens")
    elif a.design == "v11-budget":
        files = build_v11_budget_files(a.budgets)
        columns = (*columns, "max_output_tokens")
    else:
        files = builders[a.design]()
    folder = a.output_dir or MAN
    contents = {name: P2.csv_text(rows, columns) for name, rows in files.items()}
    if a.write and a.design == "v11-static-budget":
        folder.mkdir(parents=True, exist_ok=True)
        write_static_lists({folder / name: content.encode() for name, content in contents.items()})
    for name, rows in files.items():
        path = folder / name
        content = contents[name]
        if a.write and a.design != "v11-static-budget":
            P2.replace_text(path, content)
        if a.check and path.read_bytes() != content.encode():
            raise ValueError(f"{name} on disk differs from the generated list")
        print(f"{name}  {len(rows)} rows  {rows[0]['sha']}")
    if a.check:
        print(f"OK  the {a.design} files on disk equal the generated lists")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--design", choices=("v10", "v11", "v11-two-structures", "v11-budget", "v11-static-budget"))
    p.add_argument("--budgets", metavar="N,M", help="distinct positive output-token limits for the budget designs")
    p.add_argument("--output-dir", type=Path, help="directory for the fixed-order CSVs (default: manifests)")
    p.add_argument("--plan-format", choices=PLAN_FORMATS, default=None, help="default assign for v7 and v8 (T9); execute only when given explicitly")
    p.add_argument("--event", choices=EVENTS, default="none", help="none: the v7 lists (default); exchange: the v8 lists (phase3v8-*.csv)")
    p.add_argument("--write", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--exec-sha", default=None, help="v8 only: the executor commit (40 lowercase hex) for the sha column; without it the placeholder stays and --check says the files are not dispatchable")
    a = p.parse_args(argv)
    if a.output_dir is not None and a.design != "v11-static-budget":
        p.error("--output-dir is for --design v11-static-budget")
    if a.design == "v11-static-budget" and a.event != "none":
        p.error("v11-static-budget uses fixed orders for the entire run")
    if a.design in ("v11-budget", "v11-static-budget"):
        if not a.budgets or not re.fullmatch(r"[0-9]+(?:,[0-9]+)*", a.budgets):
            p.error(f"--design {a.design} requires --budgets N,M with positive integers")
        a.budgets = [int(n) for n in a.budgets.split(",")]
    elif a.budgets is not None:
        p.error("--budgets is for --design v11-budget or v11-static-budget")
    if a.design:
        if a.plan_format or a.exec_sha:
            p.error(f"{a.design} uses joint JSON plans and the pinned executor commit")
        return main_frameworks(a)
    if a.exec_sha is not None:
        if a.event != "exchange":
            p.error("--exec-sha is for --event exchange only")
        if not V8_SHA40.fullmatch(a.exec_sha):
            p.error("--exec-sha must be 40 lowercase hex characters")
        if a.exec_sha == P2.EXEC_COMMIT:
            p.error("--exec-sha is the phase-2 executor commit of exec_config.json, which has no --reveal-trigger")
    if a.event == "exchange":
        return main_v8(a)
    plan_format = a.plan_format or "assign"
    catalog, _no_plan = P2.read_reveal_catalog()
    files = build_files(catalog, plan_format)
    reference = read_reference()
    for line in check_rows(files, reference):
        print("OK  " + line)
    if plan_format == "assign":
        check_plan_format(build_files(catalog, "execute")[MAIN_FILE], files[MAIN_FILE])
        print("OK  F4 --plan-format execute adds exactly the flag to LL, LP, PL (checked against the default lists)")
    if a.write:
        for name, rows in files.items():
            P2.replace_text(MAN / name, P2.csv_text(rows))
            print(f"wrote {MAN / name} ({len(rows)} rows, plan format {plan_format})")
    if a.check:
        for name, rows in files.items():
            if (MAN / name).read_bytes() != P2.csv_text(rows).encode():
                raise ValueError(f"{name} on disk differs from the generated list")
        print("OK  the files on disk equal the generated lists")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, StopIteration) as error:
        sys.exit(f"FAIL  {error}")
