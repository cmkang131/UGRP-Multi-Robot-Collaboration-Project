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
