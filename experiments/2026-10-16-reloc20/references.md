# 표준 방법·상수 근거

2026-10-16 공식 문서·초록 열람. CMU PDF 본문은 timeout으로 미확인. 변경 전 locdiag.md/JSON과 reloc19 R3 거부 표를 먼저 읽었다. locdiag의 L1 heading 증폭 63.1–66.1%, 두 기하 위험 구간의 국소 잔차 24.2–32.9%를 근거로 횡주행/구동 평균과 경로 기하를 우선한다. 전체 위치 오차의 독립적 인과 기여율로 해석하지 않는다.

- [Nav2 footprint](https://docs.nav2.org/rolling/configuration_and_development/first_time_robot_setup_guide/footprint/setup_footprint/): 로봇 형상 footprint와 원형 모델의 차이. 이번 후보는 기존 팔 외접원과 발행 PWM FK의 화물 꼭짓점 외접원을 합친 회전 불변 enclosure를 사용한다. 정밀 SE2보다 좁은 통로 가용성을 줄이는 한계가 있다.
- [Nav2 footprint collision checker](https://api.nav2.org/nav2-rolling/html/classnav2__costmap__2d_1_1FootprintCollisionChecker.html), [Nav2 tuning](https://github.com/ros-navigation/docs.nav2.org/blob/rolling/docs/configuration_and_development/tuning_guide.md): 원래 형상/전체 경로를 검사하고 inflation은 여유와 경로 비용에 사용한다. 이번 strict A*는 시작·목표와 모든 연결 간격을 검사하고 기존 margin-release 우회를 쓰지 않는다. 경로 검사량은 기존 40,000 노드, 격자는 기존 0.05m다. 간격 .01m 검사의 최대 미관측 거리는 간격/2이며 distance의 1-Lipschitz 성질로 뺀다.
- [Nav2 velocity smoother](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/configuring_velocity_smoother/): 가감속·deadband와 실제 odometry feedback을 구분한다. 발행 명령을 실제 속도로 취급하지 않는다.
- [CMU Seegmiller/Wettergreen IROS2011 원문](https://publications.ri.cmu.edu/storage/publications/pub_files/2011/9/Seegmiller_IROS-2011_Optical_Flow_Odometry.pdf), [공식 초록](https://www.ri.cmu.edu/publications/optical-flow-odometry-with-robustness-to-self-shadowing/): 자기 그림자와 관측 불일치 제거가 필요한 optical flow odometry. 논문 방법의 우리 카메라 정확도는 미검증. 이번 LK는 metric VO가 아닌 정지 영상 판별이며 원래 forward/backward1px·tracks6·cells2를 유지한다.

## 수치 출처

- clearance `.007014 + .08*.1 = .015014m`: locdiag 최대 기하 침투 7.014mm + 기존 최고 전진속도×제어주기 8mm. DEV 설계 여유이며 위치 오차까지 보장하는 확률 경계가 아니다. 반경은 기존 .26m 팔 envelope와 명령 FK 화물 꼭짓점 반경의 최댓값+이 여유다. 카메라·하중 물리는 변경하지 않았다.
- 바닥 빔은 기존 벽 지도에 빠져 있었다. `fixed-floor-map.json`은 사용자가 허용한 고정 장애물 지도에 시나리오의 **선언된 초기** beam_1을 별도 keepout으로 명시한다. 600×40mm는 sim/zone_cargo.py의 기존 카탈로그다. 움직인 빔의 현재 형상/좌표를 안다는 뜻이 아니며 평가 정답으로 갱신하지 않는다. 원래 시나리오 파일 hash를 검증한다.
- heading release .04rad, 전진 .08m/s, 회전 .1rad/s, gain .9/.6: 기존 carry arrival/control 값 그대로다. 전진과 회전을 분리해 짧은 비대칭/횡 펄스를 제거한다.
- contact ODE: PR510 후속 `7b223e30b2a4d5044641ce23ca502bf82d176092:harness/drive_model.py`를 별도 모듈로 보존했다. rolling torque1.857e-3Nm, damping2.86e-5Nms, inertia3.85e-4kgm²는 기존 3개 무하중 v7 측정/XML 추정이며 reloc20 시드로 재적합하지 않았다. 기존 순수회전 gain을 ODE에 중복 적용하지 않는다. 원래 predictor는 그대로다.
- visual stall: flow-fit.json의 원본 R3 두 시드 마지막 정지 구간에서 median/p90 flow와 전역 mean absolute image difference 각각 p99. 전체29쌍 중 LK 자격 쌍의 경험 분포이며 학습용 fit이지 독립 검증이 아니다. 원래 minimum expected .05m, max window1.4SIMs, maximum yaw .02rad를 유지한다. 자기 팔 PWM이 바뀐 쌍·약한 질감은 unknown이다. 회전하면서 막히는 경우에는 정지 detector가 놓칠 수 있다.
- covariance: 억제한 증분의 세계 좌표 오차 `e eᵀ`를 더한다(손실 운동의 2차 모멘트). 공분산을 0으로 만들거나 임의 배율을 넣지 않는다. 독립 명령 predictor는 계속 진행해 detector가 자기 출력을 재사용하지 않는다.
- 후퇴 .30m/최대10SIMs와 역속도 .05m/s: 기존 e2e_stall_odometry.PROGRESS/CarryToZone 한도. 거리 종료는 발행 이력이며 실제 후퇴 성공으로 보고하지 않는다. 매 틱 기하 검사 뒤 발행한다.

## 영상 선검토

locdiag 93315 onset 43–58.5SIMs 2Hz 띠를 직접 읽었다. 빔 끝으로 접근→빔 끝에서 진행보다 회전이 커짐→이탈 순서이며, 시작/종료만 보면 이 구간을 놓친다. 모든 운반 완주 성공0이므로 성공1개 대조는 현재 미충족이다. 새 결과에서 실패1–2개 전체2Hz·마지막10초10Hz와 성공이 생기면 성공1개를 검토한다. Mac에서는 파일 읽기만 한다.

## R1 원본에서 발견한 RGB 벽→캔 오인

R1 candidate93266의 개요+r1+r2+r3 81.5–97.0SIMs 띠(32개 노출,2Hz)를 직접 읽었다. r1은 바닥을 보다가 보라 벽을 화면에 크게 넣고 정지/재관측으로 넘어간다. 원장에는 `can` 기억이 생겼고 첫 route start overlap은 이 자기 RGB 기억이었다. gcp2에서 저장된 native640×480 자기 RGB75–96SIMs 42장과 당시 **직전 발행 PWM**으로 기존 검출기를 재생:84.5/85.0/87.5SIMs의3장에 벽 위 `can` 윤곽, 기존 v5 `reloc16_floor_mask.floor_clear`를 검출에 연결하면3장 모두 제외. 다른 검출 결과는 유지했다. 처음 6개 듬성한 frame 재생에서는before 검출도0이라 효과를 검증하지 못했고,2Hz 전체 창을 읽어3장을 찾았다. 87.8SIMs의 정확한10Hz 제어 원본은 이 시점에 보존되지 않아 동일 프레임 재현으로 주장하지 않는다.

`reloc20_obstacle_wall_mask_v1`은 기본off. 벽/바닥 색의 기존 원본 percentile classifier를 재사용하며 새 색·크기·수용 상수는 없다. 삭제/완화로 기존 장애물 기억을 지우는 방식이 아니라 새 윤곽의 벽 픽셀을 역투영 전에 제외한다. 하중 metric VO나 정답 segmentation을 쓰지 않는다. [재생 원장](wall-replay.json), `wall_replay.py`. 성공1개 영상은 아직 없다.
