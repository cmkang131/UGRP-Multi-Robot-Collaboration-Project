"""Read completed heading cohort only; no simulation or control inputs."""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path('/Users/changmin/projects/ugrp-wt/s2-heading')
sys.path.insert(0, str(ROOT))
from scripts.evaluate_s2_heading import score, video
from scripts.tensorboard_tools.export import convert

BASE = Path('/Users/changmin/projects/ugrp/outputs')
OUT = BASE / 's2-heading-b60acdca-cohort'
TB = BASE / 'tensorboard/1009-s2-heading-dev'
SEEDS = (1066, 1068, 1065)

def write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

rows = json.loads((OUT / 'runs.json').read_text())
assert [r['seed'] for r in rows] == list(SEEDS), 'cohort not complete'
assert all((Path(r['raw']) / 'result.json').is_file() for r in rows)
assert not TB.exists(), 'preserve existing snapshot'
reports = {}
for seed in SEEDS:
    raw = BASE / f's2-heading-b60acdca-s{seed}-v143'
    p = OUT / f's{seed}-heading.json'
    report = score(raw)
    assert report['source_sha'] == 'b60acdca6e1c0c477d650b47717b84edb3f08a06'
    write(p, report)
    if seed == 1066:
        video(raw, raw / 'motion.mp4')
    reports[(seed, 'heading')] = (p, report)
    p0 = ROOT / f'experiments/2026-10-09-s2-heading/baseline-s{seed}.json'
    reports[(seed, 'baseline')] = (p0, json.loads(p0.read_text()))

comparison = []
manifests = []
for seed in SEEDS:
    for condition in ('baseline', 'heading'):
        p, r = reports[(seed, condition)]
        angles = r['carry_angles']
        metrics = {
            'offline/lateral_fraction': r['commands']['lateral_fraction_moving'],
            'offline/direction_within_20deg_fraction': r['motion']['direction_within_20deg_fraction'],
            'offline/lateral_speed_fraction': r['motion']['lateral_speed_fraction'],
            'offline/robot_contact_s': r['robot_contacts']['sampled_s'],
            'offline/robot_contact_episodes': r['robot_contacts']['episodes'],
            'offline/lateral_s': r['commands']['lateral_s'],
            'offline/moving_s': r['commands']['moving_s'],
            'offline/wall_contact_s': r['wall_contacts']['any']['sampled_s'],
            'offline/wall_contact_episodes': r['wall_contacts']['any']['episodes'],
            'offline/robot_door_center_passed': int(r['door']['robot']['passed_center']),
            'offline/cargo_door_center_passed': int(r['door']['cargo']['passed_center']),
            'offline/wall_per_sim': r['wall_per_sim'],
            'offline/active_90deg_exceeded': int(r['active_actual_90deg_exceeded']),
        }
        if angles:
            metrics['offline/carry_box_yaw_range_deg'] = max(a['box_yaw_range_deg'] for a in angles)
            metrics['offline/carry_relative_yaw_range_deg'] = max(a['relative_box_robot_yaw_range_deg'] for a in angles)
        viewdir = OUT / 'views' / f's{seed}-{condition}'
        view = dict(schema='ugrp.heading_comparison_view.v1', derived_view_only=True,
            policy='v141 off' if condition == 'baseline' else 'v143 path_tangent_v1',
            case=f'seed{seed}', seed=seed, condition=condition, source_sha=r['source_sha'],
            success=r['success'], wall_s=r['wall_s'], sim_s=r['sim_s'],
            commands=r['commands_issued'], model_calls=r['model_calls'],
            scope='Matched existing-seed DEV simulated plant; no fresh confirmation or hardware claim',
            limits='Door metric is center crossing only. Baseline1068 concurrent vs candidate serial. Carry angle absent when no carry.',
            offline_scalar_scope='Post-run command duration, sampled evaluation trajectory and contact metrics; evaluation never fed to controller',
            offline_source=dict(path=str(p), sha256=digest(p)),
            offline_scalars=metrics, evaluation=r['evaluation'])
        write(viewdir / 'result.json', view)
        if condition == 'heading' and seed == 1066:
            os.link(Path(r['raw']) / 'motion.mp4', viewdir / 'motion.mp4')
        m = convert(viewdir, TB / f's{seed}-{condition}', max_images=0)
        manifests.append(dict(run=f's{seed}-{condition}', metrics={
            **metrics, 'evaluation/reported_success': int(r['success']),
            'result/wall_s':r['wall_s'], 'result/sim_s':r['sim_s'],
            'result/commands':r['commands_issued'], 'result/model_calls':r['model_calls']},
            videos=m['videos']))
        comparison.append(dict(seed=seed, condition=condition, success=r['success'],
            status=r['status'], failure=r['failure'], **metrics))

write(OUT / 'comparison.json', dict(rows=comparison, tensorboard=str(TB),
    success_baseline=sum(reports[(s,'baseline')][1]['success'] for s in SEEDS),
    success_heading=sum(reports[(s,'heading')][1]['success'] for s in SEEDS),
    no_new_confirmation=True, hardware_test=False))
write(OUT / 'tensorboard-expected.json', manifests)
print(json.dumps(dict(completed=True, snapshot=str(TB), reports=len(reports), videos=1)))
