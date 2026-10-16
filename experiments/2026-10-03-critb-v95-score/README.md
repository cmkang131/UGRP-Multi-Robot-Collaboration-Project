# v95 기준 B 채점 어댑터 — 새 시작점 검증 (new-start validation)

Refs #219 #365. 이 PR은 **채점 코드만** 추가한다. v95 수집 raw는 열지 않았고 채점도 하지 않았다. 조정자가 독립 검토를 받은 뒤 이 어댑터의 sha256을 #219에 게시해야 채점할 수 있다. 어댑터는 그 게시 댓글을 직접 확인하며, 없으면 채점을 거부한다.

## 무엇을 하나

`scripts/score_consumer_criterion_b_v95.py`는 고정 기준 B(`74c312b5…`)를 v95 수집의 (지도, 로봇) 4칸에 적용한다. 사용하는 후보는 r4 `fa7d3aa2…`(전진·옆)와 r5 `978727fc…` 및 회전 부록 `6129f144…`(회전)다. 재적합(re-fitting)은 하지 않는다. 수치 계산은 모두 고정 검증기 `scripts/validate_consumer_criterion_b.py`(`8d2a693a…`)의 함수(`score`, `evaluate_axis`, `axis_supported`, `combine`)를 그대로 호출한다. 수치 함수를 복사하지 않았다.

판정은 지도·로봇·split(step/PRBS)·horizon마다 따로 하고 합치지 않는다. 한 축은 그 칸의 모든 split×horizon이 통과해야 통과다. 전체 축 결과는 4칸을 `combine`한다(하나라도 실패하면 false, 실패 없이 빈 칸이 있으면 null). 4칸이 모두 없으면 채점하지 않는다.

## 채점 전에 확인하는 사슬 (하나라도 어긋나면 채점하지 않고 INELIGIBLE)

