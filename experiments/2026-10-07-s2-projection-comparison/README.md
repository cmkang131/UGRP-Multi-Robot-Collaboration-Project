# egomap12 — PR #406 투영 경로 동일 프레임 비교

## 계산 전 사전 등록 (2026-10-07)

PR #405 시작 `675ca181`, 작업 `claude/ego-wall-map`. PR #406은 사용자가 지정한
`dc65cf6f`의 Git blob만 읽으며 그 파일·worktree는 수정하지 않는다. 새 튜닝/물리/렌더/모델 호출0.
`floor_boundary_v1` 및 `servo_fk_v1`의 실패 결과는 보존한다.

1. s1045–1047의 egomap11과 같은 무하중 정착 프레임·봉인 수동 접점으로 비교한다.
   #405의 기존21자세 PnP 표와 #406의 `s2_camera_v3_unloaded_sag_v1.json`,
   `approximate` → `camera_record`/`floor_camera` → pan yaw → `measured_column_model`을 대조한다.
   원문 함수는 고정 ref에서 보존하고 수치 본문을 바꾸지 않는다. 자기 명령과 고정 표만으로
   카메라 예측을 먼저 저장·해시한 뒤 GT 차체/실제 카메라/벽을 평가기에만 연다.
2. 원36프레임·96열·ignore·baseline 양의 깊이 및4m 분모를 유지한다. 동일 프레임의
   camera xyz/yaw/pitch/roll, 접점 오차 중앙/P90/RMSE, 두 경로 차이를 기록한다.
   s1042/1043 개발→무튜닝 동결→s1044–1047 확인 재생 순서를 지키며, 이미 본 자료를 새 확증으로 부르지 않는다.
3. 기존 egomap11 관문을 변경하지 않는다: **각6건** 고정 점≥50, 양의 깊이100%, 4m 유효율≥95%,
   중앙≤0.10m, P90≤0.25m, baseline 중앙 비악화, 뒤 교점0, off bytes 동일, GT 입력0.
   실패해도 분모를 운반/HIGH 프레임으로 바꾸거나 loaded 처짐을 무하중에 적용하지 않는다.
4. s1045–1047의 HIGH 명령 그룹과 s1050의 real_delivery 명령·저장 감사 결과를 별도로 비교한다.
   HIGH에는 두 고정 표의 unloaded/loaded 기하를 평가용으로 함께 기록한다. 실제 하중을 GT로
   분류하거나 운반 결과를 무하중 관문에 합산하지 않는다. 카메라 자세 차이와 관측 거리 차이를 구분한다.
5. #406 경로가 같은 프레임에서 위 관문을 통과할 때만 기본-off `camera_pose=s2_projection_v1`을
   런타임에 연결한다. 실패하면 평가 전용 비교로 끝내고 미검증 옵션을 등록하지 않는다.
   **6건 통과 시에만** RBPF100+positive_depth+pose_graph+wall_confidence 재생 및 누적 지도 그림 갱신.
   §17·§19 기준 유지. 실패 시 원인/경로별 줄 번호를 남기고 추가 보정·튜닝 중단.

raw `/Users/changmin/projects/ugrp/outputs/s2-projection-comparison-v1/`에 새로 저장한다.
기존 raw/미추적4파일 보존, ENOSPC=HOST_ERROR. source·table·입력·결과 해시 기록.
시험 통과 확인 뒤 commit/push, Codex trailer, PR #405 DRAFT 유지·병합 없음.
의존성 추가/venv 변경 없음. TensorBoard 변환은 기존 사용자 결정대로 생략하고 Drive는 사용하지 않는다.
