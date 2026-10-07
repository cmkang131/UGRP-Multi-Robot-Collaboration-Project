# explore12 결과 — 대기 정지는 수정, 안전 관문 미달로 탐색 트랙 종료

**v8 정지/대기 수정 후 개발32쌍은4/5로 실패했다.** 대기 잔류 이동·새 접촉은0이 됐고
참 B는24→28/32로 늘었지만, 접촉6·잘못된 문2·거짓 후보 통로8이 남는다.
새 확인32쌍 사전 등록/개봉·현실 잡음 실행은 하지 않았다. 추가 튜닝 없이 이 트랙을 종료한다.

## 수정한 경로와 범위

기존 `integer_episode.py:37–42`는2초 관측 대기 전에 `stop`을 이미 보냈다. 누락은
정지 명령 뒤의 적용 경로다: `GridWorld.advance` → `V7CommandOdometry` →
`OwnCamLocalizer.command:193–196`에서 목표 명령만0이 되고, `predict_to:290–300`의
τ=.3s 속도 지연이 직전 `vel`을 계속 적분했다. 이 대기에는 monitor/접촉 콜백도 없었다.

- [v8 평가 어댑터](../2026-10-07-mapfree-collision-monitor/code/integer_episode.py:13)의
  `_ZeroVelocityStop`은 stop/hold/정확한3축0 최종 명령 뒤에 남은 모델 속도를0으로 정리한다.
  같은 포트를 평가용 이동 적분기와 자기 명령 예측기에 연결했다. 시간·pose·공분산을 GT로
  덮어쓰는 수정이 아니며, 비영 명령의 gain/τ/공분산 전파는 기존과 바이트 동일 시험을 통과했다.
- `MonitorActor.wait_command`는10Hz로 zero twist를 기존 monitor에 보내고, 대기 루프도
  contact callback을 서비스한다. planner/frontier는 대기 중 실행하지 않는다.2초 후 새 RGB를
  받은 다음에만 새 controller 명령을 발행하며 기존 source/polygon 필터를 다시 통과한다.
- 옵션은 그대로 **`navigation=public_ros_v8`, 기본 off**다. off 포트는 원 객체를 즉시 반환한다.
  v1–v7 121파일·센서/B·문 후보·footprint·monitor 문턱·예산·채점식은 바꾸지 않았다.
- 이 내부 속도0 처리는 **2D cmd_vel 정지 계약**이다. Nav2가 실물의 감속 거리를0으로
  보장한다는 뜻이 아니다. 공식 문서는0명령에 대한 감속 실측도 요구한다.
  실제 브레이크 모델 적합·MuJoCo·실물 검증으로 보고하지 않는다.

원 Nav2 STOP/invalid-source의0속도, 새 입력마다 재검사, timeout이 양의 속도 재개가 아님을
[원문 줄 대조·라이선스·한계](REFERENCES.md)에 기록했다. 시험 후 사전 등록 `5bdf025b`,
수정/동결·실행 소스 `4f81c20654f374761fe9dd316cb559eda0571176`를 커밋·push했다.
기존 v8 `998d8da6`의 결과와 freeze는 보존했다(예전 실행 재현에는 해당 SHA 사용).

## 같은 개발32쌍 재진단 — 정적/자기 지도 분리

M/N×s1–s8×7701/7702, 각 static/own 총64episode를1회 실행했다. 원래 confirmation
환경 draw split 그대로, 증거 용도만 development다. 완전 관측·GT pose는 기존 oracle 포트뿐이며
자기 지도에는 관측/자기 footprint 외 GT 지도·물체·B 위치를 제공하지 않는다.
두 seed의 oracle 경로가 동일하므로 독립32표본의 확증으로 주장하지 않는다.

