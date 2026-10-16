"""v98 host clock v2 (sim.final_pair_highpose_clock): integer substep SIM time (2026-10-05 coordinator decision).

The drift model is MuJoCo's ``data.time += timestep`` (timestep 0.00025 s, 200 substeps per 0.05 s host tick); it
reproduces the recorded times of the v98 probe align_to_carry 14ba8b5e byte for byte (496.7499999899814 etc.).
No physics is run here: the fake world advances its clock exactly as mj_step does.
"""
import inspect
import math

import pytest

from sim import final_pair_highpose_clock as clock
from sim.final_pair_v3 import PhysicsBackend as V3Backend

DT = .00025
TICK = .05
SUB = 200
RESET_TICKS = 26                    # reset settle 1.3 s (applied.json reset_sim_s 1.3000000000000178)
CAP_TICKS = RESET_TICKS + 18000     # + 900 s case cap


def running_sum(ticks):
    """data.time at each host tick under float accumulation (index = tick k, k*0.05 s)."""
    t, out = 0., [0.]
    for _ in range(ticks):
        for _ in range(SUB):
            t += DT
        out.append(t)
    return out


RAW = running_sum(CAP_TICKS + 2)


class FakeData:
    def __init__(self, t): self.time = t


class FakeWorld:
    def __init__(self, t): self.data = FakeData(t)
    def robot(self, rid): return rid
    def _physics_step_for(self, robot): self.data.time += DT     # what mj_step does to the clock


class Port:
    def __init__(self): self.seen = []
    def tick(self, now): self.seen.append(now)


def host(cls, t, *, deadline=2000.):
    b = object.__new__(cls)
    b.bundle, b.dt, b.deadline, b.ports, b.world = {'check': 'carry'}, DT, deadline, {}, FakeWorld(t)
    return b


def test_drift_model_reproduces_the_recorded_14ba8b5e_times():
    assert RAW[26] == 1.3000000000000178                                  # reset_sim_s in applied.json
    assert RAW[9935] == 496.7499999899814 and RAW[9941] == 497.0499999899743   # close_ready_6 / r1 late poll
    drift = [round(k*TICK, 9) - RAW[k] for k in range(len(RAW))]
    first_pos = next(k for k, d in enumerate(drift) if d > 1e-8)
    first_neg = next(k for k, d in enumerate(drift) if d < -1e-8)
    assert round(first_pos*TICK, 9) == 496.0 and round(first_neg*TICK, 9) == 612.05


def test_old_host_advance_stops_one_substep_short_at_612_05():
    k0 = 12200
    old = host(V3Backend, RAW[k0])
    with pytest.raises(RuntimeError, match='inexact SIM advance'):
        for k in range(k0+1, k0+60):
            old.advance_to(RAW[26] + (k-26)*TICK)      # the runner's start + (i+1)*TICK_S
    assert old.now == pytest.approx(612.05 - DT, abs=1e-7)               # one substep short of the 612.05 tick


def test_new_host_is_exactly_on_the_grid_to_the_900_s_cap_and_never_raises():
    new = host(clock.PhysicsBackend, RAW[RESET_TICKS])
    new._clock_snap()                                                     # what reset() does after the settle
    port = Port()
    new.ports = {'r1': port}
    assert new.now == 1.3 and new._substeps == RESET_TICKS*SUB
    start = new.now
    for k in range(RESET_TICKS+1, CAP_TICKS+1):
        new.advance_to(start + (k-RESET_TICKS)*TICK)
        assert new.now == round(k*TICK, 9) and new._substeps == k*SUB
    assert new.now == 901.3
    # every substep the ports saw is the decimal grid value too (no running sum anywhere)
    assert all(t == round((RESET_TICKS*SUB+i)*DT, 9) for i, t in enumerate(port.seen))
    assert len(port.seen) == 18000*SUB


def test_reset_snaps_to_the_grid_and_remakes_ports_at_the_grid_time(monkeypatch):
    from sim.camera_robot_port import CameraRobotPort

    class Robot:
        servo_command_pulses = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
        def set_servo_pulses(self, updates): pass
        def set_motor_commands(self, values): pass

    world = FakeWorld(0.)
    world.robot = lambda rid: Robot()

    def parent_reset(self, cap):                       # the settle leaves the raw running sum; ports made at it
        self.world.data.time = RAW[RESET_TICKS]
        self.ports = {r: CameraRobotPort(self.world, r, allow_reverse=True, allow_mecanum=True) for r in ('r1', 'r2')}
        return self.world.data.time

    monkeypatch.setattr(V3Backend, 'reset', parent_reset)
    b = host(clock.PhysicsBackend, 0.)
    b.world = world
    assert b.reset(5.) == 1.3 and b.now == 1.3 and b._substeps == RESET_TICKS*SUB
    for rid, port in b.ports.items():
        assert port._servo_tick_time == 1.3 and port._servo_pulses == Robot.servo_command_pulses
        port.hold(b.now)                                # was: ValueError sim_time must not move backwards
    b.deadline = 2.
    b.advance_to(1.35)
    assert b.now == 1.35


