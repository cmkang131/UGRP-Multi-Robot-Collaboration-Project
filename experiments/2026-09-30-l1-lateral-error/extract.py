#!/usr/bin/env python3
"""Read-only census of existing stage-probe carry endpoints; no simulator imports.

One beam, not two robot observations, per endpoint. Missing boundaries remain in
the case denominator. A signed cross-track coordinate is reconstructed from the
route and the later robot boundary, matching pair_chain_probe. GT is eval-only.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs')
SAMPLES = ROOT / 'experiments/2026-09-29-pair-v6e-carry/hR2_samples.json'


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def digest(data):
    return hashlib.sha256(data).hexdigest()


def signed_errors(p0, p1, xy):
    """Along endpoint error and signed left-of-route error, metres."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length <= 0:
        raise ValueError('zero-length route leg')
    ux, uy = dx / length, dy / length
    ex, ey = xy[0] - p1[0], xy[1] - p1[1]
    return ex * ux + ey * uy, -ex * uy + ey * ux


def later(records):
    got = [r for r in records if r and r.get('gt')]
    return max(got, key=lambda r: r['sim_s']) if got else None


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 9) if isinstance(v, float) else v) for k, v in r.items()})


def discover(root):
    """Inventory summaries, avoiding images/checkpoints/derived TensorBoard views."""
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in ('cases', 'frames', 'eval_only', '.git')
                         and 'tensorboard' not in d and 'tbviews' not in d)
        if 'cases.jsonl' in files:
            out.append(Path(base) / 'cases.jsonl')
    return sorted(out, key=lambda p: (len(p.parts), str(p)))


class Reader:
    """Hash the exact bytes parsed, validate every available recorded hash."""
    def __init__(self, root):
        self.root = root
        self.receipts = {}

    def read(self, path, expected=None):
        data = path.read_bytes()
        sha = digest(data)
        rel = str(path.relative_to(self.root))
        if expected and not sha.startswith(expected):
            raise ValueError(f'sha256 mismatch: {rel}: expected {expected}, got {sha}')
        old = self.receipts.get(rel)
        if old and old['sha256'] != sha:
            raise ValueError(f'input changed during extraction: {rel}')
        self.receipts[rel] = {'path': rel, 'bytes': len(data), 'sha256': sha,
                              'recorded_sha256': expected or (old or {}).get('recorded_sha256', '')}
        return data

    def json(self, path, expected=None):
        return json.loads(self.read(path, expected))


def prior_info(case, samples):
    """Identify the reused hR2 posterior from errors relative to setup robot poses."""
    err = []
    for rid in ('r1', 'r2'):
        p = case.get('prior', {}).get(rid, {}).get('mean_xyyaw')
        g = case.get('placement_xyyaw', {}).get(rid)
        if p is None or g is None:
            return {'prior_id': 'unknown'}
        err.append([p[0] - g[0], p[1] - g[1], wrap(p[2] - g[2])])
    distances = {}
    for sample in samples:
        e = [sample['prior_err'][rid]['mean_err_xyyaw'] for rid in ('r1', 'r2')]
        distances[sample['id']] = max(abs(err[i][j] - e[i][j]) for i in range(2) for j in range(3))
    best = min(distances, key=distances.get)
    return {'prior_id': best if distances[best] < 1e-7 else 'other',
            'prior_y_error_mm': 500 * sum(e[1] for e in err),
            'prior_yaw_error_deg': math.degrees(sum(e[2] for e in err) / 2)}


