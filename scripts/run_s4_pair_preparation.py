"""Read-only planning by default; execute requires a frozen post-S3 release.

Called by the standard registered run_s4_live CLI's opt-in --pair-mode. This
file deliberately does not import a simulator or create a model client.
"""
import hashlib
import json
from pathlib import Path
import re

from harness import s4_pair_stage as pair

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'experiments/2026-10-06-s4-llm/s4live4/README.md'


def validate_release(release, root=ROOT):
    if release.get('status') != 'ready':
        raise ValueError('S4_PAIR_WAITING_FOR_S3FIX13: no physics/model call is permitted')
    if (not re.fullmatch('[0-9a-f]{40}', release.get('s3_source_sha') or '')
            or not re.fullmatch(r'zone-s4-pair-live-v\d+', release.get('execution_bundle_id') or '')
            or not re.fullmatch(r'\d+\.\d+\.\d+', release.get('workflow_version') or '')
            or release.get('research_result') is not False or release.get('seed') != 601
            or release.get('cap_s') != 90. or release.get('pair_mode') != pair.hs.MODE):
        raise ValueError('S4_PAIR_RELEASE_INCOMPLETE')
    expected = release.get('s3_file_sha256') or {}
    required = {'harness/zone_s3_settled_servo.py', 'scripts/run_s3_settled_probe.py'}
    if not required <= set(expected) or not isinstance(release.get('settled_servo'), dict):
        raise ValueError('S3 candidate config/source receipt missing')
    for name, sha in expected.items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('S3 candidate source changed: '+name)
    return release


class Extension:
    def __init__(self, release):
        self.release = release

    def components(self):
        return pair.Link, pair.Host, {'handshake': pair.hs.Handshake()}

    def driver(self, host, runtime):
        from harness.zone_s3_alignment_entry import attach_endpoint as entry, OPTION
        from harness.zone_s3_settled_servo import attach_endpoint, Options
        options = Options(**self.release['settled_servo'])
        def admit(rid, ep, now):
            # A synthetic alignment entrance, not inferred navigation success.
            # Reobserve the current own camera; never restore stale saved RGB.
            entry(ep, alignment_entry=OPTION)
            attach_endpoint(ep, options)
            ep.controller.set('align_start', now, stage_probe_entry=True)
        return pair.Driver(host, runtime, on_admit=admit)


def dispatch(args):
    release = json.loads(args.pair_release.read_text())
    if not args.execute:
        print(json.dumps(dict(execution_started=False, research_result=False,
            pair_mode=pair.hs.MODE, release_status=release['status'],
            bundle_id=release['execution_bundle_id'], condition=args.condition, seed=601,
            cap_s=90., host='oracle-x86', ready=release['status']=='ready')))
        return 0
    validate_release(release)
    if args.cap_s != 90.:
        raise ValueError('pair batch has a frozen 90 SIM-second cap')
    from scripts import run_s4_live as live
    live.previous.archive_guard(args.expected_source_sha, args.output)
    b = live.bundle(args.expected_source_sha, args.condition, 90.)
    b.update(execution_bundle_id=release['execution_bundle_id'], workflow_version=release['workflow_version'],
        schema='ugrp.s4_pair_live.v1', pair_mode=pair.hs.MODE, s3_release=release,
        stage_scope='r1/r2 LLM claim-align-grasp-mutual-GO-carry; r3 claim-carry',
        handshake_deadline_s=pair.hs.HANDSHAKE_S, own_rgb_response_ttl_s=pair.hs.WINDOW_S,
        grip_monitor='LLM own RGB, unvalidated', no_scripted_claims=True)
    from harness.python_source_closure import source_closure
    paths = set(source_closure(ROOT, ['scripts/run_s4_pair_preparation.py']))
    paths.update((PLAN, str(args.pair_release.relative_to(ROOT) if args.pair_release.is_absolute() else args.pair_release)))
    b['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    # The existing ledger's preregistration receipt uses this key.
    from harness.zone_final_pair_binding import bind
    from harness.zone_pair_highpose_exact_speedups import install
    _, undo = install('v98-exact-v6')
    try:
        result = bind(live.run, PLAN=PLAN)(b, args.output, args.relay_receipt, pair_extension=Extension(release))
        print(json.dumps(result))
        return int(result['status']=='HOST_ERROR')
    finally:
        undo()
