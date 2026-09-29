"""Build the v6c DRAFT prereg from the v6 registration (prepare-only; no approval, no execution source).

v6 was REGISTERED and run in PR #259; v6c drops its draft_registration receipt and starts as DRAFT.
The a+b rows become b-v6c (b-only + exact PF fix clock + grasp-range pre-grasp entry); v5h and
b-only stay as the matched controls, so b-only vs b-v6c isolates the two v6c fixes.

Only revision/bundle/contract/run-policy/denominator/readiness fields change;
every science field (environment, criteria, limits, timing, stage rules,
contact profile) is copied and asserted equal to v6 (and thereby to v5h).
Pattern: PR #261 build_prereg_v6b.py.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.zone_pair_authorization import digest, registration_payload  # noqa: E402
from scripts.zone_pair_v6_contract import PREREG, PREREG_V6C, contract    # noqa: E402

RENAME = {'v5h': ('v5h', 'v5h'), 'b-only': ('b', 'b-only'), 'a+b': ('bv6c', 'b-v6c')}
SCIENCE = ('schema', 'labels', 'research_result', 'environment', 'inputs', 'criteria', 'planned_setdown',
           'limits', 'safety_coverage', 'timing', 'stage_rules', 'contact_profile_contract',
           'baseline_registration', 'retries', 'disk_error_classification', 'model_calls')
# The scene receipt hashes executor sources; only these hashes may differ from v6.
SCENE_SOURCE_CHANGES = {'harness/zone_pair_executor.py', 'harness/zone_pair_guards.py', 'harness/zone_pair_grasp.py',
                        'harness/zone_pair_beam_track.py', 'harness/zone_pair_v6_policy.py',
                        'harness/zone_study_integration.py', 'scripts/run_zone_pair_dev.py',
                        'scripts/zone_pair_v6_contract.py',
                        # PR #249 (MasterPi v3, merged before the v6c resealing): the host and scene
                        # provider branch to v3 only for v3 maps; v2 maps keep the legacy scene, world
                        # and spawn keepouts (sim.zone_model_conventions delegates to zone_start_dock).
                        'harness/zone_own_team_host.py', 'sim/zone_own_scene_provider.py'}


def build():
    v6 = json.loads(PREREG.read_text())
    p = copy.deepcopy(v6)
    runs = []
    for run in v6['runs']:
        suffix, policy = RENAME[run['pair_policy']]
        runs.append({**copy.deepcopy(run), 'id': f"v6c-s{run['seed']}-{suffix}", 'pair_policy': policy})
    p.update(registration_revision='v6c', status='DRAFT', runnable=False, execution_status='not_run',
             execution_source_sha=None, execution_authorization=None, approval=None,
             execution_bundle_id=contract()['execution_bundle_id'], v6_contract=contract(), runs=runs,
             predecessor={'path': str(PREREG.relative_to(ROOT)), 'sha256': hashlib.sha256(PREREG.read_bytes()).hexdigest()},
             denominator=('Same two development seeds (911/912) x v5h / b-only / b-v6c, matched with the v6 '
                          'cohort (PR #259). Six nominal attempts; no pooling with v6, dev05-14 or M2. The v6c '
                          'fixes were designed from the 2026-09-28/29 stage-probe frames of these seeds, so this is a '
                          'paired development check, not a held-out result. tags_temporary manipulation diagnostic, '
                          'not research results.'))
    from scripts.zone_pair_dev_contract import scene_contract
    p['scene_contract'] = scene_contract()
    old, new = v6['scene_contract'], p['scene_contract']
    assert {k: v for k, v in old.items() if k not in ('source_sha256', 'sha256')} == \
        {k: v for k, v in new.items() if k not in ('source_sha256', 'sha256')}
    changed = {k for k in set(old['source_sha256']) | set(new['source_sha256'])
               if old['source_sha256'].get(k) != new['source_sha256'].get(k)}
    assert changed <= SCENE_SOURCE_CHANGES, changed
    p['scene_contract_changed_sources'] = sorted(changed)
    p['readiness'] = {**copy.deepcopy(v6['readiness']),
                      'requires': [*v6['readiness']['requires'],
                                   'align and grasp_lift stage-probe grids with b-v6c (scripts/run_pair_stage_probes.py) '
                                   'before any full v6c cohort',
                                   'v6c REGISTERED conversion through the PR #259 admission path (draft_registration + coordinator envelope)']}
    p.pop('draft_registration', None)
    p.pop('registration_sha256', None)
    p['registration_sha256'] = digest(registration_payload(p))
    for key in SCIENCE:
        assert p.get(key) == v6.get(key), key
    return p


if __name__ == '__main__':
    value = build()
    PREREG_V6C.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    print(PREREG_V6C, value['registration_sha256'])
