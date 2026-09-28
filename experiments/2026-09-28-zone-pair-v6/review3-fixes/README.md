# PR #246 v6 검토 3 수정

기준 HEAD `a5b486eb`, 브랜치 `codex/zone-pair-beam-relative`. 검토 3의 P1 3건·P2 4건과 코디네이터의 문헌 레시피 추가 지침을 다룬다.
물리 step·실제 모델 호출·실험 잠금은 없다. 반례는 명령 응답 모델, 해석 투영 영상, 저장된 자기 JPEG로 확인했다.
저장 JPEG의 GT는 평가 전용 대조에만 썼고 제어 입력에는 넣지 않았다.

## 항목별 수정

### P1-1. 정상 접근이 재관측 예산을 소진하던 문제

**원인 1 — 이중 합산:** envelope가 PF 평균과 anchor 사이 거리와 1.6×이동거리를 둘 다 더했다.
**수정:** 도달 집합의 중심을 anchor + 명령 적분의 절반 이득 지점(`BACKOFF_GAIN_MAX/2`)으로 옮겼다.
반경은 이득 [0, 1.6] 전 범위와 anchor yaw·회전 이득 오차가 만드는 방향 오차로 계산한다(`heading_spread`). PF 불일치는 이 중심에서 잰다.

- 10 cm 직진 뒤 σxy: 이전 0.146 m, 이후 0.066 m. unloaded HIGH는 0.08 m다.
- 이득 0/0.5/1/1.47/1.6과 anchor 방향 오차 ±2σ의 모든 끝점이 2σ 안에 드는지 전진·횡이동·전진+회전·제자리 회전에서 검사한다.

**원인 2 — 예산 공유:** 예정 재관측의 대기가 HIGH 복구 예산 10초에서 빠졌다.
**수정:** 예정 안전 재관측(`global_safety_reserve`)은 별도 예산을 쓴다.

- 회당 6초, 작업당 총 240초·80회. 초과분만 HIGH 복구 10초로 넘어간다.
- 총량이나 횟수가 소진되면 `PAIR_SCHEDULED_REOBSERVE_LIMIT`로 명시적으로 중단한다.
- 값은 `prereg_v6.v6_contract.reobserve_budgets`에 등록했다.

**결과:** 이전에는 spawn(-0.65,-0.85)에서 1.05 m 목표로 가다 0.65 m 지점에서 12회 재관측 후 timeout했다. 90° 회전은 0.94 rad에서 timeout했다.

| 시나리오 | 결과 | 예정 재관측 | 예정 대기 | HIGH 대기 |
|---|---|---:|---:|---:|
| 1.05 m 직진, fix 0.25초 지연 | 29.8초 도착 | 7회 | 7.55초 | 0초 |
| 1.05 m 직진, 현실 입력 | 39.3초 도착 | 7회 | 14.75초 | 0초 |
| 1.05 m + 횡 0.5 m, 현실 입력 | 45.0초 도착 | 8회 | 17.0초 | 0초 |
| 제자리 90° 회전, 현실 입력 | 46.7초 도착 | 7회 | 14.7초 | 0초 |

현실 입력은 settle 뒤 0.2초 지연이 있고, 정착된 시야 두 번 중 한 번은 fix가 없다.

### P1-2. a+b 정렬이 정상 진입 거리에서 즉시 실패하던 문제

- **원거리 close-in:** fresh 전체 형상이 식별됐지만 bound만 5 cm를 넘는 경우를 다룬다(`closing_ready`). 이때 전진 전용 소폭 명령을 낸다.
  최악 이득 1.6에서도 실제 grip이 standoff 0.162 m 안으로 들어가지 않게 크기를 제한한다. 전역 안전 검사를 먼저 통과해야 한다.
  준비 임계값 5 cm/3°는 그대로다. 명령은 `relative_close_in` 이벤트로 남는다.
- **view 시도 기록 초기화:** 부분뷰 시도 기록을 시각 dict로 바꿨다.
  다중 뷰 보존 창(`MULTIVIEW_KEEP_S` 4초)이 지난 view는 다시 시도할 수 있다. align relook이 끝나면 기록을 비운다.
  세 자세가 창 안에서 모두 실패하면 이전처럼 명시적으로 실패한다.
- **실제 기하의 합성 영상:** 합성 영상에 가까운 끝면(높이 32 mm)을 그린다(아래 P1-3). 이 조건의 결과는 다음과 같다.

| 진입 grip | 결과 | 도착 시 실제 grip |
|---|---|---|
| 0.36 / 0.40 / 0.43 / 0.44 / 0.462 / 0.50 / 0.55 / 0.58 m | 모두 `pregrasp_descend` 도달 | 0.167–0.172 m, IK 범위 0.145–0.18 m 안 |
| 0.33 m | 가까운 끝면이 search 하단 경계에 잘려 식별 전 `BEAM_RELATIVE_UNCERTAIN`로 명시 실패 | — |

