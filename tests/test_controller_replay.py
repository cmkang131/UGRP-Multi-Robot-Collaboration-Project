import pytest
from scripts.profile_controller_replay import Timers


def test_nested_timers_are_a_partition_including_exception():
    times = iter([0., 1., 3., 5.])
    timers = Timers(clock=lambda: next(times))
    with pytest.raises(ValueError), timers.span('outer'):
        with timers.span('inner'):
            raise ValueError('stop')
    assert timers.total['outer'] == dict(calls=1, exclusive_s=3., inclusive_s=5.)
    assert timers.total['inner'] == dict(calls=1, exclusive_s=2., inclusive_s=2.)
    assert timers.stack == []


def test_managed_catalog_plans_without_execution(tmp_path):
    from pathlib import Path
    from sim.workflow_manager import plan
    root = Path(__file__).resolve().parents[1]
    result = plan(root, 'controller-replay-profile', ['--kind', 'egomap', '--raw', str(tmp_path),
        '--adapter', str(tmp_path), '--output', str(tmp_path / 'new'), '--expected-source-sha', 'a' * 40])
    assert result['execution_started'] is False
    assert not (tmp_path / 'new').exists()
