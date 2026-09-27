#!/usr/bin/env python3
"""Map disk_report.py retention rows to docs/disk_management.md section 4 tiers (name-based estimate).

Usage: tiers.py <disk-report.json> [out.json]
Line tiers are disjoint: T0 infra/ops, T3 retired-worktrees, T4 realtime/sim-speed, T5 9/7 ZIPs,
T7 current study (9/24+ zone/owncam/M1/M2/plan/dynamic/map/beam/vision/study), T6 everything else.
T1 (test) and T2 (dev) are cross-cuts from the report's name tiers.
"""
import collections, json, re, sys
d = json.load(open(sys.argv[1]))
G = 2**30
def line(top):
    if top == "retired-worktrees": return "T3"
    if top == "experiment-archives-20260907": return "T5"
    if re.match(r"(tensorboard|agent-locks|storage-cleanup|disk-|worktree-cleanup)", top): return "T0"
    if re.match(r"(simulation-realtime|simulation-performance|sim-speed)", top): return "T4"
    m = re.search(r"(2026\d{4})", top)
    if re.match(r"(zone|owncam|m1-|m2-|plan-|dynamic-|map-goto|beam-|vision-|study)", top) and (not m or m.group(1) >= "20260924"):
        return "T7"
    return "T6"
lines = collections.defaultdict(collections.Counter)
cross = collections.Counter(); refd = collections.Counter(); folders = collections.defaultdict(collections.Counter)
for r in d["retention"]["rows"]:
    top = r["path"].split("/")[0]; t = line(top)
    lines[t][r["tier"]] += r["bytes"]; folders[t][top] += r["bytes"]
    if r["tier"] in ("test-cohort", "dev-diagnostic"):
        k = "T1" if r["tier"] == "test-cohort" else "T2"
        cross[k] += r["bytes"]; refd[k, bool(r.get("record_reference"))] += r["bytes"]
out = {"lines": {t: {"total_gib": round(sum(c.values()) / G, 2), **{k: round(v / G, 2) for k, v in c.items()},
                     "top": [(n, round(b / G, 2)) for n, b in folders[t].most_common(12)]} for t, c in sorted(lines.items())},
       "cross": {k: {"total_gib": round(v / G, 2), "record_ref_gib": round(refd[k, True] / G, 2),
                     "no_ref_gib": round(refd[k, False] / G, 2)} for k, v in cross.items()},
       "outputs_gib": round(d["outputs"]["bytes"] / G, 2)}
print(json.dumps(out, indent=1, ensure_ascii=False))
if len(sys.argv) > 2: open(sys.argv[2], "w").write(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
