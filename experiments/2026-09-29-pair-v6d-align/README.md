# 공동 운반 v6d: 정렬 단계의 PF 운동 모델 + 빔 윗면 색 (2026-09-29, Claude)

**stage probe, not E2E success.** 모든 물리 결과는 PR #260 단계 probe 하네스로 단계 하나만 통과시킨 결과다. E2E 성공도, 학생 성공도 아니다.
조건: weld OFF, `cargo_noslip_v1`, 모델 호출 0. 제어기에는 정답(GT)을 넣지 않는다. GT는 staging(teacher 예외)과 `eval_only/` 판정에만 쓴다.

Refs #221. #263(v6c, 병합됨)의 후속이다. v6c 정렬 13/25의 실패 12건을 원인별로 나누고, 원인 두 개를 opt-in 정책 `b-v6d`로 고쳤다.

## 한 줄 요약

| 단계 | 조건 | 이전 (`b-v6c`) | v6d (`b-v6d`) |
|---|---|---:|---:|
| 2 정렬 | teacher 격자 + E2E 체크포인트, E2E 정합 사전분포 (같은 25셀) | **13/25** | **25/25** |
| 3 파지+들기 | 허용오차 경계 23셀, E2E 정합 사전분포 (회귀 확인) | **22/23** | **22/23** (셀마다 같은 판정) |

- **정렬.** 실패 12건이 모두 통과했다. 마지막 정렬 yaw 오차의 최댓값은 115 → 37 mrad(기준 52 mrad)다. 정렬 SIM 시간은 34.0–38.6 s, look 명령은 262–272개로 v6c 통과 13셀(35.7–39.5 s, 262–283개)과 비슷하다(v6c `ALIGN_RELOOK_NO_FIX` 6건은 20.5–35.5 s에 조기 종료).
- **독립 궤적 기준.** 25셀 중 nominal 3시드와 E2E 체크포인트 3시드는 같은 궤적이다(SIM 시간·명령 수 동일). 궤적이 서로 다른 셀은 19개이고, v6c는 9/19, v6d는 19/19다. 25/25는 시드 25번의 독립 증거가 아니다.
- **파지 회귀 없음.** 단계 3은 셀 23개 모두 v6c와 판정·SIM 시간(7.3 s)·look 명령(176개)이 같다. v6d의 새 플래그는 정렬 상태에서만 켜지므로 예상된 결과다. 실패 셀도 같다(corner+−+, r2 `LOAD_NOT_HELD_AFTER_LIFT`).
- **범위.** 이 결과는 개발 격자의 paired 확인이다. 원인은 v6c 실패 셀을 재생해 찾았으므로 held-out 결과가 아니다.

## 버전 (사용한 ID)

