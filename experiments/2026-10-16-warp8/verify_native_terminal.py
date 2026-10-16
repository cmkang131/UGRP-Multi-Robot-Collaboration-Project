"""Recheck immutable native gate evidence on gcp3 CPU, without simulation.

Physical verdicts come from collect_gate.py's frozen evaluator criteria.
This file verifies recorded invariants and hashes; it never grants admission.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import socket
import statistics


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--recount', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    assert socket.gethostname().split('.')[0] == 'ugrp-act-l4-gcp3'
    assert a.run.parent == Path('/home/ugrp/ugrp-sim/runs/warp8')
    assert not a.out.exists()
    summary = json.loads((a.run / 'summary.json').read_text())
    receipt = json.loads(a.run.with_suffix('.receipt.json').read_text())
    proc = Path('/proc') / str(receipt['pid']) / 'cmdline'
    assert not proc.exists() or str(a.run).encode() not in proc.read_bytes().split(b'\0')
    recount = json.loads(a.recount.read_text())
    attempt, = recount['attempts']
    assert attempt['name'] == a.run.name and attempt['terminal']
    options = json.loads((a.run / 'native-contact-options.json').read_text())
    expected = dict(noslip_iterations=0, cone=1, integrator=3, impratio=5.,
                    iterations=80, ls_iterations=50)
    assert all(all(world[k] == v for k, v in expected.items()) for world in options['worlds'])
    profile_sha = 'a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a'
    assert summary['contact_profile']['module_sha256'] == profile_sha
    assert summary['weld'] == 'off' and summary['model_calls'] == 0
    assert summary['placement_graspable_filter_v1']
    source = Path('/home/ugrp/ugrp-sim/src') / summary['source_sha']
    assert sha(source / 'sim/warp_native_contact.py') == profile_sha
    manifest_path = a.run / 'artifact-sha256.json'
    declaration = summary['artifact_sha256_manifest']
    assert sha(manifest_path) == declaration['sha256']
    declared = json.loads(manifest_path.read_text())
    assert len(declared) == declaration['files']
    bad = []
    total_bytes = 0
    for relative, expected_file in declared.items():
        path = a.run / relative
        if not path.is_file() or path.stat().st_size != expected_file['bytes'] or sha(path) != expected_file['sha256']:
            bad.append(relative)
        total_bytes += expected_file['bytes']
    assert not bad, bad
    worlds = {row['world']: row for row in summary['worlds']}
    assert attempt['completed_N'] == len(worlds)
    assert all(row['recount']['agrees'] and row['audit_pass'] and row['weld'] == 'off'
               for row in attempt['worlds'])
    assert all(row['cap_end'] == worlds[row['world']]['cap_end'] for row in attempt['worlds'])
    assert not recount['read_errors']
    resource_rows = [json.loads(line) for line in a.run.with_suffix('.resources.jsonl').read_text().splitlines()]
    gpu = [float(row['gpu'].split(',')[1]) for row in resource_rows if row['gpu']]
    memory = [float(row['gpu'].split(',')[0]) for row in resource_rows if row['gpu']]
    result = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        simulation_host='gcp3', analysis_host='gcp3_CPU', contact_profile='warp_native_contact_v1',
        source_sha=summary['source_sha'], raw=str(a.run), receipt=receipt,
        raw_summary_sha256=sha(a.run / 'summary.json'), recount=str(a.recount),
        recount_sha256=sha(a.recount), N=attempt['N'], completed_N=attempt['completed_N'],
        success_N=attempt['success_N'], cap_end_N=attempt['cap_end_N'],
        HOST_ERROR_world_N=attempt['HOST_ERROR_world_N'],
        evaluator_agreement_N=len(attempt['worlds']), terminal_control_input_audit_pass_N=len(attempt['worlds']),
        input_audit_scope_counts=dict(Counter(row['input_audit']['scope'] for row in attempt['worlds'])),
        privileged_scene_preparation_prefix_excluded=(summary['flow'] == 'release'),
        declared_files_SHA_equal_N=len(declared), declared_file_bytes=total_bytes,
        raw_manifest_sha256=sha(manifest_path), options_N=len(options['worlds']),
        weld='off', model_calls=0, placement_graspable_filter_v1=True,
        first30=attempt['first30'], batch_sim_s=attempt['batch_sim_s'],
        per_world_wall_SIM=attempt['per_world_wall_SIM'], task_wall_per_SIM=attempt['task_wall_per_SIM'],
        setup_wall_s=attempt['setup_wall_s'], loop_wall_s=attempt['loop_wall_s'],
        GPU=dict(samples=len(gpu), utilization_median_pct=statistics.median(gpu) if gpu else None,
                 memory_max_MiB=max(memory) if memory else None),
        no_pooling=True, continue_authorized=False,
        scope='terminal raw evidence only; playback review and explicit admission remain separate')
    a.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: result[k] for k in ('N','completed_N','success_N','cap_end_N',
        'HOST_ERROR_world_N','declared_files_SHA_equal_N','per_world_wall_SIM')}))


if __name__ == '__main__':
    main()