0.33 m 실패는 남은 위험에 적었다.

### P1-3. 실제 tags_temporary 영상에서 정상 빔을 거부하던 문제

**원인 1 — 상대 로봇 성분:** 두 번째 색 성분(상대 로봇의 노란 부품)이 빔 전체를 거부하게 만들었다.
**수정 — 성분 연관(`associate_component`):**

- prior track이 있으면 그 corridor 안 95% 이상인 성분을 고른다. 없으면 가장 큰 성분을 고른다.
- 다른 성분은 다음 세 조건을 모두 만족할 때만 분리 대상으로 제외한다(`SEPARATE_COMPONENT_EXCLUDED`).
  - 영상에서 바닥 픽셀로 3 px 넘게 떨어져 있다.
  - 선택 성분과 합친 축 길이가 0.66 m + 끝면 여유를 넘거나, 횡으로 0.10 m 넘게 떨어져 있다. 즉 같은 catalogue 빔이 될 수 없다.
- 위 조건을 못 채우면 가림체 후보로 본다(`ADJACENT_OCCLUDER_CANDIDATE` / `DISCONNECTED_SHAPE_OR_OCCLUSION`).
  이 경우 정렬은 즉시 실패하지 않고 다른 고정 자세로 전환한다.
- 부분뷰 지지 검사에도 같은 연관을 쓴다.

**원인 2 — 끝면 투영:** 실제 렌더에서는 가까운 끝면(바닥~윗면)이 윗면 평면 투영에서 카메라 쪽으로 늘어난다. 그래서 길이가 0.66 m를 넘었다(dev09 0.709 m).
**수정 — 끝면 모델:**

- 가까운 끝을 끝면 중간 높이 가설에 둔다. 기존 16 mm 반높이 bias bound가 윗면~바닥 전체를 덮는다.
- catalogue 길이 검사는 끝면 투영 폭만큼의 길이 구간에 적용한다. 먼 끝은 보이지 않는 끝면이라 윗면 가장자리다.

**실제 렌더 표본:** 저장 raw 3개(v5h·v5b·v5g, 7,537장)에서 조사했다. 대상은 집게를 연 자기 프레임 중 빔 색 60점 이상인 것이다.

비교는 정지 프레임만 한다. 마지막 arm(3–6)/look/drive 명령 뒤 0.6초 이상 지난 프레임이고, 세 look 자세(search·p45·inspect)의 4,928장이다.
v6 제어기는 arm 큐가 settle까지 끝난 뒤에만 상대 track에 프레임을 넣으므로 이 범위가 제어 입력과 같다.

| 지표 (정지·look 자세 4,928장) | 기준 HEAD a5b486eb | 수정 후 |
|---|---:|---:|
| fit 수 | 1,625 | 3,693 |
| bound ≤ 5 cm | 1,625 | 2,121 |
| 오차 > bound (GT 평가) | 0 | 0 |
| 최대 오차/bound | 0.77 | 0.19 |

- **움직이는 프레임까지 넣으면:** 수정 후는 9,528장에서 fit 4,838개, 위반 4개(최대 2.13배)다. HEAD는 look 자세 7,537장에서 위반 1개(1.07배)다.
  위반 5개는 모두 명령 뒤 0.003–0.05초에 찍힌 프레임이다. 기록된 pulse는 발행 목표이고 카메라는 아직 움직이는 중이었다.
  예: dev11 r1 1534는 이전 자세 FK로 다시 풀면 `END_CLIPPED`로 식별하지 않는다. 분리 결과는 [survey_stationary.py](survey_stationary.py)로 재현한다.

- 요약: [shape_survey_summary.json](shape_survey_summary.json). 프레임별 raw는 기본 체크아웃 `outputs/zone-pair-v6-review3-shape-survey/`에 있고 sha256은 요약에 적었다.
- 최소 발췌만 `tests/fixtures/zone_pair_v6_review3/`에 복사했다. JPEG 5장, 자기 입력 기록, 평가 전용 GT이고 `build_fixtures.py`로 만들었다.
- 회귀 테스트는 다음을 확인한다.
  - dev09 r2 1491: 상대 로봇 성분 분리 후 ready, GT 오차가 bound 안이다.
  - dev08 r2 last_tag: 인접 성분이라 가림체 후보가 되고, a+b 정렬은 즉시 실패하지 않고 view를 바꾼다.

### P2

