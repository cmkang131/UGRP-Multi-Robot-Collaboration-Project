"""Derive the P2 smoke cases from the frozen r13 cases (only ``candidate`` changes).

    python experiments/2026-10-21-pairact-p2/make_p2_cases.py \
        --r13-cases /home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json \
        --out /home/ugrp/ugrp-sim/runs/pairact-p2/p2-smoke-cases.json

World selection (SMOKE.md §2, fixed before any carry run): among the r13
39-gate attempt-1 worlds with ``succ = true`` in ``r13-funnel-attempt1.json``
(copied byte-identical from ``claude/beamact5-r2-t`` 0610c95e5), sort by the
episode-end SIM s ``sim`` (= both teachers ``complete``, i.e. joint hold 3 s
reached) ascending, tie-break by ``case`` ascending, take the first 3.
The plan, seed and profile of every selected case stay byte-identical.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R13_CASES_SHA256 = '3d4e065db0299c0efa4c91676f537ac9b0e130773e598dfc5767d97a34ffdc63'
FUNNEL = HERE/'r13-funnel-attempt1.json'
FUNNEL_SHA256 = '31027ffbdc5904a9a39a506e687a2138d9543906ec14ae6214292dc6f35f60c2'
SMOKE_N = 3
FROM, TO = 'beamact5_r13', 'pairact_p2_r13'


def select_worlds(funnel, n=SMOKE_N):
    """Fastest grasp completions: ascending (sim, case) over successes."""
    ok = [(float(c['sim']), int(c['case'])) for c in funnel['per_case'] if c.get('succ') is True]
    return tuple(case for _, case in sorted(ok)[:n])


def load_funnel(path=FUNNEL):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != FUNNEL_SHA256:
        raise ValueError('r13 funnel hash mismatch')
    return json.loads(raw)


def derive(raw, worlds=None):
    if hashlib.sha256(raw).hexdigest() != R13_CASES_SHA256:
        raise ValueError('r13 cases hash mismatch')
    if worlds is None:
        worlds = select_worlds(load_funnel())
    cases = json.loads(raw)
    out = []
    for w in worlds:
        case = cases[w]
        if case.get('candidate') != FROM:
            raise ValueError(f'world {w}: expected candidate {FROM!r}, got {case.get("candidate")!r}')
        out.append({**case, 'candidate': TO, 'source_world_index': w})
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--r13-cases', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit('refusing to overwrite existing cases file')
    worlds = select_worlds(load_funnel())
    cases = derive(a.r13_cases.read_bytes(), worlds)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(cases, indent=1) + '\n')
    print(json.dumps({'out': str(a.out), 'sha256': hashlib.sha256(a.out.read_bytes()).hexdigest(),
                      'worlds': list(worlds), 'seeds': [c['plan']['seed'] for c in cases]}))


if __name__ == '__main__':
    main()
