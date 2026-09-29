# 2026-09-29 렌더 프로필(그림자·반사) A/B 계획 — 구현 완료, 측정 전

**상태: 코드와 오프라인 검증만 끝났다. 물리·probe는 한 번도 실행하지 않았다(다른 에이전트가 b-v6e 측정으로 `agent_lock`을 잡고 있었다). 아래 모든 "결과" 칸은 "미측정"이다.** 이 기록은 연구 결과가 아니며 단계 probe 기준 A/B 계획이다.

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

### 결과 (모두 미측정)

| 항목 | shadows_v1 | noshadow_v1 |
|---|---|---|
| 단계 0 기본 불변(프레임 바이트) | 미측정 | — |
| 영상 검사 통과율(r1 / r2) | 미측정 | 미측정 |
| 거절 사유(V<8 / 대비 / 표준편차) | 미측정 | 미측정 |
| 큐브·빔·바닥 색 검출 성공률 | 미측정 | 미측정 |
| PF 오차·σ | 미측정 | 미측정 |
| 케이스 성공(정렬 / 파지+들기 / 운반 L0 / 내려놓기) | 미측정 | 미측정 |
| SIM 시간당 wall, CPU 초, instruction (S1, S2 / N1, N2) | 미측정 | 미측정 |

속도는 부수 지표다. sim-speed 기록(같은 그림자 설정, M1 러너, 부하 3–5)에서는 robot_cam 렌더가 CPU의 약 28 %, 그중 그림자가 약 75 %였고 그림자를 끄면 렌더 −74 %로 측정됐다. 이 pair probe에서 재현되는지는 미측정이다.

## 한계

- 그림자·반사 유무는 관측 분포를 바꾼다. 기준선과 별도 조건이며, 이 A/B의 성공률을 기존 b-v6c/b-v6d 성공률에 이어 붙이지 않는다.
- 실물에 더 가까워지는지는 검증하지 않았다. 실물 방은 그림자가 있으되 부드럽다는 가정이 남아 있고(측정 없음), `noshadow_v1`이 실물 영상 분포에 더 가깝다는 근거는 없다. sim2real(#213/#214) 영향은 별도 실물 영상 비교로 검증한다.
- 정적 프레임에서 조명 분포 자체가 바뀌었다(핫스팟 소멸). "그림자만 제거"가 아니므로, 더 세분화가 필요하면 그림자만/반사만 arm(`castshadow` 끄기와 `reflectance` 0을 분리한 프로필)을 새 이름으로 추가해야 한다.
- 이 프로필은 시뮬레이터 카메라 렌더(top·로봇·관찰)에 모두 적용된다. 공용 top RGB 입력도 함께 바뀐다.
- 물리 probe·실물 검증 없음. 위 A/B 전에는 어떤 성공률도 주장하지 않는다.

## 사용자가 정할 것

1. 이 A/B를 b-v6e 측정이 끝난 뒤 실제로 돌릴지, 그리고 그 시점의 정책(`b-v6d` 또는 병합된 `b-v6e`).
2. 그림자만/반사만을 분리한 arm을 더 넣을지(정적 관찰에서 그림자 효과가 대부분이었다).
3. 실물 방의 조명 실측(`softshadow_v1`의 근거)을 sim2real 실측 항목(#213/#214)에 추가할지.
4. 채택 시 번들·workflow ID 배정(#218에서, v81/2.14.0 이후 번호).

## 참고 자료

- 저장소 측정·구현(재사용): `experiments/2026-09-26-sim-speed/README.md`(그림자 광원 4개·shadowsize 4096·MSAA 4, 그림자 끄기 300,548 px 변경, 반사 끄기 18,996 px 변경, robot_cam 렌더 CPU 비중), `docs/sim_speed.md`, `docs/local_simulation.md`(표준 관찰 창의 그림자·반사 생략), `scripts/dispatch_native_view.py`(관찰 창 `mjRND_SHADOW`/`mjRND_REFLECTION`), `scripts/eval_zone_own_perception_v3_1.py`(`LIGHTING` 조명 스트레스 프로필: 빌드된 모델의 광원 배열을 고치는 선행 방식), `harness/zone_pair_vision.py`(`valid_frame`), `experiments/2026-09-29-pair-v6c-carry/README.md`(내려놓기 목적지 `OWN_IMAGE_INVALID` 0/13), `experiments/2026-09-26-zone-m2-pair/README.md`·`experiments/2026-09-26-zone-eval-topcam/README.md`·`docs/report/04-executor.md`(조명·그림자로 인한 인식 실패 사례).
- MuJoCo 3.12 문서: XML reference의 `light`의 `castshadow`(그림자를 만드는 광원마다 렌더 패스가 하나 더 든다는 설명)와 `material`의 `reflectance`, `mjtRndFlag`(`mjRND_SHADOW`, `mjRND_REFLECTION`). 이번 세션에서 웹 문서를 다시 열지는 않았고, 설치본 MuJoCo 3.12.0에서 두 속성의 효과를 컴파일된 모델과 렌더 프레임으로 직접 확인했다(위 테스트·정적 관찰).
- 도메인 무작위화(조명·질감 변형)가 sim2real 완화책이라는 선행 근거는 `docs/design/2026-09-26-vision-localization-tagfree.md`(Tobin 등 2017 인용)와 `docs/research_todo.md`에 있다. 이 프로필은 무작위화가 아니라 고정 조건의 변경이다.
- 만들지 않은 것: 약한 그림자 프로필(근거 부재), 새 렌더러·후처리, 러너별 별도 플래그(사전등록 소스 보존).
