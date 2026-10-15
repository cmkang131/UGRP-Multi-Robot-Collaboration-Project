"""Recount pair-teacher originals on GCP; truth is evaluator-only here."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import shlex
import subprocess


def read_bytes(path):
    path = Path(path)
    if not path.exists():
        path = Path(str(path) + '.zst')
    raw = path.read_bytes()
    return (subprocess.check_output(['zstd', '-qdc', str(path)])
            if path.suffix == '.zst' else raw), path, hashlib.sha256(raw).hexdigest()


def read(path):
    raw, _, _ = read_bytes(path)
    return json.loads(raw)


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def longest_hold(rows):
    since = None
    longest = 0.
    for row in rows:
        beam = row['beam']
        both = (beam['min_z'] >= .012 and beam.get('tilt_deg', math.inf) <= 10.
                and all(min(row['contacts'][r]) >= .5 for r in ('r1', 'r2')))
        since = (row['t'] if since is None else since) if both else None
        if since is not None:
            longest = max(longest, row['t'] - since)
    return longest


def ordered_funnel(total, counts):
    rows = []
    entered = total
    for gate, passed in counts:
        if not 0 <= passed <= entered:
            raise ValueError('non-nested funnel: ' + gate)
        rows.append(dict(gate=gate, entered=entered, passed=passed,
                         rejected=entered-passed))
        entered = passed
    return rows


def verify_manifest(raw):
    if not (raw/'manifest.json').exists() and not (raw/'manifest.json.zst').exists():
        return None
    manifest = read(raw/'manifest.json')
    checked = 0
    for name, spec in manifest.items():
        path = raw/name
        data, actual, packed_sha = read_bytes(path)
        if actual == path:
            if packed_sha != spec['sha256']:
                raise ValueError('manifest mismatch: ' + str(path))
        elif hashlib.sha256(data).hexdigest() != spec['sha256']:
            raise ValueError('decoded manifest mismatch: ' + str(path))
        if spec.get('decoded_sha256') and hashlib.sha256(data).hexdigest() != spec['decoded_sha256']:
            raise ValueError('decoded hash mismatch: ' + str(path))
        checked += 1
    return checked


def recount(raw):
    entry = {'raw': str(raw), 'reason_category': 'unfinalized',
             'blocked_object': 'not_recorded', 'min_gap_m': None,
             'gap_scope': 'legacy ledger did not record a geometric blocker'}
    if not (raw/'result.json').exists() and not (raw/'result.json.zst').exists():
        entry.update(status='interrupted', strict_success=False, legacy_success=False)
        return entry
    result = read(raw/'result.json')
    _, actual, digest = read_bytes(raw/'result.json')
    entry.update(result_path=str(actual), result_sha256=digest,
                 status='interrupted' if result['status']=='running' else result['status'],
                 saved_status=result['status'], legacy_success=result.get('physical_success', False),
                 source_sha=result.get('source_sha'), profile=result.get('teacher_profile', 'legacy'),
                 cap_end=result.get('cap_end', False), sim_s=result.get('sim_s'),
                 phases={r:t.get('phase') for r,t in result.get('teachers', {}).items()},
                 outcomes={r:t.get('outcome') for r,t in result.get('teachers', {}).items()},
                 audit=result.get('input_audit'), manifest_verified_files=verify_manifest(raw))
    terminal=[t.get('outcome') for t in result.get('teachers', {}).values()]
    entry['reason_category'] = ('cap_end' if entry['cap_end'] else 'success'
        if entry['legacy_success'] else next((x for x in terminal if x and x != 'success'), result['status']))
    if (raw/'eval-only.jsonl').exists() or (raw/'eval-only.jsonl.zst').exists():
        decoded, path, digest = read_bytes(raw/'eval-only.jsonl')
        rows = [json.loads(line) for line in decoded.splitlines() if line.strip()]
        entry.update(eval_path=str(path), eval_sha256=digest, evaluation_rows=len(rows),
                     max_strict_hold_s=longest_hold(rows))
        plan = read(raw/'plan.json')
        roles = plan['roles']
        entry['assigned_ends'] = roles
        entry['end_relation_samples'] = []
        for i in sorted({0,len(rows)//2,len(rows)-1}):
            row = rows[i]
            nearest={r:min(('teal','blue'),key=lambda e:math.dist(row['robots'][r]['pose'][:2],row['beam']['ends'][e][:2])) for r in roles}
            entry['end_relation_samples'].append({'t':row['t'], 'nearest_ends':nearest,
                'same_nearest_end':len(set(nearest.values()))==1,
                'scope':'evaluator distance only; not inferred intent'})
    entry['strict_success'] = bool(result.get('status')=='complete' and entry.get('max_strict_hold_s', 0.) >= 3.-1e-8)
    entry['visible_eligible'] = bool(entry['strict_success'] and entry['profile']=='visible_only'
        and entry['audit'] and entry['audit'].get('enabled')
        and not entry['audit'].get('invisible_measurements') and not entry['audit'].get('held_world_reads'))
    return entry


def history(root, out):
    cohorts=[]
    for short in ('078cbb45','1f177950'):
        base=root/('native-grasp-teacher-gate-'+short)
        raws=sorted(base.glob('cohort-*/episode-*/raw'))
        entries=[recount(p) for p in raws]
        argv=shlex.split((base/'COMMAND').read_text())
        cap=float(argv[argv.index('--cap-s')+1]) if '--cap-s' in argv else None
        for e in entries:
            if cap is not None and e.get('sim_s') is not None and e['sim_s']>=cap-1e-8:
                e.update(cap_end=True, cap_s=cap, cap_source=str(base/'COMMAND'))
                if not e['legacy_success']:e['reason_category']='cap_end'
        counts=Counter(e['reason_category'] for e in entries)
        complete=sum(e['status']=='complete' for e in entries)
        strict=sum(e['strict_success'] for e in entries if e['status']=='complete')
        cohorts.append({'source_short':short,'raw_root':str(base),'planned_N':40,
            'started_N':len(entries),'complete_N':complete,
            'legacy_success_n':sum(e['legacy_success'] for e in entries),
            'strict_demonstrated_n':strict,
            'failure_N':sum(e['status']=='complete' and not e['legacy_success'] for e in entries),
            'interrupted_N':sum(e['status']=='interrupted' for e in entries),
            'unstarted_N':40-len(entries),'raw_recount_available':bool(entries),
            'reason_distribution':dict(counts), 'runs':entries,
            'funnel':ordered_funnel(40,[('started',len(entries)),('finalized_complete',complete),
                ('strict_joint_hold_3s',strict),('visible_input_eligible',sum(e.get('visible_eligible',False) for e in entries))])})
    report={'schema':'ugrp.beampair1.history.v1','cohorts':cohorts,
        'reproduce':f'python3 -m scripts.audit_beampair1 --history {root} --out {out}',
        'criteria_source':'existing visible_only gate: 12mm, 10deg, bilateral .5N, 3 SIMs; no new tolerance',
        'scope':'GCP script, historical ARM originals copied without changing them; old successes are not current gate success'}
    dump(out/'history.json',report)
    dump(out/'historical-rejection-table.json',{'schema':'ugrp.beampair1.funnel.v1',
        'cohorts':[{k:c[k] for k in ('source_short','raw_root','reason_distribution','funnel')} for c in cohorts],
        'reproduce':report['reproduce']})
    print(json.dumps([{k:v for k,v in c.items() if k not in ('runs','funnel')} for c in cohorts]))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--history',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();history(a.history,a.out)
