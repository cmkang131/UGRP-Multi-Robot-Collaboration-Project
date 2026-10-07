# egomap22 — 자기 RGB 폐루프 frontier / active SLAM (사전 등록)

2026-10-07 사용자 결정: egomap21 고정 경로 0/2 이후 경로를 미리 작성하지 않는다.
PR #405 DRAFT. PR #409 CI 수리는 별도 worktree/커밋 `ed2fa0e9`이며 탐색 결과와 합산하지 않는다.
이 문서는 구현 및 신규 물리 실행 전에 커밋한다. 구 경로 자료는 개발 근거이며 확증 자료가 아니다.

## 고정 구성·입력

- `active_mapping=frontier_rbpf_v1`, `active_loop=information_gain_v1` (각 기본 off).
- PR #409 `ed2fa0e9`의 public_ros_v8 / NavFn / explore_lite / collision monitor를 원본 그대로 복사하고 SHA를 보존한다.
- r3 자기 RGB, K/D, 자기 서보/이동 명령만 입력. 출발 자세는 자기 (0,0,0).
  정적 지도·목적지 위치·시뮬 관절/pose·접촉은 정책 입력 금지. 평가는 별도 파일에만 기록한다.
- RBPF100 + positive_depth + own_submap + switchable_v1 + inverse_sensor_v1 + tsdf_weight_v1 + s2_pulse_v122.
  기존 detector/FK/모션 계수/graph/신뢰도 문턱은 바꾸지 않는다. TSDF support는 정답 벽 확률이 아니다.
- 전역 graph는 10 SIM s마다 정지 중 갱신. map→odom 변환을 따로 두며 DR/입자를 정답으로 보정하지 않는다.
- 좁은 FOV: 자기 RGB의 기존 벽 접점/바닥 색 마스크를 투영하고 v8 Bresenham free ray + footprint clearing.
  끝없는 미관측 공간을 free로 만들지 않는다. B는 고정 floor_color_v3 규칙을 새 명령 FK에 연결한다.
- 연속 NavFn 추종 속도는 v122의 유효한 단축 펄스로 양자화한다. 매 펄스 후 새 RGB로 다시 판단한다.
  모션 재적합 금지. 관측 대기에는 0 명령. dev_light 보수적 경고는 기록, 실제 벽 접촉/기울기/실행 오류는 종료.

## 표준 방법과 필요한 변경

