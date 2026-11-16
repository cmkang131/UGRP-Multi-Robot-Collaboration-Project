#!/usr/bin/env python3
"""Manifest generator (CSV). Standard library only.

The group table below is an EXAMPLE: scene ids, repetitions and condition arguments are placeholders that the main session
replaces when the experiment is frozen. Values containing TODO/PLACEHOLDER make `dispatch.py run --go` refuse to start.

  make_manifest.py --out manifest.example.csv [--shuffle-seed 20261115] [--groups mainA,order]
  make_manifest.py --preset confirm2|core|optional|all --outdir manifests [--shuffle-seed 20261115] [--baseline-first]
      the real manifests (frozen values below; `check_manifests.py` validates them against the scene files)
"""
import argparse
import csv
import os
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dispatch import COLUMNS, GROUPS, load_manifest  # noqa: E402

# Folder on the work VMs that holds the scene files (the same files as ../scenes/). Set $VM_SCENE_DIR; without it the rows carry
# PLACEHOLDER and `dispatch.py run --go` refuses them.
VM_DIR = os.environ.get("VM_SCENE_DIR", "PLACEHOLDER_VM_SCENE_DIR").rstrip("/") + "/"
SCENE_FILE = VM_DIR + "scenes18b.json"              # path on the VMs
COMMON = "--robot-tags --overhead --regrasp-max 1"   # VM args shared by every run (as in queue_llm_v31_confirm.sh)
SHA = "TODO_SHA"                                     # VM code commit, fill at freeze
VMRUN = "run_team_v31.sh"
MODEL = "z-ai/glm-5.3-flash"
CODE = {"baseline": "BASE", "mainA": "A", "random": "RND", "leader": "LDR", "three": "THR", "model2": "M2",
        "ablation": "ABL", "order": "ORD", "fullinfo": "FULL"}
# group -> defaults for the rows; "teams" x "scenes" x reps. Everything here is example data.
SPEC = {
    "baseline": dict(teams=["T0"], scenes=["X01", "L01"], reps=1),
    "mainA": dict(teams=["T0", "T1", "T2"], scenes=["C01", "D01"], reps=1),
    "random": dict(teams=["T1"], scenes=["C01"], reps=2, vm_args=COMMON + " --TODO-random-arg"),
    "leader": dict(teams=["T2"], scenes=["L01"], reps=1, leaders=["r1", "r2"]),
    "three": dict(teams=["T0", "T1", "T2"], scenes=["X01"], reps=1, robots="r1,r2,r3"),
    "model2": dict(teams=["T1"], scenes=["C01"], reps=1, model="TODO_MODEL2"),
    "ablation": dict(teams=["T1"], scenes=["D01"], reps=1, server_args="--pre-exchange"),
    "order": dict(teams=["T1"], scenes=["D01"], reps=1, server_args="--option-order reverse"),
    "fullinfo": dict(teams=["T0", "T1"], scenes=["L01"], reps=1, vm_args=COMMON + " --TODO-fullinfo-arg"),
}


def build_rows(groups=GROUPS, spec=SPEC, sha=SHA, vmrun=VMRUN, seed="90721"):
    rows = []
    for group in groups:
        s = spec[group]
        for scene in s["scenes"]:
            for team in s["teams"]:
                for leader in s.get("leaders", ["r1"]):
                    for rep in range(1, s["reps"] + 1):
                        tag = "-" + leader if "leaders" in s else ""
                        rows.append(dict(run_id="%s-%s-%s%s-r%d" % (CODE[group], scene, team, tag, rep), group=group,
                                         scene_file=SCENE_FILE, scene_id=scene, team=team, rep=rep,
                                         robots=s.get("robots", "r1,r2"), leader=leader, model=s.get("model", MODEL),
                                         vm_args=s.get("vm_args", COMMON), server_args=s.get("server_args", ""),
                                         sha=sha, vmrun=vmrun, seed=seed))
    return rows


def shuffled(rows, seed):
    """Fixed-seed shuffle so structures/scenes are not clustered in time. seed 0 keeps the generated order."""
    rows = list(rows)
    if seed:
        random.Random(seed).shuffle(rows)
    return rows


