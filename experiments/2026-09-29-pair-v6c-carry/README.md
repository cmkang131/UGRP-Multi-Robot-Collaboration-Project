# 공동 운반 b-v6c: 단계 4(운반)·5(내려놓기) stage probe 첫 측정 (2026-09-29, Claude)

**stage probe, not E2E success.** 모든 물리 결과는 PR #260 단계 probe 하네스로 단계 하나만 통과시킨 결과다. E2E 성공도, 학생 성공도 아니다.
조건: weld OFF, `cargo_noslip_v1`, 모델 호출 0. 제어기에는 정답(GT)을 넣지 않는다. GT는 staging(teacher 예외)과 `eval_only/` 판정에만 쓴다. AprilTag는 쓰지 않는다(아래 '한계'의 개발 지도 주의 참고). 초음파는 번들이 켜지 않았으므로 쓰지 않았다.
**제어기는 고치지 않았다.** 진단 전용 패치는 probe 프로세스 안에서만 적용했고 전부 따로 표시한다. 진단 패치의 결과는 제어기 결과가 아니다.

Refs #221. #263(b-v6c, 단계 2·3 결과)의 후속이다. 실험 ID `2026-09-29-pair-v6c-carry`.

## 한 줄 요약

| 단계 | 조건 | 이전 | b-v6c 기준선 (수정 없음) | 진단 전용 패치 (원인 확인용, 제어기 결과 아님) |
|---|---|---:|---:|---|
| 2 정렬 | (참고) #263 | b-only 0/25 | 13/25 | 이번 범위 아님 |
| 3 파지+들기 | (참고) #263 | b-only 8/23 | 22/23 | 이번 범위 아님 |
| **4 운반** | 경로 leg 0·1·3·6·7, 정답 staging 뒤 첫 leg | v5h 0/1 (#260), b-v6c 스모크 0/1 | **0/33** (L0 0/13, L1·L3·L6·L7 각 0/5) | σ 고정: nominal 12/24, 경계 L0·L1 10/10씩. 세 패치 합성(`carry_all_three`): nominal **24/24**, L3 경계 10/10 |
| **5 내려놓기 (목적지)** | 영역 B 중심 근처, 경로의 마지막 단계 | **신규** | **0/13** (전부 `OWN_IMAGE_INVALID`) | 이미지 검사를 끄고 σ 고정: 0/13 (`COLLISION_GUARD`). σ≈0에 이미지 끔: 1/3 |
| 5 내려놓기 (픽업 위치, 예전 위치) | 예전 하네스 위치 | v5h 1/1 (#260), b-v6c 스모크 1/1 | 3/3 | – |

분모는 **staged**(teacher가 자세를 만들 수 있었던 경우)다. 19셀 격자에서 6셀은 teacher IK 범위 밖이라 제어기가 돌지 않았고, 분모에서 뺐다(아래 '분모'). 이전 숫자가 없는 칸은 "신규"다.

- **운반은 기준선에서 어느 leg도 통과하지 못한다.** 33건 모두 leg 시작 뒤 2.4–3.3 s(중앙 2.8 s)에 `SELF_POSE_UNCERTAIN`/yaw로 끝난다. 팔을 든 채 절대 위치 보정 없이 가면 yaw σ가 게이트(3°)까지 자라기 때문이다.
- **σ 확산을 막으면(진단) leg 0·1·2·6은 통과하지만 옆 이동 leg 3·4·5는 `MOTION_ERROR`로 0/9다.** 옆 이동의 열린 고리 배율이 실제보다 작아 빔이 15.6 % 더 간다.
- **목적지 내려놓기는 운반보다 더 앞에서 막힌다.** r1 자기 영상이 어두운 바닥에서 거절되고(기준선 0/13), 이를 우회해도 내려놓은 뒤 물러나는 동작이 동쪽 벽(`wall_east`)에 부딪히는 판정으로 끝난다.
- 세 패치를 합친 24/24는 "이 세 가지를 고치면 운반 leg가 통과할 수 있다"는 뜻이지 b-v6c가 운반한다는 뜻이 아니다.

## 버전

| 항목 | 값 | 이유 |
|---|---|---|
| 실행 번들 / workflow | **번호를 쓰지 않았다.** main `98efe0e6`의 `zone-pair-v76-fixclock-grasp-entry`, workflow `2.12.0` 그대로 | 이 PR은 probe 진단 하네스와 기록만 바꾼다. 등록된 제어기·번들·workflow 코드는 바이트 그대로다 |
| 정책 | `b-v6c` = `posterior_relook` + `exact_fix_clock` + `grasp_range_entry` | #263에서 병합. 이번에는 바뀌지 않음 |
| probe | `PROBE_VERSION 0.4.5` (0.3.0에서 0.4.0–0.4.5로 올림) | 아래 '하네스 변경' |
| 실행 소스 | 아래 raw별 SHA. 기준선은 `b604499d`(probe 0.4.1), 마지막 물리 실행은 병합 뒤 `cc84a791` | 코호트 동안 소스 고정(러너가 `source_changed`를 기록, 전부 False) |
| main 기준 | `98efe0e6` (#263 병합, 번들 v76, workflow 2.12.0)을 `cc84a791`에서 병합 | 병합 전 실행(`b604499d`…`0a96718b`)의 제어기 경로는 병합 뒤와 같다는 것을 병합 뒤 연속성 실행 2건으로 확인(아래) |

**병합 뒤 연속성.** 병합 전에 돌린 결과가 병합 뒤 main에서도 같은지 두 셀로 다시 확인했다(`cc84a791`).
- 기준선 carry L0 nominal s911: 병합 전 0/1(`POSE_UNCERTAIN`/yaw, r1, SIM 3.1 s)과 같은 결과(stage 3.1 s, 제출 후 2.65 s).
- 세 패치 합성 carry L3 nominal s911: 병합 전과 같은 1/1(SIM 22.2 s, 기본 명령 416개).
- 이것은 두 셀의 재현일 뿐이며 전체 격자를 병합 뒤에 다시 돌린 것이 아니다.

번호 예약 조정: 이 PR은 bundle/workflow 번호를 쓰지 않는다(조정자 메시지의 v81 · workflow 2.13.0은 코드가 바뀌는 PR을 위한 예약이라 쓰지 않았다).

### 하네스 변경 (제어기 아님)

| probe | 변경 |
|---|---|
| 0.4.0 | 운반을 경로 leg별로(`--legs 0…7`), 내려놓기를 목적지(`--legs end`)로 측정. leg 끝점 오차·횡 오차·yaw 표류를 판정 지표에 추가. 실패 원인 코드. 진단 전용 패치 `fix_age_round`, `loaded_yaw_gate_wide`, `pf_rest_no_abs_noise`, `rest_noise_off_and_gate_wide` |
| 0.4.1 | 목적지 내려놓기 admission 영상 우회(staging 보조, 제어기 아님). `OWN_IMAGE_INVALID` 원인 |
| 0.4.2 | `STAGING_IK_ENVELOPE` 원인(분모에서 제외). 패치 `image_valid_off`. staged 통과율 |
| 0.4.3 | 패치 `sigma_held_at_prior` |
| 0.4.4 | 패치 `carry_lateral_scale_measured`, `carry_all_three` |
| 0.4.5 | 패치 `sigma_held_tiny`, `setdown_sigma_tiny_image_off` |

TensorBoard 변환기(`scripts/build_pair_stage_probe_views.py`)도 함께 고쳤다: 같은 셀을 다른 raw에서 다시 돌렸을 때 view 이름 충돌, 오프라인 감사 변환기가 받는 이름(`gate/…`)으로 σ 스칼라 태그를 바꿈. 각각 회귀 테스트가 있다(`tests/test_pair_stage_probe.py` 42건).

## 측정 방법

### 단계 정의와 시작 상태

| 단계 | 시작 | 끝(제어기 전이) | 예산 |
|---|---|---|---:|
| 4 운반 | teacher가 빔을 두 로봇이 든 자세로 놓는다(들림, 두 집게 접촉). 제어기는 E2E 정합 사전분포(σ 0.03 m, 0.012 rad)로 시작 | 해당 leg를 끝내고 `_wait_lower`로 넘어가는 순간(`probe_exit_carry`) | 90 s |
| 5 내려놓기 | 같은 자세에서 시작. 목적지는 영역 B 중심 근처 경로의 마지막 단계 | 내려놓고 열고 물러난 뒤 `done` | 60 s |

- **teacher 예외.** 시작 자세는 정답으로 만든다. 제어기는 정답을 못 본다. 정답은 `eval_only/` 관측기만 읽는다.
- **경로.** 개발 지도 `zone_wide_door_tags_v2_dock_v3`. L0 0.55 m(축 방향) → L1 0.85 m(폭 0.5 m 문 통과) → L2 0.8 m → L3·L4·L5 옆 이동 각 0.7167 m → L6·L7 축 방향 각 0.7 m(영역 B 안으로). 목적지 내려놓기는 마지막 단계다. 영역 B 중심 (4.6, −2.1), `wall_east` 안쪽 면 x = 5.375 m.
- **한 leg를 한 번에 하나만 측정한다(단계 probe).** 앞 leg가 남기는 오차(열린 고리 누적)는 이 측정에 들어가지 않는다. 8 leg를 이어서 도는 E2E가 아니다.

### 판정 기준 (GT, eval-only)

| 단계 | 기준 |
|---|---|
| 4 운반 | 든 채 유지(높이 ≥ 3 cm), 기울기 ≤ 10°, 두 집게 접촉, 빔 이동 거리와 계획 leg 길이의 차 ≤ 10 cm(`leg_error`), 빔 끝점과 계획 경로점의 거리 ≤ 10 cm(`end_error`, 횡 오차 포함) |
| 5 내려놓기 | 빔이 바닥에(높이 ≤ 5 mm), 기울기 ≤ 3°, 두 로봇 집게 모두 떨어짐, 이동 ≤ 5 cm |

기준값은 개발 가설이며 모든 결과에 raw 지표와 함께 기록돼 있어 나중에 다른 임계값으로 다시 적용할 수 있다.

### 격자와 분모

- **셀 19개.** nominal × 3 seed(911–913) + 단일 오프셋 12(along ±12 mm, lat ±8 mm, yaw ±0.035 rad, 각각 같은·반대 부호) + 모서리 4. 기준선은 L0과 목적지 내려놓기에 19셀 전부, L1·L3·L6·L7에는 nominal 3 + along+/same, lat+/same, corner++/same, yaw+/same의 7셀을 썼다.
- **`STAGING_IK_ENVELOPE`(분모 제외).** 19셀 중 6셀(along+/same, along+/opp, along−/opp, corner++/same, corner++/opp, corner−−/opp)은 teacher의 `solve_grip_ik`가 보정된 파지 범위(14.5–18.0 cm) 밖이라 ValueError를 낸다. 제어기가 돌지 않았으므로 통과도 실패도 아니다. 그래서 along ±12 mm 경계는 사실상 측정되지 않았다(along−/same만 staged). 경계 격자에서 staged는 10/16이다.
- **seed는 PF 난수만 바꾼다.** 물리는 같으므로 seed 반복은 독립 증거가 아니다.
- **시간.** SIM 시간 기준이다. wall 시간과 부하는 참고용이다.

### 원인 코드

한 케이스의 실패를 하나의 코드로 분류한다(`harness/pair_stage_probe.CAUSES`): `SELF_POSE_UNCERTAIN`(자기 위치 σ가 유지 게이트 위, 세부 `sub`로 yaw / yaw+xy), `COLLISION_GUARD`(명령 가드가 팔·베이스 명령을 거절), `MOTION_ERROR`(제어기는 끝냈지만 빔이 계획점에서 벗어남), `OWN_IMAGE_INVALID`(자기 영상 검사 실패), `ENTRY_ERROR`(staged 입장 거절), `STAGING_IK_ENVELOPE`(분모 제외) 외 몇 가지.

## 결과 1: 단계 4 운반, 기준선 (`b-v6c`, 수정 없음) 0/33

| raw | leg | staged 통과 | 원인 | 처음 실패 로봇 | stage SIM s (min / 중앙 / max) | 제출 후 처음 실패까지 (중앙) | 기본 명령 수 (중앙) |
|---|---|---:|---|---|---|---:|---:|
| `b604499d-carryL0` | 0 | **0/13** (계획 19, 불가능 6) | `SELF_POSE_UNCERTAIN`/yaw 13 | r1 8, r2 5 | 3.0 / 3.2 / 3.8 | 2.75 s | 49 |
| `b604499d-carryL1367` | 1 | **0/5** (7, 2) | 위와 같음 5 | r2 3, r1 2 | 3.2 / 3.4 / 3.8 | 2.95 s | 53 |
| | 3 | **0/5** (7, 2) | 위와 같음 5 | r1 3, r2 2 | 3.0 / 3.4 / 3.7 | 2.95 s | 52 |
| | 6 | **0/5** (7, 2) | 위와 같음 5 | r1 2, r2 3 | 3.1 / 3.5 / 3.7 | 3.05 s | 55 |
| | 7 | **0/5** (7, 2) | 위와 같음 5 | r2 5 | 2.9 / 3.3 / 3.6 | 2.85 s | 51 |
| 합계 | | **0/33** | `SELF_POSE_UNCERTAIN`/yaw 33 | r1 15, r2 18 | 2.9–3.8 | 2.75–3.05 s | 49–55 |

- 모든 실패의 거절 이유는 `POSE_UNCERTAIN`(yaw)이다. 33건 모두 실패 원인이 같아서 leg·오프셋 경계에 따른 차이가 나타나지 않는다. **오프셋과 무관한 구조적 실패다.**
- 이 33건은 운반이 시작되고 SIM 3.8 s 안에 끝났다. 빔은 이동을 거의 시작하지 못했다(기본 명령 49–55개).
- 이전 숫자는 #260의 v5h carry 0/1과 b-v6c 스모크 0/1(같은 원인, 3.1 s)뿐이다. 이번 격자는 그것을 33건으로 넓혔다.

## 결과 2: 단계 5 내려놓기, 기준선

| raw | 위치 | staged 통과 | 원인 | 비고 |
|---|---|---:|---|---|
| `b604499d-sdEnd` | **목적지** (경로의 마지막 단계) | **0/13** (19, 6) | `OWN_IMAGE_INVALID` 13 (r1, 이유 `INVALID_OWN_IMAGE`) | stage SIM s 없음(admission에서 거절, 제어기는 SIM_LIMIT 11건·`STUDY_LAYER_DONE` 2건으로 끝남), 기본 명령 0개, case wall 중앙 324 s |
| `b604499d-sdPickup` | 예전 픽업 위치 | **3/3** | – | SIM 8.75 s, 기본 명령 70개, case wall 중앙 89 s |

- 목적지에서는 r1의 자기 영상이 어두운 바닥 때문에 `zone_pair_vision.valid_frame`에서 거절된다. 그래서 내려놓기가 시작도 하지 못한다. 예전 픽업 위치에서는 같은 정책이 3/3으로 통과한다. 하네스가 만든 조건(바닥 밝기·벽과의 거리)이 목적지와 다르다는 것이 이 차이의 원인이다.
- 목적지 기준선은 이번이 첫 측정이다("신규").

## 원인 진단 (진단 전용 패치, 제어기는 그대로)

### 막힘 1: 운반 중 σ 확산 (절대 위치 보정 없음) — 실측

**증상.** 기준선 33건이 leg 시작 뒤 약 3 s에 유지 게이트(`GATE_LOADED`: xy 0.07 m, yaw 3° 높은 값 / 2.5° 낮은 값, 들어갈 때 0.6 s·나올 때 0.4 s 체류)의 yaw 항목에서 멈춘다.

**측정** (기준선 33건, 같은 33건의 기록):

| 항목 | 최소–최대 | 중앙 |
|---|---:|---:|
| 운반 시작 시 σ_yaw | 0.0343–0.0374 rad | 0.0359 rad (2.06°) |
| 운반 시작 시 σ_xy | 0.019–0.038 m | 0.0275 m |
| 운반 시작 시 마지막 fix 나이 | 4.40–4.60 s | (teacher staging의 `tags_temporary` fix) |
| 처음 실패 시 σ_yaw | 0.0489–0.0529 rad | 0.0524 rad (3.00°, 게이트 값) |
| 처음 실패 시 σ_xy | – | 0.0284 m (변하지 않음) |
| 시작 뒤 처음 실패까지 | 2.4–3.3 s | 2.8 s |

**원인.** 든 상태의 운동 모델 `motion_loaded.noise_abs = [0.01494, 0.00382, 0.09762]`가 정지해 있어도 속도 잡음을 넣는다. 그래서 절대 위치 보정이 없는 동안 σ_yaw가 약 0.0218·√t rad로 자란다(산술). 시작 σ_yaw 0.036 rad가 게이트 0.0524 rad(3°)까지 자라는 데 약 2.8 s가 걸린다. 실측과 맞는다.
- 운반 중에는 태그를 쓰지 않는다(운반은 tag-blind이고 빔이 시야를 가린다). 그래서 fix가 없다. 시작 fix는 teacher staging이 준 것이다.

**진단 패치가 보인 것.**
- `loaded_yaw_gate_wide`(yaw 게이트를 12°/10°로 넓힘): 0/23. yaw는 넘어가지만 다음 게이트(yaw+xy `POSE_UNCERTAIN`)에서 멈추거나(L0, L3, L6, L7), 옆 로봇과의 스윕 가드(`PAIR_COLLISION_GUARD`, 여유 `0.02 + 0.015 + 2·σxy + 2·σyaw·lever`)에서 멈춘다(L1 0/2, SIM 11.4 s). 게이트만 넓혀서는 부족하다.
- `sigma_held_at_prior`(보고 σ를 사전분포 0.03 m / 0.012 rad로 제한): L0·L1·L2·L6 통과. 아래 표.

### 막힘 2: 옆 이동 leg의 열린 고리 배율 — 실측

`scripts/study_owncam_pair_beam.py`의 `CARRY_ODOM_SCALE = {'axial': .772, 'lateral': .697}`은 dev 601 run 7d97bab에서 한 번 맞춘 정적 보정값이다. σ를 사전분포에 고정한 9건에서 옆 이동은 계획보다 빔이 15.6 % 더 갔다.

| 실행 | leg | seed | 빔 이동 (계획 0.7167 m) | 끝점 오차 (한계 0.10 m) | 횡 오차 | yaw 표류 |
|---|---|---:|---:|---:|---:|---:|
| `e1c99f99-dxSigma` | 3 | 911 | 0.8291 | 0.1124 | 0.0025 | −0.144° |
| `e1c99f99-dxSigB` | 4 | 911 | 0.8291 | 0.1125 | 0.0025 | −0.145° |
| | 5 | 911 | 0.8290 | 0.1124 | 0.0026 | −0.152° |
| `e1c99f99-dxSigC` | 3 | 912 | 0.8287 | 0.1120 | 0.0028 | −0.171° |
| | 3 | 913 | 0.8290 | 0.1123 | 0.0025 | −0.149° |
| | 4 | 912 | 0.8290 | 0.1123 | 0.0024 | −0.146° |
| | 4 | 913 | 0.8290 | 0.1124 | 0.0025 | −0.146° |
| | 5 | 912 | 0.8285 | 0.1119 | 0.0030 | −0.182° |
| | 5 | 913 | 0.8288 | 0.1121 | 0.0027 | −0.164° |

- 끝점 오차 0.112 m이 한계 0.1 m를 넘어 `MOTION_ERROR`(`end_error`, `leg_error`)다. 횡 오차(0.0024–0.0030 m)와 yaw 표류는 작다. **한 방향(진행 방향) 길이 배율이 틀린 것이다.** 필요한 배율은 약 0.806이다.
- 배율을 0.806으로 바꾸는 진단(`carry_lateral_scale_measured`)에서 L3–L5는 빔 이동 0.712 m(비 0.994), 끝점 오차 0.0046 m로 통과한다.
- 축 방향 leg는 반대로 조금 길게 간다(끝점 오차/계획 길이로 약 +1.5 % ~ +4.9 %). 합성 실행의 끝점 오차는 L0 0.0085, L1 0.0419, L2 0.0371, L6 0.0271, L7 0.0274 m로 전부 한계 0.10 m 안이다. L1의 0.042 m은 한계의 42 %다. 8 leg를 이어 갈 때의 누적은 이 단계 probe가 측정하지 않는다.

### 막힘 3: 목적지 (영상 검사 + 물러남 여유)

**(a) 영상 검사.** 기준선 0/13은 전부 r1의 `OWN_IMAGE_INVALID`다. `image_valid_off` 실행에서 실제 판정 횟수를 세니 r1은 프레임 338개 중 176개 수락 / 162개 거절(약 48 %), r2는 339개 전부 수락이다. `valid_frame`은 밝기(V) 8 미만 픽셀이 25 % 이상이면 거절하고 대비(1–99 백분위 차 ≥ 15, 표준편차 ≥ 3)도 요구한다. 목적지 바닥이 어두워 r1이 이 검사에 걸리는 것으로 보인다(어느 항목인지는 분해하지 않았다). 운반 L7도 같은 원인으로 끝난다(σ 고정 실행에서 0/3, r1).

**(b) 물러남.** 영상 검사를 우회하면(`image_valid_off`) 내려놓은 뒤 물러나는 동작(6 s, 전진 −0.04, 0.15 s 명령)이 r2를 `wall_east` 쪽으로 보낸다. 그러면 `motion_clear`가 실패한다(`PAIR_COLLISION_GUARD`, r2). 저장소의 `SweepGuard.chassis_clearance`로 오프라인 계산했다([retreat_clearance.py](retreat_clearance.py) · [출력](retreat_clearance.txt)). r2 내려놓기 자세 (5.018, −2.1, π), 차체 x(−0.15, 0.1) y ±0.09, 여유 = 0.02 + 0.015 + 2·σ_xy + 2·σ_yaw·lever:

| σ_xy (m) | σ_yaw (rad) | 내려놓는 순간 벽과의 여유 (m) | 벽에 닿기까지 물러난 거리 (m) |
|---:|---:|---:|---:|
| 0.000 | 0.0000 | 0.172 | 0.174 |
| 0.012 | 0.0096 | 0.145 | 0.146 |
| 0.030 | 0.0096 | 0.109 | 0.110 |
| 0.034 | 0.0096 | 0.101 | 0.102 |
| 0.050 | 0.0096 | 0.069 | 0.070 |

통과하는 내려놓기의 전체 물러남은 로봇당 0.163 m(예전 픽업 위치 3/3의 GT 값)이다. σ_xy ≥ 0.012 m이면 물러날 자리가 모자란다. `image_valid_off` 5건은 GT 기준 0.083–0.093 m 물러난 뒤 멈췄다(r2 x 5.018 → 5.096–5.111, SIM 12.7–13.0 s).

**(c) σ를 거의 0으로 해도 여유가 얇다.** σ_xy 0.001 m / σ_yaw 0.0005 rad, 이미지 검사 끔(`setdown_sigma_tiny_image_off`): 1/3(s913 통과, s911·s912 `COLLISION_GUARD` r2, SIM 8.6 s). σ가 0이어도 여유는 물러난 거리보다 약 0.011 m 클 뿐이다. 목적지 지오메트리가 얇다는 뜻이다.

## 결과 3: 진단 전용 패치 격자 (제어기 결과 아님)

| 패치 | 무엇을 바꿨나 | 경우 | 통과 | 실패 |
|---|---|---|---:|---|
| `loaded_yaw_gate_wide` | yaw 게이트 12°/10° | L0 (일부 실행, 12건 중단), L1 2, L3·L6·L7 각 3 | 0/23 (완료 raw 11건은 0/11, 중단 raw 12건은 0/12) | yaw+xy `POSE_UNCERTAIN`(L0 7, L3·L6·L7 9), `COLLISION_GUARD` r2 (L1 7) |
| `image_valid_off` | 영상 검사를 항상 통과 | 목적지 내려놓기 5 | 0/5 | `COLLISION_GUARD` r2 5 |
| `sigma_held_at_prior` | 보고 σ를 0.03 m / 0.012 rad로 제한 | nominal 24 (leg 0–7 × seed 911–913, s911은 leg 0·1·3·6·7·2·4·5 나눠 실행) | 12/24 | leg 0·1·2·6: 12/12; leg 3·4·5: `MOTION_ERROR` 0/9; leg 7: `OWN_IMAGE_INVALID` 0/3 (r1) |
| `sigma_held_at_prior` 경계 | L0 · L1의 16셀 | staged 10 + 10 | **10/10, 10/10** | – (6셀씩 IK 범위 밖) |
| `carry_lateral_scale_measured` (0.806) + `sigma_held_at_prior` + `image_valid_off` = `carry_all_three` | 세 패치 합성 | nominal 24 (leg 0–7 × seed 911–913) | **24/24** | – |
| `carry_all_three` 경계 | L3의 16셀 | staged 10 | **10/10** | – (6셀 IK 범위 밖) |
| `carry_all_three` | 목적지 내려놓기 19셀 | staged 13 | **0/13** | `COLLISION_GUARD` r2 13 (벽 쪽 물러남) |
| `setdown_sigma_tiny_image_off` | σ≈0, 영상 검사 끔 | 목적지 nominal 3 | 1/3 | `COLLISION_GUARD` r2 2 |

- 합성으로 통과한 운반의 SIM 시간과 명령 수: L0 19.2 s / 356개, L1 25.7 / 486, L2 24.6 / 464, L3–L5 22.2 / 416, L6·L7 22.5 / 422. seed 3개가 같은 값을 냈다(물리는 같고 PF 난수만 다르다).
- `sigma_held_at_prior`의 nominal 12/24는 s911 3/5 + 1/3, s912·s913 8/16의 합이다. leg 3·4·5·7만 실패한다.
- **합성의 한계.** 세 패치를 따로 돌린 것은 아니다. σ 고정만 leg 0·1·2·6에서, 배율 패치는 σ 고정과 함께 leg 3–5에서, 영상 끔은 leg 7에서 효과를 본 것을 합쳐서 24/24를 얻었다. 각 패치를 단독으로 돌렸을 때 leg 3–5와 L7이 어떻게 되는지는 남은 다른 실패가 가릴 수 있다(예: 배율 패치 단독은 σ 확산이 먼저 막는다).
- 패치 실행에서 기록된 σ는 제한값이다. PF가 실제로 갖는 σ는 로그에 없다.

## 물리 격자 실행

### 실행

- 실행 방법: `scripts/ugrp_session.py run`으로 driver 셸 스크립트를 띄웠다. driver는 자기 PID로 `agent_lock`을 잡고 EXIT에서 해제한다. 러너는 `python -m scripts.run_pair_stage_probes … --execute --lock-owner claude`다. 실행 인자는 raw에 저장되지 않아 이 README의 조건 열은 `cases.jsonl`과 manifest에서 복원한 것이다.
- **병렬 유닛은 최대 2개.** 기준선은 `--workers 2` 한 줄, 진단은 `--workers 1` 줄 최대 2개를 동시에 돌렸다(조정자 지시). 시작·종료 때 `uptime` 1분 부하 평균을 기록했다(아래 표).
- 다른 에이전트의 작업이 같은 Mac에서 돌았다(부하 8–50). 판정은 SIM 시간이며 wall 시간은 비교하지 않는다.
- 러너는 `OMP_NUM_THREADS=2`를 코드에 고정한다(worker당). 바꾸지 않았다.
- 모든 raw의 manifest는 `state=completed`, `source_changed=False`다. 예외 하나(`7ded27cc-dxGate`)는 중단됐다(아래).

| raw (`/Users/changmin/projects/ugrp/outputs/pair-stage-probes-` 뒤) | 소스 | 조건 | 계획 → staged | 통과 | wall | 부하 (시작 → 끝) |
|---|---|---|---|---:|---:|---|
| `b604499d-carryL0` | b604499d (0.4.1) | 기준선, 운반 L0, 19셀 | 19 → 13 | 0 | 428.5 s | 18.3 → 45.5 |
| `b604499d-carryL1367` | b604499d | 기준선, 운반 L1·L3·L6·L7, leg당 7셀 | 28 → 20 | 0 | 528.8 s | 45.5 → 23.7 |
| `b604499d-sdEnd` | b604499d | 기준선, 목적지 내려놓기, 19셀 | 19 → 13 | 0 | 1978.3 s | 23.7 → 29.6 |
| `b604499d-sdPickup` | b604499d | 예전 픽업 위치 내려놓기 (참고) | 3 → 3 | 3 | 168.5 s | 29.6 → 27.9 |
| `7ded27cc-dxGate` | 7ded27cc (0.4.2) | `loaded_yaw_gate_wide` (**중단**) | 12건만 기록 | – | – | 30.3 (시작만) |
| `7ded27cc-dxGateB` | 7ded27cc | 같은 패치, L1 nominal·lat | 2 → 2 | 0 | 282.2 s | 38.1 → 21.4 |
| `7ded27cc-dxGateC` | 7ded27cc | 같은 패치, L3·L6·L7 nominal 3씩 | 9 → 9 | 0 | 1480.8 s | 21.4 → 31.3 |
| `7ded27cc-dxImg` | 7ded27cc | `image_valid_off`, 목적지 | 5 → 5 | 0 | 488.5 s | 31.3 → 28.9 |
| `e1c99f99-dxSigma` | e1c99f99 (0.4.3) | `sigma_held_at_prior`, leg 0·1·3·6·7 s911 | 5 → 5 | 3 | 1179.8 s | 21.9 → 21.8 |
| `e1c99f99-dxSigB` | e1c99f99 | 같은 패치, leg 2·4·5 s911 | 3 → 3 | 1 | 849.7 s | 18.8 → 27.2 |
| `e1c99f99-dxSigC` | e1c99f99 | 같은 패치, leg 0–7 s912·s913 | 16 → 16 | 8 | 2240.0 s | 29.3 → 13.5 |
| `e1c99f99-dxSigD` | e1c99f99 | 같은 패치, L1 경계 16셀 | 16 → 10 | 10 | 1362.0 s | 13.5 → 22.4 |
| `e1c99f99-dxSigE` | e1c99f99 | 같은 패치, L0 경계 16셀 | 16 → 10 | 10 | 1121.7 s | 20.3 → 16.1 |
| `3061a66e-dxAllC` | 3061a66e (0.4.4) | `carry_all_three`, leg 0–7 s911 | 8 → 8 | 8 | 1081.6 s | 22.2 → 13.8 |
| `64767041-dxAllC2` | 64767041 | 같은 패치, leg 0–7 s912·s913 | 16 → 16 | 16 | 2268.3 s | 14.0 → 20.2 |
| `64767041-dxAllD` | 64767041 | 같은 패치, L3 경계 16셀 | 16 → 10 | 10 | 1460.0 s | 12.7 → 21.2 |
| `64767041-dxAllS` | 64767041 | 같은 패치, 목적지 내려놓기 19셀 | 19 → 13 | 0 | 768.7 s | 16.4 → 18.2 |
| `0a96718b-dxTinyS` | 0a96718b (0.4.5) | `setdown_sigma_tiny_image_off`, 목적지 nominal | 3 → 3 | 1 | 117.9 s | 21.9 → 16.5 |
| `cc84a791-postBaseL0` | cc84a791 (병합 뒤) | 기준선 L0 nominal s911 | 1 → 1 | 0 | 22.9 s | 21.2 → 14.6 |
| `cc84a791-postAllL3` | cc84a791 | `carry_all_three` L3 nominal s911 | 1 → 1 | 1 | 88.3 s | 14.6 → 16.9 |

**결과표에 넣지 않는 실행 (보존).**
- 스모크: `099f4466-smoke`(probe 0.3.0, carry L0 0/1 `POSE_UNCERTAIN` 3.1 s, 예전 위치 내려놓기 1/1 8.75 s, wall 80.1 s, 부하 20.8 → 29.1), `836ea32d-smoke2-carry-L3`(0.4.0, L3 0/2 `SELF_POSE_UNCERTAIN`/yaw r1, stage 3.4–3.6 s, wall 51.7 s, 부하 20.9 → 19.9), `836ea32d-smoke2-setdown-end`(0.4.0, 목적지 0/1 `ENTRY:ADMISSION_SELF_INVALID_IMAGE`, wall 24.0 s, 부하 19.9 → 23.6). 하네스 동작 확인용이며 해당 하네스 버전에서만 유효하다.
- `7ded27cc-dxGate`: `loaded_yaw_gate_wide`로 돌던 중 소스를 바꾸려고 중단했다. `cases.jsonl` 12건(L0 7건 yaw+xy `POSE_UNCERTAIN`, L1 5건 `COLLISION_GUARD`)만 있고 `summary.json`과 `artifacts.sha256.json`은 없다. 표와 TensorBoard에서 제외했다. 같은 패치를 `dxGateB`(L1)와 `dxGateC`(L3·L6·L7)로 다시 돌렸다.

## raw와 해시

모든 raw는 `/Users/changmin/projects/ugrp/outputs/`에 있고 **로컬에만 보관한다**(원격 백업 아님). `cases.jsonl`과 `summary.json`은 이 폴더에 같은 바이트로 복사했다(`cases_<이름>.jsonl`, `summary_<이름>.json`, 합계 약 0.6 MB). 집계 출력은 [tabulate_all.txt](tabulate_all.txt) · [tabulate_all.json](tabulate_all.json)이고 [tabulate.py](tabulate.py)가 만든다. 오프라인 계산은 [retreat_clearance.py](retreat_clearance.py) · [.txt](retreat_clearance.txt).

| raw | 파일 · 크기 | `artifacts.sha256.json` | `cases.jsonl` | `summary.json` |
|---|---|---|---|---|
| `pair-stage-probes-b604499d-carryL0` | 2,329 · 43M | `585be075d671ae813d95e92cc9e0c345d3780d898c3a38c6a201acf3f3642393` | `9f383f697d4a0a42ca15197f628b46ce0e0fc16f8c75333df402601625222cb1` | `9ba4929cd8874693b8d835ecbb4c96dbbce2ac18378d6e87445b79e93838270d` |
| `pair-stage-probes-b604499d-carryL1367` | 3,584 · 65M | `4fafe0c808a336e7f46dc13b0ac79f2bc9bc16a05fb22410585a755cbeff0b1a` | `a83f4ac48849e813d336e199fde89a97b54ad4053546ae5c3ec6b104e13bc887` | `71bee9eb1d09ccb8db361d2888fafee055cfe2538eb98d0a44cb0e42998d6969` |
| `pair-stage-probes-b604499d-sdEnd` | 11,204 · 173M | `f5da4ff9cbd4323bc199c61a5b07df1ce550bfbb9afce7392026c2af6dfb2a82` | `1afe957098fafaa03cd84927fd334a088c20c3c78d6d7c08bac607eeb1baf32c` | `e18ad04824ee44a8451e458756ed88fb4029be3732dc6ade0bb7da3b72bc1adc` |
| `pair-stage-probes-b604499d-sdPickup` | 902 · 19M | `e2c37957935d2d42733e5a193d5dac41be523e987e30e707ee73699f4b82da54` | `c06a6dbfd2fafc557def933274be3f484fef5ebf2a351a37dbd534c179e65247` | `eae0c6962142c6fe202bad17f47bac673e903c19ccace55ee3e88fe52ae3777d` |
| 중단: `pair-stage-probes-7ded27cc-dxGate` | 4,917 · 81M | 없음(중단) | `246a6e3a66c0d1006ee69e9b403c4bbdcab05fcc97e41d8640354e5ed662cd2f` | 없음 |
| `pair-stage-probes-7ded27cc-dxGateB` | 737 · 12M | `67e2db549ad7bf25b3654f56828dcc889658b1268868425143974bb945cbccca` | `c2fa165d5b166bb0d38fbe2e808879267478132c7e3a6a535ffbcca68203d6b9` | `945ce0bb44619a8a586f4121e549cd5cdf518f1fe513e1ec55bae72506253e0a` |
| `pair-stage-probes-7ded27cc-dxGateC` | 3,741 · 62M | `3f331cd082ede30afdd46a12b9795c740292d916fec7103fc8f17092f71903e9` | `0493fcef9eb35187e58b918cd3e0bfb6be6bfbc13888efe6e5938c7408748178` | `a499fa3f7bc5d99b3e912d54bc1207107f741356e62922801b6a24b11c6e1e51` |
| `pair-stage-probes-7ded27cc-dxImg` | 1,316 · 24M | `28c7f78c0229d8e509fe3a1706ade1f246f1f7690e3485dc096213be25eac348` | `4d576c8abd66fdc6a73e6efe1052f8bebd24e1984a043dadcb83b6d0061e207c` | `dd39a0cdb57a24bf32604a8b2af4cc57a1f278729483d1b9a471e578f3fd6d3a` |
| `pair-stage-probes-e1c99f99-dxSigma` | 3,094 · 50M | `d6b268c736ae2fa9e6b0006b5574ff1933411a66c9aa02f873cb2a327a542eca` | `922246ec4e2c50229fc6e1c671aea9f52eda2ae5797304205791b208353a6671` | `538901220788cf6cbccf25de22f1922a0ec1999781d93debf53b5c2f92c8543e` |
| `pair-stage-probes-e1c99f99-dxSigB` | 2,089 · 34M | `dfd4a599e5c4828deca36230aa5b3cfb41d129d9c9eb3ebba7b5666527334799` | `73bd4f5eaa44e5a3aef1787d80a4a1aad1bebadc5ac2bb69fdc07d0e19d88580` | `e399bbdf1be97562a91dc30231ce8a7a3fe74273f4f5b152261e91d3fd07733f` |
| `pair-stage-probes-e1c99f99-dxSigC` | 10,359 · 167M | `7ac65c52c360c90d83000f65e34418895db75f9f7da8afd45d987bb01283f204` | `3becab20b997ed4114ef69375c53fc47558b412c2c3271aa33d67254a14b5c4d` | `a98a8f7a639316458a9f1e119925c3559996de13bda29392feb0a33c590c5629` |
| `pair-stage-probes-e1c99f99-dxSigD` | 7,443 · 120M | `e85e7047cc8fae006175921877eb975513929e157be046c87e0e19dc32b271b6` | `70ada100ad99f261f84848f818936130f50e423bf9b3b781be6410d464ae6670` | `c768870048c45d30916ed2508437d9b3bfcc8db3557c3c0b79b2b603a22d1207` |
| `pair-stage-probes-e1c99f99-dxSigE` | 5,813 · 95M | `02002bf2476373f4d8d9c1e55280b023a53ffc5c93336fea98dfc520fd94c990` | `449ce345bc617655a9c2c7d67b5ba5a6b5ad3e1fd237d58348932c47f93b9b9c` | `d35ffd8223fb2b11d1b56382f63fe7fa1be9c5069bcbec8debbeef792cedcd3e` |
| `pair-stage-probes-3061a66e-dxAllC` | 5,182 · 84M | `17c8dcac58f1b373179da1465c846b7b3f73be81c6b846a8bb5c5d491f0cf402` | `09b084825f0f034c1aba514395353c43f05ab969967bc2e4abef69c40e1dba35` | `664680f847e97b4474ecb3af94080f7f907e24695faf8a50028510c5fa6c025c` |
| `pair-stage-probes-64767041-dxAllC2` | 10,359 · 167M | `af294ecd64f0d9d73d72355036adc530cdff34b41ee983fc27357c4e57a07e1c` | `7df9ae0ad61f92f8a3533c5ef9455e09d743f9292de1722c9e825a17bcd31a04` | `ce0ae78f4e134ca96b574f2b11ffad4edb585c9a496144754b27ca11ed31ce31` |
| `pair-stage-probes-64767041-dxAllD` | 6,563 · 106M | `5798bc8ce7909c6661ddf7b09f0d43e19e158979f266a7ab007a48baaf987c4a` | `ae4a303ca90706aed4d4fe9a8200db97a79e59eb55dd51f34fa6534e010ddbb5` | `eb8e7cb6e59a82cfc84d3eb23a9c92821a1da01ae3cca0cc68740aa6c2ce2b83` |
| `pair-stage-probes-64767041-dxAllS` | 3,676 · 67M | `cd2851f637f05145aab256cf1f1b633d787e1eb205e304b324d32e15ed77279d` | `1f9061e1c5c444c98d8e447e0f3cc512622d41a0ce2d27a3d5386db4b53c9cad` | `4ea8cd747933f54b7e7bdc7a9527d95d762da38efa3991c40b562fb970ddab56` |
| `pair-stage-probes-0a96718b-dxTinyS` | 896 · 17M | `8f16b3ecdd86722d58ce44acb89dcda1b4f5b265221f89ca1abc0cd26c2d0721` | `8ca6dfbda8ddfc22260e4de9efed15a397bce674bfa7c41d5c6441fdc21b3183` | `4471c93fa1a48df711b14d2ac6346f2272610ed4db514d5e3906067201ffbf63` |
| `pair-stage-probes-cc84a791-postBaseL0` | 164 · 3.1M | `a3f4118bb87022e23e07238888329f45d89c424ba3805c30e6a0f19f368e2678` | `0f295b540612b41a2c9c6b4dfe11f9cf275bfbddd6da7541feedd544665180dd` | `225a57046c28839bc792d8703933b585cd8b5359d48a1bbfd019dab556feaac0` |
| `pair-stage-probes-cc84a791-postAllL3` | 641 · 10M | `0641bb6dfbcf200a9279648ba2fc510ed4af1b4f5f80dd20e20b24777cae94cd` | `4bc9340eb499c2f647601faccb0fda6b55c7eb761410ccec1d5d42bf0ff13db5` | `75fa478c16a52bae66c0ad32a7c0e8d01a4dfda39208a3a61a92225071f5c74c` |
| 스모크: `pair-stage-probes-099f4466-smoke` | 463 · 9.4M | `40ae29a91f268a91c51f71d4c121146b9d25efae0caceb4bdb51265dbfd682f8` | `91cee7174f18a278725001b9f7735294d02d849305c2d96cf79f5a3a1a6a0ede` | `16c451a8e0040fa2af90bbabd20e8081d1e791cbc9ed18ad5a7dc072f685b690` |
| 스모크: `pair-stage-probes-836ea32d-smoke2-carry-L3` | 342 · 6.2M | `d616a5f5df434f735a09c505de50ea44094fdc1dd8da8949b00503cda0d7ec57` | `0472d7d984a264774f567dc711d478f7abb7968de3007ea68b64762873118d8f` | `7b0672654b99143df8877f1d3a932ab720e4bc96202bcb3bbf24e3b0517b49f3` |
| 스모크: `pair-stage-probes-836ea32d-smoke2-setdown-end` | 97 · 1.8M | `dd27f99a500e779163ada998ee24f8b3448afe1d876305107906b11caca8cecd` | `c6d1a85234e7c5c9fc0d33fc48b679f3b619c3fc16dbf2b5529c6f5f3524e641` | `76c9951cf7f772ff8eddc42455fa07635c8836aa36ff0af19ab03bbf183874d0` |

이 폴더의 산출물 sha256: `tabulate_all.txt` `f2f173223d8971d77365b5702165376ee8e933e7c1825ee3c1169fda5a005304`, `tabulate_all.json` `be60b25b40720c1ccdc72536136548bce021a8c241262931ab234be9425c4c6d`, `retreat_clearance.txt` `ada462800dd5ee843d4eacff39cc2ae061913c6c699e7e5aa5603f979bf1cfcc`, `retreat_clearance.py` `31b67216e42e3b88c91236584a8f27e0e58f0a1b21a669c328488c48e6c5e5ba`.

driver log sha256 (`outputs/pair-stage-probes-<sha8>-<이름>-driver.log`, 각 실행의 시작·종료 시각과 `uptime`을 담는다):

| driver log | sha256 |
|---|---|
| `b604499d-base1` | `202a329f1e2e4109e7152e2510e0827a3de08c229ed606ffabbc9e9927695586` |
| `7ded27cc-diag1` | `24dfd6732c6776c5b009c4091b0cd5abad0f2cadec2cb256ba2c5c826a9b5993` |
| `7ded27cc-diag2` | `0055f83175943d4a032044612b7db74740db57352dc049b5496e691b9b12079b` |
| `e1c99f99-diag3` | `1f854d6e5de9802bb0cc165df60c6642c6968532fba72814042673d32f8cd3fd` |
| `e1c99f99-diag4` | `04e52a4da8ea6d57205397b20c5f4030f2bd2164c16ccfca39141c2f44ce3316` |
| `e1c99f99-diag4b` | `6c65ac4f5d7c24d83d8f8b7b453c0f15d63a94d65c86a358c6d33b69abb4bb0a` |
| `3061a66e-diag5` | `47510b9f77b7317a8b24e25c9208bc5bc53dfc2e0e7b78faf5c3fbebc8dc2e23` |
| `64767041-diag6` | `ddd22c7f1abfcf6d6c385d8fe0ce8fab7536038678e2aa361cac96ea9d72276c` |
| `64767041-diag6b` | `3ecb3bd80a479cd3808df5e7463994b35cec3e8442fd82ed65c3c799455c2990` |
| `64767041-diag7` | `93f72d64243fd109f109e3d29cf43ade4e9709b0da53404a5fe96fa900dcf755` |
| `0a96718b-diag8` | `a80bfc4d55e074895356e16c50c555bbd0fcabdd2c09e5ddaaf17d5a3a8bbbec` |
| `cc84a791-diag9` | `97e89417eb7b2643a47d636d0bec81b6a753dfc300ff42138c24853bdfc5cef1` |
| `099f4466-smoke` | `384664f2227a97651d8765a47171fbc4c811db971c2eed60999061e39555f6d5` |
| `836ea32d-smoke2` | `14b9e1eaf06be42e7ef10d9f6ef23f1c6757537e49bf407f207cc8a6708ee0c4` |

**환경** (모든 manifest 공통): python 3.12.13, macOS 27.2 arm64, mujoco 3.12.0, numpy 2.5.2, opencv-python-headless 5.0.0.93, Pillow 12.3.0, gymnasium 1.3.0. 실행 소스 트리 해시(앞 12자리): `6cf4c23b48ae`(b604499d), `3765ece0bb34`(7ded27cc), `0611dc744a52`(e1c99f99), `61a1dea76687`(3061a66e·64767041), `74494c3465a5`(0a96718b), `83bf5e962d26`(cc84a791). 뒤쪽 manifest에서 `source_dirty: True`인 것은 미추적 파일 `retreat_clearance.*`가 있었기 때문이며 실행 소스는 바뀌지 않았다.

## TensorBoard

- **스냅샷.** `/Users/changmin/projects/ugrp/outputs/tensorboard/0929-pair-stage-probes-v6c-carry`, run 224개(경우별 205 + 그룹 집계 `ALL-*` 19). `collection.json` sha256 `bae69c7c782b2d25f9ab0df97ff8929841827d83246491e14d6df5c3c61282e2`. 기존 스냅샷은 건드리지 않았다.
- **파생 뷰.** `outputs/pair-stage-probes-tbviews-0929-v6c-carry`(index sha256 `bf37dd1ea3dba200025707b109bdbd87d54b7f37012b5791bed7cae7d8445a66`). 빌더 `scripts/build_pair_stage_probe_views.py`, 변환기 `scripts/tensorboard_tools/offline_audit.py`. 중단된 `dxGate`와 스모크 3건은 뷰에서 뺐고 19개 raw만 넣었다.
- **검증 1.** EventAccumulator로 205개 경우 run과 19개 집계의 값(`offline/stage_pass`, `offline/pass_rate`, `result/sim_s`, `result/wall_s`, `result/commands` 등)을 원본 raw·뷰와 비교했다. 불일치 0건이다(`result/sim_s`·`result/wall_s`는 float32라 허용오차 1e-3·1e-2로 비교).
- **검증 2.** 공용 서버(다른 작업 소유, 재시작하지 않음)의 `/data/runs`에 새 run 224개가 모두 있다(서버 전체 2052 run).
- **대시보드.** `outputs/tensorboard-view.json`의 `pair_stage_probes_v6c_carry_20260929` URL. 고정 카드는 `evaluation/reported_success`, `offline/pass_rate`, `offline/stage_pass`, `result/sim_s`, `result/wall_s`, `result/commands`, `result/model_calls`. run filter `^0929-pair-stage-probes-v6c(-carry)?/`로 #263 스냅샷을 함께 보인다. 공용 키 파일은 쓰기 직전에 다시 읽고 내 키만 추가했다(117개 키).
  - run이 500개를 넘는 공용 logdir라서 처음 열면 "unselected" 안내가 뜬다. 헤더 체크박스를 눌러 선택하면 7개 카드에 값이 그려지는 것을 브라우저에서 확인했다. HParams 열 선택은 UI 상태라 저장하지 않았다.
- **이름.** `C-` = b-v6c. `ca` = 운반, `sd` = 내려놓기, `t` = teacher 격자. `-pE` = E2E 정합 사전분포. `-dx`+글자 = 진단 패치(G `loaded_yaw_gate_wide`, N `pf_rest_no_abs_noise`, V `image_valid_off`, S `sigma_held_at_prior`, L `carry_lateral_scale_measured`, A `carry_all_three`, T `sigma_held_tiny`, D `setdown_sigma_tiny_image_off`). 끝의 `-L<n>`은 leg, `-Lend`는 목적지.
- 집계 `offline/pass_rate`(통과/계획, 괄호는 staged): carryL0 0/19(13), carryL1367 0/28(20), sdEnd 0/19(13), sdPickup 3/3, dxGateB 0/2, dxGateC 0/9, dxImg 0/5, dxSigma 3/5, dxSigB 1/3, dxSigC 8/16, dxSigD 10/16(10), dxSigE 10/16(10), dxAllC 8/8, dxAllC2 16/16, dxAllD 10/16(10), dxAllS 0/19(13), dxTinyS 1/3, postBaseL0 0/1, postAllL3 1/1. `offline/staged_pass_rate`는 staged 분모다.

## 다음 막힘 (앞에서부터)

1. **운반 중 σ 확산 + 게이트 (제어기, 최우선).** 기준선 0/33이 전부 같은 원인이다. 든 채 절대 위치 보정이 없으면 σ_yaw가 약 2.8 s 만에 게이트 3°에 닿는다. 다른 모든 운반 결과가 이것에 가려 있었다.
2. **옆 이동 열린 고리 배율.** σ 확산을 풀면 L3·L4·L5가 다음으로 `MOTION_ERROR`를 낸다(0/9, +15.6 %). 정적 보정값 0.697이 맞지 않는다(필요 약 0.806).
3. **목적지.** 영상 검사(r1의 어두운 바닥, 기준선 0/13)와 물러남 여유(벽 0.17 m, 물러남 0.163 m)가 겹친다. σ를 0으로 해도 1/3이다.

나머지 단계 2(정렬 13/25)와 단계 3 잔여 실패는 #263의 다음 막힘 목록 그대로다.

## 수정 제안 (README에만 기록, 이 PR에서 고치지 않음)

| 막힘 | 제안 | 근거 |
|---|---|---|
| 1 σ 확산 | (a) 정지·미동 구간에서 운동 잡음을 움직인 거리·각도에 비례시킨다(정지하면 σ가 자라지 않음). (b) 게이트와 가드 여유를 σ가 아니라 σ의 변화 속도와 남은 leg 길이로 판단한다. (c) 절대 보정을 준다: 번들이 켠 경우의 초음파(허용 입력), 또는 leg 중간에 태그·정적 지도 특징을 다시 본다 | Thrun·Burgard·Fox의 odometry 운동 모델은 잡음을 이동량에 비례(α1–α4)시킨다. Nav2 AMCL도 `alpha1…alpha5`와 `update_min_d`·`update_min_a`로 움직이지 않으면 갱신하지 않는다 |
| 2 옆 이동 배율 | 정적 계수를 dev 601 값에서 다시 잰다(이번 측정 약 0.806). 더 낫게는 자기 추정으로 고리를 닫는다(leg 끝에서 지도 대비 확인). 열린 고리 계수는 지형·하중이 바뀌면 다시 틀어지므로 "지형/하중 성능은 실제 검증 없이 확정하지 않는다" 원칙과도 맞다 | Borenstein·Feng UMBmark: 체계적 오도메트리 오차는 보정하지만 지면·하중에 따라 달라 검증이 필요하다 |
| 3 목적지 | (a) 어두운 바닥에서 유효 영상 판정을 재검토한다(V < 8 픽셀 25 % 기준). (b) 물러남을 벽을 아는 형태로 바꾸거나 짧게 한다. (c) 끝 로봇 뒤에 약 0.4 m를 비운다(지도 배치). 여유 식을 σ 크기에 덜 민감하게 만든다 | MoveIt Task Constructor pick-and-place의 retreat는 `MoveRelative`에 `setMinMaxDistance`로 범위를 준다 |

### 후속 작업 제안

- teacher IK 범위 확장(along ±12 mm 경계와 모서리 셀이 측정되지 않는다).
- 태그가 없는 지도에서의 운반 증거(최종 환경은 태그 0개다).
- 위 제어기 수정 3가지를 각각 새 정책 플래그로 등록하고, 패치 없이 이 격자를 다시 돌린다.
- 8 leg를 이은 누적 오차는 이 probe가 재지 않는다. 수정 후 이어 달리기 probe가 필요하다.

## 한계

- **stage probe이며 E2E가 아니다.** teacher 정답으로 자세를 만들고 한 leg만 돌린다. 진단 패치의 통과는 제어기 성공이 아니다.
- **개발 지도에는 AprilTag가 있다.** 단계 시작 창에서 fix가 태그로 만들어지고(`fix_source: tags_temporary`), 운반 자체는 tag-blind다. 최종 환경은 태그 0개이므로 시작 fix가 태그 없이 얻어진다는 증거는 이 측정에 없다.
- **통로·지형 지도는 측정하지 못했다.** 통로 지도는 하네스가 `UNSUPPORTED_PAIR_MAP`을 내고(`harness/zone_pair_executor.py`), 영역 지도는 지형이 없다(`"terrain": []`). 조정자가 요청한 통로·지형 조건은 이번에 측정하지 못했다.
- **teacher IK 범위.** 19셀 중 6셀이 staging 불가라서 경계 셀이 얇다(along−/same만 staged).
- **진단 격자는 줄였다.** 병렬 2개 제한과 부하 때문에 leg 2·4·5·7은 nominal 시작만 돌렸다. 경계 격자는 L0·L1(σ 고정)과 L3(합성)에만 있다.
- **기록된 σ는 제한값이다**(패치 실행). 세 패치는 따로 돌린 결과가 아니라 합성 결과다.
- **seed는 PF 난수만 바꾼다**(물리 반복은 독립 증거가 아니다).
- **목적지 admission 영상 우회**(probe 0.4.1)는 staging 보조다. 제어기 측정이 아니다.
- **"처음 실패" 시각 규약이 두 가지다.** stage 시작 기준(`stage_sim_s`)과 제출 기준(`fail_after_submit_s`). 표는 제출 기준을 쓴다.
- **기준선 목적지 내려놓기는 `stage_sim_s`가 없다**(admission에서 거절, 실행은 SIM_LIMIT까지 이어진다).
- **부하.** 같은 Mac에서 다른 에이전트가 돌았다(부하 8–50). SIM 시간 판정에는 영향이 없지만 wall 시간은 비교할 수 없다.
- 전체 raw는 로컬에만 있다.

## 참고 자료

- S. Thrun, W. Burgard, D. Fox, *Probabilistic Robotics*, MIT Press 2005, 5장 odometry 운동 모델(잡음을 이동량에 비례, α1–α4). 막힘 1의 확산 모델 제안 근거.
- Nav2 AMCL 설정(`alpha1…alpha5`, `update_min_d`, `update_min_a`): https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/others/configuring_amcl/
- J. Borenstein, L. Feng, "Measurement and correction of systematic odometry errors in mobile robots," IEEE Trans. Robotics and Automation 12(6):869–880, 1996 (UMBmark). 막힘 2의 보정 방식.
- MoveIt Task Constructor, Pick and Place tutorial (retreat의 `MoveRelative` + `setMinMaxDistance`): https://moveit.picknik.ai/main/doc/tutorials/pick_and_place_with_moveit_task_constructor/pick_and_place_with_moveit_task_constructor.html
- robot_localization `FilterBase::processMeasurement`: https://github.com/cra-ros-pkg/robot_localization/blob/ros2/src/filter_base.cpp (#263에서 인용한 상태 시각 규칙)
- R. R. Burridge, A. A. Rizzi, D. E. Koditschek, "Sequential Composition of Dynamically Dexterous Robot Behaviors," IJRR 18(6):534–555, 1999 (단계 사이의 funnel 합성; 운반 끝 집합 ⊆ 내려놓기 입장 영역). 단계 probe를 앞 단계 종료 상태에서 시작하는 근거.
- 저장소 내부: `experiments/2026-09-29-pair-v6c/README.md`(#263, b-v6c 단계 2·3), `experiments/2026-09-28-pair-stage-probes/README.md`(#260, 단계 probe 기준선), `harness/zone_own_guards.py`(`GATE_LOADED`), `harness/zone_pair_vision.py`(`valid_frame`), `scripts/study_owncam_pair_beam.py`(`CARRY_ODOM_SCALE`), `harness/pair_stage_probe.py`(`CAUSES`, `CRITERIA`), 조정자 지시(`docs/tensorboard.md`, `docs/execution_versioning.md`).
