import pytest
import io
import urllib.error
from unittest.mock import patch

from scripts.azure_api import Arm
from scripts.azure_idle_guard import reason
from scripts.remote_run_finish import collect


def cost_client(columns, rows, next_link=None):
    client = object.__new__(Arm)
    client.request = lambda *args, **kwargs: {'properties': {
        'columns': [{'name': name} for name in columns], 'rows': rows, 'nextLink': next_link}}
    return client


def test_cost_uses_usd_column_not_billing_currency():
    client = cost_client(['Cost', 'Currency', 'CostUSD'], [[136475, 'KRW', 100], [68237.5, 'KRW', 50]])
    assert client.cost_usd('subscription') == 150


@pytest.mark.parametrize('columns,next_link', [(['Cost'], None), (['CostUSD'], 'more')])
def test_incomplete_cost_cannot_admit_paid_compute(columns, next_link):
    with pytest.raises(RuntimeError, match='Incomplete'):
        cost_client(columns, [[0]], next_link).cost_usd('subscription')


def test_guard_boundaries_and_hard_cap_even_when_recently_busy():
    assert reason(28799, 1199) is None
    assert reason(100, 1200) == 'twenty_minutes_idle'
    assert reason(28800, 0) == 'eight_hour_cap'


def test_cost_rate_limit_waits_for_longest_header_before_retry():
    client = object.__new__(Arm)
    client._token = 'fixture'
    failure = urllib.error.HTTPError('https://management.azure.com/query', 429, 'throttled',
        {'retry-after': '2', 'x-ms-ratelimit-microsoft.costmanagement-entity-retry-after': '58'}, io.BytesIO(b''))
    response = io.BytesIO(b'{"ok": true}')
    response.headers = {}
    with patch('urllib.request.urlopen', side_effect=[failure, response]) as send, patch('time.sleep') as wait:
        assert client.request('POST', '/query', {}) == {'ok': True}
        wait.assert_called_once_with(58)
        assert send.call_count == 2


def test_finished_run_preserves_only_its_standard_records_once(tmp_path):
    source, run = tmp_path/'source', tmp_path/'run'
    record = source/'outputs/simulation-runs/own'
    other = source/'outputs/simulation-runs/other'
    record.mkdir(parents=True); other.mkdir(); run.mkdir()
    (record/'manifest.json').write_bytes(b'{"status":"FAILED"}')
    (record/'source.json').write_bytes(b'original source bytes')
    (other/'manifest.json').write_bytes(b'other task')
    line = f'Simulation record: {record}/manifest.json\n'
    (run/'log.txt').write_text(line+line)
    assert collect(source, run) == ['own']
    assert (run/'management/own/source.json').read_bytes() == b'original source bytes'
    assert not (run/'management/other').exists()


def test_record_path_cannot_collect_files_outside_source(tmp_path):
    run = tmp_path/'run'; run.mkdir()
    (run/'log.txt').write_text(f'Simulation record: {tmp_path}/outside/manifest.json\n')
    with pytest.raises(ValueError, match='outside'):
        collect(tmp_path/'source', run)
