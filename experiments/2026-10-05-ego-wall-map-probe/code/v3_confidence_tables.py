"""Generate README tables from sealed results, no simulation or estimator calls."""
import json
from pathlib import Path
import v3_confidence_replay as run

CONDITIONS=[('off__dr','DR/off'),('off__rbpf_graph','RBPF+guard+graph, old camera'),
            ('v3_unloaded_extrinsic_v1__rbpf_graph','+v3'),('v3_unloaded_extrinsic_v1__confidence','+v3+confidence')]

def tables():
    cases=[f's{s}' for s in range(1042,1048)]
    records={c:run.load(run.OUT/c/'evaluation/complete-summary.json') for c in cases}
    lines=['### 23.8 현행 v7·카메라 v3 재생 결과','',
           '아래 precision과 recall은 %, 벽 RMSE는 m이다. precision 허용 거리 0.15 m, 전체 벽 표본 **349개**,',
           '점유 기준 log-odds>0를 유지했다. `old camera`는 v3 RGB에 기존 FK+sag 투영을 적용한 비교 조건이며',
           '**구 녹화라는 뜻이 아니다**. 모든 RBPF 행은 100입자+positive-depth+자기 pose graph다.',
           '개발 2건과 확인 재생 4건, 구 녹화와 현행 녹화는 합산하지 않는다.','',
           '| 녹화 | DR/off | RBPF old camera | +v3 | +v3+confidence | GT+v3+guard |',
           '|---|---|---|---|---|---|']
    def cell(m):
        f=m['final']
        if f['precision_015'] is None: return 'NA / 0.0 / NA'
        return f"{100*f['precision_015']:.1f} / {100*f['wall_coverage']:.1f} / {f['wall_error_rmse_m']:.3f}"
    for case,s in records.items():
        name=case+(' 개발' if s['split']=='development' else ' 확인')
        lines.append('|'+name+'|'+'|'.join(cell(s['metrics'][c]) for c,_ in CONDITIONS)+
                     '|'+cell(s['metrics']['v3_unloaded_extrinsic_v1__gt'])+'|')
    lines+=['','관측 탈락 효과를 분리한 v3의 **동일 유효 관측** DR/GT 기준선:','',
            '| 녹화 | v3 DR (P/R/RMSE) | v3 GT+confidence (P/R/RMSE) |',
            '|---|---|---|']
    for case,s in records.items():
        lines.append('|'+case+'|'+cell(s['metrics']['v3_unloaded_extrinsic_v1__dr'])+
                     '|'+cell(s['metrics']['v3_unloaded_extrinsic_v1__gt_confidence'])+'|')
    lines+=['','전체 경로의 종료/중앙/P95/RMSE 위치 오차(m). 종료 위치와 지도 품질은 합산하지 않는다.',
            'v3+confidence는 지도 가중치가 정합에 간접 영향을 준 새 RBPF 실행이다. 구 자료의 고정 자세 삽입 비교와 다르다.','',
            '| 녹화 | 조건 | 종료 | 경로 중앙 | P95 | 경로 RMSE |',
            '|---|---|---|---|---|---|']
    for case,s in records.items():
        for key,label in CONDITIONS:
            m=s['metrics'][key]; p=m['path_position_error']
            lines.append(f"|{case}|{label}|{m['end_position_error_m']:.3f}|{p['median_m']:.3f}|{p['p95_m']:.3f}|{p['rmse_m']:.3f}|")
    lines+=['','§17·§19 원래 7개 기준을 모두 만족한 녹화 수(항목별 값은 각 JSON에 보존):','',
            '| 조건 | 개발 통과 | 확인 재생 통과 |',
            '|---|---|---|']
    for key,label in CONDITIONS[1:]:
        a=sum(records[c]['section17_19_success'][key] for c in cases[:2])
        b=sum(records[c]['section17_19_success'][key] for c in cases[2:])
        lines.append(f'|{label}|{a}/2|{b}/4|')
    lines+=['','실제 camera-pose GT가 없어서 **가시 recall 기준은 전 건 NA/검증 미달**이다. 따라서 이를 포함한',
            '전체 성공으로 판정할 수 없다. 비양수 깊이/광선 끝점은 전 조건 0이며 off 골든은 시험으로 확인했다.',
            '하중/미등록/정착 관측을 탈락시켜 분모를 바꾸지 않았으며 전체 경로의 끝까지 DR을 계속했다.','',
            '### 23.9 삽입·정합·관측 제한','',
            '| 녹화 | 전체 RGB | 검사 tick | 무하중 보정 | 하중 미지원 | 정착 보류 | 유효 벽 프레임 |',
            '|---|---|---|---|---|---|---|']
    for case in cases:
        s=run.load(run.OUT/case/'v3_unloaded_extrinsic_v1/extract-summary.json'); c=s['counts']
        lines.append(f"|{case}|{s['frames']}|{sum(c.values())}|{c.get('calibrated_unloaded',0)}|{c.get('loaded_or_unknown_load_not_calibrated',0)}|{c.get('unsettled',0)}|{s['contacts']}|")
    lines+=['','루프 표의 각 칸은 **수락 / 실제 정합 거부**다. 회원 scan·시간 인접 제외는 실제 거부에 합산하지 않고',
            '각 prediction JSON에 이유별 횟수를 보존했다. 수락은 참 루프를 GT로 입증한 수가 아니다.','',
            '| 녹화 | old camera | +v3 | +v3+confidence |',
            '|---|---|---|---|']
    for case,s in records.items():
        values=[]
        for key,_ in CONDITIONS[1:]:
            counts=s['metrics'][key]['loop_counts']
            rejected=sum(n for k,n in counts.items() if k not in ('accepted','member_scan','temporal_separation'))
            values.append(f"{counts.get('accepted',0)} / {rejected}")
        lines.append('|'+case+'|'+'|'.join(values)+'|')
    lines+=['','RBPF frontend 수락·보류·거부는 loop closure와 다른 사건이다. `frontend_counts`와 각 scan/입자의',
            '`frontend-decisions.jsonl`에 이유·자세·삽입 여부를 보존했다. 전체 graph 후보의 진단도 로컬에 보존했다.',
            'confidence를 적용하면 옅은 지도 셀이 기존 graph의 확률 gate에 걸릴 수 있다. 기존 gate를 완화해',
            '성공률을 맞추지 않았고, 가중 삽입이 위치 개선을 자동으로 보장한다고 해석하지 않는다.','',
            '![구 녹화: GT 벽·추정 지도·경로](results/v3_confidence_v1/old-topdown.png)','',
            '![현행 녹화: GT 벽·신뢰도 가중 지도·경로](results/v3_confidence_v1/current-topdown.png)','',
            '![신뢰도별 precision: 구/현행 및 GT/추정 자세 분리](results/v3_confidence_v1/confidence-calibration.png)','',
            '곡선은 5개 사전 고정 신뢰도 구간의 0.05 m 선분 표본 precision이다. 반복 프레임을 독립 벽으로',
            '세지 않으며 각 bin의 검출/표본 수는 [calibration-curves.json](results/v3_confidence_v1/calibration-curves.json)에 있다.',
            '빈 bin은 NA다. evidence weight가 정답 확률로 보정됐다는 증거가 아니며 곡선으로 계수를 다시 맞추지 않았다.','']
    path=run.OUT/'verification/readme-result-tables.md'
    if path.exists(): raise FileExistsError(path)
    path.write_text('\n'.join(lines))
    print(path)

if __name__=='__main__': tables()
