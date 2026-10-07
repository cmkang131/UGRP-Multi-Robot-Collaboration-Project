# explore11 — public_ros_v8 원본 설정 이식 (구현 전 사전 등록)

2026-10-07 사용자 요청. PR #409, `claude/mapfree-explore`. MuJoCo·렌더·모델 호출 없음.
v7 M/N32 결과(`648bc227`, 실행 `66a5fe94`)는 수정하지 않고 **이번 개발에만** 사용한다.
기존 off·v1–v7 및 B floor_color_v3 소스/문턱은 보존한다. GT는 평가 및 명시적 oracle
자세 포트에만 있고 own frontier에 지도·물체·B 정답을 전달하지 않는다.

## 수정 전 진단 (저장 로그만 재검산)

[v7 건별 기록](results/v7-event-diagnosis.json), [예산 출처](results/s2-budget-source.json).

|문제|건별 원인/수치|
|---|---|
|충돌2|s3/M, seed7701·7702,257.3s, wall_divider_1. 발행 경로 중심선9표본 모두 raw free(0), 다음 footprint38칸 모두 free, 실제 벽 중심표본1칸도 free. unknown 진입으로 설명되지 않는다. 관측 나이 .2s, 벽점77개. 카메라 밖/격자·footprint clearing 문제와 검출점을 직접 쓰는 monitor를 구분한다.|
|거짓 통로14|s4/N4,s5/M4,s8/M6. 모두 짧은 실제 이동의 벽 접촉0, 중심선9표본 모두 free. s4/s5 후보는 `free_connection_unknown`, s8은 `clearance_feasible`. 기존 채점은 authored passage 중심 .3m 이내 일치 없이 검출 gap에 .3m 접근하면 센다. 실제 막힌 벽 통과14회라는 뜻이 아니다. 기준/분모는 변경하지 않는다.|
|frontier 소진4|s4/M2: 마지막1개(blacklist), s4/N2: 마지막23개 모두11 blacklist 범위 안. B까지 최소 카메라 거리2.923/2.822m, 투영 FOV 안 최대1425/1133표본이나 가림 뒤0. 사거리4m 초과만의 문제가 아니다.|
|B 시간 경계2|s3/M,20/20 참 관측인데19track,최대2view. 3.0000000000002274s 차이가 3s 상한을 넘겨15회 track 단절/실행. 종료317s로900s 예산 소진 아님.|

s1050/s1051 실제 저장 실행은260.10/264.35 SIM s(성공 인수 아님). 기존900 modeled s는
이 시간보다 짧지 않고 S2 v106 `CAP_S=900`과 같다. 따라서 **900s/40m/300관측 유지**.
2D 시간은 물리 실행 시간/실물 성공으로 해석하지 않는다.

## 변경 범위와 원본값 (새 옵션 기본 off)

|옵션/항목|v7|v8 사전 고정|
|---|---|---|
|`navigation=off`|기존 출력|동일 bytes, 호출/컴파일도 하지 않음|
|`public_ros_v7`|기존 결과|원 소스121파일 hash 보존|
|`public_ros_v8`|없음|아래 원본 기본값 포트만 적용|
|collision monitor|없음|Nav2 bringup FootprintApproach: 현재 padded footprint(.28×.24m), TTC1.2s, dt.1s, min_points6|
|source timeout/base shift|없음|1s/true; 자기 카메라 wall endpoints만, own odom으로 최신 body 좌표 이동, 입력 누락/지연이면 정지|
|재계획|1Hz|이미 원본 BT1Hz, 유지|
|costmap 갱신|10Hz|Nav2 local5Hz; 한 장 지도 어댑터이므로 planner도 이 최신 지도 사용(별도 global1Hz 복제 없음)|
|explore_lite 설정|potential1/gain1/min.1m|배포 explore.launch 그대로3/1/.75m, planner_frequency .33Hz, progress_timeout30s|
|frontier callback|실패 후 다음 후보|원 abort/blacklist lifecycle 유지; .33Hz timer와 별개로 abort 뒤 즉시 재탐색|
|평가 clock|float +=.1|정수100ms tick→초 변환. ROS sec/nanosec 방식, B의3s 문턱 수정 없음(별도 평가 어댑터 커밋)|

코드 fallback 기본값과 배포 launch 기본값은 다르다. coherent 배포 launch를 선택했으며
실패 결과를 보고 값을 선택하지 않는다. narrow-FOV 카메라는 Nav2의 일반 LiDAR와 다르다.
관측하지 않은 벽·GT 장애물을 monitor에 채워 넣거나 min_points6을 낮추지 않는다.
원문·라이선스·줄 대조는 [REFERENCES](REFERENCES.md). ROS executor/TF/topic 대신 기존
순수2D own-observation 포트/own odom을 쓰며 controller10Hz, 2s관측+1s행동은 그대로다.

## 고정 관문·진행 순서

기존 §17의 다섯 기준/분모를 **변경하지 않는다**:
1. 완전한32쌍·경계/소스 hash·off bytes 검사.
2. frontier 참 B≥26/32, 거짓 B=0.
3. 공통 성공쌍의 이동거리/시간 비율 중앙값 각각≤2 (공통0이면 실패).
4. 직접 관측 탐색 coverage 중앙값≥40%.
5. frontier 충돌=0, 잘못된 문=0, 거짓 후보 통로=0, 실제 문 시도≥1.

구현 전 이 문서 커밋 → 단위 시험 → 소스/설정 커밋·push/동결 → 이미 본 **M/N×s1–s8×7701/7702
32쌍 개발**(각 static/own,64episode) 한 번. seed별 oracle 궤적 중복은 독립32표본이라 주장하지 않는다.
**개발5/5일 때만** 기존 모든 cohort와 좌표/ID 중복을 검사한 새32쌍을 사전 등록·커밋하고
frontier oracle(같은 정적 비교분모) 한 번. 그 관문5/5일 때만 S2 실측 잡음+ B recall79% 단계.
실패하면 추가 튜닝·새 확인·현실 잡음 실행 없이 원인과 원 결과를 기록하고 멈춘다.

개발 raw: `/Users/changmin/projects/ugrp/outputs/mapfree-monitor-v8/development`.
`ugrp_session`으로 유한 CPU 작업만 실행, wall 시간 성능 비교 없음(물리 잠금 불필요).
ENOSPC는 HOST_ERROR이며 실패 분모에서 제외하지 않는다. raw 보존, 작은 그림/표/hash만 Git.
커밋은 시험 통과 뒤 Co-Authored-By: Codex. PR #409 DRAFT 유지, 병합하지 않는다.
TensorBoard 변환은 사용자의 앞선 생략 지시를 유지한다.
