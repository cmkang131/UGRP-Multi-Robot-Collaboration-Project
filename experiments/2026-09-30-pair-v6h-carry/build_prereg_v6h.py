"""Prepare the fixed v6h cases, or create/verify the coordinator-authorized analysis seal.

python -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h --dry-run
python -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h --verify

build(), --dry-run and --verify remain current-tree previews. --seal writes the
separate two-commit registration once; --verify-seal audits it without reading raw.
Independent review is required before unblinding/merging this registration.
Science text comes from the final disclosure/definitions in PREREG_DRAFT.md;
the coordinator fixed A=48/60 and C=report-only before any outcome inspection.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from harness.zone_pair_v6_policy import EXECUTION_BUNDLE_ID, pair_policy  # noqa: E402
from scripts.zone_pair_v6_contract import (PREREG_V6E, V6E_DRAFT_COMMIT,  # noqa: E402
                                           candidate_contract, verify_v6_historical)

PLACEMENTS_SHA256 = 'bb8044058377d86efc658ce3a7458c8afc141680acfd98542260e0efda018454'
RESERVED = {'revision': 'v6h', 'policy': 'b-v6h1', 'bundle': 'zone-pair-v83-carry-door-gain', 'workflow': '2.16.0'}


def receipt(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def source_changes(old, new):
    return [{'path': path, 'old_sha256': old.get(path), 'new_sha256': new.get(path)}
            for path in sorted(set(old) | set(new)) if old.get(path) != new.get(path)]


def build():
    verify_v6_historical(revision='v6e')
    predecessor = json.loads(PREREG_V6E.read_text())
    placements = HERE/'placements_confirmatory_DRAFT.json'
    if receipt(placements)['sha256'] != PLACEMENTS_SHA256:
        raise ValueError('confirmatory placement bytes differ from PR #285 draft')
    rows = json.loads(placements.read_text())
    generator = importlib.import_module('experiments.2026-09-30-pair-v6h-carry.make_confirmatory_placements')
    if placements.read_text() != json.dumps(generator.draw(), indent=1) + '\n':
        raise ValueError('confirmatory placements differ from the fixed draw')
    from harness import owncam_carry_v6e as carry
    fit = carry.forward_gain_receipt(pair_policy('b-v6h1').carry_fwd_gain)
    closure = candidate_contract('v6h')
    from scripts.zone_pair_dev_contract import scene_contract
    runs = [{'id': f"v6h-{r['name']}-s{seed}-bv6h1", 'pair_policy': 'b-v6h1',
             'seed': seed, 'placement': r, 'primary': seed == 941}
            for seed, subset in ((941, rows), (943, rows[:12])) for r in subset]
    science = (HERE/'PREREG_DRAFT.md').read_text()
    value = {'schema': 'ugrp.zone_pair_v6h_confirmatory.DRAFT.v1', 'status': 'DRAFT',
            'sealed': False, 'runnable': False, 'registration_revision': 'v6h',
            'registration_sha256': None, 'execution_source_sha': None,
            'execution_authorization': None, 'approval': None, 'execution_status': 'not_run',
            'cohort_kind': 'teacher_staged_pair_chain_L0_L1',
            'execution_bundle_id': EXECUTION_BUNDLE_ID, 'reserved_ids': RESERVED,
            'predecessor': {**receipt(PREREG_V6E), 'sealing_commit': V6E_DRAFT_COMMIT},
            'v6_contract': closure, 'scene_contract': scene_contract(),
            'contact_profile_contract': predecessor['contact_profile_contract'],
            'fit': fit, 'placements': receipt(placements),
            'confirmatory_plan': {'source': receipt(HERE/'PREREG_DRAFT.md'), 'text_verbatim': science,
                'coordinator_decisions': {'carry_axial_lag': True, 'sigma_scope': pair_policy('b-v6h1').door_relax_sigma_scope,
                                          'progress_rule': 'p2f; no reliable stall detection for the loaded pair'},
                'default_A': {'pass_at_least': 48, 'n_placements': 60,
                              'claim': 'observed fixed-cohort rate, not population >=80%'},
                'default_C': 'report-only, not an adoption gate',
                'primary_seed': 941, 'sensitivity_seed': 943, 'sensitivity_n': 12,
                'classification': {'hard_limits_first': True, 'whole_chain': True,
                                   'categories': ['PASS_CLEAN', 'PASS_CONTACT_RECOVERED', 'BLOCKED_BY_CONTACT',
                                                  'FAIL', 'FAIL_HARD_LIMIT']},
                'operation': {'clock': 'SIM', 'weld': False, 'model_calls': 0,
                              'stage': 'chain', 'chain_stop_leg': 1, 'sources': ['teacher'],
                              'policy': 'b-v6h1', 'pf_track': True, 'contact_track': True,
                              'render_profile': 'floor_light_v1', 'workers': 4, 'omp_threads': 1,
                              'case_timeout_s': 1500.,
                              'raw_root': '/Users/changmin/projects/ugrp/outputs',
                              'enospc': 'HOST_ERROR', 'minimum_free_gib': 10}},
            'runs': runs,
            'changed_sealed_sources': source_changes(predecessor['v6_contract']['source_sha256'], closure['source_sha256']),
            'qualification': 'UNSEALED preview; no physical replay, confirmatory result or execution admission'}
    from scripts.zone_pair_v6h_admission import cases_for_plan
    value['cases'] = cases_for_plan(value)
    # Match the committed thin-driver plan's JSON key order, not just values.
    # No execution/admission/controller source is changed by this formatting.
    for case in value['cases']:
        case['chain_stop_leg'] = case.pop('chain_stop_leg')
    return value


def verify(value):
    if value != build():
        raise ValueError('candidate preview differs from current sources or fixed draft inputs')
    if value['sealed'] or value['runnable'] or value['registration_sha256'] is not None:
        raise ValueError('pre-seal preview must never contain an admission seal')
    assert len(value['runs']) == 72 and sum(r['primary'] for r in value['runs']) == 60
    return {'status': 'verified_unsealed', 'runs': 72, 'sources': len(value['v6_contract']['source_sha256'])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='print source changes; no writes')
    mode.add_argument('--verify', action='store_true', help='verify fixed draw, predecessor, fit and sources; no writes')
    mode.add_argument('--seal', action='store_true', help='write coordinator-authorized seal once; never overwrite')
    mode.add_argument('--verify-seal', action='store_true', help='audit separate execution/analysis pins; no raw')
    parser.add_argument('--seal-commit', help='commit containing this seal (analysis git-blob verification)')
    args = parser.parse_args(argv)
    if args.seal or args.verify_seal:
        module = importlib.import_module('experiments.2026-09-30-pair-v6h-carry.analysis.seal_registration')
        path = HERE/'prereg_v6h.json'
        if args.seal:
            if path.exists():
                raise FileExistsError('sealed registration is immutable; write a new revision')
            value = module.build_seal(build())
            module.verify_seal(value)
            with path.open('x') as stream:
                stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
        value = json.loads(path.read_bytes())
        print(json.dumps(module.verify_seal(value, args.seal_commit), indent=2))
        return 0
    value = build()
    print(json.dumps(verify(value) if args.verify else {
        'status': 'UNSEALED', 'reserved_ids': RESERVED, 'runs': len(value['runs']),
        'changed_sealed_sources': value['changed_sealed_sources'],
        'final_steps': 'separate coordinator commit: prereg_v6h.json seal + CURRENT_REVISION after independent review'},
        indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
