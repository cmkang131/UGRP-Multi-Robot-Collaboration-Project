# PR #253 적대적 검토 수정 기록 — 2026-09-28

Claude가 시작한 `claude/vis6-recipe1` PR을 사용자 지시로 Codex가 이어서 수정했다. 시작 HEAD는 `0687c6207bb21ce20707a022f54c77796b1c4206`, base/main은 `d5bd208e45331a73f1f71dd9b3e129c26c5eaac6`다. 검토 원본은 `/Users/changmin/projects/ugrp/outputs/review-253-20260928.md`이며 P1 1건·P2 7건·P3 10건을 대상으로 삼았다.

## 변경과 확인 범위

| 항목 | 변경 | 합성 검증·남은 범위 |
|---|---|---|
| P1-1 | 2 s timeout 할인 갱신, 연속 stall 5회 뒤 원 예측 복귀, 몸체 좌표 평균만 제거, 입자별 잡음 보존, velocity_gain=.5 | 연속 거짓 stall 21회에서 timeout ≥2회, 5회 이내부터 σ 증가, 상한 뒤 이동량 복귀 확인. 실제 자료 효과 미확인 |
| P2-1 | 예측 지도 벌점을 별도 누적하고 stall 뒤 보정 위치에서 재계산 | 중간 명령 경계, 입자별 다른 벌점, gain=.5/1의 보정·분산 보존 확인 |
| P2-2 | “명령 적분 단독 금지” 주장을 철회. unknown·상한 초과는 명령 예측을 쓴다고 명시. 판정별 이동 누적 진단 추가 | unknown을 stall로 유지하는 hysteresis는 넣지 않음. 바닥이 가린 carry는 영상 이동 확인을 보장하지 않음 |
| P2-3 | 실제 VIS6 하위 클래스의 on-but-inert 경로를 VIS5와 비교. T1c_inert를 P0에 추가 | 명령·팔·적재 전환·강제 재표본화 뒤 입자/가중치/scale/vel/난수/보고 동일. x+1 m 변이 검출. 실제 P0는 관리자 실행 전 |
| P2-4 | 체커 색상 후보 마스크·blur/gradient 경계 제외, 양끝 10% 절사 평균, 점별 정지·이동 혼재 시 unknown | 청록 물체·NaN 경계 인공물·두 운동 집단 거부. 회색 물체/그림자/광택/차체 pitch는 완전히 배제하지 못함 |
| P2-5 | F 주 기준을 event_frames ≥30% 감소로 변경. loaded/unloaded σ p90 각각 7 cm 상한. 사건은 ≥5 bad frame, ≤1 s 간격 병합 | baseline 1사건/911프레임 → 후보 10사건/50프레임을 허용. 0 baseline·불확실성 부풀리기 거부 |
| P2-6 | run 전후 config/plan/runtime 해시·clean HEAD 확인. evaluate는 meta/config/plan/module/추정 파일 해시·완료 frame 수·실패/dirty·동일 HEAD 대조. select는 split/seed 완전성 확인 | 같은 stem의 변조 config·실패·dirty·해시 불일치·누락 meta·혼합 HEAD 거부. GT 접근 전 첫 단위 meta 검증 확인 |
| P2-7 | range 재표본화 때 이전 카메라 입자 ancestry 유지. 주입 입자는 현재 자세로 초기화. pending map prior는 range 재표본화에서 보류 | 재표본화 없음/있음/주입 3경로 뒤 stall 검사가 계속 실행됨. range gate 이동 누적은 카메라 주기에서만 수행 |
| P3-1 | η·effective_columns 비식별성 문서화 | n_terms≥8에서 η=.5/.25/.125 ↔ effective_columns=4/2/1. 작은 열 수에서는 포화 때문에 일반적으로 동등하지 않음 |
| P3-2 | recovery fit은 gate/η 적용 전 우도로 계산 | 같은 prior에서 η가 달라도 fit 동일, 적용 logw는 다름 |
| P3-3 | AMCL과 게이트의 차이 명시 | 경로 길이 합 유지. 순변위·휠 odometry와 같다고 주장하지 않음 |
| P3-4 | S3 최저 NLL 앞에 문 정확도 악화 한도 추가 | 정확도가 악화한 더 낮은 NLL 후보 거부 |
| P3-5 | 검출기 GT 판정에 yaw 포함. seed0 고유 프레임 쌍만 집계 | 제자리 회전 정지/회전 지속 사례, PF 3 seed라도 2개의 쌍을 2개로 집계 |
| P3-6/7/8 | 1차원 탐색·팔/pitch·반사/그림자 한계 명시 | 측방/yaw 대안, 가감속 제외, 수직 흐름 감사, 근거리 표본 비교는 후속 진단으로 남김 |
| P3-9 | reproduce에 std_xy_m/std_yaw_rad/measured 추가. 첫 회차 seed0를 먼저 검사 | 보고 필드 변이 거부. T0와 실제 저장 a1의 동등성은 아직 미확인 |
| P3-10 | yaw wrapped-normal NLL, 지표 가중/σ 정의 명시, 호출별 단위 상태 파일로 실패 판정, s945 선택 편향 명시 | 과거 FAILED 로그는 다음 호출 성공을 막지 않으며 현재 단위 실패는 감지 |

