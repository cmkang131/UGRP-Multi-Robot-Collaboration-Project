# 새 실행의 heading 기본값 · v145 (2026-10-09)

사용자 heading3 결정 “heading을 기본으로 해주라”에 따라 새 공통 주행은 `heading_mode=path_tangent_v1`을 기본으로 쓴다. 완료된 v143 코호트는 `b60acdca` 그대로 3/3 종료·보고했고 이후에만 변경했다. PR #406/#420을 포함한 main `1ba3668b`를 merge하여 CI 목록 충돌을 해결했다(`d9b2a39e`, 관련 47 PASS 후 push). PR #419는 main 기준 DRAFT다.

## 사용 및 공통 적용점

새 S2 실행 진입점은 표준 관리의 `zone-path-heading-v145`(실행 번들 `zone-s2-realism-v145`, workflow 7.38.0)다. [예약](reservation.json)은 main과 열린 PR 전체의 최대 v144/7.37.0 확인 기록이다.

```sh
# 기본 on; --execute를 생략하면 계획만 출력한다.
python3 scripts/sim_cli.py run zone-path-heading-v145 -- \
  --expected-source-sha <committed-sha> --seed 1066 --output <new-primary-output>
# 같은 새 번들의 옆걸음 비교: --heading-mode off
# 1068 원인 수정안 비교: --heading-visual-lock unique_cyan_align_v1
```

기본값은 `harness/path_heading_policy.py:DEFAULT` 한 곳이다. 명령은 `zone_solo_cyan_path_heading.select_waypoint` → `select`에서 생성한다. 제자리 회전 뒤 전진, 최종 목표 0.10m 안에서만 측방 미세 정렬한다. 중간 waypoint 0.10m 접근은 옆걸음을 허용하지 않는다. 기존 측정된 turn ±0.35/0.10초와 coast·지연 관측 대기, 운반 turn 한도 및 별도 능동 관측 ±90° 제한을 유지한다. 연속 각가속도 수치를 새로 검증했다고 주장하지 않는다.

| 경로 | 기본 on 연결 지점 | 기록/검증 범위 |
|---|---|---|
| S2 새 v145 | `run_path_heading` → `run_s2_graduation59.runtime_factory` → 공통 `run_s2_unknown_start.runtime_factory` | bundle의 옵션/최상위 heading, result의 heading, student 결정 기록; 실제 factory·명령 시험 |
| S3 no-prior / s3-host v144 후속 | `zone_s3_no_prior.solo_factory`가 동일 factory에 `controller_config.options` 전달 | PR #416 소스의 실제 factory에 heading on·기존 회전 가드가 함께 붙는 오프라인 통합 확인. 실행은 S3 담당 브랜치에서 최종 SHA를 merge한 뒤 수행 |
| S4 | `s4_llm_host.S3Link` → 위 S3 RobotLink → 동일 r3 주행 제어기 | S4는 별도 운동 제어기를 만들지 않는다. S3 링크의 설정을 계승하며 S4 자체 live launcher/새 물리 성공 증거는 없음 |
| 자기 지도 이동 | `own_map_heading.command(plan, own_pose, profiles, robot_id=...)` → 같은 `select_waypoint` | PR #409의 `coordinate_frame/status/path_m/heading_rad` 계획 형식 어댑터 기본 on, 다른 로봇 좌표계 거부. off는 기존 명령 객체 그대로 반환. 자기 지도 PR은 아직 오프라인 계획·위치 추정 단계이며 host 연결/물리 이동 인수는 후속 작업 |

위 공통 계층의 대상은 단독 운반/경로 주행이다. S3 r1/r2의 공동 빔 자세·GO 합의는 별도의 공동 제어기이며 각 로봇을 독립 회전시키지 않는다. `ownmap_s2`의 기존 `OWNMAP_S2_OFFLINE_LOCALIZATION_ONLY` 차단을 유지한다. 자기 지도 어댑터가 실제 호스트에 붙을 때는 기존 pulse/coast/새 추정 대기 및 회전 footprint 검사를 호스트가 유지해야 한다.