1. **다중 뷰 near-end bias:** 누락 길이를 ptp 대신 fit의 1–99% robust extent(`visible_length_m`)로 계산한다. 먼 끝 너머 작은 같은 색 점이 bound를 줄이지 못하는지 회귀한다.
2. **벽 근처 교착:** 얇은 여유(`gap<.04`) 트리거는 envelope가 마지막 fix 이후 커졌을 때만 발동한다(`reducible`, σ 증가 5 mm/5 mrad). 예정 재관측 횟수 상한도 적용된다.
   - 여유 0.0365 m 반례: 이전에는 재관측 160회·drive 0회였다. 이후에는 재관측 0회로 기존 planner가 0.2초에 `APPROACH_NO_PATH`로 명시 종료한다.
   - 벽 옆 회전 반례: 예정 재관측 23회 뒤 `GLOBAL_ENVELOPE_BLOCKED`로 끝난다. 유한하다.
3. **공용 경로 변경:** `zone_pair_executor.py`의 차단된 명령 배치 처리와 `zone_pair_obstruction.py`의 성분 마스킹은 v5h·b-only에도 적용된다.
   **v5h 조건은 과거 frozen v5h와 동일하지 않다.** 상위 README에도 적었다. 세 조건 사이의 한 플래그 차이는 유지된다.
4. **README 정정:** 상위 README의 삭제된 단일 부분뷰 갱신 설명을 다중 뷰로 고쳤다.
   표식 의존 목록에 형상 대체의 거리 한계를 추가했다. 기준은 bound ≤ 5 cm이고, grip 약 0.43 m(이전 모델)·약 0.47 m(현재 모델) 이상에서는 band 대체에 의존한다.

## 문헌 레시피 반영 (코디네이터 추가 지침)

[lit_review.md](lit_review.md) 요약: 성공 사례는 파지 전 정렬을 물체 기준 look-move로 닫고, 전역 위치는 정렬 중단 조건에 쓰지 않는다.

- **a+b 정렬의 PF 격리:** 정렬·pre-close 중에는 PF HIGH/수렴을 중단 조건에서 뺐다.
  - 대신 `object_anchor`로 벽·팔 여유를 계속 검사한다. 진입 시 전역 envelope와 ready 상대 뷰로 정지한 빔을 세계에 한 번 놓는다.
  - 이후 자기 상대 뷰로 로봇 pose bound를 만든다. 이 bound는 이동 누적으로 커지지 않는다.
  - 두 독립 bound 중 성분별로 더 좁은 쪽을 쓴다.
  - 재관측은 안전 bound 자체의 지원 한계 여유(σxy ≥ 0.10, σyaw ≥ 0.15)나 비-clear일 때만 한다. relook 뒤에는 다시 anchor한다.
  - PF envelope는 `global_safety.pf_reference`로 기록만 한다.
  - 전역 fix가 30초보다 오래돼도 정지 대기 중 여유 인증이 유지된다.
- **정의 등록:** 이 정의는 `beam_relative`(A) 플래그 의미로 `v6_contract.flag_definitions`에 등록했다. 새 조건을 만들지 않았으므로 v5h→b-only→a+b는 여전히 한 플래그씩만 다르다.
- **해시:** `registration_sha256`은 `scripts/zone_pair_authorization.py` 방식(`digest(registration_payload)`)으로 다시 계산해 prereg에 기록했다.
- **초음파 자리:** `closing_command(forward_range_m=None)`에 자기 초음파 거리 인터페이스 자리만 두었다. 아무 판단에도 쓰지 않는다.
- **이번 범위 밖:** 레시피의 접근 도착 판정을 빔 검출로 바꾸는 일과 들기를 2–3단계 증분으로 나누는 일은 하지 않았다.
  접근 중 envelope 재관측은 벽 여유 검사에 필요하므로 레시피로 없어지는 문제가 아니다. 그래서 이중 합산 수정과 예산 분리로 해결했다.

## 동류 감사: 짧은 테스트 조건이 긴 실제 조건의 실패를 가린 곳

