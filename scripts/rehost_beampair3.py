"""Reproduce e645b34b on gcp2 with a recorded host-admission-only substitution.

The source/dependency checkouts remain clean. No controller, scene, camera,
threshold, input, success predicate or recording code is substituted.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from harness.beampair_host import gcp2_identity

BASELINE = 'e645b34beb4fa693ab4ddedfe77045ae26b46388'


def run(source, dependency, episode, out):
    if sys.platform != 'linux':
        raise RuntimeError('gcp2 Linux only')
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != BASELINE:
        raise ValueError('exact beampair3 baseline required')
    path = source / 'scripts/run_beampair1.py'
    original = path.read_text()
    old = """        host=identity('gcp1')
        if host['instance']!='ugrp-sim-gcp1' or host['machine_type']!='n4-highcpu-64':
            raise ValueError('gcp1 n4-highcpu-64 only')"""
    if original.count(old) != 1:
        raise ValueError('baseline host admission no longer matches')
    adapted = original.replace(old, '        host=gcp2_identity(identity)')
    out.parent.mkdir(parents=True, exist_ok=False)
    proof = dict(baseline_source_sha=BASELINE, execution_host='gcp2',
        project_id='ugrp-sim-b-1014', controller_source_unchanged=True,
        original_runner_sha256=hashlib.sha256(original.encode()).hexdigest(),
        loaded_runner_sha256=hashlib.sha256(adapted.encode()).hexdigest(),
        host_only_diff=''.join(difflib.unified_diff(original.splitlines(True), adapted.splitlines(True))),
        wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='gcp2 reproduction only; never pool with gcp1')
    (out.parent / 'host-portability.json').write_text(json.dumps(proof, indent=2)+'\n')
    # Load all control imports from the clean baseline, not this adapter tree.
    for name in list(sys.modules):
        if name.split('.')[0] in ('scripts', 'sim', 'harness'):
            del sys.modules[name]
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location('baseline_beampair3', path)
    module = importlib.util.module_from_spec(spec)
    module.gcp2_identity = gcp2_identity
    exec(compile(adapted, str(path), 'exec'), module.__dict__)
    plan = json.loads((source / 'experiments/2026-10-15-beampair1/gate-plan.json').read_text())
    return module.run(plan['episodes'][episode], out, dependency,
                      mode='beampair1_v1', candidate='baseline', cap_s=60.,
                      rendezvous='peer_rendezvous_v2')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--dependency-root', type=Path, required=True)
    p.add_argument('--episode', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    run(a.source.resolve(), a.dependency_root.resolve(), a.episode, a.out.resolve())
