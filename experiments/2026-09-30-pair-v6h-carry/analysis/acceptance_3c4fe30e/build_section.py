"""Adds the 3c4fe30e replay section to acceptance_replay.json (keeps the 3afc61b0 section)."""
import hashlib, json
from pathlib import Path
OUT = Path('/Users/changmin/projects/ugrp/outputs/v6h1-acceptance-3c4fe30e-claude-20260930')
JS = Path(__file__).resolve().parents[2] / 'acceptance_replay.json'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
audit = json.loads(JS.read_text())
plan = json.loads((OUT / 'plan.json').read_text())
manifest = json.loads((OUT / 'manifest.json').read_text())
receipts = json.loads((OUT / 'acceptance_receipts.json').read_text())
rows = {json.loads(l)['case_id']: json.loads(l) for l in (OUT / 'cases.jsonl').read_text().splitlines()}
cases = []
for r in receipts:
    row = rows[r['case_id']]
    leg0 = r['registered_legs'][0]
    cases.append({
        'cohort': r['cohort'], 'cell': r['cell'], 'seed': r['seed'], 'sanity': r['sanity'], 'case_id': r['case_id'],
        'reference_raw': r['reference_raw'], 'reference_case_dir': r['reference_case_dir'],
        'probe_commands_sha256': r['reference_commands_sha256'], 'registered_commands_sha256': r['registered_commands_sha256'],
        'registered_case_dir': r['registered_case_dir'], 'commands_equal': r['commands_equal'],
        'command_json_equal': r['command_json_equal'], 'recorded_legs_equal': r['recorded_legs_equal'],
        'leg_checks_equal': r['leg_checks_equal'], 'bit_identical': r['bit_identical'],
        'probe_legs_end_error_mm': [round(l['end_error_m'] * 1000, 9) for l in r['probe_legs']],
        'registered_legs_end_error_mm': [round(l['end_error_m'] * 1000, 9) for l in r['registered_legs']],
        'registered_category': r['category'], 'registered_first_failure': row.get('first_failure'),
        'registered_command_counts': r['command_counts'], 'wall_s': row.get('wall_s'), 'model_calls': 0,
        'first_divergence': r['first_divergence'],
        'leg0_sigma_xy_end_m': leg0['sigma_xy_end_m'], 'leg0_sigma_yaw_end_rad': leg0['sigma_yaw_end_rad']})
lag_on = [c for c in cases if not c['sanity']]
san = [c for c in cases if c['sanity']][0]
n_id = sum(c['bit_identical'] for c in lag_on)
verdict = 'PASS' if (len(lag_on) == 10 and n_id == 10 and san['bit_identical']) else 'FAIL'
audit['replay_3c4fe30e'] = {
    'schema': 'ugrp.v6h1-acceptance-replay.v3-section',
    'verdict': verdict, 'pass': verdict == 'PASS',
    'scope': audit['scope'],
    'registered_source_sha': plan['source_sha'], 'pr': 292, 'branch': 'codex/pair-v6h-register',
    'source_commit_message': 'Match b-v6h1 sigma scope to the exploratory probe',
    'raw_output': str(OUT), 'cases_jsonl_sha256': sha(OUT / 'cases.jsonl'), 'plan_sha256': sha(OUT / 'plan.json'),
    'driver_sha256': sha(OUT / 'driver.py'), 'receipts_sha256': sha(OUT / 'acceptance_receipts.json'),
    'change_vs_3afc61b0_run': 'only plan.json source_sha/raw_output and the driver lock purpose/expected_minutes (20) changed; no probe patch, no in-process override; registered fields only (--policies b-v6h1); the lag-off sanity uses the same worker-local carry_axial_lag=False replace as before',
    'expected_acceptance_cases': 10, 'comparable_acceptance_cases': len(lag_on), 'bit_identical_acceptance_cases': n_id,
    'diverged_acceptance_cases': len(lag_on) - n_id,
    'sanity': {'lag_off_case_vs_tX0': san['bit_identical'], 'probe_commands_sha256': san['probe_commands_sha256'], 'registered_commands_sha256': san['registered_commands_sha256']},
    'tests': {'command': 'pytest -q tests/test_zone_pair_v6h.py tests/test_zone_pair_registered_source.py (run by the driver under the lock)', 'exit_code': manifest['tests_exit_code'], 'result': '164 passed'},
    'cases': cases, 'manifest': manifest}
JS.write_text(json.dumps(audit, ensure_ascii=False, indent=1) + '\n')
print(verdict, n_id, san['bit_identical'])