1. #219 약속 댓글 5968608872와 관문 기록 5968809408: 저장소 스냅샷(`commitment_comment.json`, `gate_comment.json`)의 sha256을 코드에 고정했다. GitHub에서 실시간으로 다시 읽어 같아야 하고, 수정 이력이 없어야 한다(created = updated).
2. 약속 본문에 사전검사 `precheck.json`·`binding.json`·`SHA256SUMS.json`의 전체 sha256이 있어야 하고, 실제 파일 바이트와 같아야 한다. `binding.json`의 `frozen_sha256`에 있는 B·r4·r5·부록·고정 검증기 전체 해시가 현재 파일과 같아야 한다. 약속 본문에는 해시 앞 8자리만 있어서, 전체 해시는 이 경로로 확인한다. 현재 소스로 `binding()`을 다시 계산하지 않는다(기록된 바이트만 사용).
3. 지도마다 raw `bundle.json`(source_sha·case 제외) digest와 `inputs/schedule.json` 바이트가 binding과 같아야 한다. 4개 궤적의 운동 해시는 사전검사의 값과 같아야 한다. 사례 `result.json`과 `artifacts.sha256.json`의 해시는 관문 기록 본문에 있어야 한다. `plan.json`은 약속 댓글 id·시각과 사전검사 해시를 기록하고 있어야 한다.
4. 선후 관계: 약속 댓글은 가장 이른 수집 시작 기록(잠금 획득 시각 하한 포함)보다 먼저여야 한다. 관문 기록과 어댑터 해시 댓글(`--adapter-comment`)은 raw 읽기 시작보다 먼저여야 한다.
   - **어댑터 해시 댓글 형식(검토 #372 지적 1):** 작성자는 저장소 소유자여야 한다(`author_association == OWNER`, login `cmkang131`). 본문에는 정확히 한 줄의 표지 줄 `V95_SCORING_ADAPTER_SHA256: <이 파일의 sha256>`이 있어야 한다. 다른 사람의 댓글은 거부한다. 해시만 적힌 "REJECTED … <sha>" 같은 문장도, 표지 줄이 두 줄인 댓글도 거부한다. 약속·관문 댓글도 실시간 조회에서 소유자 작성이어야 한다.
4b. **의존 소스 재해시(검토 #372 지적 2):** 사전검사 `binding.json`의 `source_sha256`에 기록된 271개 파일을 모두 현재 바이트로 다시 해시한다. 대상에는 `kinematic_overlap.py`, v95 관문 검증기, 제외 목록, v91 어댑터, `fit_unloaded_consumer.py`, `fit_unloaded_hammerstein.py`, 고정 검증기가 포함되며, 하나라도 다르면 채점하지 않는다. 채점한 체크아웃의 `git rev-parse HEAD`와 `git status --porcelain`을 보고서에 남긴다. 따라서 채점은 271개 파일이 binding과 같은 체크아웃(예: 이 PR head)에서 해야 한다. 이 PR head에서 271/271 일치를 확인했다. 회전도 r5가 수집 전에 고정되었으므로 PRE_COLLECTION이다.
5. 고정 v95 운동 관문(이전 자료 38개)과 새 궤적 6쌍 상호 비교를 프로세스 안에서 다시 실행한다. 겹치면 채점하지 않는다.

## r2와 부호

- r2 읽기(`load_robot`)는 새 코드다. 고정 `load_case`의 검사를 로봇 매개변수만 바꿔 그대로 옮겼다. 채점할 때마다 r1 결과가 고정 `load_case`와 완전히 같은지 확인한다.
- 명령은 `measurement_by_robot[rid]`에 기록된 값과 그대로 비교한다. 적재 시기의 r2 부호 반전(`motion_events`)은 쓰지 않는다. 테스트 확인 내용: r2 명령의 부호를 뒤집은 가짜 자료는 거부되고, 소스에 `motion_events`·`-1 if rid`가 없다.

## 시험 (v95 raw 없음)

- `tests/test_score_consumer_criterion_b_v95.py`(29개):
  - 합성 2지도×2로봇 수집·사전검사·#219 댓글 모의로 전체 사슬과 4칸 채점 구조를 확인한다.
  - 사슬 고리마다 하나씩 변조 19종을 넣고(소유자 아님, 표지 줄 없음·중복, 관문 댓글 작성자, binding 소스 불일치·누락 포함), 각각 의도한 고리에서 채점 전에 거부되는지 사유 문자열로 확인한다.
  - r1 읽기가 고정 `load_case`와 같은지, r2가 자기 파일·계획을 쓰는지 확인한다. 부호 반전 거부와 문구도 확인한다.
  - 복사한 체크아웃에서 `kinematic_overlap.py` 바이트를 실제로 바꾸면, 겹침·잔차 통계를 하나도 계산하기 전에 거부된다.
  - 보고서에 체크아웃 HEAD·상태, 재해시 파일 수, 어댑터 댓글 작성자가 기록되는지 확인한다.
  - v88 학습 자료(이미 본 자료, 로컬에만 있음, 없으면 건너뜀)로 r1·r2 경로가 고정 읽기와 같은지 확인한다.
- 모든 테스트에 v95 raw 경로를 열면 실패하는 보호 장치를 걸었다.

## 채점 명령 (어댑터 해시가 #219에 게시된 뒤, 조정자만)

```bash
# #219에 소유자가 아래 한 줄을 포함한 댓글을 올린 뒤, 시계 차이를 피하려고 1분쯤 지나서 실행한다:
# V95_SCORING_ADAPTER_SHA256: <scripts/score_consumer_criterion_b_v95.py 의 sha256>
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

## 채점 결과 (2026-10-03, 새 시작점 검증)

조정자가 #372 독립 재검토 승인(댓글 5971418968) 뒤 #219에 어댑터 해시 댓글을 올렸고(5971425132, 소유자 `cmkang131`, 17:06:21Z), 1분 넘게 지난 17:07:31Z에 이 PR head(b4cd1336, 변경 없음)에서 `nice -n 10`으로 채점했다. 17:07:37Z에 종료 코드 0으로 끝났다. 부하 평균(load average)은 시작 17.44/15.94/16.70, 끝 16.37/15.74/16.63이다.

### 판정

채점기가 쓴 그대로 옮긴다. 하나의 "통과"로 줄이지 않는다.

| 항목 | 값 |
|---|---|
| 범위(scope) | `HELD_OUT_VALIDATION` (새 시작점 검증) |
| 원래 B 축별 판정 | forward `true`, left `true`, rotate `null`(r4에 회전 후보 없음) |
| 원래 B 전체 판정 | `null` (회전 축이 비어 있으므로) |
| r5 회전 부록 포함 축별 판정 | forward `true`, left `true`, rotate(yaw) `true` |
| r5 회전 부록 포함 전체 판정 | `true` |

### 사례별 수치 (지도 × 로봇, 분할별 최악값)

정규화 절대오차 95백분위수(`p95(|e|/σ)`, 한계 ≤ 2)의 최댓값과 2σ 포함률(한계 ≥ 0.9)의 최솟값이다. 6개 예측 시간(0.2~3.2초)과 성분 중 최악값이다. 모든 사례에서 steps와 PRBS 분할이 각각 통과했다.

| 지도 | 로봇 | forward steps / PRBS | left steps / PRBS | yaw(r5) steps / PRBS | 2σ 포함률 최솟값 |
|---|---|---|---|---|---|
| door_geometry_v3 | r1 | 1.8081063 / 0.8014 | 1.9991754 / 0.7778 | 1.9999994 / 0.3603 | 1.0 |
| door_geometry_v3 | r2 | 1.8081063 / 0.8017 | 1.9991754 / 0.7775 | 1.9999992 / 0.3603 | 1.0 |
| corridor_final_v3 | r1 | 1.8081063 / 0.8014 | 1.9991754 / 0.7778 | 1.9999994 / 0.3603 | 1.0 |
| corridor_final_v3 | r2 | 1.8081063 / 0.8017 | 1.9991754 / 0.7775 | 1.9999992 / 0.3603 | 1.0 |

steps 최악값은 모두 3.2초 예측 시간에서 나왔다. 전체 수치는 [criterion_B_v95.json](criterion_B_v95.json)에 있고, 요약은 [score_summary.json](score_summary.json)에 있다.

### 증거 기록

- 어댑터 해시 댓글: [5971425132](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5971425132). 작성자 OWNER `cmkang131`, 17:06:21Z, 수정 없음. sha256은 `f64016dd…5a`이다.
- 순서:
  - 약속 댓글 5968608872(11:12:35Z)가 가장 이른 수집 시작 기록(11:14:03Z, 잠금 획득 시각 하한)보다 먼저다.
  - 관문 기록 5968809408(11:40:41Z)과 어댑터 댓글(17:06:21Z)이 raw 읽기 시작(17:07:33Z)보다 먼저다.
  - 시계 한계: GitHub 서버 UTC와 채점 컴퓨터 UTC를 비교한 것이고, raw에 서명은 없다.
- 운동 관문: `DISJOINT`. 이전 자료와 152번 비교했고, 새 궤적끼리 6쌍을 비교해 겹침 0건이다.
- `sources_rehashed`: 271개 파일 모두 binding과 일치했다.
- `scoring_checkout`: HEAD `b4cd1336d3b5a77785314b69dad64f42625fd73f`, `git status --porcelain`은 빈 목록이다.
- 읽은 입력 파일 300개의 sha256은 결과 JSON의 `input_files`에 있다.
- 산출물 경로: `/Users/changmin/projects/ugrp/outputs/criterion-b-v95-score-20261003T170731Z/`
  - `criterion_B_v95.json` `998bc3d4c32eeae1dae4225c4dbade458dd13c0562a0a21bf3613bfc6052a368` (이 폴더에 같은 바이트로 복사)
  - `run_meta.txt` `36e80f7411ff4a4c40a354a6153b68fb06c1f2d267ed9f0eeb305e0347564c11`
  - `stdout.txt` `db31d066fce20cc5e2b55030c6d4e9cd9cd961014b27d4e8ec5d29528e71d46b`
  - `stderr.txt`는 빈 파일이다.

### 해석 한계

1. **steps 구간은 새 증거가 아니다.**
   - steps 분할의 수치는 v91 r2 door와 사실상 같다. 정규화 오차 차이는 forward 3e-7, left 9.5e-6, yaw 4.6e-6 이하다. 네 v95 사례끼리도 같다.
   - v95 일정은 v88의 10초 부호 계단 명령 뒤 1초 정지를 그대로 쓰고 축 순서만 바꿨다. 그래서 계단 명령은 늘 정지 상태에서 시작한다.
   - 결정적 시뮬레이션에서 몸체 기준 응답이 시작 자세에 영향을 받지 않는다는 설명과 맞는다. 다만 원리를 따로 증명하지는 않았다.
   - 실제로 달라진 부분은 PRBS 구간(위상 7/13비트 이동)과 세계 좌표·시작 yaw 변환이다. PRBS 최댓값 차이는 forward 0.094, left 0.076, yaw 0.021이다.
2. **yaw 여유가 거의 없다.** steps 3.2초 yaw 값이 1.9999994로, 한계 2와의 차이가 약 6e-7이다. r5의 σ를 학습 자료에서 p95가 2가 되도록 맞췄기 때문이다(회전 README: 학습 p95 1.9999999996663158). 같은 계단 응답이 다시 나와서 통과한 것이고, 여유를 보여 주는 결과가 아니다.
3. **제외 관문은 세계 좌표 기준이다.**
   - v95 운동 관문은 세계 좌표의 위치·회전 궤적이 겹치는지만 본다. 시작점을 옮기거나 돌리면 관문을 통과하지만, 몸체 기준 증분은 학습 때와 같을 수 있다.
   - 이것은 이번 설계(#365)의 한계이며, 최종 보고서에 적을 항목이다.
   - 몸체 기준 증분까지 다르게 하려면 명령 크기나 계단 길이가 학습과 달라야 한다. 그러면 "같은 명령 크기"라는 이번 조건 밖이 된다.
4. 두 지도는 같은 명령 일정을 쓰므로 독립 반복이 아니다. door와 corridor의 차이는 3e-5 이하다. r1과 r2는 PRBS 위상만 다르다.
5. PF 전체 동작, 학생 제어, 실물 성공, 적재 상태는 이 결과의 범위 밖이다. r4·r5 후보는 계속 `CANDIDATE_UNVALIDATED`이고, criterion A는 다시 채점하지 않았다(`FAILED_NOT_RESCORED`).

### TensorBoard

- 새 스냅샷: `outputs/tensorboard/1003-critb-v95-score/`. run은 `door-r1`, `door-r2`, `corridor-r1`, `corridor-r2`이고, 여기서 r1/r2는 로봇이다.
  - 파생 뷰는 `outputs/critb-v95-score-tbviews-20261003/`에 있다. 생성기 사본은 [make_tb_views.py](make_tb_views.py)이다. 원본 JSON 값만 옮기며 v95 raw는 열지 않는다.
  - 변환에는 `scripts/export_offline_audit.py`를 썼다(내보냄 4, 실패 0).
- 비교 기준: v91 스냅샷 `1003-critb-v91-score/`(r1/r2는 채점 회차, 로봇은 r1뿐)를 다시 변환하지 않고 같은 화면에 별도 코호트로 띄운다.
- 링크: `outputs/tensorboard-view.json`의 `critb_v95_score_20261003.url`. 필터는 `^1003-critb-v9[15]-score/`, 고정 카드 12개, smoothing 0이다. run이 500개를 넘어 새 run은 처음에 선택되지 않으므로 왼쪽 전체 선택을 눌러야 한다.
- 확인:
  - EventAccumulator로 4개 run × 스칼라 86개를 다시 읽어 파생 뷰와 일치함을 확인했다(32비트 반올림 범위).
  - 기존 공용 서버(PID 54928, 재시작하지 않음) API로 gate 1, yaw 3.2초 1.9999994/1.9999993(v91 2.0), 모델 호출 0을 확인했다.
  - 브라우저에서 고정 카드를 열어 forward 1.8081(8개 run), yaw 2(반올림), yaw 2σ 포함률 v91 0.9501 / v95 1을 확인했다.
  - 원본 해시 `998bc3d4`는 새 스냅샷의 manifest에만 있어 중복 변환이 없다.
