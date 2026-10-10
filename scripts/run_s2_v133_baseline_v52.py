"""Administrative seed admission only; frozen v133 controller/plant bytes unchanged."""
import argparse
import copy
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

from harness import zone_s2_landmarks_contract as original_contract
from harness.zone_final_pair_binding import bind
from scripts import run_s2_landmarks_dev as frozen
from scripts.run_final_environment_checks import check_source, write

ROOT = original_contract.ROOT
PLAN = ROOT / 'experiments/2026-10-06-s2-realism/baseline-v52-registration.json'


def read_plan():
    return json.loads(PLAN.read_text())


def baseline():
    p = read_plan()['baseline_bundle']
    path = Path(p['path'])
    if original_contract.old.hp.base.sha(path) != p['sha256']:
        raise ValueError('baseline bundle changed')
    value = json.loads(path.read_text())
    original_contract.require_execution(value)
    return value


def bundle(seed, registration_sha):
    plan = read_plan()
    if seed not in plan['seeds']:
        raise ValueError('only three preregistered fresh seeds admitted')
    b = copy.deepcopy(baseline())
    b['task']['seed'] = seed
    b['source_sha'] = plan['frozen_source_sha']
    b['reproduction'] = dict(registration_sha=registration_sha,
        registration_sha256=original_contract.old.hp.base.sha(PLAN),
        baseline_bundle_sha256=plan['baseline_bundle']['sha256'],
        baseline_execution_sha=plan['baseline_execution_sha'],
        scope='new DEV seed only; frozen v133 runtime, options, calibration and thresholds')
    b.pop('bundle_sha256')
    b['bundle_sha256'] = original_contract.old.hp.base.digest(b)
    return b


def require_execution(value):
    registration_sha = value.get('reproduction', {}).get('registration_sha')
    if value != bundle(value['task']['seed'], registration_sha):
        raise ValueError('frozen v133 reproduction differs from preregistration')
    # Validate every original runtime dependency against the requested commit,
    # as well as the successful raw bundle. The new adapter is separate metadata.
    for path, digest in value['source_sha256'].items():
        raw = subprocess.check_output(['git', 'show', value['source_sha'] + ':' + path], cwd=ROOT)
        import hashlib
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('frozen source commit differs: ' + path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--expected-registration-sha', required=True)
    p.add_argument('--seed', required=True, type=int)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    b = bundle(args.seed, args.expected_registration_sha)
    require_execution(b)
    if not args.execute:
        print(json.dumps(dict(execution_started=False, seed=args.seed,
            source_sha=b['source_sha'], execution_bundle_id=b['execution_bundle_id'], options=b['options'])))
        return
    check_source(args.expected_registration_sha)
    primary = Path('/Users/changmin/projects/ugrp/outputs').resolve()
    expected = primary / f"s2-realism-{b['source_sha'][:8]}-s{args.seed}-v133-reproduction"
    if args.output != expected or args.output.exists():
        raise ValueError('one new preregistered primary output per seed required')
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    held = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/s2-realism',
        purpose=f's2v52 frozen v133 baseline seed {args.seed}', pid=os.getpid(),
        expected_minutes=35, timing_sensitive=True)
    undo = None
    try:
        _, undo = install('v98-exact-v6')
        def writer(path, value):
            if path.name == 'result.json':
                value = {**value, 'reproduction': b['reproduction'], 'seed': args.seed}
            write(path, value)
        runner = bind(frozen.run, c=SimpleNamespace(require_execution=require_execution), write=writer)
        result = runner(b, args.output)
        print(json.dumps({k: result.get(k) for k in ('status', 'evaluation', 'failure', 'wall_per_sim')}), flush=True)
    finally:
        if undo is not None:
            undo()
        released = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
        write(args.output/'lock.json', dict(acquired=held, released=released,
            status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))


if __name__ == '__main__':
    main()
