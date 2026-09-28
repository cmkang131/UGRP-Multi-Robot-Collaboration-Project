# 2026-09-28 자기 초음파 거리 입력: 센서 모델 v1과 provider (#221)

**구현·오프라인 검증만 했다. 물리 실행·시뮬레이션 실행·모델 호출은 0회이며 연구 결과가 아니다.**

## 결정과 범위

- 2026-09-28 사용자 결정(#221 최신 코멘트)에 따라 로봇 입력에 MasterPi 차체 전면 초음파 거리를 더했다. 네 통신 조건 모두 같게 제공한다.
- 이번에 한 일: 실물 사양 조사, SIM 거리 센서 모델, 제어기용 provider와 이력 기록, 정적 지도 예상 거리·일관성·우도 헬퍼, 문서, 테스트.
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
| `tests/test_ultrasonic_range.py`(신규 22개, CI 목록 등록) | 22 passed |
| `test_rgb_execution_bundle`, `test_zone_study_source_pinning`, `test_zone_study_contract`, `test_zone_study_inputs`, `test_zone_pair_{admission,status,executor,dev}`, `test_zone_study_integration_pair` | passed, 0 failed |
| `test_zone_pair_review{,2..7}`, `test_zone_study_integration`, `test_zone_study_integration_seams` | passed, 0 failed |
| 제외: `test_sim_real_shared_source`(13개), `test_masterpi_physical_geometry`(17개) | world를 만들 때 physics step이 필요해 가드가 막았다(실패 원인 100 %가 가드). 이번 변경은 이 테스트들이 읽는 파일을 바꾸지 않았다 |

최종 커밋 직전 통합 실행(신규 22개 + 위 두 묶음 + `test_vision_pose_source`, 20개 파일): **656 passed, 0 failed, 가드 step 시도 0회**(210 s). MuJoCo 없는 CI 환경을 흉내 낸 실행에서는 신규 파일이 15 passed, 6 skipped였다(ray 테스트는 skip).

새 테스트가 확인하는 것:

- **기하:** 벽 정면(지도 예측과 SIM 차이 < 4 mm, 벽 태그 두께), 10°·30° 비스듬한 벽, 40°에서 에코 없음, 4 m 너머 벽 없음, 2 cm 미만 invalid, 바닥 단독 grazing 무반사.
- **막대(실제 `zone_wide_door_tags_v2` + `long_beam` 장면):**
  - 바닥 막대는 틈 5·7 cm에서 안 보이고, 10–100 cm에서 보이며, 150 cm에서 안 보인다(ray 해상도).
  - 파지 자세에서는 막대가 아니라 상대 로봇이 보인다.
  - M2 운반 높이(몸체 z 0.061 m)로 든 막대는 제외하지 않으면 끝면 47 mm가 보이고, 제외하면 상대 로봇이 보인다.
- **상대 로봇 감지:** 마주 본 r2(팔 포함)가 첫 에코가 된다. crosstalk OFF에서는 편차 < 5 cm이고, ON에서는 400회 중 5–60회(실측 16회)가 짧거나 invalid였다. 상대가 90° 돌면 간섭은 0이다.
- **자기 팔 제외:** 팔을 내려 집게가 원뿔을 가리는 자세를 만들었다. 제외하지 않은 raw ray는 `r1__` geom에 맞고, 센서 판독은 벽 거리를 낸다.
- **결정성:** 같은 seed는 같은 판독, 다른 seed와 다른 로봇은 다른 판독을 낸다. 잡음 평균과 σ를 확인하고, 1 mm 양자화를 확인한다.
- **provider:** 시각·나이·출처·σ, `stale`·`invalid`·`no_reading` 제한, 미래 판독 미사용, 시간 역행 거부를 확인한다.
- **이력 JSONL:** 행은 `t, range_m, valid`만 담고, 덮어쓰기는 거부한다.
- **입력 경계:** 주 4조건의 설정이 같다. harness 모듈 3개는 `sim`·`mujoco`를 import하지 않는다.
- **번들 불변:** 새 파일 4개가 rgb 번들 source closure와 zone study 실행 번들 `runtime_files_sha256`에 없다.

## 남은 위험

- 실물 장착·정확도·주기·블라인드 존·무반사 반환값은 측정하지 않았다(보정 계획은 문서 6절).
- 쥔 물체 제외는 SIM 규칙이다. 실물에서는 들어 올린 막대가 원뿔 안에 들어온다. v6는 적재 중 판독을 `unknown`으로 두는 것을 권한다.
- 2.5° ray 간격이라 약 1.2 m 너머의 작은 띠를 놓친다.
- 간섭 모델(기본 OFF)과 우도 가중치는 적합하지 않은 시작값이다.

## 원본

raw 출력은 없다(물리 실행 0회). 테스트 로그는 PR 검증 절에 요약했다.