[Stachniss/Grisetti/Burgard RSS2005](https://www.roboticsproceedings.org/rss01/p09.pdf)의
RBPF 지도·궤적 entropy 감소와 이동 비용을 비교한다. 후보는 frontier 경로와 과거 위치 재방문 경로다.
가중치로 입자 하나를 뽑아 자기 지도에서 가상 관측을 만들고 RBPF 복사본에 넣는다.
미관측 ray의 기대 map entropy 감소는 새 칸 수로 근사한다. 자세 entropy는 방문 장소별 평균이다.
효용은 정보 이득 − α × 경로 비용이다. 실제 로봇/지도는 가상 관측으로 갱신하지 않는다.
필요 변경: lidar 대신 카메라 FOV 54.5°/4 m, 후보 frontier 최대 2 + 재방문 최대 2,
가상 관측 간격 0.5 m, 결정 주기 10 s, α=0.35 고정. 불확실성 σXY≥0.15 m 또는 σyaw≥5°일 때 재방문 후보를 추가한다.
원 논문에 없는 계산 예산/카메라 제한값이며 이번 결과로 재튜닝하지 않는다.

## 옵션 (기본은 기존 동작)

| 옵션 | on | off |
|---|---|---|
| active_mapping | frontier_rbpf_v1 | 기존 실행 경로 |
| active_loop | information_gain_v1 | v8 frontier 선택 그대로 |
| wall_texture | photo_v1 / speckle_v1 | 기존 장면 문자열 그대로 |
| camera_pose | look_ahead_v1 | 기존 SEARCH/보정 유지 |

photo_v1은 ambientCG [PaintedPlaster017](https://ambientcg.com/view?id=PaintedPlaster017)
Surface Photogrammetry 컬러 사진, [CC0](https://docs.ambientcg.com/license/). 절차 생성 재질과 구분한다.
speckle_v1은 DIC 비반복·등방·대비 원칙의 고정 seed 다중 크기 점무늬다.
실물 벽은 아직 없으며 인쇄 가능 재질을 사용자가 선택하도록 허용했다. 실물 재현 확인 주장이 아니다.
look_ahead_v1은 마운트/FOV 변경 없이 손목 명령만 바꿔 명령 FK pitch −7.5°를 목표로 한다.
real_v1 강성에서 실제 pitch 오차는 평가 전용으로 재측정한다. S2 파일/보정표는 수정하지 않는다.

## 실행 순서·예산 (결과 전 고정)

1. 이 사전 등록을 관련 골든 시험 통과 후 커밋.
2. 원본 이식/own-only/기본 off bytes/entropy 선택/좌표·펄스 어댑터 오프라인 시험.
3. 소스 커밋·push 후 agent_lock null일 때만 정적 자세 8 SIM s 1회: SEARCH→look_ahead.
4. 정착 마지막 1 s의 look_ahead 절대 pitch 오차 중앙 ≤0.3°, p95 ≤0.5°이면 DEV 2건.
   실패하면 물리를 추가하지 않고 기록. `photo` seed22001 / `speckle` seed22002,
   각 180 SIM s, r3 시작 (3.25,0.75,π)는 setup 전용. 둘 다 look_ahead + active_loop on.
   경로·벽/문 목적점은 지정하지 않는다. 재질/seed가 달라 우열 비교나 통계 확증으로 합산하지 않는다.
5. 각 실행은 ugrp_session + 표준 workflow, 락 하나, freeze/모델 호출 없음.
   로컬 예상 wall 예산 최대 30분/건(초과 시 HOST_BUDGET으로 기록); raw 예상 500 MiB/건 이하.
   ENOSPC는 HOST_ERROR. 다른 프로세스 종료/우선순위 변경 금지.

## 판정·분모 (사전 고정)

- 회귀 관문: 기본 off JSON/XML bytes 동일, GT/peer 입력 거부, 원본 v8 파일 해시 일치.
- 물리 DEV 통합 관문: 180 s 예산 종료 또는 자기 B 확인 후 도착, 벽 접촉 0,
  잘못된 문 통과 시도 0, 실제 주행 거리 ≥3 m, 실제 footprint union 면적 ≥0.75 m²,
  평가상 관측 가능 벽 표본 ≥50개(벽 표본 0.1 m 간격).
- 지도: 기존 전체 벽 P/R/덮임/RMSE + 실제 지나간 경로에서 카메라에 가시였던 벽 recall,
  해당 범위 map precision 및 분자/분모, 가시 벽 길이·전체 비율을 별도로 보고.
  영역 P≥0.70, R≥0.50, 벽 RMSE≤0.15 m, 경로 RMSE≤0.25 m를 모두 충족해야 통합 통과.
  기존 §17·§19 기준은 변경하지 않고 별도 보존한다. 새 DEV 기준으로 과거 통과를 재명명하지 않는다.
- B 첫 확인·GT 실제 도착은 구분. B 미도달도 기록하되 180 s 탐색 완주와 같지 않다.
  접촉은 GT 평가 전용, 잘못된 문은 선택 경로가 GT 벽/너비에 막힌 횟수(연속 같은 시도 1건).
- ECE는 기존 occupancy의 진단값만, TSDF는 support-score calibration gap 명시.
  작은 표본은 판정 미달: P만 높아도 통과하지 않는다. 결과 후 문턱 수정/재실행 튜닝 없음.

## 상태

사전 등록. 구현/오프라인/새 물리 결과 없음. TensorBoard 변환은 사용자 앞선 생략 지시 유지.
raw: `/Users/changmin/projects/ugrp/outputs/active-wall-map-v1/`.

## 구현 전/오프라인 검증 기록

사전 등록 `85bc483d`(기존 pulse/강성 8시험 통과). 새3파일 21시험 통과: off bytes,
94파일 원본 일치, FK 축, 유효 펄스/정지, 정보예측 복사본 격리, own-only, NavFn frontier 연결.
첫 시험의 Python proxy deepcopy 재귀와 DoorMemory 인자 누락2개는 오프라인에서 수정했다.
RGB 기존 SEARCH 영상1장을4시점 반복한 API smoke는 graph2회·information2회를 실행했다.
이 smoke는 프레임 합성 시점/비실행 명령이라 새로운 탐색/지도 품질 근거가 아니다(`offline-acceptance.json`).

[출처와 명시적 어댑터 차이](REFERENCES.md), [인쇄 자료 전체 해시](prints.json).
두 재질24면씩과 미터 단위 배치표는 raw `prints/`에 보관(사진1.60MB, speckle3.88MB).
일반 로컬 실행 환경을 재사용하며 새 라이브러리/venv 없음. C++ 바이너리는 소스 해시로 로컬 빌드.
