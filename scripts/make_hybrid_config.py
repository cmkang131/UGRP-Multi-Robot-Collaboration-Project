"""Hybrid carry config v2 from the loaded-odometry fit (the only way to lift the template's [확인 필요]).

    python scripts/make_hybrid_config.py --fit <out>/loaded-odom-fit.json \
        --template experiments/2026-10-21-pairact-p2/HYBRID_CARRY_NAV_TEMPLATE_V2.json \
        --purpose teacher_smoke|hybrid_n --out hybrid.json [--expect-fit-sha256 <sha>] \
        --set limits.carry_budget_s=110 --set nav.profile=gpu_calib_v5_h112 ...

* calibration (gain, latency, bias) and the sigma growth rates come ONLY from the fit file; ``--set``
  on them (or on mode / calibration_provenance) is refused. The config records the fit file sha256
  and values_sha256, which harness/hybrid_carry.validate_config recomputes.
* every other ``[확인 필요]`` placeholder must be replaced by an explicit owner ``--set``; nothing is
  defaulted. The result is validated with the teacher's own validate_config(purpose=...).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import hybrid_carry as hc   # noqa: E402

FITTED_TOP = ('mode', 'calibration', 'calibration_provenance')
PLACEHOLDER = '[확인 필요'


def _value(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return float(text)          # '.25'
        except ValueError:
            return text


def _placeholders(node, path=''):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _placeholders(v, f'{path}.{k}' if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _placeholders(v, f'{path}[{i}]')
    elif isinstance(node, str) and PLACEHOLDER in node:
        yield path


def build(fit, fit_sha256, template, sets, *, purpose):
    if fit.get('schema') != hc.FIT_SCHEMA or fit.get('fit_quality') not in hc.FIT_QUALITIES:
        raise ValueError('not a loaded-odometry fit file (schema / fit_quality)')
    if fit.get('values_sha256') != hc.calibration_values_sha256(fit['calibration'], fit['sigma']):
        raise ValueError('fit file values do not match its values_sha256 (edited fit file)')
    cfg = copy.deepcopy(template)
    for item in sets:
        key, sep, raw = item.partition('=')
        parts = key.split('.')
        if not sep or not key:
            raise ValueError(f'--set needs key=value: {item!r}')
        if parts[0] in FITTED_TOP or (parts[0] == 'limits' and len(parts) > 1 and parts[1] in hc.SIGMA_FIT_KEYS):
            raise ValueError(f'{key} is fit-tool output, not an owner value')
        node = cfg
        for p in parts[:-1]:
            if not isinstance(node.get(p), dict):
                raise ValueError(f'unknown config path {key}')
            node = node[p]
        if parts[-1] not in node:
            raise ValueError(f'unknown config key {key} (template keys only)')
        node[parts[-1]] = _value(raw)
    cfg['mode'] = hc.MODE
    cfg['calibration'] = dict(fit['calibration'])
    for k in hc.SIGMA_FIT_KEYS:
        cfg['limits'][k] = fit['sigma'][k]
    if purpose == 'teacher_smoke':
        cfg['shadow_predict'] = False
    cfg['calibration_provenance'] = {
        'schema': hc.FIT_SCHEMA, 'fit_sha256': fit_sha256, 'values_sha256': fit['values_sha256'],
        'fit_quality': fit['fit_quality'], 'seeds': list(fit['seeds']), 'sources': list(fit['sources']),
        'tool': 'scripts/fit_loaded_odom.py + scripts/make_hybrid_config.py'}
    left = list(_placeholders(cfg))
    if left:
        raise ValueError(f'[확인 필요] placeholders left (owner --set required): {left}')
    hc.validate_config(cfg, purpose=purpose)
    return cfg


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--fit', type=Path, required=True)
    p.add_argument('--template', type=Path, required=True)
    p.add_argument('--purpose', choices=hc.PURPOSES, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--set', action='append', default=[])
    p.add_argument('--expect-fit-sha256')
    a = p.parse_args(argv)
    raw = a.fit.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if a.expect_fit_sha256 is not None and a.expect_fit_sha256 != sha:
        raise ValueError(f'fit_sha256 {sha} != expected {a.expect_fit_sha256}')
    cfg = build(json.loads(raw), sha, json.loads(a.template.read_text()), a.set, purpose=a.purpose)
    a.out.write_text(json.dumps(cfg, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'config': str(a.out), 'config_sha256': hashlib.sha256(a.out.read_bytes()).hexdigest(),
                      'fit_sha256': sha, 'purpose': a.purpose}, ensure_ascii=False))
    return cfg


if __name__ == '__main__':
    main()
