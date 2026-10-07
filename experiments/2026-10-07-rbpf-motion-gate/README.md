# egomap23 — RBPF 갱신 관문 / tape·SEARCH 폐루프 1회 (사전 등록)

2026-10-07 사용자 요청: 범위를 줄인다. egomap22 자료 진단 후 기본 off 옵션 하나,
tape_v1 + 기존 SEARCH + frontier_rbpf_v1 물리 DEV **1회만**. 재질/자세 비교 없음.
기존 사용자 파일4개·PR406·egomap22 원본은 수정하지 않는다. DRAFT, TensorBoard 생략 유지.

## 오프라인 원인 (구 자료, 평가·튜닝 자료로만)

|egomap22|정합/재표본|정지 정합/재표본|초기 조상100→|마지막 서로 다른 XY(1mm)|σXY 처음→끝 m|
|---|---:|---:|---:|---:|---:|
|photo|24/14|0/0|1 (t17.1)|85|.10169→.00644|
|speckle|137/32|128/28|1 (t134.7)|13|.10238→.00150|

[진단과 입력 해시](results/egomap22-audit.json), `code/audit.py`.
Neff<100/2 조건은 이미 정확히 적용됐다. 마지막 Neff71.63/68.11은 재표본 후
균등화 때문에 계보 다양성을 보증하지 않는다. 조상1개도 현재 pose가 모두 동일하다는 뜻은 아니다.
photo는 이동 중에도 붕괴했으므로 정지 중복만으로 모든 오차를 설명하지 않는다.
모션은 v122 고정 표(2245bb9f…)이며 Q가 0인 정지는 올바른 동작이다. 누적 명령 Q 대각합은
photo [.000168,.000679,.005537], speckle [.000033,.000124,.001000] (m²,m²,rad²).
이를 반복 관측 likelihood가 줄이고 재표본화가 계보를 제거했다. 모델 평균 편향·오정합은
이 Q가 표현하지 못할 수 있다. GT로 잡음을 맞추거나 임의 noise floor를 넣지 않는다.
첫 감사 JSON에 numpy 정수 직렬화 오류1회, Python scalar 변환으로 저장만 수정했다.

## 표준 적용 / 옵션 (구현 전에 고정)

`rbpf_update=gmapping_motion_v1`, 기본 `off`.
[Grisetti et al. TRO2007](https://people.eecs.berkeley.edu/~pabbeel/cs287-fa13/optreadings/GrisettiStachnissBurgard_gMapping_T-RO2006.pdf)
§III-C의 Neff<N/2 선택적 재표본화·기존 improved proposal은 유지한다.
[OpenSLAM processScan](https://github.com/ros-perception/openslam_gmapping/blob/master/gridfastslam/gridslamprocessor.cpp#L338-L366)의
누적 병진/절대 회전 및 first-scan 조건을 적용한다.
[ROS slam_gmapping 기본값](https://github.com/ros-perception/slam_gmapping/blob/melodic-devel/gmapping/src/slam_gmapping.cpp#L213-L220)
그대로 **linearUpdate=1.0m, angularUpdate=.5rad, temporalUpdate=-1, resampleThreshold=.5**.
이동 정보만 자기 명령 DR로 대체한다. 표준식 재구현, 원본 코드 복사/새 의존성 없음
(OpenSLAM BSD 계열, ROS wrapper BSD-3). 원문은 이번에 열어 확인했다.

첫 유효 scan 또는 누적 DR 거리≥1m 또는 |회전| 합≥.5rad일 때만 RBPF 관측·정합·지도 삽입.
나머지는 명령 예측/공분산 전파만 하며 RNG·입자 가중·지도는 갱신하지 않는다.
frontier의 현재 RGB free/장애물 안전 관측은 계속 사용한다. 범용 lidar 전체를 대체했다고 주장하지 않는다.
GT로 gate를 판단하지 않고 기존 settle/range/peer/중복 검사도 유지한다.
확인: off bytes 동일, 정지 반복으로 covariance/RNG/지도 불변, 회전·병진 관문,
Neff 선택적 재표본화 기존 시험. egomap22 same-input on frontend 오프라인 재생만 추가.
그 결과로 문턱을 바꾸지 않는다. graph/모션/검출기/active-loop 조건은 egomap22 그대로.

## 물리 1회 / 판정

- 소스 커밋·push 및 오프라인 시험 후 lock null일 때만 ugrp_session/표준 workflow.
- seed22001, setup 시작[3.25,.75,π], r3 단독 자기 RGB/명령. 경로 지정/GT 제어 없음.
- real_v1 강성 + tape_v1 + SEARCH(PWM3=740) + v122 + RBPF100 + graph + switchable +
  inverse_sensor/TSDF + frontier_rbpf_v1 + information_gain_v1 + gmapping_motion_v1.
- 180 SIM s, wall 최대30분. 실제 접촉/기울기/실행 오류는 종료, dev_light. freeze/모델0.
  중단 때 새 재실행 없이 partial을 보존. 결과 저장은 finally에서 무조건 재정합하지 않고,
  이미 완료한 최종 graph가 있으면 재사용, 없으면 frontend를 별도 표시한다.
- egomap22 기준 유지: P≥.70/R≥.50(실제 경로 FOV 영역), 벽RMSE≤.15/경로RMSE≤.25m,
  거리≥3m/footprint union≥.75m²/가시 벽표본≥50, 접촉·잘못된 문0, 예산 완료 또는 B도착.
  B 확인/GT 도착, 전체 P/R, 노출 분모를 함께 기록. 작은 범위로 성공을 주장하지 않는다.
- raw `/Users/changmin/projects/ugrp/outputs/rbpf-motion-gate-v1/`, 예상≤300MiB;
  ENOSPC=HOST_ERROR. 디스크/잠금 확인, S2 동시 실행 금지. 실패 후 튜닝·두 번째 물리 없음.
