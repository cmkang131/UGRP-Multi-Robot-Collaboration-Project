#!/usr/bin/env python3
"""Rough power of the second experiment's contrasts from the v38 main experiment's variance (normal approximation, scene = unit).
  python3 -I -B power_leader.py CELLS_CSV
Per-run SD of R inside a scene and structure is estimated from the 2 repetitions of v38 (pooled); the scene-by-contrast spread tau^2 is the v38 spread of
the scene differences T2-T1 minus the run noise (an upper-ish value: it also holds real scene-by-structure differences and the fixed leader r1).
"""
import csv, math, statistics as st, sys
from collections import defaultdict
from fractions import Fraction
from statistics import NormalDist

rows = [r for r in csv.DictReader(open(sys.argv[1])) if r["group"] == "main3"]
R = defaultdict(list)
for r in rows:
    R[(r["scene"], r["structure"], r["control"] == "True")].append(float(Fraction(r["R"])))
scenes = sorted({(s, c) for s, _, c in R})
nc = [s for s, c in scenes if not c]
var = {t: st.mean(st.variance(R[(s, t, False)]) for s in nc) for t in ("T1", "T2")}
diff = [st.mean(R[(s, "T2", False)]) - st.mean(R[(s, "T1", False)]) for s in nc]
tau2 = max(0.0, st.variance(diff) - var["T1"] / 2 - var["T2"] / 2)
print("non-control scenes %d | within-scene run variance T1 %.4f (SD %.3f) T2 %.4f (SD %.3f) | tau^2 %.4f (tau %.3f)" %
      (len(nc), var["T1"], math.sqrt(var["T1"]), var["T2"], math.sqrt(var["T2"]), tau2, math.sqrt(tau2)))
N = NormalDist()


def mde(n_scenes, reps, terms, alpha, power=0.8, tau=tau2):
    """smallest true mean difference (in R units) detected with `power`; terms = number of independent cells in the contrast (2 = a difference)."""
    v = (tau * (terms // 2) + terms * 0.5 * (var["T1"] + var["T2"]) / reps) / n_scenes
    return (N.inv_cdf(1 - alpha / 2) + N.inv_cdf(power)) * math.sqrt(v)


for name, n, reps, terms, alpha in (("stage 1 T2hub - T1peer, 24 scenes, 4 reps, alpha .05/2 (Holm, R and R0)", 24, 4, 2, 0.025),
                                    ("stage 1 same, 30 scenes incl. controls", 30, 4, 2, 0.025),
                                    ("stage 1 election vs fixed leader, 24 scenes", 24, 4, 2, 0.025),
                                    ("stage 2 one axis, T2-T1 at level vs base (interaction), 9 scenes, 4 reps, alpha .05", 9, 4, 4, 0.05),
                                    ("stage 2 same, 12 scenes", 12, 4, 4, 0.05),
                                    ("stage 2 same with 2x the scene variance share removed (tau 0)", 9, 4, 4, 0.05)):
    print("%-90s MDE %.1f pp" % (name, 100 * mde(n, reps, terms, alpha, tau=0.0 if "tau 0" in name else tau2)))
print("one axis effect on one structure (level vs base), 9 scenes, 4 reps, alpha .05: %.1f pp" % (100 * mde(9, 4, 2, 0.05)))
