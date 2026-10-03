# v95 기준 B 채점 어댑터 — 새 시작점 검증 (new-start validation)

Refs #219 #365. 이 PR은 **채점 코드만** 추가한다. v95 수집 raw는 열지 않았고 채점도 하지 않았다. 조정자가 독립 검토를 받은 뒤 이 어댑터의 sha256을 #219에 게시해야 채점할 수 있다. 어댑터는 그 게시 댓글을 직접 확인하며, 없으면 채점을 거부한다.

## 무엇을 하나

`scripts/score_consumer_criterion_b_v95.py`는 고정 기준 B(`74c312b5…`)를 v95 수집의 (지도, 로봇) 4칸에 적용한다. 사용하는 후보는 r4 `fa7d3aa2…`(전진·옆)와 r5 `978727fc…` 및 회전 부록 `6129f144…`(회전)다. 재적합(re-fitting)은 하지 않는다. 수치 계산은 모두 고정 검증기 `scripts/validate_consumer_criterion_b.py`(`8d2a693a…`)의 함수(`score`, `evaluate_axis`, `axis_supported`, `combine`)를 그대로 호출한다. 수치 함수를 복사하지 않았다.

판정은 지도·로봇·split(step/PRBS)·horizon마다 따로 하고 합치지 않는다. 한 축은 그 칸의 모든 split×horizon이 통과해야 통과다. 전체 축 결과는 4칸을 `combine`한다(하나라도 실패하면 false, 실패 없이 빈 칸이 있으면 null). 4칸이 모두 없으면 채점하지 않는다.

## 채점 전에 확인하는 사슬 (하나라도 어긋나면 채점하지 않고 INELIGIBLE)

1. #219 약속 댓글 5968608872와 관문 기록 5968809408: 저장소 스냅샷(`commitment_comment.json`, `gate_comment.json`)의 sha256을 코드에 고정했다. GitHub에서 실시간으로 다시 읽어 같아야 하고, 수정 이력이 없어야 한다(created = updated).
2. 약속 본문에 사전검사 `precheck.json`·`binding.json`·`SHA256SUMS.json`의 전체 sha256이 있어야 하고, 실제 파일 바이트와 같아야 한다. `binding.json`의 `frozen_sha256`에 있는 B·r4·r5·부록·고정 검증기 전체 해시가 현재 파일과 같아야 한다. 약속 본문에는 해시 앞 8자리만 있어서, 전체 해시는 이 경로로 확인한다. 현재 소스로 `binding()`을 다시 계산하지 않는다(기록된 바이트만 사용).
3. 지도마다 raw `bundle.json`(source_sha·case 제외) digest와 `inputs/schedule.json` 바이트가 binding과 같아야 한다. 4개 궤적의 운동 해시는 사전검사의 값과 같아야 한다. 사례 `result.json`과 `artifacts.sha256.json`의 해시는 관문 기록 본문에 있어야 한다. `plan.json`은 약속 댓글 id·시각과 사전검사 해시를 기록하고 있어야 한다.
4. 선후 관계: 약속 댓글은 가장 이른 수집 시작 기록(잠금 획득 시각 하한 포함)보다 먼저여야 한다. 관문 기록과 어댑터 해시 댓글(`--adapter-comment`, 본문에 이 파일의 sha256 포함)은 raw 읽기 시작보다 먼저여야 한다. 회전도 r5가 수집 전에 고정되었으므로 PRE_COLLECTION이다.
5. 고정 v95 운동 관문(이전 자료 38개)과 새 궤적 6쌍 상호 비교를 프로세스 안에서 다시 실행한다. 겹치면 채점하지 않는다.

## r2와 부호

- r2 읽기(`load_robot`)는 새 코드다. 고정 `load_case`의 검사를 로봇 매개변수만 바꿔 그대로 옮겼다. 채점할 때마다 r1 결과가 고정 `load_case`와 완전히 같은지 확인한다.
- 명령은 `measurement_by_robot[rid]`에 기록된 값과 그대로 비교한다. 적재 시기의 r2 부호 반전(`motion_events`)은 쓰지 않는다. 테스트 확인 내용: r2 명령의 부호를 뒤집은 가짜 자료는 거부되고, 소스에 `motion_events`·`-1 if rid`가 없다.

## 시험 (v95 raw 없음)

- `tests/test_score_consumer_criterion_b_v95.py`(21개):
  - 합성 2지도×2로봇 수집·사전검사·#219 댓글 모의로 전체 사슬과 4칸 채점 구조를 확인한다.
  - 사슬 고리마다 하나씩 변조 13종을 넣고, 각각 의도한 고리에서 채점 전에 거부되는지 사유 문자열로 확인한다.
  - r1 읽기가 고정 `load_case`와 같은지, r2가 자기 파일·계획을 쓰는지 확인한다. 부호 반전 거부와 문구도 확인한다.
  - v88 학습 자료(이미 본 자료, 로컬에만 있음, 없으면 건너뜀)로 r1·r2 경로가 고정 읽기와 같은지 확인한다.
- 모든 테스트에 v95 raw 경로를 열면 실패하는 보호 장치를 걸었다.

## 채점 명령 (어댑터 해시가 #219에 게시된 뒤, 조정자만)

```bash
cd <이 PR head worktree>
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.score_consumer_criterion_b_v95 \
  --raw /Users/changmin/projects/ugrp/outputs/final-pair-v95-heldout-2fe14826-20261003T111306Z/zone_wide_door_geometry_v3 \
  --raw /Users/changmin/projects/ugrp/outputs/final-pair-v95-heldout-2fe14826-20261003T111306Z/zone_wide_corridor_final_v3 \
  --precheck /Users/changmin/projects/ugrp/outputs/heldout-v95-precheck-20261003T085307Z \
  --adapter-comment <어댑터 해시 댓글 id> \
  --output /Users/changmin/projects/ugrp/outputs/criterion-b-v95-score-<UTC>/criterion_B_v95.json
```

종료 코드: 0 = 통과, 1 = 실패, 2 = 판정 없음(INELIGIBLE 또는 빈 칸).

## 결과 문구 범위

말할 수 있는 것: 고정 r4/r5가 학습에 없던 시작 자세(세계 좌표, 0이 아닌 시작 yaw, 두 로봇 구동, 새 축 순서·PRBS 위상)의 궤적 4개에서 B의 잡음 예산 안으로 몸체 운동을 예측하는지. 두 지도는 같은 명령 일정을 쓰므로 독립 반복이 아니다. 명령 크기도 학습과 같다. PF 전체 동작, 학생 제어, 실물 성공은 범위 밖이다.
