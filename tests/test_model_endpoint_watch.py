import io
import json
import urllib.error

from scripts import model_endpoint_watch as w

CONFIG = dict(price_increase_tolerance=0.05, endpoints=[dict(
    model='m/x', provider='Novita',
    baseline_usd_per_million=dict(prompt=0.021, completion=0.0616, input_cache_read=0.0042))])


def endpoint(name='Novita', prompt='0.000000021', status=0):
    return dict(provider_name=name, status=status,
                pricing=dict(prompt=prompt, completion='0.0000000616', input_cache_read='0.0000000042'))


def test_ok_when_unchanged():
    assert w.check(CONFIG, get=lambda m: dict(data=dict(endpoints=[endpoint()]))) == []


def test_price_increase_beyond_tolerance():
    alerts = w.check(CONFIG, get=lambda m: dict(data=dict(endpoints=[endpoint(prompt='0.00000005')])))
    assert [a['kind'] for a in alerts] == ['price_increase']
    assert alerts[0]['prices']['prompt']['now'] == 0.05


def test_small_change_within_tolerance_is_ok():
    assert w.check(CONFIG, get=lambda m: dict(data=dict(endpoints=[endpoint(prompt='0.000000022')]))) == []


def test_provider_stopped_lists_remaining():
    alerts = w.check(CONFIG, get=lambda m: dict(data=dict(endpoints=[endpoint('DeepInfra')])))
    assert alerts == [dict(kind='provider_stopped', model='m/x', provider='Novita',
                           remaining_providers=['DeepInfra'])]


def test_model_removed():
    def gone(m):
        raise urllib.error.HTTPError('u', 404, 'nf', {}, io.BytesIO())
    assert w.check(CONFIG, get=gone)[0]['kind'] == 'model_removed'


def test_alert_written_once(tmp_path, monkeypatch):
    cfg = tmp_path / 'c.json'
    cfg.write_text(json.dumps(CONFIG))
    monkeypatch.setattr(w, 'fetch', lambda m, timeout=30: dict(data=dict(endpoints=[endpoint('Other')])))
    monkeypatch.setattr(w, 'check', lambda c, get=None: [dict(kind='provider_stopped', model='m/x', provider='Novita')])
    out = tmp_path / 'alerts'
    assert w.main(['--config', str(cfg), '--alerts', str(out)]) == 2
    assert w.main(['--config', str(cfg), '--alerts', str(out)]) == 2
    assert len([p for p in out.iterdir() if p.name != 'last-alerts.json']) == 1


def _run(tmp_path, monkeypatch, alerts_or_exc):
    cfg = tmp_path / 'c.json'
    cfg.write_text(json.dumps(CONFIG))

    def fake(c, get=None):
        if isinstance(alerts_or_exc, Exception):
            raise alerts_or_exc
        return alerts_or_exc
    monkeypatch.setattr(w, 'check', fake)
    return w.main(['--config', str(cfg), '--alerts', str(tmp_path / 'alerts')])


def _alert_files(tmp_path):
    return [p for p in (tmp_path / 'alerts').iterdir() if p.name not in ('last-alerts.json', 'check-failures.json')]


def test_alert_clear_then_recur_alerts_again(tmp_path, monkeypatch):
    a = [dict(kind='price_increase', model='m/x', provider='Novita')]
    assert _run(tmp_path, monkeypatch, a) == 2
    assert _run(tmp_path, monkeypatch, []) == 0
    assert not (tmp_path / 'alerts' / 'last-alerts.json').exists()
    import time; time.sleep(1.1)
    assert _run(tmp_path, monkeypatch, a) == 2
    assert len(_alert_files(tmp_path)) == 2


def test_three_failures_raise_check_failed_alert(tmp_path, monkeypatch):
    for _ in range(3):
        assert _run(tmp_path, monkeypatch, w.CheckFailed('net down')) == 3
    files = _alert_files(tmp_path)
    assert len(files) == 1 and 'check_failed' in files[0].read_text()
    assert _run(tmp_path, monkeypatch, []) == 0
    assert not (tmp_path / 'alerts' / 'check-failures.json').exists()


def test_missing_or_bad_price_is_reported():
    e = endpoint(); e['pricing'] = dict(prompt='0.000000021', completion=None, input_cache_read='abc')
    kinds = w.check(CONFIG, get=lambda m: dict(data=dict(endpoints=[e])))
    assert [k['kind'] for k in kinds] == ['price_missing', 'price_missing']


def test_malformed_response_is_check_failure():
    import pytest
    for payload in (dict(data=[]), dict(data=dict(endpoints=[dict(status=0)])),
                    dict(data=dict(endpoints=[dict(provider_name='Novita', pricing=[1])]))):
        with pytest.raises(w.CheckFailed):
            w.check(CONFIG, get=lambda m, p=payload: p)


def test_tag_pins_one_of_several_provider_endpoints():
    cfg = dict(CONFIG, endpoints=[dict(CONFIG['endpoints'][0], tag='novita/turbo')])
    turbo = dict(endpoint(), tag='novita/turbo')
    other = dict(endpoint(prompt='0.0000002'), tag='novita/fp8')
    assert w.check(cfg, get=lambda m: dict(data=dict(endpoints=[turbo, other]))) == []
    assert w.check(cfg, get=lambda m: dict(data=dict(endpoints=[other])))[0]['kind'] == 'provider_stopped'


def test_tagless_endpoint_next_to_tagged_one_is_ignored():
    cfg = dict(CONFIG, endpoints=[dict(CONFIG['endpoints'][0], tag='novita/turbo')])
    turbo = dict(endpoint(), tag='novita/turbo')
    assert w.check(cfg, get=lambda m: dict(data=dict(endpoints=[endpoint('Other'), turbo]))) == []