새 bundle은 on/off를 명시한다. 공통 `run_final_environment_checks.write`는 그 bundle에서 result의 `heading_mode`, `heading_visual_lock`을 기록하므로 S3 HOST_ERROR도 누락하지 않는다. 기존 v141/v143 실행기와 과거 번들의 옵션 누락은 동결된 off 의미를 유지한다. `--heading-mode off`의 제어 명령/초기 student record/RNG는 기존과 바이트 동일하며 **새 v145 bundle/result에는 사용 모드·버전 메타데이터가 있으므로 과거 파일과 같다고 주장하지 않는다**. 과거 bundle 전체 재현은 역사적 v141 실행기 또는 `zone_s2_heading_contract.bundle(..., heading_mode='off')` 경로를 쓴다.

## 완료 코호트 (새 기본값 변경 전 고정 소스)

수치는 baseline v141 `99d81d8c` → heading v143 `b60acdca`, 같은 seed다. SIM은 reset 포함 종료 시각이며 1068/1065의 본 실행 한도는 900초다. 방향 비율은 실제 병진 속도≥0.01m/s에서 차체와 진행 방향 차이≤20°의 시간 비율, 옆걸음은 ∫|측방 속도|dt/∫속력dt다.

| seed | 성공 | SIM초 | 방향≤20° | 측방 속도 비율 | 벽/로봇 접촉 표본초(전→후) |
|---|---|---|---|---|---|
|1066|성공→성공|285.75→423.95|60.40→90.73%|63.56→6.52%|벽0→0 / 로봇0.40→0|
|1068|실패→실패|296.00→901.30|65.94→85.33%|47.13→5.74%|벽50.40→0 / 로봇0→0|
|1065|실패→실패|901.30→901.30|48.18→76.10%|15.08→7.98%|벽1.25→0 / 로봇16.50→0|

