#!/usr/bin/env python3
"""Check pinned LLM endpoints for price increases or end of serving.

Reads configs/model_endpoints.json, queries the public OpenRouter endpoints API
(no key) and reports a model that disappeared, a pinned provider that stopped
serving it, a non-zero endpoint status, or a price above baseline+tolerance.
New alerts are written to <alerts>/<timestamp>.json; the same alert set is not
re-written until it changes; last-alerts.json exists only while alerts are
active. Three consecutive failed checks write a check_failed alert.
Exit 0 = ok, 2 = alert, 3 = check failed.
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
FAILS_BEFORE_ALERT = 3


class CheckFailed(Exception):
    pass


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
            raise CheckFailed(f'{model}: HTTP {exc.code}') from exc
        except (urllib.error.URLError, OSError, KeyError, ValueError, TypeError) as exc:
            raise CheckFailed(f'{model}: {exc!r}') from exc
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
        pricing = e.get('pricing') or {}
        missing = sorted(k for k in base if pricing.get(k) in (None, ''))
        if missing:
            alerts.append(dict(kind='price_missing', model=model, provider=provider, keys=missing))
        up = {}
        for k in base:
            if k in missing:
                continue
            try:
                now = float(pricing[k]) * 1e6
            except (TypeError, ValueError):
                alerts.append(dict(kind='price_missing', model=model, provider=provider, keys=[k]))
                continue
            if now > base[k] * (1 + tol):
                up[k] = dict(baseline=base[k], now=round(now, 6))
        if up:
            alerts.append(dict(kind='price_increase', model=model, provider=provider, prices=up))
    return alerts


def notify(alerts):
    if sys.platform != 'darwin':
        return
    text = '; '.join(f"{a['kind']} {a.get('model', '')} @ {a.get('provider', '')}" for a in alerts)[:200]
    # Text goes in as argv, never spliced into AppleScript source.
    subprocess.run(['osascript', '-e', 'on run argv', '-e',
                    'display notification (item 1 of argv) with title "UGRP 모델 공급 경보"',
                    '-e', 'end run', text], check=False)


def main(argv=None):
    repo = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=repo / 'configs/model_endpoints.json')
    p.add_argument('--alerts', type=Path, default=Path.home() / 'projects/ugrp/outputs/model-endpoint-alerts')
    p.add_argument('--notify', action='store_true', help='Mac notification on a new alert')
    a = p.parse_args(argv)
    config = json.loads(a.config.read_text())
    a.alerts.mkdir(parents=True, exist_ok=True)
    state, fails = a.alerts / 'last-alerts.json', a.alerts / 'check-failures.json'
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    try:
        alerts = check(config)
    except CheckFailed as exc:
        n = (json.loads(fails.read_text()).get('consecutive', 0) if fails.exists() else 0) + 1
        fails.write_text(json.dumps(dict(consecutive=n, last_utc=stamp, error=str(exc))) + '\n')
        print(json.dumps(dict(ok=False, error=str(exc), consecutive_failures=n)))
        if n == FAILS_BEFORE_ALERT:
            failure = [dict(kind='check_failed', consecutive=n, error=str(exc))]
            (a.alerts / f'{stamp}.json').write_text(json.dumps(
                dict(checked_utc=stamp, config=str(a.config), alerts=failure), indent=1) + '\n')
            if a.notify:
                notify(failure)
        return 3
    if fails.exists():
        fails.unlink()
    print(json.dumps(dict(ok=not alerts, alerts=alerts), ensure_ascii=False))
    if not alerts:
        if state.exists():
            state.unlink()  # cleared: a recurrence must alert again
        return 0
    body = json.dumps(alerts, sort_keys=True, ensure_ascii=False)
    if not state.exists() or state.read_text() != body:
        (a.alerts / f'{stamp}.json').write_text(json.dumps(
            dict(checked_utc=stamp, config=str(a.config), alerts=alerts), indent=1, ensure_ascii=False) + '\n')
        state.write_text(body)
        if a.notify:
            notify(alerts)
    return 2


if __name__ == '__main__':
    sys.exit(main())
