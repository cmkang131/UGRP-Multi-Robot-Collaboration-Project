"""Build the v6d DRAFT prereg from the sealed v6c DRAFT (prepare-only; no approval, no execution source).

v6c (PR #263) is sealed and historical (``verify_v6_historical(revision='v6c')``, sealing commit be95f8b0),
so the b-v6d stage-probe fixes (wide-hue beam heading, M1 ``fine`` align motion profile) are a NEW revision
with its own bundle (v80) and source contract instead of a re-seal of v6c. The b-v6c rows become b-v6d; v5h
and b-only stay as the matched controls, so b-only vs b-v6d shows the v6c and v6d fixes together and
the stage probes (b-v6c vs b-v6d) show the v6d fixes alone.

Only revision/bundle/contract/run-policy/denominator/readiness fields change; every science field
(environment, criteria, limits, timing, stage rules, contact profile) is copied from v6c and asserted
equal (v6c asserted the same against v6 and v5h). Pattern: build_prereg_v6c.py (PR #263).
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.zone_pair_authorization import digest, registration_payload  # noqa: E402
from scripts.zone_pair_v6_contract import PREREG_V6C, PREREG_V6D, V6C_DRAFT_COMMIT, contract, verify_v6_historical  # noqa: E402

RENAME = {'v5h': ('v5h', 'v5h'), 'b-only': ('b', 'b-only'), 'b-v6c': ('bv6d', 'b-v6d')}
SCIENCE = ('schema', 'labels', 'research_result', 'environment', 'inputs', 'criteria', 'planned_setdown',
           'limits', 'safety_coverage', 'timing', 'stage_rules', 'contact_profile_contract',
           'baseline_registration', 'retries', 'disk_error_classification', 'model_calls')
# The scene receipt hashes executor sources; only these hashes may differ from v6c.
SCENE_SOURCE_CHANGES = {'harness/zone_pair_executor.py', 'harness/zone_pair_align.py', 'harness/zone_pair_v6_policy.py',
                        'harness/zone_study_integration.py', 'scripts/zone_pair_v6_contract.py',
                        'scripts/run_zone_pair_dev.py'}


def build():
    verify_v6_historical(revision='v6c')        # the predecessor is exactly its sealed record
    v6c = json.loads(PREREG_V6C.read_text())
    p = copy.deepcopy(v6c)
    runs = []
    for run in v6c['runs']:
        suffix, policy = RENAME[run['pair_policy']]
        runs.append({**copy.deepcopy(run), 'id': f"v6d-s{run['seed']}-{suffix}", 'pair_policy': policy})
    p.update(registration_revision='v6d', status='DRAFT', runnable=False, execution_status='not_run',
             execution_source_sha=None, execution_authorization=None, approval=None,
             execution_bundle_id=contract()['execution_bundle_id'], v6_contract=contract(), runs=runs,
             predecessor={'path': str(PREREG_V6C.relative_to(ROOT)),
                          'sha256': hashlib.sha256(PREREG_V6C.read_bytes()).hexdigest(),
                          'sealing_commit': V6C_DRAFT_COMMIT},
             denominator=('Same two development seeds (911/912) x v5h / b-only / b-v6d, matched with the v6 and '
                          'v6c cohorts. Six nominal attempts; no pooling with v6, v6c, dev05-14 or M2. The v6d '
                          'fixes were designed from the 2026-09-29 stage-2 replay of the b-v6c stage probe (12 of 25 '
                          'align cells failed) on cells that include these seeds, so this is a paired development '
                          'check, not a held-out result. tags_temporary manipulation diagnostic, not research '
                          'results. The stage probes (experiments/2026-09-29-pair-v6d-align) are not part of this '
                          'denominator.'))
    from scripts.zone_pair_dev_contract import scene_contract
    p['scene_contract'] = scene_contract()
    old, new = v6c['scene_contract'], p['scene_contract']
    assert {k: v for k, v in old.items() if k not in ('source_sha256', 'sha256')} == \
        {k: v for k, v in new.items() if k not in ('source_sha256', 'sha256')}
    changed = {k for k in set(old['source_sha256']) | set(new['source_sha256'])
               if old['source_sha256'].get(k) != new['source_sha256'].get(k)}
    assert changed <= SCENE_SOURCE_CHANGES, changed
    p['scene_contract_changed_sources'] = sorted(changed)
    p['readiness'] = {**copy.deepcopy(v6c['readiness']),
                      'requires': [*v6c['readiness']['requires'],
                                   'stage-2 align and stage-3 grasp+lift probe grids with b-v6d '
                                   '(scripts/run_pair_stage_probes.py, experiments/2026-09-29-pair-v6d-align) '
                                   'before any full v6d cohort',
                                   'v6d REGISTERED conversion through the PR #259 admission path (draft_registration + coordinator envelope)']}
    p.pop('draft_registration', None)
    p.pop('registration_sha256', None)
    p['registration_sha256'] = digest(registration_payload(p))
    for key in SCIENCE:
        assert p.get(key) == v6c.get(key), key
    return p


if __name__ == '__main__':
    value = build()
    PREREG_V6D.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    print(PREREG_V6D, value['registration_sha256'])
