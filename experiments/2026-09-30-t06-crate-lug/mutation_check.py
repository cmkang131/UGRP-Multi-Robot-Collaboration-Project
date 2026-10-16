"""Run focused pytest against in-memory mutants; never edit working sources.

Usage: <existing-python> experiments/2026-09-30-t06-crate-lug/mutation_check.py \
    --output /absolute/primary/outputs/t06-crate-lug/NEW-DIRECTORY
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'harness/zone_crate_skill.py'
TEST = 'tests/test_zone_own_executor_crate.py'
MUTANTS = {
    'own_ready_without_partner': (
        "return result['phase'] == 'GO'", 'return ready',
        'test_one_side_not_ready_or_wrong_lug_never_closes'),
    'omit_grasp_gate': (
        "fresh and lug and ev.grasped == 'yes'", 'True',
        'test_missing_one_side_grasp_or_holding_blocks_next_phase'),
    'omit_holding_gate': (
        "fresh and lug and ev.holding == 'yes'", 'True',
        'test_missing_one_side_grasp_or_holding_blocks_next_phase'),
    'ignore_holding_loss': (
        "if not lug or ev.holding != 'yes':", 'if False:',
        'test_holding_loss_stops_carry_and_peer_before_any_further_motion'),
    'ignore_peer_holding': (
        "if not self._peer_holding(now):", 'if False:',
        'test_fresh_peer_status_without_holding_stops_carry'),
    'ignore_peer_missed_go': (
        "if self.status.grant and now > self.status.grant[1] + EPS:", 'if False:',
        'test_one_peer_misses_go_stops_before_next_barrier'),
    'ignore_heartbeat_loss': (
        "if not peer['alive'] and (self.peer_seen or peer['age_s'] is not None):", 'if False:',
        'test_heartbeat_break_at_every_phase_terminates'),
    'grasp_crate_body': (
        "'part': 'lug_' + role", "'part': 'box'",
        'test_lug_contract_matches_static_catalogue_without_copying_beam'),
    'claim_physical_support': (
        "'native_adapter': False, 'physical_supported': False", "'native_adapter': False, 'physical_supported': True",
        'test_complete_decision_sequence_has_simultaneous_lift_but_no_physical_success'),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--child', choices=MUTANTS)
    args = parser.parse_args()
    original = SOURCE.read_text()
    if args.child:
        before, after, test = MUTANTS[args.child]
        assert original.count(before) == 1, 'mutation anchor must be unique'
        sys.path.insert(0, str(ROOT))
        for name in ('mujoco', 'torch', 'torchvision', 'google.genai', 'openai', 'anthropic'):
            sys.modules[name] = None
        def forbidden(*args, **kwargs):
            raise AssertionError('T06 mutation check: physics/provider/network forbidden')
        socket.socket.connect = socket.socket.connect_ex = forbidden
        import harness
        module = types.ModuleType('harness.zone_crate_skill')
        module.__file__ = str(SOURCE)
        sys.modules[module.__name__] = module
        harness.zone_crate_skill = module
        exec(compile(original.replace(before, after), str(SOURCE), 'exec'), module.__dict__)
        import pytest
        return pytest.main(['-q', TEST + '::' + test, '--tb=short',
                            '--junitxml=' + str(args.output / (args.child + '.xml'))])
    args.output.mkdir(parents=True, exist_ok=False)
    result = {'scope': 'offline mutations only; no physical or vision success',
              'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'mutants': []}
    for name, (before, after, test) in MUTANTS.items():
        command = [sys.executable, str(Path(__file__).resolve()), '--child', name, '--output', str(args.output)]
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        log = args.output / (name + '.log')
        log.write_text(proc.stdout + proc.stderr)
        xml = args.output / (name + '.xml')
        suites = ET.parse(xml).getroot().findall('testsuite') if xml.exists() else []
        failures = sum(int(s.get('failures', '0')) for s in suites)
        errors = sum(int(s.get('errors', '0')) for s in suites)
        skipped = sum(int(s.get('skipped', '0')) for s in suites)
        result['mutants'].append({'name': name, 'removed_or_changed': before, 'replacement': after,
                                  'test': TEST + '::' + test, 'exit_code': proc.returncode,
                                  'assertion_failures': failures, 'collection_errors': errors,
                                  'skipped': skipped,
                                  'killed': proc.returncode == 1 and failures > 0 and errors == skipped == 0,
                                  'log': str(log), 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
    result['source_unchanged'] = hashlib.sha256(SOURCE.read_bytes()).hexdigest() == result['source_sha256']
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['source_unchanged'] and all(r['killed'] for r in result['mutants']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
