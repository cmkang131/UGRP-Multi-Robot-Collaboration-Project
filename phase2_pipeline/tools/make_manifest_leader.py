#!/usr/bin/env python3
"""Manifests of the second experiment (draft, nothing is run). Same columns as the batch scheduler manifests of the first experiment (v38 main3-180.csv).

  python3 -I -B make_manifest_leader.py --outdir ../manifests          # writes stage1.csv (core + bridge) and stage2.csv, prints the counts
  python3 -I -B make_manifest_leader.py --check ../manifests/stage1.csv ...   # validates files (needs the team/ planner copy next to this tool)

Stage 1 (group lead2s1, all 30 scenes, 4 repetitions): T1peer, T2hub, T2hubE. Bridge cells (group lead2br, 30 scenes, 2 repetitions): the v38 message
rules with the study fixes, T1 and T2, so that the protocol effect can be told from the effect of the fixes.
Stage 2 (group lead2s2, 12 scenes chosen by structure with a fixed seed, 4 repetitions): one factor at a time from the stage-1 base cells, with the
base cells run again in the same file (concurrent controls).
Every row's server_args is parsed with the real brain_server.parse_args by --check, and the group names are accepted by the batch loader only after
the main session adds them to dispatch.EXTRA_GROUPS (--check patches them in memory, like the first experiment did).
"""
import argparse, csv, json, os, random, shlex, sys, zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENES = Path(os.environ.get("P2_SCENES3") or HERE.parent.parent / "scenes3" / "scenes3_main.json")
SEED = 20261117
FIX = "--parser-fix --merge-calls --options-v2"          # parser, one call per choice, stand-by wording: the study fixes of the v38 limits
COLUMNS = ["run_id", "group", "scene_file", "scene_id", "team", "rep", "robots", "leader", "model", "vm_args", "server_args", "sha", "vmrun", "seed"]
FIXED = dict(scene_file="/data/scenes3_main.json", robots="r1,r2,r3", leader="r1", model="z-ai/glm-5.3-flash",
             vm_args="--robot-tags --overhead --regrasp-max 1 --cap-s 900", sha="ceed05f", vmrun="run_team_v38.sh", seed="90721")

# cell code -> (team, server_args). {seed} is replaced by a per-run integer (message-loss draws).
S1 = {"T1peer": ("T1", "--protocol peer-roco " + FIX), "T2hub": ("T2", "--protocol hub-hmas2 " + FIX),
      "T2hubE": ("T2", "--protocol hub-hmas2 --leader-election " + FIX)}
BRIDGE = {"T1v38f": ("T1", FIX), "T2v38f": ("T2", FIX + " --route-note")}
S2 = {"T1peerC": S1["T1peer"], "T2hubC": S1["T2hub"],                                        # concurrent controls (same flags as the stage-1 base cells)
      "T1peerD6": ("T1", "--protocol peer-roco --msg-delay-s 6 " + FIX), "T2hubD6": ("T2", "--protocol hub-hmas2 --msg-delay-s 6 " + FIX),
      "T1peerL30": ("T1", "--protocol peer-roco --msg-loss 0.3 --msg-seed {seed} " + FIX),
      "T2hubL30": ("T2", "--protocol hub-hmas2 --msg-loss 0.3 --msg-seed {seed} " + FIX),
      "T1peerF1": ("T1", "--protocol peer-roco --fail-robot r1 --fail-at-s 60 " + FIX), "T2hubF1": ("T2", "--protocol hub-hmas2 --fail-robot r1 --fail-at-s 60 " + FIX),
      "T1peerF2": ("T1", "--protocol peer-roco --fail-robot r2 --fail-at-s 60 " + FIX), "T2hubF2": ("T2", "--protocol hub-hmas2 --fail-robot r2 --fail-at-s 60 " + FIX),
      "T2cmas": ("T2", "--protocol hub-hmas2 --hub-rounds 0 " + FIX),
      "T1peerI": ("T1", "--protocol peer-roco --idle-option " + FIX), "T2hubI": ("T2", "--protocol hub-hmas2 --idle-option " + FIX)}


def scenes():
    return json.load(open(SCENES))["scenes"]


