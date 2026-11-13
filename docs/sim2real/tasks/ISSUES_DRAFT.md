# GitHub 이슈 초안

**게시하지 않은 초안**이다. 13개 모두 병렬 준비 가능하며 담당자는 미지정이다. 아래 제목·본문을 향후 이슈로 옮길 때 문서 링크를 해당 저장소의 경로로 연결한다. 이 파일의 상대 링크는 현재 파일 기준이다. 원격 이슈·PR 생성은 이번 작업 범위가 아니다.

모든 본문에 적용: 실물 전부 확인 안 됨. 카드의 새 기준은 **초안 제안·실물 미검증·담당자 합의 필요**다. 근거·합의 전 수용 상수로 구현하지 않는다. 공용 TOP·지도·AprilTag 금지, 보드는 offline 보정 후 제거, 시작 지정상자 1회 정보를 자동 GT로 확대 금지. PWM 500–2500은 실물 전범위 스윕 허가가 아니며 기구 확인·비상정지·무부하부터 시작한다. 10 Hz/0.15 s 중첩 정책은 미확인이다.

## T01

제목: `[Sim2Real][T01] 경기장 외형과 실물 HSV 임계 검증`

본문:
- 목표: 초록 벽과 빨강·파랑 상자를 실물 사진으로 분리한다. [카드와 절차](T01_environment.md).
- 준비/의존: 사진 수집·마스크 작성은 독립. T02 전처리 변경 시 재평가한다.
- 완료 후보: 미사용 30장 이상·클래스별 등장 10장 이상, precision/recall 각각 ≥0.90. 사용자 초기 HSV와 변경값·근거를 함께 제출한다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T01-<run>/`, `hsv.json`, `color_metrics.csv`와 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 기준 합의 [ ] 미사용 평가 [ ] 실패 포함 전체 분모 [ ] 원본/마스크 해시 [ ] 실물 여부 표시.

## T02

제목: `[Sim2Real][T02] 어안 카메라 보정과 장착 자세 측정`

본문:
- 목표: 640×480 자기 RGB와 320×240 모델 입력의 시야·왜곡·장착 차이를 잰다. [카드와 절차](T02_camera.md).
- 준비/의존: 정적 촬영 독립, 팔 구동 시 T04 안전 범위 필요. calibration board는 offline 촬영 후 제거한다.
- 완료 후보: 기존 프로토콜 30–40장, 적합 2/3·검증 1/3, RMS ≤1.0 px·검증 평균 ≤적합의 2배를 보고하고 최신 적용 여부를 재합의한다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T02-<run>/`, `camera.json`, `reprojection.csv`와 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 어안 모델 일치 [ ] 독립 검증 [ ] 실제 FOV/장착 측정 [ ] 보드 제거 [ ] 사진 해시.

## T03

제목: `[Sim2Real][T03] 바퀴 펄스 변위와 불감대 측정`

본문:
- 목표: 전후·좌우·양회전의 실제 변위·정지 지연을 측정한다. [카드와 절차](T03_wheel_pulses.md).
- 준비/의존: 독립 단일 펄스 벤치 가능. 연속 구동은 T06 중첩 정책 확정 필요.
- 완료 후보: 6방향 각각 0.10 s 펄스 5회 이상, 그중 검증 2회 이상. 필수 측정 커버리지 100%, 누락 이유 없는 행 0개. 실물 정확도 채택 기준은 별도 합의한다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T03-<run>/`, `pulses.csv`, `wheel_fit.json`과 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] STOP 무부하 확인 [ ] SDK 단위 구별 [ ] 전압/바닥 기록 [ ] 방향별 잔차 [ ] 실패 원장.

## T04

제목: `[Sim2Real][T04] 서보 안전 범위·각도·집게 폭 보정`

본문:
- 목표: 관절별 PWM–각도·정착 시간·집게 폭을 측정한다. [카드와 절차](T04_servos.md).
- 준비/의존: 독립 벤치 가능. 전범위 스윕 금지, 기구·케이블·낙하 위험 먼저 확인한다.
- 완료 후보: 5/5 채널과 안전 범위 기록, 관절별 안전 표본 3개 이상에 양방향 각 3회, 집게 3위치 각 3회, 범위 밖 명령 0건.
- 결과: `experiments/sim2real-<YYYYMMDD>-T04-<run>/`, `servo_table.csv`, `safe_ranges.json`과 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 기구 확인 [ ] 비상정지 [ ] 양방향 반복 [ ] 실측과 명령 구별 [ ] 허용 범위 근거.

## T05

제목: `[Sim2Real][T05] 팬·기울기와 카메라 시선 환산`

본문:
- 목표: 서보 변화와 광축/픽셀 변화의 부호·결합을 측정한다. [카드와 절차](T05_pan_tilt.md).
- 준비/의존: 저장 영상 분석 독립. 실제 구동은 T04 범위, 영상각 적합은 T02 보정값 필요.
- 완료 후보: 안전 자세 3개 이상·양방향 각 3회, 부호 일치 100%, 미사용 자세 각도 MAE ≤2°. 2°는 미검증 오차 예산 제안이다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T05-<run>/`, `pan_tilt.csv`, `transform.json`과 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 축/부호 정의 [ ] 자세별 잔차 [ ] 독립 검증 [ ] 보정 의존 해시 [ ] 기준 합의.

