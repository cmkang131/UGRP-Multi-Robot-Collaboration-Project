# release19 준비 (2026-10-15)

단계 1: 제어 소스 `a3bbc90e07d3d731278cb6c83185687a190e3c6b` 그대로, 새 시드 **110600–110639** 40개를 예약했다.
로컬 vm3-queue와 experiments의 JSON/Markdown/텍스트 7,081파일을 보수적으로 확인했고 중복 0개다.
저장소 전체/원격 브랜치 검색은 하지 않았다. 입력 경로 목록·해시의 digest는 `release18-gate40-seed-audit.json`에 있다.
관문은 **≥38/40**, 인계 실패·HOST_ERROR·timeout은 실패이고 대체 시드를 넣지 않는다. 학습 기록 off·180초 상한·기존 판정 유지.
큐 `20261015-release-gate40-a3bbc90e.json`은 40회 모두 승인·준비·실행 플래그 false이고 제출하지 않았다.

새 입력 계획은 제어 소스와 별개다. 큐는 압축된 계획과 SHA-256을 내장하고 원격 명령 argv로 전달한다.
따라서 a3bbc90e에 새 파일/수정 없이 기존 run()을 호출한다. 조정자는 각 SHA의 깨끗한 별도 source checkout을 지정한다.
활성 worktree를 과거 SHA로 되돌리지 않는다. `--commands`는 argv를 출력만 하고 실행하지 않는다.

```sh
python3 -m scripts.prepare_release_gate40_queue --verify /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-release-gate40-a3bbc90e.json
python3 -m scripts.prepare_release_gate40_queue --commands /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-release-gate40-a3bbc90e.json --candidate A --source-worktree /path/to/clean-a3bbc90e-source
```

## 참고 자료

- `scripts/make_grasp_act_release_plan.py`: 기존 분포·판정·정적 시작 배치 생성기(물리/렌더 없음).
- `release18-diagnostic-plan.json`, `release18.md`: release18 실행 옵션과 기존 관문.
- 로컬 `outputs/e2e18-admin/gcp-reports/release18-diagnostic-a3bbc90e.json`: 제공된 9/9 진단, 관문과 합산하지 않음.

## 단계 2 — 기본 off release19_v1

자기 RGB·자기 명령만 유지한다. 잡은 화물 세계 좌표·공용 top 입력은 추가하지 않았다.
`--release-profile release19_v1`에서만 중복 sweep 대기를 재사용하며, API/CLI 기본값은 `off`다.
release18의 FOV/명령 대기/목표 영역 옵션과 **0.04 m 여유·시각 안정·들기 확인·180초 상한을 그대로 유지**한다.

74976 첫 보정의 실제 원장(선택 world t=29.2→76.7, 양쪽 로봇 동시 시간을 중복 합산하지 않음):

| 구간 | SIM초 | 시간의 근거 / 처리 |
|---|---:|---|
| 접근 전·후 선 정렬 | 5.5+0.7=6.2 | 자기 RGB 0.3초 연속 안정·FOV 펄스·순차 양단 확인; 유지 |
| 펄스 접근 | 1.2 | 자기 명령 기반 접근, 지도 여유 검사; 유지 |
| 재파지 | 6.1 | 시작 0.2 + hover 1.2 + 하강 8×0.2 + 닫기/들기·대기; 유지 |
| 순차 들기 확인 | 13.8 | 각 로봇 lift 1.4 + settle 3.0 + 연속 yes 1.0 + restore 1.4, tick/전환 포함; 유지 |
| 재파지 ACK | 0.1 | 기존 GO/ACK 인계; 유지 |
| 적재 펄스 이동 | 1.8 | GO 0.2 + 0.1초 tick 16개(0.2/0.129 m/s); 유지 |
| 다시 낮추기·ACK·열기 | 2.4+0.1+1.4=3.9 | 8개 waypoint·낮추기 안정·열기 1.2와 tick; 유지 |
| 되돌아보기·재관측 | 14.4 | 전후 sweep 2×4.5 + 후퇴/안정 3.6 + gaze 복귀 1.0 + 관측/전달 0.8 |
| 합계 | **47.5** | release19 조건부 scheduler 재생 **45.9** |

