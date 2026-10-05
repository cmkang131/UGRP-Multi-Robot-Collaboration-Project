"""v104 loaded pair rest calibration: static plan, rest windows for the v101 rule, bundle and registration (no physics)."""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import final_pair_loaded_gain_v102 as v102  # noqa: E402
from harness import final_pair_loaded_rest_v104 as env  # noqa: E402


def test_plan_is_registered_generator_output_and_admitted():
    plan = env.protocol()
    assert plan == env.build_plan()
    report = env.validate(plan, for_execution=True)
    assert set(report) == {'restL', 'restF'}
    assert all(v['admitted'] and v['start_pose_check']['admitted'] for v in report.values())
    assert not {r['seed'] for r in plan['runs']} & set(env.RESERVED_SEEDS)
    assert not {r['seed'] for r in plan['runs']} & {r['seed'] for r in v102.RUNS}


def test_config_bytes_equal_canonical_generator_output():
    text = (ROOT / env.CONFIG).read_text()
    assert text == json.dumps(env.build_plan(), ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def test_changed_plan_is_rejected():
    plan = json.loads(json.dumps(env.protocol()))
    plan['runs'][0]['segments'][1]['duration_s'] = 3.
    with pytest.raises(ValueError, match='contract changed'):
        env.validate(plan, for_execution=False)


def test_program_is_one_fit_step_then_explicit_zero_rest():
    for run in env.protocol()['runs']:
        step, rest = run['segments']
        assert (step['phase'], step['role'], step['duration_s'], abs(step['value'])) == ('step', 'fit', 3., .03)
        assert (rest['phase'], rest['value'], rest['duration_s']) == ('coast', 0., 12.)
        moves = [e for e in env.events(run) if e['action']['kind'] == 'mecanum']
        assert all(e['action']['duration_s'] == env.COMMAND_LEASE_S for e in moves)
        zero = [e for e in moves if e['t'] >= env.PREP_END_S + 3. - 1e-9]
        assert zero and all(e['action'][run['axis']] == 0. for e in zero)       # explicit zero commands, no gap


def test_v101_rest_rule_has_windows_at_the_selected_v102_stop_lag():
    # v101 rest_rms: windows start ceil(5 tau_stop / 0.05) samples after the step end and last 1 s (20 samples).
    tau_stop, dt = .10035335696344526, .05
    for run in env.protocol()['runs']:
        b_step = round(3. / dt)
        b = round(15. / dt)
        j0 = b_step + math.ceil(5 * tau_stop / dt)
        assert b - round(1. / dt) - j0 + 1 >= 200


def test_bundle_identity_and_workflow_registration():
    b = env.bundle('restL')
    assert b['execution_bundle_id'] == 'zone-final-pair-loaded-restcal-v104' and b['runnable']
    assert b['controller_inputs'] == [] and b['seed'] == 1301
    assert 'harness/final_pair_loaded_rest_v104.py' in b['source_sha256']
    wf = json.loads((ROOT / env.WORKFLOW).read_text())['workflows'][0]
    assert wf['id'] == env.WORKFLOW_ID and wf['runner'] == 'scripts.run_final_pair_loaded_rest_v104'


def test_v102_contract_is_untouched():
    assert v102.BUNDLE_ID == 'zone-final-pair-loaded-gaincal-v102'
    assert v102.protocol() == v102.build_plan()
