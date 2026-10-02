"""Read-only full-byte provenance audit; run separately against base and PR trees."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.root.resolve()))
from harness import zone_final_pair_contract as c
from harness import zone_final_pair_heldout as v90
from harness.zone_final_pair_excitation import MAP_ID
from scripts import run_final_pair_v3, run_final_pair_heldout
from sim.workflow_manager import source_fingerprint


def writer_sha(value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    return hashlib.sha256(raw).hexdigest()


report = {'root': str(args.root), 'cases': {}, 'execution_tree': source_fingerprint(args.root)}
cases = [(c, run_final_pair_v3, map_id, check) for check in c.CHECKS
         for map_id in sorted({case['map_id'] for case in c.cases(check)})]
cases += [(v90, run_final_pair_heldout, map_id, v90.CHECK) for map_id in v90.MAPS]
for contract, runner, map_id, check in cases:
    bundle = contract.bundle(map_id, check)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        runner.main(['--check', check, '--map-id', map_id, '--seed', '911',
                     '--expected-source-sha', 'a'*40, '--output', '/private/tmp/review355-plan-unused'])
    plan = json.loads(out.getvalue())
    report['cases'][f'{contract.BUNDLE_ID}/{map_id}/{check}'] = {
        'source_sha256': bundle['source_sha256'],
        'bundle_writer_sha256': writer_sha(bundle),
        'bundle_digest': c.base.digest(bundle),
        'plan_writer_sha256': hashlib.sha256(out.getvalue().encode()).hexdigest(),
        'plan_bundles_sha256': plan['bundles_sha256'],
    }
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2)+'\n')
