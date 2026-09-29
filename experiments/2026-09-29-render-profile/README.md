# 2026-09-29 렌더 프로필(그림자·반사) A/B — 측정 완료(단계 probe, 진단 규모)

**상태: 물리 probe를 실행했다(SIM 시간, 잠금 보유, b-v6d 정책, 소스 `584ee391`). 아래 "결과"에 채웠다. 이것은 단계 probe 비교이며 E2E 성공이 아니다. b-v6d의 운반은 σ(SELF_POSE_UNCERTAIN)로 조기 종료돼 성공이 아니다. 렌더 프로필의 채택·등록·push·PR은 하지 않았다(사용자가 #218에서 정한다).** 계획서였던 이전 본문은 아래에 그대로 두었고, 실행에서 계획과 달라진 점은 "실행 기록"에 적었다.

## 왜 하는가

사용자 판단: 시뮬레이터의 그림자와 바닥 반사가 실물보다 과하다. 그러나 로봇 카메라·공용 top 영상이 바뀌면 인식과 제어 결과가 바뀐다. 그래서 **기본값은 그대로 두고** 렌더 프로필을 새 버전으로 분리하고, A/B로 영향을 잰 뒤 최종 환경 고정(#218) 때 채택 여부를 정한다. 기준선(b-v6c 등)은 지금의 그림자 켠 조건이다. 카메라 배치·FOV, 로봇 외관, 물체, 물리는 바꾸지 않는다.

## 프로필 정의

`sim/render_profile.py`. 장면 XML 문자열만 고친다(`<light castshadow>`, `<material reflectance>`). 실행 기록에는 이름·정의 해시가 남는다.

| 프로필 | 하는 일 | 정의 해시(SHA-256) | 기본과 차이 |
|---|---|---|---|
| `shadows_v1` (= 플래그 없음) | 아무것도 바꾸지 않는다 | `f10e51da…c598f8c5` | 없음(같은 XML 문자열 객체를 돌려준다) |
| `noshadow_v1` | 모든 `<light>`에 `castshadow="false"`, 반사 재질(`reflectance` 속성이 있는 모든 `<material>`)을 `0`으로 | `c30f1ef6…5abc5809` | zone 장면 기준 광원 4개(키 3 + `dispatch_ceiling`)의 그림자 끔, `groundmat` 반사 0.035 → 0. 광원의 diffuse/ambient/specular, headlight, 텍스처, `shadowsize`, MSAA는 그대로 |
| `softshadow_v1` | **만들지 않았다** | — | 저장소 코드·문서·측정 프로토콜에 실제 방의 조명 세기(lux, 그림자 농도)를 적은 곳이 없다. diffuse/ambient 값을 정하면 근거 없는 추측이 된다. 실물 조명을 재면(#213/#214 실측 항목에 추가) 그때 추가한다 |

- 물리 불변: 두 모델을 컴파일해 `mjModel`의 모든 배열을 비교한 테스트에서 달라지는 것은 `light_castshadow`와 `mat_reflectance` 둘뿐이다. 광원 밝기·카메라 pose/FOV·timestep·noslip은 같다. 다만 영상이 바뀌므로 인식·제어 경로는 달라진다(그것이 A/B의 대상이다).
- 적용 지점: `sim.render_profile.install(scene, name)`이 장면 객체의 `transform`을 인스턴스 수준에서 감싼다. `isinstance` 검사(`own_scene`)와 v6d/v6e 사전등록이 고정한 파일(`zone_own_team_host.py`, `run_m2_pair.py`, `zone_scene.py` 등)을 고치지 않는다.
- 기록: `scene.record()['render_profile']`(이름, 해시, 정의, 프로필 적용 전후 장면 XML SHA-256), probe `manifest.json`의 `render_profile`, 각 케이스 `result.json`의 `applied.render_profile`(컴파일된 모델의 광원 `castshadow`와 반사 재질 실측값. 요청과 다르면 `RuntimeError`로 실패), 결과 행의 `render_profile`.
- 실행 경로: 이번에는 `scripts/run_pair_stage_probes.py --render-profile {shadows_v1,noshadow_v1}`만 연결했다(기본 없음). 다른 러너(`run_m2_pair.py` 등)는 사전등록 소스라 건드리지 않았다. 채택 시 새 번들·workflow를 등록하면서 연결한다(번호는 그때 main과 열린 PR 최댓값을 확인한다. v81/workflow 2.14.0은 b-v6e 몫으로 예약돼 있어 쓰지 않았다).
- 관찰 창은 이미 그림자·반사를 생략한다(`docs/local_simulation.md`, `scripts/dispatch_native_view.py`의 `viewer.user_scn.flags`). 그 스위치는 관찰 창 전용이고 로봇 카메라 렌더러에는 닿지 않아 재사용하지 못했다. 그래서 모델 수준에서 끈다.

## 기본 경로 불변 검증(오프라인, 이번 세션에 실행)

`tests/test_render_profile.py`(13개 통과), 함께 돌린 `tests/test_pair_stage_probe.py`·`tests/test_zone_pair_registered_source.py`·`tests/test_zone_pair_v6d.py` 포함 114개 통과.

- 프로필 없음/`shadows_v1`: `apply_xml`이 같은 문자열 객체를 돌려주고, `install(scene, None)`은 장면을 전혀 바꾸지 않는다(`transform` 속성도 안 생긴다). `shadows_v1`로 컴파일한 모델은 기본 모델과 `mjModel` 배열 전부(100개 이상) 동일하다.
- 실제 `zone_wide_door_tags_v2` 장면에서 160×120 프레임 한 장을 기본/`shadows_v1`로 렌더해 **바이트 동일**, `noshadow_v1`은 다름을 확인했다(`mj_forward`만, 정지 상태).
- probe 기본 계획은 그대로다(`cases == 38` 테스트 유지, 플래그 없을 때 케이스에 새 키 없음). 플래그가 있어도 plan 모드는 MuJoCo를 import하지 않는다.
- **실제 probe 실행에서의 바이트 동일은 미검증이다.** 아래 단계 0이 그 확인이다.

## 정적 관찰 한 가지(가설이 뒤집힐 수 있다)

`static_frames/render_static_frames.py`(이 폴더, `mj_forward`만, 장면 setup·스텝·probe 없음, 로봇은 모델 기본 위치, 카메라는 fisheye 재매핑 전의 이상적 렌더)로 얻은 프레임 한 쌍이다. 640×480, [stats.txt](static_frames/stats.txt).

| 카메라 | 바뀐 픽셀 | 평균 V (기본 → 프로필) | V<8 픽셀 비율 (기본 → 프로필) |
|---|---:|---|---|
| `r1__robot_cam` | 106,036 / 307,200 | 70.0 → 63.8 | 0.0000 → 0.0139 |
| `cctv_warehouse` (top) | 252,519 / 307,200 | 89.5 → 78.7 | 0.0008 → 0.0011 |

분해: 그림자만 끄면 각각 105,067 / 251,920 px, 반사만 끄면 19,275 / 8,006 px가 바뀐다(sim-speed 기록의 300,548 / 18,996 px와 같은 자릿수). 그림은 [robot_cam](static_frames/r1__robot_cam_default_vs_noshadow_v1.jpg)과 [top](static_frames/cctv_warehouse_default_vs_noshadow_v1.jpg)(왼쪽 기본, 오른쪽 프로필)이다.

- 그림자 광원을 끄면 밝은 조명 웅덩이(핫스팟)도 함께 사라지고 전체 평균 V가 **내려간다.** 이 프레임에서는 V<8 비율(`valid_frame`의 거절 기준 25 %와 같은 지표)이 오히려 올랐다. 원인은 추적하지 않았다. 따라서 "그림자를 끄면 어두운 바닥의 `OWN_IMAGE_INVALID`가 줄 것"이라는 기대는 **보장되지 않으며 반대일 수도 있다.** 실제 운반·내려놓기 자세의 프레임에서 측정해야 한다.
- 이 프레임 한 쌍은 대표성이 없다(정지 초기 자세, 로봇 카메라 마운트 미동기, 왜곡 전).

## A/B 계획(잠금이 풀린 뒤)

조건: 같은 케이스·seed에서 `shadows_v1`(기준)과 `noshadow_v1`(처치)만 비교한다. 물리는 같으므로 차이는 영상에서 온다. 그림자 유무는 관측 분포를 바꾸므로 **기존 b-v6c/b-v6d 기준선과 합산하지 않고 별도 조건으로 취급한다.**

### 고정

- 실행 소스: 이 브랜치와 정책 코드가 함께 있는 하나의 커밋(예: 그때의 main + 이 PR). probe는 추적 파일이 깨끗해야만 실행된다. 정책은 그 시점 main의 `b-v6d`(b-v6e가 병합돼 있으면 그 정책; 결정 후 기록). 두 arm은 같은 SHA·같은 정책·같은 인자만 다르다.
- 제어기, 카메라, 로봇, 물체, weld OFF, `cargo_noslip_v1`, 모델 호출 0(`labels: stage_probe, not_e2e_success`). 초음파는 연결하지 않는다.
- 잠금: `python3 scripts/agent_lock.py acquire --owner claude --branch claude/render-profile --purpose "render-profile A/B" --pid <드라이버 PID> --expected-minutes <분>`을 잡고 끝나면 `release`한다. 다른 에이전트의 잠금이 있으면 시작하지 않는다. 출력은 기본 체크아웃 `outputs/render-profile-ab-20260929/<arm>-<run>/`에 절대 경로로 쓴다.
- 각 실행 시작 시 부하 평균이 manifest(`environment.loadavg_at_start/end`)와 케이스 행(`loadavg_case`)에 남는다.

### 케이스(seed 911–913 nominal, `--cells nominal --nominal-seeds 911 912 913 --seeds 911 --sources teacher --policies b-v6d`)

| 케이스 | 명령 조각 | 왜 |
|---|---|---|
| 정렬 | `--stage align` | 짧고 영상 의존(빔 방향 색 범위) |
| 파지+들기 | `--stage grasp_lift` | 빔·집게 색 인식, 밝기 민감 |
| 운반 L0 nominal | `--stage carry --legs 0` | 기본 경로 첫 구간 |
| 내려놓기 목적지 | `--stage setdown --legs end` | b-v6c에서 어두운 목적지 바닥 때문에 r1 `OWN_IMAGE_INVALID`로 0/13 거절된 사례(`experiments/2026-09-29-pair-v6c-carry/README.md`) |

케이스 ID 예: `setdown@b-v6d:teacher:nominal:s911:Lend`. 케이스 ID는 프로필과 무관하게 같고 arm은 출력 폴더가 구분한다.

### 단계

0. **기본 불변 확인(물리 1케이스):** `align` nominal s911 하나를 `(가) 플래그 없음`, `(나) --render-profile shadows_v1`로 각각 `--workers 1`로 실행. `frames/` JPEG의 바이트 SHA-256과 `result.json`(wall·부하·경로 필드 제외)이 같아야 한다. 다르면(이 Mac은 785장 중 1장이 1단계 달랐던 전례가 있다) 차이 프레임 수와 궤적 동일 여부를 기록하고, 기준선 변동으로 읽을지 따로 판정한다. 통과 전에는 1·2단계를 시작하지 않는다.
1. **결과 비교(케이스 12개/arm):** `shadows_v1`, `noshadow_v1` 각각 위 4개 조각을 실행(`--workers 2`; 동시 작업이 없는 잠금 구간). 케이스 성공·`cause`·`first_failure`를 비교하고 프레임을 저장한다.
2. **시간 비교(seed 911 4케이스, `--workers 1`):** arm 실행 순서를 **기준·처치·처치·기준(S1, N1, N2, S2)**으로 교차한다. 기준을 두 번 재서 실행 변동(S1↔S2)과 처치의 변동(N1↔N2)을 먼저 본다. 각 arm 실행을 `/usr/bin/time -l python -m scripts.run_pair_stage_probes …`로 감싸 사용자+시스템 CPU 초와 retired instruction(부하에 덜 민감한 지표)을 기록한다. 이 방식은 워커 자식 프로세스의 CPU를 합산한다. 예상 규모: 케이스당 약 300 wall s(b-v6c 부하 25 기록). 4케이스 × 4실행 ≈ 80분(부하에 따라 가변).

명령 예(처치 arm, 정렬·파지):
```
python -m scripts.run_pair_stage_probes --stage align grasp_lift --sources teacher --cells nominal \
  --nominal-seeds 911 912 913 --policies b-v6d --render-profile noshadow_v1 --workers 2 --execute \
  --lock-owner claude --output /Users/changmin/projects/ugrp/outputs/render-profile-ab-20260929/noshadow-1-align-grasp
```
운반은 `--stage carry --legs 0`, 내려놓기는 `--stage setdown --legs end`를 따로 실행한다(`--legs`는 한 호출의 모든 단계에 걸린다).

### 지표(관측 전에 고정)

| 지표 | 계산 원천 | 비고 |
|---|---|---|
| 영상 검사(`valid_frame`) 통과율 | 저장된 로봇별 own 프레임 JPEG에 `harness/zone_pair_vision.valid_frame`의 식을 그대로 적용(오프라인) | 로봇·단계별 |
| 거절 사유 분해 | V<8 픽셀 비율(기준 25 %), 1–99 백분위 대비(기준 ≥ 15), V 표준편차(기준 ≥ 3) | 어느 항목에서 걸리는지 |
| 색 검출 성공률 | 큐브·빔·바닥 색을 기존 검출기(`harness/owncam_pair_beam_v2`, `harness/zone_own_perception_v3` 등)로 프레임마다 판정 | 검출기·문턱은 바꾸지 않는다 |
| PF 추정 오차와 σ | `result.json`의 `est_vs_gt_at_ref`(정답 대비 오차, 평가 전용), `own_at_ref`/`sigma_yaw_max`, `localizer_log` | 정답은 평가에만 쓴다 |
| 케이스 성공 | 결과 행 `passed`, `category`, `cause` | 성공률·거절 원인 분포 |
| 시간 | 행 `wall_s`, `stop_sim_s`(없으면 `stage_sim_s`)로 SIM 시간당 wall, 위 `time -l`의 CPU 초·instruction, 부하 평균 | S1/S2 변동과 함께 |

오프라인 분석 스크립트(`scripts/analyze_render_profile_ab.py`)는 **아직 없다.** 실행 전에 작성해 커밋하고 코호트 동안 고정한다(이 PR 범위 밖).

### 결과를 읽는 방식

- 물리가 같으므로 성공·인식 차이는 영상 변화에 귀속한다. 단, 케이스 12개/arm은 작은 진단이다. 통계적 결론이 아니라 방향과 실패 원인 분포를 본다.
- 기준 두 번(S1, S2)이 서로 다르면 그 폭이 처치 효과 해석의 하한이다.
- 채택 여부는 이 A/B가 아니라 #218에서 사용자가 정한다. 이 실험은 "채택 후보로 볼 만한가"와 "바뀌는 것"을 알려주는 것까지다.

### 실행 기록(계획과 달라진 점)

- **소스·환경.** 모든 물리 실행은 `584ee391`(브랜치 `claude/render-profile`, 추적 파일 clean, `source_dirty=false`; 프로필 구현 `6782a8f5` + 분석 스크립트) 하나로 했다. 이후 커밋(`96971959` 등)은 분석 옵션·문서뿐이다. `.venv-sim-worker-mac`(python 3.12.13, mujoco 3.12.0), 워커 OMP 스레드는 러너 고정값 2. 정책 `b-v6d`(origin/main; b-v6e는 미병합)로 계획서와 같다. weld OFF, `cargo_noslip_v1`, 모델 호출 0, 초음파 미연결. 프로필 이름·해시는 각 manifest와 결과 행에 있다(`applied.render_profile`이 컴파일된 모델의 실측값과 같아야 통과).
- **계획서 명령의 누락 하나:** `--prior-std e2e`가 없었다. 계획서 명령 그대로(기본 grid 0.06 m 사전분포)는 세 실행 모두(플래그 없음·`shadows_v1`·`noshadow_v1`) 5 s 안에 `ENTRY:ADMISSION_SELF_UNCERTAIN`으로 끝났다(raw `s0-none`, `s0-shadows`, `smoke-noshadow`). b-v6c/b-v6d 격자가 쓰는 `--prior-std e2e`(케이스 ID 끝 `:pE2E`)로 전부 다시 했다. 처음 세 실행은 지우지 않고 남겼다.
- `--omp-threads 1`은 `run_pair_stage_probes.py`에 없다(v6d의 `run_cells.py`만 환경변수로 덮는다). 소스를 고정하려고 러너 그대로(OMP 2) 썼다.
- 단계 1은 워커 2, 단계 0·2는 워커 1. 워커 2를 쓴 실행은 모두 시작 시 1분 부하 평균이 20 이하였다(로그의 `load=`; 20 초과 시 워커를 1로 줄이는 규칙은 발동하지 않았다). 워커 1 실행은 부하가 22–23에서 시작한 것도 있다(표 참고). 호스트 오류(HOST_ERROR)는 없었다.
- **계획 밖 추가 하나:** 아래 시간 측정에서 N1·N2·S3이 부하 60–115 구간에 걸려서 quiet 구간 반복 한 쌍(N3, S3; align+grasp, carry만)을 더했다. 사전 순서(S1, N1, N2, S2)는 그대로 했고 N3/S3는 따로 표시한다.
- `/usr/bin/time -l`의 `instructions retired`는 부모 프로세스만 센다(실행 하나가 CPU 100–600 s인데 5–9 G 명령어). 워커 자식이 빠져 있어 **명령어 수 지표는 쓸 수 없다.** CPU 초(user+sys)는 자식을 포함한다.
- 시드 911–913(nominal)은 PF 난수만 바꾼다. align/grasp의 영상 통계는 세 시드에서 같아서(위 분석에서 시드 간 수치가 같다) 독립 반복이 아니다. 단계당 3개가 아니라 "사실상 1개 + 난수 변형"으로 읽는다.

### 결과

모두 **단계 probe(nominal, teacher 진입, b-v6d, prior e2e)**이며 E2E 성공이 아니다. 성공/분모는 arm당 12케이스(4단계 × 시드 3).

**단계 0 — 기본 불변(통과).** align nominal s911을 `플래그 없음`과 `--render-profile shadows_v1`로 실행(`s0e-none`, `s0e-shadows`)한 결과, 프레임 924장(로봇 3대)의 JPEG 바이트 SHA-256이 **모두 같았고**(`frames_differing=0`) `result.json`은 wall·부하·프로필 표기를 뺀 전체가 같았다([stage0-compare.json](stage0-compare.json)). 이 Mac의 "785장 중 1장이 1단계 다름" 전례는 나타나지 않았다. 더 나아가 같은 케이스를 워커 1/2, 서로 다른 부하에서 반복한 S1·S2·S3(shadows), N1·N2·N3(noshadow), 단계 1(워커 2)과 단계 2(워커 1)를 짝지어 비교한 결과, 프레임이 전부 같고 결과도 같았다([analysis-repro.json](analysis-repro.json)). **물리와 영상은 재실행에 결정적이다. 따라서 "기준 두 번(S1↔S2)의 변동"은 결과·영상에서 0이며, 변하는 것은 wall·CPU(호스트 부하)뿐이다.**

**단계 1 — 케이스 성공(12/arm).** 결과는 두 arm이 같다.

| 단계 | shadows_v1 | noshadow_v1 | 원인(두 arm 같음) |
|---|---|---|---|
| align | 3/3 | 3/3 | — |
| grasp_lift | 3/3 | 3/3 | — |
| carry L0 | 0/3 | 0/3 | SELF_POSE_UNCERTAIN(σ 조기 종료, 정지 SIM 8.7–9.5 s) |
| setdown(목적지) | 0/3 | 0/3 | OWN_IMAGE_INVALID(6.05 s) |
| 합계 | 6/12 | 6/12 | |

**영상 검사(`valid_frame` 식, 저장 프레임 오프라인; 로봇 r1/r2, 프레임 통과율).** 통과율은 통과 프레임/전체 프레임이다. 거절 사유 분해(V<8 / 대비 / 표준편차)는 프레임 수다. [analysis-stage1.json](analysis-stage1.json).

| 단계 (프레임 창) | shadows_v1 r1 / r2 | noshadow_v1 r1 / r2 | 거절 사유(noshadow) |
|---|---|---|---|
| align 전체 | 1.000 / 1.000 | 1.000 / 1.000 | 없음 |
| grasp_lift 전체 | 1.000 / 1.000 | 1.000 / 1.000 | 없음 |
| carry 전체 | 1.000 / 1.000 | 1.000 / 1.000 | 없음 |
| **setdown, 첫 6.05 s(같은 창, 실패 시각까지)** | **0.917 / 1.000** | **0.583 / 0.458** | r1: V<8 30; r2: V<8 39, 대비 18, 표준편차 18 |
| setdown 각 arm 실행 전체(참고, 창이 다름) | 0.068 / 1.000 (r1 V<8 906/972) | 0.630 / 0.407 (81프레임) | shadows는 r2가 계속 유효해 SIM 66 s까지 돌았다 |

- 평균 V(밝기): align r1 139.6 → 119.0, r2 123.6 → 118.5. setdown 첫 6.05 s r1 41.2 → 39.0, **r2 43.7 → 26.7**. 이 프레임 창에서 V<8 비율 평균은 r1 0.121 → 0.136, **r2 0.005 → 0.477.**
- **어두운 바닥 내려놓기 목적지(필수 사례).** 기준선(shadows)은 r1이 `OWN_IMAGE_INVALID`로 거절되는 기존 현상(b-v6c 0/13)을 그대로 재현했다(r1 실패, 세 시드 모두). noshadow는 이를 줄이지 못했다. 실패 로봇이 **r2로 옮겨가고**(r2 프레임이 더 어두워짐: 평균 V 43.7 → 26.7) r1도 거절 프레임이 늘었다(2 → 10/24). 결과는 0/3 → 0/3.

**검출(기존 검출기, 문턱 불변; 프레임 비율).**

| 단계·로봇 | 지표 | shadows_v1 | noshadow_v1 |
|---|---|---:|---:|
| align r1 / r2 | 빔 검출(visible) | 1.000 / 0.943 | 1.000 / 0.959 |
| align r1 / r2 | 밴드 끝 검출(BAND_VISIBLE) | 0.875 / 0.853 | 0.865 / 0.861 |
| align r1 / r2 | 태그 유효 갱신 프레임 | 0.387 / 0.383 | 0.387 / 0.382 |
| grasp_lift **r1** | 빔 검출(visible) | **0.987** | **0.551** |
| grasp_lift r2 | 빔 검출(visible) | 1.000 | 1.000 |
| grasp_lift r1 / r2 | 잡기 화면(grip_view) | 0.474 / 0.481 | 0.474 / 0.481 |
| carry r1 / r2 | 빔 검출(visible) | 0.209 / 1.000 | 0.188 / 1.000 |

- grasp_lift r1의 빔 검출이 절반으로 떨어졌지만(77/78 → 43/78프레임) 잡기 화면 판정은 같아 grasp_lift는 3/3을 유지했다. 원인은 추적하지 않았다.

**PF 추정 오차와 σ(정답 대비, 평가 전용, 각 케이스 기준 시점 평균).**

| 단계 | 지표 | shadows_v1 r1 / r2 | noshadow_v1 r1 / r2 |
|---|---|---|---|
| align | 위치 오차(mm) | 2.8 / 16.5 | 3.6 / 23.2 |
| align | 방향 오차 |yaw|(mrad) | 1.3 / 4.1 | 2.6 / 6.8 |
| align | σ_yaw 최댓값 평균(mrad) | 13.0 / 10.9 | 12.9 / 10.8 |
| grasp_lift | 위치 오차(mm) | 23.3 / 34.1 | 23.4 / 34.1 |
| carry L0 | 위치 오차(mm) | 15.1 / 22.2 | 14.5 / 21.4 |
| carry L0 | σ_yaw 최댓값 평균(mrad) | 52.6 / 52.1 | 52.7 / 51.6 |
| setdown | σ_yaw 최댓값 평균(mrad) | 34.7 / 34.1 | 34.9 / 34.1 |

- align의 위치 오차가 noshadow에서 29–41 % 커졌지만(mm 단위, 통과 기준 안) σ는 같다. carry σ는 두 arm 모두 조기 종료 문턱을 넘겼다.

**시간(부수 지표; 워커 1, seed 911).** CPU 초는 `/usr/bin/time -l`의 user+sys(워커 자식 포함). [timing.json](timing.json), [driver.txt](driver.txt).

| 실행 | 부하 시작→끝(1분) | align+grasp CPU s (wall s) | carry CPU s | setdown CPU s (wall s) |
|---|---|---|---:|---|
| S1 shadows | 12.7 → 9.6 | 168.7 (171) | 27.4 | 223.1 (264) |
| N1 noshadow | 22.3 → 59.2 (이후 90) | 134.9 (231) | 33.0 | 15.4 (26) |
| N2 noshadow | 83.3 → 30.9 | 120.1 (170) | 14.2 | 8.4 (9) |
| S2 shadows | 23.4 → 15.2 | 175.1 (180) | 26.4 | 220.6 (257) |
| N3 noshadow(추가) | 21.5 → 23.5 | **72.0 (76)** | 24.2 | — |
| S3 shadows(추가) | 23.5 → 114.6 | 257.0 (527) | 22.3 | — |
| 단계 0 align만: none / shadows / noshadow | 9.9–13.9 | 112.1 / 110.8 / **56.7** (wall 116 / 120 / 58) | — | — |

- **기준 변동.** S1 168.7 ↔ S2 175.1(+3.8 %), 단계 0 none 112.1 ↔ shadows 110.8(−1.2 %)로 부하가 낮을 때 기준의 CPU 재현성은 몇 %다. 그러나 부하가 튈 때 CPU도 부풀었다(S3: 같은 일에 257 s, +47 %). N1·N2는 부하 22–90 구간이라 노이즈가 크다(135, 120 vs 조용한 구간 N3 72).
- **속도 이득.** 같은 일(영상·궤적 바이트 동일)을 quiet 구간에서 비교하면 align 단계 CPU 112 → 57 s(−49 %, 단계 0), align+grasp 172(S1·S2 평균) → 72 s(−58 %, N3). 부하 스파이크에 걸린 N1·N2는 −22~−30 %로 작게 나온다(부하 영향). **범위: 대략 CPU 절반(−50 % 안팎, 표본 소수, 부하 민감).** SIM 초당 CPU: align+grasp 3.6 s/s → 1.5 s/s(N3) 정도. 정적 sim-speed 기록의 "렌더 −74 %"는 렌더만의 값이고, 이 probe에서는 인식·PF 등이 남아 전체는 약 절반이다.
- **setdown 칸은 렌더 속도 비교가 아니다.** shadows는 r2가 계속 유효 영상을 받아 `SIM_LIMIT` 66 SIM s까지 돌았고(CPU 220 s), noshadow는 두 로봇이 같은 시각에 거절되어 6.55 s에 종료했다(CPU 8–15 s). 종료 경로가 달라서 CPU를 SIM 시간으로 나눌 수 없다.
- 명령어 수는 위 이유로 쓰지 않는다.

**TensorBoard.** 새 스냅샷 `outputs/tensorboard/0929-render-profile-ab`(49 케이스 run: `ST1-SH`/`ST1-NS`=단계 1, `T2-*`=시간 반복, `S0-*`=단계 0·smoke; `condition` 끝에 프로필). EventAccumulator로 49개 run의 `offline/stage_pass`·`result/wall_s`·`result/sim_s`가 `cases.jsonl`과 같음을 확인했다(0 불일치). `tensorboard-view.json`에 `render_profile_ab_20260929` 키만 추가했다(고정 카드: stage_pass, r1/r2 프레임 통과율, sim_s, wall_s, commands, model_calls, invocation_cpu_s). 서버는 띄우지 않았고 고정 카드 링크를 열어 보는 표시 검증은 하지 않았다. 뷰 생성기: [build_tb_views.py](build_tb_views.py).

### 가설 판정

| 가설 | 판정 |
|---|---|
| 그림자를 끄면 어두운 목적지 바닥의 `OWN_IMAGE_INVALID`가 줄 것이다(기대) | **반증.** 0/3 → 0/3, 같은 창(6.05 s)에서 r2의 통과율이 1.00 → 0.46으로 나빠지고 r1은 0.92 → 0.58. 정적 관찰의 경고(핫스팟 소멸로 평균 V 하락)가 맞았다 |
| 렌더 프로필 A/B의 기본 불변(플래그 없음 = shadows_v1) | **확인**(프레임 바이트 동일 924/924, 결과 동일) |
| noshadow_v1은 인식·성공을 크게 바꾼다 | **align/grasp/carry에서는 반증**(결과·검사 통과율 동일). 바뀐 것: 밝기(align r1 평균 V −15 %), grasp_lift r1 빔 검출(0.99 → 0.55), align PF 오차(mm, +29–41 %), 목적지 영상(더 어두워짐) |
| 그림자 끄기는 CPU 시간을 줄인다 | **확인**(−50 % 안팎, 부하 민감, 표본 소수) |
| 재실행 변동이 결과를 흔든다 | 이 probe에서는 **없음**(영상·결과 바이트 동일). 변동은 wall·CPU뿐 |

## 한계

- 그림자·반사 유무는 관측 분포를 바꾼다. 기준선과 별도 조건이며, 이 A/B의 성공률을 기존 b-v6c/b-v6d 성공률에 이어 붙이지 않는다.
- **진단 규모.** 단계당 nominal 케이스 3(시드는 PF 난수만 바꿈, 사실상 1개+변형)이고 nominal 셀 하나뿐이다. 다른 셀·경로 구간·목적지(L1 이후, 다른 구역)에서 같은 방향이라는 보장은 없다. 물리와 영상이 재실행에 결정적이라 반복으로 분산을 줄일 수 없고, 일반화는 셀·시드를 늘려서만 볼 수 있다.
- **속도는 부하에 민감하다.** 이 Mac은 실행 중 다른 작업으로 부하가 60–115까지 튀었다(N1, N2, S3). 부하 스파이크 구간에서 CPU 초도 최대 +47 % 부풀었다. −50 % 안팎은 quiet 구간(N3, 단계 0)의 값이고 표본이 적다. 명령어 수는 워커 자식을 세지 않아 쓰지 못했다.
- 실물에 더 가까워지는지는 검증하지 않았다. 실물 방은 그림자가 있으되 부드럽다는 가정이 남아 있고(측정 없음), `noshadow_v1`이 실물 영상 분포에 더 가깝다는 근거는 없다. 이번 결과(목적지 영상이 더 어두워짐)는 오히려 실물과의 거리가 늘 수 있음을 시사하지만 실물 영상과 비교하지 않았다. sim2real(#213/#214) 영향은 별도 실물 영상 비교로 검증한다.
- 정적 프레임에서 조명 분포 자체가 바뀌었다(핫스팟 소멸). "그림자만 제거"가 아니므로, 더 세분화가 필요하면 그림자만/반사만 arm(`castshadow` 끄기와 `reflectance` 0을 분리한 프로필)을 새 이름으로 추가해야 한다. 목적지가 더 어두워지는 원인(반사 0의 효과인지, 그림자 광원 제거의 효과인지)은 분리하지 않았다.
- 이 프로필은 시뮬레이터 카메라 렌더(top·로봇·관찰)에 모두 적용된다. 공용 top RGB 입력도 함께 바뀐다. 이 probe는 top 영상 인식을 쓰지 않으므로 top 입력 영향은 측정하지 못했다.
- b-v6d의 carry는 σ로 조기 종료돼 운반 구간 이후의 영상(운반 중 바닥)은 이 A/B에서 보지 못했다. 목적지(setdown)는 staged 진입이라 운반 후 실제 도착 자세의 영상이 아니다.
- 프레임 통계는 오프라인(저장 프레임에 `valid_frame` 식을 그대로 적용, 제어기 입력 경로의 실제 판정이 아님). 검출기 통과율은 "검출기가 낸 값"이며 정답과의 정확도 평가가 아니다.
- 계획서 명령에서 `--prior-std e2e`가 빠져 있었다(위 실행 기록). 분석 스크립트의 `--t-max` 옵션은 실행 뒤(`96971959`)에 추가했다(같은 창 비교용; 나머지 분석 코드는 `584ee391` 그대로).

## 결과 위치·해시

- raw(로컬): `/Users/changmin/projects/ugrp/outputs/render-profile-ab-20260929/`(약 479 MB, 28개 실행 폴더·`.time`·`driver.log`). 원격 백업이 아니다. 실행별 `cases.jsonl`·`artifacts.sha256.json`·`manifest.json`의 SHA-256은 [raw_sha256.json](raw_sha256.json)에 있다.
- 분석 산출물(이 폴더): [analysis-stage1.json](analysis-stage1.json)(단계 1 프레임 통계), [analysis-setdown-t6p05.json](analysis-setdown-t6p05.json)(setdown 같은 창), [analysis-repro.json](analysis-repro.json)(재실행 프레임 동일성), [stage0-compare.json](stage0-compare.json), [timing.json](timing.json), [build_tb_views.py](build_tb_views.py). 분석 스크립트: `scripts/analyze_render_profile_ab.py`(테스트 `tests/test_render_profile_ab_analysis.py`).
- 실행 SHA `584ee39118aed683869b965709056c7008aa008d`(source_dirty false). 실행 시작 부하는 표와 `driver.log`에 있다. 잠금: 단계 0(A2), 단계 1·2(B), 추가 반복(C) 각각 `agent_lock`을 잡고 EXIT에서 해제했고 종료 뒤 `status`가 null이다.

## 사용자가 정할 것

1. **채택 후보로 볼지.** 이 A/B만 보면 noshadow_v1은 인식·성공을 개선하지 않았고(목적지에서는 악화) CPU를 약 절반으로 줄인다. 최종 환경 고정(#218)에서 정하며, 속도만을 이유로 채택하기에는 목적지 영상 악화가 걸린다.
2. 그림자만/반사만을 분리한 arm(목적지가 어두워지는 원인 분리)과 밝기를 보정한 부드러운 그림자 arm(`softshadow_v1`)을 더 돌릴지. 근거가 되는 실물 방 조명 실측을 #213/#214 항목에 추가할지.
3. 셀·시드를 늘린 확대(다른 셀, carry 구간 이후)를 할지. 물리가 결정적이므로 시드 반복보다 셀·경로 구간을 늘리는 쪽이 정보가 많다.
4. 채택 시 번들·workflow ID 배정(#218에서, v81/2.14.0 이후 번호).

## 참고 자료

- 저장소 측정·구현(재사용): `experiments/2026-09-26-sim-speed/README.md`(그림자 광원 4개·shadowsize 4096·MSAA 4, 그림자 끄기 300,548 px 변경, 반사 끄기 18,996 px 변경, robot_cam 렌더 CPU 비중), `docs/sim_speed.md`, `docs/local_simulation.md`(표준 관찰 창의 그림자·반사 생략), `scripts/dispatch_native_view.py`(관찰 창 `mjRND_SHADOW`/`mjRND_REFLECTION`), `scripts/eval_zone_own_perception_v3_1.py`(`LIGHTING` 조명 스트레스 프로필: 빌드된 모델의 광원 배열을 고치는 선행 방식), `harness/zone_pair_vision.py`(`valid_frame`), `experiments/2026-09-29-pair-v6c-carry/README.md`(내려놓기 목적지 `OWN_IMAGE_INVALID` 0/13), `experiments/2026-09-26-zone-m2-pair/README.md`·`experiments/2026-09-26-zone-eval-topcam/README.md`·`docs/report/04-executor.md`(조명·그림자로 인한 인식 실패 사례).
- MuJoCo 3.12 문서: XML reference의 `light`의 `castshadow`(그림자를 만드는 광원마다 렌더 패스가 하나 더 든다는 설명)와 `material`의 `reflectance`, `mjtRndFlag`(`mjRND_SHADOW`, `mjRND_REFLECTION`). 이번 세션에서 웹 문서를 다시 열지는 않았고, 설치본 MuJoCo 3.12.0에서 두 속성의 효과를 컴파일된 모델과 렌더 프레임으로 직접 확인했다(위 테스트·정적 관찰).
- 도메인 무작위화(조명·질감 변형)가 sim2real 완화책이라는 선행 근거는 `docs/design/2026-09-26-vision-localization-tagfree.md`(Tobin 등 2017 인용)와 `docs/research_todo.md`에 있다. 이 프로필은 무작위화가 아니라 고정 조건의 변경이다.
- 만들지 않은 것: 약한 그림자 프로필(근거 부재), 새 렌더러·후처리, 러너별 별도 플래그(사전등록 소스 보존).
- 이번 측정(2026-09-29 실행)의 실행·분석 방법은 저장소 기존 도구를 재사용했다: `scripts/run_pair_stage_probes.py`, `scripts/build_pair_stage_probe_views.py`, `scripts/export_offline_audit.py`, `harness/zone_pair_vision.valid_frame`·`harness/owncam_pair_beam_v2` 검출기(문턱 불변). 새 외부 문헌은 조사하지 않았다.
