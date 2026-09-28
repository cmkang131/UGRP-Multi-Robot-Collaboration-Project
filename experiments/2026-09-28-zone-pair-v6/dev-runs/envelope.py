"""Write/print the late coordinator envelope for one run (working tree only; never committed).

usage: envelope.py digest <source_sha>            -> 6 approval lines
       envelope.py write <source_sha> <run_id> <comment_url>
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.zone_pair_authorization import approval_digest, digest, validate_authorization
from scripts.zone_pair_v6_contract import PREREG

p = json.loads(PREREG.read_text())
mode, sha = sys.argv[1], sys.argv[2]
if mode == 'digest':
    for r in p['runs']:
        print(approval_digest(sha, p['registration_sha256'], r['id']))
elif mode == 'write':
    run, ref = sys.argv[3], sys.argv[4]
    auth = {'by': 'coordinator', 'ref': ref, 'source_sha': sha,
            'registration_sha256': p['registration_sha256'], 'run_id': run}
    auth['sha256'] = digest(auth)
    p['execution_authorization'] = auth
    validate_authorization(p, execute=True, expected_source_sha=sha, run_id=run)
    PREREG.write_text(json.dumps(p, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(auth))
