# S2 졸업 시도 — 실행 전 계획 (2026-10-06)

## 고정 후보와 범위

- base `da92d91dbf4af193d3aa3559de9efe55653ec5c0` (main, #391/#392 병합).
  브랜치 `codex/s2-graduation`, PR은 DRAFT 유지·병합 금지.
- v106 제어기·시각·이동 보정·물리 backend는 `dfec1f19e1580534242d3b1b436eb45c07a979ea`와 바이트 동일하다.
  기존 CLI/contract는 seed 911–914만 허용하므로 **915–928의 허용 목록만 확장**한다.
  새 후보 SHA는 이 계획·launcher·허용 목록·관련 시험을 커밋한 뒤 실행 인자로 고정한다.
  기존 SHA로 실행했다고 표현하지 않는다. 실행 도중 튜닝·수정·재시도·seed 교체는 없다.
- 번들 `zone-solo-cyan-v106`, workflow 3.13.0, r3, 목적지 B, door_1,
  `zone_wide_door_geometry_v3`, `cargo_noslip_v1`, weld OFF, `v98-exact-v6`, LLM 0회.
  실제 번들에는 source closure/지도/보정/카메라/물리 해시를 저장한다.
- **stop-ON은 끈다.** v106은 `Runtime(dev_light=False)`를 명시적으로 거절하며,
  켜려면 검증 대상 제어 동작을 바꿔야 한다. 고정 후보를 그대로 평가하기 위해 DEV light를 유지한다.
  would-stop을 전수 보고하며 정식 stop-ON 통과·연구 확증·실물 성공으로 승격하지 않는다.
  s911에서 맞춘 yaw 모델은 탐색 모델이다. 911–914는 아래 새 표본 분모에서 모두 제외한다.
- 낙하·기울기·집게 이탈의 실행 중 감지는 기존 코드에 없다. 이를 새로 구현하지 않는다.
  영상 오류·blind 경로 이탈·실행 오류·900 SIM초 상한은 기존대로 종료한다.

## 사전 목록과 순서

결과를 보기 전 고정한다. 접근/파지 6곳 → 문 통과 → 놓기/심판 → 새 seed 단독 전 구간 6회 순이다.
각 행은 한 번만 실행하고 실패도 보존한다. 단계 통과는 다음 절의 사후 물리 기하 조건도 요구한다.

| 순서 | seed | slot | 실행 stage | 용도 |
|---:|---:|---|---|---|
| 1 | 915 | P2-1 | pick | 접근·파지·HIGH |
| 2 | 916 | P1-1 | pick | 접근·파지·HIGH |
| 3 | 917 | P2-3 | pick | 접근·파지·HIGH |
| 4 | 918 | P1-3 | pick | 접근·파지·HIGH |
| 5 | 919 | P2-2 | pick | 접근·파지·HIGH |
| 6 | 920 | P1-2 | pick | 접근·파지·HIGH |
| 7 | 921 | P2-2 | door | 실제 시작부터 문 뒤까지 |
| 8 | 922 | P1-2 | place | 실제 시작부터 놓기·심판 |
| 9 | 923 | P1-1 | place | 새 단독 전 구간 1/6 |
| 10 | 924 | P2-1 | place | 새 단독 전 구간 2/6 |
| 11 | 925 | P1-2 | place | 새 단독 전 구간 3/6 |
| 12 | 926 | P2-2 | place | 새 단독 전 구간 4/6 |
| 13 | 927 | P1-3 | place | 새 단독 전 구간 5/6 |
| 14 | 928 | P2-3 | place | 새 단독 전 구간 6/6 |

## 판정·중단 규칙

- pick: controller HIGH 도달 + 원본 cyan z>0.06 m 상승 이력 + 종료 시 z>0.06 m 유지.
  door: controller 문 뒤 도달 + cyan 전체가 door_1 벽의 목적지 쪽을 통과 + 종료 시 상승 유지.
  place: 정상 종료 + 상승 이력 + 상자 전체가 B 안 + 바닥 안정 최소 1.95초(목표 2초).
- 최종 상자의 8개 꼭짓점을 rotation/half-size로 직접 계산하여 B 내부 포함과 바닥 조건을
  기존 `evaluate()`와 별도 구현으로 재계산한다. 마지막 2초 위치 변화 ≤8 mm,
  바닥 오차 <8 mm, 중심 z<40 mm, 상승 z>60 mm. 누락·비단조 시각은 판정 불가다.
- 거짓 성공/거짓 실패는 저장된 **evaluation.success**와 독립 trajectory 판정의 양방향 불일치다.
  controller의 단계 완료만으로 배송 성공을 주장하지 않는다. pick/door는 배송 완료가 목적이 아니며
  배송 판정과 단계 판정을 별도 기록한다. 재계산 일치는 이 기하 범위의 일치이며
  접촉·파손·정답 판정의 완전성까지 보증하지 않는다. 대표 원본 RGB도 확인한다.
- 동일 원인(실패 코드 또는 같은 사후 물리 실패 분류)이 **두 실행**에서 나오면 즉시 남은 실행을 멈춘다.
  would-stop tick 수는 실패 실행 수로 세지 않는다. 반복 실패 후 표준/고전 방법·최근 논문/공개 코드를
  조사해 출처와 최소 수정안을 기록한다. 이 후보를 그 자리에서 튜닝해 계속하지 않는다.
- 단계 실패가 남으면 다음 단계의 졸업 증거 수집으로 넘어가지 않는다. 미실행은 미실행으로 남긴다.
  HOST_ERROR·ENOSPC·누락을 성공 분모에서 숨기지 않는다. 기록·해시 검증 오류도 졸업 차단이다.
- 졸업 조건은 단계 통과, 새 단독 전 구간 6회 이상, 거짓 판정 0, 3대 스모크 6회 모두 충족해야 한다.
  단독 DEV light 표본이 늘어도 이것만으로 전체 졸업을 선언하지 않는다.

## 실행·보존

`launch_dev.zsh FULL_SHA ABS_OUT STAGE SEED SLOT`은 #391 launcher 형식을 따른다.
`ugrp_session.py run s2-grad-s<seed> -- /bin/zsh launch_dev.zsh ...`로 관리한다.
null 잠금에서 owner codex/branch codex/s2-graduation/purpose `S2 graduation`/자기 셸 PID로
acquire하고 자기 자식·watchdog 정리 후 release한다. 한 번에 한 시뮬레이션, nice 0,
`NO_BG_NICE`; 최대 900 SIM초/10800 wall초. 전체 계획의 상한은 14회이며 반복 실패 시 조기 종료한다.
raw는 `/Users/changmin/projects/ugrp/outputs/s2-graduation-<sha8>-s<seed>-<slot>-<stage>`에만 쓴다.
실행 전 여유 35.55 GiB 확인. 매 실행 여유 10 GiB 미만이면 HOST_ERROR로 보존하며 시작하지 않는다.
원본 삭제·덮어쓰기·Drive 업로드 없음. local raw와 GitHub 기록을 구분한다.
기존 Codex worktree 수가 상한을 넘었지만 사용자 지정 새 worktree와 다른 작업 보존을 위해
관리 명령의 `--allow-over-cap --reason`으로 생성했다. 다른 worktree는 변경하지 않았다.

## 3대 스모크: 미지원, 실행하지 않음

현재 v106 backend `issue()`는 지정 로봇 외 명령을 거절하고 `capture()`는 자기 한 대만 반환한다.
장면에는 cyan 1개, 평가도 첫 물체 1개뿐이다. `IntegratedTrial`은 3개의 RobotLink를 요구하지만
기존 `ZoneOwnExecutor`의 wrist v9 경로이며 v106 Runtime/FinalV3Scene을 연결하지 않았다.
따라서 단독 실행을 3개 병렬로 돌려 3대 스모크로 대체하지 않는다.

최소 S3 계획: (1) 표준 FinalV3Scene에 cyan 3개·명시적 slot/주문을 배치하고 평가 item ID를 보존,
(2) 하나의 clock/world에서 v106 Runtime 3개에 각 own RGB/명령 이력만 전달,
(3) 고정 주문을 RobotLink의 deliver/job_done/job_failed에 연결하고 동시 통로 충돌·양보를 처리,
(4) 물체별 trajectory와 정착 심판을 eval_only에 기록, 3개 주문 모두 배송 확인,
(5) 새 번들/소스를 고정한 무 LLM 6개 seed 스모크. 기존 단독의 재탐색은 단일 cyan을 가정하므로
여러 cyan의 소유·중복 후보 선택도 별도 검증해야 한다. 이번 PR에서는 구현하지 않는다.

## 참고 자료와 검증 범위

- [Gymnasium 공식 seeding API](https://gymnasium.farama.org/api/utils/#seeding):
  2026-10-06 본문 확인. 명시 seed를 RNG/reset에 연결하는 표준 방식을 참고했다.
  저장소의 기존 seed 전달을 그대로 사용하며 새 seed 허용만 바꾼다. 외부 시뮬레이터를 도입하지 않는다.
- v106 원본의 고전 PF/visual servo/관측 퇴화·최근 NuRF/SVM 참고는 기존 기록의 검증 범위를 유지한다.
  새 실패가 생기면 원인과 직접 관련된 자료를 다시 확인한다.
- 커밋 전 관련 시험 `tests/test_solo_cyan_v106.py`, `tests/test_solo_cyan_v106_runner.py`,
  launcher 구문·계획 목록·`git diff --check`를 확인한다. 넓은 시험은 GitHub CI에 맡긴다.
- 결과는 이 README·새 TensorBoard snapshot·DRAFT PR 코멘트에 기록한다.

실행 전 검증: 관련 두 시험 **34 passed / 13.42 s**. 별도 꼭짓점 심판의 정상·밀기·경계 돌출·표본 누락 검사 통과. launcher 구문과 diff 공백 검사 통과.