def endpoint_row(base, case, result, k, start, end, metrics):
    route = case['route']
    p0, p1 = route[k:k + 2]
    s, e = start['gt'], end['gt']
    ax, lat = signed_errors(p0, p1, e['beam_xyz'])
    sx, sy = signed_errors(p0, p1, s['beam_xyz'])
    recorded = metrics.get('end_error_m')
    if recorded is not None and abs(math.hypot(ax, lat) - recorded) > 1e-6:
        raise ValueError(f'endpoint disagreement: {base["cohort"]} {base["case_id"]} L{k}')
    yaw_errors = []
    if base['stage'] == 'chain':
        for rid, raw in result.get('chain_raw', {}).items():
            t = raw.get('leg_start', {}).get(str(k))
            if t and t.get('own') and t.get('gt'):
                yaw_errors.append(wrap(t['own']['xyyaw'][2] - t['gt']['robots'][rid][2]))
    else:
        for rid, entry in result.get('entry', {}).items():
            own = entry.get('own_report')
            if own and own.get('xyyaw') and rid in s.get('robots', {}):
                yaw_errors.append(wrap(own['xyyaw'][2] - s['robots'][rid][2]))
    load = {v.get('own_report', {}).get('load_state') for v in result.get('entry', {}).values()}
    return {**base, 'leg': k, 'axis': 'axial' if abs(p1[1] - p0[1]) < 1e-8 else 'lateral',
            'load': 'loaded' if case.get('teacher_held') or load == {'loaded'} else 'unknown',
            'start_s': start['sim_s'], 'end_s': end['sim_s'],
            'planned_mm': 1000 * math.dist(p0, p1),
            'axial_mm': 1000 * ax, 'lateral_mm': 1000 * lat, 'end_mm': 1000 * math.hypot(ax, lat),
            'yaw_end_deg': math.degrees(wrap(e['beam_yaw'])),
            'yaw_drift_deg': metrics.get('yaw_drift_deg'),
            'start_axial_mm': 1000 * sx, 'start_lateral_mm': 1000 * sy,
            'start_yaw_deg': math.degrees(wrap(s['beam_yaw'])),
            'start_pf_yaw_error_deg': math.degrees(sum(yaw_errors) / len(yaw_errors)) if yaw_errors else None,
            'door_start_distance_mm': 1000 * abs(2.2 - s['beam_xyz'][0]),
            'door_end_distance_mm': 1000 * abs(2.2 - e['beam_xyz'][0])}


