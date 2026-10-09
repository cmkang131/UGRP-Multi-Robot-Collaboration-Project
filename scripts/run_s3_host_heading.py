"""Single committed S3 v144 smoke with host v3 binding and heading enabled."""
import argparse
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess

from harness import zone_s3_host_heading_contract as contract
from harness.zone_final_pair_binding import bind
from scripts import run_s3_no_prior as old
from scripts.run_final_environment_checks import check_source, write
from scripts.run_s3_host import artifact_manifest

run = bind(old.run, contract=contract)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--seed', type=int, choices=contract.SEEDS, default=14201)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--release-s3-simulation', action='store_true')
    a = p.parse_args(argv)
    b = contract.bundle(a.expected_source_sha, seed=a.seed)
    if not a.execute:
        print(json.dumps(dict(execution_started=False, execution_bundle_id=contract.BUNDLE_ID,
            s3_camera_binding=b['s3_camera_binding'], options=b['options'], seed=a.seed)))
        return 0
    if not a.release_s3_simulation:
        raise ValueError('explicit coordinator S3 release required')
    check_source(a.expected_source_sha)
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=contract.ROOT, text=True).strip()
    if branch != 'codex/s3-no-prior-smoke' or os.getpriority(os.PRIO_PROCESS, 0) != 0:
        raise ValueError('own S3 branch and nice zero required')
    from scripts import agent_lock
    primary = agent_lock.DEFAULT_ROOT.parent
    expected = primary/f's3-host-heading-{a.expected_source_sha[:8]}-s{a.seed}-v144'
    if not a.output.is_absolute() or a.output.resolve() != expected.resolve() or a.output.exists():
        raise ValueError('new registered primary output required')
    if shutil.disk_usage(primary).free < b['raw_budget_bytes']+10*1024**3:
        raise OSError(errno.ENOSPC, 'raw budget plus 10 GiB reserve required')
    held = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch=branch,
        purpose='S3 v144 one host-corrected mixed heading smoke', pid=os.getpid(),
        expected_minutes=180, timing_sensitive=True)
    from harness.zone_pair_highpose_exact_speedups import install
    undo = None
    try:
        _, undo = install('v98-exact-v6')
        result = run(b, a.output)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result['status'] == 'DEV_DELIVERED' else 1
    finally:
        if undo:
            undo()
        released = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
        if a.output.exists():
            write(a.output/'lock.json', dict(acquired=held, released=released,
                status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))
            artifact_manifest(a.output)


if __name__ == '__main__':
    raise SystemExit(main())