## T06

제목: `[Sim2Real][T06] 10 Hz 명령 어댑터와 중첩·STOP 계약`

본문:
- 목표: 4바퀴·5서보 요청의 단위와 실제 발행/정지 의미를 맞춘다. [카드와 절차](T06_command_contract.md).
- 준비/의존: mock 독립, 실물 서보는 T04 범위 필요. 10 Hz/0.15 s 중첩 정책 미확인 상태에서는 연속 실물 실행 금지.
- 완료 후보: mock 1000틱 누락·중복 0, 중앙 주기 0.100 s ±0.005 s, P95 절대 오차 ≤0.020 s, 부적합 요청 발행 0건. 실물 지연·STOP은 별도 측정한다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T06-<run>/`, `contract.md`, `timing.csv`와 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 중첩 정책 근거 [ ] 단절/종료 STOP [ ] 무부하 확인 [ ] clock domain [ ] 타이밍 기준 합의.

## T07

제목: `[Sim2Real][T07] 소비 영상·명령·실패 trace 완전성 확인`

본문:
- 목표: 실제 소비 프레임과 명령을 실행 단위로 재구성한다. [카드와 절차](T07_recorder.md).
- 준비/의존: 저장 입력 재생·오류 주입 독립, 실물 연결은 T06 이벤트 의미 필요.
- 완료 후보: mock 100틱 명령 연결 100/100, 누락 이유 없는 프레임 0, 해시 불일치 0. full-frame 모드는 보존율 100%, 오류 주입 결과는 별도 집계한다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T07-<run>/`, `trace_audit.csv`, `analysis.json`과 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 4 Hz 샘플/full-frame 구별 [ ] 분석기 실행 [ ] 입력/명령 직접 대조 [ ] 누락 사유 [ ] 공개정보 검사.

## T08

제목: `[Sim2Real][T08] 집기를 끈 색 추종 접근 분리 시험`

본문:
- 목표: 상자 정면 0.20 m 정지와 정렬 오차를 검증한다. [카드와 절차](T08_approach.md).
- 준비/의존: 저장 영상/시뮬 준비 독립. 실물은 T01/02/03/06/07, 가동 팬은 T05 필요. 시작 정보는 1회만 제공한다.
- 완료 후보: 미사용 12배치 중 10개 이상 거리/횡오차 각각 ≤0.01 m·방향 ≤4°, 충돌 0. 기준점과 약 4°의 판정 해석은 먼저 합의한다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T08-<run>/`, `approach.csv`, `initial_information.json`과 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] main 미포함 코드 식별 [ ] 초기 정보 출처 [ ] GT 갱신 없음 [ ] 미사용 분할 [ ] 단계별 분모.

## T09

제목: `[Sim2Real][T09] seg5_v1 ACT 집기·들기 추론 검증`

본문:
- 목표: 4000스텝 모델의 실기 추론·전처리·파지를 검증한다. [카드와 절차](T09_act_pick.md).
- 준비/의존: 저장 입력 추론 독립. 실물은 T01/02/04/06/07, T08 대신 수동 초기화 가능.
- 완료 후보: 추론 100회 invalid 0·전처리+추론 P95 ≤0.10 s, 실물 10회 중 8회 이상 들고 3 s 유지, 비의도 낙하 0. 순간 들림·명령 끝·물리 성공을 분리한다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T09-<run>/`, `inference.csv`, `pick.csv`, `model_manifest.json`과 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 모델 실로드 [ ] 전처리 해시 [ ] 워밍업 제외 공개 [ ] 규칙 전환 오탐 [ ] 물리 평가 분리.

