"""sim.walltime_monitor: opt-in wall-time sidecar must be measurement-only (no physics run here).

The real-run byte-identity check (monitored vs unmonitored v98 align_to_carry prefix) is recorded in
experiments/2026-10-05-sim-walltime-monitor/README.md; these tests pin the wrapper semantics it relies on.
"""
import json

import pytest

from sim import walltime_monitor as wm


class Base:
    def __init__(self):
        self.t = 0.
        self.log = []

    @property
    def now(self):
        return self.t

    def advance_to(self, t):
        self.log.append(('advance', t))
        self.t = t

    def capture(self, rid):
        self.log.append(('capture', rid))
        return {'rid': rid, 'pixels': [1, 2, 3]}

    def boom(self):
        raise KeyError('kept')


class Child(Base):
    def advance_to(self, t):          # calls super(): timed once (outermost)
        self.log.append(('child', t))
        return super().advance_to(t)


def test_wrap_keeps_args_return_exceptions_and_order(tmp_path):
    mon = wm.WalltimeMonitor(tmp_path / wm.SIDECAR, window_sim_s=1.)
    orig = {n: vars(Base)[n] for n in ('advance_to', 'capture', 'boom')}
    mon.wrap_family([Child], 'advance_to', 'physics')
    mon.wrap(Base, 'capture', 'capture')
    mon.wrap(Base, 'boom', 'boom')
    b = Child()
    assert b.capture('r1') == {'rid': 'r1', 'pixels': [1, 2, 3]}
    with pytest.raises(KeyError, match='kept'):
        b.boom()
    b.advance_to(.5)
    assert b.log == [('capture', 'r1'), ('child', .5), ('advance', .5)]
    assert mon.calls['physics'] == 1          # reentrant super() call not double counted
    assert mon.calls['boom'] == 1 and mon.calls['capture'] == 1
    mon.close()
    assert {n: vars(Base)[n] for n in orig} == orig
    assert 'advance_to' in vars(Child) and getattr(vars(Child)['advance_to'], '__wrapped__', None) is None


def test_windows_go_to_the_sidecar_only(tmp_path):
    run = tmp_path / 'run'
    case = run / 'case'
    case.mkdir(parents=True)
    (case / 'result.json').write_text('{}')
    before = sorted(p.relative_to(run) for p in run.rglob('*'))
    mon = wm.WalltimeMonitor(run / wm.SIDECAR, window_sim_s=1.)
    mon.wrap_family([Child], 'capture', 'capture')
    mon.wrap_family([Child], 'advance_to', 'physics')
    mon.attach_marks([Child, Base])
    b = Child()
    for i in range(1, 26):
        b.capture('r1')
        b.advance_to(i * .1)
    mon.close()
    rows = [json.loads(line) for line in (run / wm.SIDECAR).read_text().splitlines()]
    assert [r['sim_t1'] for r in rows] == [1.0, 2.0, 2.5]      # two full windows + the flushed partial one
    assert all(r['schema'] == wm.SCHEMA and r['phases']['physics']['calls_per_sim_s'] > 0 for r in rows)
    assert all({'loadavg', 'memory', 'process', 'cpu_util_pct', 'other_wall_per_sim_s'} <= set(r) for r in rows)
    # Nothing new inside the case directory; the only new file is the run-root sidecar.
    after = sorted(p.relative_to(run) for p in run.rglob('*'))
    assert set(after) - set(before) == {wm.Path(wm.SIDECAR)}
    s = wm.summarize(run / wm.SIDECAR)
    assert s['rows'] == 3 and s['sim_s'] == pytest.approx(2.5)
    assert vars(Child)['advance_to'].__name__ == 'advance_to' and not hasattr(vars(Child)['advance_to'], '__wrapped__')


def test_install_v98_patches_and_restores_everything(tmp_path):
    import mujoco
    from scripts import run_pair_highpose as runner
    from sim import camera_robot_port, final_environment_checks, final_pair_v3
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
    owners = [mujoco, runner, camera_robot_port.CameraRobotPort, final_environment_checks.PhysicsBackend,
              final_pair_v3.PhysicsBackend, MultiMasterPiProductionV2]
    snapshot = [dict(vars(o)) for o in owners]
    mon = wm.WalltimeMonitor(tmp_path / wm.SIDECAR).install_v98(runner)
    assert mujoco.mj_step is not snapshot[0]['mj_step']
    assert final_pair_v3.PhysicsBackend.capture.__wrapped__ is snapshot[4]['capture']
    mon.close()
    for o, before in zip(owners, snapshot):
        assert {k: v for k, v in vars(o).items() if k in before} == before
    assert not (tmp_path / wm.SIDECAR).exists()        # nothing ran, nothing written


def test_window_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        wm.WalltimeMonitor(tmp_path / 'x.jsonl', window_sim_s=0)