| 항목 | 값 | 이유 |
|---|---|---|
| 실행 번들 | `zone-pair-v80-align-widehue-finemotion` (**v80**) | 조정자 배정. #263 병합 뒤 main 번들 v76에 이어 배정받았다. v76은 `RETIRED_BUNDLE_IDS`로 옮겼고 `llm_driver.json`에 v80을 등록했다 |
| workflow `zone-study-integration-run` | **`2.13.0`** | main 2.12.0(#263) 다음. 단계 4/5 probe 쪽(#266)은 병합됐고 workflow 버전을 바꾸지 않아 2.13.0은 겹치지 않았다 |
| 정책 | `b-v6d` = `b-v6c` + `align_fine_motion` + `beam_wide_hue` | 새 플래그 2개는 opt-in. v5h·b-only·a+b·b-v6c 동작은 바뀌지 않는다 |
| 등록 revision | `v6d` ([prereg_v6d.json](prereg_v6d.json), DRAFT, `CURRENT_REVISION`) | 파일 sha256 `cbdb4b2503d928e141131b893cb56060fd6fe54292ef1667da9f57bdeea39972`, `registration_sha256` `1a1529963a320d6644f5f1f6ff3120c0fbcffb737840772d74dc4530292290e3`. 적대적 검토 반영(플래그 설명·probe 버전) 뒤 한 번 다시 봉인했다. 이전 봉인 값(파일 `4c403253…`, 등록 `f4bcd84e…`)은 이 값으로 대체됐다 |
| v6c 봉인 | `prereg_v6c.json` 바이트 그대로, historical | `scripts/zone_pair_v6_contract.py`가 v6/v6b/v6c를 봉인 커밋(v6c는 `be95f8b018bb110e2fc97ec5a3c90e357a949449`)의 blob으로 감사한다. v6c 소스를 고치지 않고 v6d revision으로 분리했다 |
| probe | `PROBE_VERSION 0.5.0` (`b-v6d` 추가) | 정렬 정책 목록과 TensorBoard 뷰 접두어(`D-`) 추가. **raw의 0.4.0은 두 가지 코드 상태(#265, #266 smoke)에서 나왔고 실행 SHA로 구분한다.** #266(`claude/pair-v6c-carry-probes`, 단계 4/5 probe 도구, main에 병합됨)이 0.4.0–0.4.5를 써서 겹치지 않게 이 PR은 0.5.0으로 올렸다. 병합 뒤 `harness/pair_stage_probe.py`의 `PROBE_VERSION` 주석에 0.4.x가 #266의 값이라는 매핑 메모를 남겼다. 이 PR의 raw(25셀·단계 3)는 manifest `probe_version`이 모두 `0.4.0`이고, 0.5.0으로 다시 돌린 물리 실행은 없다. 이 값은 기록용 문자열이라 동작을 바꾸지 않는다 |

- 등록의 `denominator`에는 이 단계 probe를 포함하지 않는다.
- **raw 기록의 번들 ID.** 각 경우 `result.json`의 `execution_bundle_id_on_main`은 실행 당시 main의 번들을 적은 값이다. 단계 2 25셀(`052e3eba-v6d-venv-align-0`·`-1`, 13+12)과 단계 3 공식 환경 실행(`052e3eba-v6d-venv-bound-e2e`, 23)은 `zone-pair-v76-fixclock-grasp-entry`(v76)로 기록됐다. v6c 기준선(`b5234b7a-v6c-align` 25, `b534a9b5-v6c-bound-e2e` 46)도 v76이다. **v80(`zone-pair-v80-align-widehue-finemotion`)으로 기록된 raw는 병합 트리 `4714263a`에서 돌린 6셀(`4714263a-v6d-final-align-subset`)과 단계 3의 23셀(`4714263a-v6d-final-bound-e2e`)뿐이다.** 그래서 25셀 결과는 v80 등록 트리의 실행이 아니라 그 코드 트리 `052e3eba`의 실행이다. 두 트리가 같은 소스라는 근거는 `052e3eba` 실행 트리 파일 951개가 각각 `git show 052e3eba:<경로>`의 blob과 바이트 단위로 같다는 확인(manifest에 `source_dirty: true`가 있는 것은 실행 트리 밖의 미커밋 실험 기록 때문이다)과, `4714263a` 974개가 모두 blob과 같다는 확인이다. 25셀 전체를 v80 트리에서 다시 돌린 것은 아니다.

## 12건 실패의 원인 분류 (v6c 정렬 격자, `pair-stage-probes-b5234b7a-v6c-align`)

| 분류 | 셀 | 판정 | 원인 |
|---|---|---|---|
| **A** PF 운동 모델 | teacher corner++/same, corner−−/opp, corner−−/same, yaw+/opp, yaw+/same, yaw−/same (6건) | `ALIGN_RELOOK_NO_FIX` (SIM 20–36 s에 종료) | 기본 운동 프로필이 정렬 펄스의 이동을 크게 과대 적분함(재생 중앙값: x 4.74배, y 4.27배, yaw 2.17배) |
| **B** 빔 윗면 색 | teacher along+/same (r1 yaw 115 mrad), corner++/opp (r1 57), yaw−/opp (r1 54) | `GT_CRITERIA:r1_yaw` | r1이 보는 빔 윗면이 노란색이라 heading이 치우침 |
| B | E2E `v6-s912-v5h` × 시드 911/912/913 (r1·r2 yaw 66 mrad) | `GT_CRITERIA:r1_yaw,r2_yaw` | 같은 체크포인트라 세 시드가 사실상 같은 셀 |

12건 중 A 6건, B 6건이다. 독립 궤적으로는 A 6개, B 4개다.

### 원인 A: 정렬 펄스를 과대 적분하는 PF 운동 모델

**증상.** relook 스윕이 정보 있는 fix를 얻지 못해 `ALIGN_RELOOK_NO_FIX`로 끝났다. v6c가 고친 음수 fix 나이(#263 문제 1)가 아니라, 그 뒤에 남은 다음 원인이다.

**근본 원인.** 자기 위치 필터(`OwnCamLocalizer`)는 자기 발행 명령을 운동 프로필로 적분한다. 기본 프로필(`experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json`의 `motion`, gain 1.47, spin-up tau 0.3 s)은 주행 명령으로 맞춘 것이다. 정렬은 0.2–0.3 s, 최대 0.05 m/s 펄스를 손목 카메라가 주변을 둘러보는 자세(`search`/`p45`/`inspect`)에서 보낸다. 이때 실제 차체는 훨씬 느리게 가속하므로 기본 프로필은 이동을 크게 과대 예측한다.

- **재생** ([diagnosis/motion_replay.py](diagnosis/motion_replay.py), 결과 [diagnosis/motion_replay.txt](diagnosis/motion_replay.txt), 축별 요약 [diagnosis/motion_replay_axes.py](diagnosis/motion_replay_axes.py) → [diagnosis/motion_replay_axes.txt](diagnosis/motion_replay_axes.txt)). v6c 원자료의 발행 명령 이력 50건(25셀 × 로봇 2대)을 두 프로필로 적분해 정렬 구간 전체의 몸통 x·y·yaw 이동을 eval-only GT와 비교했다. 아래 배율은 예측 이동량 / GT 이동량의 **중앙값**(범위)이고, 배율은 GT 이동량이 축별 임계(x 0.05 m, y 0.03 m, yaw 0.03 rad) 이상인 이력만 쓴다. 평균 절대 오차는 50건 전체다.

| 축 | 프로필 | 배율 중앙값 (최소–최대) | 배율에 쓴 이력 | 평균 절대 오차 (최대) |
|---|---|---:|---:|---:|
| x | 기본 (`calibration_loop_v2`) | **4.74** (4.35–5.02) | 50 | 1035 mm (1244) |
| x | M1 `fine` (`calibration_m1_dev`) | **0.96** (0.94–0.99) | 50 | 9.9 mm (16.0) |
| y | 기본 | **4.27** (3.14–6.64) | 35 | 144.5 mm (275.0) |
| y | M1 `fine` | **1.40** (1.07–2.06) | 35 | 19.2 mm (38.0) |
| yaw | 기본 | **2.17** (0.90–3.31) | 31 | 53.2 mrad (136.0) |
| yaw | M1 `fine` | **1.16** (0.84–1.66) | 31 | 10.3 mrad (40.0) |

- **x축만 좋아 보이지 않게 정리하면:** `fine` 프로필도 y는 실제의 1.40배(최대 2.06배), yaw는 1.16배(최대 1.66배)로 아직 과대 예측한다. 평균 오차는 기본 프로필보다 y에서 7.5배, yaw에서 5.2배 작아졌지만 x(9.9 mm)만큼 잘 맞지는 않는다. 앞선 초안의 "평균 4.74배"는 x축 배율의 중앙값이었다.
- **독립 이력은 50건이 아니라 36건이다.** 25셀 중 nominal 3시드와 E2E 체크포인트 3시드가 같은 궤적이라, GT·기본·`fine` 세 값이 완전히 같은 이력을 합치면 36건이 된다. 36건만으로 다시 구해도 x 4.74/0.96, y 4.14/1.35, yaw 2.20/1.22로 결론이 같다(같은 파일에 있다).
- **한계.** 이 재생은 v6c 실패를 진단한 바로 그 원자료(25셀)로 프로필의 효과를 본 것이다(in-sample). 프로필은 새로 맞추지 않고 M1 dev의 기존 값을 그대로 썼으므로 이 재생에서 적합한 매개변수는 없다. 다만 새 조건(새 시드·새 자세)의 독립 확인은 아니다. 재생은 결정적이다(무작위 없음).

- 정렬 구간에서 실제 차체는 0.25–0.33 m 움직였는데 기본 프로필은 1.2–1.6 m로 적분했다.
- 그 결과 자세 사후분포가 과신한 채(표준편차 약 0.03 m) 6 s fix 간격 동안 0.23–0.26 m 어긋났다. relook 프레임에는 tag가 보이는데도 내부 일치 비율이 0이라 fix를 얻지 못하고 `ALIGN_RELOOK_NO_FIX`로 끝났다.
- 이 재생은 운동 모델만 분리해 본 것이다. 필터 전체(관측 갱신 포함)를 새 프로필로 다시 돌린 결과는 아래 물리 격자다.

**수정** (`harness/owncam_align_motion_v6d.py`, 플래그 `align_fine_motion`). 정렬 상태(`align`, `align_relook_stop`, `align_relook`, `align_relook_return`)에서만 M1 `fine` 프로필로 적분한다.

- M1 `fine` 프로필은 저장소에 있던 값이다(`harness/m1_owncam_delivery.py:_set_motion_profile`이 같은 방식으로 고른다). 새 값을 만들지 않고 그대로 가져왔다. 출처 파일 sha256 `126cadaa9265ed2ae2b034f675e67c227193a2e1678f6b0c82dd53b186e6fc72`, 프로필 sha256 `8651d76e…97e`.
- **`fine`은 gain·tau만이 아니라 매개변수 묶음 전체다.** gain 대각 (1.95, 1.95, 0.95), tau 1.28 s(축별 (1.28, 1.28, 0.05)), tau_stop 0.05 s, 잡음 noise_rel (0.25, 0.4, 0.2), **noise_abs (0.003, 0.003, 0.005)**, scale_std 0.2, **슬립 배율 끔(`use_scale` false)**이다. 기본 프로필은 noise_abs (0.015, 0.005, 0.014)이고 슬립 배율이 켜져 있다. 그래서 프로필을 바꾸면 이동 예측뿐 아니라 yaw를 포함한 절대 잡음도 함께 줄고 슬립 배율이 사라진다. 이전 초안의 "잡음 변경 없음"은 틀렸다.
- **적합 조건과 적용 조건이 다르다.** `fine`은 M1 dev 시드 s91에서 파지 단계에 발행한 명령(팔을 내리고 상자 곁에서 느리게 움직이는 구간, 전진 21개·회전 7개)으로 맞춘 값이다(`experiments/2026-09-26-zone-m1-owncam/fine_motion_fit_dev.json`, 적합 코드 `fit_fine_motion.py`). 그 자료에 옆걸음(y) 명령이 없어 y 이득은 전진 값을 그대로 쓴다. 위 재생에서 y가 x보다 덜 맞는(1.40배) 것과 맞는 방향이지만, 이것이 원인이라고 확인한 것은 아니다. 정렬 펄스는 손목 카메라가 둘러보는 자세에서 나간다. 이 자세에서 `fine`이 맞는지는 위 재생(x 0.96, y 1.40, yaw 1.16)과 물리 격자로만 확인했고, 독립 시드에서 적합 조건을 재현한 확인은 없다. 정렬 단계 probe 셀로 맞춘 값이 아니라는 점은 그대로다.
- 임계값을 풀거나 fix를 clamp하지 않았다. 필터 코드와 판정 게이트는 바뀌지 않았고 상태 전이마다 프로필(매개변수 묶음)만 바꾼다. 다른 상태에서는 v6c와 같은 프로필이다.

### 원인 B: 노랗게 렌더되는 r1의 빔 윗면

**증상.** 정렬이 "끝났다"고 선언한 시점의 실제 r1 yaw가 0.07–0.115 rad(기준 0.052)였다.

**근본 원인.** 정렬의 빔 heading은 v1 lime 마스크(hue 36–54)의 픽셀을 PCA로 맞춰 얻는다. r1이 45° 자세(`p45`)와 점검(`inspect`) 자세에서 보는 빔 윗면은 노랗게(hue ≈ 25–36) 렌더되어 마스크 밖에 놓인다. 같은 현상을 `owncam_pair_beam_v2`가 이미 기록했다(`BEAM_HUE = (25, 54)`, dev 613). 마스크 밖 픽셀 때문에 PCA 축이 치우친다.

- **재생** ([diagnosis/fullreplay_v6d.py](diagnosis/fullreplay_v6d.py), 결과 [diagnosis/fullsum_v6d.txt](diagnosis/fullsum_v6d.txt) · [diagnosis/fullsum_simplemask.txt](diagnosis/fullsum_simplemask.txt) · [diagnosis/heading_diag.txt](diagnosis/heading_diag.txt)). v6c 원자료의 자기 프레임을 v1 마스크와 넓힌 hue 25 마스크로 다시 처리하고 eval-only GT heading과 비교했다.

| 자세 | v1 마스크 yaw 오차 (편향 / rms) | 넓힌 마스크 (편향 / rms) |
|---|---:|---:|
| r1 `p45` (1212 프레임) | +0.021 / 0.031 rad | +0.006 / 0.007 rad |
| r1 `inspect` (0.1 m 이상 보이는 프레임) | rms 0.052 rad (44/304 프레임만 보임) | rms 0.008 rad (242/304 프레임) |
| r2 `search` (2321 프레임) | 편향 +0.007 / rms 0.014 | 편향 +0.027 / rms 0.030 (나빠짐) |

- r2 `search`에서는 넓힌 마스크가 오히려 나빠지므로 search에는 적용하지 않는다.
- **적용 조건은 자세뿐이고 로봇을 가리지 않는다.** `p45`/`inspect`이면 r2에도 hue 25가 적용된다(정렬 셀 25개에서 r2가 hue 25를 쓴 프레임은 모두 1062개, 셀당 약 42개다). 위 표는 r1 `p45`/`inspect`와 r2 `search`만 재생했고, r2 `p45`/`inspect`에서 넓힌 마스크의 효과는 재생으로 확인하지 않았다(아래 '후속 확인 근거'가 저장 프레임 위에서 오프라인으로 본 것뿐이다).

**수정** (`harness/owncam_pair_beam_v6d.py`, 플래그 `beam_wide_hue`). `p45`와 `inspect`에서만 hue 하한을 25로 넓힌다(`WIDE_HUE_LO = 25`, `WIDE_HUE_POSTURES = ('p45', 'inspect')`).

- 프레임 복사본에서 hue 25–36 픽셀을 lime 색으로 다시 칠한 뒤(`widen_lime`) v1 관측기를 그대로 호출한다. `harness/owncam_pair_beam.py`와 `harness/owncam_pair_beam_v2.py`(v1/v2 빔 모듈)는 바꾸지 않았다.
- **M2 동결 파일은 바뀌었다(앞선 초안의 "건드리지 않았다"는 틀렸다).** `scripts/study_owncam_pair_beam.py`는 M2 동결 파일(`experiments/2026-09-26-zone-m2-pair/imports.json`이 고정)인데 이 PR이 16줄(추가 15, 삭제 1)을 바꿨다. 새 메서드 `_beam_hue_lo()`가 `policy.beam_wide_hue`가 켜져 있고 현재 자세가 `p45`/`inspect`일 때만 hue 하한 25를 돌려주고, `_align`은 그 값이 있을 때만 `owncam_pair_beam_v6d.observe_beam(..., hue_lo=…)`를 부르며 아니면 v2 `observe_beam`을 이전과 똑같이 부른다. `beam_obs` 로그에 `hue_lo`가 붙는 것도 넓힌 경우뿐이다. 왜 이 파일을 바꿨나: 자세별로 색 범위를 고르는 곳이 `PairStudent._align` 안이라, 이 파일 밖에서는 다른 호출을 끼울 수 없었다(다른 정책은 코드 경로가 그대로다).
- **그 영향.** 동결 파일 허용 목록(`tests/test_zone_pair_executor.py:485-489`)이 이 파일의 새 sha256 `6f3b7776b17804269fe9060bb355d5fecb17172c10c343672394bc7f1d771a00`을 추가로 허용하도록 바뀌었다. 초안의 "바이트 계약 테스트 통과"는 이 허용 목록 변경 덕분이지, 파일을 안 건드려서가 아니다. 이전 revision 봉인(v6/v6b/v6c)은 `verify_v6_historical`이 각 봉인 커밋(v6c는 `be95f8b018bb110e2fc97ec5a3c90e357a949449`)의 blob과 대조하므로 이 변경으로 영향을 받지 않는다.
- 판정 임계값·채도·명도 하한은 v1 그대로다. 마스크가 보는 색 범위만 넓힌다.
- 새 AprilTag 경로는 없다.

### 두 수정의 근거와 한계

- **귀속은 재생으로만 했다.** A와 B를 각각 따로 켠 물리 실행(단일 플래그 ablation)은 하지 않았다. 재생에서 A는 NO_FIX 6건을, B는 yaw 6건을 각각 설명했다. 물리 25/25는 두 플래그를 함께 켠 결과이며, 플래그별 기여는 후속 작업이다.
- **원인 B의 자세 제한.** r2 `search`와 다른 자세는 v1 마스크를 유지한다. 새 자세에 적용하려면 재생으로 다시 확인한다.
- **`beam_wide_hue`는 r2 p45/inspect에도 걸린다.** 조건이 자세뿐이라서다. r2에서 이 범위가 안전한지는 이 PR의 재생이 아니라 후속 확인(아래)으로만 봤다.
- **음성 대조가 없다.** 노란 물체가 빔 옆에 있을 때 마스크에 들어오지 않는지는 확인하지 않았다. 후속 확인에서 넓힌 범위가 추가한 픽셀이 모두 빔 발자국 안이었지만, 그 프레임에 빔이 아닌 노란 물체가 있었는지는 알 수 없다.
- **`align_fine_motion`은 잡음·슬립 배율도 바꾼다.** 위 '수정' 절 참고. 적합은 M1 dev 시드 하나(s91)의 팔 내린 파지 구간이고, 정렬 자세에서의 적합성은 재생과 물리 격자만 본다.
- **동결 파일 수정.** `scripts/study_owncam_pair_beam.py`가 바뀌었고 허용 목록에 새 해시가 들어갔다(위 '수정' 절 참고).
- **재생 통계.** 독립 이력 36건, in-sample이다. 평균 4.74배가 아니라 축별 중앙값(x 4.74, y 4.27, yaw 2.17)이다.

### 후속 확인 근거 (판정에 쓰지 않음)

적대적 검토(PR #265 코멘트)가 지적한 r2 p45/inspect의 미검증과 음성 대조 부재를 저장 프레임으로 오프라인에서 봤다. 물리·모델 호출은 없다. **물리 25/25 판정에도, 이 PR의 어떤 주장에도 쓰지 않는다.** 이후 확인의 근거로만 남긴다.

- 스크립트 [diagnosis/hue_mask_check.py](diagnosis/hue_mask_check.py), 결과 [diagnosis/hue_mask_check.txt](diagnosis/hue_mask_check.txt)(sha256 `1fc8afcee74e98081056cd361b9404fd37d8c114cb6f348cae27007c946bd851`). 프레임별 행은 1 MiB 한도 때문에 저장소 밖 `/Users/changmin/projects/ugrp/outputs/pair-stage-probes-052e3eba-v6d-hue-mask-check.json`(sha256 `96aafae9bae05fef89930ab61a1ac049c2424e0062356dc93fbbd531f6801cbd`)에 둔다.
- 대상: `052e3eba-v6d-venv-align-0`·`-1`의 저장 프레임 중 제어기가 hue 25로 빔을 본 `beam_obs` 이벤트에 대응하는 프레임(r1 1049개, r2 1062개). 각 프레임을 같은 jpg로 v1 마스크(hue 36)와 넓힌 마스크(hue 25)로 다시 관측했고, 로그의 `points`·`axis_heading_rad`와 일치함을 확인했다(재현 2111/2111).
- 비교는 eval-only GT(오프라인 진단에만 사용, 제어기 입력 아님)의 빔 heading과 빔 윗면 평면에 투영한 발자국(0.60 × 0.05 m + 여유 0.06 m)이다.

| 로봇 | 자세 | 프레임 | \|heading 오차\| 중앙값 hue36 → hue25 | 0.05 rad 초과 hue36 → hue25 | 발자국 밖 추가 픽셀 |
|---|---|---:|---:|---:|---:|
| r1 | p45 | 288 | 0.023 → 0.005 | 28 → 0 | 0 |
| r1 | inspect | 761 | 0.050 → 0.005 | 377 → 0 | 0 |
| r2 | p45 | 290 | 0.007 → 0.003 | 0 → 0 | 0 |
| r2 | inspect | 772 | 0.006 → 0.004 | 93 → 0 | 0 |

- **r2:** 넓힌 범위는 r2 p45/inspect에서 프레임 대부분(1062개 중 855개)에서 결과를 바꾸지 않고, 바뀐 프레임에서도 대개 좋아졌다(201개 개선, 6개 악화, 5 mrad 이상 차이 기준). 참고로 v6d 정렬 25셀은 r2가 넓힌 범위를 쓰고도 모두 통과했으므로 물리 결과와 어긋나지는 않는다.
- **빔 밖 노랑:** 추가된 픽셀은 프레임마다 0개가 발자국 밖이었다(r1 5,964,436개, r2 650,715개 중 0). 빔 평면 위로 투영되지 않는 추가 표본도 0개다.
- **한계.** 이것은 음성 대조가 아니다. 저장 프레임에는 빔 옆에 노란 다른 물체(노란 바퀴·상자)가 시야에 들어온 경우가 없었을 수 있고, 있었는지 라벨링하지 않았다. "빔이 아닌 노랑이 마스크에 안 들어온다"의 증거가 아니라 "이 프레임들에서는 들어오지 않았다"는 관찰이다. 다음 확인은 노란 물체를 시야에 일부러 넣는 별도 장면이다.

## 물리 격자 (단계 probe)

### 실행

- **환경.** 공식 환경 `.venv-sim-worker-mac`(python 3.12.13, mujoco 3.12.0, numpy 2.5.2, opencv-headless 5.0.0.93, `/Users/changmin/Project-Runtimes/ugrp/.venv-sim-worker-mac/bin/python`). v6c 기준선과 같은 환경이다.
- **driver.** [run_cells.py](run_cells.py)(sha256 `d326f725733d85aecc2d8ca2906a7f557d2cc6c8e030b667fac3f165d7a99405`)가 v6c 격자 계획을 그대로 읽어 정책만 `b-v6d`로 바꿔 실행한다. `--only-failed-of`, `--baseline-policy`, `--skip-done`, `--omp-threads`, `--shard K/N`, `--cells`를 추가했다. 다른 로직은 `scripts/run_pair_stage_probes.py`를 그대로 쓴다.
- **동기 SIM 모드, agent_lock 없음.** 조정자 지시에 따라 물리 잠금을 잡지 않고 동기 SIM 시간으로만 측정했다. wall 시간은 결과 주장에 쓰지 않는다. 실행마다 `uptime` 부하 평균을 manifest에 남겼다.
- **워커.** 분할 실행마다 워커 1개, `OMP_NUM_THREADS=1`. 부하 평균이 20을 넘으면 1개로 줄이는 규칙을 지켰다.
- **소스.** `052e3eba`(코드 실행 트리 sha256 `f20a2f87ec6a39cdd11bade9fb57ce039a0114fb5b70569e81399274b310d0b9`). 병합 트리 `4714263a`에서 확인한 결과는 아래 '병합 트리 동등성 확인'에 있다.

### 단계 2 정렬: b-v6c 13/25 → b-v6d 25/25

같은 25셀(teacher 19 + E2E 체크포인트 6). 열은 판정 / 마지막 정렬 GT 오차의 최악값(로봇 r1·r2 중, x mm, y mm, yaw mrad) / 정렬 SIM 초 / look 명령 수다. GT 오차는 eval-only 판정값이며 제어기 입력이 아니다. 판정이 실패한 v6c 셀은 정지하지 못해 GT 오차가 없다(`-`). 표는 [compare.py](compare.py)로 만들었다.

| case | b-v6c: 판정 · x · y · yaw · SIM s · look | b-v6d: 판정 · x · y · yaw · SIM s · look |
|---|---|---|
| e2e:v6-s911-v5h:s911 | PASS · 7 · 5 · 45 · 36.7 · 265 | PASS · 7 · 8 · 15 · 36.7 · 265 |
| e2e:v6-s911-v5h:s912 | PASS · 7 · 5 · 47 · 36.7 · 265 | PASS · 7 · 8 · 15 · 36.7 · 265 |
| e2e:v6-s911-v5h:s913 | PASS · 7 · 5 · 47 · 36.7 · 265 | PASS · 7 · 8 · 15 · 36.7 · 265 |
| e2e:v6-s912-v5h:s911 | GT_CRITERIA r1_yaw,r2_yaw · 7 · 7 · 66 · 36.5 · 263 | PASS · 7 · 7 · 37 · 36.9 · 263 |
| e2e:v6-s912-v5h:s912 | GT_CRITERIA r1_yaw,r2_yaw · 7 · 8 · 66 · 36.5 · 271 | PASS · 7 · 7 · 37 · 36.9 · 263 |
| e2e:v6-s912-v5h:s913 | GT_CRITERIA r1_yaw,r2_yaw · 7 · 7 · 66 · 36.5 · 263 | PASS · 7 · 7 · 37 · 36.9 · 263 |
| teacher:along+/opp | PASS · 7 · 6 · 48 · 38.2 · 272 | PASS · 7 · 6 · 6 · 38.2 · 272 |
| teacher:along+/same | GT_CRITERIA r1_yaw · 7 · 7 · 115 · 39.5 · 300 | PASS · 7 · 7 · 6 · 34.0 · 272 |
| teacher:along−/opp | PASS · 7 · 6 · 40 · 39.5 · 272 | PASS · 7 · 7 · 6 · 38.3 · 272 |
| teacher:along−/same | PASS · 6 · 6 · 32 · 39.1 · 272 | PASS · 8 · 7 · 3 · 38.3 · 272 |
| teacher:corner++/opp | GT_CRITERIA r1_yaw · 7 · 5 · 57 · 38.6 · 280 | PASS · 7 · 5 · 25 · 38.6 · 272 |
| teacher:corner++/same | ALIGN_RELOOK_NO_FIX · - · - · - · 24.8 · 219 | PASS · 7 · 5 · 23 · 34.5 · 272 |
| teacher:corner−−/opp | ALIGN_RELOOK_NO_FIX · - · - · - · 23.1 · 181 | PASS · 7 · 7 · 15 · 37.9 · 272 |
| teacher:corner−−/same | ALIGN_RELOOK_NO_FIX · - · - · - · 23.1 · 164 | PASS · 8 · 7 · 11 · 38.6 · 272 |
| teacher:lat+/opp | PASS · 7 · 6 · 42 · 35.7 · 262 | PASS · 6 · 6 · 0 · 35.8 · 262 |
| teacher:lat+/same | PASS · 7 · 5 · 42 · 35.7 · 267 | PASS · 6 · 5 · 10 · 35.8 · 267 |
| teacher:lat−/opp | PASS · 7 · 5 · 45 · 36.4 · 280 | PASS · 7 · 5 · 10 · 35.8 · 272 |
| teacher:lat−/same | PASS · 8 · 6 · 36 · 37.8 · 283 | PASS · 8 · 6 · 10 · 35.8 · 267 |
| teacher:nominal:s911 | PASS · 7 · 6 · 42 · 36.1 · 272 | PASS · 7 · 6 · 4 · 36.2 · 272 |
| teacher:nominal:s912 | PASS · 7 · 6 · 42 · 36.1 · 272 | PASS · 7 · 6 · 4 · 36.2 · 272 |
| teacher:nominal:s913 | PASS · 7 · 6 · 42 · 36.1 · 272 | PASS · 7 · 6 · 4 · 36.2 · 272 |
| teacher:yaw+/opp | ALIGN_RELOOK_NO_FIX · - · - · - · 20.5 · 154 | PASS · 8 · 7 · 32 · 36.1 · 262 |
| teacher:yaw+/same | ALIGN_RELOOK_NO_FIX · - · - · - · 35.5 · 271 | PASS · 7 · 7 · 31 · 35.7 · 267 |
| teacher:yaw−/opp | GT_CRITERIA r1_yaw · 7 · 5 · 54 · 36.7 · 280 | PASS · 7 · 6 · 25 · 35.8 · 272 |
| teacher:yaw−/same | ALIGN_RELOOK_NO_FIX · - · - · - · 28.0 · 215 | PASS · 7 · 5 · 22 · 36.1 · 267 |

- 통과 셀의 yaw 오차도 v6c(32–48 mrad)보다 작아졌다(0–37 mrad). 정렬 기준 52 mrad에 대한 여유가 늘었다.
- x·y 오차는 v6c와 같은 크기(≤ 8 mm)다. 정지 시간과 명령 수도 v6c 통과 셀과 같은 범위다.
- 빠뜨린 셀 없음, 재시도 없음, 호스트 오류 없음.

### 단계 3 파지+들기 (회귀 확인): b-v6c 22/23 → b-v6d 22/23

허용오차 경계 23셀, E2E 정합 사전분포, 시드 911. v6c 기준선 디렉터리 `pair-stage-probes-b534a9b5-v6c-bound-e2e`에는 b-only 23건도 들어 있어 `@b-v6c:` 행만 비교했다([compare.py](compare.py)는 이를 위해 기준 정책으로 걸러낸다).

- 23셀 모두 판정이 같다. SIM 7.3 s, look 명령 176개로도 같다.
- 실패 1건은 같다. corner+−+, r2 `LOAD_NOT_HELD_AFTER_LIFT`. 이 실패는 v6c의 미해결 항목이고 v6d는 손대지 않았다.
- v6d의 새 플래그가 정렬 상태에서만 켜지므로 파지 경로는 실행 코드가 같다. 그래서 이 결과는 "회귀 없음"을 확인하지만, 파지 성능을 새로 개선한 증거는 아니다.

### 병합 트리 동등성 확인 (최종 커밋 `4714263a`)

병합 트리(`4714263a` = main `98efe0e6` + `claude/pair-v6d-align` `052e3eba`, 코드 실행 트리 sha256 `f243cf42159d370c9894aaf656644051f9688c4219be13ca6c7f9408d977a25a`)에서 대표 셀을 다시 돌려 위 결과가 같은지 확인했다. PR에 실리는 트리가 이 병합 결과이기 때문이다. 공식 환경, 분할마다 워커 1개, `OMP_NUM_THREADS=1`, 동기 SIM 모드, 모델 호출 0이다. 두 실행 모두 manifest `state=completed`, `source_changed=False`(실행 전후 소스 sha256 동일)이다.

- **단계 3 경계 23셀 전부** (`4714263a-v6d-final-bound-e2e`): **22/23**. 셀마다 판정·SIM 시간(7.2–7.3 s)·look 명령(176개)이 `052e3eba` 공식 환경 실행과 같다. 실패 1건은 같은 corner+−+ r2 `LOAD_NOT_HELD_AFTER_LIFT`이다.
- **단계 2 대표 6셀** (`4714263a-v6d-final-align-subset`): **6/6 통과**. 6셀은 e2e v6-s911-v5h, e2e v6-s912-v5h(원인 B), teacher nominal, along+/same(원인 B), corner++/same(원인 A), yaw+/opp(원인 A)이다. 셀마다 SIM 시간, look 명령 수, GT 최종 오차(grip x, yaw)가 `052e3eba` 정렬 combined 결과와 소수점 자릿수까지 같다.

| 셀 (`align@b-v6d:`…) | 통과 | SIM s | look 명령 | 최악 yaw mrad | 최악 grip x mm |
|---|:---:|---:|---:|---:|---:|
| teacher:nominal | 통과 | 36.2 | 272 | 4.2 | 6.5 |
| teacher:along+/same | 통과 | 34.0 | 272 | 6.4 | 7.5 |
| teacher:corner++/same | 통과 | 34.5 | 272 | 22.5 | 7.4 |
| teacher:yaw+/opp | 통과 | 36.1 | 262 | 32.2 | 7.5 |
| e2e:v6-s911-v5h | 통과 | 36.7 | 265 | 15.1 | 7.4 |
| e2e:v6-s912-v5h | 통과 | 36.9 | 263 | 37.0 | 7.4 |

- 이 6셀은 병합 트리에서도 결과가 그대로라는 확인일 뿐, 25셀 전체를 다시 돌린 것이 아니다. 25셀 결과는 `052e3eba` 실행이다. 두 트리의 코드 차이는 브랜치 시점 이후 main에 들어온 변경(v6b 시작 bootstrap, MasterPi v3 scene, B6/B7 referee·driver 등)과 v6c/v6d 등록 분리다. `PairTeam`의 bootstrap 호출은 `policy.stationary_bootstrap`(b-v6d는 False)일 때만, scene provider의 v3 분기는 v3 지도 id일 때만 동작하므로 이 probe의 경로는 쓰지 않는다. 두 트리의 결과가 자릿수까지 같은 것이 그 확인이다.
- 부하(uptime): 시작 `8:40 … 13.57 15.96 17.81`, 종료 `8:59 … 13.54 17.25 18.26`(단계 3), `8:59 … 14.88 16.83 18.04`(단계 2). wall 시간은 주장하지 않는다.

### 먼저 돌린 anaconda 환경 실행과 인터프리터 불일치

처음 만든 v6d 실행은 `/opt/anaconda3/bin/python3`(python 3.13.5, numpy 2.4.4, opencv 4.13.0.92)로 돌렸다. v6c 기준선은 공식 환경(`.venv-sim-worker-mac`)이므로 인터프리터가 달랐다. 이를 알아채고 공식 환경으로 전부 다시 돌렸다. 위 표와 요약은 공식 환경 결과만 쓴다. anaconda 실행은 삭제하지 않고 기록으로 남긴다.

| 디렉터리 (`outputs/pair-stage-probes-…`) | 셀 | 결과 | 비고 |
|---|---:|---:|---|
| `9622bc43-v6d-pilot` | 8 (`cases.jsonl` 6) | 8/8 | 중단(INTERRUPTED). 조정자가 워커 1개를 요청해 멈춤. 결과 파일 2건은 `cases.jsonl`에 없고 `cases/*/result.json`에만 있다 |
| `ec30e57d-v6d-pilot2` | 4 | 4/4 | 이어서 실행 |
| `df5bb798-v6d-align-a` | 7 | 7/7 | 분할 0/2. 실행 중 소스를 커밋해 manifest `source_changed=True`(TB 뷰 빌더와 helper만 바뀜) |
| `df5bb798-v6d-align-b` | 6 | 6/6 | 분할 1/2 |
| `052e3eba-v6d-align-combined` | 25 | 25/25 | 위 네 실행을 `combine_grid.py`로 합친 파생물. 한 셀도 두 번 돌지 않았다. 최악 yaw 36 mrad |
| `052e3eba-v6d-bound-e2e` | 23 | 21/23 | 실패: ex+12 mm(`PREGRASP_BEAM_UNCERTAIN`), corner+−+(위와 같은 `LOAD_NOT_HELD_AFTER_LIFT`) |
| `052e3eba-v6d-diag-ex12-{b-v6c,b-v6d}-omp{1,2}` | 1 × 4 | 0/4 | ex+12 mm 진단. v6c와 v6d 모두 anaconda 환경에서 실패 |

- 정렬 결과(25/25)는 두 환경에서 같다.
- **ex+12 mm 파지 셀은 라이브러리 스택에 민감하다.** anaconda 환경에서는 v6c와 v6d 모두 `PREGRASP_BEAM_UNCERTAIN`으로 실패하고, 공식 환경에서는 둘 다 통과한다. OMP 스레드 수(1/2)와 부하는 결과에 영향이 없었다(위 진단 4건). v6d의 변경 때문이 아니라 v6c 자체의 견고성 한계다. #263의 v6c 결과는 공식 환경 기준이므로 그대로 유효하다. 원인(numpy·opencv 차이가 빔 fit 경계에 미치는 영향)은 파고들지 않았다.

## raw와 해시

모든 raw는 기본 체크아웃 `/Users/changmin/projects/ugrp/outputs/`에 있고, 아래 이름의 접두어는 `pair-stage-probes-`이다. 이 저장소에는 raw 프레임·영상을 커밋하지 않는다(로컬 보관이며 원격 백업이 아니다).

| 디렉터리 | 크기 | `cases.jsonl` sha256 | `manifest.json` sha256 |
|---|---:|---|---|
| `b5234b7a-v6c-align` (기준선, 25건) | 489M | `2805da62afdb1864eaafd43b05ed496eb8c006a7ae72ac39e053ac0bc10ac817` | `67b63c4a…` (v6c README 참고) |
| `b534a9b5-v6c-bound-e2e` (기준선, b-v6c 23 + b-only 23) | 178M | `8fc97b96b1fbc56bb6bff26c84bbf5fb78e100148cf7b793e173df828a064678` | v6c README 참고 |
| `052e3eba-v6d-venv-align-0` (13건, 분할 0/2) | 269M | `c455297a05aebedd356d9ab4b53abf29da0fa7b890efe9b9695a894c1f6ee207` | `027318c4c9eeab9aecfe61d023e9cee48cbeb8f0cb306be13cdd6ba48810d5c4` |
| `052e3eba-v6d-venv-align-1` (12건, 분할 1/2) | 244M | `69a695a25f49f5a60b87a6b02cb0ac68939d3351db686a05e11c3a3c9ab58293` | `885452943a1a9154af9906c23a8e36d444ea8563420dbdac4caae60f985dc55b` |
| `052e3eba-v6d-venv-align-combined` (25건, 파생) | 60K | `bb6c2075f19bf282b1ebf763a68a8dd4a5493e7e8ab5959c225f13c5ea9544a6` | `4806c19e60f67951486fbde80d9d68fb1dc95a6199f549ec10057524edcb0ce9` |
| `052e3eba-v6d-venv-bound-e2e` (23건) | 103M | `a86bcd5b2a39776541ca61163c1013980e024acfa45b01f8801c38b47a6bc75e` | `0b841f4029ab05484f8d34bc684a547082e566c31d66f4c59c62a9bc9d89f7bf` |
| `4714263a-v6d-final-bound-e2e` (병합 트리, 23건) | 103M | `fb1ad7effc62d6e05f1032929f04781ae7100e6a53f52ec5839b11eb3daf71da` | `cd36ccd0515e2b89a994b470845c99c5a0744451fcddc9d6c44097151510564d` |
| `4714263a-v6d-final-align-subset` (병합 트리, 6건) | 120M | `5895a85ba2b4399efae22ec489f150885e5e3c6cd7f86b19222c67337b3c4825` | `0f6dbc68b52b3b0320081378f987912f4bbd1521bfb7c9e24978e3d89bf9fb36` |
| `052e3eba-v6d-bound-e2e` (anaconda, 23건) | 101M | `28defe461ee45da6efe4c65ff3c9d22519ee7c73ba2f08a47852d69ad1a924b7` | 디렉터리 `artifacts.sha256.json` 참고 |
| `df5bb798-v6d-align-a` / `-align-b` (anaconda) | 144M / 124M | `8c99d22385ec08858693244f07c3885f07e5fc701d7cc18fc8312f279e15a5d3` / `067a6c0aca2693c7ef09526190e02f0496e5f54ef05e0d018bb18b4ed05c114d` | 〃 |
| `ec30e57d-v6d-pilot2` / `9622bc43-v6d-pilot` (anaconda) | 83M / 165M | `b77894f45d3ff0c14d64948a026d12ef7b0e5e0dd29764d0d6bac353b4359ad6` / `c265be02f0c2e56a44cd15d2486128c0004edad41da34c665d07ee91a15c61f9` | 〃 |

- `summary.json` sha256: `venv-align-combined` `aab7ef69229a56be668ca14e5b3e9ad6c17c758e4cf126b9f3eccc2b796729be`, `venv-bound-e2e` `43470ac653623fad5b0c1b376f53d6fc0944650b4b2b235081dec442070d1ee1`, `final-bound-e2e` `d3ef9bc13fceb346738fcb3daba92c52a436854b70fd6970ee8d9faf2e1d8307`, `final-align-subset` `d39d1254537171df430d58eeaadc061eb674f99d112a9e0c761ad3f0be9b736d`.
- 각 디렉터리의 `artifacts.sha256.json`에 `cases.jsonl` · `summary.json` · `manifest.json`의 바이트 수와 sha256이 있다(합친 디렉터리는 `combine_grid.py`가 만든다).
- **부하(uptime, load 1/5/15분).** 실행마다 manifest에 기록했다. 공식 환경 실행: 단계 3 시작 26.54/25.86/21.63 → 종료 13.29/15.61/17.35, 단계 2 두 분할 시작 9.48/14.53/16.91 → 종료 23.74/22.28/20.12(분할 1은 36.37/23.68/19.97). 다른 작업이 동시에 돌아 부하가 높았지만 동기 SIM 시간이라 결과에는 영향이 없다.
- **진단 스크립트의 고정 경로.** `diagnosis/*.py`는 분석 시점의 worktree(`/Users/changmin/projects/ugrp-wt/claude-v6d-align`)와 v6c raw 경로를 하드코딩했다. 다른 곳에서 다시 돌리려면 경로를 바꿔야 한다. 새로 추가한 `hue_mask_check.py`는 저장소 루트를 `UGRP_ROOT`(기본: 파일 위치 기준)로 잡고 raw는 기본 체크아웃 `outputs/` 절대 경로를 쓴다. `motion_replay_axes.py`는 `motion_replay.txt`만 읽는다.

## 검증

병합 트리 `4714263a`에서 다시 돌린 결과다(공식 환경 python 3.12.13, 로컬 Mac, `OMP_NUM_THREADS=1`).

- **검토 반영 뒤 재확인(origin/main `1e7bdfe0` = #264·#266 병합 후의 브랜치, 코드 동작 변경 없음).** `scripts/run_ci_tests.py`의 314개 파일 전체 pytest: **6252 통과, 16 건너뜀, 3 실패**(831 s, 실패 3건은 아래와 같은 sparse checkout 원인). `tests/test_pair_stage_probe.py`(#266이 327줄 추가, CI 목록에 없음)와 `tests/test_zone_pair_v6d.py` 80개 통과. `tests/test_zone_study_multiturn_properties.py`·`tests/test_zone_multiturn_ci.py` 두 파일 전체 750개 통과. `verify-current`, `verify-registry --base origin/main`(= `1e7bdfe0`)과 `--base 98efe0e6`, `scripts/check_media_size.py --base origin/main` 통과. `build_prereg_v6d.py`를 병합 뒤 다시 돌려도 `prereg_v6d.json`이 바이트 같아(`registration_sha256` `1a152996…`) 병합 때문에 다시 봉인할 필요는 없었다.
- 아래는 그 전, 병합 트리 `4714263a` 시점의 결과다.

- **CI 오프라인 묶음.** `scripts/run_ci_tests.py`의 `TEST_PATTERNS` 314개 파일 전체를 `pytest -q`로 직접 돌렸다(로컬 agent_lock은 잡지 않으려고 스크립트 대신 같은 목록을 썼다). **6252 통과, 16 건너뜀, 3 실패**(853 s). 실패 3건은 모두 `tests/test_zone_study_review_r7_contract.py::test_r7_p2_frozen_records_…`이고 원인은 이 worktree의 sparse checkout이 `experiments/**/*.gz`를 뺀 것이다(`experiments/2026-09-26-zone-study-offline-smoke/v{3,4,5}/example_trial_record.json.gz` 없음, FileNotFoundError). 전체 체크아웃인 기본 체크아웃에서 같은 파일을 돌리면 22개 모두 통과한다. GitHub Actions는 전체 체크아웃이므로 영향이 없다.
- **v6d 신규·TensorBoard 시험.** `tests/test_zone_pair_v6d.py` 38개(마스크·프로필 적용 조건·플래그 조합·등록 계약·재생 기록 고정값)와 `tests/test_tensorboard_export.py`, `tests/test_offline_audit_export.py`, `tests/test_owncam_loop_views.py`를 함께 돌려 125개 통과.
- **CI 계약 검사.** `python -m harness.rgb_execution_bundle verify-current --id rgb-standard-dispatch-v63`, `verify-registry --base origin/main`(= `98efe0e6`), `scripts/check_media_size.py --base origin/main`을 로컬에서 통과시켰다. multiturn 16개 shard 중 shard 0/16(`tests/test_zone_study_multiturn_properties.py`, `tests/test_zone_multiturn_ci.py`)만 로컬에서 49개 통과시켰다. 나머지 shard는 CI에 맡긴다. 이 PR이 바꾼 것은 `test_zone_study_multiturn_properties.py`의 기대 번들 ID 한 줄(v76 → v80)뿐이다.
- **이전 실행에서 보인 기존 실패**(v6d와 무관, base `98efe0e6`에서도 같음): `tests/test_zone_pair_v5c.py::test_saved_small_jpegs_reproduce_recorded_own_tag_ids[dev10_r1_1240.jpg]`와 `tests/test_zone_study_pair_delay.py::test_real_m2_checkpoint_relocalization_readiness_and_go[...]` 3개. `test_zone_pair_v5c.py`는 CI 목록에 없어 이번에 돌리지 않았다. `test_zone_study_pair_delay.py`는 CI 목록에 있고 이번 실행에서 실패하지 않았다(앞선 실패와의 환경 차이는 조사하지 않았다).

## TensorBoard

- **스냅샷.** `/Users/changmin/projects/ugrp/outputs/tensorboard/0929-pair-stage-probes-v6d`, run 51개(경우별 48 + 그룹 집계 `ALL-*` 3). `collection.json` sha256 `a78d9c3edf016e6d86bbb1ed73df2a56e3ada3584b812ce5d3a91b962de679ef`.
- **파생 뷰.** `outputs/pair-stage-probes-tbviews-0929-v6d`(index sha256 `37650be8e3f698a6ef34319ccf4087e5dc400ebe6baa8548d8c05a53874dc500`). 빌더 `scripts/build_pair_stage_probe_views.py`, 변환기 `scripts/export_offline_audit.py`. 공식 환경 결과(정렬 combined + 단계 3 경계)만 넣었다. anaconda 실행과 진단은 넣지 않았다.
- **검증 1.** EventAccumulator로 51개 run의 `offline/stage_pass`, `offline/pass_rate`, `evaluation/reported_success`를 파생 뷰 값과 비교했다. 불일치 0건이다(float32 반올림 허용 1e-4). 경우별 48개 중 47개가 통과 판정이고(정렬 25 + 단계 3 22) 집계 값은 `ALL-D-al-t-052e3eba-combined` 1.0, `ALL-D-al-e2e-052e3eba-combined` 1.0, `ALL-D-gl-bd-052e3eba-e2e` 0.957이다.
- **검증 2.** 공용 서버(PID 9291, 다른 작업 소유, 재시작하지 않음)의 `/data/runs`에 `0929-pair-stage-probes-v6d/` run 51개가 모두 있다(v6c 135개도 함께 있어 기준선을 나란히 볼 수 있다).
- **대시보드 설정.** `outputs/tensorboard-view.json`에 내 키 `pair_stage_probes_v6d_20260929`만 추가했다(다른 키는 바꾸지 않음). run filter `^0929-pair-stage-probes-v6[cd]/`, 고정 카드 `evaluation/reported_success`, `offline/pass_rate`, `offline/stage_pass`, `result/sim_s`, `result/wall_s`, `result/commands`, `result/model_calls`, HParams 열은 v6c 항목과 같다.
- **대시보드 링크(공용 서버, 로컬).** http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22evaluation/reported_success%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline/pass_rate%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline/stage_pass%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result/sim_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result/wall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result/commands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result/model_calls%22%7D%5D&smoothing=0&runFilter=%5E0929-pair-stage-probes-v6%5Bcd%5D/#timeseries
- **이름.** `D-` = b-v6d, `C-` = b-v6c(v6c 스냅샷), `B-` = b-only, 접두어 없음 = v5h. `al` = 정렬, `gl` = 파지+들기, `t` = teacher 격자, `e2e` = E2E 체크포인트, `bd` = 허용오차 경계, 끝의 `-pE` = E2E 정합 사전분포.

## 다음 막힘

1. **플래그별 ablation 없음.** A(`align_fine_motion`)와 B(`beam_wide_hue`)를 하나씩 켠 물리 실행으로 기여를 나눈다. 재생상 A는 NO_FIX 6건, B는 yaw 6건을 설명하지만 물리로 확인하지는 않았다.
2. **단계 4(운반)·5(내려놓기).** v6d 정책으로는 아직 probe하지 않았다. #266이 만든 단계 4/5 probe 도구는 이 브랜치에 병합되어 있고(`--policies b-v6d` 선택 가능), 실행은 후속 작업이다.
3. **a+b 정렬.** a+b 정렬은 손대지 않았다. 제안(구현 안 함): r1의 노란 윗면이 r2의 시야에도 들어오게 두 정책을 합치면 빔 길이 1.54 m를 r2의 한 번 관측에 맞출 수 있는지 확인할 가치가 있다.
4. **ex+12 mm 파지 셀의 라이브러리 민감도.** 위 환경 불일치 절 참고. v6c 견고성 문제로 따로 다룬다.
5. **held-out 확인.** 원인을 v6c 실패 셀에서 찾았으므로, 새 시드·새 체크포인트의 정렬 확인은 아직 없다.

## 참고 자료

- 저장소 내부: M1 `fine` 운동 프로필(`experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json`, `harness/m1_owncam_delivery.py:_set_motion_profile`), `harness/owncam_pair_beam_v2.py`의 `BEAM_HUE = (25, 54)`(dev 613 파지 거리 빔 색 모델), `experiments/2026-09-29-pair-v6c/README.md`(#263 기준선과 문제 1·2), `experiments/2026-09-28-pair-stage-probes/README.md`(#260).
- S. Thrun, W. Burgard, D. Fox, *Probabilistic Robotics*, MIT Press 2005. 6장 odometry 운동 모델과 Bayes 필터의 predict 단계: 예측 운동 모델이 실제와 맞지 않으면 분산 보정만으로는 관측 갱신이 회복되지 않는다.
- robot_localization, `FilterBase` (`processMeasurement`가 측정 시각으로 predict). 운동 모델 입력은 센서별로 별도 프로필을 두는 구조의 참고. https://github.com/cra-ros-pkg/robot_localization
- ROS `amcl`의 odometry 운동 모델 alpha 매개변수: 작은 이동에서는 큰 이동과 다른 잡음·이득을 쓰는 설계의 참고. https://wiki.ros.org/amcl
- R. R. Burridge, A. A. Rizzi, D. E. Koditschek, "Sequential Composition of Dynamically Dexterous Robot Behaviors," IJRR 18(6):534–555, 1999. doi:10.1177/02783649922066385. 정렬 목표 집합이 다음 파지 입장 영역 안에 들어가야 한다는 근거(v6c와 같은 이유로 인용).
- R. Hartley, A. Zisserman, *Multiple View Geometry in Computer Vision*, 2nd ed., Cambridge 2004. 평면 위 선의 heading을 마스크 픽셀로 맞출 때 마스크 밖 픽셀이 축을 치우치게 하는 이유의 배경.
- F. Chaumette, S. Hutchinson, "Visual Servo Control, Part I: Basic Approaches," IEEE RAM 13(4):82–90, 2006. 이미지 특징의 추정 편향이 정렬 수렴점을 옮기는 이유의 배경.
- MoveIt Task Constructor, pick 파이프라인 튜토리얼: 단계별 통과 조건을 앞 단계 출력 범위로 맞추는 구조. https://moveit.picknik.ai/main/doc/tutorials/pick_and_place_with_moveit_task_constructor/pick_and_place_with_moveit_task_constructor.html
