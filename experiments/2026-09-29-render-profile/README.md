# 2026-09-29 렌더 프로필(그림자·반사) A/B — 측정 완료(단계 probe, 진단 규모)

**상태: 물리 probe를 실행했다(SIM 시간, 잠금 보유, b-v6d 정책, 소스 `584ee391`). 아래 "결과"에 채웠다. 이것은 단계 probe 비교이며 E2E 성공이 아니다. b-v6d의 운반은 σ(SELF_POSE_UNCERTAIN)로 조기 종료돼 성공이 아니다. 렌더 프로필의 채택·번들 등록은 하지 않았다(사용자가 #218에서 정한다). PR은 opt-in 코드와 이 기록을 담는다.** 계획서였던 이전 본문은 아래에 그대로 두었고, 실행에서 계획과 달라진 점은 "실행 기록"에 적었다.

**2026-09-29 추가(사용자 결정): "그림자/반사는 빼고 밝게. 기존 영상에 맞추지 말고 더 밝게 해. 굳이 더 테스트하지 않는다."** 그래서 새 프로필 `noshadow_bright_v1`(opt-in)을 추가했고, 이어서 밝은 바닥 프로필 `floor_light_v1`(맨 아래 "floor_light_v1(밝은 바닥)" 절)을 추가했다. 정의·근거 수치·검증 범위는 맨 아래 "## noshadow_bright_v1(밝게)" 절. 기본 경로·기존 두 프로필은 바이트 불변이고 물리는 바뀌지 않는다. 이 프로필로 인식·성공을 다시 재지 않았다. 채택(기본값 여부)은 #218 최종 환경 동결 때 정한다.

## 왜 하는가

사용자 판단: 시뮬레이터의 그림자와 바닥 반사가 실물보다 과하다. 그러나 로봇 카메라·공용 top 영상이 바뀌면 인식과 제어 결과가 바뀐다. 그래서 **기본값은 그대로 두고** 렌더 프로필을 새 버전으로 분리하고, A/B로 영향을 잰 뒤 최종 환경 고정(#218) 때 채택 여부를 정한다. 기준선(b-v6c 등)은 지금의 그림자 켠 조건이다. 카메라 배치·FOV, 로봇 외관, 물체, 물리는 바꾸지 않는다.

## 프로필 정의

`sim/render_profile.py`. 장면 XML 문자열만 고친다(`<light castshadow>`, `<material reflectance>`). 실행 기록에는 이름·정의 해시가 남는다.

| 프로필 | 하는 일 | 정의 해시(SHA-256) | 기본과 차이 |
|---|---|---|---|
| `shadows_v1` (= 플래그 없음) | 아무것도 바꾸지 않는다 | `f10e51da…c598f8c5` | 없음(같은 XML 문자열 객체를 돌려준다) |
| `noshadow_v1` | 모든 `<light>`에 `castshadow="false"`, 반사 재질(`reflectance` 속성이 있는 모든 `<material>`)을 `0`으로 | `c30f1ef6…5abc5809` | zone 장면 기준 광원 4개(키 3 + `dispatch_ceiling`)의 그림자 끔, `groundmat` 반사 0.035 → 0. 광원의 diffuse/ambient/specular, headlight, 텍스처, `shadowsize`, MSAA는 그대로 |
| `noshadow_bright_v1` | `noshadow_v1`의 두 편집에 더해 모든 `<light>`를 점광원(`cutoff=180`)으로 바꾸고 diffuse·ambient·specular에 0.3을 곱한다 | `f994f8d6…e2e5f` | 아래 "noshadow_bright_v1(밝게)" 절. 물리 배열은 바뀌지 않는다(테스트로 mjModel 전 배열 비교) |
| `floor_light_v1` | `noshadow_bright_v1`의 편집에 더해 바닥 텍스처 `ground`(재질 `groundmat`의 체커)를 어두운 남색 체커 rgb1 .20 .22 .24 / rgb2 .27 .29 .31 에서 무채색 중간톤 회색 체커 rgb1 .36 .35 .34 / rgb2 .62 .61 .59 로 바꾼다 | `e3ea8aeb…2b6ec5` | 아래 "floor_light_v1(밝은 바닥)" 절. tex_data 외 모든 mjModel 배열이 noshadow_bright_v1과 같다(테스트) |
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

## noshadow_bright_v1(밝게) — 2026-09-29, 정지 프레임 측정, 물리 실행 없음

### 사용자 결정과 이 절이 답하는 것

A/B에서 `noshadow_v1`은 CPU를 약 절반으로 줄였지만 영상이 어두워졌다(setdown r2 평균 V 43.7 → 26.7, 검사 통과율 0.92/1.00 → 0.58/0.46). 사용자는 "그림자·반사는 빼고 밝게"를 정했고, 이어서 "기존 영상에 맞추지 말고 그냥 더 밝게, 어두워서 못하는 게 비현실적"이라고 정정했다. 원인 분리는 하지 않기로 했으나, 밝기를 정하다가 **어두워진 원인이 조명 세기가 아니라 렌더러의 검은 프레임**임이 드러나 그것만 확인했다(아래). 물리 probe는 하지 않았다(잠금 없음). 실행한 것은 정지 프레임 렌더뿐이다.

### 정의

`sim/render_profile.py`의 `noshadow_bright_v1`(정의 해시 `f994f8d61af3157e973764225d581758106329ab2259922e28d5d14881fe2e5f`). 장면 XML만 고친다.

1. 모든 `<light>` `castshadow="false"`, 반사가 있는 모든 `<material>` `reflectance=0` (`noshadow_v1`과 같음)
2. 모든 `<light>` `cutoff="180"` (스포트라이트 → 점광원)
3. 모든 `<light>`의 `diffuse`, `ambient`, `specular`에 **하나의 스칼라 0.3**을 곱한다(속성이 없으면 MuJoCo 기본값 ambient 0, diffuse .7, specular .3에서 곱함)

컴파일된 모델 검증: 기본과 다른 mjModel 배열은 `light_ambient`, `light_castshadow`, `light_cutoff`, `light_diffuse`, `light_specular`, `mat_reflectance`뿐이다(`tests/test_render_profile.py`, 나머지 배열·timestep·noslip·카메라 위치/FOV 동일). `verify_model`은 그림자·반사가 남았거나 스포트 광원(`cutoff != 180`)이 남으면 실행을 막는다. 카메라 배치·FOV, 로봇 외관, 물체, 물리, 헤드라이트, 텍스처는 그대로다. **실물 방 밝기는 측정하지 않았다. 값은 shadows_v1에 맞춘 것이 아니라 아래 규칙으로 정지 프레임에서 정했다.**

### 왜 점광원(cutoff 180)인가 — `noshadow_v1`의 검은 프레임

- 같은 상태(A/B raw의 `setdown` 시작 체크포인트, `mj_setState`+`mj_forward`)에서 r2의 own 카메라는 `noshadow_v1`에서 **모든 픽셀이 0**(평균 V 0.0, V<8 비율 100 %)이고 shadows_v1에서는 평균 V 34.6이다. A/B 원본 프레임에서도 noshadow arm의 r2는 setdown 프레임 18번(0부터)부터 평균 V 0이 된다(s911, 처음 30장 중 12장). 그러니 "어두워짐"의 큰 몫은 밝기가 아니라 **검은 프레임**이다.
- 이것은 조명 세기 때문이 아니다. 광원 세기를 5배로 올려도, 헤드라이트를 5배로 올려도, 문제의 광원(세 번째 광원)의 diffuse·ambient·specular를 0으로 만들어도 검다. 렌더러 플래그(`mjRND_SHADOW`)를 끄고 `castshadow` 속성은 그대로 두어도 검다(XML이 아니라 그림자 없는 렌더 경로의 문제). 세 번째 광원을 0.1 m 옮기거나 방향을 기울이면 값이 바뀐다. 그 시점 r2 카메라의 시선과 그 광원의 축 사이 코사인이 0.997이다(관찰이며 기전은 확인하지 않았다).
- `cutoff`를 60·90·120으로 줄이거나 넓혀도 검고, **179 이상(점광원)에서만 사라진다.** 스포트 그림자 없는 경로를 피하는 방법으로 점광원을 골랐다.
- 무작위 자세 감사(로봇 r1·r2 각 60자세, 기준 상태 주변 x 0.3–5.5, y −2.6–0.4, yaw 전 범위, 렌더만, 일부는 비물리적 자세): **전체 어두운 프레임(평균 V<1) shadows_v1 0/120, noshadow_v1 16/120(13 %), noshadow_bright_v1 0/120.** [brightness_calibration.json](static_frames/brightness_calibration.json)의 `black_audit`.
- 점광원으로 바꾸면 스포트 원뿔이 사라져 조명이 균일해지므로, 원뿔 밖의 어두운 바닥(setdown 목적지)은 밝아지고 원뿔 안의 밝은 곳은 다소 어두워진다. 이 변화는 의도한 것이다(어두워서 못 하는 것을 줄임).

### 0.3을 정한 방법(정지 프레임, 관측 전에 정한 규칙)

정지 프레임: A/B raw(`st1-*`)의 `mj_getState` 체크포인트 8개(align·grasp_lift·carry·setdown의 시작·종료 시점, seed 911)를 같은 장면에 복원하고 로봇 own 카메라(실제 포트 경로: 어안 재매핑 + JPEG q82)와 공용 top 카메라를 렌더했다. 도구: [calibrate_brightness.py](static_frames/calibrate_brightness.py), 결과: [brightness_calibration.json](static_frames/brightness_calibration.json), 그림: [noshadow_bright_v1_montage.jpg](static_frames/noshadow_bright_v1_montage.jpg)(왼쪽 shadows_v1, 가운데 noshadow_v1, 오른쪽 bright). 통계는 `valid_frame`과 같은 림 마스크와 HSV V로 계산했다. 광원 배율 k를 0.15–0.5로 훑고 아래 규칙을 모든 상태·로봇에 적용했다.

- 규칙 1(검사 여유): V<8 비율 ≤ 1 %(기준 25 %의 1/25), 1–99 백분위 대비 ≥ 30(기준 15의 2배), V 표준편차 ≥ 6(기준 3의 2배).
- 규칙 2(과노출 상한): 포화(V ≥ 250) 비율 ≤ max(shadows_v1, noshadow_v1) + 1 %p.
- 규칙 3: 위를 만족하는 k의 구간 안에서 가운데 값.

결과: k = 0.26–0.34가 규칙을 모두 만족하고 0.36에서 setdown r1의 벽 띠가 포화(15 %)해 규칙 2를 깬다. 그 구간의 가운데 근처 **k = 0.30**을 골랐다(0.34에서는 align·grasp의 큰 물체도 포화가 0.8 % → 8.9 %로 뛰는 절벽이 있어 그 아래로 잡음).

| k | setdown 평균V / 하위10%V / 포화% (r1) | align_entry 포화% (r1/r2) | grasp_lift_entry 포화% (r1/r2) | 최악 V<8 % | 최소 대비 | 최소 표준편차 |
|---|---|---|---|---:|---:|---:|
| shadows_v1 | 32.7 / 7 / 0.0 | 2.4 / 2.3 | 8.3 / 8.5 | 30.1(r1 setdown, 검사 실패 2건) | 106 | 35.8 |
| noshadow_v1 | 37.4 / 9 / 0.0 | 2.3 / 2.0 | 8.2 / 8.7 | 100(r2 setdown, 검은 프레임) | 0 | 0 |
| 0.20 | 56 / 14 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.52 | 147 | 19.3 |
| **0.30** | **68.8 / 17 / 0.0** | **0.5 / 0.1** | **0.8 / 0.2** | **0.30** | **204** | **25.6** |
| 0.34 | 74 / 18 / 0.0 | 2.8 / 2.3 | 8.9 / 8.3 | 0.24 | 221 | 28.2 |
| 0.36 | 76 / 19 / 15.2 | 2.8 / 2.4 | 9.0 / 8.4 | 0.22 | 227 | 28.1 |
| 0.50 | 81 / 23 / 23.6 | 3.0 / 2.5 | 9.4 / 8.7 | 0.15 | 223 | 28.5 |

### 0.3에서의 수치(shadows_v1과 비교, 정지 프레임 16개: 8상태 × r1/r2)

- **검사(`valid_frame` 식): 16/16 통과**(shadows_v1 14/16: setdown 시작·종료 r1이 V<8 28.6·30.1 %로 실패 — A/B의 기존 `OWN_IMAGE_INVALID` 재현. noshadow_v1 14/16: setdown r2가 검은 프레임). V<8 비율 최대 0.30 %(기준 25 %), 대비 최소 204(기준 15), 표준편차 최소 25.6(기준 3).
- **가장 어두운 장면(setdown, 목적지 바닥):** 평균 V 32.7/34.6 → 68.8/67.7(r1/r2, 약 2배), 하위 10 % V 7/8 → 17/17.
- **잘 보이는 장면:** 평균 V가 오히려 낮다. align_entry r1 130.1 → 107.9(−17 %), align_stop r1 154.6 → 124.1(−20 %), grasp_lift_entry r1 115.2 → 112.3(−3 %). 스포트 원뿔의 밝은 중심이 사라진 결과다. **"모든 장면이 shadows_v1보다 밝다"가 아니라 "어두운 곳을 끌어올리고 밝은 곳의 과노출(핫스팟)을 줄인다"이다.**
- **포화(V ≥ 250):** align_entry 2.4 → 0.5 %, grasp_lift_entry 8.3 → 0.8 %(r1). 그 외는 shadows_v1과 같은 수준(align_stop 11.6, grasp_lift_stop 39.7/38.5, carry 23.5–25.0). 어떤 상태도 규칙 2를 넘지 않는다.
- **더 밝게 못 올리는 이유:** 어두운 바닥의 하위 10 % V는 k를 0.3 → 0.5 → 0.7로 올려도 17 → 23 → 30 정도로 느리게 늘지만, 벽 띠·빔은 0.36부터 포화(setdown 15–24 %)한다. 8비트 영상 한 장 안에서 어두운 면과 밝은 물체의 밝기 비가 크다(하위 10 % V 17 대 벽 띠 250 근처). 톤 매핑 없이 하나의 스칼라로 "어두운 면 V ≥ 100"은 불가능하다. 규칙에 넣지 않았고, 사용자가 더 밝은 값을 원하면 k 한 상수만 바꾸면 되지만 새 프로필 이름·해시가 필요하다.
- 공용 top 카메라 평균 V 86.9 → 100.2(+15 %, 점광원 효과). top 영상 인식은 이번에도 재지 않았다.

### 속도 이득(정지 프레임 기준, 렌더만)

640×480 own 카메라 한 프레임의 이 프로세스 CPU 시간(`time.process_time`, 세 프로필을 교차해 5회 반복, 부하 평균 14–21의 Mac): shadows_v1 대비 `noshadow_v1` **0.15배**(0.134 → 0.020 s), `noshadow_bright_v1` **0.15배**(0.021 s). 즉 밝기 조정은 렌더 시간 이득을 그대로 유지했고(+6 % 이내, 부하 잡음 범위) 렌더 −85 %이다. 이것은 A/B의 전체 probe CPU −50 % 안팎과 다른 값이다(probe에는 인식·PF·물리가 남는다). 이 프로필로 probe 전체의 CPU를 다시 재지는 않았다.

### 아직 검증되지 않은 것

- **이 프로필로 인식·성공을 재측정하지 않았다.** 빔·집게 색 검출, PF, 검사 통과율, 단계 성공은 미측정이다. 특히 빔 색조가 바뀐다(밝은 노랑 → 노란 초록, `noshadow_v1`의 채널 클리핑이 줄어든 결과, montage 참고). 색 범위 검출기의 문턱은 바꾸지 않았고 영향은 보지 않았다.
- 실물 영상과 비교하지 않았다. 실물 방 밝기는 저장소에 없다(**실물 방 미측정, 값은 위 규칙으로 정지 프레임에서 정함**). 실물에 더 가깝다는 근거가 없다.
- 정지 프레임은 seed 911의 nominal 8개 시점뿐이다. 다른 경로 구간·목적지·로봇 자세는 무작위 자세 감사(렌더만)에서 검은 프레임이 없다는 것까지만 봤다.
- 자세 감사의 자세는 일부가 비물리적이다. 검은 프레임의 기전(광원 축과 시선 정렬)은 확인하지 않았다.
- 점광원은 스포트 원뿔을 없앤다. 실제 방의 조명 배치와 무관하게 균일해진다(측정 없음).
- 채택 시점: **#218 최종 환경 동결 때** 기본값으로 삼을지 정한다. 지금은 opt-in(`--render-profile noshadow_bright_v1`)뿐이고 기본 경로(플래그 없음 = shadows_v1)는 바이트 불변이다. 채택하면 실행 번들·workflow ID를 새로 배정하고 기존 기준선과 합산하지 않는다.

## floor_light_v1(밝은 바닥) — 2026-09-29, 정지 프레임 측정, 물리 실행 없음

### 사용자 결정과 한계

사용자 결정: "실제 방 바닥은 지금 시뮬레이션의 어두운 남색 바닥보다 더 밝은 색이다." 그래서 `noshadow_bright_v1`의 편집 위에 바닥 색만 밝은 중간톤으로 바꾼 프로필 `floor_light_v1`을 추가했다(opt-in). **실물보다 밝은 색이라는 사용자 진술만 있고 실제 바닥 색값은 측정하지 않았다(저장소에도 없다).** 그래서 색은 "채도 낮은 밝은 중간톤 회색, 빔 노랑과 먼 색"이라는 조건으로 정지 프레임에서 골랐고 실물 색과 같다는 뜻이 아니다. 물리 불변(장면 XML의 텍스처 색만 바뀜, 테스트로 확인), 기본 불변이다. 기존 프로필의 해시는 그대로다.

바뀌는 것: 바닥 텍스처 `ground`의 rgb1/rgb2뿐이다. 바닥 위의 구역 표시(`zone_pickup`, `zone_zone_A/B`의 반투명 색 덮개 rgba, 알파 0.14–0.3)는 그대로 둬서, 픽업 구역 위 바닥에는 옅은 파란 기운이 남는다(montage 참고). 광원 배율은 0.3 그대로.

### (a) setdown 목적지 — 이 프로필이 바꾸지 않는다

세그멘테이션 렌더(같은 어안 재매핑)로 픽셀이 어떤 물체인지 셌다. **setdown 시작·종료 프레임(r1·r2)에는 바닥 픽셀이 0이다.** 화면은 빔(연두 `cargo_cargoX__bar`, 약 6만 px)과 빔 위의 **어두운 그립 띠**(`__band_neg/pos`, rgba .06, 약 19만 px)뿐이다. 즉 A/B에서 "어두운 목적지"로 본 영역은 바닥이 아니라 이 띠다. 따라서 바닥 색은 setdown 영상에 영향이 없고(floor_light_v1 = noshadow_bright_v1: 평균 V 69/68 동일), setdown 통과는 광원 배율이 좌우한다. 띠 평균 V: shadows_v1 9.5/10.3(r1 검사 실패 V<8 28.6 %) → noshadow_v1 11.0/0.0(r2 검은 프레임) → noshadow_bright_v1·floor_light_v1 19.1/19.2. grasp_lift_stop·carry에서도 바닥은 보이지 않는다(빔·띠가 채움). 바닥이 보이는 정지 프레임은 align_entry·align_stop·grasp_lift_entry(r1·r2 6장)뿐이다.

### 정한 규칙(관측 전에 정함)과 결과

바닥이 보이는 6장(align_entry·align_stop·grasp_lift_entry × r1·r2)에서, 도구 [calibrate_floor.py](static_frames/calibrate_floor.py), 결과 [floor_light_calibration.json](static_frames/floor_light_calibration.json)(4개 프로필 × 8상태), [floor_candidates.json](static_frames/floor_candidates.json)(후보 색·배율), 그림 [floor_light_v1_montage.jpg](static_frames/floor_light_v1_montage.jpg)(열: shadows_v1, noshadow_v1, noshadow_bright_v1, floor_light_v1).

- R1 검사 여유(이전과 같음): V<8 ≤ 1 %, 대비 ≥ 30, 표준편차 ≥ 6, 전 상태.
- R2 포화(전체 프레임 V≥250) ≤ max(shadows_v1, noshadow_v1) + 1 %p, 전 상태.
- R3 바닥은 밝은 중간톤: 바닥 평균 V 100–180, 바닥 포화 ≤ 1 %.
- R4 빔 색 검출: 빔 색 마스크(`harness/owncam_pair_beam_v2.beam_colour_mask`, 문턱 불변)가 빔 픽셀 중 잡는 비율 ≥ 0.85, 바닥 오검출 픽셀이 shadows_v1 수준(0.15 % 이내).
- R5 바닥 무늬 단서: 바닥 픽셀 기울기 크기 / 평균 V(체커 경계의 상대 세기)가 shadows_v1의 80 % 이상.
- R6 AprilTag 대비(태그 판 픽셀의 V 95–5 백분위 차이) ≥ 180.

| 프로필 (바닥이 보이는 6장 평균/최악) | 바닥 평균V / 하위10%V | 바닥 포화 | 벽 V | 빔 V | 바닥−벽 V 차(align_entry) | 빔 마스크 재현율(최소) | 바닥 오검출 px(최대, 전체 25만 px 중) | 태그 대비(최소) | 바닥 기울기/V | 바닥 코너 수(중앙값) |
|---|---|---|---|---|---|---|---|---|---|---|
| shadows_v1 | 127 / 99 | 0.0 % | 70 | 234 | 55 | 0.86 | 317 (0.13 %) | 142 | 0.037 | 199 |
| noshadow_v1 | 111 / 98 | 0.0 % | 69 | 237 | 40 | 0.93 | 372 (0.15 %) | 144 | 0.017 | 366 |
| noshadow_bright_v1 | 106 / 98 | 0.0 % | 95 | 219 | 9 | 0.90 | 301 (0.12 %) | 245 | 0.015 | 224 |
| **floor_light_v1** | **143 / 120** | **0.0 %** | **96** | **219** | **45** | **0.90** | **356 (0.14 %)** | **245** | **0.031** | **134** |

- **(b) 빔·벽·태그 대비, 색 검출.** 빔 색 마스크는 빔을 shadows_v1과 같은 수준으로 잡는다(재현율 최소 0.86 → 0.90, 빔 픽셀 수 1.0만/장 동일). 바닥 오검출은 shadows_v1과 같은 자릿수(최대 356 px = 0.14 %)이고 빔 가장자리 픽셀로 보이며 새 바닥이 늘린 것이 아니다(noshadow_bright_v1 301). 무채색 회색은 빔 마스크의 채도 문턱(S ≥ 100)에 한참 못 미친다. 바닥−벽 밝기 차는 noshadow_bright_v1에서 9로 붕괴(벽이 밝아짐)했다가 45로 회복했다(shadows_v1 55). 태그 대비는 245(shadows_v1의 그림자에 가린 142보다 높음).
- **(c) 바닥 무늬.** 체커 경계의 상대 세기는 noshadow_bright_v1에서 shadows_v1의 40 %(0.015 대 0.037)로 줄었고 floor_light_v1에서 84 %(0.031)로 회복했다. 체커 두 색의 대비를 원래(.20/.27, 비 1.35)보다 키운 덕이다(.36/.62). **shadows_v1의 기울기에는 그림자 경계와 핫스팟이 섞여 있어 순수한 무늬 세기가 아니다.** 코너 수(`goodFeaturesToTrack`, 품질 문턱은 프레임 최대 반응 대비 상대값이라 불안정한 지표)는 199 → 134로 줄었다(shadows_v1의 67 %). 위치 추정에서 바닥 무늬를 실제로 쓰는지는 확인하지 않았고(PnP는 태그), 이 지표는 무늬 단서 유지의 대리 지표일 뿐이다.
- **(d) 포화.** 전체 프레임: align_entry 2.4/2.3 → 0.5/0.1 %, align_stop 11.8/11.6 → 11.5/11.6 %, grasp_lift_entry 8.3/8.5 → 0.8/0.2 %, grasp_lift_stop 38.7/28.3 → 39.7/38.5 %(빔 자체), carry 23.5–25.0 %(빔). 모든 상태에서 규칙 2 만족. 바닥 자체 포화 0.0 %.
- **R1 검사:** 16/16 통과, V<8 최대 0.31 %, 대비 최소 204, 표준편차 최소 32.1(noshadow_bright_v1 25.6; 바닥이 밝아져 올랐다).
- **광원 배율 0.3 유지.** 바닥 후보 색(A 따뜻한 회색 .52/.62, A2 .46/.62, D1 베이지 .42/.68, D2 무채색 .36/.62)은 모두 R1–R4·R6을 만족했다. 바닥 무늬(R5)는 체커 대비를 키운 D1(0.030)·D2(0.031)만 shadows_v1의 80 % 이상이라 D2(무채색, 색조 위험이 가장 작음)를 골랐다(베이지 D1도 잡음 범위에서 같다: 색 계열은 자유). 배율을 낮추면(0.25, 0.20) 빔이 어두워져 빔 마스크 재현율이 0.82로 떨어져 규칙 4를 깬다. 바닥이 밝아도 포화는 생기지 않아 배율을 더 낮출 이유가 없다. 그래서 별도 배율 프로필은 만들지 않았고 `floor_light_v1`은 0.3을 쓴다.

### 아직 검증되지 않은 것(floor_light_v1)

- 실제 바닥 색·명도 미측정(사용자 진술만). 실물 영상과 비교하지 않았다.
- 이 프로필로 인식·PF·단계 성공을 재측정하지 않았다(정지 프레임의 색 마스크·태그 대비뿐). 위치 추정이 바닥 무늬를 쓰는지 확인하지 않았다. AprilTag는 픽셀 대비만 봤고 실제 태그 검출기(PnP)를 돌리지 않았다.
- 정지 프레임은 seed 911 nominal의 8상태이고 바닥이 보이는 것은 6장뿐이다. carry·setdown의 실제 경로 구간(로봇이 이동하며 바닥이 보이는 프레임)은 보지 않았다.
- 구역 표시 덮개(반투명 파랑/주황)는 그대로라 그 위 바닥색이 순수한 회색이 아니다.
- 채택 시점은 #218이다. 지금은 `--render-profile floor_light_v1` opt-in뿐이다.

## 사용자가 정할 것

0. (2026-09-29 사용자 결정 반영) 그림자·반사를 빼고 밝게 가는 방향으로 `noshadow_bright_v1`을 만들었다. 기본값 여부는 #218에서 정한다. 아래 2·3번(그림자만/반사만 분리, `softshadow_v1`)은 사용자가 "더 테스트하지 않는다"고 해서 하지 않는다.
1. **채택 후보로 볼지.** 이 A/B만 보면 noshadow_v1은 인식·성공을 개선하지 않았고(목적지에서는 악화) CPU를 약 절반으로 줄인다. 최종 환경 고정(#218)에서 정하며, 속도만을 이유로 채택하기에는 목적지 영상 악화가 걸린다.
2. 그림자만/반사만을 분리한 arm(목적지가 어두워지는 원인 분리)과 밝기를 보정한 부드러운 그림자 arm(`softshadow_v1`)을 더 돌릴지. 근거가 되는 실물 방 조명 실측을 #213/#214 항목에 추가할지.
3. 셀·시드를 늘린 확대(다른 셀, carry 구간 이후)를 할지. 물리가 결정적이므로 시드 반복보다 셀·경로 구간을 늘리는 쪽이 정보가 많다.
4. 채택 시 번들·workflow ID 배정(#218에서, v81/2.14.0 이후 번호).

## 참고 자료

- 저장소 측정·구현(재사용): `experiments/2026-09-26-sim-speed/README.md`(그림자 광원 4개·shadowsize 4096·MSAA 4, 그림자 끄기 300,548 px 변경, 반사 끄기 18,996 px 변경, robot_cam 렌더 CPU 비중), `docs/sim_speed.md`, `docs/local_simulation.md`(표준 관찰 창의 그림자·반사 생략), `scripts/dispatch_native_view.py`(관찰 창 `mjRND_SHADOW`/`mjRND_REFLECTION`), `scripts/eval_zone_own_perception_v3_1.py`(`LIGHTING` 조명 스트레스 프로필: 빌드된 모델의 광원 배열을 고치는 선행 방식), `harness/zone_pair_vision.py`(`valid_frame`), `experiments/2026-09-29-pair-v6c-carry/README.md`(내려놓기 목적지 `OWN_IMAGE_INVALID` 0/13), `experiments/2026-09-26-zone-m2-pair/README.md`·`experiments/2026-09-26-zone-eval-topcam/README.md`·`docs/report/04-executor.md`(조명·그림자로 인한 인식 실패 사례).
- MuJoCo 3.12 문서: XML reference의 `light`의 `castshadow`(그림자를 만드는 광원마다 렌더 패스가 하나 더 든다는 설명)와 `material`의 `reflectance`, `mjtRndFlag`(`mjRND_SHADOW`, `mjRND_REFLECTION`). 이번 세션에서 웹 문서를 다시 열지는 않았고, 설치본 MuJoCo 3.12.0에서 두 속성의 효과를 컴파일된 모델과 렌더 프레임으로 직접 확인했다(위 테스트·정적 관찰).
- 도메인 무작위화(조명·질감 변형)가 sim2real 완화책이라는 선행 근거는 `docs/design/2026-09-26-vision-localization-tagfree.md`(Tobin 등 2017 인용)와 `docs/research_todo.md`에 있다. 이 프로필은 무작위화가 아니라 고정 조건의 변경이다.
- `noshadow_bright_v1` 정지 프레임 측정(2026-09-29)도 저장소 기존 도구를 재사용했다: `mj_getState` 체크포인트(`scripts/run_pair_stage_probes.py` `save_checkpoint`), `scripts/zone_pair_dev_runtime.make_scene`, `harness/zone_own_team_host.OwnCamTeamHost`의 실제 own 카메라 경로(`world.render_jpeg`), `harness/zone_pair_vision.valid_frame`의 림 마스크·문턱. 새 외부 문헌은 조사하지 않았고 검은 프레임은 MuJoCo 3.12.0에서 직접 측정했다(기전 미확인, 위 절). 광원의 `cutoff`·`diffuse`·`ambient`·`specular`는 MuJoCo XML 참조의 `light` 속성이다.
- 만들지 않은 것: 약한 그림자 프로필(근거 부재), 새 렌더러·후처리, 러너별 별도 플래그(사전등록 소스 보존).
- 이번 측정(2026-09-29 실행)의 실행·분석 방법은 저장소 기존 도구를 재사용했다: `scripts/run_pair_stage_probes.py`, `scripts/build_pair_stage_probe_views.py`, `scripts/export_offline_audit.py`, `harness/zone_pair_vision.valid_frame`·`harness/owncam_pair_beam_v2` 검출기(문턱 불변). 새 외부 문헌은 조사하지 않았다.
