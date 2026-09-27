# 2026-09-26 자기 카메라 실행기(패키지 F) no-LLM 3대 스모크

**질문.** 패키지 F 실행기(`harness/zone_own_executor.py`)를 쓰면 로봇 3대가 world 하나에서 동시에 움직일 수 있는가? 각 로봇은 자기 손목 카메라와 자기 명령 이력만 쓴다. 또 각 실행기는 deliver 작업의 결과를 평가 전용 GT와 어긋나지 않게 보고하는가(사건, 자기 카메라 확인)? **대화가 아니라 실행기를 시험한다.** 작업은 LLM이 아니라 실험자가 미리 고정한 스크립트가 준다.

**의존성.** PR #201(M1 제어기·위치 추정·계약, `cceb7ee`까지)과 PR #193(자기 RGB 판단)을 읽기 전용으로 병합했다. 스킬 v9(`04a5e3c`)는 #201 안에 들어 있다. 사용법과 API는 [실행기 문서](../../docs/zone_own_executor.md)에 있다.

## 사전 등록 (`prereg.json`, 스모크 데이터 수집 전 커밋)

- **에피소드.** `smoke-s700`, `smoke-s701`. `zone_wide_door_tags_v2`, 목표 A/B/C 청록 1개씩, 추가 상자 빨강 2·초록 1.
  - seed 규칙: 700 이상에서 청록 3개가 서로 다른 pickup 슬롯에 놓이는 처음 두 seed.
  - `dev-s703`: 다음 해당 seed다. 배관 확인 전용이며 결과에 합산하지 않는다.
- **스크립트 작업.**
  - 배정: 로봇을 spawn y 기준 북→남으로 정렬한다. 청록 상자도 설정 y 기준 북→남으로 정렬해 짝짓는다.
  - 목적 슬롯: 북→남 순서로 A2, C2, B2.
  - 시작 시각: 첫 로봇은 바로 `deliver`를 시작한다. 둘째는 `hold(120 s)`, 셋째는 `hold(240 s)` 뒤 `deliver`한다.
  - 스크립트는 실행기 사건만 읽는다.
  - 주문서: 줄마다 청록·1개·목적 구역·개략 pickup 슬롯(`P{열}-{행}`, 패키지 A 규칙)을 담는다. 설정 배치에서 만들며 좌표는 없다.
- **조건.**
  - 동기 SIM(timestep 0.00025 s), 스레드 1, 내 sim 프로세스는 동시에 최대 2개, 부하 평균 기록.
  - weld OFF, `cargo_noslip_v1`.
    - 표기는 "pending user approval"이다. 작업 지시를 따른 것이다. PR #201 `3a03130`에는 2026-09-26 사용자 승인 기록이 있다.
  - 에피소드 SIM 한도 1200 s, 작업당 720 s.
  - 스킬 v9 `mode='m1'`, 교정 `calibration_m1_dev.json`(M1 A6과 같음).
- **게이트 E1–E6.** 모두 통과해야 스모크 통과다.
  - E1: 두 에피소드 모두 `result.json`이 남는다(호스트 예외 없음).
  - E2: 받아들인 작업마다 `job_started` 1개와 종료 사건 1개가 있고, 모든 로봇이 deliver를 받는다.
  - E3: 실행기 k에 들어간 프레임은 모두 로봇 k의 `robot_cam`이다(6 로봇-에피소드에서 `foreign_frames_fed=0`).
  - E4: 모든 자세 출처가 `owncam_pf_v2:*`다.
  - E5: weld OFF(eq_active 최대 0), noslip 반복 > 0.
  - E6: GT상 슬롯이 비어 있는데 `job_done(own_camera_confirmed)`인 경우가 없다.
- **보고만 하고 게이트로 쓰지 않는 것.**
  - 로봇별 m1-style 성공: `scripts/run_m1_owncam.py`와 같은 검사 목록이다. 자기 카메라 출처, 자기 RGB pickup, IN_SLOT 주장, GT 슬롯, 벽 접촉 0, weld OFF, 지도 면 fallback 없음, 한도 안, 배치 프레임 look-back 게이트, 예외 없음, 운반 step의 양손가락 접촉 ≥ 95%, 운반 중 상자 z ≥ 0.04 m.
  - 6개 중 자기 카메라 확인 수.
  - 로봇 간·벽 접촉 step.
  - 작업별 SIM 시간.
  - 평가 전용 위치 오차.
  - 막힘·위치 불확실 사건.
  - 6 로봇-에피소드로 성공률을 주장하지 않는다.