|조건|참 B/32(거짓)|직접 관측 coverage 중앙|성공 B 거리 중앙(m)|성공 B 시간 중앙(s)|접촉|잘못된 문/시도|거짓 후보|
|---|---:|---:|---:|---:|---:|---:|---:|
|v8 수정 전 static|32(0)|63.21%|3.638|95.0|0|0/44|6|
|v8 정지 수정 static|32(0)|53.91%|2.965|104.0|0|0/36|14|
|v8 수정 전 frontier|24(0)|71.80%|3.858|137.0|16|0/34|10|
|v8 정지 수정 frontier|28(0)|64.81%|3.510|144.5|6|2/42|8|

coverage 분모는 각조건 전체32건, B 거리·시간은 그 조건 성공 건만이다. 대기 drift를 제거해
경로/관측 위치와 성공 집합도 달라졌으므로 전체 성적 변화를 단순히 “기존14접촉 제거”로 계산하지 않는다.
이번 공통 성공28쌍의 own/static 거리비·시간비 중앙은 **1.1174 / 1.3363**이다.
정적 후보 통로 오인6→14와 frontier 잘못된 문0→2도 그대로 남겼다.

|고정 관문|수정 전|정지 수정|
|---|---|---|
|32쌍 완전성·입력 경계·off/소스|통과|통과|
|참 B≥26/32·거짓0|실패24/32|통과28/32|
|공통 성공 거리/시간비 각각≤2|통과|통과|
|coverage 중앙≥40%|통과|통과|
|접촉/잘못된 문/거짓 후보0·문 시도≥1|실패|실패6/2/8,시도42|
|통과 수|3/5|**4/5 → 중단**|

64episode의 **2,916개 관측 대기·58,320개 대기 tick**에서 모델 속도·누적 이동·pose 변화·새 접촉이
모두 정확히0이었다. 이전 대기 접촉14회→0회. 대기 monitor의55,468회는 source 만료/누락으로
zero 출력,2,852회는 유효 source에 대한 zero 요청 통과다. 행동 중 monitor28,520회는 모두 clear;
새 가까운 장애물 관측이나 안전 개선을 monitor에 가정해 넣지 않았다.
[검산](results/stop-verification.json), [관문](results/gate.json), [64건 CSV](results/episodes.csv).

## 기존 거짓 통로10회·행동 접촉2회: 원인 표만, 추가 수정 없음

전체 건별 시각·후보·셀·관측·발행 명령은 [12사건 표](results/prior-events.md)와
[원장 JSON](results/prior-events.json)에 있다. 저장된 자기 관측/명령으로 costmap을 재구성하고
별도 평가에서만 실제 기하와 대조했다. 정책/경로를 다시 실행해 더 나은 후보를 선택하지 않았다.

|기존 사례(각 seed7701/7702)|사건 시각(s)|건수|원인/확인 사실|
|---|---|---:|---|
|s1/M 거짓 후보|146.2,152.0|4|모두 free_connection_unknown. 후보 중심은 free/벽 각2, authored passage 중심 거리.301/.378m|
|s3/N 거짓 후보|122.8|2|free_connection_unknown, 후보 중심 벽254, authored 중심 거리.353m|
|s4/N 거짓 후보|80.9|2|free_connection_unknown, 후보 중심 벽254, authored 중심 거리1.114m|
|s5/M 거짓 후보|101.3|2|free_connection_unknown, 후보 중심 free0, authored 중심 거리.329m|
|s5/M 행동 접촉|107.25|2|wall_divider_1. 최근 카메라79점 중 해당 벽0, 가장 가까운 endpoint3.246m. monitor clear/TTC−1|

거짓 후보10건 모두 실제 발행 중심선9표본은 free이고 짧은 실제 footprint sweep 접촉은 없었다.
후보 중심 자체는6건 wall254,4건 free0이다. scorer는 후보.3m 접근과 authored passage 중심
불일치를 센다. 따라서 이10회를 실제 벽 통과/충돌10회라고 부르지 않으며, .3m나 문 판정도 바꾸지 않았다.

