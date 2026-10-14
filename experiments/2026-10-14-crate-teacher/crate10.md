# crate10 — 접근 펄스 검사와 벽 앞 명시적 핸드오프

2026-10-15, PR #500 `claude/act-crate-teacher`. 먼저 [crate9](crate9.md)을 읽었다.
기준은 `bf31840fe16cd2d37631d8a8e50ff077e3d42575`: 새 진단 **8/10**, 집기/들기 진입
부분집합 **8/8**이다. 본체 누름 네 실패가 있었던 이전 `5644e3dd`의 5/10과 합산하지 않는다.
이번 수정의 물리 성공률은 아직 없다. 실행 SHA·대기열은 커밋/push 뒤 로컬
`outputs/e2e18-admin/crate10-delivery.json`에 고정한다.

## 세 실패의 독립 확인

원본은 `outputs/gcp1-runs/crate-diag-77969-5644e3dd/`와
`crate-diag-7797{0..9}-bf31840f/`다. 회수된 SHA256SUMS **2,199/2,199 파일 일치**,
누락·불일치 0이다(이전 77969 213개, bf31840f 10개 1,986개).
[원본 해시](crate10-source-hashes.json), [분류](crate10-analysis.json),
[평가 전용 회전](crate10-motion-eval.json)에 근거를 남겼다.

세 실패 모두 **pick permit 0, lift permit 0**이다. 77969는 r1, 77978·77979는 r2가
READY에서 기다렸다. 운영자의 “상자를 잡았다”는 관찰은 명령 원장과 다르다.
서로 다른 끝이 배정됐으며, 동료가 목표점을 덮는 search8 주원인은 이 세 건에서 확인되지 않았다.

| 시드 / 로봇 | 분류와 원장 근거 | 새 결정의 범위 |
|---|---|---|
| 77969 / r2 | 자기 화물 가까이 접근한 뒤 시야 상실·회전 정체. 마지막 가시 접근 11.3초부터 여유 안에서 회전 포함 펄스를 발행. 후반 392.6° 명령 회전 대비 실제 순회전 74.316/0.659/0.481° | 격리한 11.3초 가시 입력에서 원래 펄스 거부. 쌍 전체의 첫 차이는 더 이른 6.7초 r1의 안전 재계획 정지 |
| 77978 / r1 | 정적 벽. 11.9초 모든 유효 antipodal 후보(0/±15°)가 벽 여유 **81.216–92.568 mm 부족**. 다른 각도는 파지 기하 검사에서 제외. 동료/다른 화물 목표 차단 아님 | 11.9초 `static_stances_blocked_handoff`. 37.8초까지 탐색/재계획을 반복하지 않음 |
| 77979 / r1 | 자기 화물 접근 펄스의 경로 침범(10.7초), 재탐색, 정체 자세 제외 누적. 마지막 실패 계획은 0/−15° previously_stalled, +15° unsafe_segment. 목표 자체는 peer/wall/cargo 여유 밖 | 10.7초 `unsafe_pulse_hold_replan`. 안전 대안 없이는 진행하지 않음 |

벽과 접촉한 힘의 분담은 원본 저장 범위 밖이다. 77979의 실제 회전은 첫 원에서188.35°,
둘째에서378.58°라서 77969처럼 계속 거의 안 돌았다고 일반화하지 않는다.
77978의 벽 부족은 몇 mm의 목표 이동으로 해결되지 않는다. 화물 재배치 없이 안전한
파지를 보장하지 않으며, 명시적 지도 단계 핸드오프도 **실패**다.

각 실패의 처음·중간·마지막 저장 JPEG를 포함해 **6시각 × overview/r1/r2 = 18장,
총54장** 직접 봤다. 시각은 77969=1.8/14.8/27.8/39.8/52.8/65.8,
77978=1.8/8.8/15.8/23.8/30.8/37.8,
77979=1.8/14.8/26.8/39.8/51.8/64.8 SIM초다. 최대 간격13초.
[프레임 경로·해시](crate10-visual-review.json), 모음은 로컬
`outputs/e2e18-admin/crate10-audit/<seed>-frames.jpg`다. 새 렌더는 하지 않았다.

## 변경

상자는 빔의 `VisibleOnlyGraspTeacher`를 상속하며 같은 경로·목표 후보 모듈을 쓴다.
`git fetch origin` 후 원격 최신 `793865d2`를 병합했다. 기존 상자 profile·가시 재획득
분기를 유지하도록 충돌을 합쳤고, 새 공통 복구에도 상자 장애물 형상을 전달한다.
최종 fetch에서도 원격 최신은793865d2였다. search9는 아직 미커밋이므로 복사하지 않았다.

상자에만 기본 OFF `--crate-approach-recovery crate_approach_recovery_v1`을 추가했다.
켜면 공통 `approach_recovery_v1`·`approach_progress_v1`도 켜며 기존 search_reacquire_v1을 유지한다.

- 현재 보이는 맡은 손잡이가 있을 때 접근/정렬의 실제 발행 바퀴 펄스를 명령 운동학으로
  투영한다. 바퀴별 종료 시각과 최대5ms 간격에서 원래 장애물/동료/벽 여유를 검사한다.
  이미 여유 안이면 제자리 회전을 진행으로 인정하지 않는다. 안전한 같은 경로의 병진
  단독 명령을 다시 검사하고, 없으면 정지 후 재계획한다. 물리 예측/실측 이동 보증은 아니다.
