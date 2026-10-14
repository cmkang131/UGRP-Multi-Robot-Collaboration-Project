# 1대 상자 교사 학습용 시연 기록 준비 — PR #502

기준 HEAD `c35e2ff2f89ca90060432d66023a35e831ff324b`. 새 실행 SHA는 이 문서를 포함한
push 완료 커밋으로 고정하고, 큐 파일명과 각 실행 `source_sha`에 전체 SHA를 넣는다.
코드·기록 준비만 완료한다. 실제 기록·원격 자원 검사·학생 학습·학생 성공 검증은 하지 않았다.

## 선행 근거와 승인 경계

- 사용자 제공 및 로컬 요약: gcp1 n4-highcpu-64, 상자 관문 79700–79739 **40/40**,
  cyan/red/green/yellow 각 10/10, 입력 감사 invisible/held 0/0. 조정자가 원격
  result.json 40개의 physical_success=true를 재확인했다는 사용자 보고다.
  이번 작업에서 원격 원본을 재확인하거나 영상을 열지는 않았다.
- 놓침 진단 79790–79797: 사용자 보고 오탐 0/8. 관문·진단 시드는 기록에 사용하지 않는다.
- 기준 요약: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/solo-gate-c35e2ff2.json`.
  이 기준의 입력 감사 0/0은 아래 코드 누설 점검을 대신하지 않는다.
- **코드 누설 1곳 발견·기록 프로필에서 제거.** 수정된 둘러보기의 동작은 기준과 다르므로
  기존 40/40을 새 교사의 성공률로 승계하지 않는다. 예비 2개는 채택되지 않은 원시 기록이고,
  후속 48개·데이터 채택 전에 수정된 소스의 같은 머신 관문 ≥38/40과 명시적 조정자 승인을 요구한다.

## 행동 입력 코드 전수 점검

정답 위치는 **현재 자기 카메라에 보이는 대상의 상대 위치**를 전달하는 교사 어댑터에서만
행동 입력으로 허용한다(AGENTS.md 근거리 교사 예외). 전체 정답·접촉·측정 관절·평가값은
성공 판정·평가·초기 시드/장면 생성용이다. 상대 좌표로 변환하기 위한 자기 자세를 독립
절대 자기 위치로 전달하는 경로도 확인했다. 점검 파일 전체 해시는 [record-source-audit.json](record-source-audit.json)에 있다.

| 코드 경로 | 입력/정답 용도 | 판정 및 기록 프로필 조치 |
|---|---|---|
| `scripts/run_solo_grasp_act_teacher.py` 기준 278–285 → `SoloLookaround.arm/make_plan` | **실시간 truth_pose + 시드의 handoff_pose_error**로 지도 자기 위치를 만들고 팔·팬·몸체 관측 방향 선택 | **누설 1곳**. `solo_truth_free_lookaround_v1` 기본 OFF, 기록 때 필수 ON. `arm()`은 위치 인자를 거부하고 고정 자기 RGB 스캔만 한다. 현재 코드 304–312. |
| `sim/grasp_act_solo_teacher.py:85` `InputAudit.measure` | 현재 가시 비율 ≥1/3 및 holding=false 뒤에만 lazy 상대 위치/yaw 읽기 | 허용된 visible-target 교사 입력. 불가시·들고 있는 동안 콜백 미호출. xyz/yaw만 허용. |
| 실행기 `read_relative` | 카메라 ray 가시성 확인 후 cargo pose·자기 base를 몸체 상대 xyz/yaw로 변환 | 가시 대상의 상대 위치만 교사에 전달. 독립 자기 정답 좌표·접촉·관절·판정값 전달 없음. |
| 실행기 `refresh_obstacles/route` | 각 물체·로봇·벽의 현재 가시 비율을 통과한 상대 위치·기존 형상 상수 | 허용된 visible-only 장애물 경로. route에는 몸체 목표·가시 장애물만 전달. 숨은 목적 거리로 인계·표본 선택하지 않음. |
| `SoloTeacher._target/_seek/_pick_geometry/step` | 가시 대상 측정, 이전 발행 명령으로 이동한 유한 기억, 스킬·종류·역할, RGB 판정 | live GT·접촉·관절·Score 입력 없음. 마지막 가시 위치로 IK 표적을 고정한 뒤 holding 구간에서 새 위치 판독 차단. |
| `sim/grasp_act_teacher.py:IssuedArm` | 발행 PWM 저장만 | **빔 GraspTeacher.step(기준 246–254)의 접촉·높이 성공 경로 미호출**. 상속도 하지 않음. 빔 GT handoff 미공유. |
| `sim/grasp_act_teacher_v3.py:propagate_owned`, `harness/grasp_act_visible_world.py:command_delta` | 이전 발행 wheel/pulse의 고정 운동학 | 이 함수만 재사용. pair teacher 클래스와 perfect_self_comparison 경로 미호출. |
| `scripts/zone_teacher.py:ArmSequence/plan_path/proportional_drive` | 발행 PWM 보간, 전달받은 상대 목표·가시 장애물 | TeacherRobot(world 접근 클래스) 미사용. 보간 완료는 명령 완료이며 실제 관절 완료가 아님. |
| `harness/visual_arm.py`, `visual_arm_v3.py`, `servo_camera_fk.py` | 고정 SDK/구조 형상 + 발행 PWM + 가시 표적 | qpos/측정 관절/접촉 입력 없음. FK/IK는 명령 공간 예측. |
| `sim/grasp_act_visible_gaze.py`, `grasp_act_gaze.py` | 가시 표적·발행 자세·고정 카메라 형상 | 불가시 때 유한 명령 기억으로 시선만 조절. GT 새로 읽지 않음. |
| `sim/grasp_act_release_teacher.py` | PAD_MID_M/PAD_TOL_M **상수만** | pair release 제어기·정답 인계 미사용. |
| `sim/grasp_act_solo_lookback.py`, `solo_lookback_margin.py` | 집기 전 RGB, 그때의 발행 자세, 후속 명령·RGB | 원래 자리와 후퇴를 FK/명령 이력으로 계산. GT 거리·실제 변위·접촉을 행동 보정에 쓰지 않음. margin은 정적 민감도 상수. |
| `sim/grasp_act_solo_rgb.py` | 자기 RGB·명령(이전 off 경로는 마지막 가시 표적 기억도 사용) | 기록 프로필은 lookback 모드만 허용해 다른 판정 경로에 들어가지 않음. |
| `sim/grasp_act_solo_lookaround.py`, `lookaround_localization.py:ScriptRunner/look_servo` | 기록 때 위치 없이 고정 pan 500/1000/1500/2000/2500/1500, 기존 팔 자세·시한, 자기 RGB | 새 스캔은 pose-free. 지도 prior·측정 위치 추정·몸체 회전 없음. `captured_only`; 위치 추정 성공을 주장하지 않음. 기존 localizer 경로는 기본 OFF 토글의 비교 경로로 보존. |
| `sim/grasp_act_port.py`, `camera_robot_port.py` | 자기 카메라와 발행 wheel/PWM 캐시 | 초기 `_servo_pulses`도 `servo_command_pulses`에서 가져온 명령 캐시. 실제 qpos 읽기 없음. 정상 물리 드라이버는 유지. |
| 실행기 Score·look_truth, `sim/grasp_act_solo_evaluation.py` | 전체 pose·contact force·속도·기울기·성공 | 평가 파일/최종 결과만. 평가 결과가 step·route·종료 시각으로 돌아가지 않음. 종료는 교사 자체 명령/RGB 완료 또는 cap. |
| `scripts/make_solo_teacher_plan.py`, `sim/grasp_act_scene.py` | spawn·장면 배치·가시 시작·충돌 없는 시드 생성 | setup-only. spawn/cargo_pose/handoff_pose_error를 기록 프로필의 행동·학생 입력으로 전달하지 않음. |
| `scripts/run_grasp_act_teacher.py` 공유 import | write/apply/compress_logs만 | 전체 GT snapshot·pair run·handoff 함수 미호출. |
| `harness/grasp_act_solo_recording.py` | 자기 RGB·이전 발행 명령·번호표 → observation, 다음 교사 명령 → 별도 target | whitelist로 GT 혼입 거부. local handoff는 `zone_color_boxes.detect_own/markerless_box`의 **자기 RGB+발행 카메라 FK** 거리 ≤0.8 m만 사용하며 교사 행동을 바꾸지 않음. |

정적 코드 점검 결과는 **발견 1곳, 기록 프로필의 미해결 행동 누설 0곳**이다.
런타임 보안 샌드박스나 새 교사 물리 성공률의 검증으로 확대하지 않는다.

## 기록 프로필과 실제 학생 카메라 비교

`solo_visible_only_v1 + held_object_hidden_v1 + setdown_lookaround_v1 + align_relook_v1 +
pad_window_v2 + solo_lift_lookback_v1 + solo_lift_lookback_margin_v1`은 관문과 같다.
추가: `training_rgb=true`, `solo_truth_free_lookaround_v1=true`; negative probe OFF, weld OFF,
cap 90 SIM초. 둘러보기 누설 제거 외에는 집기·정렬·물리·명령 주기를 바꾸지 않는다.

이 checkout에는 별도 학생 camera YAML이 없다. 실제 학생 설정 파일은
`sim/masterpi_camera_profile.py`(원본 K/D·해상도), `sim/masterpi_camera_review_v3.py` 및
`sim/s2_realism_camera_binding.py`(실제 mount), `harness/grasp_act_contract.py`(학생 주기·이력)다.
기록기는 이 파일을 직접 읽고 경로·sha256을 `student-camera.json`과 계획에 저장한다.
`harness/grasp_act.py`의 standard 224×224/smoke 96×96은 **학습 전처리 해상도**이며 원본 해상도가 아니다.

| 항목 | 실제 학생 설정 | c35e2ff2 관문 코드 | 기록 프로필 |
|---|---|---|---|
| 원본 자기 카메라 | robot_cam, 640×480 | 동일, 제어에 사용 | 동일 JPEG 바이트 전량 보존; 재렌더·축소 없음 |
| RGB/명령 주기 | PERIOD_S=0.1 s, 10 Hz | 0.1 s 제어; 학습 기록 OFF | 0.1 s 촬영·observation·target |
| K pinhole FOV | H=54.535162°, V=42.148949° | 같은 K 및 runtime binding | 같은 K; 실제 runtime intrinsic·해상도도 별도 저장/검사 |
| 원본 fisheye | D=(-0.019981952, -0.170759362, -0.256831820, 0.965093342); 단일 FOV로 표현 불가 | 같은 remap | 동일. 제조사 170°를 fovy로 대체하지 않음 |
| 장착 | camera review v3, local pos=(0.052982010,0,0.028152174) m, 기존 quat | bind_camera 적용 | 동일; runtime pos/quat 검증. 실물 보정 완료 주장은 없음 |
| RGB 이력 | 5.2/1.5/0.5/0 s 전 4장 | 입력 저장 없음 | 동일 time-only 선택; 첫 5.2초는 최초 프레임 반복 bootstrap 표시 |
| 명령 이력 | 최근 16개 발행 wheels/duration/PWM(팬 포함) | 교사 명령 원장만 | 다음 행동 전에 최근 16개 저장; 최초 hold 반복 bootstrap 표시 |

비교는 코드상 설정 비교다. 관문의 원격 runtime 파일이나 새 기록 파일을 이번 작업에서 회수하지 않았다.

기존 destination 번호표는 A/B/C뿐이라 원래 집은 자리에 놓기를 A 등으로 허위 표시할 수 없다.
`pickup_site` 이산 번호표를 추가하고 학생 계약/adapter를 v6으로 올렸다(context 251→252).
기존 v5 가중치·데이터와 암묵적으로 혼용하지 않는다. 새 학생 학습 시 이 계약을 사용해야 한다.

## 저장 분리와 실패 처리

- 학생 입력: `rgb/r1/*.jpg`, `student-r1.jsonl`(v6 whitelist: RGB 참조·이전 명령·스킬·종류·역할·목적 번호표·명령 시계).
- 교사 원시 자료: `teacher-raw/commands.jsonl`(visible_target/RGB 판단 포함), `plan.json/scene.json/scene.xml`(setup-only 전체 배치).
- 학습 표적: `teacher-r1.jsonl`(같은 sample_id/t의 다음 발행 명령, done, 구간/샘플 적격 라벨). 학생 파일에 넣지 않는다.
- 평가: `evaluation/eval-only.jsonl`, `evaluation/camera-runtime.json`, `result.json`. contacts/전체 pose/성공은 이 영역에만 둔다.
- 전체 기간을 저장하고 navigation/approach/grasp/carry/release/inspection 구간을 붙인다.
  이 교사는 집기→유지→원래 자리 재관측을 위한 짧은 후퇴/복귀→같은 자리에 놓기만 한다.
  목적 구역 운반·문 통과 시연으로 표현하지 않는다. 부재 구간을 만들어 넣지 않는다.
- 실패·HOST_ERROR·중단도 입력/표적/평가 원본과 전체 파일 manifest 해시를 보존한다.
  `training_include=false`, `data_admitted=false`; 완료·물리 성공·허용 RGB handoff·승인 조건을
  갖춘 실행만 `training_candidate=true`. 독립 데이터 적합도 검토 뒤 별도 채택한다.
  실패를 done 표적으로 바꾸거나 기록 단계에서 원본을 지우지 않는다.

## 50개 계획과 단계

[solo-record-plan.json](solo-record-plan.json): train **86000–86049**.
로컬 관련 계획·큐 52개에서 충돌 0; [record-seed-check.json](record-seed-check.json).
새 예약은 `configs/grasp_act_seed_splits.json`에 있다. 원격 미사용 여부는 제출 직전 조정자가 확인한다.
관문·진단과 겹치지 않으며 held-out s4를 포함하지 않는다.

50은 4로 나누어떨어지지 않아 가장 균등한 **cyan/red/green/yellow=13/13/12/12**다.
예비 cyan/red 1개씩(86000/86001), 후속 48개는 각 12개다.

1. 예비 **2개** 원시 기록. source/host/크레딧/저장 예산/미사용 시드 점검 후 운영자가 활성화한다.
   첫 30 SIM초에 `python -m scripts.check_solo_recording <RAW> --out <CHECK.json>` 실행:
   파일 bytes·sha256, tick당 유일 프레임, 640×480 RGB, 0.1 s 간격,
   실제 K/mount, 4장 시각 이력, 이전 16개 명령과 다음 target의 정렬을 모두 검사한다.
   처음·중간·끝 최소 6장과 실제 변위/명령 변위, 별도 물리 결과도 조정자가 확인한다.
2. **조정자 명시 승인**. 수정된 소스 관문 ≥38/40, 같은 execution_host,
   두 예비 검사 파일 path/sha256/passed, source_sha를 담은 approval JSON이 필요하다.
   `gate_promotion_authorized_if_all_conditions_pass=false`. 예비 통과만으로 승격하지 않는다.
3. 승인 뒤 **48개**. `--recording-stage batch --recording-approval <JSON>` 없으면
   실행기가 world 생성 전에 거부한다. 같은 결함 확인 시 진행/대기 실행을 멈추고 원본을 보존한다.

큐는 준비만 하며 **50개 모두 enabled=false, runs_enabled=false**로 만든다.
예비 동시 2, 후속 동시 6, 서버 전체 ≤40; 각각 새 기록 모드 첫 30초 속도/저장 부하를 측정한다.
원격 제출·활성화·새 스캔 관문·예비 검토·승인은 아직 하지 않았다.

## 디스크 예산과 보존 위치

| 항목 | 에피소드당 | 50개 합계 | 근거 |
|---|---:|---:|---|
| 예상 | 96 MiB | 4,800 MiB = 4.6875 GiB | JPEG 평균 50 KiB×900장 ≈43.95 MiB + 명령/평가/검토 여유; **미측정 추정** |
| 보수적 예약 | 1,024 MiB | 51,200 MiB = 50 GiB | 640×480×3×900 = 791.02 MiB RGB 등가량 + 로그/manifest 여유 |

원본은 **gcp1 n4-highcpu-64 GCP 영속 디스크**의
`/home/ugrp/ugrp-sim/runs/solo-record-<seed>-<SHA8>/raw`에 둔다.
[GCP 실행·보존 경로](../../docs/gcp_simulation.md). ARM 백업은 아직 미구현이며 원본을
회수/백업 완료로 보고하지 않는다. 원본 RUN_META class=dev, 실제 사용 축소 학습 자산은 milestone.
Mac 준비 시 df 여유 약 97 GiB; GCP/ARM live 여유와 다른 작업 예약은 원격 금지 범위 때문에 확인하지 않았다.
제출 전 storage_budget.py --all-hosts로 각 바닥·다른 예약 쓰기·이번 50 GiB를 합산해야 한다.
예비 2개 실제 bytes와 wall/SIM으로 후속 예산을 재산정한다. 크레딧 정지·8시간 STOP·유휴 20분을 유지한다.

## 검증과 남은 작업

시험은 `test_grasp_act_solo_recording.py`, `test_grasp_act_solo_run_path.py`,
`test_grasp_act_contract.py` 3파일만 수행한다. 원본/hash/이력/target/FOV 훼손 거부,
정답 자세 스캔 인계 거부·지도 변화 독립성, 관문 시드/잘못된 프로필/승인 없는 batch 거부,
가짜 backend의 실제 기록 loop와 실패 저장을 확인한다. 결과는 record-pytest.txt 및
record-static-summary.json에 남긴다. 가짜 backend·오프라인 검증이며 Mac 물리/렌더를 하지 않는다.

남음: 수정 교사 관문, 원격 자원/미사용 시드, 예비 2개 실제 기록/30초 검사·영상 확인,
조정자 승인, 후속 48개 기록·원본 검증·데이터 채택·학생 학습. 선행 40/40과 합산하지 않는다.
