# ACT10 — 명령 이력으로 방향 복귀 후 넓혀 찾는 회복 교사

기준 `a7e269e7`(act9 `ec0bd628` + actgpu1), 교사 의존성 `6f057f7e`, PR #504.
새 기본 OFF 모드 `recovery_active_search_v1`만 변경한다. 학생 대체 제어기는 아니다.
관문 재측정을 위한 코드·비활성 큐 준비이며 새 물리 성공·RGB 기록·학습은 없다.

- 마지막 가시 상대 위치를 실제 발행 명령(교란 포함)으로 10 Hz 적분한다.
  이 기억은 방향 탐색 전용이고, 현재 보이지 않는 대상으로 접근/정렬하지 않는다.
  재획득하면 원래 교사의 접근을 계속한다. 잡기 시작/비근거리 단계에서 기억을 지운다.
- 예상 방향으로 제자리 회전(최대 3초) → 거리별 기존 카메라 FK로 틸트 선택 +
  팬 500–2500 훑기(8.1초) → 팬을 유지하며 몸 회전(명령 추정 최대 360°).
  탐색 전체 상한 24초/1회전 완료 시 `recovery_search_exhausted`로 실패한다.
  속도 모델은 기존 65 mm/150 rpm 명령 모델이며 실제 주행계/측정 관절이 아니다.
- act9의 .35 duty × .1초 × 9틱 교란/라벨 제외는 유지한다. 교사 입력은 허용된
  가시 상대 측정·자기 명령뿐이며 정답/잡은 화물 세계 좌표를 탐색에 전달하지 않는다.
  새 모드도 녹화 후 교란 라벨·원장 대조와 청크 경계 검증을 받는다.
- 검토 지적: 손실 시작은 교란 중 또는 마지막 교란 틱 뒤 1초 이내만 귀속한다.
  이미 시작한 손실의 늦은 재획득은 센다. 판정기는 해시로 묶은 큐의 40개 시드와
  결과 시드·`fresh_seeds`를 모두 대조한다. 새 모드도 ≥38/40 성공 및 회복 장면이
  있는 성공 ≥20개가 필요하다. 동시 수는 실측 n4-highcpu-64 상한 40과 남은 승인
  슬롯 중 작은 값이며 첫30 검토 후 채운다. 과거 저장 큐는 수정하지 않았다.

## 확인한 증거와 범위

8316902 own+top 0/12/24/36/48/60초의 6쌍을 직접 확인했다. 12초부터 자기 영상은
바닥이며 상자가 보이지 않고, top에서는 몸 방향이 거의 그대로다. 원장에서도 시야
손실 이후 교란이 끝난 뒤 바퀴 명령은 정지다. 결과 SHA-256
`966914e8699d2666bcc5ad92b6054c5ff7968f132435764ae75c6cb41bb4479f`.

[재생 요약·원본/추적 경로와 해시](act10-offline.json): 8316902 비가시 575틱의
방향 각도 오차 중앙값 **7.9681° / p95 8.8278° / 최대 9.9494°**(4.5–61.9초).
마지막 가시 측정은 4.4초, 거리 .6954 m다. 예상 방향 계산이 끝난 후에만 별도 평가기가
평가 원장의 화물·차체 좌표/차체 yaw로 각도 오차를 계산했다. 보이지 않는 실제 위치는
예상 방향 계산에 쓰지 않았다. 바퀴 미끄럼·관성·마찰 오차가 남으므로 정확한 위치가 아니다.

새 탐색을 끈 어댑터는 저장된 clean 판단·가시성을 고정하고 `ec0bd628` 어댑터와 비교:
8316900 **507틱**, 8316901 **487틱**(추가로 8316902 607틱)의 발행 명령·원장 완전 일치.
전체 교사의 물리 재실행 동등성 검증은 아니다. 8316902의 새 탐색 명령/FK 재생은
20.0초에 명령 추정 360°로 소진됐다. 거리에 맞춘 광축 고도는 −19.88°,
기존 12초 발행 자세는 −55.88°다. 이는 명령/FK 수치이고 실제 재획득 증거는 아니다.

