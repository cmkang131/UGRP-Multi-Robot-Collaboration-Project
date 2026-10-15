# ACT9 — 회복 장면 먼저

기준 act8 `01a892fa`, 고정 교사 `6f057f7e`, PR #504. 사용자 결정(2026-10-15):
“회복 장면 먼저”. act8 회수 원본은 성공40/40이나 lost/reacquired 모두0이다.
새 물리 실행·렌더·학습·원격 호스트 접속은0이며 실제 회복 성공은 미측정이다.

- 기본 OFF `recovery_perturb_v1`: 접근·정렬에서 현재 대상이 보이고 이동 명령인
  틱을12회 센 뒤 매 적격 틱 확률.1, 실행당 최대1회. 시드로 방향을 뽑아
  고정 .35 duty/100ms를9틱(0.9초) 발행한다. 크기는 GT와 무관한 프로젝트
  후보값이며 최적화 DART 잡음이나 실측 회전각이 아니다. 물체·카메라 배치/FOV는 그대로다.
- 교란 중 발행 PWM을 고정하고 기존 교사의 명령 시계는 진행하며 위치 관측을 버린다.
  이전 대상·정렬 적분을 지우고 교란 뒤 기존 자기 시야 탐색으로 복귀한다.
  학생 이력은 실제 발행 명령, 교사 라벨은 현재 상태의 clean 명령이다.
  `perturbation_interval=true`는 `local_skill_sample=false`, `training_target=false`로
  제외하며 청크를 끊는다. 변환기도 원장 시각과 라벨 마스크를 대조한다.
- 실행마다 `recovery.audit`에 교란 귀속 lost→reacquired 장면 수,
  전체 명령 틱 대비 교란 비율, 단계 종료/실행 끝까지 미재획득한 실패 수,
  시야 이탈이 없었던 교란 수를 기록한다. 자기 카메라 가시성 관문을 세며
  재획득은 임무 성공과 별개다. `recovery.sha256`은 비압축 원장 해시다.
- 관문은 기존 `dart_wheels_v1` 판정을 유지하고 act8 모드도 받는다.
  새 모드는 해시가 맞는 원장을 재계수해 성공≥38/40, **성공한 실행≥20개에서
  각각 회복 장면≥1회**를 요구한다. 모드 혼합·출처 불일치·입력 감사 위반은 거부한다.
  act8 실행 회수 원본40개를 임시 verifier 시험 fixture로 확인했으며 승인 영수증은 만들지 않았다.

[검증 요약·40개 원본/재생 경로와 해시](act9-offline.json): 관련 시험70 passed.
원장40개를 새 선택기로 오프라인 재생해 교란40실행·360틱과 제외 라벨 모형360개를
확인했다. ACT8의 고정 관측을 쓰는 명령 재생이므로 ACT9의 실제 시야 이탈·회복이나
네이티브 RGB 시연의 성공 증거가 아니다. 실제 pinned recorder의 `target` 메서드로
직렬화·실제 명령 이력·교란 전후 청크 분리를 단위 검증했다. 모듈 격리 시험은 world
생성 직전에 차단하며 act7의 과거 ACT blob 기록을 덮어쓰지 않고 고정 교사 blob을 검사한다.

새 시드8316900–8316939(4색 각10): 이전 로컬 큐113개·계획7개만 읽어 중복0.
[목록·해시](act9-seed-inventory.json). 원격 미사용은 미확인이다. 커밋 후
`20261015-act9-<sha8>.json`을 새로 생성하며 승인·실행·승격 플래그는 전부false,
training_rgb OFF, 동시1개다. 이전 큐/결과와 합산하지 않는다. 실제 GCP 관문과
영상 검토, 이후 RGB 기록 승인은 남아 있다.

## 재현

아래 명령은 이 worktree에서 실행한다. 재생 output은 매번 새 경로를 쓴다.

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_grasp_act_act9.py tests/test_grasp_act_act8.py tests/test_grasp_act_act7.py tests/test_grasp_act_act6.py tests/test_grasp_act_data.py
PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.audit_grasp_act_act9 --summary /Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act8-01a892fa.json --noise experiments/2026-10-15-act-train/act9-noise.json --output /tmp/act9-independent-replay
python3 -m scripts.queue_grasp_act_act9 --output-dir /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue
```

계획 재생성은 `PYTHONDONTWRITEBYTECODE=1`을 켜고 위 큐 CLI에
`--prepare --dependency-root /Users/changmin/projects/ugrp-wt/solo-teacher`를 붙인다.
로컬 큐가 바뀌면 시드 목록/해시 영수증도 다시 검토한다. Git 전체 검색은 쓰지 않는다.

## 참고 자료

2026-10-15 원문 열람. 미확인 인용은 없다. 논문 방식과 프로젝트 변경은 구분한다.

- [Laskey et al., DART, CoRL 2017, §1·4/Algorithm1](https://proceedings.mlr.press/v78/laskey17a/laskey17a.pdf):
  시연 중 잡음을 넣어 교정 행동을 얻고 학생 오류에 맞춰 잡음 수준을 반복 최적화한다.
  여기서는 시야 이탈 장면을 위한 고정 회전 probe만 채택했다. 학생 오차분포에 맞춘
  최적화·DART 반복 학습을 수행했다는 주장은 하지 않는다.
- [Ross et al., DAgger, AISTATS 2011, §3/Algorithm3.1](https://proceedings.mlr.press/v15/ross11a/ross11a.pdf):
  정책이 방문한 상태에 전문가 행동을 붙여 누적 학습한다. 교란 후 현재 상태의 교사
  라벨을 쓰는 근거이며, 학생을 실행/재학습하지 않은 이번 작업은 DAgger 구현이 아니다.
- [Zhao et al., ACT, RSS 2023, §II·V-B](https://arxiv.org/html/2304.13705v1):
  실제는 ALOHA 원격조작, 시뮬레이션은 scripted/human 성공 시연을 수집한다.
  §II는 잡음이 정밀 조작 실패를 부를 수 있다고 지적한다. 따라서 새 교사 성공 관문을
  먼저 확인하고 그 뒤 학생 카메라로 기록한다. 교란 라벨 제외는 이번 사용자 요구다.