- 기하상 유효한 파지 후보가 전부 정적 장애물 안이면 즉시 명시적 핸드오프한다.
  동료 점유·no_path·unsafe_segment·이전 정체 제외를 정적 차단으로 오인하지 않는다.
- 자기 RGB에서 맡은 끝을 못 본 시간은 “가시 접근3초 무진척”에 넣지 않는다.
  상자 타이머 `crate_visible_progress`를 공통 `approach_progress` 모드와 분리했다.
- CLI→교사→실행 메타데이터/결과에 모드를 기록한다. 실제 runner에도 visual mapping
  입력 경계 감사를 적용하고 금지 필드 읽기 시 예외/카운터를 남긴다.

0.25kg·색 손잡이·antipodal 검사·기존 Cartesian 상승 명령·성공 기준·카메라·서보·접촉·마찰·
weld OFF를 유지한다. 들고 있을 때에는 이 항목에서 화물 위치를 읽지 않는다.
새 ACT 학생 실행이나 수작업 학생 파지 대체는 없다.

참고로 직접 읽은 1차 자료:
[Nav2 Rotation Shim](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/controller_plugins/configuring_rotation_shim_controller/),
[실제 투영/충돌 검사 코드](https://api.nav2.org/nav2-rolling/html/nav2__rotation__shim__controller_8cpp_source.html),
[SimpleProgressChecker](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/controller_server/controller_server_plugins/simple_progress_checker/).
표준의 명령 투영→충돌 거부·유한 재계획 구조를 따른다. 여기서는 TF/실측 odometry 대신
허용 가시 측정과 자기 명령 운동학만 사용한다. 새 논문의 성능 재현을 주장하지 않는다.

## 저장 입력 재생·시험

[재생](crate10-replay.json)은 평가 위치·접촉·관절을 제거한 뒤 컨트롤러를 만든다.
이전 소스의 교사 클래스를 Git SHA에서 고정해 grasp 명령 **8,368/8,368**을 대조했다.
PWM·바퀴·시각·단계·done 정확 일치, 펄스 길이만 GCP/Mac libm 차이≤1e−10초다.
후보는 첫 명령/단계/종료 결정 차이에서 중단한다. 뒤의 옛 영상을 새 궤적의 결과로 쓰지 않는다.

성공8건 총5,078명령 중 **4건(77970/74/75/77), 2,458명령은 변경0**이다.
나머지4건은 각 첫 변경 명령1개를 확인했다(77971=13.6초, 77972=8.2초,
77973=21.3초, 77976=21.9초; 모두 안전 정지/재계획). 이후 변경 총수는 미측정이다.
첫 차이 이후 입력을 계속 강제 주입해 변경 수나 성공을 부풀리지 않는다.
세 실패의 새 결정은 위 표와 별도 가시 단면 fixture로 확인했다.
재생 입력 감사 **invisible_measurements=0, held_world_reads=0**이다.

시험3파일 **94 passed**: `test_crate_approach_recovery.py`, `test_crate_antipodal.py`,
`test_grasp_act_goal_set.py`. 저장 실패 펄스, 벽 핸드오프, OFF 명령 유지, 가시 시간,
held 금지 객체, 기존 상승 궤적, 중간 펄스 충돌, 메타데이터를 검사했다.
로컬 원격 실행·물리·렌더는0회다. 실제 새 GCP 입력 감사와 성공/충돌/속도는 미검증이다.

## 새 대기열과 남은 일

`20261015-crate-<SHA8>.json`은 **ready=true**, 진단10 새 시드77980–77989와
기존 실패3 정확 시작 재현(77969/78/79)을 활성화한다. 별도 새 관문40은77400–77439,
`gate_promotion_authorized_if_all_conditions_pass=false`, `coordinator_approval.approved=false`,
관문 run은 ready/runs_enabled=false다. 진단10/10·재현3/3 실제 성공, 회수·감사·영상·속도·
결함 검토 후 **해당 SHA에 대한 조정자 승인**이 있어야 관문을 활성화한다.
핸드오프/timeout/HOST_ERROR를 성공으로 바꾸지 않으며 관문은 최소38/40이다.

시드의 로컬 과거 계획·공용 대기열·회수 디렉터리 충돌0, 원격 예약은 미확인이다.
실제 학생 해상도/FOV를 바꾸지 않고 정적 시작 시선 검사만 진단10/10·관문40/40 통과했다.
그 과정에서 step/forward/inverse/renderer 진입점은 실패하도록 차단했다.
GCP 크레딧 정지·8h·유휴20분·디스크·실제 동시 부하 속도·예약 잠금은 운영자가 제출 전에 확인한다.
총 동시 상한40/상자10·실행당128MiB(53개6,784MiB, 복사 별도)를 유지한다.

bf31840f 대기열은 운영 결과상 완료지만 읽은 파일 status는 `ready`였다. 사용자 지시대로
내용을 바꾸지 않으며 새 큐에 `never_resubmit`와 기존 파일 SHA를 남긴다.
이번 작업은 원격 접속/제출을 하지 않는다. **77978의 안전한 실제 파지와 새 관문 승격은 미해결**이며,
실패 시작 재현이 핸드오프라면 관문은 승인 대상이 되지 않는다.
