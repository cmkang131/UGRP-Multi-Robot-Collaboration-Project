"""Thin orchestrator: new-seed cases / canonical XML / native refs / rejection table for P2.

No physics, no GPU, no MuJoCo import here. The real steps run on gcp6 with the
existing tools (pairact-p1 TONIGHT.md §0.1, dsh/pairact-p0-diag ab84b451d,
proven on seed 9420000 on 2026-10-20):

  (a) cases   beamact5-tools/wide_start.py     (repo copy: d94122ad0 experiments/2026-10-17-beamact5/teacher/wide_start.py)
  (b) export  beamact5-tools/run_warp_flow_teacher_gcp6.py --export-compiled-only  (mujoco 3.12 venv)
  (c) refs    beamact5-tools/prepare_native_references_gcp6.py                     (mujoco 3.12 venv)
  (d) rejection table = (a)'s wide-setup-funnel.json (gate r1 precedent, 5d906886f
      gate-40-r1/rejection_table.json:31-32). gate-40-r13/rejection_table.json is a
      copy of gate-40-r2's table (README-r3.md:21, sha 16fe662a), not a per-seed product.

Subcommands:

  plan        print the VM commands for --seed-start/--n (nothing executed)
  manifest    after (a)-(c): bind seed -> exported scene.xml -> native refs key, verify, write
              seed-refs-manifest.json (input of make_p2_cases.py seed mode)
  check-init  after an --initialize-only run with the *P2 stack and run flags*: every
              world-XXX/raw/scene.xml sha256 must be a key of the refs (the runtime lookup,
              scripts/warp_act_backend.py initialize + scripts/run_warp_flow_teacher.py:272-273)
"""
import argparse
import hashlib
import json
from pathlib import Path

GATE_N = 40                 # wide_start.py always generates exactly 40 worlds (GATE_N, loop range(GATE_N))
MAX_ATTEMPTS = 5000         # wide_start.py: for attempt in range(5000); rng = seed + i*10000 + attempt
KNOWN_SERIES = (8420000, 9420000)   # existing wide-start series on gcp6 (TONIGHT.md §0.2)
SCHEMA = 'ugrp.pairact_p2.seed_refs_manifest.v1'
# Verified gcp6 paths (pairact-p1 TONIGHT.md §0 / §0.1, 2026-10-20).
SRC = '/home/ugrp/ugrp-sim/src'
RUNS = '/home/ugrp/ugrp-sim/runs/beamact5'
P2_RUNS = '/home/ugrp/ugrp-sim/runs/pairact-p2'   # SMOKE.md §0: P2 writes only here
R13_STACK = dict(root=f'{SRC}/pairact-root-05046e9d', adapter=f'{SRC}/pairact-adapter-d354468a',
                 teacher=f'{SRC}/pairact-teacher-fe6858ec', frozen=f'{SRC}/beamact5-teacher-3170d909')


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def seed_series(seed_start, n):
    """Plan seeds of wide_start.py --seed seed_start, first n worlds (episode seed = seed + i)."""
    if not 1 <= n <= GATE_N:
        raise ValueError(f'n must be 1..{GATE_N}: wide_start.py always generates {GATE_N} worlds per --seed')
    return [seed_start + i for i in range(n)]


def rng_collisions(seed_a, seed_b, n=GATE_N, max_attempts=MAX_ATTEMPTS):
    """(i, j, min attempt in b) pairs where world i of series a and world j of series b could draw
    the same random.Random seed (seed + i*10000 + attempt). Empty = no shared rng seed possible."""
    out = []
    for i in range(n):
        for j in range(n):
            d = (seed_a + i * 10000) - (seed_b + j * 10000)   # attempt_b - attempt_a
            if -max_attempts < d < max_attempts:
                out.append(dict(world_a=i, world_b=j, attempt_offset=d))
    return out


def paths(seed_start, runs=RUNS):
    return dict(start=f'{runs}/wide-start-{seed_start}', export=f'{runs}/wide-export-old-{seed_start}e',
                refs=f'{runs}/native-refs-{seed_start}e')


