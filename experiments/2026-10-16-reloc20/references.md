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

## R2 수치와 R3 후보 선택

R2의 원본 prefix 거부 표는 `r2-partial-rejection-table.json`에 실행 중임을 표시해 저장했다. 93315 초기26.8SIMs의 같은 추정 상태를 재생하면 모든 RGB 기억을 넣은5개 목표는0/5, 빔 disc만 제외해도0/5, 정적 벽·초기 빔을 모두 유지하고 RGB 가설을 제외한 진단은5/5였다(`route_counterfactual.py`, 원본 경로/sha는 candidate-research-integrity.json). 이는 센서 가설이 경로 가용성을 막는다는 반례이며 RGB 장애물 삭제를 실행에 채택하지 않는다. no_route의 마지막 검사 물체가 wall_west였다는 것만으로 실제 막은 물체를 확정하면 안 된다. R3는 전체 거부 탐색 edge의 물체별 분포와 최소 틈을 함께 기록한다.

R2 초반1.5–40SIMs 저장 자기 RGB를 시드별77장 재생: 픽셀 벽 제외 후의 `can` 검출65/25건이 원래 색 덩어리를 유지한 벽 자격 거부 후0/0건. long_beam5/2, cyan31, yellow51, red14건은 그대로다. 이는 반복 검출 사건 수이며 독립 물체 수가 아니다. 기존 `_components`의3×3 open/close·최소 면적을 그대로 사용하고, 벽 픽셀을 먼저 빼서 생긴 조각을 새 물체로 세지 않는다. 원래 부모 윤곽에 기존 wall-class 픽셀이 있으면 그 윤곽 전체를 unknown 표면으로 거부한다. 새 면적·색·분율 문턱은 없다. `reloc20_obstacle_wall_component_v1` 기본off, R3 두 후보on. `component_replay.py`와 요약/원본 SHA를 보존했다.

R2 평가 전용 wheel angle 계측에서 순수회전의 wheel→body yaw gain은 약.984–.986으로 가까웠다. 명령 ODE→body는 같은 partial 분석에서.513/.740, bias−.780/−.0003deg/s였다. 이는 접촉점 slip이나 실물 적합도 측정이 아니다. 큰 명령 오차를 바닥 미끄럼으로 확정할 수 없고 native 휠의 펄스 응답 확인이 우선이라는 근거다.

순수회전 duty는93266 p0/p50/p100=4.469/7.317/18.571ms,93315=4.458/13.266/18.571ms였다. held travel 구간의 min_z는 각각약70.5/70.3mm 이상이고 finger contact는100%였으므로 이 분포를 단순히 짐이 바닥에 놓여 생긴 yaw 응답이라고 해석하지 않았다. 자유 회전에서 body/wheel 응답은 가깝지만, 짧은 pulse의 명령 모델 오차가 크다.

93266의180SIMs prefix(기존 carry phase180SIMs 상한과 같은 기록 창)로 방향별 배율.3142/.6058을 적합하면 그 시드 local yaw p95 .4903→.2089deg였으나, 적합하지 않은93315는.4974→.5026deg, signed sum1.728→−55.545deg로 악화됐다. 앞선 진단에서 본 DEV 시드이며 blind holdout이라고 주장하지 않는다. **배율 후보는 거부하고 runtime에 넣지 않았다.** `yaw-fit-rejected-summary.json`과 전체 원본/sha를 보존했다.

대신 R3 별도 `reloc20_turn_density_v1`(기본off)은 순수 운반/획득 회전에서 기존 on-time을 누적해 기존 제어 주기1개(.1s)의 대칭 pulse로 내보내는1차 pulse-density accumulator다. .1s는 새로 적합한 수치가 아니라 `SoloTeacher.PERIOD_S`/기존 duty_wheels의10Hz 주기다. 기존 wheel effort .35와150ms 계약 한도를 유지한다. 정지·방향 변경 시 미발행 잔여를 취소하고, 실제 발행 pulse만 ODE에 적분한다. 일정 방향에서 요청/발행 on-time 차이는1제어 주기 미만이다. 같은 전기 on-time이 같은 실제 운동을 보장한다는 주장은 하지 않는다. 긴 pulse의 새 물리 결과를 R3에서 비교하며, 100ms burst에 의한 떨림·정렬 실패도 실패로 기록한다.

[PDM 모터 구동 연구 초록](https://arxiv.org/abs/1302.7172)은 PWM 대신 delta-sigma/PDM과 기계 부하의 관계를 설명한다. AC motor 연구이며 우리10Hz MasterPi 성능 근거가 아니다. [NASA1994 PDM brushless DC motor 기록](https://ntrs.nasa.gov/citations/19940015169)은 검색 초록만 확인했고 페이지403으로 본문 미확인이다. [Group3 DC motor driver 제조사 매뉴얼](https://www.group3technology.com/_files/ugd/d47bcc_329eeb11b343452da9a8cae265bc102a.pdf)도 PDM 사용례의 참고다. 이번 적용은 기존 인터페이스에 맞춘 DEV 설계이고 실물 검증은 없다.