def collect(raw, files, expectations):
    reader = Reader(raw)
    samples = json.loads(SAMPLES.read_text())['samples']
    endpoints, cases, inventory, acceptance = [], [], [], []
    seen_dirs = set()
    for summary in files:
        root = summary.parent
        cohort = str(root.relative_to(raw))
        manifest = reader.json(root / 'manifest.json') if (root / 'manifest.json').exists() else {}
        data = reader.read(summary, manifest.get('cases_jsonl_sha256'))
        for expected in expectations.get(cohort, []):
            reader.read(summary, expected['sha256'])
        entries = [json.loads(line) for line in data.splitlines() if line.strip()]
        artifacts = reader.json(root / 'artifacts.sha256.json') if (root / 'artifacts.sha256.json').exists() else {}
        inv = {'cohort': cohort, 'rows': len(entries), 'state': manifest.get('state'),
               'source_sha': manifest.get('source_sha'), 'source_changed': manifest.get('source_changed'),
               'cases_sha256': digest(data), 'stages': dict(Counter(r.get('stage') for r in entries)),
               'carry_chain_cases': 0, 'endpoints': 0, 'duplicate_case_dirs': 0,
               'missing_files': 0, 'cases_without_endpoint': 0}
        plan, acceptance_meta = {}, {}
        if (root / 'plan.json').exists():
            plan = reader.json(root / 'plan.json', manifest.get('plan_sha256'))
        if (root / 'acceptance_receipts.json').exists():
            for receipt in reader.json(root / 'acceptance_receipts.json'):
                acceptance_meta[receipt['case_id']] = receipt
                ref = raw / Path(receipt['reference_case_dir']).relative_to(RAW)
                reg = raw / Path(receipt['registered_case_dir']).relative_to(RAW)
                ref_cmd = (reader.read(ref / 'commands.json', receipt['reference_commands_sha256'])
                           if (ref / 'commands.json').exists() else None)
                reg_cmd = (reader.read(reg / 'commands.json', receipt['registered_commands_sha256'])
                           if (reg / 'commands.json').exists() else None)
                reader.read(ref.parent.parent / 'cases.jsonl', receipt['reference_cases_jsonl_sha256'])
                reader.read(ref.parent.parent / 'plan.json', receipt['reference_plan_sha256'])
                ref_result = reader.json(ref / 'result.json')
                reg_result = reader.json(reg / 'result.json') if (reg / 'result.json').exists() else {}
                ref_legs = (ref_result.get('row', {}).get('chain') or {}).get('legs', [])[:2]
                reg_legs = (reg_result.get('row', {}).get('chain') or {}).get('legs', [])[:2]
                acceptance.append({'cohort': cohort, 'case_id': receipt['case_id'],
                                   'reference_case': str(ref.relative_to(raw)),
                                   'sanity_lag_off': receipt.get('sanity', False),
                                   'attribution_override': bool(plan.get('attribution')),
                                   'command_files_present': ref_cmd is not None and reg_cmd is not None,
                                   'command_bytes_equal': ref_cmd == reg_cmd if ref_cmd is not None and reg_cmd is not None else None,
                                   'audited_L0_L1_legs_equal': bool(ref_legs) and ref_legs == reg_legs,
                                   'registered_recorded_legs': sum(bool(l.get('recorded')) for l in reg_legs),
                                   'receipt_legs_equal': receipt.get('recorded_legs_equal'),
                                   'receipt_bit_identical': receipt.get('bit_identical'),
                                   'used_as_new_model_unit': False})
        for row in entries:
            if row.get('stage') not in ('carry', 'chain'):
                continue
            inv['carry_chain_cases'] += 1
            cid = row['case_id']
            d = root / 'cases' / cid.replace('@', '_').replace(':', '_').replace('/', '_')
            if not (d / 'case.json').exists() or not (d / 'result.json').exists():
                inv['missing_files'] += 1
                cases.append({'cohort': cohort, 'case_id': cid, 'status': 'missing_result_or_case',
                              'category': row.get('category'), 'endpoints': 0})
                continue
            physical = str(d.resolve())
            if physical in seen_dirs:
                inv['duplicate_case_dirs'] += 1
                continue
            seen_dirs.add(physical)
            vals = []
            for name in ('case.json', 'result.json'):
                p = d / name
                expected = artifacts.get(str(p.relative_to(root)), {}).get('sha256')
                vals.append(reader.json(p, expected))
            case, result = vals
            policy = case.get('policy_id', case.get('pair_policy', 'unknown'))
            rawlag = bool(case.get('carry_axial_lag'))
            rawgain = bool(case.get('carry_gain_fix'))
            # Registered b-v6h1 embodies these flags; its acceptance receipt is
            # assessed as a repeated run, not a new treatment cohort.
            lag = (rawlag or policy == 'b-v6h1') and not acceptance_meta.get(cid, {}).get('sanity', False)
            gain = rawgain or policy == 'b-v6h1'
            lateral_lag = policy in ('b-v6e-lag', 'b-v6e-base', 'b-v6e', 'b-v6e-pm', 'b-v6e-edge',
                                     'b-v6g', 'b-v6g-l7', 'b-v6h', 'b-v6h1')
            bp = case['beam_xyyaw']
            sheet = case.get('coarse_order_sheet', {}).get('beam_xyyaw', [None] * 3)
            base = {'cohort': cohort, 'case_id': cid, 'stage': case['stage'], 'cell': case['cell'],
                    'seed': case['seed'], 'policy': policy, 'axial_lag': int(lag), 'lateral_lag': int(lateral_lag),
                    'gain_fix': int(gain), 'door_relax': case.get('door_relax') or '',
                    'progress': case.get('progress_relax') or '', 'diag': case.get('diag_patch') or '',
                    'attribution_override': int(bool(plan.get('attribution'))),
                    'setup': case.get('setup_variant') or '', 'sheet_x': sheet[0],
                    'place_x': bp[0], 'place_y': bp[1], 'place_yaw_deg': math.degrees(wrap(bp[2])),
                    'dx_mm': 1000 * (bp[0] - sheet[0]) if sheet[0] is not None else None,
                    'stage_category': row.get('category'),
                    'wall_episodes': (row.get('wall_contact') or {}).get('episodes'),
                    **prior_info(case, samples)}
            got = []
            if case['stage'] == 'chain':
                chain = row.get('chain') or (result.get('row') or {}).get('chain') or {}
                for leg in chain.get('legs', []):
                    if not leg.get('recorded'):
                        continue
                    k = leg['leg']
                    starts = [r.get('leg_start', {}).get(str(k)) for r in result['chain_raw'].values()]
                    ends = [r.get('leg_end', {}).get(str(k)) for r in result['chain_raw'].values()]
                    if not all(starts) or not all(ends):
                        raise ValueError(f'recorded leg missing robot boundary: {cid} L{k}')
                    got.append(endpoint_row(base, case, result, k, later(starts), later(ends), leg))
            elif row.get('metrics', {}).get('end_error_m') is not None:
                end = later(result['exits'].values())
                # Carry metrics use the last robot's recorded exit; starting GT
                # is the logged pre-submit observation (unlike chain start).
                start = {'sim_s': result['gt_at_entry']['t'], 'gt': result['gt_at_entry']}
                got.append(endpoint_row(base, case, result, int(case.get('leg') or 0), start, end, row['metrics']))
            endpoints.extend(got)
            inv['endpoints'] += len(got)
            inv['cases_without_endpoint'] += not bool(got)
            cases.append({'cohort': cohort, 'case_id': cid, 'status': 'parsed', 'category': row.get('category'),
                          'endpoints': len(got), 'reported_stage_pass': row.get('passed'),
                          'complete_l0_l1': {r['leg'] for r in got}.issuperset({0, 1})})
        inventory.append(inv)
    return endpoints, cases, inventory, list(reader.receipts.values()), acceptance


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, default=RAW)
    p.add_argument('--out', type=Path, default=HERE / 'results')
    p.add_argument('--source-list', type=Path, default=HERE / 'inputs/source_list.json')
    p.add_argument('--discover', action='store_true', help='explicitly replace the frozen input list')
    p.add_argument('--verify-only', action='store_true', help='rehash all parsed raw inputs against the saved receipt; writes nothing')
    a = p.parse_args()
    if any(p.resolve().is_relative_to(a.raw.resolve()) for p in (a.out, a.source_list)):
        raise ValueError('outputs/ is read-only; choose an analysis destination outside it')
    if a.verify_only:
        with (a.out / 'input_hashes.csv').open() as f:
            receipts = list(csv.DictReader(f))
        reader = Reader(a.raw)
        for r in receipts:
            reader.read(a.raw / r['path'], r['sha256'])
        print(f'verified {len(receipts)} unchanged raw inputs; no writes')
        return
    if a.discover:
        files = discover(a.raw)
        a.source_list.parent.mkdir(parents=True, exist_ok=True)
        a.source_list.write_text(json.dumps([str(f.relative_to(a.raw)) for f in files], indent=1) + '\n')
    else:
        files = [a.raw / name for name in json.loads(a.source_list.read_text())]
    expectations = json.loads((HERE / 'inputs/recorded_checksums.json').read_text())
    endpoints, cases, inventory, receipts, acceptance = collect(a.raw, files, expectations)
    a.out.mkdir(parents=True, exist_ok=True)
    write_csv(a.out / 'endpoints.csv', endpoints)
    write_csv(a.out / 'cases.csv', cases)
    write_csv(a.out / 'input_hashes.csv', receipts)
    write_csv(a.out / 'acceptance_audit.csv', acceptance)
    (a.out / 'inventory.json').write_text(json.dumps(inventory, indent=1) + '\n')
    print(json.dumps({'sources': len(files), 'cases': len(cases), 'endpoints': len(endpoints),
                      'hashed_files': len(receipts), 'verified_recorded_hashes': sum(bool(r['recorded_sha256']) for r in receipts)}))


if __name__ == '__main__':
    main()
