"""Build the v6e DRAFT prereg from the sealed v6d DRAFT (prepare-only; no approval, no execution source).

v6d (PR #265) is sealed and historical (``verify_v6_historical(revision='v6d')``, sealing commit 48f9872a),
so the b-v6g carry stage-probe flags (dead-reckoning PF model with lateral breakaway ramp and cross-axis drift,
pair-mean carry yaw, beam-edge relative yaw, optical-black image validity, bounded retreat) are a NEW revision
with its own bundle (v81) and source contract instead of a re-seal of v6d. The b-v6d rows become b-v6g; v5h
and b-only stay as the matched controls.

Only revision/bundle/contract/run-policy/denominator/readiness fields change; every science field
(environment, criteria, limits, timing, stage rules, contact profile) is copied from v6d and asserted
equal. Pattern: build_prereg_v6d.py (PR #265).
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.zone_pair_authorization import digest, registration_payload  # noqa: E402
from scripts.zone_pair_v6_contract import PREREG_V6D, PREREG_V6E, V6D_DRAFT_COMMIT, contract, verify_v6_historical  # noqa: E402

RENAME = {'v5h': ('v5h', 'v5h'), 'b-only': ('b', 'b-only'), 'b-v6d': ('bv6g', 'b-v6g')}
SCIENCE = ('schema', 'labels', 'research_result', 'environment', 'inputs', 'criteria', 'planned_setdown',
           'limits', 'safety_coverage', 'timing', 'stage_rules', 'contact_profile_contract',
           'baseline_registration', 'retries', 'disk_error_classification', 'model_calls')
# The scene receipt hashes scene closure sources; only run_zone_pair_dev.py changed since the sealed v6d DRAFT
# (its --pair-policy choices gained b-v6g).
SCENE_SOURCE_CHANGES = {'scripts/run_zone_pair_dev.py'}


def build():
    verify_v6_historical(revision='v6d')        # the predecessor is exactly its sealed record
    v6d = json.loads(PREREG_V6D.read_text())
    p = copy.deepcopy(v6d)
    runs = []
    for run in v6d['runs']:
        suffix, policy = RENAME[run['pair_policy']]
        runs.append({**copy.deepcopy(run), 'id': f"v6e-s{run['seed']}-{suffix}", 'pair_policy': policy})
    p.update(registration_revision='v6e', status='DRAFT', runnable=False, execution_status='not_run',
             execution_source_sha=None, execution_authorization=None, approval=None,
             execution_bundle_id=contract()['execution_bundle_id'], v6_contract=contract(), runs=runs,
             predecessor={'path': str(PREREG_V6D.relative_to(ROOT)),
                          'sha256': hashlib.sha256(PREREG_V6D.read_bytes()).hexdigest(),
                          'sealing_commit': V6D_DRAFT_COMMIT},
             denominator=('Same two development seeds (911/912) x v5h / b-only / b-v6g, matched with the v6, v6c and '
                          'v6d cohorts. Six nominal attempts; no pooling with earlier cohorts, dev05-14 or M2. The v6e '
                          'carry flags were designed and fitted from the 2026-09-29 carry stage probes of these seeds\' '
                          'geometry (experiments/2026-09-29-pair-v6e-carry: cal placements for the fit, hR2 for the '
                          'criteria check), so this is a paired development check, not a held-out result. tags_temporary '
                          'manipulation diagnostic, not research results. The stage probes are not part of this '
                          'denominator.'))
    from scripts.zone_pair_dev_contract import scene_contract
    p['scene_contract'] = scene_contract()
    old, new = v6d['scene_contract'], p['scene_contract']
    assert {k: v for k, v in old.items() if k not in ('source_sha256', 'sha256')} == \
        {k: v for k, v in new.items() if k not in ('source_sha256', 'sha256')}
    changed = {k for k in set(old['source_sha256']) | set(new['source_sha256'])
               if old['source_sha256'].get(k) != new['source_sha256'].get(k)}
    assert changed <= SCENE_SOURCE_CHANGES, changed
    p['scene_contract_changed_sources'] = sorted(changed)
    p['readiness'] = {**copy.deepcopy(v6d['readiness']),
                      'requires': [*v6d['readiness']['requires'],
                                   'carry stage probes with b-v6g (scripts/run_pair_stage_probes.py, '
                                   'experiments/2026-09-29-pair-v6e-carry: hR2 56/70 at the 80 % threshold, door legs L0/L1 6/20) '
                                   'before any full v6e cohort',
                                   'v6e REGISTERED conversion through the PR #259 admission path (draft_registration + coordinator envelope)']}
    p.pop('draft_registration', None)
    p.pop('registration_sha256', None)
    p['registration_sha256'] = digest(registration_payload(p))
    for key in SCIENCE:
        assert p.get(key) == v6d.get(key), key
    return p


if __name__ == '__main__':
    value = build()
    PREREG_V6E.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    print(PREREG_V6E, value['registration_sha256'])
