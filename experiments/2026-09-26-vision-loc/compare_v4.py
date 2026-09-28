#!/usr/bin/env python3
"""Finite, serial VIS4 DEV replay. Uses frozen pre-run plan; no test or renderer.

All original inputs are read-only. Every result goes below the worktree outputs.
Complete baseline estimates are reused, with hashes (not claimed as a new run).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
from pathlib import Path
from types import SimpleNamespace

import diagnose_v4 as d
import vision_loc as vl
import vision_loc_cli_v4 as cli
import vision_loc_io as vio
import vision_loc_score as score

HERE = Path(__file__).resolve().parent
OUT = d.OUT
RUNTIME = ('vision_loc.py', 'vision_pf_v4.py', 'vision_motion.py', 'vision_sigma.py', 'vision_loc_cli_v4.py', 'vision_loc_io.py',
           'vision_loc_score.py', 'compare_v4.py', 'diagnose_v4.py', 'dev_plan_v4.json', 'selected_config_v3.json',
           'calibration_train.json', 'maps/zone_wide_door_walls_v3_notags.json')


def source_hashes():
    return {name: vio.sha_file(HERE/name) for name in RUNTIME}


def baseline(episodes, output):
    output.mkdir(parents=True, exist_ok=False)
    sources = {}
    for ep in episodes:
        records = None
        for kind, sub in (('vision', 'dev-grid'), ('oracle', 'dev-oracle')):
            path = vio.PRIMARY_OUT/'r3'/sub/'a1_open'/f'{ep}.estimates.jsonl'
            meta = json.loads(path.with_name(f'{ep}.meta.json').read_text())
            if meta['failure'] is not None or meta['frames'] != meta['frames_written']:
                raise ValueError(f'incomplete baseline {path}')
            sources[str(path)] = vio.sha_file(path)
            rows = vl.read_jsonl(path)
            if records is None:
                records = rows
            else:
                if [(r['frame'], r['t']) for r in rows] != [(r['frame'], r['t']) for r in records]:
                    raise ValueError('baseline frame mismatch')
                for a, b in zip(records, rows): a[kind] = b[kind]
        cli._write_estimates(output/f'{ep}.estimates.jsonl', records)
    d.save(output/'reuse_manifest.json', {'reused': True, 'sources_sha256': sources})


def metric_sets(directory, episodes, validation):
    result = {}
    for name, eps in (('all_dev', episodes), ('validation', validation)):
        target = directory/f'metrics_{name}.json'
        score.score(SimpleNamespace(episodes=eps, estimates=str(directory), output=str(target),
                                    obs=None, oracle_obs=None, config=None, checkpoint=None, role='primary'))
        result[name] = json.loads(target.read_text())
    return result


def select(metrics):
    """The pre-written rule, never gate retuning based on a result."""
    checks, eligible = {}, []
    for name in ('x1', 'm1'):
        reasons = []
        for cohort in ('validation', 'all_dev'):
            b, c = metrics['b0'][cohort], metrics[name][cohort]
            bd, cd = b['pooled']['vision']['door_loaded'], c['pooled']['vision']['door_loaded']
            for key, limit in (('pos_p90_m', .003), ('lat_abs_p99_m', .003), ('yaw_p90_deg', .3)):
                if cd[key] > bd[key] + limit: reasons.append(f'{cohort}:{key}:regressed')
            if cd['pos_p90_m'] > bd['pos_p90_m'] - .003 + 1e-12: reasons.append(f'{cohort}:P:not_improved_3mm')
            ba, ca = b['pooled']['vision']['all'], c['pooled']['vision']['all']
            if ca['pos_p90_m'] > ba['pos_p90_m'] + .02: reasons.append(f'{cohort}:all_p90:regressed')
            if c['recovery_pooled']['vision']['lost_frames'] > b['recovery_pooled']['vision']['lost_frames'] + math.ceil(.01*ba['n']):
                reasons.append(f'{cohort}:lost:regressed')
        b, c = metrics['b0']['all_dev'], metrics[name]['all_dev']
        if c['pooled']['oracle']['door_loaded']['pos_p90_m'] > b['pooled']['oracle']['door_loaded']['pos_p90_m'] + .005:
            reasons.append('oracle:P:regressed')
        checks[name] = {'eligible': not reasons, 'reasons': reasons}
        if not reasons: eligible.append(name)
    def rank(name):
        c = metrics[name]['validation']['pooled']['vision']['door_loaded']
        return c['pos_p90_m'], c['lat_abs_p99_m'], metrics[name]['all_dev']['recovery_pooled']['vision']['lost_frames'], name != 'x1'
    return {'selected': min(eligible, key=rank) if eligible else 'b0', 'checks': checks,
            'scope': 'dev selection only; no independent test or closed-loop claim'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, default=OUT/'comparison')
    ap.add_argument('--motion', type=Path, default=OUT/'motion_fit_final.json')
    args = ap.parse_args()
    plan = vio.load_json(d.PLAN)
    episodes = plan['fit_episodes'] + plan['validation_episodes']
    d.require_dev(episodes)
    motion = vio.load_json(args.motion)
    if motion['plan_sha256'] != vio.sha_file(d.PLAN) or motion['fit_episodes'] != plan['fit_episodes']:
        raise ValueError('motion fitting provenance differs from plan')
    args.output.mkdir(parents=True, exist_ok=False)
    hashes = source_hashes()
    d.save(args.output/'source_freeze.json', {'source_sha256': hashes, 'motion_sha256': vio.sha_file(args.motion),
           'plan_sha256': vio.sha_file(d.PLAN), 'python': platform.python_version(), 'loadavg_start': os.getloadavg(),
           'source_commit': plan['base_sha'], 'uncommitted_by_user_request': True})
    metrics = {}
    cfg0 = vio.load_json(HERE/'selected_config_v3.json')
    try:
        baseline(episodes, args.output/'b0')
        metrics['b0'] = metric_sets(args.output/'b0', episodes, plan['validation_episodes'])
        for variant in ('x1', 'm1'):
            cfg = {**cfg0, 'motion_v4': {'exact': True} if variant == 'x1' else motion['motion_v4']}
            config = args.output/f'{variant}.json'
            d.save(config, cfg)
            for ep in episodes:
                if source_hashes() != hashes: raise ValueError('runtime changed during cohort')
                print(f'START {variant} {ep} loadavg={os.getloadavg()}', flush=True)
                cli.localize(SimpleNamespace(filters='vision,oracle', episodes=[ep], config=str(config),
                    calibration=str(HERE/'calibration_train.json'), role='primary',
                    checkpoint=str(vio.PRIMARY_OUT/'model'/'seg-v2'/'seg_lraspp_mbv3.pt'),
                    obs=str(vio.PRIMARY_OUT/'r3'/'obs-w6'), oracle_obs=str(vio.PRIMARY_OUT/'r3'/'oracle-w6'),
                    motion=str(args.motion) if variant == 'm1' else None, output=str(args.output/variant)))
            metrics[variant] = metric_sets(args.output/variant, episodes, plan['validation_episodes'])
        if source_hashes() != hashes: raise ValueError('runtime changed during cohort')
        decision = select(metrics)
        d.save(args.output/'selection.json', {**decision, 'plan_sha256': vio.sha_file(d.PLAN), 'metrics': metrics})
        print(json.dumps(decision), flush=True)
    except BaseException as exc:
        d.save(args.output/'INCOMPLETE.json', {'reason': f'{type(exc).__name__}: {exc}', 'loadavg': os.getloadavg()})
        raise


if __name__ == '__main__':
    main()
