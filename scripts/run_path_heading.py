"""New shared-heading DEV entry; historical v141/v143 runners remain replayable."""
import argparse
import json
import os
from pathlib import Path
import shutil

from harness import zone_path_heading_contract as contract
from harness.path_heading_policy import DEFAULT, VISUAL_LOCK
from harness.zone_final_pair_binding import bind
from scripts import run_s2_graduation59 as previous
from scripts.run_final_environment_checks import check_source, write


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--seed', type=int, choices=(1066, 1068, 1065), required=True)
    p.add_argument('--heading-mode', choices=('off', DEFAULT), default=DEFAULT)
    p.add_argument('--heading-visual-lock', choices=('off', VISUAL_LOCK), default='off')
    p.add_argument('--output', type=Path, required=True)
    return p


def run(b, out):
    return bind(previous.run, contract=contract)(b, out)


def main(argv=None):
    a = parser().parse_args(argv)
    b = contract.bundle(a.expected_source_sha, a.seed,
                        heading_mode=a.heading_mode, heading_visual_lock=a.heading_visual_lock)
    if not a.execute:
        print(json.dumps(dict(execution_started=False, execution_bundle_id=contract.BUNDLE_ID,
                              options=b['options'])))
        return
    check_source(a.expected_source_sha)
    contract.require_execution(b)
    if os.getpriority(os.PRIO_PROCESS, 0) != 0:
        raise ValueError('nice must be zero; never renice')
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    expected = agent_lock.DEFAULT_ROOT.parent/f'path-heading-{a.expected_source_sha[:8]}-s{a.seed}-v145'
    if not a.output.is_absolute() or a.output.resolve() != expected.resolve() or a.output.exists():
        raise ValueError('new primary output required')
    if shutil.disk_usage(a.output.parent).free < 10*1024**3:
        raise OSError(28, 'ENOSPC preflight: less than 10 GiB')
    held = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/s2-heading',
        purpose=f'new shared heading DEV s{a.seed}', pid=os.getpid(), expected_minutes=45, timing_sensitive=True)
    undo = None
    try:
        _, undo = install('v98-exact-v6')
        result = run(b, a.output)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        if undo:
            undo()
        released = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
        if a.output.exists():
            write(a.output/'lock.json', dict(acquired=held, released=released,
                                           status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))


if __name__ == '__main__':
    main()