def plan_commands(seed_start, n, runs=RUNS, src=SRC, stack=R13_STACK, p2_runs=P2_RUNS):
    seed_series(seed_start, n)
    p = paths(seed_start, runs)
    idx = ','.join(str(i) for i in range(n))
    pyw, pys = f'{src}/../ugrp/.venv-warp/bin/python', f'{src}/../ugrp/.venv-sim/bin/python'
    tools = f'{src}/beamact5-tools'
    here = 'experiments/2026-10-21-pairact-p2'
    return [
        ('a_cases', f"cd {stack['adapter']} && PYTHONPATH=$PWD {pyw} {tools}/wide_start.py --seed {seed_start} "
                    f"--output {p['start']} --dependency-root {stack['teacher']} --frozen-root {stack['frozen']} "
                    f"--candidate beamact5_r13"),
        ('b_export', f"cd {stack['root']} && WARP_SOURCE_ROOT=$PWD {pys} {tools}/run_warp_flow_teacher_gcp6.py "
                     f"--flow beampair --adapter-source {stack['adapter']} --teacher-source {stack['teacher']} "
                     f"--cases {p['start']}/wide-cases.json --indices {idx} --cap-s 60 --out {p['export']} "
                     f"--vm-hourly-usd 1.096 --gcp6-isolated-v1 --placement-graspable-filter-v1 "
                     f"--world-model-parameters-v1 --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 "
                     f"--export-compiled-only --rejection-table {p['start']}/wide-setup-funnel.json"),
        ('c_refs', f"cd {stack['frozen']} && {pys} {tools}/prepare_native_references_gcp6.py "
                   f"--source {stack['frozen']} --old-export {p['export']} --out {p['refs']}"),
        ('d_manifest', f"python3 {here}/make_seed_refs.py manifest --seed-start {seed_start} --n {n} "
                       f"--cases {p['start']}/wide-cases.json --export {p['export']} --refs {p['refs']} "
                       f"--out {p2_runs}/seed-refs-{seed_start}-manifest.json"),
        ('e_p2_cases', f"python3 {here}/make_p2_cases.py --seed-start {seed_start} --n {n} "
                       f"--seed-cases {p['start']}/wide-cases.json --seed-refs-manifest {p2_runs}/seed-refs-{seed_start}-manifest.json "
                       f"--to <pairact_p2_r13|pairact_p2_r13_detour> --out {p2_runs}/p2-seed{seed_start}-cases.json"),
    ]


def build_manifest(seed_start, n, cases_path, export_dir, refs_dir):
    """Bind each requested seed to the native refs key it needs; raise on any gap."""
    cases_path, export_dir, refs_dir = Path(cases_path), Path(export_dir), Path(refs_dir)
    seeds = seed_series(seed_start, n)
    cases_raw = cases_path.read_bytes()
    cases = json.loads(cases_raw)
    summary = json.loads((export_dir/'summary.json').read_text())
    if summary.get('cases_sha256') != sha256_bytes(cases_raw):
        raise ValueError('export summary cases_sha256 != cases file sha256')
    if summary.get('status') != 'initialization_only':
        raise ValueError(f"export status {summary.get('status')!r} != 'initialization_only'")
    indices = summary['world_indices']
    proof = json.loads((refs_dir/'proof.json').read_text())
    if Path(proof['old_export']).resolve() != export_dir.resolve():
        raise ValueError(f"refs proof.old_export {proof['old_export']} != {export_dir}")
    native_of = {p['old_xml_sha256']: p['native_xml_sha256'] for p in proof['proof']}
    refs_path = refs_dir/'per-world-references.json'
    refs = json.loads(refs_path.read_text())
    by_seed = {}
    for k, case_index in enumerate(indices):
        xml = export_dir/f'world-{k:03d}'/'raw'/'scene.xml'
        if not xml.is_file():
            raise ValueError(f'missing exported scene {xml}')
        old = sha256_file(xml)
        native = native_of.get(old)
        if native is None or native not in refs:
            raise ValueError(f'world-{k:03d}: exported scene {old} has no native refs entry')
        for key in ('actuator', 'geometry'):
            if not Path(refs[native][key]).is_file():
                raise ValueError(f'world-{k:03d}: missing {key} file {refs[native][key]}')
        seed = cases[case_index]['plan']['seed']
        by_seed[str(seed)] = dict(case_index=case_index, export_world=k, exported_scene_sha256=old,
                                  native_xml_sha256=native)
    missing = [s for s in seeds if str(s) not in by_seed]
    if missing:
        raise ValueError(f'seeds without exported world: {missing}')
    return dict(
        schema=SCHEMA, seed_start=seed_start, n=n, seeds=seeds,
        cases=dict(path=str(cases_path), sha256=sha256_bytes(cases_raw)),
        rejection_table=dict(path=str(cases_path.parent/'wide-setup-funnel.json'),
                             sha256=sha256_file(cases_path.parent/'wide-setup-funnel.json')),
        canonical_xml=dict(path=str(export_dir/'canonical-scene.xml'), sha256=sha256_file(export_dir/'canonical-scene.xml')),
        export_summary_sha256=sha256_file(export_dir/'summary.json'),
        refs=dict(path=str(refs_path), sha256=sha256_file(refs_path), proof_sha256=sha256_file(refs_dir/'proof.json')),
        by_seed={str(s): by_seed[str(s)] for s in seeds})


