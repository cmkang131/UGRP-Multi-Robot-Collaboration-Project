"""E2E-min actuation: ACT owner path vs nav runner ``issue`` (CPU only).

Both paths are decoded by the byte-vendored ``control_tape``; this compares
the per-substep actuator tape for one robot.  The ACT owner port is the frozen
``DutyActPort`` [T 6f057f7e sim/grasp_act_port.py] driven like
[O 0362037 scripts/warp_act_api.py:386-390].
"""
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import e2e_min_actuation as A
from harness import e2e_min_handoff as H

ROOT = Path(__file__).resolve().parents[1]
INITIAL = {1: 1500, 3: 1200, 4: 1800, 5: 1500, 6: 1500}
SERVOS = (1, 3, 4, 5, 6)
SERVO_IDS = [[4, 5], [6], [7], [8], [9]]
WHEEL_IDS = [0, 1, 2, 3]
CLOCK = dict(dt=.00025, steps=400, start_fraction=.325, kinetic_fraction=.3, torque_cap_nm=1.)


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CORE = _module('_test_vendor_core', ROOT / 'scripts/e2ewarp_vendor/warp_act_core.py')
LOOKUP = np.tile(np.arange(500, 2501, dtype=float), (5, 1))  # identity: ctrl == PWM


def _duty_port_class(tmp_path):
    try:
        src = subprocess.check_output(['git', '-C', str(ROOT), 'show', '6f057f7e:sim/grasp_act_port.py'],
                                      text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip('frozen teacher source 6f057f7e not available')
    path = tmp_path / 'grasp_act_port_T.py'
    path.write_text(src)
    return _module('_test_grasp_act_port_T', path).DutyActPort


def _world():
    robot = SimpleNamespace(servo_command_pulses=dict(INITIAL),
                            set_motor_commands=lambda v: None, set_servo_pulses=lambda u: None)
    return SimpleNamespace(data=SimpleNamespace(time=0.), robot=lambda rid: robot)


def _runner_port():
    return SimpleNamespace(_motor_commands=(0.,) * 4, _wheel_deadlines=[None] * 4,
                           _servo_applied={k: float(v) for k, v in INITIAL.items()},
                           _servo_targets={}, _servo_tick_time=0.)


def _step(port, tick, relay):
    """Q/vendored WarpTransport step: snapshot -> control_tape -> write back."""
    row = dict(ctrl=np.zeros(10), wheels=port._motor_commands,
               deadlines=[v or 0. for v in port._wheel_deadlines],
               applied=[port._servo_applied[s] for s in SERVOS],
               target=[port._servo_targets.get(s, port._servo_applied[s]) for s in SERVOS],
               servo_active=[s in port._servo_targets for s in SERVOS],
               now=tick * .1, servo_time=port._servo_tick_time)
    tape, state = CORE.control_tape([row], relay, lookup=LOOKUP, wheel_ids=WHEEL_IDS,
                                    servo_ids=SERVO_IDS, **CLOCK)
    port._servo_applied = dict(zip(SERVOS, state['applied'][0]))
    port._servo_targets = {s: int(state['target'][0, k]) for k, s in enumerate(SERVOS)
                           if state['servo_active'][0, k]}
    port._servo_tick_time = float(state['servo_time'][0])
    port._motor_commands = tuple(state['wheels'][0])
    port._wheel_deadlines = [d if d is not None and d > port._servo_tick_time else None
                             for d in port._wheel_deadlines]
    return tape[:, 0], state['relay']


def _commands():
    pwm = dict(INITIAL)
    out = []
    for tick in range(30):
        if tick == 2:
            pwm[1] = 2000                   # long slew (0.25 s)
        if tick == 3:
            pwm[1] = 1700                   # retarget mid-slew
        if tick in (5, 6, 7):
            pwm[3] = 1200 + 40 * tick       # consecutive small steps
        if tick == 12:
            pwm[6] = 900                    # look servo
        if tick == 20:
            pwm[4], pwm[5] = 1500, 1400     # two servos in one command
        wheels = [.35, -.35, .35, -.35] if tick % 4 == 1 else [0.] * 4
        dur = [.05, .1, .1, .05] if tick % 4 == 1 else [0.] * 4
        out.append(dict(t=tick * .1, wheels=wheels, duration_s=dur,
                        pwm={str(k): v for k, v in pwm.items()}))
    return out


def _owner_tape(tmp_path):
    port = _duty_port_class(tmp_path)(_world(), 'r1', allow_reverse=True, allow_mecanum=True)
    previous, relay, rows = dict(pwm={str(k): v for k, v in INITIAL.items()}), np.zeros((1, 4), int), []
    for tick, cmd in enumerate(_commands()):
        now = tick * .1
        port.apply(dict(kind='wheel_pulse', wheels=cmd['wheels'], duration_s=cmd['duration_s']), now)
        for servo, pulse in cmd['pwm'].items():
            s = int(servo)
            if pulse != previous['pwm'][servo]:
                port.apply(dict(kind='look', pan_pulse=pulse) if s == 6
                           else dict(kind='arm', servo_id=s, pulse=pulse), now)
        previous = cmd
        tape, relay = _step(port, tick, relay)
        rows.append(tape)
    return np.concatenate(rows)


def _runner_tape(monkeypatch, actuation):
    from scripts import e2e_warp_physics as P
    if actuation:
        monkeypatch.setenv(H.ENV, H.MODE)
        monkeypatch.setenv(A.ENV, actuation)
    else:
        monkeypatch.delenv(A.ENV, raising=False)
    port, relay, rows = _runner_port(), np.zeros((1, 4), int), []
    context = dict(ports=dict(r1=port))
    for tick, cmd in enumerate(_commands()):
        P.issue(context, 'r1', cmd)
        tape, relay = _step(port, tick, relay)
        rows.append(tape)
    return np.concatenate(rows)


def test_default_direct_matches_owner_wheels_and_servos_within_half_pwm(tmp_path, monkeypatch):
    owner = _owner_tape(tmp_path)
    direct = _runner_tape(monkeypatch, None)
    assert np.array_equal(owner[:, WHEEL_IDS], direct[:, WHEEL_IDS])  # wheel pulses identical
    diff = np.abs(owner[:, 4:] - direct[:, 4:])
    assert diff.max() <= 1.0 + 1e-6   # nearest-even rounding of a 0.5 PWM lead
    # direct slews exactly one 0.25 ms substep ahead of the owner (target set
    # before, not after, the first-substep advance); only slewing substeps differ.
    lead = np.all(direct[:-1, 4:] == owner[1:, 4:], axis=1)
    assert lead.mean() > .999
    assert np.array_equal(owner[-400:], direct[-400:])  # same settled state


def test_duty_port_v1_reproduces_owner_tape_exactly(tmp_path, monkeypatch):
    owner = _owner_tape(tmp_path)
    duty = _runner_tape(monkeypatch, 'duty_port_v1')
    assert np.array_equal(owner, duty)


def test_mode_default_off_and_fail_closed():
    assert A.mode({}) == 'direct'
    assert A.mode({A.ENV: 'direct'}) == 'direct'
    with pytest.raises(ValueError, match='requires'):
        A.mode({A.ENV: 'duty_port_v1'})
    assert A.mode({A.ENV: 'duty_port_v1', H.ENV: H.MODE}) == 'duty_port_v1'
    with pytest.raises(ValueError, match='must be unset'):
        A.mode({A.ENV: 'other', H.ENV: H.MODE})


def test_backwards_clock_rejected():
    port = _runner_port()
    port._servo_tick_time = 1.0
    with pytest.raises(ValueError, match='backwards'):
        A.duty_port_servos(port, {'1': 900, '3': 1200, '4': 1800, '5': 1500, '6': 1500}, .5)


# -- queue binding / current-stack admission of the e2e_* keys ------------------
def _config(tmp_path):
    from harness import e2e_min_runner as M
    measure = tmp_path / 'measure.json'
    measure.write_text(json.dumps(dict(verdict=dict(adopted='act_lift_end'))))
    import hashlib
    cfg = dict(level='E2E-1p',
               cubes={'r1': dict(item_id='cyan_1', xy=[-0.05, -2.375]),
                      'r2': dict(item_id='red_1', xy=[-0.05, -2.875])},
               carry_pose_verdict=dict(path=str(measure),
                                       sha256=hashlib.sha256(measure.read_bytes()).hexdigest()),
               act=dict(python='py', act_source='src', expected_act_sha='a' * 40, checkpoint='ck',
                        expected_model_sha256='b' * 64, device='cuda'),
               release=dict(backoff_m=0.03), timeouts=dict(settle=0.2), sim_budget_s=30.0)
    path = tmp_path / 'e2e-config.json'
    path.write_text(json.dumps(cfg))
    return M, {M.CONFIG_ENV: str(path), H.ENV: H.MODE}


def test_actuation_is_queue_bound_and_default_byte_identical(tmp_path):
    M, env = _config(tmp_path)
    record = M.load_config(env)
    default = M.queue_fields(record, env)
    assert 'e2e_actuation' not in default
    duty_env = {**env, A.ENV: 'duty_port_v1'}
    duty = M.queue_fields(record, duty_env)
    assert duty['e2e_actuation'] == 'duty_port_v1'
    M.validate_queue(default, env)
    M.validate_queue(duty, duty_env)
    with pytest.raises(ValueError, match='E2E_ACTUATION_CHANGED'):
        M.validate_queue(default, duty_env)
    with pytest.raises(ValueError, match='E2E_ACTUATION_CHANGED'):
        M.validate_queue(duty, env)


def _stack_queue():
    from scripts import run_e2e_warp as R
    stack, digest = R.stack_config()
    values = {r['id']: r['current'] for r in stack['rules'] if 'e2e_llm' in r['flows']}
    values.update(gcp_host=R.INSTANCE, gcp_project=R.PROJECT, gcp_account=R.ACCOUNT,
                  dialogue_language='no_comm')
    queue = dict(schema='ugrp.e2ewarp.queue.v1', flow='e2e_llm', mode='nav', seed=601,
                 condition='no_comm', stack_sha256=digest, stack_values=values, stack_deviations=[],
                 host=dict(instance=R.INSTANCE, project_id=R.PROJECT, account=R.ACCOUNT),
                 no_pooling=True)
    return stack, queue


def test_current_stack_accepts_e2e_queue_keys_unchanged(tmp_path):
    from scripts.check_current_stack import check_document
    M, env = _config(tmp_path)
    stack, queue = _stack_queue()
    before = check_document(queue, stack)
    for extra in (M.queue_fields(M.load_config(env), env),
                  M.queue_fields(M.load_config(env), {**env, A.ENV: 'duty_port_v1'})):
        after = check_document({**queue, **extra}, stack)
        assert [(r['id'], r['status'], r['observed']) for r in after] == \
               [(r['id'], r['status'], r['observed']) for r in before]


def test_no_current_stack_selector_reaches_e2e_keys():
    from scripts import run_e2e_warp as R
    from scripts.check_current_stack import CONTAINERS
    stack, _ = R.stack_config()
    heads = {p.split('.')[0] for r in stack['rules']
             for k in ('paths', 'derived_kind_paths') for p in r['verification'].get(k, [])}
    assert not [h for h in heads if h.startswith('e2e')]
    assert not [c for c in CONTAINERS if c.startswith('e2e')]
