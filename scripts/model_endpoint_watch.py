#!/usr/bin/env python3
"""Check pinned LLM endpoints for price increases or end of serving.

Reads configs/model_endpoints.json, queries the public OpenRouter endpoints API
(no key) and reports a model that disappeared, a pinned provider that stopped
serving it, a non-zero endpoint status, or a price above baseline+tolerance.
New alerts are written to <alerts>/<timestamp>.json; the same alert set is not
re-written until it changes. Exit 0 = ok, 2 = alert, 3 = check failed.
"""
import argparse
import datetime
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = 'https://openrouter.ai/api/v1/models/{model}/endpoints'
PRICE_KEYS = ('prompt', 'completion', 'input_cache_read')


def fetch(model, timeout=30):
    with urllib.request.urlopen(API.format(model=model), timeout=timeout) as r:
        return json.load(r)


def check(config, get=fetch):
    tol = float(config.get('price_increase_tolerance', 0.05))
    alerts = []
    for ep in config['endpoints']:
        model, provider = ep['model'], ep['provider']
        try:
            data = get(model)['data']
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                alerts.append(dict(kind='model_removed', model=model, provider=provider))
                continue
            raise
        found = {e['provider_name']: e for e in data.get('endpoints', [])}
        e = found.get(provider)
        if e is None:
            alerts.append(dict(kind='provider_stopped', model=model, provider=provider,
                               remaining_providers=sorted(found)))
            continue
        if e.get('status', 0) != 0:
            alerts.append(dict(kind='endpoint_status', model=model, provider=provider,
                               status=e.get('status'), uptime_last_1d=e.get('uptime_last_1d')))
        base = ep['baseline_usd_per_million']
        price = {k: float(e['pricing'].get(k) or 0) * 1e6 for k in PRICE_KEYS}
        up = {k: dict(baseline=base[k], now=round(price[k], 6)) for k in PRICE_KEYS
              if k in base and price[k] > base[k] * (1 + tol)}
        if up:
            alerts.append(dict(kind='price_increase', model=model, provider=provider, prices=up))
    return alerts


def notify(alerts):
    if sys.platform != 'darwin':
        return
    text = '; '.join(f"{a['kind']} {a['model']} @ {a['provider']}" for a in alerts)[:200]
    subprocess.run(['osascript', '-e', f'display notification "{text}" with title "UGRP 모델 공급 경보"'],
                   check=False)


def main(argv=None):
    repo = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=repo / 'configs/model_endpoints.json')
    p.add_argument('--alerts', type=Path, default=Path.home() / 'projects/ugrp/outputs/model-endpoint-alerts')
    p.add_argument('--notify', action='store_true', help='Mac notification on a new alert')
    a = p.parse_args(argv)
    config = json.loads(a.config.read_text())
    try:
        alerts = check(config)
    except Exception as exc:  # network or API shape change: report, do not alert
        print(json.dumps(dict(ok=False, error=repr(exc))))
        return 3
    print(json.dumps(dict(ok=not alerts, alerts=alerts), ensure_ascii=False))
    if not alerts:
        return 0
    a.alerts.mkdir(parents=True, exist_ok=True)
    state = a.alerts / 'last-alerts.json'
    body = json.dumps(alerts, sort_keys=True, ensure_ascii=False)
    if not state.exists() or state.read_text() != body:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        (a.alerts / f'{stamp}.json').write_text(json.dumps(
            dict(checked_utc=stamp, config=str(a.config), alerts=alerts), indent=1, ensure_ascii=False) + '\n')
        state.write_text(body)
        if a.notify:
            notify(alerts)
    return 2


if __name__ == '__main__':
    sys.exit(main())