## T10

제목: `[Sim2Real][T10] 87행 고정 놓기 시퀀스 안전 검증`

본문:
- 목표: 교사 시연 140개 출처의 고정 87행 재생과 초기 자세 민감도를 확인한다. [카드와 절차](T10_release.md).
- 준비/의존: 출력 없는 재생 독립. 실물은 T04/06/07, T09 대신 안전 지지 초기화 가능.
- 완료 후보: 87행 원본 순서·값 차이 0, 자유 놓기 10회 중 8회 이상·비의도 낙하/충돌 0. 지지 사용 시행은 별도 분모다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T10-<run>/`, `replay_diff.csv`, `release.csv`, `sequence_manifest.json`과 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 원본 시각 유지 [ ] 기구 범위 [ ] 초기 자세 기록 [ ] 지지 사용 공개 [ ] 실패 보존.

## T11

제목: `[Sim2Real][T11] 지도 없는 무하물 문 통과·구역 도착`

본문:
- 목표: 자기 RGB의 초록 벽·구역 색으로 무하물 이동한다. [카드와 절차](T11_navigation.md).
- 준비/의존: 검출/모의 실행 독립. 실물은 T01/02/03/06/07, 가동 팬은 T05 필요. 집기는 불필요.
- 완료 후보: 문 11/12 이상·구역 5/6 이상, 충돌 0·금지 입력 0. 시뮬과 같은 규모의 비교 제안이며 실물 보장 아님.
- 결과: `experiments/sim2real-<YYYYMMDD>-T11-<run>/`, `navigation.csv`, `evaluation_definition.md`와 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 실제 문/차체 치수 [ ] 지도 없음 [ ] 평가 경계 고정 [ ] 막은 물체/틈 [ ] 문/구역 분리 집계.

## T12

제목: `[Sim2Real][T12] 로봇 간 메시지 송수신과 오래된 메시지 거부`

본문:
- 목표: 로봇 사이 계획용 메시지 통로와 단절 처리를 검증한다. [카드와 절차](T12_robot_messaging.md).
- 준비/의존: 모터 없는 통신 독립. 후속 구동 연결만 T06/07 필요. 본 과제에서 로봇을 움직이지 않는다.
- 완료 후보: 방향별 100회에서 ≥99/100 응답·RTT P95 ≤0.10 s, 오류 주입 시 오래된 메시지가 최신으로 받아들여진 경우 0건.
- 결과: `experiments/sim2real-<YYYYMMDD>-T12-<run>/`, `message_contract.md`, `messages.csv`와 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 1비트 업무 payload [ ] 감사 필드 옆길 없음 [ ] 지연/역순/손실 [ ] 동일 시계 RTT [ ] 공동 들기 성공과 구별.

## T13

제목: `[Sim2Real][T13] 실측 출처 기반 SysID 후보와 독립 검증`

본문:
- 목표: 실측값을 새 기본 off 시뮬 프로필 후보로 연결한다. [카드와 절차](T13_sysid.md).
- 준비/의존: 형식·단위 검증 독립. 채택할 항목의 실측 결과만 필요하며 모든 과제 완료를 기다리지 않는다.
- 완료 후보: 출처/해시/단위 연결 100%, fit–holdout 중복 0·근거 없는 상수 0, 항목별 독립 holdout ≥3. 기존 validator의 더 큰 요구는 유지한다.
- 결과: `experiments/sim2real-<YYYYMMDD>-T13-<run>/`, `parameter_mapping.csv`, `fit_report.json`, `comparison.csv`와 [공통 template](../04_tasks.md#result-template).
- 체크: [ ] 실측/합성 구별 [ ] baseline 보존 [ ] 기본 off [ ] 독립 잔차 [ ] validated 수동 변경 없음.