def write_manifest(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ------------------------------------------------------------------ real manifests (frozen values, decided by the main session)
SCENES_DIR = Path(__file__).resolve().parent.parent / "scenes"
SCENE_FILES = {                                              # basename on the VMs -> copy in this repository (checked by sha256 against the VMs)
    "scenes_designed_v2.json": SCENES_DIR / "scenes_designed_v2.json",
    "scenes_random_v2.json": SCENES_DIR / "scenes_random_v2.json",
    "scenes_coop.json": SCENES_DIR / "scenes_coop.json",
    "scenes18b.json": SCENES_DIR / "scenes18b.json",
}
FROZEN_SHA = "dbb692c"
FROZEN_VMRUN = "run_team_v32.sh"
FROZEN_COMMON = COMMON + " --cap-s 900"                      # every real run
MODEL2 = "qwen/qwen3-235b-a22b-2507"
SEED = "90721"
SHUFFLE_SEED = 20261115
TEAMS = ("T0", "T1", "T2")
CODE.update({"confirm2": "CF2", "listen0": "LS0", "random_baseline": "RBASE"})
OPTIONAL_ORDER = ("three", "listen0", "random_baseline", "random", "model2", "leader")   # the order optional.csv is run in

DESIGNED = ["L2-%02d" % i for i in range(1, 13)] + ["C2-%02d" % i for i in range(1, 13)] + ["X2-01", "X2-02", "X2-03", "D2-01", "D2-02", "D2-03"]
K2 = ["K2%02d" % i for i in range(1, 11)]
MAIN40 = DESIGNED + K2                                       # [L, C, X, D, K, by number]
ODD20 = MAIN40[0::2]                                         # 1st, 3rd, ... 39th
ABL10 = ["L2-%02d" % i for i in range(1, 6)] + ["C2-%02d" % i for i in range(1, 6)]
LEADER20 = ["L2-%02d" % i for i in range(1, 11)] + ["C2-%02d" % i for i in range(1, 11)]
RANDOM20 = ["RND2-%02d" % i for i in range(1, 21)]
THREE7 = ["K301", "K302", "K303", "K304", "L301", "L302", "L303"]


def file_of(scene_id):
    if scene_id in DESIGNED:
        return "scenes_designed_v2.json"
    if scene_id in RANDOM20:
        return "scenes_random_v2.json"
    if scene_id in K2 or scene_id in THREE7:
        return "scenes_coop.json"
    return "scenes18b.json"


def real_row(group, scene, team, rep, tag="", vm_extra="", server_args="", robots="r1,r2", leader="r1", model=MODEL):
    return dict(run_id="%s-%s-%s%s-r%d" % (CODE[group], scene, team, tag, rep), group=group, scene_file=VM_DIR + file_of(scene),
                scene_id=scene, team=team, rep=rep, robots=robots, leader=leader, model=model,
                vm_args=(FROZEN_COMMON + " " + vm_extra).strip(), server_args=server_args, sha=FROZEN_SHA, vmrun=FROZEN_VMRUN, seed=SEED)


def grid(group, scenes, teams, reps, **kw):
    return [real_row(group, scene, team, rep, **kw) for scene in scenes for team in teams for rep in range(1, reps + 1)]


def confirm2_rows():
    return grid("confirm2", ["C01", "L01", "D01"], TEAMS, 2)


def core_groups():
    """name -> rows (not shuffled)."""
    ablation = (grid("ablation", ABL10, ["T1"], 2, tag="-NR", vm_extra="--no-redecide-destination") +
                grid("ablation", ABL10, ["T1"], 2, tag="-PX", server_args="--pre-exchange"))
    return {"baseline": grid("baseline", MAIN40, ["T0"], 1, vm_extra="--fixed oracle"),   # team column is unused with --fixed
            "mainA": grid("mainA", MAIN40, TEAMS, 2),
            "fullinfo": grid("fullinfo", ODD20, ["T1"], 1, vm_extra="--full-info"),
            "order": grid("order", ["C2-01", "C2-02", "C2-03", "C2-04"], ["T0"], 2, server_args="--option-order reverse"),
            "ablation": ablation}


def optional_groups():
    return {"three": grid("three", THREE7, TEAMS, 2, robots="r1,r2,r3"),
            "listen0": grid("listen0", ABL10, ["T1"], 2, vm_extra="--listen-s 0"),
            "random_baseline": grid("random_baseline", RANDOM20, ["T0"], 1, vm_extra="--fixed oracle"),
            "random": grid("random", RANDOM20, TEAMS, 1),
            "model2": grid("model2", ODD20, TEAMS, 1, model=MODEL2),
            "leader": grid("leader", LEADER20, ["T2"], 2, tag="-lead2", leader="r2")}


def core_rows(shuffle_seed=SHUFFLE_SEED, baseline_first=True):
    """core.csv: with baseline_first the 40 baseline rows come first (throughput check right after the freeze), the other 308 are shuffled."""
    groups = core_groups()
    if baseline_first:
        return groups["baseline"] + shuffled([r for g, rows in groups.items() if g != "baseline" for r in rows], shuffle_seed)
    return shuffled([r for rows in groups.values() for r in rows], shuffle_seed)


def optional_rows(shuffle_seed=SHUFFLE_SEED):
    """optional.csv: groups in OPTIONAL_ORDER; rows are shuffled inside a group only."""
    groups = optional_groups()
    return [r for g in OPTIONAL_ORDER for r in shuffled(groups[g], shuffle_seed)]


def main_real(a):
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    want = ("confirm2", "core", "optional") if a.preset == "all" else (a.preset,)
    for name in want:
        rows = {"confirm2": confirm2_rows,
                "core": lambda: core_rows(a.shuffle_seed, a.baseline_first),
                "optional": lambda: optional_rows(a.shuffle_seed)}[name]()
        path = outdir / (name + ".csv")
        write_manifest(rows, path)
        load_manifest(path, real=True)  # also refuses TODO/PLACEHOLDER
        counts = {}
        for r in rows:
            counts[r["group"]] = counts.get(r["group"], 0) + 1
        print("wrote %d rows to %s: %s" % (len(rows), path, counts))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("manifest.example.csv"))
    p.add_argument("--shuffle-seed", type=int, default=0, help="0 = no shuffle")
    p.add_argument("--groups", default=",".join(GROUPS))
    p.add_argument("--sha", default=SHA)
    p.add_argument("--vmrun", default=VMRUN)
    p.add_argument("--preset", choices=["confirm2", "core", "optional", "all"], help="write the real manifests instead of the example")
    p.add_argument("--outdir", default="manifests")
    p.add_argument("--baseline-first", action="store_true", help="core: the 40 baseline rows first, the rest shuffled")
    a = p.parse_args(argv)
    if a.preset:
        a.shuffle_seed = a.shuffle_seed or SHUFFLE_SEED
        return main_real(a)
    groups = [g for g in a.groups.split(",") if g]
    rows = shuffled(build_rows(groups, SPEC, a.sha, a.vmrun), a.shuffle_seed)
    write_manifest(rows, a.out)
    load_manifest(a.out)  # validates ids, teams, leaders, quoting
    print("wrote %d rows to %s (EXAMPLE data: fill scenes/conditions/sha at freeze)" % (len(rows), a.out))


if __name__ == "__main__":
    main()
