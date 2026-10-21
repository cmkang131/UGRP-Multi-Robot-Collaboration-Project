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

Seed mode (opt-in, SEED_REFS.md): ``--seed-start S --n N --seed-cases <wide-cases.json>
--seed-refs-manifest <seed-refs-manifest.json>`` takes the worlds with plan seeds S..S+N-1
from a new wide_start.py cases file (candidate beamact5_r13) instead of r13. Every seed must
have a native compiled reference in the manifest's per-world-references.json, else
``SystemExit('MISSING_SEED_REFS: ...')``. Without ``--seed-start`` the behaviour above is unchanged.
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
# -c3 opt-in: same worlds/plans, candidate = the adapter's carry detour candidates (--to)
TO_CHOICES = (TO, 'pairact_p2_r13_detour', 'pairact_p3_collect_detour')


def select_worlds(funnel, n=SMOKE_N):
    """Fastest grasp completions: ascending (sim, case) over successes."""
    ok = [(float(c['sim']), int(c['case'])) for c in funnel['per_case'] if c.get('succ') is True]
    return tuple(case for _, case in sorted(ok)[:n])


def load_funnel(path=FUNNEL):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != FUNNEL_SHA256:
        raise ValueError('r13 funnel hash mismatch')
    return json.loads(raw)


def derive(raw, worlds=None, to=TO):
    if to not in TO_CHOICES:
        raise ValueError(f'unknown target candidate {to!r}')
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
        out.append({**case, 'candidate': to, 'source_world_index': w})
    return out


SEED_MANIFEST_SCHEMA = 'ugrp.pairact_p2.seed_refs_manifest.v1'   # make_seed_refs.py manifest


def load_seed_refs(manifest):
    """The manifest's refs file, sha-checked; entries whose compiled files are absent are dropped."""
    path = Path(manifest['refs']['path'])
    if not path.is_file():
        raise SystemExit(f'MISSING_SEED_REFS: refs file {path} not found')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['refs']['sha256']:
        raise ValueError('seed refs hash mismatch')
    refs = json.loads(raw)
    return {k: v for k, v in refs.items() if Path(v['actuator']).is_file() and Path(v['geometry']).is_file()}


def derive_seeds(raw, manifest, refs, seed_start, n, to=TO):
    """Seed mode: plan seeds seed_start..seed_start+n-1 from a wide_start cases file; only candidate changes."""
    if to not in TO_CHOICES:
        raise ValueError(f'unknown target candidate {to!r}')
    if manifest.get('schema') != SEED_MANIFEST_SCHEMA:
        raise ValueError('not a seed refs manifest')
    if hashlib.sha256(raw).hexdigest() != manifest['cases']['sha256']:
        raise ValueError('seed cases hash mismatch')
    if n < 1:
        raise ValueError('n must be positive')
    cases = json.loads(raw)
    index = {c['plan']['seed']: i for i, c in enumerate(cases)}
    seeds = list(range(seed_start, seed_start + n))
    absent = [s for s in seeds if s not in index]
    if absent:
        raise SystemExit(f'MISSING_SEED_CASES: seeds {absent} not in seed cases file')
    by_seed = manifest.get('by_seed', {})
    missing = [s for s in seeds if by_seed.get(str(s), {}).get('native_xml_sha256') not in refs]
    if missing:
        raise SystemExit(f'MISSING_SEED_REFS: seeds {missing} have no compiled per-world reference '
                         f'in {manifest["refs"]["path"]} (run make_seed_refs.py plan for the generation commands)')
    out = []
    for s in seeds:
        w = index[s]
        if by_seed[str(s)]['case_index'] != w:
            raise ValueError(f'seed {s}: manifest case_index {by_seed[str(s)]["case_index"]} != {w}')
        case = cases[w]
        if case.get('candidate') != FROM:
            raise ValueError(f'world {w}: expected candidate {FROM!r}, got {case.get("candidate")!r}')
        out.append({**case, 'candidate': to, 'source_world_index': w})
    return out


def main_seeds(a):
    manifest_raw = a.seed_refs_manifest.read_bytes()
    manifest = json.loads(manifest_raw)
    refs = load_seed_refs(manifest)
    cases = derive_seeds(a.seed_cases.read_bytes(), manifest, refs, a.seed_start, a.n, to=a.to)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(cases, indent=1) + '\n')
    print(json.dumps({'out': str(a.out), 'sha256': hashlib.sha256(a.out.read_bytes()).hexdigest(),
                      'worlds': [c['source_world_index'] for c in cases], 'seeds': [c['plan']['seed'] for c in cases],
                      'seed_cases_sha256': manifest['cases']['sha256'],
                      'seed_refs_manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
                      'refs_sha256': manifest['refs']['sha256'], 'canonical_xml': manifest['canonical_xml'],
                      'rejection_table': manifest['rejection_table'], 'indices': ','.join(map(str, range(len(cases))))}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--r13-cases', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--to', choices=TO_CHOICES, default=TO)
    p.add_argument('--seed-start', type=int, help='seed mode (opt-in): first plan seed')
    p.add_argument('--n', type=int, help='seed mode: number of consecutive seeds')
    p.add_argument('--seed-cases', type=Path, help='seed mode: wide_start.py wide-cases.json')
    p.add_argument('--seed-refs-manifest', type=Path, help='seed mode: make_seed_refs.py manifest output')
    a = p.parse_args()
    seed_args = (a.n, a.seed_cases, a.seed_refs_manifest)
    if a.seed_start is None:
        if any(v is not None for v in seed_args):
            p.error('--n/--seed-cases/--seed-refs-manifest require --seed-start')
        if a.r13_cases is None:
            p.error('--r13-cases is required (or use seed mode --seed-start)')
    else:
        if a.r13_cases is not None or any(v is None for v in seed_args):
            p.error('seed mode needs --n --seed-cases --seed-refs-manifest and no --r13-cases')
    if a.out.exists():
        raise SystemExit('refusing to overwrite existing cases file')
    if a.seed_start is not None:
        return main_seeds(a)
    worlds = select_worlds(load_funnel())
    cases = derive(a.r13_cases.read_bytes(), worlds, to=a.to)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(cases, indent=1) + '\n')
    print(json.dumps({'out': str(a.out), 'sha256': hashlib.sha256(a.out.read_bytes()).hexdigest(),
                      'worlds': list(worlds), 'seeds': [c['plan']['seed'] for c in cases]}))


if __name__ == '__main__':
    main()
