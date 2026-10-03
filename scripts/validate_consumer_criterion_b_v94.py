"""Kinematic eligibility gate v94; frozen v91 outputs remain reproducible.

--pose audits only position/rotation/time, before any scoring or result reads.
--v91-raw applies this mandatory gate before the historical v91 scorer. The
v91 corridor counterexample therefore cannot produce residuals in this version.
Neither a DISJOINT result nor a headless precheck is a criterion B pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from harness.kinematic_overlap import POLICY, audit, read_trace

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'configs/criterion_b_prior_kinematics_v94.json'
FROZEN = ROOT / 'experiments/2026-10-03-critb-heldout-v94/frozen.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_frozen():
    hashes = json.loads(FROZEN.read_text())
    for name, expected in hashes.items():
        if sha(ROOT/name) != expected:
            raise ValueError('frozen source/candidate changed: '+name)
    return hashes


def load_prior(manifest=CORPUS):
    record = json.loads(Path(manifest).read_text())
    if record['schema'] != 'ugrp.criterion_B_prior_kinematics.v94' or record['policy'] != POLICY:
        raise ValueError('exclusion corpus/policy mismatch')
    if not record['files'] or len({r['path'] for r in record['files']}) != len(record['files']):
        raise ValueError('empty/duplicate exclusion corpus')
    traces = []
    for item in record['files']:
        t = read_trace(item['path'])
        if t.sha256 != item['kinematic_sha256'] or len(t.t) != item['samples']:
            raise ValueError('exclusion corpus kinematic hash changed: '+item['path'])
        # Historical candidate byte hashes are provenance ONLY, never exclusion
        # identity. Do not read/hash non-kinematic v91 fields, even for provenance.
        if 'source_byte_sha256' in item:
            if any(p.startswith('final-pair-v91-heldout-') for p in Path(item['path']).parts):
                raise ValueError('v91 whole-file hash forbidden')
            if sha(item['path']) != item['source_byte_sha256']:
                raise ValueError('prior provenance hash changed: '+item['path'])
        traces.append(t)
    # Corpus cannot silently omit any of the five source hashes in frozen r4/r5.
    from scripts import validate_consumer_criterion_b_v91 as old
    known = {r.get('source_byte_sha256') for r in record['files']}
    for path in (old.frozen.CANDIDATE, old.ROTATION_CANDIDATE):
        if not set(json.loads(path.read_text())['previously_seen_pose_sha256']) <= known:
            raise ValueError('exclusion corpus omits a frozen candidate prior')
    return traces


def validate_poses(paths, *, prior=None):
    verify_frozen()
    candidates = [read_trace(p) for p in paths]
    prior = load_prior() if prior is None else prior
    result = audit(candidates, prior)
    result.update(schema='ugrp.consumer_B_kinematic_eligibility.v94',
                  scope='KINEMATIC_ELIGIBILITY_ONLY', criterion_B_pass=None,
                  previously_seen=result['status'] == 'PREVIOUSLY_SEEN',
                  note='DISJOINT is not scoring, acquisition chronology or collection success')
    return result


def validate_v91(raws, *, rotation_addendum=False, refetch=False):
    """Fail before touching any v91 score/result when a robot repeats a trace."""
    from scripts import validate_consumer_criterion_b_v91 as old
    paths = []
    for raw in raws:
        root = Path(raw)
        # Do not use old.collection_root here: its result/bundle probes are not
        # needed for the kinematics-only first stage.
        found = sorted(root.glob('**/eval_only/r[12]/pose.jsonl'))
        if not found:
            raise ValueError('no r1/r2 kinematic inputs')
        paths.extend(found)
    novelty = validate_poses(paths)
    if novelty['previously_seen']:
        report = old.ineligible('PREVIOUSLY_SEEN_KINEMATICS')
    else:
        report = old.validate(raws, refetch=refetch, rotation_addendum=rotation_addendum)
    report['schema'] = 'ugrp.consumer_B_validation.v94.v91_compatibility'
    report['kinematic_eligibility'] = novelty
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--pose', type=Path, action='append')
    group.add_argument('--v91-raw', type=Path, action='append')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--rotation-addendum', action='store_true')
    p.add_argument('--refetch-commitment', action='store_true')
    args = p.parse_args(argv)
    if any(args.output.resolve() == p.resolve() for p in (args.pose or [])):
        raise ValueError('output must not replace an input')
    if any(args.output.resolve().is_relative_to(p.resolve()) for p in (args.v91_raw or [])):
        raise ValueError('output must be outside raw')
    result = (validate_poses(args.pose) if args.pose else validate_v91(args.v91_raw,
              rotation_addendum=args.rotation_addendum, refetch=args.refetch_commitment))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    if args.pose:
        print(result['status'])
        return int(result['previously_seen'])
    print(result['scope'])
    return 0 if result['pass'] is True else (1 if result['pass'] is False else 2)


if __name__ == '__main__':
    raise SystemExit(main())
