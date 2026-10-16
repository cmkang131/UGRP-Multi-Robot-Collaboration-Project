"""sha256 of the cases.jsonl of every raw run the analysis reads (raw stays in /Users/changmin/projects/ugrp/outputs)."""
import sys, json
sys.path.insert(0, '.')
from xb_common import *
import build_windows, run_counterfactual

def main(out):
    names = {k.split('#')[0] for k in build_windows.RAWS} | {v[0] for v in run_counterfactual.CHAIN.values()} | {v[0] for v in run_counterfactual.LEGS.values()}
    res = {}
    for n in sorted(names):
        p = OUT/n/'cases.jsonl'
        res[n] = dict(cases_jsonl_sha256=sha256(p), cases=sum(1 for _ in open(p)))
    json.dump(res, open(out, 'w'), indent=1)
    print(len(res), 'raws')
main(sys.argv[1])
