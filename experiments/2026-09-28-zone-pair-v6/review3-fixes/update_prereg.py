"""Refresh prereg_v6 v6_contract (current source hashes, flag semantics, reobserve
budgets) and record registration_sha256 with scripts/zone_pair_authorization.py.
The DRAFT/prepare-only status, approvals and runs are unchanged."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.zone_pair_v6_contract import PREREG, contract
from scripts.zone_pair_authorization import digest, registration_payload

p = json.loads(PREREG.read_text())
before = {'v6_contract_sha256': digest(p['v6_contract']), 'registration_sha256': digest(registration_payload(p))}
p['v6_contract'] = contract()
p['execution_bundle_id'] = p['v6_contract']['execution_bundle_id']  # top-level mirror
p['registration_sha256'] = digest(registration_payload(p))
PREREG.write_text(json.dumps(p, indent=2, ensure_ascii=False)+'\n')
print(json.dumps({'before': before, 'after': {'v6_contract_sha256': digest(p['v6_contract']),
                                              'registration_sha256': p['registration_sha256']}}, indent=1))
