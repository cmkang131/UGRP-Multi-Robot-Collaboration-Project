"""pairact P1: derive one arm's cases file from the frozen r13 cases.

Only the per-case ``candidate`` field changes (root run_warp_flow_teacher.py reads
``case.get('candidate')`` and the adapter maps it to teacher modes). The source file
is never modified. Usage:
    python make_arm_cases.py SRC.json OUT.json CANDIDATE
Prints a JSON line with both sha256 values and the old candidate set.
"""
import copy
import hashlib
import json
import sys
from pathlib import Path

ARMS = ('beamact5_r13', 'pairact_p1c1', 'pairact_p1c2b', 'pairact_p1c3')


def _cases(doc):
    return doc if isinstance(doc, list) else doc['cases']


def derive(doc, candidate):
    if candidate not in ARMS:
        raise ValueError(f'unknown arm {candidate!r}')
    out = copy.deepcopy(doc)
    old = sorted({c.get('candidate', 'baseline') for c in _cases(out)})
    for case in _cases(out):
        case['candidate'] = candidate
    # Self-check: nothing except 'candidate' differs.
    for a, b in zip(_cases(doc), _cases(out)):
        if {k: v for k, v in a.items() if k != 'candidate'} != {k: v for k, v in b.items() if k != 'candidate'}:
            raise AssertionError('non-candidate field changed')
    return out, old


def main(src, dst, candidate):
    src, dst = Path(src), Path(dst)
    if dst.exists():
        raise FileExistsError(dst)
    raw = src.read_bytes()
    out, old = derive(json.loads(raw), candidate)
    dst.write_text(json.dumps(out, ensure_ascii=False))
    print(json.dumps(dict(src=str(src), src_sha256=hashlib.sha256(raw).hexdigest(), dst=str(dst),
                          dst_sha256=hashlib.sha256(dst.read_bytes()).hexdigest(), candidate=candidate,
                          old_candidates=old, n=len(_cases(out)))))


if __name__ == '__main__':
    main(*sys.argv[1:4])
