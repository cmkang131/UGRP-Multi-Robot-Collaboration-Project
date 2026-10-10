"""v154 saved-scene probe through actual align_start; <=60 SIM seconds."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

from harness.zone_final_pair_binding import bind
from harness.zone_s3_alignment_entry import attach_endpoint, OPTION
from scripts import run_s3_alignment_probe as previous

BUNDLE_ID = 'zone-s3-alignment-entry-probe-v154'
WORKFLOW_VERSION = '7.47.0'
ROOT = previous.ROOT
WORKFLOW = 'configs/simulation_workflows.d/s3_alignment_entry_probe_v154.json'


def bundle(sha, case):
    b = previous.bundle(sha, case, 'off')
    b.update(execution_bundle_id=BUNDLE_ID, workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_alignment_entry_probe.v154', alignment_entry=OPTION,
        servo_option='off', entry_path='saved own history -> actual align_start -> unchanged RGB servo')
    from harness.python_source_closure import source_closure
    paths = set(b['source_sha256']) | set(source_closure(ROOT,
        ['scripts/run_s3_alignment_entry_probe.py', 'harness/zone_s3_proposal_runtime.py']))
    paths.update((WORKFLOW, 'experiments/2026-10-09-s3-no-prior/s3fix9/README.md'))
    b['source_sha256'] = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
    return b


def enter_pair(rt, now, ignored_option):
    eps = previous.enter_pair(rt, now, 'off')
    for ep in eps.values():
        attach_endpoint(ep, alignment_entry=OPTION)
        # Restore history as v153 did, then exercise the real entry transition.
        # No RGB aligned claim is injected and no port/servo metadata is forged.
        ep.controller.set('align_start', now, stage_probe_entry=True)
    return eps


def run(b, out):
    entries = {}
    def entered(*args):
        eps = enter_pair(*args)
        entries.update({r: ep.controller.s3_alignment_entry for r, ep in eps.items()})
        return eps
    result = bind(previous.run, enter_pair=entered)(b, out)
    previous.write(out/'alignment-entry.json', dict(option=OPTION, robots=copy.deepcopy(entries)))
    previous.artifact_manifest(out)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(); p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--case', choices=['pair', 'cyan'], default='pair')
    p.add_argument('--execute', action='store_true'); a = p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False, bundle_id=BUNDLE_ID, case=a.case, cap_sim_s=previous.CAP)))
        return 0
    previous.check_source(a.expected_source_sha)
    if os.getpriority(os.PRIO_PROCESS, 0) != 0: raise ValueError('nice zero required')
    from scripts import agent_lock
    primary = agent_lock.DEFAULT_ROOT.parent
    if not a.output.is_absolute() or primary.resolve() not in a.output.resolve().parents or a.output.exists():
        raise ValueError('new primary output required')
    if shutil.disk_usage(primary).free < 11*1024**3: raise OSError('10GiB reserve plus1GiB probe budget required')
    acquired = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/s3-no-prior-smoke',
        purpose='s3fix9 alignment entry '+a.case+' <=60 SIM s', pid=os.getpid(), expected_minutes=15)
    try:
        result = run(bundle(a.expected_source_sha, a.case), a.output)
        previous.write(a.output/'lock-acquired.json', acquired)
    finally:
        held = agent_lock.status(agent_lock.DEFAULT_ROOT)
        if held and held['pid'] == os.getpid(): agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
    print(json.dumps(result)); return int(result['status'] == 'HOST_ERROR')


if __name__ == '__main__': raise SystemExit(main())
