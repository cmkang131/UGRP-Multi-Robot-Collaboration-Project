"""Derive the P2 smoke cases from the frozen r13 cases (only ``candidate`` changes).

    python experiments/2026-10-21-pairact-p2/make_p2_cases.py \
        --r13-cases /home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json \
        --out /home/ugrp/ugrp-sim/runs/pairact-p2/p2-smoke-cases.json

Worlds 6, 10, 20 are the r13 stage-2 joint-hold PASS worlds (README-align r13
row). The plan, seed and profile of every selected case stay byte-identical.
"""
import argparse
import hashlib
import json
from pathlib import Path

R13_CASES_SHA256 = '3d4e065db0299c0efa4c91676f537ac9b0e130773e598dfc5767d97a34ffdc63'
SMOKE_WORLDS = (6, 10, 20)
FROM, TO = 'beamact5_r13', 'pairact_p2_r13'


def derive(raw, worlds=SMOKE_WORLDS):
    if hashlib.sha256(raw).hexdigest() != R13_CASES_SHA256:
        raise ValueError('r13 cases hash mismatch')
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
    cases = derive(a.r13_cases.read_bytes())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(cases, indent=1) + '\n')
    print(json.dumps({'out': str(a.out), 'sha256': hashlib.sha256(a.out.read_bytes()).hexdigest(),
                      'worlds': list(SMOKE_WORLDS), 'seeds': [c['plan']['seed'] for c in cases]}))


if __name__ == '__main__':
    main()
