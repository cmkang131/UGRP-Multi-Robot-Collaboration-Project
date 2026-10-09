"""Read-only raw replay; independent cuboid-corner judge, never a control input."""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vertices(row):
    r, c, h = row['cyan_rotation'], row['cyan_xyz_m'], row['box_half_m']
    return [[c[i] + sum(r[3*i+j]*sign[j]*h[j] for j in range(3)) for i in range(3)]
            for sign in itertools.product((-1, 1), repeat=3)]


def independent(rows, region):
    if not rows:
        return {'valid': False, 'success': None, 'reason': 'NO_TRAJECTORY'}
    times = [r['t'] for r in rows]
    gaps = [b-a for a,b in zip(times, times[1:])]
    finite = all(math.isfinite(v) for r in rows for k in
                 ('cyan_xyz_m', 'cyan_rotation', 'box_half_m') for v in r[k])
    valid = (finite and all(math.isfinite(t) for t in times)
             and bool(gaps) and min(gaps) > 0 and max(gaps) <= .050001)
    tail = [r for r in rows if r['t'] >= times[-1]-2.-1e-8]
    corner_rows = [vertices(r) for r in tail]
    cx, cy = region['center_m']
    hx, hy = region['half_extents_m']
    inside = all(cx-hx <= v[0] <= cx+hx and cy-hy <= v[1] <= cy+hy
                 for vs in corner_rows for v in vs)
    floor = all(abs(min(v[2] for v in vs)) < .008 and r['cyan_xyz_m'][2] < .04
                for vs,r in zip(corner_rows, tail))
    displacement = max(math.dist(r['cyan_xyz_m'], rows[-1]['cyan_xyz_m']) for r in tail)
    stable = displacement <= .008
    lifted = any(r['cyan_xyz_m'][2] > .06 for r in rows)
    duration = tail[-1]['t']-tail[0]['t']
    success = lifted and inside and floor and stable and duration >= 1.95
    return dict(valid=valid, success=bool(success) if valid else None, lifted=lifted,
                inside=inside, floor=floor, stable=stable, settled_s=duration,
                final_xyz_m=rows[-1]['cyan_xyz_m'], rows=len(rows), max_gap_s=max(gaps, default=None),
                max_tail_displacement_m=displacement)


def audit(path):
    read = lambda name: json.loads((path/name).read_text())
    result, bundle, manifest, student = [read(n) for n in
        ('result.json', 'bundle.json', 'artifacts.sha256.json', 'student_record.json')]
    bad = [n for n,h in manifest.items() if not (path/n).is_file() or sha(path/n) != h]
    rows = [json.loads(line) for line in (path/'eval_only/trajectory.jsonl').read_text().splitlines()]
    static = read('inputs/static_map.json')
    judged = independent(rows, static['regions']['zone_'+bundle['task']['destination']])
    reported = result.get('evaluation', {}).get('success')
    mismatch = (reported != judged['success']) if judged['valid'] and isinstance(reported, bool) else None
    stage = bundle['stage_probe']
    physical_stage = judged['success']
    if stage in ('pick', 'door'):
        physical_stage = judged['valid'] and judged['lifted'] and rows[-1]['cyan_xyz_m'][2] > .06
    if stage == 'door':
        door = next(p for p in static['passages'] if p['id'] == bundle['task']['passage_id'])
        physical_stage = physical_stage and min(v[0] for v in vertices(rows[-1])) > door['center_m'][0]+door['half_extents_m'][0]
    managed_path = Path(str(path)+'-managed')/'manifest.json'
    managed = json.loads(managed_path.read_text())
    record_ok = not bad and judged['valid'] and not managed['source_changed_during_run']
    passed = (record_ok and result['status'] == 'STAGE_REACHED_UNQUALIFIED'
              and physical_stage and mismatch is False and managed['exit_code'] == 0)
    failure = result.get('failure')
    if isinstance(failure, dict):
        failure = failure.get('class', failure.get('type', 'HOST_ERROR'))
    if not failure and not passed:
        failure = ('EVIDENCE_INVALID' if not record_ok else 'JUDGE_MISMATCH' if mismatch is not False
                   else 'NOT_LIFTED' if not judged.get('lifted') else 'PHYSICAL_STAGE_FAILED')
    return dict(source=str(path), source_sha=bundle['source_sha'], task=bundle['task'], stage=stage,
        passed=bool(passed), failure_class=failure, result=result, independent=judged,
        false_positive=bool(mismatch and reported), false_negative=bool(mismatch and not reported),
        stage_false_positive=bool(result.get('stage_reached') and not physical_stage),
        stage_false_negative=bool(not result.get('stage_reached') and physical_stage),
        judge_disagreement=mismatch, artifact_files_checked=len(manifest), artifact_mismatches=bad,
        managed={k:managed[k] for k in ('exit_code','status','runtime_s','source_changed_during_run','finalization_errors')},
        would_stop=student['dev_light_would_stop'],
        state_events=[e for e in student['events'] if e['event']=='state'],
        hashes={n:sha(path/n) for n in ('result.json','bundle.json','artifacts.sha256.json',
                    'student_record.json','eval_only/trajectory.jsonl')},
        managed_manifest_sha256=sha(managed_path))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    data = audit(args.source)
    with args.output.open('x') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print(json.dumps({k:data[k] for k in ('task','stage','passed','failure_class','judge_disagreement',
                                       'artifact_files_checked','would_stop')}, ensure_ascii=False))
