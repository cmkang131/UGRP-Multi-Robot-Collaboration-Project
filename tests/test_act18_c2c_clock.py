"""C2c v7 issued-clock deadband and HO4 diag admission (default off)."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import act18_evaluate as e
from harness import grasp_act_contract as c

PROTOCOL = ROOT / 'experiments/2026-10-17-act18/protocol.json'
CONTRACT = ROOT / 'harness/grasp_act_contract.py'
ADAPTER = Path('/home/ubuntu/act-refs/act18-e1-r8-release/act/adapter.json')
# E0 retrieved read-only dataset columns (200 TRAIN episodes / 72,572 rows).
DATASET = Path('/home/ubuntu/UGRP/outputs/runs/act18-clockaudit-20261019T151956Z/dataset-columns.jsonl')
CONTRACT_SHA = '6bc58d6f9707abd5d854c6dbbb63357ed14dab6c37bcf055ddd8d1d66d171056'


def base_pwm(**changes):
    value = {str(s): 1500 for s in c.SERVOS}
    value['1'] = 2000
    value.update({str(k): v for k, v in changes.items()})
    return value


def test_install_clock_zero_keeps_original_and_matches_v6():
    contract = SimpleNamespace(IssuedClock=c.IssuedClock)
    original = e.install_issued_clock(contract, 0)
    assert original is c.IssuedClock
    assert contract.IssuedClock is c.IssuedClock

    e.DeadbandIssuedClock.DEADBAND = 0
    old, new = c.IssuedClock(), e.DeadbandIssuedClock()
    instruction = ('grasp', 'cyan', 'west', 'none')
    sequence = [(0.0, base_pwm()), (0.1, base_pwm()), (0.2, base_pwm(**{'4': 1501})),
                (0.3, base_pwm(**{'4': 1500})), (0.4, base_pwm(**{'4': 1750})),
                (0.5, base_pwm(**{'4': 1750, '5': 1499})),
                (0.6, base_pwm(**{'4': 1750, '5': 1499}))]
    for now, pwm in sequence:
        assert old.observe(instruction, now, pwm) == new.observe(instruction, now, pwm)


def test_deadband_two_resets_only_at_three_pwm():
    e.DeadbandIssuedClock.DEADBAND = 2
    e.CLOCK_STATS.update(instances=0, resets=0, max_pwm_elapsed_s=0.)
    clock = e.DeadbandIssuedClock()
    instruction = ('grasp', 'cyan', 'west', 'none')
    assert clock.observe(instruction, 0.0, base_pwm())['pwm_elapsed_s'] == 0.
    assert clock.observe(instruction, 0.1, base_pwm())['pwm_elapsed_s'] == pytest.approx(.1)
    # +1 and +2 relative to the previously observed issued value do not reset.
    assert clock.observe(instruction, 0.2, base_pwm(**{'4': 1501}))['pwm_elapsed_s'] == pytest.approx(.2)
    assert clock.observe(instruction, 0.3, base_pwm(**{'4': 1503}))['pwm_elapsed_s'] == pytest.approx(.3)
    assert clock.observe(instruction, 0.4, base_pwm(**{'4': 1505}))['pwm_elapsed_s'] == pytest.approx(.4)
    # -2 is still inside the deadband.
    assert clock.observe(instruction, 0.5, base_pwm(**{'4': 1503}))['pwm_elapsed_s'] == pytest.approx(.5)
    # A three-PWM move resets the own-issued clock.
    assert clock.observe(instruction, 0.6, base_pwm(**{'4': 1506}))['pwm_elapsed_s'] == 0.
    assert clock.observe(instruction, 0.7, base_pwm(**{'4': 1506}))['pwm_elapsed_s'] == pytest.approx(.1)
    assert e.CLOCK_STATS['resets'] == 1


def test_observation_clock_changes_only_pwm_elapsed_s():
    e.DeadbandIssuedClock.DEADBAND = 2
    clock = e.DeadbandIssuedClock()
    issued = [{'t': 0., 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': base_pwm()}]
    observation = {'schema': c.SCHEMA, 'robot_id': 'r1', 'sample_id': 'x:0:r1', 't': .4,
                   'skill': 'grasp', 'object_kind': 'cyan', 'role': 'west',
                   'destination_zone': 'none', 'rgb': [], 'issued': issued,
                   'skill_elapsed_s': .4, 'pwm_elapsed_s': .4}
    clock.observe(('grasp', 'cyan', 'west', 'none'), .3, base_pwm())
    updated = e.c2c_observation_clock(observation, clock)
    assert updated['pwm_elapsed_s'] == pytest.approx(.1)
    assert updated['skill_elapsed_s'] == observation['skill_elapsed_s']
    assert updated['issued'] == observation['issued']
    assert observation['pwm_elapsed_s'] == .4


@pytest.mark.skipif(not DATASET.exists(), reason='E0 dataset columns not retrieved on this host')
def test_teacher_dataset_v6_and_v7_clocks_are_identical():
    previous_seed = previous_pwm = None
    changed_v6 = changed_v7 = None
    rows = changed_rows = mismatched_v6 = 0
    with DATASET.open() as handle:
        for line in handle:
            row = json.loads(line)
            now, pwm = float(row['t']), row['issued_pwm']
            if row['seed'] != previous_seed:
                changed_v6 = changed_v7 = now
                previous_pwm = None
                previous_seed = row['seed']
            else:
                step = max(abs(int(pwm[str(s)]) - int(previous_pwm[str(s)])) for s in c.SERVOS)
                if step > 0:
                    changed_v6 = now
                if step >= 3:
                    changed_v7 = now
            v6, v7 = now - changed_v6, now - changed_v7
            if abs(v6 - float(row['pwm_elapsed_s'])) > 1e-6:
                mismatched_v6 += 1
            if abs(v6 - v7) > 1e-6:
                changed_rows += 1
            previous_pwm = pwm
            rows += 1
    assert rows == 72572
    assert mismatched_v6 == 0
    assert changed_rows == 0


def test_contract_file_sha_is_unchanged():
    digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    assert digest == CONTRACT_SHA
    if ADAPTER.exists():
        assert json.loads(ADAPTER.read_text())['contract_sha256'] == digest


def test_diag_holdout_accepts_ho4_and_rejects_locked_overlap(tmp_path):
    protocol = json.loads(PROTOCOL.read_text())
    good = dict(schema=e.DIAG_SCHEMA, holdout=dict(name='HO4', seeds=[88668, 88669, 88670, 88671],
                                                   expected_worlds=4))
    path = tmp_path / 'prereg.json'
    path.write_text(json.dumps(good))
    receipt = e.diag_holdout(path, protocol)
    assert receipt['seeds'] == [88668, 88669, 88670, 88671]
    assert receipt['name'] == 'HO4'
    assert receipt['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert e.allowed_seeds(protocol, 'diag', {}, 'x', receipt) == {88668, 88669, 88670, 88671}
    with pytest.raises(ValueError, match='diag prereg required'):
        e.allowed_seeds(protocol, 'diag', {}, 'x')

    bad = dict(good, holdout=dict(name='HO4', seeds=[88668, 88600]))
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match='overlap locked gate seeds'):
        e.diag_holdout(path, protocol)

    bad = dict(good, schema='unregistered')
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match='schema'):
        e.diag_holdout(path, protocol)
