"""No simulator/GPU/network: the inherited eight-hour deadline cannot stop a batch."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock


def test_batch_finishes_after_eight_hours_without_host_deadline(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'experiments/2026-10-16-warp8/run_batch.py'
    spec = importlib.util.spec_from_file_location('warp8_batch', path)
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    monkeypatch.setattr(batch, 'ROOT', tmp_path)
    monkeypatch.setattr(batch, 'OPS', tmp_path / 'ops')
    # No host-start.json is created: an obsolete session deadline must not be read.
    cases, table, refs = [tmp_path / name for name in ('cases.json', 'table.json', 'refs.json')]
    cases.write_text(json.dumps([{'plan': {'seed': 1}}]))
    table.write_text('{}')
    refs.write_text('{}')
    child = Mock(pid=1234)
    child.poll.side_effect = [None, 0]
    child.wait.return_value = 0
    monkeypatch.setattr(batch.subprocess, 'Popen', Mock(return_value=child))
    monkeypatch.setattr(batch.subprocess, 'check_output', lambda *a, **kw: 'test-sha\n')
    monkeypatch.setattr(batch.subprocess, 'run', lambda *a, **kw: Mock(stdout='1,0'))
    monkeypatch.setattr(batch.time, 'sleep', lambda _: None)
    real_datetime = dt.datetime

    class Clock(real_datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return real_datetime(2026, 10, 16, tzinfo=dt.timezone.utc) + dt.timedelta(days=cls.calls)

    monkeypatch.setattr(batch.dt, 'datetime', Clock)
    monkeypatch.setattr('sys.argv', ['run_batch', '--source-sha', 'test-sha', '--tag', 'release-test',
        '--flow', 'release', '--cases', str(cases), '--indices', '0', '--references', str(refs),
        '--rejection-table', str(table)])
    assert batch.main() == 0
    child.send_signal.assert_not_called()
    receipt = json.loads((tmp_path / 'runs/warp8/release-test.receipt.json').read_text())
    command = json.loads((tmp_path / 'runs/warp8/release-test.command.json').read_text())
    lease = json.loads((tmp_path / 'leases/warp8-release-test.json').read_text())
    assert receipt['exit_code'] == 0
    assert command['supervisor_wall_deadline'] is None
    assert lease['expected_end'] is None
    assert not (tmp_path / 'runs/warp8/release-test.supervisor-stop.json').exists()
    # The original release SIM cap is still passed unchanged to the teacher.
    cap_index = command['command'].index('--cap-s')
    assert command['command'][cap_index + 1] == '180'
