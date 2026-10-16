"""DRAFT -> REGISTERED for the six v6 dev runs (2026-09-28, Claude).

Administrative fields only. Scientific content (environment, inputs, criteria,
stage_rules, limits, timing, runs, v6 flags/budgets) is untouched; only the
v6_contract source hash of scripts/zone_pair_v6_contract.py changes because the
loader gained the registered execution path. The DRAFT bytes stay in git at
DRAFT_COMMIT and are bound below by sha256.
"""
import hashlib, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.zone_pair_v6_contract import PREREG, contract
from scripts.zone_pair_authorization import digest, registration_payload

DRAFT_COMMIT = 'e8ff18822050c957993eb3d4c569d574186c1526'
rel = PREREG.relative_to(ROOT).as_posix()
draft_bytes = subprocess.check_output(['git', 'show', f'{DRAFT_COMMIT}:{rel}'], cwd=ROOT)
draft = json.loads(draft_bytes)
assert draft['status'] == 'DRAFT' and PREREG.read_bytes() == draft_bytes, 'start from the merged DRAFT bytes'
p = json.loads(draft_bytes)
SCIENTIFIC = ('schema', 'labels', 'research_result', 'environment', 'inputs', 'criteria', 'planned_setdown',
              'limits', 'safety_coverage', 'timing', 'stage_rules', 'contact_profile_contract', 'runs',
              'scene_contract', 'baseline_registration', 'predecessor', 'planned_run_count', 'denominator',
              'retries', 'disk_error_classification', 'model_calls', 'execution_bundle_id')
p['status'] = 'REGISTERED'
p['runnable'] = True
p['draft_registration'] = {'path': rel, 'commit': DRAFT_COMMIT,
                           'sha256': hashlib.sha256(draft_bytes).hexdigest(),
                           'registration_sha256': draft['registration_sha256']}
p['readiness'] = {**draft['readiness'],
                  'status': 'DEV_EXECUTION_AUTHORIZED_OPEN_REQUIREMENTS',
                  'draft_status': draft['readiness']['status'],
                  'open_at_execution': ['relative/global bound calibration',
                                        'markerless provider and shape coverage'],
                  'decision': ('2026-09-28 manager session authorized the six dev runs on the user delegation '
                               '(merges approved; run decisions delegated). Open requirements are disclosed, '
                               'not waived as evidence: results stay tags_temporary dev diagnostics.')}
p['v6_contract'] = contract()
for k in SCIENTIFIC:
    assert p[k] == draft[k], k
changed = sorted(k for k in set(p) | set(draft) if p.get(k) != draft.get(k))
changed_src = sorted(k for k in p['v6_contract']['source_sha256']
                     if p['v6_contract']['source_sha256'][k] != draft['v6_contract']['source_sha256'].get(k))
assert set(changed) <= {'status', 'runnable', 'draft_registration', 'readiness', 'v6_contract', 'registration_sha256'}
assert changed_src == ['scripts/zone_pair_v6_contract.py'], changed_src
assert {k: v for k, v in p['v6_contract'].items() if k != 'source_sha256'} == \
       {k: v for k, v in draft['v6_contract'].items() if k != 'source_sha256'}
p['registration_sha256'] = digest(registration_payload(p))
PREREG.write_text(json.dumps(p, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({'changed_fields': changed + ['registration_sha256'], 'changed_source_hashes': changed_src,
                  'draft_sha256': p['draft_registration']['sha256'],
                  'draft_registration_sha256': draft['registration_sha256'],
                  'registration_sha256': p['registration_sha256'],
                  'file_sha256': hashlib.sha256(PREREG.read_bytes()).hexdigest()}, indent=1))
