#!/usr/bin/env python3
"""HAN-32: local read-only evidence analysis, never imports a simulator.

Writes only to --output (default: this new experiment directory). Requires
existing Oracle originals, zstd and sha256sum. Does not replay physics or infer
missing funnel flags. Do not point --output at a sealed evidence directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.pair_carry_eval import Criteria, success_strict_from_result

PILOT = Path('/home/ubuntu/UGRP/outputs/transfer/gcp6-20261021-shardsmoke/pairact-p2-c4-20261021T0555Z/pilot-8343000-b')
SECOND = Path('/home/ubuntu/ugrp-audit/clockfix/gap-fill-20261024/extracted/shards/s01/batches/b010/try-1/world-011/raw')
LEDGER = Path('/home/ubuntu/ugrp-audit/postclose/merged/ledger.jsonl')
SCOPED = Path('/home/ubuntu/ugrp-pair-gpu-scoped-retry-gcp6-20261027/results')
COLLECTOR = Path('/home/ubuntu/UGRP-wt/p5-registered/harness/pairact_collect.py')
W9 = Path('/home/ubuntu/ugrp-wt/codex-arm-s-post-render-20261027/experiments/2026-10-27-arm-s-post-render/DIAGNOSIS-ready-w9.md')
FINAL_FLAGS = ('zone_inside_final', 'lowered_resting', 'released', 'still_1s')


def load(path):
    if path.suffix == '.zst':
        return json.loads(subprocess.check_output(['zstd', '-dc', str(path)]))
    return json.loads(path.read_text())


def existing(raw, name):
    path = raw / name
    if path.exists():
        return path
    path = raw / (name + '.zst')
    if path.exists():
        return path
    raise FileNotFoundError(raw / name)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


class Index:
    def __init__(self):
        self.entries = {}

    def add(self, path, manifest_entry=None):
        path = Path(path).absolute()
        if str(path) not in self.entries:
            digest = subprocess.check_output(['sha256sum', '--', str(path)], text=True).split()[0]
            self.entries[str(path)] = {'sha256': digest, 'bytes': path.stat().st_size}
        entry = self.entries[str(path)]
        if manifest_entry is not None and entry['sha256'] != manifest_entry['sha256']:
            raise ValueError(f'manifest mismatch: {path}')
        return {'path': str(path), **entry}


def physical_trace(path, ev):
    """Stored 10 Hz positions/forces; no native collision-pair claim or new gate."""
    proc = subprocess.Popen(['zstd', '-dc', str(path)], stdout=subprocess.PIPE, text=True)
    path_m, carry_path_m, last, last_carry = 0., 0., None, None
    samples, held = 0, Counter()
    try:
        for line in proc.stdout:
            row = json.loads(line)
            xy = row['beam']['pose'][:2]
            if last is not None:
                path_m += math.dist(last, xy)
            last = xy
            if ev['handover_t'] <= row['t'] < ev['lower_start_t']:
                samples += 1
                if last_carry is not None:
                    carry_path_m += math.dist(last_carry, xy)
                last_carry = xy
                for rid in ('r1', 'r2'):
                    if min(row['contacts'][rid]) >= Criteria.released_max_force:
                        held[rid] += 1
    finally:
        proc.stdout.close()
        code = proc.wait()
    if code:
        raise RuntimeError(f'zstd exit {code}: {path}')
    return {'trace': str(path), 'full_trace_beam_xy_path_m': path_m,
            'carry_window_beam_xy_path_m': carry_path_m, 'carry_window_samples': samples,
            'bilateral_force_at_least_0p5N_ticks': dict(held),
            'bilateral_force_fraction': {rid: held[rid]/samples if samples else None for rid in ('r1', 'r2')},
            'scope': 'stored sampled gripper forces; no new force-duration acceptance threshold; not native collision pairs'}


def golden_case(raw, cohort, index, batch_manifest=None):
    ev = load(raw/'carry-eval.json')
    result_path, manifest_path = existing(raw, 'result.json'), existing(raw, 'manifest.json')
    result, plan, manifest = load(result_path), load(raw/'plan.json'), load(manifest_path)
    assert success_strict_from_result(ev), raw
    assert all(ev['funnel'].get(k) is True for k in FINAL_FLAGS), raw
    assert ev['drop_events'] == [] and ev['robot_robot_contact_ticks'] == 0, raw
    assert result['weld'] == 'off' and result['teacher_profile'] == 'visible_only', raw
    assert result['input_audit']['invisible_measurements'] == result['input_audit']['held_world_reads'] == 0, raw
    artifacts = {}
    entries = {}
    for name in ('carry-eval.json', 'result.json', 'plan.json', 'eval-only.jsonl.zst'):
        path = existing(raw, name)
        entry = manifest.get(path.name)
        artifacts[name] = index.add(path, entry)
        entries[path.name] = entry
        if batch_manifest is not None:
            batch_entry = batch_manifest.get(str(path.relative_to(PILOT)))
            if batch_entry is not None:
                index.add(path, batch_entry)
    index.add(manifest_path)
    for name in ('RUN_META.json', 'scene.xml', 'scene.json'):
        path = raw/name
        if path.exists():
            index.add(path)
    return {'cohort': cohort, 'seed': plan['seed'], 'world_id': raw.parent.name,
            'success': ev['success'], 'success_strict': True, 'carried_max_m': ev['carried_max_m'],
            'carried_min_m': ev['criteria']['carried_min_m'], 'door_passed': ev['funnel']['door_passed'],
            'door_passed_t': ev['door_passed_t'], 'funnel': ev['funnel'], 'sim_s': result['sim_s'],
            'drop_events': ev['drop_events'], 'robot_robot_contact_ticks': ev['robot_robot_contact_ticks'],
            'contact_source': ev['contact_source'], 'teacher_profile': result['teacher_profile'],
            'weld': result['weld'], 'input_audit': result['input_audit'],
            'source_sha': result.get('source_sha', load(raw/'RUN_META.json')['sha']),
            'manifest_path': str(manifest_path), 'manifest_entries': entries, 'artifacts': artifacts}, physical_trace(raw/'eval-only.jsonl.zst', ev)


def teacher_rescore(index):
    index.add(LEDGER)
    index.add(COLLECTOR)
    all_rows = [json.loads(line) for line in LEDGER.read_text().splitlines()]
    rows = [r for r in all_rows if r.get('type') == 'attempt']
    legacy = [r for r in rows if r.get('success') is True or r.get('outcome') == 'success']
    proxy = [r for r in legacy if r.get('success') is True and r.get('carried_max_m', 0.) >= 1.
             and r.get('funnel_last') == 'still_1s' and r.get('eval_failure') is None and r.get('drop_kinds') == []]
    # Collector 619-622 stores the LAST TRUE KEY, not a sequential conjunction.
    # Distance plus terminal stillness cannot prove passage through the door.
    ambiguous = [{'seed': r['seed'], 'raw': r['raw'], 'carried_max_m': r.get('carried_max_m'),
                  'reason': 'carried_1m and door_passed booleans absent; funnel_last is last true key, not conjunction'}
                 for r in legacy]
    return {'N': len(rows), 'total_jsonl_records': len(all_rows), 'legacy_success': len(legacy),
            'strict_success': None, 'strict_success_lower_bound': 0, 'strict_success_upper_bound': len(legacy),
            'strict_proxy': len(proxy), 'ambiguous_N': len(ambiguous),
            'ambiguous_rows': ambiguous, 'method': 'ledger-only proxy, NOT raw carry-eval recomputation',
            'proxy_definition': 'success AND carried_max_m>=1 AND funnel_last=still_1s AND eval_failure=null AND drop_kinds=[]',
            'limitation': 'All legacy successes lack independent door/carried booleans; do not certify proxy as strict success.',
            'rejection_reasons': dict(Counter(r.get('reason') or 'success:no_rejection' for r in rows))}


def student_rescore(arm, index):
    audit_path = SCOPED/f'{arm}-audit.json'
    audit = load(audit_path)
    index.add(audit_path)
    raw_root = SCOPED/'pair-gpu-scoped-20261027'/f'arm-{arm.lower()}'
    records = []
    for ep in audit['episodes']:
        raw = raw_root/f"world-{ep['world']:03d}"/'raw'
        result_path = existing(raw, 'result.json')
        result = load(result_path)
        index.add(result_path)
        ev_path = next((p for p in (raw/'carry-eval.json', raw/'carry-eval.json.zst') if p.exists()), None)
        ev = load(ev_path) if ev_path else result.get('carry_eval')
        if ev_path:
            index.add(ev_path)
        if ev is not None:
            strict = success_strict_from_result(ev)
            method = 'recomputed_from_carry_eval'
        elif ep['success'] is False and result['physical_success'] is False and result.get('carry_success') is False:
            strict = False
            method = 'inferred_false: raw/audit legacy failure implies strict failure; carry-eval absent'
        else:
            strict = None
            method = 'unknown: missing carry-eval evidence'
        records.append({'world': ep['world'], 'seed': ep['seed'], 'legacy_success': ep['success'],
                        'success_strict': strict, 'method': method, 'result_path': str(result_path),
                        'funnel': ep['funnel'], 'termination': ep['termination']['termination']})
    return {'N': audit['N_eff'], 'legacy_success': audit['successes'],
            'strict_success': sum(r['success_strict'] is True for r in records),
            'ambiguous_N': sum(r['success_strict'] is None for r in records),
            'raw_carry_eval_recomputed_N': sum(r['method'] == 'recomputed_from_carry_eval' for r in records),
            'inferred_failure_N': sum(r['success_strict'] is False for r in records),
            'audit_path': str(audit_path), 'raw_root': str(raw_root),
            'candidate_funnel': audit['candidate_funnel'], 'stage_counts': audit['stage_counts'],
            'termination_counts': dict(Counter(r['termination'] for r in records)), 'rows': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    out = args.output.absolute()
    if out in (PILOT, SECOND, SCOPED) or any(out.is_relative_to(p) for p in (PILOT, SECOND, SCOPED, LEDGER.parent)):
        parser.error('output must not be a sealed input location')
    out.mkdir(parents=True, exist_ok=True)
    index = Index()
    summary = load(PILOT/'summary.json')
    batch_manifest = load(PILOT/'artifact-sha256.json')
    for name in ('summary.json', 'rejection_table.json', 'artifact-sha256.json'):
        index.add(PILOT/name)
    index.add(W9)
    index.add(SCOPED/'GPU_CAP_RAISE_APPROVAL.json')
    index.add(SCOPED/'global-gpu-budget.json')
    index.add(PILOT/'artifact-sha256.json', summary['artifact_sha256_manifest'])
    gold, physical, exclusions = [], [], []
    funnel = Counter(requested=summary['planned_N'])
    for world in summary['worlds']:
        raw = PILOT/f"world-{world['world']:03d}"/'raw'
        ev_path = raw/'carry-eval.json'
        ev = load(ev_path) if ev_path.exists() else {}
        result = load(existing(raw, 'result.json'))
        audit = result.get('input_audit') or {}
        if ev_path.exists():
            index.add(ev_path)
        stages = [('carry_eval_present', bool(ev)), ('legacy_carry_success', ev.get('success') is True),
                  ('carried_1m', ev.get('funnel', {}).get('carried_1m') is True),
                  ('door_passed', ev.get('funnel', {}).get('door_passed') is True),
                  ('distance_at_least_1m', ev.get('carried_max_m', 0.) >= 1.),
                  ('final_placement_release_still', all(ev.get('funnel', {}).get(k) is True for k in FINAL_FLAGS)),
                  ('no_drops', ev.get('drop_events') == []),
                  ('robot_robot_proxy_zero', ev.get('robot_robot_contact_ticks') == 0),
                  ('weld_off_visible_only_clean_audit', result.get('weld') == 'off'
                   and result.get('teacher_profile') == 'visible_only'
                   and audit.get('invisible_measurements') == audit.get('held_world_reads') == 0)]
        passed = True
        for stage, flag in stages:
            passed = passed and flag
            funnel[stage] += int(passed)
        if passed:
            case, trace = golden_case(raw, 'pilot-8343000-b', index, batch_manifest)
            gold.append(case)
            physical.append({'cohort': case['cohort'], 'seed': case['seed'], **trace})
        else:
            exclusions.append({'world': world['world'], 'seed': world['seed'], 'batch_success': world['success'],
                               'cap_end': world['cap_end'], 'carry_eval_success': ev.get('success'),
                               'carried_max_m': ev.get('carried_max_m'), 'funnel': ev.get('funnel'),
                               'reason': ev.get('failure') or ('cap_end' if world['cap_end'] else 'carry_eval_missing'),
                               'blocked_object': 'UNKNOWN:not_observed', 'min_gap_m': None, 'raw': str(raw)})
    assert len(gold) == 15
    case, trace = golden_case(SECOND, 'p3-clockfix-gap-fill-s01-b010-try1', index)
    assert case['seed'] == 8340211
    gold.append(case)
    physical.append({'cohort': case['cohort'], 'seed': case['seed'], **trace})
    with (out/'golden-cases.jsonl').open('w') as handle:
        for case in gold:
            handle.write(json.dumps(case, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
    write(out/'physical-corroboration.json', physical)
    teacher = teacher_rescore(index)
    # Keep the explicit ambiguous-row inventory small and separate from the summary.
    with (out/'teacher-ambiguous.jsonl').open('w') as handle:
        for row in teacher.pop('ambiguous_rows'):
            handle.write(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n')
    teacher['ambiguous_rows_file'] = 'teacher-ambiguous.jsonl'
    rescore = {'schema': 'ugrp.han32.strict_rescore.v1', 'report_only': True,
               'sealed_inputs_modified': False, 'new_physics_runs': 0, 'gpu_hours': 0,
               'teacher': teacher, 'C': student_rescore('C', index), 'S': student_rescore('S', index)}
    write(out/'strict-rescore-20261028.json', rescore)
    stages, previous = [], summary['planned_N']
    for stage, count in funnel.items():
        stages.append({'stage': stage, 'passed_cumulative_N': count, 'rejected_N': previous-count})
        previous = count
    rejection = load(PILOT/'rejection_table.json')
    write(out/'rejection_table.json', {'scope': 'offline teacher-level / HOLD_SCENE / not a gate / new cohort / do not pool',
          'raw': str(PILOT), 'reproduce': [sys.executable, str(Path(__file__).absolute())],
          'original_reproduce': rejection['reproduce'], 'funnel': stages, 'exclusions': exclusions,
          'legacy_batch_success_n': summary['success_n'], 'funnel_valid_n': len(gold)-1,
          'summary_overcount_worlds': [r['world'] for r in exclusions if r['batch_success']],
          'source_rejection_table': str(PILOT/'rejection_table.json'),
          'prior_rejection_table': rejection['reproduce'][rejection['reproduce'].index('--rejection-table')+1]})
    (out/'pilot-reproduce-excerpt.txt').write_text('# HISTORICAL ONLY: do not execute without fresh GPU approval\n' + shlex.join(rejection['reproduce']) + '\n')
    write(out/'artifact-index.json', {'hash_method': 'sha256sum -- <absolute_path>', 'files': index.entries,
          'scope': 'selected local originals, not a backup; original manifests checked for golden carry-eval/result/plan/trace'})
    (out/'artifact-index.sha256').write_text(''.join(f"{v['sha256']}  {p}\n" for p, v in sorted(index.entries.items())))
    print(json.dumps({'golden_pilot': 15, 'independent': 1, 'teacher_legacy': teacher['legacy_success'],
                      'teacher_strict': teacher['strict_success'], 'teacher_proxy': teacher['strict_proxy'],
                      'teacher_ambiguous': teacher['ambiguous_N'], 'C': rescore['C']['strict_success'],
                      'S': rescore['S']['strict_success'], 'indexed_files': len(index.entries)}))


if __name__ == '__main__':
    main()
