# 바닥 경계 벽 검출기 독립 관문 (PR #405)

## 구현 전 사전 등록

시작 SHA `28263ad5`, 브랜치 `claude/ego-wall-map`. [egomap9 §23](../2026-10-05-ego-wall-map-probe/README.md#23-v7카메라-v3-재검증--inverse_sensor_v1-사전-등록-2026-10-07)의
현행 confidence 지도 precision3.8–13.4%, GT 차체 자세에서도0–16.6%를 그대로 보존한다.
이는 **누적 지도** 수치이며 아래 프레임 검출기 precision으로 치환하지 않는다.
GT 차체 자세를 써도 고정 카메라 보정/실제 팔 자세 차이는 남는다. 벽 경계 픽셀과 투영 오차를 분리한다.

[조사·선택](REFERENCES.md): Ulrich–Nourbakhsh 2000 §4 single-frame HSI histogram floor segmentation,
§3의 열별 최하단 obstacle 접점+평면 투영을 독립 구현한다. DBN/원 저자 공개 코드 이식으로 주장하지 않는다.
새 `wall_detector=floor_boundary_v1`, 기본 off는 egomap9의 기존 검출기/출력 bytes 그대로다.
v1/v2/prob/RBPF/graph/confidence와 카메라 보정은 변경하지 않는다. 실험 중 계수 재튜닝 없음.

### 평가 자료와 정답 경계

- s1042/1043 개발, s1044–1047 확인 재생. 모두 이미 본 v7·카메라 v3 녹화이며 새 독립 연구 확증이 아니다.
- egomap9와 동일한 매2프레임·명령 정착·등록된 무하중21자세만 사용한다. 관측 보류도 전체 분모와 함께 기록.
- 모든 유효 프레임에서 예측을 먼저 저장한 뒤 GT 차체 pose/벽 지도만 평가기로 읽어 검출 점의
  벽 경계 거리≤.15 m precision, RMSE, 프레임별 및 거리[0,2),[2,3),[3,4] m를 기록한다.
- 현 녹화에 실제 카메라 transform/관절 GT가 없어 기하 FOV를 실제 가시 recall이라고 부르지 않는다.
  각 녹화의 유효 frame 목록에서 시간순 **6개 중앙 분위점** `floor((k+.5)*N/6)`, k=0..5를 먼저 고정한다.
  총36프레임을 undistort한 RGB만 보고 바닥–벽 접촉선의 polyline을 수동 주석한다. 예측 결과는 표시하지 않는다.
  보이는 물체/로봇/색 바닥은 벽이 아니다. 가린 부분은 선을 연결하지 않는다. 모호한 구간은 ignore로 표시·집계한다.
  주석·샘플 frame/SHA를 검출기 구현 전에 봉인한다. 확인 영상 주석을 임계값 학습에 쓰지 않는다.
- 96개 고정 열에서 주석 선과의 행 차이≤3 px로 pixel precision/recall을 계산한다.
  주석 접점을 같은 고정 보정으로 투영해 거리 구간을 나누고, GT 자세+실제 벽까지≤.15 m인
  예측을 metric TP로 센다. 주석 없는 열의 예측은 FP다(ignore 제외). metric recall 분모는 보이는 주석 접점이다.
  픽셀 정답과 nominal projection 기반 거리 구간의 한계를 분리해 기록한다. 전체349벽 recall로 대체하지 않는다.
- 기존 검출기의 동일 평가 수치를 먼저 기록·커밋하고 새 검출기를 구현한다. 무검출 precision은 NA,
  양성 주석이 있으면 recall0이다. 빈 출력으로 precision 관문을 통과할 수 없다.

### 고정 검출기 관문 (기존 지도 §17·§19는 그대로)

확인4건 **각각** 아래를 모두 충족해야 후속 지도 재생을 허용한다. 합산으로 실패를 덮지 않는다.
1. 전체 유효 프레임의 point precision≥90%, 주석 frame의 metric precision≥90% 및 recall≥70%.
2. 주석 frame pixel precision≥90%, recall≥70%. 기존 검출기보다 metric/pixel precision 비감소.
3. 주석 유효 벽 접점≥50개·metric TP≥30개/녹화. [0,2),[2,3),[3,4] m 각 구간의
   precision/recall/표본 수를 그대로 공개(빈 구간 NA, 개별 구간을 합산 수치로 숨기지 않음).
4. off 골든 bytes 동일, behind-camera 교점0, detector로 GT/타 로봇 지도 유입0.

기준 미달/자료 부족은 FAIL/NOT_ESTIMABLE로 중단하며 임계값·관문을 바꾸지 않는다.
통과할 때만 고정된 RBPF100+positive_depth+pose_graph+wall_confidence로 s1042–1047을 재생하고
기존 회색 GT벽/점유 신뢰도 음영/경로 2D 그림을 갱신한다. 실패면 기존 지도 그림을 새 결과처럼 바꾸지 않는다.

### 실행·보존

오프라인 RGB/로그 분석만 예정, 새 물리/렌더/모델 호출 없음. 새 물리가 필요하면 별도 사전 등록·agent_lock·
ugrp_session·한 번에 하나·freeze금지를 따른다. 이번에 관측 부족을 이유로 자동 새 실행을 시작하지 않는다.
시험은 변경 모듈1–3개·off golden. 통과 뒤에만 커밋, 모든 메시지에 Codex trailer.
raw는 `/Users/changmin/projects/ugrp/outputs/wall-floor-boundary-v1/`, 기존 원본은 읽기 전용.
1 MiB 이하 표/그림/manifest만 실험에 남긴다. ENOSPC=HOST_ERROR, 같은 원인 두 번 막히면 중단.
PR #405 DRAFT 유지·병합 없음, 다른 worktree 수정 없음. TensorBoard는 기존 사용자 결정대로 생략한다.

## 기존 검출기 기준값 (새 검출기 구현 전 봉인)

주석·평가기 `bf567b19`, 사전 등록 `dd8fb5dc`. 3,469 유효 프레임에서 96열의 **연결 전 primary 접점**을
양의 깊이·4 m로 제한했다. egomap9의 연결 후 누적 지도 수치와 다르다. 주석36프레임은 단일 Codex 시각 주석이며
전문가 독립 라벨/실제 camera GT가 아니다. 문틈의 모호한 원거리 접점은 열 단위 ignore로 집계했다.

|자료|유효 frame|전체 접점 P|주석 pixel P/R|주석 metric P/R|전체 접점 RMSE m|수동 주석 투영 오차 중앙 m|
|---|---:|---:|---:|---:|---:|---:|
|s1042 개발|863|10.34%|96.4/93.1%|9.2/8.9%|0.487|0.525|
|s1043 개발|586|0.00%|95.8/88.4%|0.0/0.0%|0.586|0.484|
|s1044 확인 재생|736|0.00%|94.3/85.1%|0.0/0.0%|0.580|0.515|
|s1045 확인 재생|558|6.97%|96.8/88.4%|1.7/1.6%|0.520|0.457|
|s1046 확인 재생|351|2.17%|98.8/88.4%|0.0/0.0%|0.606|0.620|
|s1047 확인 재생|375|1.50%|97.3/90.2%|0.0/0.0%|0.601|0.665|

**새롭게 확인한 한계:** 선택된 주석 frame에서는 기존 검출기의 픽셀 경계가 대체로 맞는데 투영이 어긋난다.
검출기와 독립적으로 주석 접점을 투영해도 중앙0.457–0.665 m 오차가 남는다. GT **차체** 자세만으로
카메라 extrinsic/실제 팔 자세/캘리브레이션 적용/scene-map 정합 오차까지 없어진다고 볼 수 없다.
따라서 egomap9의 낮은 GT 지도 precision만으로 병목을 색 경계 검출 하나로 확정하지 않는다.
이 결과로 카메라 계수를 피팅하거나 주석·사전 기준을 바꾸지 않고, 예정된 방법을 평가한다.
전체 프레임의 실제 pixel recall은 미주석이므로 NA, 주석 subset 수치와 혼합하지 않는다.

원시 예측·프레임별 채점은 `outputs/wall-floor-boundary-v1/off/s104*/`(primary checkout),
Git 보존 요약은 [results/off](results/off). 각 JSON에 거리별 P/R·분모·ignore·입력/정답/주석 해시를 보존했다.
기존 예측 hash를 확인한 다음에만 평가용 trajectory/static_map/주석을 열었다.
시험: `test_wall_detector_evaluation.py` 3개 + 기존 `test_wall_confidence.py` 13개 통과.