- **정지 규칙.**
  - 같은 커밋 SHA로 두 에피소드를 병렬로 1회씩 돌린다. 실행 중·사이에 코드를 바꾸지 않는다.
  - 인프라 실패(`result.json` 없음)만 같은 SHA로 1회 재실행한다.
  - 로봇 단위 실패도 결과이며 재실행하지 않는다.
  - 수정하려면 새 에피소드 ID와 새 사전 등록이 필요하다.

## 배관 확인 (dev-s703, 결과 아님)

| 확인 | SHA | 결과 |
|---|---|---|
| plumb1 | 미커밋 | 호스트 설정에서 `AttributeError`: v9가 `StaticKeepout`을 다시 내보내지 않는다(#201 A6b와 같은 문제). v6 클래스를 쓰도록 고쳤다 |
| plumb2 (SIM 20 s) | 미커밋 | 작업 시작·사건·프레임 격리 정상. 대기 로봇은 수동 프레임만으로 초기화됐다. r3 평가 오차 p50 12 cm인데 σ는 6 cm였다 → deliver 시작 전에 넓게 한 번 둘러보도록 고쳤다(M1 시작과 같음). wall 104 s(렌더링 3대 × 5 Hz가 주 비용) |
| plumb3 (SIM 300 s) | 미커밋(`1b9d3d9`와 실행기 동일) | r1·r3 `SEARCH_NOT_FOUND`. 주문 슬롯이 P2(x 0.7–1.85)인데 서쪽 관측점(x −0.47)에서 상자까지 1.5–2.1 m라 지평선 근처 몇 픽셀이었다. near·far_coarse 모두 적합되지 않았다(r1 프레임 150·175 직접 확인). r2(P1-2)는 파지해 운반 단계에 들어갔고(평가 전용: 운반 step 100% 양손가락 접촉, 최저 z 0.085 m) SIM 한도로 끊겼다. `blockage_seen` 2회는 pickup의 상자(지도에 없는 물체)를 본 것이다. wall 1588 s, 부하 10.6→157(다른 작업 합산) |
| plumb4 (SIM 170 s) | `cc7a3c5` | 먼 bay는 서쪽 관측점 다음에 추가 관측점을 둔다(`lane_viewpoints`: bay 서쪽 가장자리, 행 사이 통로(행 ± 0.40 m)). 확인 전에 호스트 디스크가 가득 찼다(`OSError: No space left on device`, 여유 1.8 GB, 다른 작업 합산). r1·r2의 프레임 쓰기가 실패했다 → 호스트 I/O 오류는 로봇 실패가 아니라 인프라 실패로 올리도록 고쳤다 |
| plumb5 (SIM 140 s) | `54621bb` | r1: 서쪽 관측점 2곳 → 통로 관측점 (0.70, 0.35)에서 탐색 → 131 s에 상자(1.6, −0.05) 서쪽 접근점(평가 GT 1.19, −0.10)에 도착했다. 한도로 끊김. `blockage_seen`(`door_1` 포함)은 지도에 없는 상자·로봇을 본 것이다. 평가 전용 위치 오차 p50 r1 1.7 cm, r2 5.5 cm, r3 11.8 cm(r3은 대기 중 spawn에서 태그 1개만 보임) |

## 결과 (소스 `4371f36`, 깨끗한 트리, 두 에피소드 병렬 1회씩)

**게이트: E1·E2·E3·E5·E6 통과, E4 문자 그대로는 실패 → 사전 등록 기준 스모크 불통과.**
- E4 (a) 모든 로봇의 자세 출처가 `owncam_pf_v2:757f7f09` 하나다. 이 절은 통과다.
- E4 (b) "자기 RGB 탐색에 도달한 모든 로봇의 `counts_as_m1`이 true"는 실패다.
  - 6개 deliver 작업이 모두 탐색에 도달했다.
  - 그런데 M1 판정기는 탐색이 목표를 **찾았을 때만** `counts_as_m1`을 true로 둔다(`pickup_from_own_rgb`). 그래서 목표를 못 찾은 3대는 false다.
  - 사전 등록 문구가 판정기 정의와 어긋난 것이다. GT를 쓴 것이 아니다. 문구를 사후에 재해석하지 않고 실패로 기록한다.
- 그 밖의 확인:
  - 실행기마다 들어간 프레임은 모두 자기 `robot_cam`이다(6 로봇-에피소드 모두 `foreign_frames_fed=0`).
  - weld eq_active 최대 0, noslip 10.
  - 거짓 확인 0: GT상 슬롯이 비어 있는데 확인한 경우가 없다.

**로봇별 결과.** m1-style 성공 3/6, 자기 카메라 확인 3/6. 확인한 3건은 모두 평가 GT에서 슬롯 안이다.

| 에피소드 | 로봇 | pickup → 목적 | deliver 결과 | 작업 SIM s | m1-style | 평가 전용 메모 |
|---|---|---|---|---:|---|---|
| s700 | r3 (바로 시작) | P1-3 → A2 | `SEARCH_NOT_FOUND` | 69 | 실패 | 상자 (−0.2, 0.75)가 서쪽 관측점(x −0.47)에서 0.27 m 앞이다. 프레임 아래 가장자리에 잘려 적합되지 않았다(r3 프레임 172 확인) |
| s700 | r1 (120 s 대기) | P2-2 → C2 | IN_SLOT, 확인 | 336 | **성공** | 슬롯 오차(자기 RGB) −1.4 / 4.1 cm |
| s700 | r2 (240 s 대기) | P2-1 → B2 | IN_SLOT, 확인 | 412 | **성공** | −0.9 / 0.6 cm |
| s701 | r2 (바로 시작) | P1-3 → A2 | IN_SLOT, 확인 | 298 | **성공** | −0.5 / −1.4 cm |
| s701 | r3 (120 s 대기) | P1-2 → C2 | `SEARCH_NOT_FOUND` | 32 | 실패 | 상자 (−0.2, −0.85). s700 r3과 같은 근거리 잘림이다(plumb3의 같은 배치에서는 찾았다) |
| s701 | r1 (240 s 대기) | P2-1 → B2 | `LOCAL_TIMEOUT` | 720 | 실패 | 먼 관측(far_coarse)으로 가까운 관측점까지 가는 M1 구간에서, 못 본 초록 상자(0.4, −1.65)에 약 660 SIM s 동안 걸려 있었다. 그 사이 `pose_uncertain` 사건이 약 65회 반복됐다 |

- 운반 판정(평가 전용): 성공 3건 모두 운반 step 100%에서 양손가락이 접촉했고, 상자 최저 z는 ≥ 0.083 m였다.
- 로봇 간 접촉 step: 0 (6/6).
- 벽 접촉 step: 0 (6/6).
- 위치 오차 p50(평가 전용): 0.5–7.6 cm. 가장 큰 값은 s701 r1이 걸려 있던 구간이다.
- 에피소드 SIM 654 / 962 s. wall 5357 / 6733 s.
- 1분 부하 평균: 46.6(시작) → 110.5 / 15.6(끝). 다른 작업과 합산한 값이다. 동기 SIM이라 결과에는 영향이 없고 wall만 늘었다.

**해석 범위.**
- 이 스모크는 실행기의 배관·격리·정직한 보고를 시험한 것이다. 3/6은 성공률이 아니다.
- 성공 3건은 M1 사슬(PR #201)이 3대 동시 장면에서도 끝까지 돈다는 사례일 뿐이다. M1 test 코호트와 합산하지 않는다.

**발견한 문제(수정은 새 사전 등록으로).**
1. 서쪽 관측점 x −0.47은 첫 열(x −0.2) 상자에 너무 가깝다.
2. far_coarse 뒤 가까운 관측 구간은 못 본 상자를 피하지 못한다(M1 사슬 쪽).
3. `pose_uncertain` 가장자리 검출에 이력(hysteresis)이 없어 한 자리에서 반복된다.
4. 사전 등록 E4 문구.

## 이슈 #221 수정 뒤 스모크 v2·v3 (같은 동결 시나리오, 2026-09-27)

Codex 적대적 검토 2차(P1 5건·P2 3건)와 품질 감사를 고친 뒤, v1과 같은 시나리오(seed 700/701, 지도·화물·배정·대기 시간·한도 동일)를 새 버전으로 다시 돌렸다. v1 기록·사전 등록·러너는 그대로 두었다. 세 코호트는 합산하지 않는다. 수정 내용은 [실행기 문서](../../docs/zone_own_executor.md)에 있다.

- **회귀 테스트.** 새 테스트를 수정 전 소스 `254d4461`(= `c8a2355a` 실행기 + origin/main)에 복사해 돌렸다: 56 failed / 35 passed(`regression_prefix_254d4461.txt`). v2 뒤에 더한 3개는 `a5b3687e`에서 3 failed였다. 현재 `tests/test_zone_own_executor*.py` 94 passed이고, 관련 테스트를 합쳐 243 passed다.
- **0.40 m 벽 둘러보기 검증**(`calibrate_body_model.py` → `body_model_calibration.json`, MuJoCo, weld OFF, 결과 아님): v1 전체 sweep을 (2.08, 0.18)에서 돌리면 팔-벽 접촉이 222 step 났다(pan 1890–2030). guard 계획은 5개 자세 모두 0 step이었다. 접촉 pan은 모두 guard가 위험하다고 표시한 구간 안이었다. 몸체 구 모델의 잔차는 0.0144 m였다.
- **배관 dev-v2-s703**(`50dba9cd`, SIM 150 s, 결과 아님): 호스트 예외가 없었다. 작업 4개가 종료 사건 1회씩으로 끝났다(`EPISODE_END:SIM_LIMIT` 3건). 늦은 호출은 `EPISODE_ENDED`로 거부됐다. wall 33,608 s에는 Mac 절전(22:58–07:54)이 포함된다.

### v2 (`prereg_v2.json`, 소스 `a5b3687e`)

**게이트 E1–E7 통과**(E4는 v1 문구의 모순을 고쳐 자세 출처만 본다. E7 = 게이트가 uncertain일 때 확인 없음). m1-style **1/6**, 자기 카메라 확인 1/6, 거짓 확인 0, 벽 접촉 0.

- 6개 중 4개가 `<구간>_no_path`로 끝났다(s700 r1 운반, s700 r2·s701 r1 탐색, s701 r3 접근).
- 원인(`diagnosis_v2.json`, 사후, 평가 전용 GT): 진행 감시가 "명령 주행 6 s" 규칙으로 정체를 선언했다. 그 keep-out(0.20 m 앞)이 구간 목표나 문 차로를 덮어 계획이 3회 실패했다.
  - 정체 5건 중 3건은 거짓이었다. 목표 0.07 m 앞의 느린 접근, 긴 둘러보기 뒤 주행, 그리고 이동 중이었다.
  - 진짜 정체 2건: s701 r1은 v1과 같은 초록 상자, s701 r3은 목표 상자 자체에 닿았다.
- v2 수정이 v1보다 나빠진 결과다. 다음 판에서 고쳤다.

### v3 (`prereg_v3.json`, 소스 `92e0feeb`, 러너 `run_smoke_v3.py` = v2 러너 + v3 파일 목록)

v2 대비 바뀐 점:
- 정체는 자기 명령 이동량 0.40 m 이후의 믿을 만한 추정으로 판단한다. 믿을 만한 추정이 없으면 먼저 확인용 둘러보기를 한다.
- 정체 keep-out을 목표 0.45 m·문 0.60 m 안에 두지 않는다. 복구 뒤 계획이 없으면 `blocked`로 끝낸다.
- 접근 구간에서는 목표 상자도 장애물로 둔다.

**게이트 E1–E7 통과.** m1-style **4/6**, 자기 카메라 확인 4/6, 거짓 확인 0, 로봇 간·벽 접촉 0.

| 에피소드 | 로봇 | pickup → 목적 | deliver 결과 | 작업 SIM s | m1-style | `pose_uncertain` | 메모 |
|---|---|---|---|---:|---|---:|---|
| s700 | r3 | P1-3 → A2 | `SKILL_GRASP_TARGET_NOT_VISIBLE` | 95.9 | 실패 | 0 | 근거리 잘림 → 한 번 물러나 다시 봄 → 상자 찾음(v1은 `SEARCH_NOT_FOUND`). 파지 단계에서 스킬 v9가 상자를 잃었다(v2와 같음) |
| s700 | r1 | P2-2 → C2 | IN_SLOT, 확인 | 342.0 | **성공** | 2 | v2는 문 앞 정체 keep-out으로 `CARRY_LEG_no_path` |
| s700 | r2 | P2-1 → B2 | IN_SLOT, 확인 | 409.0 | **성공** | 2 | |
| s701 | r2 | P1-3 → A2 | IN_SLOT, 확인 | 301.3 | **성공** | 2 | |
| s701 | r3 | P1-2 → C2 | IN_SLOT, 확인 | 432.1 | **성공** | 3 | 근거리 잘림 → 물러나 다시 봄(v1은 `SEARCH_NOT_FOUND`) |
| s701 | r1 | P2-1 → B2 | `SEARCH_LEG_blocked` | 182.2 | 실패 | 5 | v1과 같은 초록 상자(0.4, −1.65)에 막힘(평가 GT: 마지막 40 s 이동 0.002 m). 복구 2회 뒤 명시 실패와 `blockage_seen(own_progress_stall)`. v1은 720 s 한도까지 걸렸고 `pose_uncertain` 66회였다 |

- 둘러보기 pan 제한은 로봇당 1–3회였고, 물러나기는 0–1회였다(모두 문 근처). 벽 접촉은 0이었다.
- 위치 오차 p50(평가 전용): 0.2–8.2 cm.
- 에피소드 SIM 651 / 554 s. wall 4347 / 3913 s.
- 1분 부하 평균: 60.5(시작) → 19–29(끝). 다른 작업과 합산한 값이고, 동기 SIM이라 결과에는 영향이 없다.

**해석 범위.**
- 6 로봇-에피소드로 성공률을 주장하지 않는다. v1/v2/v3는 같은 시나리오의 서로 다른 코호트이고 합산하지 않는다.
- v3는 v2 결과를 보고 고친 판이다. 같은 두 seed에서 다시 쟀으므로 개선 폭을 일반화하지 않는다. 새 seed의 확인은 다음 판의 몫이다.
- 짝 상태 채널은 단독 운반이라 트래픽이 0이다. 공동 운반 검증은 M2의 몫이다.

**남은 문제.**
1. s700 r3: 스킬 v9 파지 단계의 근거리 적합 상실(PR #181 범위).
2. s701 r1: 탐색 중 지도에 없는 상자에 막히면 실패로 끝난다. 다른 관측점으로 돌아가는 판단은 연구 층의 몫이다.
3. M1 파지 스킬 내부 macro 구간은 진행 감시 밖이다.

## TensorBoard

스냅샷 `outputs/tensorboard/0926-zone-own-executor-smoke`(로봇-에피소드 6개 + PR #201 dev-a8 단일 로봇 기준 2개)은 `build_results.py --tensorboard`로 만들었다. 공용 서버(6006)에서 8 run이 로드되는 것을 API로 확인했다. 표시값(`evaluation/reported_success`, `result/sim_s`, `result/commands`, `result/wall_s`, `result/model_calls=0`)도 원본과 일치했다. 보기 설정은 `outputs/tensorboard-view.json`의 `zone_own_executor_smoke_20260926`에 있다. `result/sim_s`는 deliver 작업 시간이고, `result/wall_s`는 3대 에피소드 전체 wall이다.

v2·v3는 새 스냅샷 `0927-zone-own-executor-smoke-v2`(`exec2-*` 6 run)와 `0927-zone-own-executor-smoke-v3`(`exec3-*` 6 run)이다. `build_results_v2.py` / `build_results_v3.py --tensorboard`로 만들었다. v1 run은 다시 변환하지 않고 보기 필터로 함께 보인다.
- 보기 키: `zone_own_executor_smoke_v2_v3_20260927`. run filter는 `^092[67]-zone-own-executor-smoke(-v[23])?/exec`, 고정 카드는 success·sim_s·commands·model_calls·wall_s·`offline/pose_uncertain_events`·`offline/stall_recoveries`다.
- `offline/*`는 원본 result.json의 실행기 안전장치 계수다(진단용이며 성공·시간이 아니다). v1 run에는 이 태그가 없다.
- 공용 서버(6006)에서 20 run이 로드되는 것을 API로 확인했다. 대표 값(success, sim_s, `pose_uncertain`)이 원본 JSON과 일치했다.

## 파일

- `run_smoke.py`: 러너. 결과·manifest·로봇별 입력·실행기 로그와 `eval_only/`를 분리해 쓴다.
- `prereg.json`: 사전 등록.
- `build_results.py` → `results.json`(게이트·로봇별 표), `raw_index.json`(원본 JSON/JSONL 파일별 SHA-256). 스모크 원본은 `smoke-4371f36/`에 있다.
- v2·v3: `prereg_v2.json`·`prereg_v3.json`(사전 등록), `run_smoke_v2.py`·`run_smoke_v3.py`(러너; 예외·중단 시 부분 로그와 `failure.json`을 남기고 world를 닫으며 기존 에피소드를 덮어쓰지 않는다), `build_results_v2.py`·`build_results_v3.py` → `results_v2.json`·`results_v3.json`, `raw_index_v2.json`·`raw_index_v3.json`. 원본은 `smoke-v2-a5b3687e/`, `smoke-v3-92e0feeb/`, 배관은 `dev-v2-50dba9cd/`.
- `diagnosis_v2.json`(v2 실패 원인, 사후), `regression_prefix_254d4461.txt`(수정 전 테스트 결과), `calibrate_body_model.py` → `body_model_calibration.json`.
- 원본: `/Users/changmin/projects/ugrp/outputs/zone-own-executor-20260926/`. 로컬에만 있고 원격 백업이 아니다.

## 참고 자료

PR #206 본문의 "참고 자료"와 같은 목록이다.
- 논문: 새로 인용한 논문은 없다.
- 공개 코드: Nav2(https://github.com/ros-navigation/navigation2, commit `7b9bcb4c2d68`, Apache-2.0). `nav2_controller/plugins/simple_progress_checker.cpp`(기준 자세·이동 반경·허용량 구조)와 `nav2_behaviors/plugins/back_up.cpp`(뒤로 물러나기)의 설계를 옮겨 적응했다. 코드는 복사하지 않았다.
  - 그 밖: MuJoCo 3.12.0(Apache-2.0, 호스트·몸체 교정만), OpenCV 5.0.0.93(Apache-2.0), PythonRobotics(MIT, `b2020cd`, #201 경유), NumPy 2.5.2, pytest 9.1.1.
  - 쓰지 않은 것: python-fcl·trimesh·shapely(환경에 없고 바이너리 의존성이 필요하다. 필요한 도형은 구 대 직사각형 기둥뿐이다). 학생 안에서 MuJoCo 충돌 질의(실행 중 시뮬레이터 상태 금지).
- 저장소 안: `harness/visual_arm.py`(순기구학), `harness/zone_study_contract.py`·`harness/zone_event_scheduler.py`·`harness/zone_map_schematic.py`(import), `harness/m1_owncam_delivery.py`·`harness/owncam_drive*.py`·`harness/owncam_pose_source.py`(#201/#178/#197), `harness/wrist_zone_skill_v9.py`(#181), `harness/zone_own_perception.py`(#193), `harness/zone_color_boxes.py`, `harness/team_carry_status.py`(#200, 범위 설명), #229 abort 우회, 환경 v3 기록(#208 M3).
- 문서: Nav2 두 소스 파일, `docs/tensorboard.md`, `docs/execution_versioning.md`, Codex 설계 문서.