def check_init(manifest, init_dir):
    """Runtime lookup replay on an --initialize-only output: every scene.xml sha must be a refs key."""
    refs = json.loads(Path(manifest['refs']['path']).read_text())
    init_dir = Path(init_dir)
    worlds = sorted(init_dir.glob('world-*/raw/scene.xml'))
    if not worlds:
        raise ValueError(f'no world-*/raw/scene.xml under {init_dir}')
    rows = [dict(world=w.parent.parent.name, scene_sha256=sha256_file(w)) for w in worlds]
    bad = [r for r in rows if r['scene_sha256'] not in refs]
    return dict(ok=not bad, worlds=len(rows), missing=bad)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    for name in ('plan', 'manifest'):
        s = sub.add_parser(name)
        s.add_argument('--seed-start', type=int, required=True)
        s.add_argument('--n', type=int, default=GATE_N)
    sub.choices['plan'].add_argument('--runs-root', default=RUNS)
    m = sub.choices['manifest']
    m.add_argument('--cases', type=Path, required=True)
    m.add_argument('--export', type=Path, required=True)
    m.add_argument('--refs', type=Path, required=True)
    m.add_argument('--out', type=Path, required=True)
    c = sub.add_parser('check-init')
    c.add_argument('--manifest', type=Path, required=True)
    c.add_argument('--init-out', type=Path, required=True)
    a = p.parse_args()
    if a.cmd == 'plan':
        seeds = seed_series(a.seed_start, a.n)
        for other in KNOWN_SERIES:
            hits = rng_collisions(a.seed_start, other)
            print(f'# rng vs {other}: ' + ('no shared rng seed possible' if not hits else
                  f'{len(hits)} world pairs share rng seeds only if attempt offset matches, e.g. {hits[0]}; '
                  'check plan.proposal_attempts of both cases files'))
        print(f'# seeds {seeds[0]}..{seeds[-1]} (n={len(seeds)})')
        for step, cmd in plan_commands(a.seed_start, a.n, runs=a.runs_root):
            print(f'# {step}\n{cmd}')
    elif a.cmd == 'manifest':
        if a.out.exists():
            raise SystemExit('refusing to overwrite existing manifest')
        manifest = build_manifest(a.seed_start, a.n, a.cases, a.export, a.refs)
        a.out.write_text(json.dumps(manifest, indent=1) + '\n')
        print(json.dumps(dict(out=str(a.out), sha256=sha256_file(a.out), seeds=len(manifest['seeds']),
                              cases_sha256=manifest['cases']['sha256'], refs_sha256=manifest['refs']['sha256'],
                              canonical_xml_sha256=manifest['canonical_xml']['sha256'],
                              rejection_table_sha256=manifest['rejection_table']['sha256'])))
    else:
        result = check_init(json.loads(a.manifest.read_text()), a.init_out)
        print(json.dumps(result))
        if not result['ok']:
            raise SystemExit('MISSING_SEED_REFS: initialize-only scenes not in refs: ' +
                             ', '.join(r['world'] for r in result['missing']))


if __name__ == '__main__':
    main()
