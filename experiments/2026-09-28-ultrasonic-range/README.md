# 2026-09-28 자기 초음파 거리 입력: 센서 모델 v1, provider, 운반 높이 (#221)

**구현·오프라인 검증만 했다. 물리 실행·시뮬레이션 실행·모델 호출은 0회이며 연구 결과가 아니다.**

## 결정과 범위

- 2026-09-28 사용자 결정(#221 최신 코멘트)에 따라 로봇 입력에 MasterPi 차체 전면 초음파 거리를 더했다. 네 통신 조건 모두 같게 제공한다.
- 이번에 한 일: 실물 사양 조사, SIM 거리 센서 모델, 제어기용 provider와 이력 기록, 정적 지도 예상 거리·일관성·우도 헬퍼, 문서, 테스트.
- 후속(같은 날, coordinator 요청): 쥔 물체를 ray에서 제외하던 규칙을 정정했다(제외하지 않는다). 짐을 원뿔 위로 드는 운반 높이도 운동학으로 분석했다(아래 "운반 높이").
- 이번 범위가 아닌 일: PF·guard·align 연결. 공동 운반 v6(#246)에서 이어받는다. 연결 제안은 [센서 문서 7절](../../docs/ultrasonic_range_sensor.md#7-공동-운반-v6246-연결-제안-이번-범위-아님)에 있다.
- 기존 등록 실험·번들: 동작 변경 없음. 새 모듈은 기존 코드가 import하지 않고, 기본값은 OFF다.

## 소스·환경

- 브랜치 `claude/ultrasonic-range`, base `origin/main` `6e44c5e7`. 구현 커밋은 이 README가 들어간 커밋이다(PR 참조).
- Mac arm64(Darwin 27.2.0), `.venv-sim`: Python 3.12.13, numpy 2.5.2, MuJoCo 3.12.0, pytest 9.1.1.
- 센서 모델 `masterpi_ultrasonic_v1`의 spec sha256은 `harness.ultrasonic_model.spec_record()`로 확인한다. provider source는 `own_ultrasonic_v1:<해시 8자리>`다.
- 동기 테스트만 실행했고 시간 측정 실험은 없다. 실행 시 부하 평균은 12.35(1분)였다.

## 확인한 사양(요약)

| 항목 | 상태 |
|---|---|
| 2–400 cm, 15°, 40 kHz, I2C 0x77 | 확인(Hiwonder 제품 사양) |
| `Sonar.getDistance()`: mm 정수, 5000 clamp, 실패 시 99999 | 확인(Hiwonder SDK) |
| 15°가 반각인지 전체각인지 | 미확인 → 반각으로 가정 |
| 정확도·갱신 주기 | 미확인 → HC-SR04 값(3 mm, 60 ms)으로 가정 |
| 장착 x 78 mm·높이 54 mm·수평 | 미확인(사진 기반 SIM 명목값) |

출처와 전체 표는 [센서 문서 1절](../../docs/ultrasonic_range_sensor.md)에 있다.

## 검증

명령: `OMP_NUM_THREADS=2 .venv-sim/bin/python -m pytest -q -p no:cacheprovider --basetemp=./.pytest_tmp -rf ...`. 모든 실행은 `mj_step*`를 실패 스텁으로 바꾼 가드 아래에서 돌렸다. 새 테스트 파일은 자체 가드를 쓰고, 기존 테스트에는 scratchpad plugin을 붙였다.

| 묶음 | 결과 |
|---|---|
| `tests/test_ultrasonic_range.py`(22개), `tests/test_ultrasonic_carry.py`(7개), 둘 다 CI 목록 등록 | 29 passed |
| `test_rgb_execution_bundle`, `test_zone_study_source_pinning`, `test_zone_study_contract`, `test_zone_study_inputs`, `test_zone_pair_{admission,status,executor,dev}`, `test_zone_study_integration_pair` | passed, 0 failed |
| `test_zone_pair_review{,2..7}`, `test_zone_study_integration`, `test_zone_study_integration_seams` | passed, 0 failed |
| 제외: `test_sim_real_shared_source`(13개), `test_masterpi_physical_geometry`(17개) | world를 만들 때 physics step이 필요해 가드가 막았다(실패 원인 100 %가 가드). 이번 변경은 이 테스트들이 읽는 파일을 바꾸지 않았다 |

1차 커밋 `b7851aaf` 직전 통합 실행(20개 파일): 656 passed, 0 failed. 후속 커밋 직전 통합 실행(신규 2개 + 위 두 묶음 + `test_vision_pose_source`, 21개 파일): **663 passed, 0 failed, 가드 step 시도 0회**(370 s, 부하 평균 40.8). MuJoCo 없는 CI 환경을 흉내 내면 신규 두 파일은 22 passed, 7 skipped다.

새 테스트가 확인하는 것:

- **기하:** 벽 정면(지도 예측과 SIM 차이 < 4 mm, 벽 태그 두께), 10°·30° 비스듬한 벽, 40°에서 에코 없음, 4 m 너머 벽 없음, 2 cm 미만 invalid, 바닥 단독 grazing 무반사.
- **막대(실제 `zone_wide_door_tags_v2` + `long_beam` 장면):**
  - 바닥 막대는 틈 5·7 cm에서 안 보이고, 10–100 cm에서 보이며, 150 cm에서 안 보인다(ray 해상도).
  - 파지 자세에서는 막대가 아니라 상대 로봇이 보인다.
  - M2 운반 높이(몸체 z 0.061 m)로 든 막대는 끝면 47 mm가 첫 에코다. 쥔 물체를 숨기는 API는 없다(시그니처 검사).
- **상대 로봇 감지:** 마주 본 r2(팔 포함)가 첫 에코가 된다. crosstalk OFF에서는 편차 < 5 cm이고, ON에서는 400회 중 5–60회(실측 16회)가 짧거나 invalid였다. 상대가 90° 돌면 간섭은 0이다.
- **자기 팔 제외:** 팔을 내려 집게가 원뿔을 가리는 자세를 만들었다. 제외하지 않은 raw ray는 `r1__` geom에 맞고, 센서 판독은 벽 거리를 낸다.
- **결정성:** 같은 seed는 같은 판독, 다른 seed와 다른 로봇은 다른 판독을 낸다. 잡음 평균과 σ를 확인하고, 1 mm 양자화를 확인한다.
- **provider:** 시각·나이·출처·σ, `stale`·`invalid`·`no_reading` 제한, 미래 판독 미사용, 시간 역행 거부를 확인한다.
- **이력 JSONL:** 행은 `t, range_m, valid`만 담고, 덮어쓰기는 거부한다.
- **입력 경계:** 주 4조건의 설정이 같다. harness 모듈 3개는 `sim`·`mujoco`를 import하지 않는다.
- **운반 높이:** 필요 높이 공식·장착 민감도, 보정 IK 도달(최대 0.161 m), 권장값 0.110 m, M2·권장 높이 lift IK, 운반 초음파 판정(두 모드·debounce), kinematics 장면 확인을 검사한다. kinematics 장면에서는 M2 높이에서 자기 짐, 권장 높이에서 상대 로봇이 첫 에코다. 관절 범위, grip site, 막대 여유 > 2 cm, tip 여유, 카메라 대리 IoU도 함께 확인한다.
- **번들 불변:** 새 파일 6개가 rgb 번들 source closure와 zone study 실행 번들 `runtime_files_sha256`에 없다.

## 남은 위험

- 실물 장착·정확도·주기·블라인드 존·무반사 반환값은 측정하지 않았다(보정 계획은 문서 6절).
- `near_face` 권장 높이는 막대 아랫면의 grazing 무반사 가정에 기댄다. 아랫면 모서리 회절 에코는 실물에서 확인하지 않았다.
- 권장 높이에서 tool pitch가 grasp 대비 12.1° 바뀐다(M2 8.0°). 턱 안에서 막대가 도는 마찰 여유는 물리로 확인하지 않았다. 카메라 IoU는 pinhole 대리값이다.
- 2.5° ray 간격이라 약 1.2 m 너머의 작은 띠를 놓친다.
- 간섭 모델(기본 OFF)과 우도 가중치는 적합하지 않은 시작값이다.

## 운반 높이 (2026-09-28 후속)

사용자 요청은 짐을 초음파 원뿔 위로 들어 운반 중에도 앞을 보는 것이다. 운동학만으로 분석했다. 분석기는 `scripts/analyze_ultrasonic_carry_height.py`다(`mj_step*` 금지, `mj_forward`·`mj_multiRay`·`mj_geomDistance`만 사용). 결과는 `carry_height_analysis.json`(sha256 `147ba671…58bb`, scene XML sha256 `3486ce92…`)이다. 해석과 표는 [센서 문서 8절](../../docs/ultrasonic_range_sensor.md#8-운반-높이-짐을-초음파-원뿔-위로-들-수-있는가-2026-09-28-221246)에 있다.

- **막대 전체를 원뿔 밖으로 드는 것(`whole_beam`)은 불가능하다.** 필요한 명령 grip z는 반각 15°에서 0.287 m, 7.5°에서 0.199 m다. 보정 IK의 최대 도달은 0.161 m(pitch −40°)이고, pitch를 0°까지 풀어도 0.239 m다.
- **권장: `near_face`, 명령 grip z 0.110 m(`recommended_carry_tool_z()`).** 가까운 끝면을 원뿔 밖으로 두고, 아랫면은 grazing 입사로 에코가 없다. kinematics 장면에서 첫 에코는 상대 로봇(0.694 m)이다. M2 높이 0.095 m에서는 자기 막대 끝면(0.048 m)이 첫 에코다.
- **나머지 확인:**
  - IK pitch −60.0°(grasp 대비 +12.1°, M2 +8.0°). SIM 관절 범위 OK, grip site와 FK 일치.
  - 막대–wrist 최소 거리 31 mm. 전방 tip 가속도 4.0 m/s², 측방 7.9 m/s².
  - 손목 카메라 대리 IoU 0.83(M2 0.86).
  - 장착 44–64 mm / 68–88 mm에서 권장값은 0.095–0.120 m다.
- **운반 규칙:** `CarrySonarMonitor('above_cone')`를 쓴다. 판정은 `formation_ok` / `load_in_cone`(≤ 12 cm, 짐 처짐·미끄러짐) / `intrusion` / `beyond_baseline`이고, 3회 연속일 때만 낸다. 짐 확인만 원하면 현재 높이에서 `load_in_cone` 모드를 쓴다(기준 ≈ 0.048 m, 길게 뛰면 `load_lost`). 두 모드는 동시에 쓸 수 없다. facing-pair에서는 센서가 서로를 향하므로 대형 밖의 진행 방향 장애물은 볼 수 없다.

## 혼자 운반하는 작은 짐 (2026-09-28 후속 2)

질문: 혼자 드는 작은 짐(box·can·tile)을 원뿔 밖으로 들어 앞을 볼 수 있는가. 방법은 위와 같다(`--solo-out`). 결과는 `solo_carry_height_analysis.json`이고, 해석은 [센서 문서 9절](../../docs/ultrasonic_range_sensor.md#9-혼자-운반하는-작은-짐-2026-09-28-221)에 있다. 값은 v2 기하 기준이다.

- **기존 lift hover 0.095 m:** 세 종류 모두 원뿔 안이다(여유 −24/−25/−12 mm). box·can은 자기 짐이 첫 에코다(0.060/0.058 m).
- **직선 lift 최소:** 15°에서 box·can 0.120 m, tile 0.110 m다. 7.5°에서는 0.110/0.110/0.095 m다. 남는 여유는 1–3 mm로 얇다.
- **권장: 기존 운반 자세 `carry_p30`(grip z 0.180, pitch −30°)를 그대로 쓴다.** 여유는 63–77 mm이고, 강체 기울기 42°/36°와 기록된 32°에서도 원뿔 밖이다. 첫 에코는 벽 0.495 m로 정적 지도 0.497 m와 맞는다. 코드 변경은 필요 없다.
- **자기 팔·집게:** 자기 geom을 포함한 ray cast(실물 조건)에서 세 자세 모두 자기 geom이 하나도 맞지 않았다.
- **나머지 확인:**
  - 전방 전복 비는 9.4 이상이다.
  - 손목 카메라가 보는 바닥은 0.18–0.32 m에서 0.32–3.80 m로 넓어진다.
  - 내려놓기(운반 자세 → hover → 16단계 하강)에서 짐 최저점은 68 mm 이상이고, 하강 IK는 모든 단계에서 풀린다.
- **전진 규칙:** `solo_forward_state`를 쓴다. 정지 거리는 짐 앞끝 0.092 + 0.057 + 0.02 ≈ 0.169 m, 감속 거리는 ≈ 0.30 m다. 정적 지도 일치 결과를 함께 돌려준다. 이 규칙은 기존 충돌 guard에 더해지는 입력이다.

## 공동 운반 ㄱ자 측면 파지 (2026-09-28 후속 3)

9/9 사용자 요청으로 만든 측면 파지 자세를 v6 장면에 다시 놓았다(`--side-out`). 결과는 `side_grasp_pair_analysis.json`이고, 해석은 [센서 문서 10절](../../docs/ultrasonic_range_sensor.md#10-공동-운반-ㄱ자-측면-파지로-앞-보기-2026-09-28-221246)에 있다. 원 기록은 [`2026-09-09-side-grasp`](../2026-09-09-side-grasp/README.md), [`2026-09-09-loaded-transport`](../2026-09-09-loaded-transport/README.md), `scripts/probe_dual_grasp_sync.py --side-grasp`(commit `9bb41317`)다. 막대 축 방향으로 바뀐 것은 commit `87eaac86`(9/25 카탈로그)부터다.

| 구간 | 몸체 방향 | 팔 yaw | 초음파 용도 |
|---|---|---|---|
| 횡 이동(막대에 수직) | 두 로봇 모두 진행 방향 | ∓90°(PWM 500/2500) | 전방 장애물 거리 vs 지도(2.546/2.547 m 일치) + 기존 충돌 여유 |
| 축 이동·문 통과 | 그대로(strafe) | ∓90° | 앞은 못 봄. 옆 문기둥 거리 vs 지도(0.172 m 일치)로 문 중앙 정렬 확인 |
| 현재 M2·v6 | 마주 봄 | 0° | 서로를 봄(0.694 m), 대형 감시만 |

- **축 이동에서 앞 보기는 불가능하다.** 팔 yaw 180°가 필요한데 한계는 ±100.3°다. 최선도 진행 방향에서 79.7° 벗어난다.
- **문 폭:** 대형 폭은 0.1885 m(현재 0.162 m)다. 0.5 m 문의 한쪽 여유는 0.156 m(현재 0.169 m)다.
- **yaw servo:** 짐 무게의 정적 토크는 0이다. 막대에 수직인 힘에는 0.155 m 팔이 걸린다. SIM 한계 1.2 N·m(7.7 N)이고, 실물은 LD-1501MG 17 kg·cm로 가정했다(미확인). 대형 어긋남이 위험하지만, 팔이 늘 막대 축을 따르므로 이 위험은 방식과 무관하다.
- **전복·카메라:**
  - 측방 전복 비 4.6, tip 가속도 4.65 m/s²다. 현재 방식의 전방 값은 3.9, 3.98 m/s²다.
  - 손목 카메라의 막대 이미지는 현재 방식과 같다(IoU 1.0). 다만 ±90°는 보정된 pan 범위(1300–1700) 밖이다.
- **odometry:** 측면 방식에서는 0.60 m 축 이동이 strafe가 된다. 현재 보정값(lateral 0.697)은 현재 방식에서 잰 값이라 측면 방식에는 새 보정이 필요하다.
- **근거 범위:** 9/9 결과는 다른 물체, 정답 좌표 바퀴 제어, 50 cm 전진뿐이다. `long_beam`·strafe·자기 카메라 실행은 검증되지 않았다.
- **권장:** v6 비교 조건 후보로 둔다. 채택 전에 물리 파지·strafe 운반, odometry 재보정, ±90° 카메라 보정을 확인한다.

## 리모델 v3 기하 (2026-09-28 후속 4, 초안 PR #249)

v3 값은 센서 88.0/61.7 mm, 팔 축 +48.2 mm다(도면 기반, 측정 아님). 이 값으로 해석식을 다시 계산했다(`--geometry-out`, `geometry_v2_v3_analysis.json`, [센서 문서 11절](../../docs/ultrasonic_range_sensor.md#11-리모델-v3초안-pr-249-기하에서-다시-계산-2026-09-28)).

- **공동 운반 `near_face`:** 0.110 → **0.125 m**, pitch 변화 +12.1 → +18.1°.
- **solo 직선 lift 최소:** box·can 0.120 → **0.140 m**, tile 0.110 → **0.125 m**. `carry_p30`는 여전히 원뿔 밖이다(여유 45–56 mm). 정지 거리는 ≈ 0.207 m다.
- **자기 팔·집게:** 원뿔 축에서 최소 25.6° 떨어져 있어 원뿔 밖이다. 측면 파지에서는 팔·막대가 센서 면 뒤에 있다.
- **방향 전환:** 팔 축이 앞에 있으므로 몸체 중심으로 90° 돌면 grip이 68 mm 움직인다. 팔 축을 중심으로 돌아야 한다(mecanum으로 원리상 가능, 미검증).
- **링크 민감도:** 위팔 57.7 mm, 집게 94 mm(도면 값)를 넣으면 최대 grip z는 0.161 → 0.151 m다. 권장 높이는 모두 도달 범위 안이다. 집게 94 mm에서는 tile의 7 mm grip이 IK로 풀리지 않는다.

## 원본

raw 출력은 없다(물리 실행 0회). 분석 JSON은 이 폴더에 커밋했다. 재현 명령: `OMP_NUM_THREADS=2 .venv-sim/bin/python scripts/analyze_ultrasonic_carry_height.py --out carry_height_analysis.json --solo-out solo_carry_height_analysis.json --side-out side_grasp_pair_analysis.json --geometry-out geometry_v2_v3_analysis.json`

| 파일 | sha256 |
|---|---|
| `carry_height_analysis.json` | `147ba67117122dc3793d010726d2a5e8bd344dbcbd7a8d9a3a41f63a131458bb` |
| `solo_carry_height_analysis.json` | `e906de961473078a17680429ba9c12776f4c3b1aabed088e344ecec4adc704b2` |
| `side_grasp_pair_analysis.json` | `3ac92dec110cf7e7d52410e6ccbb44a9acb0912ed8d02696418d36a0a63a9ede` |
| `geometry_v2_v3_analysis.json` | `3d9cf884568b6def01970a815b5b8200e21b14c167ef7a291191ac28b05b568f` |

테스트 로그는 PR 검증 절에 요약했다.