| 가린 조건 | 실제 조건의 실패 | 조치 |
|---|---|---|
| 센서 stub이 camera ready 즉시 fix | 지연·실패가 섞이면 예산 소진 | `Scenario(fix_delay_s, fail_every, fail_s)` 추가. 새 접근·회전·정렬 시나리오는 현실 입력을 쓴다. |
| 접근 40 cm 한 번 | spawn→prestation 1 m 이상에서 timeout | 1.05 m 직진·대각, 90° 회전 테스트 |
| 정렬 시작 0.33 m | 정상 진입 0.462 m에서 즉시 실패 | 0.43/0.44/0.462/0.55 m 시나리오 |
| 윗면만 그린 합성 빔 | 실제 렌더의 끝면이 길이 검사를 깨고 grip을 끝면 높이만큼 치우치게 함 | 끝면을 그리는 `box_pixels`. 기존 0.33→0.306 테스트는 식별 가능한 0.36→0.336으로 옮겼다. 정확값 대신 bound 안 오차를 확인한다. |
| 실제 fixture가 형상 경로를 한 번도 통과하지 못함 | 실제 렌더에서 형상 경로 미검증 | 7,537장 survey와 GT 평가, fixture 5장 회귀 |
| 다중 뷰 테스트가 1초 안에 끝남 | relook이 4초 창을 끊으면 세 자세 소진 | 시각 기반 tried 만료, relook 뒤 초기화 테스트 |
| missing-fix 테스트 12.45초 | 예산 두 개의 상호작용 미검증 | 30초로 늘려 예정 6초 → HIGH 10초 순서를 확인 |
| 예정 예산 총량 미사용 | 긴 작업에서 무한 재관측 가능성 | 횟수·총량 한계와 abort 테스트 |
| 벽 옆 시작 미검증 | 정적 얇은 여유에서 재관측 무한 반복 | `reducible` 조건과 벽 옆 테스트 |
| 전역 fix 30초 수명 | 상대 READY 대기(최대 20초)와 정렬이 길어지면 `GLOBAL_ANCHOR_UNKNOWN` | 정렬·pre-close에서 object_anchor 유지 테스트(+31초) |
| envelope 단위 테스트가 작은 이동만 | 긴 이동에서 과대 bound | 이득·방향 전 범위 포함성 검사 |

**확인했지만 바꾸지 않은 것:**

- `zone_pair_align.MAX_LOOKS=8`은 작업 누적이다. b-only는 여러 carry 구간의 regrasp마다 누적될 수 있다. 세 조건 공용 상수라 이번에 바꾸지 않았고 위험으로 남긴다.
- HIGH 복구 10초도 작업 누적이다. 예정 재관측을 분리했으므로 이제는 실제 실패 복구에만 쓰인다.

## 검증

- 요청 범위 전체(`tests/test_zone_pair*.py`, `test_zone_start_dock*`, `test_owncam*`, `test_zone_own*`, `test_zone_study*`, `test_rgb_execution_bundle*`, `test_m1*`, `test_record_owncam*`): **2744 passed, 382 subtests passed, 0 failed** (33분 32초, 부하 평균 40–380에서 실행).
- 새 테스트 `tests/test_zone_pair_v6_review3.py`와 fixture `tests/fixtures/zone_pair_v6_review3/`(JPEG 5장, 발췌 manifest)를 포함한다.
- `prereg_v6.json`: `v6_contract`가 현재 소스 해시와 일치하고 `registration_sha256 = 0fb27e9a…0a34`가 `digest(registration_payload)`와 같음을 확인했다.
- MuJoCo 물리 step·모델 호출·실험 잠금: 0. 물리 dev 실행: 미실행.

## 남은 위험

- **Object-anchored bound:** 진입 envelope와 상대 bound 두 번을 합한 보수적 개발 bound다(약 0.10–0.12 m). 보정된 coverage가 아니다.
  빔이 움직이면 기존 association 검사가 track을 버리고 envelope 경로로 돌아간다. 상대 로봇 위치는 입력이 아니다. 상대 로봇 충돌 여유는 이번에도 직접 검사하지 않는다.
- **끝면 중간 높이 가설:** 최종 실제 grip이 목표 0.162 m보다 약 0.8 cm 멀다. IK 범위 안이지만 파지 성공은 물리 검증 전이다.
- **가까운 시작:** 약 0.35 m보다 가까이서 시작하면 끝면이 모든 고정 자세에서 잘려 식별하지 못하고 명시적으로 실패한다. 후진 재획득은 없다.
- **인접 성분:** dev08처럼 영상에서 붙은 성분은 가림체 후보로 처리한다. 모든 자세에서 붙어 보이면 정렬은 실패한다.
- **표본 조사의 범위:** 단일 프레임 조사다. 폐루프 재생이나 물리 실행이 아니다. 정지 프레임은 대부분 search 자세다(p45 634·inspect 52장). 움직이는 중 프레임이 제어에 들어가지 않는다는 근거는 arm 큐 idle 조건이다. 재생으로는 확인하지 않았다.
- **예산 값:** 예정 재관측 예산 값(6/240/80)은 개발 값이다. 물리 dev에서 실제 fix 지연으로 재검토해야 한다.
- **공정성 해석:** v5h 조건은 과거 frozen v5h와 공용 경로 2건이 다르다.
- **미반영 레시피:** 도착 판정을 빔 검출로 바꾸기, 들기 2–3단계 증분은 반영하지 않았다.