## 계획 재생성

사용자 확인상 VIS6 replay는 아직 실행되지 않았다. 따라서 FROZEN 뒤 발견한 결함을 실제 결과를 보기 전에 고쳤다. 이전 `plan_v6.json`과 29개 설정을 `pre_review_0687c620/`에 보존하고 `make_plan_v6.py --out <새 임시 폴더>` 결과를 반영했다. 원본 해시 보존과 새 계획·30개 설정의 바이트 단위 재생성이 테스트를 통과했다. 새 계획은 revision 2이며 이전 계획 SHA와 런타임 소스 해시를 포함한다. 29개 비교 후보와 중립 검사 전용 T1c_inert 1개다.

실행 번들 ID·workflow 버전은 새로 등록하지 않았다. VIS3/VIS4/VIS5 원본 PF는 수정하지 않았고 frozen-source 검사도 통과했다. 새 모델·태그·weld·GT 제어 입력은 추가하지 않았다.

## 테스트

사용자가 지정한 기존 가상환경·OMP_NUM_THREADS=2·cacheprovider 비활성·로컬 basetemp를 사용했다.

```sh
OMP_NUM_THREADS=2 ../../ugrp/.venv-sim/bin/python -m pytest -q -p no:cacheprovider --basetemp=./.pytest_tmp \
  tests/test_vision_loc_v6.py tests/test_vision_loc_v5.py tests/test_vision_loc_v4.py \
  tests/test_vision_loc_sigma_v4.py tests/test_vision_loc_frozen_split.py tests/test_vision_loc.py \
  -k 'not test_segmenter_shapes_when_torch_is_available'
```

- 기존 VIS 회귀 포함: **266 passed, 3 skipped, 1 deselected in 34.80s**.
- 이후 런타임 소스 변경 없이 입자별 지도 벌점·부분 gain·설정 경계 테스트 7개를 추가한 VIS6 재검사: **88 passed in 1.87s**. 두 실행의 개수는 합산하지 않는다.
- skipped 3개는 기존 VIS4의 로컬 전용 raw/checkpoint 파일 부재에 따른 해시 검사 생략이다. 해당 파일 해시는 검증하지 않았다. 신경망을 실제 실행하는 `test_segmenter_shapes_when_torch_is_available` 1개는 사용자의 모델 호출 금지에 따라 제외했다.
- 초기 VIS6 검사: 73 passed/2 failed. 실패는 새 테스트가 재표본화를 실제로 유발하지 않은 조건, fixture에 없는 `motion_loaded` 키 사용이었다. 테스트 조건을 수정한 뒤 75 passed, 이후 위 회귀 묶음과 최종 88 passed를 확인했다.
- `git diff --check`, 실행 셸 `bash -n` 통과. `.pytest_tmp`는 테스트 뒤 제거했다.
- 실제 데이터 replay/채점·물리 에피소드·렌더러·신경망/외부 모델 호출은 실행하지 않았다. 셸 실행 테스트는 fake Python/AC/디스크 명령만 사용했다. 실험 결과가 없으므로 TensorBoard 변환·서버는 시작하지 않았다.

## 전달 제약

현재 worktree 파일만 수정했다. 샌드박스는 공용 Git 메타데이터를 읽기 전용으로 제공하여 `git fetch origin`은 FETCH_HEAD 쓰기에서, `git add --sparse -A`는 index.lock 생성에서 거부됐다. GitHub CLI 네트워크도 연결되지 않았다. GitHub 연결 도구로 PR #253의 실제 원격 HEAD·base와 열린 PR 목록을 확인했으며 로컬 시작 SHA와 일치했다. 통과한 파일의 GitHub tree 생성을 시도했으나 도구가 `MCP tool call requires approval, but approval policy is never`로 거부했다. 따라서 원격 커밋·push도 완료하지 못했다. 로컬 index/HEAD와 원격 PR HEAD는 시작 커밋 그대로다. PR 본문 갱신도 같은 승인 정책으로 거부됐다. Claude 시작 작업을 Codex가 이어받았다는 설명을 담은 본문 초안은 `pr_body_20260928.md`에 보존한다. 관리자 재생 전에 로컬 Git 상태와 최종 원격 커밋 일치를 확인해야 한다. 병합은 하지 않는다.

## 참조 대조

[Nav2 AMCL 원문](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/amcl_node.cpp)의 `shouldUpdateFilter`(축별 순변위)와 `nomotionUpdateCallback`(force_update)을 2026-09-28 다시 읽었다. 자동 2 s timeout과 할인 우도는 VIS6 자체 정책이며 Nav2 기본 동작이라고 주장하지 않는다.
