"""Reproducible search19 tables, local evidence verification and finite sweeps."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts.replay_grasp_act_search19 import read, KW, BASE
from sim.grasp_act_search19 import BodyNavigation, body_fallback
import sim.grasp_act_search19 as s19
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    summary = json.loads((a.replay/'summary.json').read_text())
    failures = []
    verification = {'verified': [], 'missing': [], 'mismatch': []}
    candidate_rows, evaluation = [], []
    sweep = []
    relationships = {
        315709: '배정 r1 파랑/r2 청록. 실제 최근접 끝은 두 대 모두 청록(처음·중간·끝). r1은 파랑을 바라보며 접근하나 상대 여유 경계에서 정지.',
        8311709: '배정 r1 파랑/r2 청록, 실제 최근접 끝은 둘 다 청록. r2 청록 끝 대기. r1의 직접 후보 거부는 tile 판정.',
        8311711: '초기 맞교환 배치 후 각자 배정 끝으로 이동. 후반 r2의 상대 기억이 남아 대기 시한 종료.',
        8311723: '배정 r1 파랑/r2 청록, 실제 최근접 끝은 r1 청록/r2 파랑(맞교환 배치 유지). r1 배정 자리의 can 겹침이 직접 원인.'}
    for item in summary['runs']:
        run = json.loads(read(a.replay/f"{item['seed']}.json"))
        raw = Path(run['raw'])
        manifest = json.loads((raw/'manifest.json').read_text())
        for name, digest in run['sha256'].items():
            entry = manifest.get(name) or manifest.get(name+'.zst')
            if entry is None:
                verification['missing'].append(str(raw/name)+' (manifest entry)')
                continue
            expected = entry.get('decoded_sha256', entry['sha256'])
            target = 'verified' if digest == expected else 'mismatch'
            verification[target].append(str(raw/name))
        if run['original_success']:
            continue
        ev = [json.loads(x) for x in read(raw/'eval-only.jsonl').splitlines()]
        plan = json.loads(read(raw/'plan.json'))
        for fraction in (0, .5, 1):
            row = ev[round((len(ev)-1)*fraction)]
            distances = {}
            for rid, end in plan['roles'].items():
                ds = {e: math.dist(row['robots'][rid]['pose'][:2], q[:2]) for e, q in row['beam']['ends'].items()}
                distances[rid] = {'assigned': end, 'nearest': min(ds, key=ds.get), 'distances_m': ds}
            evaluation.append({'seed': item['seed'], 'sim_s': row['t']-ev[0]['t'],
                               'scope': 'evaluator truth ONLY; never controller input', 'robots': distances})
        if item['seed'] == 8311711:
            x = [x for x in run['trace'] if x['rid']=='r2'][-1]
            row = min(ev, key=lambda e: abs(e['t']-x['world']['t']))
            own, ghost, true_own = x['pose'], x['world']['robots']['r1']['pose'], row['robots']['r2']['pose']
            c, s = math.cos(own[2]), math.sin(own[2])
            dx, dy = ghost[0]-own[0], ghost[1]-own[1]
            lx, ly = c*dx+s*dy, -s*dx+c*dy
            c, s = math.cos(true_own[2]), math.sin(true_own[2])
            predicted = (true_own[0]+c*lx-s*ly, true_own[1]+s*lx+c*ly)
            end = row['beam']['ends']['teal']; yaw = row['beam']['pose'][2]
            goal = (end[0]-.203*math.cos(yaw), end[1]-.203*math.sin(yaw))
            evaluation.append({'seed': item['seed'], 'sim_s': x['sim_s'], 'scope': 'evaluator truth ONLY',
                               'stale_peer_position_error_m': math.dist(predicted, row['robots']['r1']['pose'][:2]),
                               'true_peer_to_true_nominal_goal_m': math.dist(row['robots']['r1']['pose'][:2], goal),
                               'current_peer_visible': 'r1' in x['world']['visibility']['r2']['peers']})
        frame_rows = []
        for view in ('eval-overview', 'eval-own/r1', 'eval-own/r2'):
            frames = sorted((raw/view).glob('*.jpg'))
            for f in frames:
                digest = hashlib.sha256(f.read_bytes()).hexdigest()
                entry = manifest.get(str(f.relative_to(raw)))
                target = 'verified' if entry and entry['sha256'] == digest else 'mismatch'
                verification[target].append(str(f))
                frame_rows.append({'path': str(f), 'sha256': digest, 'sim_s': int(f.stem)/10})
            assert len(frames) >= 6, (raw, view, len(frames))
        failures.append({'seed': item['seed'], 'relationship_review': relationships[item['seed']],
                         'frames': frame_rows, 'decisions': len(run['decisions']),
                         'reasons': dict(Counter(c['reason'] for d in run['decisions'] for c in d['candidates'])),
                         'variants': run['variants']})
        for decision in run['decisions']:
            for ordinal, row in enumerate(decision['candidates']):
                candidate_rows.append({'seed': item['seed'], 'rid': decision['rid'], 'sim_s': decision['sim_s'],
                                       'ordinal': ordinal, **{k: row.get(k) for k in
                                       ('offset_deg', 'distance_m', 'reason', 'nearest', 'disc_gap_mm', 'body_gap_mm')}})
        if item['seed'] in (8311709, 8311723):
            decision = run['decisions'][0]
            for mm in (0, 5, 10, 15, 30, 45, 65):
                t = VisibleOnlyGraspTeacher('r1', 'blue', decision['pwm'], **KW, **BASE)
                t.folded_ready = True
                try:
                    s19.BODY_MARGIN_M = mm/1000
                    best, checked = body_fallback(t, decision['world'], decision['world']['t'])
                    sweep.append({'seed': item['seed'], 'margin_mm': mm,
                                  'selected': None if best is None else {k: v for k, v in best.items() if k!='path'},
                                  'feasible': sum(c['reason']=='feasible' for c in checked),
                                  'reasons': dict(Counter(c['reason'] for c in checked))})
                finally:
                    s19.BODY_MARGIN_M = .005
    fields = ('seed', 'rid', 'sim_s', 'ordinal', 'offset_deg', 'distance_m', 'reason',
              'nearest', 'disc_gap_mm', 'body_gap_mm')
    with (a.out/'candidate-clearance.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidate_rows)
    write(a.out/'local-verification.json', verification)
    assert not verification['mismatch'], verification['mismatch']
    write(a.out/'candidate-margin-sweep.json', sweep)
    write(a.out/'failure-review.json', failures)
    write(a.out/'relationship-eval-only.json', evaluation)
    write(a.out/'summary.json', {**summary, 'failures': failures,
                                'candidate_table': str(a.out/'candidate-clearance.csv'),
                                'verification_counts': {k: len(v) for k, v in verification.items()}})
    lines = ['# search19 저장 입력 분석', '',
             f"기준 search18 00620d7a, {len(summary['runs'])} 실행·{summary['robot_ticks']} 로봇 틱, 기준 불일치 {summary['baseline_mismatch_ticks']}.",
             '한 틱 동일 상태 분기이며 실제 성공 재측정이 아니다. 제어에는 visible_measurements와 저장 발행 명령만 사용했다.', '',
             '| 실패 | 로봇 관계 | 판정 변화 틱 |', '|---|---|---|']
    for row in failures:
        lines.append(f"| {row['seed']} | {row['relationship_review']} | {row['variants']['search19']['changed']} |")
    lines += ['', '## 6초 종료의 첫 계획: 후보별 거부·여유 mm', '',
              '전체 반복/중복 후보는 candidate-clearance.csv. 아래는 첫 계획의 고유 (각도, 거리, 이유)다. body gap은 차체와 관측 장애물 사이 유클리드 거리이며 음수는 원형 장애물과 겹침이다.', '',
              '| 시드 | 각도 ° | 거리 mm | 거부 이유 | 최근접 | 원판 여유 mm | 차체 여유 mm |',
              '|---|---:|---:|---|---|---:|---:|']
    for seed in (8311709, 8311723):
        rows = [r for r in candidate_rows if r['seed']==seed]
        first = min(r['sim_s'] for r in rows)
        seen = set()
        for r in rows:
            key = (r['offset_deg'], r['distance_m'], r['reason'])
            if r['sim_s'] != first or key in seen:
                continue
            seen.add(key)
            lines.append(f"| {seed} | {r['offset_deg']:.1f} | {1000*r['distance_m']:.0f} | {r['reason']} | {r['nearest']} | {r['disc_gap_mm']:.2f} | {r['body_gap_mm']:.2f} |")
    lines += ['', '## 마진 스윕', '', '| mm | 성공 12건 중 저장 이동 추가 차단 | 8311709 전체 검사 통과 후보 | 8311723 |', '|---:|---:|---:|---:|']
    for mm, count in summary['body_margin_sweep_success_runs_rejecting_recorded_motion'].items():
        n = [next(s for s in sweep if s['seed']==seed and s['margin_mm']==int(mm))['feasible'] for seed in (8311709,8311723)]
        lines.append(f'| {mm} | {count}/12 | {n[0]} | {n[1]} |')
    lines += ['', '5mm는 기하 패딩이며 위치 오차의 보증이 아니다. 기존 계획이 가능한 성공 입력은 fallback을 활성화하지 않는다. 새 동작 뒤의 궤적·충돌·들기와 40회 교사 관문은 미측정이다.', '',
              '## 참고 자료', '',
              '- Fox, Burgard, Thrun (1997), DWA 저자 초록: https://www.cs.cmu.edu/~dfox/abstracts/colli-ieee.abstract.html — 속도 공간에서 허용 명령을 고르는 원칙만 참조; 동역학/제동 보증 구현 아님.',
              '- Nav2 footprintCostAtPose 공개 코드 본문: https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_costmap_2d/src/footprint_collision_checker.cpp — 자세에 따라 footprint를 변환하는 검사 참조. 전체 planner 재현 아님.',
              '- Daniel et al., Theta* (JAIR 2010), 저자·초록·서지 확인: https://arxiv.org/abs/1401.3843 — 격자의 방향 제약 참고. 이번 두 6초 실패는 A* 전 목표 거부라 격자 해상도 변경을 하지 않았다.']
    (a.out/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'verified': len(verification['verified']), 'missing': len(verification['missing']),
                      'mismatch': len(verification['mismatch']), 'candidate_rows': len(candidate_rows)}))


if __name__ == '__main__':
    main()