def subset12():
    """3 scenes of each non-control type (one per 'central robot' seat: holder for L3 and C3, the odd robot for K3) and 3 of the 6 control scenes,
    drawn with a fixed seed. Structure only; no result is read."""
    rng, chosen = random.Random(SEED), []
    for code, key in (("L3", "holder"), ("C3", "holder"), ("K3", "odd_robot")):
        by_seat = {}
        for s in scenes():
            if s["type_code"] == code:
                by_seat.setdefault(s["balance"][key], []).append(s["id"])
        assert len(by_seat) == 3, (code, by_seat.keys())
        chosen += [rng.choice(sorted(v)) for _, v in sorted(by_seat.items())]
    chosen += rng.sample(sorted(s["id"] for s in scenes() if s["control"]), 3)
    return sorted(chosen)


def rows_for(group, cells, scene_ids, reps):
    rows = []
    for scene in scene_ids:
        for code, (team, args) in cells.items():
            for rep in range(1, reps + 1):
                run_id = "LD2-%s-%s-r%d" % (scene, code, rep)
                rows.append(dict(FIXED, run_id=run_id, group=group, scene_id=scene, team=team, rep=str(rep),
                                 server_args=args.format(seed=zlib.crc32(run_id.encode()) % 2 ** 31)))
    random.Random(SEED).shuffle(rows)
    return rows


def write(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def build(outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    ids = [s["id"] for s in scenes()]
    s1 = rows_for("lead2s1", S1, ids, 4) + rows_for("lead2br", BRIDGE, ids, 2)
    random.Random(SEED).shuffle(s1)
    s2 = rows_for("lead2s2", S2, subset12(), 4)
    write(out / "stage1.csv", s1)
    write(out / "stage2.csv", s2)
    return s1, s2


def check(paths):
    sys.path.insert(0, str(Path(os.environ.get("P2_PLANNER_DIR") or HERE.parent / "team"))); sys.path.insert(0, str(Path(os.environ.get("P2_BATCH_DIR") or HERE.parent.parent / "batch"))); sys.dont_write_bytecode = True
    import brain_server, dispatch
    dispatch.EXTRA_GROUPS += ("lead2s1", "lead2br", "lead2s2")
    dispatch.ALL_GROUPS = dispatch.GROUPS + dispatch.EXTRA_GROUPS
    known = {s["id"] for s in scenes()}
    total = 0
    for path in paths:
        rows = dispatch.load_manifest(path, real=True)          # the batch loader: columns, ids, groups, leader in robots, TODO markers
        cells = {}
        for r in rows:
            assert r["scene_id"] in known, r["run_id"]
            assert r["sha"] == "ceed05f" and r["vmrun"] == "run_team_v38.sh" and "--cap-s 900" in r["vm_args"], r["run_id"]
            cell = r["run_id"].split("-")[2]
            cells.setdefault((r["group"], cell, r["team"]), []).append(r)
            args = shlex.split(r["server_args"])
            ns = brain_server.parse_args(["--team", r["team"], "--robots", r["robots"], "--leader", r["leader"], "--model", r["model"],
                                          "--port", "1", "--log-dir", "/x"] + args)       # the launcher's argument line; a bad flag exits here
            assert (ns.protocol is None) == cell.endswith("f") or cell.endswith("v38f"), r["run_id"]
        print(path, "rows", len(rows), "scenes", len({r["scene_id"] for r in rows}))
        for (group, cell, team), v in sorted(cells.items()):
            print("   %-8s %-10s %s  rows %3d  scenes %2d  reps %s  e.g. %s" % (group, cell, team, len(v), len({r["scene_id"] for r in v}),
                  sorted({r["rep"] for r in v}), v[0]["server_args"].replace(FIX, "<FIX>")))
        total += len(rows)
    print("total rows", total)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--outdir")
    p.add_argument("--check", nargs="+")
    a = p.parse_args()
    if a.outdir:
        s1, s2 = build(a.outdir)
        print("stage1 rows %d, stage2 rows %d, subset12 = %s" % (len(s1), len(s2), subset12()))
    if a.check:
        check(a.check)
