#!/usr/bin/env python3
"""Criterion B v95 오프라인 채점 JSON 1개 -> 파생 뷰(result.json) 4개(지도 x 로봇).
원본 JSON 값만 옮긴다(재계산 없음, v95 raw 미열람). 태그 이름은 v91 뷰(critb-v91-score-tbviews-20261003)와 같다."""
import hashlib, json
from pathlib import Path

OUT = Path(__file__).resolve().parent
SRC = Path('/Users/changmin/projects/ugrp/outputs/criterion-b-v95-score-20261003T170731Z/criterion_B_v95.json')
SRC_SHA = '998bc3d4c32eeae1dae4225c4dbade458dd13c0562a0a21bf3613bfc6052a368'
SCORER = 'f64016dd'  # scripts/score_consumer_criterion_b_v95.py sha256 prefix
CHECKOUT = 'b4cd1336'
MAPS = {'door': 'zone_wide_door_geometry_v3', 'corridor': 'zone_wide_corridor_final_v3'}
LIMITS = ('Offline new-start validation (새 시작점 검증) only; gate/* are declared gate verdicts (1=pass), not robot success. '
          'steps split equals v91/training to <=1e-5 normalized error (10 s signed steps from rest, same levels): not new evidence; '
          'only PRBS phase and world/start-yaw transform are new. yaw steps h3.2 p95=1.9999994 vs limit 2 (r5 sigma fitted to training p95=2). '
          'Exclusion gate is world-frame; body-frame increments can equal training. Both maps share one schedule (not independent). '
          'Original-B rotate/pass null; criterion_A FAILED_NOT_RESCORED; CANDIDATE_UNVALIDATED. No PF/student/physical/loaded claim.')


def axis_scalars(axis, metrics, scalars):
    allnae, allcov, allnees = [], [], []
    for split in ('steps', 'prbs'):
        for h, m in metrics[split].items():
            hk = 'h' + h.replace('.', 'p')
            nae, cov = max(m['normalized_abs_error_p95']), min(m['coverage_2sigma'])
            scalars[f'offline/{axis}/{split}_{hk}_nae_p95_max'] = nae
            scalars[f'offline/{axis}/{split}_{hk}_cov2sigma_min'] = cov
            allnae.append(nae); allcov.append(cov); allnees.append(m['mean_joint_NEES'])
    scalars[f'offline/{axis}/nae_p95_max'] = max(allnae)
    scalars[f'offline/{axis}/cov2sigma_min'] = min(allcov)
    scalars[f'offline/{axis}/mean_joint_nees_max'] = max(allnees)


def main():
    assert hashlib.sha256(SRC.read_bytes()).hexdigest() == SRC_SHA
    d = json.loads(SRC.read_text())
    assert d['scope'] == 'HELD_OUT_VALIDATION' and d['ordering_evidence']['verified'] is True
    add = d['rotation_addendum']
    made = []
    for mk, map_id in MAPS.items():
        for rid in ('r1', 'r2'):
            case = next(c for c in d['cases'] if c['map_id'] == map_id and c['robot_id'] == rid)
            yaw = next(c for c in add['cases'] if c['map_id'] == map_id and c['robot_id'] == rid)
            scalars = {}
            for axis in ('forward', 'left'):
                a = case['axes'][axis]
                axis_scalars(axis, a['metrics'], scalars)
                scalars[f'gate/{axis}_pass'] = int(a['pass'] is True)
            scalars['gate/yaw_scored'] = int(yaw['metrics'] is not None)
            if yaw['metrics'] is not None:
                axis_scalars('yaw', yaw['metrics'], scalars)
                scalars['gate/yaw_pass'] = int(yaw['pass'] is True)
            ok = all(case['axes'][a]['pass'] is True for a in ('forward', 'left'))
            outcome = ('FWD_LEFT_PASS' if ok else 'FWD_LEFT_NOT_PASS') + ('_YAW_PASS' if yaw['pass'] is True else '_YAW_NOT_PASS')
            name = f'{mk}-{rid}'
            hp = [t for t in scalars if t.endswith(('/nae_p95_max', '/cov2sigma_min')) or t.startswith('gate/')]
            view = {
                'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
                'offline_source': {'path': str(SRC), 'sha256': SRC_SHA},
                'offline_scalar_scope': (f'Criterion B v95 HELD-OUT new-start validation, map {map_id}, robot {rid}; '
                                         'r5 rotation addendum PRE_COLLECTION. No robot/PF/physical success.'),
                'offline_source_pointer': (f'cases[map_id={map_id},robot_id={rid}].axes.{{forward,left}}.metrics; '
                                           f'rotation_addendum.cases[map_id={map_id},robot_id={rid}].metrics'),
                'offline_scalars': scalars,
                'model_calls': 0,
                'family': 'criterion_B_v95', 'condition': rid, 'case': mk, 'split': 'HELD_OUT_VALIDATION',
                'scenario': map_id,
                'policy': f'B {d["candidate_sha256"][:8]} + yaw r5',
                'judgment': 'new-start validation; with_rotation_addendum.pass=' + json.dumps(d['with_rotation_addendum']['pass']),
                'belief': f'scorer {SCORER} @ {CHECKOUT}',
                'outcome': outcome, 'source_sha': '2fe14826', 'run_id': SRC_SHA[:8],
                'scope': d['scope'],
                'hparam_metrics': hp,
                'texts': {
                    'notes/verdict': {'axis_pass_original_B': d['axis_pass'], 'pass_original_B': d['pass'],
                                      'with_rotation_addendum': d['with_rotation_addendum'],
                                      'validation_kind': d['validation_kind'],
                                      'cohort_note': 'v95 runs are map-robot (r1/r2 = robot). v91 runs r1/r2 = scoring round, robot r1 only.'},
                    'notes/ordering_evidence': {
                        'commitment': d['ordering_evidence']['commitment']['id'],
                        'gate_record': d['ordering_evidence']['gate_record']['id'],
                        'adapter_comment': d['ordering_evidence']['adapter_comment']['id'],
                        'raw_read_started': d['ordering_evidence']['raw_read_started'],
                        'sources_rehashed': d['ordering_evidence']['sources_rehashed'],
                        'scoring_checkout': d['ordering_evidence']['scoring_checkout'],
                        'kinematic_gate': d['ordering_evidence']['kinematic_gate']['status'],
                        'clock_limit': d['ordering_evidence']['clock_limit'],
                        'scope_note': d['scope_note']},
                    'notes/limits': LIMITS,
                },
                'limits': LIMITS,
            }
            folder = OUT / name
            folder.mkdir(exist_ok=False)
            (folder / 'result.json').write_text(json.dumps(view, indent=1, ensure_ascii=False) + '\n')
            made.append((name, outcome, len(scalars)))
    print(made)


main()
