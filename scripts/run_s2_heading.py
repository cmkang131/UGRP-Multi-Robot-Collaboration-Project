"""Managed, sequential heading DEV. Queue order is checked by the coordinator."""
import argparse
import copy
import json
import os
from pathlib import Path

from harness import zone_s2_heading_contract as contract
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_path_heading import runtime_class, OPTION
from harness.zone_solo_cyan_unknown_start import Runtime as UnknownStart
from harness.zone_solo_cyan_active_observation import attach as active
from harness.zone_solo_cyan_rotation_envelope import attach as envelope
from scripts import run_s2_unknown_start as unknown
from scripts import run_s2_active_observation as previous
from scripts.run_final_environment_checks import check_source, write


def queue_receipt(records):
    """A momentarily free lock never permits overtaking the assigned queue."""
    s2=next((r for r in reversed(records) if r.get('purpose') ==
             's2v59 preregistered six-seed DEV and one pair throughput'),None)
    if s2 is None:raise ValueError('S2V59_NOT_RELEASED')
    later=[r for r in records if r['released_unix']>s2['released_unix']]
    s3=next((r for r in later if r.get('purpose')=='S3 v142 single mixed no-prior smoke'),None)
    if s3 is None:raise ValueError('S3_NOT_RELEASED')
    ego=[]
    for seed in (54001,54002,54003,54004):
        row=next((r for r in later if r.get('purpose')==f'egomap54 teach/repeat seed{seed}'
                  and r['released_unix']>s3['released_unix']),None)
        if row is None:raise ValueError(f'EGOMAP54_SEED_{seed}_NOT_RELEASED')
        ego.append(row)
    speed=next((r for r in later if r.get('purpose')=='simspeed bounded ABBA (research first)'),None)
    if speed is None:raise ValueError('SIMSPEED_NOT_RELEASED')
    return dict(s2=s2,s3=s3,egomap54=ego,simspeed=speed)


def runtime_factory(b, clouds, index):
    if b['options'].get('heading_mode', 'off') == 'off':
        from scripts.run_s2_graduation59 import runtime_factory as original
        return original(b, clouds, index)
    plain = copy.deepcopy(b)
    guard = plain['options'].pop('active_rotation_guard')
    # Preserve the exact v140 snapshot/active attachment path, injecting only
    # the cooperative drive class at its existing runtime factory seam.
    factory = bind(unknown.runtime_factory, UnknownStart=runtime_class(UnknownStart))
    from types import SimpleNamespace
    make = bind(previous.runtime_factory, previous=SimpleNamespace(runtime_factory=factory))(plain, clouds, index)
    return lambda *a, **kw: envelope(make(*a, **kw), active_rotation_guard=guard)


def run(b, out):
    return bind(previous.run, contract=contract, runtime_factory=runtime_factory)(b, out)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--heading-mode', choices=('off', OPTION), default='off')
    p.add_argument('--output', type=Path, required=True)
    return p


def main():
    a = parser().parse_args()
    b = contract.bundle(a.expected_source_sha, a.seed, heading_mode=a.heading_mode)
    if not a.execute:
        print(json.dumps(dict(execution_started=False, bundle=b['execution_bundle_id'], options=b['options'])))
        return
    check_source(a.expected_source_sha)
    contract.require_execution(b)
    if os.getpriority(os.PRIO_PROCESS, 0) != 0:
        raise ValueError('nice must be zero; never renice')
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    expected = agent_lock.DEFAULT_ROOT.parent / f's2-heading-{a.expected_source_sha[:8]}-s{a.seed}-v143'
    if not a.output.is_absolute() or a.output.resolve() != expected.resolve() or a.output.exists():
        raise ValueError('new primary output required')
    predecessors=queue_receipt([json.loads(s) for s in
        (agent_lock.DEFAULT_ROOT/'released.jsonl').read_text().splitlines()])
    import shutil
    if shutil.disk_usage(a.output.parent).free < 10*1024**3:
        raise OSError(28,'ENOSPC preflight: less than 10 GiB')
    held = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/s2-heading',
        purpose=f'heading matched DEV s{a.seed}', pid=os.getpid(), expected_minutes=45, timing_sensitive=True)
    undo = None
    try:
        _, undo = install('v98-exact-v6')
        result = run(b, a.output)
        print(json.dumps({k: result.get(k) for k in ('status', 'failure', 'evaluation', 'wall_per_sim')}), flush=True)
    finally:
        if undo:
            undo()
        released = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
        if a.output.exists():
            write(a.output/'lock.json', dict(acquired=held, released=released,
                status_after=agent_lock.status(agent_lock.DEFAULT_ROOT),predecessors=predecessors))


if __name__ == '__main__':
    main()