관련 오프라인 시험 **84 passed**. 고정 교사 실제 클래스의 시계·탐색·재획득 연결,
가시 입력 경계·모듈 격리·Mac 실행 차단을 검사했고 물리/렌더 진입점은 차단했다.
새 시드 **8317000–8317039**, 4색 각10개: [로컬 목록·해시](act10-seed-inventory.json)와
[계획](act10-gate-plan.json). act8·act9 포함 로컬 큐/계획 중복 0; 원격 미사용은 미확인.
큐는 커밋 후 `outputs/e2e18-admin/vm3-queue/20261015-act10-<sha8>.json`에 생성한다.
승인·준비·제출·실행·자동 승격 플래그 모두 false, training_rgb OFF다.
남은 일은 새 SHA의 GCP 관문 40개와 첫30/영상 검토이며 이전 성공을 합산하지 않는다.

## 재현

worktree 루트에서 실행한다. 재생 출력은 매번 새 경로를 지정한다. 시드 준비는 정적 계획만 만든다.

```sh
export PYTHONDONTWRITEBYTECODE=1
ACT_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
$ACT_PY -m pytest -q tests/test_grasp_act_act10.py tests/test_grasp_act_act9.py tests/test_grasp_act_act8.py tests/test_grasp_act_act7.py tests/test_grasp_act_act6.py tests/test_grasp_act_data.py
$ACT_PY -m scripts.audit_grasp_act_act10 --runs-root /Users/changmin/projects/ugrp/outputs/gcp1-runs --evidence-root /Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act9-ec0bd628-ops --dependency-root /Users/changmin/projects/ugrp-wt/solo-teacher --output /tmp/act10-independent-replay
$ACT_PY -m scripts.queue_grasp_act_act10 --prepare --dependency-root /Users/changmin/projects/ugrp-wt/solo-teacher --output-dir /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue
# --prepare 변경을 커밋해 작업 트리를 clean으로 만든 뒤:
$ACT_PY -m scripts.queue_grasp_act_act10 --output-dir /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue
```

## 참고 자료

2026-10-15 구현 전 표준 방법을 확인했다. 원문 열람 범위와 이번 설계 차이는 다음과 같다.

- [Laskey et al., DART, CoRL 2017 §1·4/Algorithm 1](https://proceedings.mlr.press/v78/laskey17a/laskey17a.pdf):
  교사 명령에 잡음을 주어 이탈한 상태의 교정 행동을 얻는다. 교란 이후 회복 행동을
  clean 교사 라벨로 남기는 근거다. 이번 고정 교란은 DART 잡음 최적화의 재현이 아니다.
- [Thrun, Burgard, Fox, Probabilistic Robotics (2005), 저자 자료](https://robots.stanford.edu/probabilistic-robotics/):
  저자 공개 자료 페이지·운동 모델 자료 목록 확인(책 본문 전체 미열람). 운동 모델로
  상태를 예측하고 관측으로 갱신하는 원칙을 따른다. 여기서는 측정 주행계 없이 발행
  명령만 적분하는 nominal dead reckoning이며 확률 필터/정확한 위치 추정 구현은 아니다.
  능동 관측은 저자들의 [Active Markov Localization §3·4.3](https://www.cs.cmu.edu/~motionplanning/papers/sbp_papers/integrated4/fox_active_loc.pdf)를 직접 확인했다:
  관측 방향도 선택 대상이다. 이번 유한 확대 탐색은 그 원칙을 적용한 설계이며
  엔트로피 기반 최적화 알고리즘을 구현했다는 뜻은 아니다.
- [Zhao et al., ACT, RSS 2023 §III](https://arxiv.org/html/2304.13705v1):
  action chunking과 겹치는 청크의 temporal ensembling으로 시연 학습을 한다.
  회복 교사 시연과 학생의 독립 실행은 별도 검증한다. 교란 틱 제외·청크 분리는
  프로젝트 데이터 계약이고, 본 작업에서 ACT를 학습하거나 성능을 측정하지 않았다.