분모는 3, 성공은 양쪽 1/3. 1068 실패를 제외하지 않았다. 1066의 SIM은 48.36% 늘어 성능 동등 판정은 보류하지만 기본 on은 사용자 결정으로 적용한다. 문 중심 통과는 양쪽1066만, 새 접촉 표본은 모두0. 표본 사이 무접촉 보장은 아니다. 1066 운반 상자 절대 yaw 범위57.73→179.09°, 로봇 대비 상대 yaw 범위0.331→0.252°; 나머지 두 seed는 운반 없음. [원 비교 기록](../comparison.json), [4배속 영상](http://127.0.0.1:6007/video/63dceac77fc57ed37436), [물리 결과 TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1009-s2-heading-dev%2F&smoothing=0#timeseries).

## 1068은 왜 탐색 실패했나

저장된 자기 RGB·명령된 카메라 자세·당시 자기 추정치를 현재와 동일한 검출기로 재생했다. 평가용 실제 위치는 별도 [사후 위치 오차](s1068-pose-evaluation.json)에서만 읽었다. [검출 재생](s1068-detections.json)은 원 프레임 해시·검출/슬롯 판정·마스크 범위를 보존한다.

| 관찰 | 옆걸음 baseline v141 | heading v143 | 판단 |
|---|---|---|---|
| 최초 탐색→정렬 | 63.25초, cyan 고유 검출 | 147.0초, cyan 고유 검출 | heading도 처음에는 찾았다. “계속 미발견”은 아님 |
| 처음 정렬의 자기 영상 | cyan bbox x182–207, y143–166 | x571–591, y144–164(147.1초) | 경로·시야가 달라졌다. 초기 평가 yaw 오차1.66°→−31.30° |
| 비슷한 접근 거리의 검출 | 85초, 거리0.489m, bbox x241–303/y318–385, 1개·슬롯 통과 | 187.9초, 거리0.475m, bbox x284–347/y328–396, 1개·슬롯 탈락 | 상자가 화면 중앙에 남아 있다. 단순 회전 FOV 이탈 가설은 이 프레임에서 반증 |
| 당시 자기 pose 오차(평가만) | XY0.150m, yaw0.68° | XY0.559m, yaw−39.17° | heading 경로에서 추정 오차가 커짐. 회전 모델/영상 갱신의 각각 기여도는 미분리 |
| 실제 탈락 조건 | 추정 cyan y=−0.734m | y=−1.655701m < 슬롯 하한−1.650m | 마지막 ±turn 직후 원래 지도 슬롯 필터가 보이는 상자를 제거(5.701mm 경계 초과) |
| 후속 | 96.65초 집기,122.75초 운반 후 문 실패 | 191.6초 `CYAN_ALIGN_VIEW_LOST`, 반복 탐색 후900초 상한 | 직접 원인은 검출 실패가 아닌 전역 pose 의존 슬롯 거부. 나중에는 탐색 방향도 실제와 어긋나 재획득 실패 |

heading의 경로/회전은 달라졌고 오류가 나타난 연쇄는 재현된다. 다만 저장 영상만으로 “회전 자체가 필터 오차 전부를 만들었다”는 인과 효과를 분리할 수는 없다. 해당 실패를 직접 제거하는 후보 `heading_visual_lock=unique_cyan_align_v1`을 **기본 off**로 추가했다. 최초 검색의 원래 슬롯 확인은 유지하고, 그 후 align 상태에서는 자기 RGB의 고유 cyan 후보로 시각 서보를 이어간다. 후보0/복수이면 기존 시야 상실 처리로 돌아가며, GT·새 검출 문턱·필터 문턱은 쓰지 않는다. 단일 cyan 조건의 시험적 국소 추적이며 새로운 물리 완주/재획득 성공을 주장하지 않는다. 회전 주행의 장기 위치 추정 오차는 별도 남은 문제다.

## 표준 방법과 출처

- [Nav2 RPP 공식 구현](https://api.nav2.org/nav2-rolling/html/regulated__pure__pursuit__controller_8cpp_source.html), [공식 README](https://github.com/ros-navigation/navigation2/blob/main/nav2_regulated_pure_pursuit_controller/README.md): carrot의 atan2, `use_rotate_to_heading`, 제자리 회전과 각속도/각가속도 제한. 기존 실측 pulse vocabulary로 구현하고 .10m 최종 정렬 경계는 원 계약을 유지한다.
- [Chaumette & Hutchinson, Visual Servo Control I (저자 제공 PDF)](https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/ChaHut06.pdf): 영상 특징 오차로 국소 제어하는 표준 시각 서보와 시야 유지 문제. 제안 옵션은 초기 지도 기반 후보 확인 뒤 국소 영상 추적을 계속하는 적용이며 논문의 전체 제어기를 구현했다는 뜻은 아니다.
- [RPP 논문](https://arxiv.org/abs/2305.20026): 경로 추종 속도 조절의 근거. 이번에는 새로운 연속 속도/가속도 튜닝이나 물리 설정 변경을 하지 않았다.

## 검증 및 보존

[통합/재생](integration.json): PR #416의 실제 `solo_factory` 연결 확인, 기존 저장 명령 **1757/1757 바이트 일치**. 고정 초기 student record149,508bytes의 변경 전 SHA를 확인한 뒤 경로 접두사만 `$ROOT`로 정규화한 휴대용 시험 해시를 남겼다. 실행 당시 원본과 v143 등록은 덮어쓰지 않았다. 이번 변경의 추가 물리 실행0, 새 성공 결과0, GT 제어 입력0이다.

최종 변경 범위 시험은 3개 파일 **46 PASS (57.73s)**. v145 계획 출력은 기본 on/수정안 off 확인. [검증 상세](verification.json). CI를 기다리지 않고 push한다.

[1068 진단 TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1009-heading-diagnosis%2F&smoothing=0&pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Frgb_detections%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fslot_accepted%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fpose_xy_error_m%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fpose_yaw_error_abs_deg%22%7D%5D#timeseries): 새2run·12수치의 원본/이벤트/API 일치,4개 pin·두 run 표시·HParams model_calls 열 재적용 확인. 기존 물리 결과 스냅샷과 영상은 보존했다. [화면](tensorboard-diagnosis.png).
