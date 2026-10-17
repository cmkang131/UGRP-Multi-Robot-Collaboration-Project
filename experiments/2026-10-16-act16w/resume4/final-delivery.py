"""Finite, owned-L4 postprocessing of the existing final40; never submits physics."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import time

B = Path('/home/ugrp/ugrp-sim')
R = B / 'runs/act16w-native-experiment-r1'
S = B / 'src/34d53cfaadc093ac957bbfffc780a76f372041f9'
Q = B / 'src/f0db6b1abb842ea65b71c433738210254f300a7c'
W = B / 'runs/simalt3/warp-env/bin/python'
A = Path('/home/ugrp/ugrp-rl1b-act-env/bin/python')
E = R / 'final40'
LEASE = B / 'leases/act16w-final-delivery.json'
ENV = {**os.environ, 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
       'LP_NUM_THREADS': '1', 'MUJOCO_GL': 'osmesa', 'PYTHONDONTWRITEBYTECODE': '1'}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, python=W):
    subprocess.run([str(python), str(S / 'scripts' / args[0]), *map(str, args[1:])],
                   cwd=Q, env=ENV, check=True)


def status(stage, **extra):
    data = dict(stage=stage, utc=datetime.now(timezone.utc).isoformat(),
                physics_steps=0, model_calls=0, script_sha256=sha(Path(__file__)), **extra)
    (R / 'final-delivery-status.json').write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(data), flush=True)


with LEASE.open('x') as stream:
    json.dump(dict(task='act16w-final-delivery', pid=os.getpid(),
                   start_utc=datetime.now(timezone.utc).isoformat(), concurrency=0,
                   expected_end='existing final40 followed by finite saved-state analyses; no wall cap'), stream)
try:
    status('waiting_existing_final40')
    while not ((E / 'summary.json').exists() and read(E / 'summary.json').get('complete')):
        if read(R / 'summary.json')['status'] in ('HOST_ERROR', 'SUPERVISOR_STOP', 'FINAL40_INCOMPLETE'):
            raise RuntimeError('existing controller stopped; no retries or duplicate submission')
        time.sleep(10)
    run(['audit_act16w_native_student.py', '--evaluation', E,
         '--out', R / 'independent-final40.json'], python=A)
    recount = read(R / 'independent-final40.json')
    assert recount['N'] == 40 and recount['raw_recomputed_metrics_match_original']
    assert sorted(row['seed'] for row in recount['rows']) == list(range(91620, 91660))
    assert all(row['N'] == 10 for row in recount['kinds'].values())
    rows = []
    for group in sorted(E.glob('group-*')):
        for index, plan in enumerate(read(group / 'plans.json')['episodes']):
            seed = plan['seed']
            world = group / f'evaluation/owner/world-{index:03d}'
            alignment = R / f'alignment-final-{seed}.json'
            run(['audit_act16w_alignment.py', '--enabled', '--world-root', world,
                 '--actions', group / 'evaluation/actor-actions.jsonl', '--action-format',
                 'student', '--world-index', str(index), '--out', alignment])
            gaps = R / f'gaps-final-{seed}.json'
            run(['audit_act16w_saved_gaps.py', '--enabled', '--world-root', world,
                 '--references', R / 'final40-references/per-world-references.json', '--out', gaps])
            rows.append(dict(seed=seed, kind=plan['kind'], world=str(world), world_index=index,
                             alignment_rejection=read(alignment)['alignment_rejection'],
                             alignment=dict(path=str(alignment), sha256=sha(alignment)),
                             closest=read(gaps)['closest']['non_floor_external'],
                             gap_report=dict(path=str(gaps), sha256=sha(gaps))))
            status('saved_geometry', completed=len(rows), requested=40)
    assert len(rows) == 40
    geometry = R / 'final40-geometry-summary.json'
    geometry.write_text(json.dumps(dict(complete=True, N=40, rows=rows,
        alignment_rejections=sum(row['alignment_rejection'] for row in rows),
        physics_steps=0, scope='saved MJWarp poses/exact geometry; no GPU force, blocker causality or C physics run'), indent=2) + '\n')
    original = E / 'rejection_table.json'
    table = read(original)
    by_seed = {row['seed']: row for row in rows}
    for row in table['rejections']:
        data = by_seed[row['seed']]
        closest = data['closest']
        row.update(blocking_object='not_attributed_no_blockage_causality_claim',
                   nearest_non_floor_object=closest['external_geom'], minimum_gap_m=closest['gap_m'],
                   minimum_gap_elapsed_SIM_s=closest['elapsed_SIM_s'],
                   minimum_gap_status='saved poses/exact compiled geometry; not GPU force or proven blocker',
                   gap_report=data['gap_report'])
    table.update(original_table=dict(path=str(original), sha256=sha(original)),
                 post_action_supplement=dict(path=str(geometry), sha256=sha(geometry), original_unchanged=True),
                 independent_stage_counts=recount['independent_stage_counts'])
    (R / 'rejection-table-final40-enriched.json').write_text(json.dumps(table, indent=2) + '\n')
    failures = sorted((row for row in recount['rows'] if not row['task_success']), key=lambda row: row['seed'])
    chosen = []
    for row in failures:
        if not chosen or row['kind'] != chosen[0]['kind']:
            chosen.append(row)
        if len(chosen) == 2:
            break
    if len(chosen) < 2:
        chosen += [row for row in failures if row not in chosen][:2 - len(chosen)]
    successes = sorted((row for row in recount['rows'] if row['task_success']), key=lambda row: row['seed'])
    chosen += successes[:1]
    playback = []
    for row in chosen:
        world = Path(row['raw_world'])
        out = B / f'runs/act16w-native-final-playback-{row["seed"]}'
        run(['act16w_playback.py', '--run', world.parent, '--world', str(int(world.name.split('-')[-1])), '--out', out])
        playback.append(dict(seed=row['seed'], kind=row['kind'], student_success=row['task_success'],
                             out=str(out), metadata_sha256=sha(out / 'playback-meta.json')))
    (R / 'final40-playback-selection.json').write_text(json.dumps(dict(
        rule='lowest failed seed, then lowest failed seed of different kind; lowest successful seed if available',
        rows=playback, actual_student_success_examples=len(successes[:1]),
        teacher_reference_if_no_student_success='act16w-native-playback-teacher-87429; never student success'), indent=2) + '\n')
    status('complete', n=recount['n'], N=40, playback=playback, direct_review_pending=True)
except BaseException as error:
    status('ANALYSIS_ERROR', error=repr(error), complete=False)
    raise
finally:
    if LEASE.exists() and read(LEASE)['pid'] == os.getpid():
        LEASE.unlink()
