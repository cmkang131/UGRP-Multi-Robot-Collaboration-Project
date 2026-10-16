# ACT11 — 초기 시선 훑기·중단 감사·선택 회전 보정

기준 act10 `567dc120`, 고정 교사 `6f057f7e`, PR #504. 물리·렌더·학습·원격 접속 없이
코드·저장 원장만 검증했다. 새 동작은 `recovery_active_search_v1` 안에서만 동작하고,
추가 회전 보정 `--rotation-calibration act8_yaw_gain_v1`은 기본 OFF다.

- 마지막 목격 시각이 없으면 부모의 초기 시선 훑기를 유지한다. 고정 교사 실제 클래스에
  +24°/−24.8°의 초기 미관측을 공급해 12초 훑기와 4.3초 뒤 가시 재개를 각각 검사했다.
  RGB/FOV를 렌더해 처음 안 보이는지 새로 측정한 시험은 아니다.
- 어댑터는 첫 SIGINT 또는 감독 마커의 KeyboardInterrupt 생성부터 추가 SIGINT를 무시한다.
  실제 InputAudit 객체를 붙잡아 finally에서 terminal result와 감사를 원자적으로 저장한다.
  기존 except writer 오류·부분 원장도 검사했고, 미생성 감사는 0으로 꾸미지 않는다.
  작업 밖 운영 도구는 수정하지 않았다:
  `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act9-ec0bd628-ops/stop_owned.py`
  (act10-567dc120-ops에도 같은 이름의 도구가 있다).
- 회전 계수 **0.6790684337506349**는 act8의 근거리·비파지·순수 제자리 회전 **12틱**만으로
  절편 없는 최소제곱으로 맞췄다. act9/10은 계수 계산에서 제외했다. 사용자 검토의 233틱과
  다른 엄격한 영(0) 병진 필터이며 작은 보정 표본의 한계가 있다. 적용은 탐색의 기억 적분·
  방향 복귀 펄스·1회전 추정에 한정한다. 부모 접근/정렬 경로는 바꾸지 않는다.
- 탐색 기억의 나이 5.2초 상한은 채택하지 않았다. 부모의 접근 기억은 여전히 5.2초다.
  별도 탐색 기억은 병진/집기 입력으로 반환하지 않고, 8.1초 팬 훑기와 몸 회전에만 쓴다.
  탐색 시작부터 24초 또는 추정 360°에서 실패하고, 재관측·파지·비근거리 단계에서 초기화한다.
  `memory_age_s`를 기록한다. 5.2초 만료는 팬 훑기도 끝내기 전에 실패시키므로 별도 설계가 필요하다.

## 확인한 결과

관련 pytest **104 passed**, 단일 프로세스. 실제 고정 runner를 world 생성 직전에 차단해
신호/마커×중복 SIGINT×writer 오류×부분 원장을 검사했다. 물리·렌더 진입점도 차단했다.
탐색 OFF 저장 재생은 8316900/01/02 **507/487/607틱**, 명령·원장 완전 일치다.

| 저장 입력의 비가시 방위 오차 | 틱 | OFF 중앙/p95/최대 ° | ON 중앙/p95/최대 ° |
|---|---:|---:|---:|
| 검토와 같은 act9 15실행(8316900–14) | 2,128 | 11.214/13.070/16.096 | 5.879/7.131/7.585 |
| 로컬에 있는 act9 전체 17실행 | 2,164 | 11.212/13.066/16.096 | 5.843/7.119/7.585 |
| act10 첫 2실행 | 24 | 5.301/12.037/14.141 | 3.804/6.502/6.704 |

act10 8317000/01의 순수 회전 구간 절대 회전 합은 실제 **93.636°/87.646°**,
명목 **130.518°/122.361°**, 보정 추정 **88.631°/83.091°**다(각 16/15틱).
기존 결과의 성공은 각각 true이며 새 실행 성공으로 세지 않는다. 영상은 이번에 새로 판독하지 않았다.
act8에는 이 필터의 비가시 오차 표본이 없었다. act9 중단/running 원본을 완료로 바꾸지 않았다.
정답은 계수 산출·오차 평가에서만 읽고 예측기는 가시 상대 측정·발행 명령만 받는다.

[원장·해시·실행별 값](act11-offline.json), [시험 기록](act11-verification.json),
[계획](act11-gate-plan.json), [시드 중복 검사](act11-seed-inventory.json).
새 8317100–39를 두 후보가 같은 순서로 사용한다. 첫 2개는 **8317100/8317116**이며
후자는 시작 방위 **+21.544°**다. 큐는 `outputs/e2e18-admin/vm3-queue/20261015-act11-<sha8>.json`.
각 후보가 독립적으로 ≥38/40 및 회복 장면이 있는 성공 ≥20을 만족해야 하며 합산하지 않는다.
training_rgb OFF, 승인/준비/제출/실행/자동 승격 false, 행별 approved=false다.
원격 미사용 확인·첫2/첫30 검토·새 GCP 관문은 남아 있다.

## 재현

```sh
export PYTHONDONTWRITEBYTECODE=1
ACT_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
$ACT_PY -m pytest -q tests/test_grasp_act_act{11,10,9,8,7,6}.py tests/test_grasp_act_data.py
$ACT_PY -m scripts.audit_grasp_act_act11 --runs-root /Users/changmin/projects/ugrp/outputs/gcp1-runs --output /tmp/act11-fresh-replay
$ACT_PY -m scripts.queue_grasp_act_act11 --prepare --dependency-root /Users/changmin/projects/ugrp-wt/solo-teacher --evidence /tmp/act11-fresh-replay/summary.json --output-dir /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue
# prepare 변경을 커밋한 clean worktree에서만 실행하며, 기존 큐는 덮어쓰지 않는다.
$ACT_PY -m scripts.queue_grasp_act_act11 --output-dir /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue
```

## 참고 자료

- [Borenstein & Feng, 1996, UMBmark / systematic odometry correction](https://web.cecs.pdx.edu/~mperkows/CLASS_479/S2006/Paper-correction-odometry-error.pdf):
  원문 p.869 초록·p.873 §III.B의 차동 구동 휠 지름/축간 거리와 양방향 정사각형 시험을 확인했다.
  반복 측정으로 계수를 산출해 오차를 줄이는 근거다. 본 작업은 메카넘의 발행 명령 회전
  1계수를 저장 원장으로 맞춘 것으로 UMBmark 시험이나 실물 오도메트리 보정 재현이 아니다.
- [Python signal](https://docs.python.org/3/library/signal.html): SIG_IGN과 이전 처리기 복구를 사용한다.
  원자 교체는 기존 프로젝트 write_json 및 압축 결과의 임시 파일→replace 경로를 따른다.