행동 접촉2건은 기존 대기 접촉 뒤 재출발한107.2s의 forward 요청(.12m/s)에서 생겼다.
해당 command 직전 모델 전진속도는−.0181m/s, yaw-rate−.07585rad/s인데 새 요청 yaw-rate는
+.27166rad/s였다. 실제 제안 pose가 벽과 겹쳤고 원 명령의 짧은 sweep도 벽과 겹친다.
재구성된 중심선/제안 footprint36칸은 모두 free, 해당 근거리 벽은 카메라 점에 없었다.
**근거리 관측·footprint 격자와 활성 주행 응답의 한계**로 기록하며, 그 기여율을 단정하지 않는다.
두 사건에 맞춘 회복/지도/문/monitor 설정 변경은 하지 않았다.

## 정지 수정 후 남은 실패

- B 미확인4건: s4/M·N 각2. 모두 B 가시·검출0,167/179s에 frontier 소진/blacklist로 종료.
  시간/거리 예산 조정이나 후보 크기·gain 재튜닝 없음.
- 접촉6건: s1/M 각1(176.9s), s5/M 각2(131.95/134.1s), 모두 행동 중 wall_divider_1.
  대기 잔류 접촉은0이다. 기존14/2 사건과 위치/경로가 달라 같은 사건의 단순 차감으로 보고하지 않는다.
- 거짓 후보8건: s5/M 각3, s8/N 각1. 잘못된 문2건도 남았다. 안전 관문 미달 그대로다.

[새 실패 원장](results/failures.json). 이상의 실패를 보고 소스/설정을 다시 바꾸지 않았다.

## v5–v8 전체 기록 (코호트/조건 합산 금지)

|버전|코호트/조건|B 참/분모(거짓)|coverage 중앙|접촉|잘못된 문|거짓 후보|관문|
|---|---|---:|---:|---:|---:|---:|---|
|v5|I/J5701–5702 확인 / static oracle|32/32 (0)|51.13%|0|0|2|정적 선행32/32≥30/32|
|v5|K/L6701–6702 확인 / frontier oracle|0/32 (0)|17.25%|0|0|0|1/5|
|v6|K/L32 첫 관측 개발 / 연결 진단만|미측정|미측정|미측정|미측정|미측정|유효 경로0/32; 임무 미실행|
|v7|M/N7701–7702 확인→개발 / frontier oracle|26/32 (0)|70.11%|2|0|14|4/5|
|v8 수정 전|동일 M/N32 개발 / frontier oracle|24/32 (0)|71.80%|16|0|10|3/5|
|v8 정지 수정|동일 M/N32 개발 재진단 / frontier oracle|28/32 (0)|64.81%|6|2|8|4/5|

v6는 연결 성분만 복구하고 짧은 footprint 연결에서 막혔다. 임무를 실행하지 않았으므로
B/접촉을0으로 채우지 않았다. [기계 판독 표](results/v5-v8.json), [생성된 표](results/v5-v8.md).

## 검증·보존

관련 시험3파일 **13개 통과**: 기존 residual 반례,0명령 불변 pose/속도, 비영 명령 원 적분 동일,
monitor timeout/STOP/새 안전 입력 재개, 대기 중 planner 미실행, 실제2D world/pose bridge 배선,
off bytes·v7 121파일·공개 원본 해시. 새 실행150파일 freeze를 시작/종료와 결과 집계 때 재확인했다.
64개 result·707개 raw파일 SHA256/합계 **186,973,389bytes**를 보존한다.
원본은 `/Users/changmin/projects/ugrp/outputs/mapfree-v8-stop/development`, 원격 raw 백업 주장은 하지 않는다.

MuJoCo·렌더·모델 호출·새 라이브러리 설치0, wall-time 성능 비교0, 자기 ugrp_session 종료.
새 확인쌍/잡음/추가 튜닝0. 다른 worktree와 미추적4파일 보존, PR #409 DRAFT·병합/강제 push/reset0.
TensorBoard는 이전 사용자 생략 지시를 유지했다. 이번 결과로 **탐색 평가기 트랙을 종료**한다.