각 sweep의 `arm_to_look`는 첫 시야와 **완전히 같은 PWM**을 주고 1.0초 기다린다.
직후 `view_+0_-60`이 같은 명령을 재발행하고 다시 0.8초 기다린다. release19는 이 두 번째 대기만 재사용한다.
원래 0.8초를 충족한 최신 명령 이력·같은 PWM·holding=false·빈 servo/주행 큐·바퀴 정지를 모두 요구한다.
새 명령·이력 불명/변경·잡은 상태·몸체 이동 뒤에는 재사용하지 않는다. 새 캡처와 3방향 시야·두 번의 sweep·지도 수락 검사는 유지한다.
픽업 hover는 정렬 hover와 실제 PWM이 다르므로 1.2초를 줄이지 않았다. 들기 확인·후퇴 안정 시간도 줄이지 않았다.

0.2 m는 `release_global_observation.MAX_SHIFT_M`의 소프트웨어 폐루프 보정 상한이며, 모터의 물리적 최대 이동량이 아니다.
`ReleaseTeacher.shift_plan()` 자체는 더 긴 거리를 펄스로 만들 수 있다. 그러나 상한을 늘리면 재관측 없이 적재 이동하는 구간도 늘어난다.
기존 기록에는 횡방향 누적 드리프트가 있으며, 더 긴 한 번의 적재 이동에 대한 파지 유지·물체/벽 swept clearance 근거가 없다.
이번에는 0.2 m를 유지한다. 시작 여유 −0.56 m 미만의 **4회 보정·180초 위험은 해소하지 못했다**.

저장 원장 9실행의 result/teacher **27파일**을 로컬 manifest와 제공된 진단 보고의 복원 해시로 확인했다.
양쪽 92 sweep에서 실제 ScriptRunner를 재생했고 **명령 순서·입력 특징/이미지 해시 순서가 모두 동일**했다.
14개 보정마다 1.6초 절감, 중앙 **47.95→46.35초**; 74976/78526 전체는 각각 6.4초 대기 절감이다(최초 관측 포함).
이전 상태의 같은 특징열을 앞당긴 조건부 재생이며 새 궤적·물리 시간·관문 성공 예측이 아니다.
관련 시험 **61 passed**: release19/18/runner 3파일. release19를 끈 release18 경로는 a3bbc90e의 원래 run()과
25초 clock-only backend에서 양쪽 teacher JSONL·actuator 명령·결정·결과가 동일했다. 실제 물리/렌더·원격 접속은 0회다.

실행 결과 `input_audit`에 `control_top_camera_reads`와 평가용 top 호출 수를 추가했다.
공개 `world.render_team_jpeg` 진입을 감싸 제어 호출은 **계수 후 차단**, 평가 캡처에만 명시적 허용을 준다.
clock-only runner에서는 control_top_camera_reads=0이고 금지 호출 양성 시험도 통과했다. private renderer API는 계수 범위 밖이다.
a3bbc90e 원본에는 계수가 없으므로 과거 9회에 런타임 top=0을 소급하지 않는다. 새 후보의 GCP 계수는 미측정이다.

```sh
python3 -m scripts.replay_release19 --report /Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/release18-diagnostic-a3bbc90e.json --out /private/tmp/release19-replay.json.zst
python3 -m pytest -q tests/test_release19.py tests/test_release18.py tests/test_grasp_act_release_run.py
```

참고 자료 추가:
- `sim/lookaround_localization.py:script/ScriptRunner`, `sim/release_regrasp.py`, 양쪽 teacher 원장: 위 시간과 중복 명령의 직접 근거.
- `sim/release_global_observation.py:MAX_SHIFT_M`, `sim/grasp_act_release_teacher.py:shift_plan`, `release5.md`: 이동 상한·펄스·과거 누적 드리프트.
- [ViSP 공식 IBVS 코드](https://github.com/lagadic/visp/blob/master/tutorial/visual-servo/ibvs/tutorial-ibvs-4pts-wireframe-robot-viper.cpp): 매 반복 새 특징 갱신을 확인, 캡처 생략 없이 중복 대기만 재사용.
- [ROS 2 trajectory controller 공식 문서](https://github.com/ros-controls/ros2_controllers/blob/master/joint_trajectory_controller/doc/userdoc.rst): 명령 시각과 실제 도달 판정의 구분을 확인했다. 이 교사는 측정 관절을 받지 않으므로 도달 판정을 도입하지 않는다. 외부 문서는 프로젝트의 0.8/1.0초 수치를 보증하지 않는다.