def test_new_host_keeps_the_parent_guards():
    new = host(clock.PhysicsBackend, 1.3, deadline=2.)
    with pytest.raises(RuntimeError, match='before reset'):
        new.advance_to(1.35)
    new._clock_snap()
    with pytest.raises(ValueError, match='outside SIM deadline'):
        new.advance_to(2.05)
    with pytest.raises(ValueError, match='outside SIM deadline'):
        new.advance_to(1.2)
    with pytest.raises(RuntimeError, match='inexact SIM advance'):
        new.advance_to(1.3 + DT/2)
    new.advance_to(1.3 + 3*DT)                                            # substep grid, not only ticks
    assert new.now == 1.30075 and new._substeps == 5203
    bad = host(clock.PhysicsBackend, 1.3 + DT/3)
    with pytest.raises(RuntimeError, match='not on the substep grid'):
        bad._clock_snap()
    assert "startswith('calibration-')" in inspect.getsource(clock.IntegerClock.advance_to)   # parent's collection path


def test_staged_and_case_backends_use_the_clock_and_the_runner_records_it():
    from sim.final_pair_highpose_staged import StagedBackend
    assert StagedBackend.__mro__[2] is clock.IntegerClock and clock.PhysicsBackend.__mro__[2] is clock.IntegerClock  # [1] = NearClip (render near-clip)
    assert StagedBackend.host_clock == clock.PhysicsBackend.host_clock == clock.ID
    from scripts import run_pair_highpose as run
    src = inspect.getsource(run)
    assert 'from sim.final_pair_highpose_clock import PhysicsBackend' in src
    assert "result['host_clock']" in src
    r = clock.record()
    assert r['id'] == clock.ID and 'never pooled' in r['pooling']


# --- the close barrier of 14ba8b5e, with the frozen executor grid rule and the frozen status barrier ----------------
EXECUTOR_RULES = ('control_due = now + EPS >= self.next_control',
                  'self.next_control = round((math.floor((now + EPS) / CONTROL_S) + 1) * CONTROL_S, 9)')


def close_barrier(times, descent_until):
    """Both robots poll at ``times``; wait_close starts at the first control tick after the blind descent ends."""
    from harness.zone_pair_status import CONTROL_S, EPS, PairStatusChannel, PairStatusEndpoint
    bus = PairStatusChannel('t')
    eps = {r: PairStatusEndpoint(bus, r) for r in ('r1', 'r2')}
    bars = {r: e.sync_for('close@6') for r, e in eps.items()}
    nxt = {r: times[0] for r in eps}
    reported, out = {}, []
    for now in times:
        for rid, e in eps.items():
            e.tick(e.latched or 'aligning', now)                           # heartbeat
            if not now + EPS >= nxt[rid]:                                  # EXECUTOR_RULES[0]
                continue
            nxt[rid] = round((math.floor((now + EPS) / CONTROL_S) + 1) * CONTROL_S, 9)   # EXECUTOR_RULES[1]
            if now < descent_until:
                continue
            if rid not in reported:
                assert bars[rid].report(rid, ready=True, observed_at_s=now, received_at_s=now,
                                        frame_id=f'{rid}-1-0123456789ab')
                reported[rid] = now
                continue
            verdict = bars[rid].authorize(now)
            out.append((rid, now, verdict['phase'], bars[rid].go_at))
            if verdict['phase'] != 'WAIT':
                return reported, out
    return reported, out


def test_frozen_executor_rules_are_the_ones_replayed():
    from harness import zone_pair_executor
    src = inspect.getsource(zone_pair_executor)
    assert all(rule in src for rule in EXECUTOR_RULES)


def test_old_clock_reproduces_the_recorded_late_go_and_new_clock_takes_go_on_time():
    ks = range(9900, 9960)
    reported, out = close_barrier([RAW[k] for k in ks], 496.74)
    assert reported == {'r1': 496.7499999899814, 'r2': 496.7499999899814}           # recorded close_ready_6
    assert out[-1] == ('r1', 497.0499999899743, 'ABORT', 497.0)                        # recorded LATE_OR_EXPIRED_GO
    reported, out = close_barrier([round(k*TICK, 9) for k in ks], 496.74)
    assert reported == {'r1': 496.8, 'r2': 496.8}                                      # control grid kept
    assert out[-1] == ('r1', 497.0, 'GO', 497.0)                                       # GO polled exactly on time
    assert all(round(now*10, 9) == round(now*10) for _, now, _, _ in out)            # every poll on the 0.1 s grid
