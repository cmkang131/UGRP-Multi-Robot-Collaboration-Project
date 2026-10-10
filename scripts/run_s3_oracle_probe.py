"""v154-derived stage probes on committed Oracle ARM/OSMesa archives only."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil

from harness.zone_final_pair_binding import bind
from harness.zone_s3_alignment_entry import attach_endpoint, OPTION
from harness.python_source_closure import source_closure
from scripts import run_s3_alignment_probe as previous
from scripts import run_s3_alignment_entry_probe as entry

ROOT = previous.ROOT
BUNDLE_ID = 'zone-s3-oracle-stage-probe-v155'
WORKFLOW_VERSION = '7.48.0'
FIXTURE = 'experiments/2026-10-09-s3-no-prior/s3fix10/scene-setup.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_oracle_stage_probe_v155.json'


def setup_record(_raw, case):
    fixture = json.loads((ROOT/FIXTURE).read_text())
    assert fixture['eval_only_setup'] and fixture['source_t'] == previous.STAGE_T
    return copy.deepcopy(fixture['cases'][case])


def bundle(sha, case, alignment_entry=OPTION):
    if alignment_entry not in ('off', OPTION): raise ValueError('unregistered alignment entry')
    b = entry.bundle(sha, case)
    b.update(execution_bundle_id=BUNDLE_ID, workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_oracle_stage_probe.v155', host='oracle-a1', render_backend='osmesa',
        alignment_entry=alignment_entry, stop_after_close=case != 'cyan',
        stage_scope='align-hover-descent-close' if case == 'pair' else 'align-hover-descent-close-lift-carry',
        setup_fixture=FIXTURE, source_raw='committed evaluation-side setup extract',
        wall_cap_s=1800., parent_bundles=[*b['parent_bundles'], entry.BUNDLE_ID],
        comparison_scope='same Oracle ARM/OSMesa cohort only; no Mac byte-equivalence claim')
    paths = set(b['source_sha256']) | set(source_closure(ROOT, ['scripts/run_s3_oracle_probe.py']))
    paths.update((FIXTURE, WORKFLOW, 'experiments/2026-10-09-s3-no-prior/s3fix10/README.md'))
    b['source_sha256'] = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
    return b


def archive_guard(sha, output):
    if not re.fullmatch('[0-9a-f]{40}', sha): raise ValueError('full committed SHA required')
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64') or os.environ.get('MUJOCO_GL') != 'osmesa':
        raise ValueError('Oracle ARM/OSMesa execution only; Mac execution prohibited')
    if output.is_absolute() or len(output.parts) != 3 or output.parts[0] != 'outputs' or output.parts[2] != 'raw' or '..' in output.parts:
        raise ValueError('output must be outputs/<run-name>/raw')
    if ROOT.name != sha or (output.resolve().parent/'SOURCE_SHA').read_text().strip() != sha:
        raise ValueError('oracle_run archive/source receipt mismatch')
    if output.exists(): raise ValueError('new immutable output required')
    if os.getpriority(os.PRIO_PROCESS, 0) != 0: raise ValueError('nice zero required')
    if shutil.disk_usage(output.parent).free < 11*1024**3: raise OSError('10GiB reserve plus1GiB probe budget required')


def run(b, out):
    audits = {}
    def enter_pair(rt, now, ignored_option):
        eps = previous.enter_pair(rt, now, 'off')
        for rid, ep in eps.items():
            attach_endpoint(ep, alignment_entry=b['alignment_entry'])
            if b['alignment_entry'] != 'off': audits[rid] = ep.controller.s3_alignment_entry
            ep.controller.set('align_start', now, stage_probe_entry=True)
        return eps
    original_environment = previous.environment_record
    def environment_record():
        return {**original_environment(), 'host': 'oracle-a1', 'MUJOCO_GL': os.environ['MUJOCO_GL'],
            'machine': platform.machine(), 'concurrent_probe_limit': 3,
            'source_mode': 'oracle_run committed git archive; no local Mac execution'}
    result = bind(previous.run, setup_record=setup_record, enter_pair=enter_pair,
        environment_record=environment_record)(b, out)
    result.update(host='oracle-a1', alignment_entry=b['alignment_entry'], stage_scope=b['stage_scope'])
    # The existing host terminates actual tilt/drop faults. Preserve its full
    # traceback and classify that terminal separately from execution errors.
    match = re.search(r'^sim\.zone_s3_no_prior\.PhysicalStop: (.+)$', result.get('failure', ''), re.M)
    if match: result.update(status='PHYSICAL_STOP', physical_stop=match.group(1))
    previous.write(out/'result.json', result)
    previous.write(out/'alignment-entry.json', dict(option=b['alignment_entry'], robots=copy.deepcopy(audits)))
    previous.artifact_manifest(out)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(); p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--case', choices=['pair', 'cyan'], default='pair')
    p.add_argument('--alignment-entry', choices=['off', OPTION], default=OPTION)
    p.add_argument('--execute', action='store_true'); a = p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False, bundle_id=BUNDLE_ID, host='oracle-a1', case=a.case, cap_sim_s=60.)))
        return 0
    archive_guard(a.expected_source_sha, a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _, undo = install('v98-exact-v6')
    try:
        result = run(bundle(a.expected_source_sha, a.case, a.alignment_entry), a.output)
        print(json.dumps(result)); return int(result['status'] == 'HOST_ERROR')
    finally: undo()


if __name__ == '__main__': raise SystemExit(main())
