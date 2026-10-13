"""Speed admission and runtime warnings, with short fake children; no physics."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import azure_speed_gate as gate


def sample(wall=90., **changes):
    return dict(sim_s=30., wall_s=wall, expected_stop=True, finalization_errors=[], finalization_complete=True, exit=1, **changes)


def test_full_planned_concurrency_required_and_median_includes_every_member():
    assert gate.verdict([sample(30), sample(120), sample(150)], 3, 4)['admitted']
    assert gate.verdict([sample(120.1), sample(150)], 2, 4)['status'] == 'SPEED_GATE_FAIL'
    assert not gate.verdict([sample(30)], 6, 4)['admitted']
    assert not gate.verdict([], 0, 4)['admitted']


@pytest.mark.parametrize('changes', [dict(sim_s=29.9), dict(wall_s=float('nan')),
    dict(wall_s=float('inf')), dict(sim_s=float('inf')), dict(expected_stop=False),
    dict(finalization_errors=['disk_full']), dict(finalization_complete=False),
    dict(finalization_complete=None), dict(exit=-9), dict(sim_s=0)])
def test_partial_failed_or_nonfinite_member_never_passes(changes):
    row = sample(); row.update(changes)
    assert not gate.verdict([sample(10), row], 2, 4)['admitted']


def test_override_is_explicit_nonempty_and_records_failed_measurement():
    for reason in ('', '  '):
        with pytest.raises(Exception, match='nonempty'):
            gate.verdict([], 6, 4, reason)
    result = gate.verdict([], 6, 4, 'coordinator speed diagnosis')
    assert result['admitted'] and not result['measured_pass']
    assert result['override_reason'] == 'coordinator speed diagnosis'
    assert result['status'] == 'SPEED_GATE_OVERRIDE'


def test_probe_reuses_configuration_and_replaces_only_measurement_output_options(tmp_path):
    command = ['python', '-m', 'scripts.sim_cli', 'workflow', 'run', 'v214', '--',
               '--speed3', 'dt1_v1', '--seed', '61001', '--output', '/old/raw', '--execute',
               '--measure-sim-s', '60', '--rbpf-audit-hash', 'final_v1']
    result = gate.probe_command(command, tmp_path)
    assert result[:result.index('--output')] == command[:command.index('--output')]
    assert result.count('--measure-sim-s') == result.count('--rbpf-audit-hash') == 1
    assert result[result.index('--measure-sim-s') + 1] == '30.0'
    assert result[result.index('--rbpf-audit-hash') + 1] == 'none'
    assert result[result.index('--output') + 1] == str(tmp_path / 'raw')
    assert command[command.index('--output') + 1] == '/old/raw'


def test_runtime_warning_requires_ten_continuous_minutes_and_recovers():
    warning = gate.SpeedWarning(4)
    assert warning.observe(0, 0) is None
    for t in range(30, 600, 30):
        assert warning.observe(t, t / 7) is None
    row = warning.observe(600, 600 / 7)
    assert row['continuous_slow_s'] == 600 and row['limit_wall_per_sim'] == 6
    assert warning.observe(630, 600 / 7 + 30) is None  # healthy interval resets
    assert warning.slow_since is None
    for t in range(660, 1230, 30):
        assert warning.observe(t, 600 / 7 + 30) is None
    assert warning.observe(1230, 600 / 7 + 30)['stalled']


def test_azure_execution_guard_rejects_mac(monkeypatch, tmp_path):
    monkeypatch.setattr(gate.platform, 'system', lambda: 'Darwin')
    with pytest.raises(ValueError, match='AZURE_ONLY'):
        gate.preflight([], tmp_path)


FAKE = '''import argparse,json,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output');a,_=p.parse_known_args()
r=Path(a.output);r.mkdir(parents=True)
(r/'started').write_text(str(time.monotonic()))
time.sleep(.15)
(r/'result.json').write_text(json.dumps(dict(failure='MEASUREMENT_SIM_LIMIT',finalization_errors=[],finalization_complete=True)))
(r.parent/'measurement.json').write_text(json.dumps(dict(sim_s=30.,wall_s=60.,expected_stop=True)))
raise SystemExit(1)
'''


def specs(tmp_path, count=3, command=None):
    result = []
    for i in range(count):
        target = tmp_path / f'cohort-{i}'; target.mkdir()
        (target / 'RUN_META.json').write_text(json.dumps(dict(pr=448, sha='abc', **{'class': 'dev'})))
        result.append(dict(name=target.name, target=str(target),
                           command=command or [sys.executable, '-c', FAKE]))
    return result


def test_real_processes_are_simultaneous_and_expected_nonzero_exit_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, 'require_azure', lambda _: None)
    planned = specs(tmp_path)
    root = tmp_path / 'gate'
    result = gate.preflight(planned, root)
    assert result['completed'] == 3 and result['median_wall_per_sim'] == 2
    starts = [float(p.read_text()) for p in root.glob('*/raw/started')]
    assert max(starts) - min(starts) < .15
    assert all(not (Path(s['target']) / 'raw').exists() for s in planned)


def test_incomplete_child_is_preserved_and_refuses_cohort(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, 'require_azure', lambda _: None)
    planned = specs(tmp_path, 1, [sys.executable, '-c', 'raise SystemExit(2)'])
    root = tmp_path / 'gate'
    result = gate.preflight(planned, root)
    assert not result['admitted']
    assert json.loads((root / 'SPEED_GATE_FAIL.json').read_text())['completed'] == 0
    assert (root / 'speed-gate-cohort-0/EXIT').read_text().strip() == '2'


def test_start_cli_does_not_launch_after_gate_failure(monkeypatch, tmp_path):
    plan = tmp_path / 'plan.json'; plan.write_text('[]')
    monkeypatch.setattr(gate, 'preflight', lambda *a: dict(admitted=False, status='SPEED_GATE_FAIL'))
    monkeypatch.setattr(gate.subprocess, 'Popen', lambda *a, **k: pytest.fail('cohort launched'))
    assert gate.main(['start', '--plan', str(plan), '--gate-root', str(tmp_path/'gate')]) == 1


def test_all_shell_launchers_gate_start_and_preserve_six_cell_plan():
    for name in ('e2e-idle', 'e2e-usstall', 'e2e-vomask-registration'):
        path = Path('experiments') / ('2026-10-12-' + name) / 'azure-pair.sh'
        text = path.read_text()
        assert 'scripts.azure_speed_gate add' in text and 'scripts.azure_speed_gate start' in text
        assert 'setsid nohup' not in text
        subprocess.run(['bash', '-n', str(path)], check=True)
    rows = subprocess.check_output(['bash', 'experiments/2026-10-12-e2e-idle/azure-pair.sh',
        'sha', '453', '--plan', 'pair'], text=True).splitlines()
    assert len(rows) == 6


def test_zero_supervisor_exit_does_not_hide_incomplete_finalization(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, 'require_azure', lambda _: None)
    fake = FAKE.replace('finalization_complete=True', 'finalization_complete=False').replace('SystemExit(1)', 'SystemExit(0)')
    planned = specs(tmp_path, 1, [sys.executable, '-c', fake])
    result = gate.preflight(planned, tmp_path / 'gate')
    assert not result['admitted'] and result['completed'] == 0
    assert result['samples'][0]['exit'] == 0
    assert result['samples'][0]['expected_stop'] and not result['samples'][0]['finalization_complete']


R52 = Path(__file__).resolve().parents[1] / 'experiments/2026-10-12-e2e18/r52-wall-sim-phase.tsv'


def r52_rows():
    return [(float(a), float(b), c) for a, b, c in (l.split() for l in R52.read_text().splitlines()[1:])]


def replay_r52(make, offset, poll=2.):
    """Feed e2e-progress as the 2 s watch loop would see it (integer SIM seconds)."""
    import bisect
    rows = r52_rows()
    walls = [r[0] for r in rows]
    t, fired = offset, None
    while t < walls[-1] and fired is None:
        i = bisect.bisect_right(walls, t) - 1
        sim, phase = (rows[i][1], rows[i][2]) if i >= 0 else (0., None)
        fired = make(t, sim, phase)
        t += poll
    return fired


def test_r52_regression_old_rule_missed_warning_rolling_rule_fires_at_every_offset():
    # 4.7-5.6 wall/SIM for >1400 s against limit 3.0*1.5=4.5; old rule never fired for 15 of 30 offsets.
    def old(offset):
        w = gate.SpeedWarning(3.0)
        return replay_r52(lambda t, sim, phase: w.observe(t, sim), offset)
    assert [old(o) for o in (15, 18, 21, 24, 27)] == [None] * 5
    for offset in range(0, 30, 3):
        w = gate.RollingSpeedWarning(3.0)
        fired = replay_r52(lambda t, sim, phase: w.observe(t, sim), offset)
        assert fired and fired['rule'] == 'rolling_window_v1' and fired['wall_per_sim'] > 4.5
        assert fired['sim_s'] < 910  # before the run reached SIM 910 (wall ~3600 s)


def test_rolling_rule_ignores_a_fast_burst_and_recovers_and_flags_stall():
    w = gate.RollingSpeedWarning(4)  # limit 6
    assert w.observe(0, 0) is None
    for t in range(30, 600, 30):
        assert w.observe(t, t / 7) is None
    assert w.observe(600, 600 / 7)['wall_per_sim'] == pytest.approx(7)
    assert w.observe(630, 600 / 7 + 30) is None  # the window now averages below the limit
    w = gate.RollingSpeedWarning(4)
    w.observe(0, 5)
    assert w.observe(600, 5)['stalled']


def test_phase_warning_uses_progress_phase_and_never_stops_the_run():
    ph = gate.PhaseSpeedWarning(3.0, limits={'align': 3.5})
    changed = [ph.observe(t, sim, p) for t, sim, p in
               ((w, s, p) for w, s, p in r52_rows())]
    kinds = [(e['kind'], e['phase']) for e in ph.events]
    assert ('phase_running', 'relook') in kinds and ('phase_end', 'grasp_lift') in kinds
    assert not any(e['phase'] in ('mapping',) for e in ph.events)  # 2.25 < 4.5
    relook = [e for e in ph.events if e['phase'] == 'relook'][0]
    assert relook['wall_per_sim'] > 4.5 and relook['limit_wall_per_sim'] == 4.5
    assert ph.snapshot(1e9, 1e9)['limits'] == {'align': 3.5} and any(changed)
    assert [s['phase'] for s in ph.segments][:3] == ['mapping', 'align', 'grasp_lift']
