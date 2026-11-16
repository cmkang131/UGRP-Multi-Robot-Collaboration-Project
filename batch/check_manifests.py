#!/usr/bin/env python3
"""Check the real manifests (manifests/*.csv) against the scene files on this server. Standard library only. No ssh.

  check_manifests.py [--dir manifests]     exit 0 = every check passed

Checks: loader accepts rows in real mode (no TODO/PLACEHOLDER); run_id unique across ALL files; scene id exists in the local copy of the row's
scene_file; robots column = robot count of the scene; oracle (--fixed) rows have a non-empty oracle_plan; every row has --cap-s 900, sha dbb692c,
run_team_v32.sh, seed 90721; --pre-exchange never with T0; group counts; baseline rows first in core.csv; odd-20 composition; sha256 of the local scene files.
"""
import argparse
import collections
import hashlib
import json
import shlex
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dispatch  # noqa: E402
import make_manifest as mm  # noqa: E402

EXPECT = {"confirm2": {"confirm2": 18},
          "core": {"baseline": 40, "mainA": 240, "fullinfo": 20, "order": 8, "ablation": 40},
          "optional": {"three": 42, "listen0": 20, "random_baseline": 20, "random": 60, "model2": 60, "leader": 40}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_scenes():
    out = {}
    for base, path in mm.SCENE_FILES.items():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        out[base] = {s["id"]: s for s in (data["scenes"] if isinstance(data, dict) else data)}
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", type=Path, default=Path(__file__).resolve().parent / "manifests")
    a = p.parse_args(argv)
    scenes, errors, allids = load_scenes(), [], collections.Counter()
    for base, path in mm.SCENE_FILES.items():
        print("scene file %-24s %d scenes  sha256 %s" % (base, len(scenes[base]), sha(path)))
    for name, expect in EXPECT.items():
        path = a.dir / (name + ".csv")
        try:
            rows = dispatch.load_manifest(path, real=True)
        except (OSError, ValueError) as error:
            errors.append("%s: %s" % (name, error))
            continue
        counts = collections.Counter(r["group"] for r in rows)
        print("%-9s %3d rows %s" % (name, len(rows), dict(counts)))
        if dict(counts) != expect:
            errors.append("%s: group counts %s, expected %s" % (name, dict(counts), expect))
        for r in rows:
            allids[r["run_id"]] += 1
            where = "%s %s" % (name, r["run_id"])
            if not r["scene_file"].startswith(mm.VM_DIR) or Path(r["scene_file"]).name not in scenes:
                errors.append(where + ": unknown scene_file " + r["scene_file"])
                continue
            scene = scenes[Path(r["scene_file"]).name].get(r["scene_id"])
            if scene is None:
                errors.append(where + ": scene %s not in %s" % (r["scene_id"], r["scene_file"]))
                continue
            robots = r["robots"].split(",")
            if sorted(x["rid"] for x in scene["robots"]) != sorted(robots):
                errors.append(where + ": scene robots %s != robots column %s" % ([x["rid"] for x in scene["robots"]], robots))
            if dispatch.no_brain(r["vm_args"]):
                if "--fixed oracle" not in r["vm_args"] or not any(scene["oracle_plan"].values()):
                    errors.append(where + ": --fixed without a usable oracle_plan")
                if r["server_args"]:
                    errors.append(where + ": server_args on a run without a planner server")
            tokens = shlex.split(r["vm_args"])
            if tokens.count("--cap-s") != 1 or tokens[tokens.index("--cap-s") + 1] != "900":
                errors.append(where + ": --cap-s 900 missing")
            if "--scenes" in tokens or "--scene-id" in tokens:
                errors.append(where + ": vm_args must not repeat --scenes/--scene-id (dispatch adds them)")
            if (r["sha"], r["vmrun"], r["seed"]) != (mm.FROZEN_SHA, mm.FROZEN_VMRUN, mm.SEED):
                errors.append(where + ": sha/vmrun/seed %s" % ((r["sha"], r["vmrun"], r["seed"]),))
            if "--pre-exchange" in r["server_args"].split() and r["team"] == "T0":
                errors.append(where + ": --pre-exchange with T0")
            if r["group"] == "three" and len(robots) != 3 or r["group"] != "three" and len(robots) != 2:
                errors.append(where + ": robot count %d" % len(robots))
        if name == "core":
            first = [r["group"] for r in rows[:40]]
            if first != ["baseline"] * 40:
                errors.append("core: rows 1-40 are not all baseline (use --baseline-first): %s" % collections.Counter(first))
    for run_id, n in allids.items():
        if n > 1:
            errors.append("run_id %s appears %d times across files" % (run_id, n))
    kinds = collections.Counter(s[0] for s in mm.ODD20)
    print("odd-20 kinds %s, X/D %s, K %s" % (dict(kinds), [x for x in mm.ODD20 if x[0] in "XD"], [x for x in mm.ODD20 if x[0] == "K"]))
    if not (kinds["L"], kinds["C"], kinds["X"] + kinds["D"], kinds["K"]) == (6, 6, 3, 5) or [s for s in mm.ODD20 if s[0] in "XD"] != ["X2-01", "X2-03", "D2-02"]:
        errors.append("odd-20 composition unexpected: %s" % mm.ODD20)
    print("total run_ids: %d (unique %d)" % (sum(allids.values()), len(allids)))
    for e in errors:
        print("FAIL:", e)
    print("RESULT:", "PASS" if not errors else "FAIL (%d)" % len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
