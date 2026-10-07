# egomap36 — 지도 지지 PR 곡선과 고정 운영점

2026-10-08, egomap35 후속. **오프라인만**, 물리/렌더/모델/잠금0.
기존 PR405 브랜치에서 진행하고 다른 작업·worktree·S2 상태는 건드리지 않는다.

## 결과 전 사전 등록

- 개발: seed31001 (`outputs/active-frontier-audit-v1/new-seed`).
  보류: seed32002 (`outputs/wall-segment-dev-v1/new-seed`).
  **32002는 egomap34/35에서 이미 본 녹화다.** 이번 선택 과정에서 보류할 뿐
  미개봉 독립 확증으로 부르지 않는다. 서로 다른 motion model/경로의 기록임도 유지한다.
- 개발 곡선/선택 규칙 커밋 → 개발 결과만으로 두 운영점 선정 → 선택 JSON·README를
  다시 커밋 → 보류용에서 고정된 두 점을 한 번 평가. 보류용 곡선·재선택·재튜닝0.
  raw 결과를 존재 여부 검사로 보호하고, 단계별 supervisor 파일을 확인한다.
- 카메라/검출/자세/삽입 원장/가중치/graph 모두 고정. 격자는 egomap35의 own support
  누적을 재사용한다. 선분은 `segments_v1`의 실제 RGB 열 접점·공분산, split-and-merge,
  CI 병합, 자기 Manhattan 축까지 **원본 그대로**. 파라미터 변경0.

### 후보군과 공통 지지 정의

- 필요 시점수 `N ∈ {1,2,3,4,5,6,7,8}` × 최소 방위 다양성
  `A ∈ {0°,5°,15°,30°,60°}` = 표현마다40점. 이는 결과 전에 정한 유한 비교 격자이며
  공개 라이브러리의 기본값이라고 주장하지 않는다.
- 서로 다른 시점 판정은 egomap35 그대로: 이전 채택 시점 모두와 카메라 위치차≥.1m
  또는 대상점 방위차≥atan2(.1m,min(range)). 같은 카메라 위치의 단순 회전/반복은
  같은 벽점의 독립 시차 지지로 늘리지 않는다.
- 그 채택 시점들의 **최대 쌍별 작은 방위각 차이**를 다양성으로 쓰고,
  `count≥N AND diversity≥A`로 채택한다. 각도는 자기 추정 카메라→대상점 방향이며
  GT/세계 Manhattan 축을 쓰지 않는다. 한 시점의 다양성은0°다.
- 격자 대상점은 셀 중심. free로 지지 초기화하는 v1 원장은 보존한다.
  선분 대상점은 최종 선분 중심, 시점은 frozen `frame_ids`에 해당하는 자기 추정
  카메라 위치다. **선분 전체의 지지이지 각 부분이 N회 보였다는 보장은 아니다.**
  이 비교는 frozen 선분 지도를 필터링하며 선분 재적합·쪼개기·확장0.
- 새 `wall_validation=pr_support_v1`, 기본off; N/A는 명시 입력(추가 기본 운영점 없음).
  이전 `multiview_weight_v1`과 `segments_v1`의 출력·설정은 보존한다.
  off는 입력 객체/JSON bytes 그대로. 이는 지도 출력 옵션이며 제어/RBPF 피드백0.

### 지표와 운영점 선택 — 결과 후 변경 금지

두 표현의 주 지표를 동일한 .1m raster 셀 P, GT 벽329표본 R=덮임, .15m 허용거리로
맞춘다. 선분은 기존처럼 .05m 연속 길이 표본 P/R/RMSE도 보조로 기록한다.
P 분모와 R 분모가 다른 **기하 PR**이며, 이진 분류기의 AP/AUC를 계산하지 않는다.
각 A별 N 곡선·모든 점·표본수를 남기고, 표현별 선택은 다음 순서를 따른다.

1. 비어 있지 않고 **전체 P≥.90인 점 중 전체 R 최대**.
2. 동률이면 P 큰 순 → RMSE 작은 순 → N 작은 순 → A 작은 순.
3. P≥.90인 점이 없으면 **적격 운영점 없음**으로 기록한다. 그래도 사용자 요청의
   보류 재생을 위해 비어 있지 않은 점 중 P 최대 → R 최대 → RMSE 최소 → N/A 최소의
   **기준 미달 진단점** 하나를 고정한다. 빈 지도는 P=NA, 선택 대상에서 제외한다.
4. 두 표현 모두 비어 있으면 해당 표현은 보류 예측 empty로 고정, 기준 미달로 기록한다.

분모/표본수·잠재가시 영역 P/R·전체 P/R·덮임·벽 RMSE·원장 프레임 수를 항상 같이 보고한다.
운영점 선택에 영역 지표나 보류용 GT를 사용하지 않는다. GT는 평가/개발 선택만,
지도 생성 입력에는 금지다. 개발 seed로 문턱을 고른 사실을 숨기지 않는다.

## 보류 판정과 조건부 export

egomap20의 **P≥.90, R≥.70, 벽 RMSE≤.15m** 절대관문은 그대로다.
'가까워지면'은 egomap34에 이미 등록한 정의를 재사용한다: 각 표현의 보류용 off 대비
`[max(0,.9-P), max(0,.7-R), max(0,RMSE-.15)]`가 모두 비증가하고 하나 이상 감소하거나,
세 절대기준을 모두 만족해야 한다. 표본0/NA는 해당하지 않는다.
격자는 raw occupancy, 선분은 필터 없는 frozen segments_v1이 각 off 기준선이다.
어느 표현이라도 이 조건을 만족하면 `wall_export=segments_confidence_v1` 함수 구현에 착수한다.
confidence는 지지수/방위 다양성/공분산 같은 증거이며 calibrated probability로 부르지 않는다.
자기 출발 좌표계·단위·로봇 ID를 필수로 포함하고, 타 로봇 지도 공유/LLM 호출은 하지 않는다.
가까워짐은 export 개발 착수 조건일 뿐 기존 절대관문 통과나 F 실증 성공으로 보고하지 않는다.
미달이면 원인만 기록하고 export를 보류한다.

## 표준 방법과 범위

- [scikit-learn: decision threshold tuning](https://scikit-learn.org/stable/modules/classification_threshold.html)
  §3.3.1: 예측 점수는 고정하고 사전 정의한 지표로 문턱을 선택, 선택 자료와 평가 자료 분리.
  이번에는 시간상관이 있는 프레임을 랜덤 분할하지 않고 녹화 단위로 분리한다.
- [공식 PR 예제](https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html):
  문턱에 따른 P/R trade-off 표시. 이진 confusion matrix 대신 기존 기하 평가를 사용하며
  임의 보간이나 서로 다른 A/표현 사이의 면적 합산은 하지 않는다. scikit-learn 설치0.
- 지지 누적/독립 시점·free reset의 출처 및 이식 차이는
  [egomap35](../2026-10-08-wall-cell-attribution/README.md), 선분 추출/병합의 원본 출처는
  [egomap34](../2026-10-08-wall-segment-dev/README.md) 그대로다.

raw: `/Users/changmin/projects/ugrp/outputs/wall-pr-operating-point-v1`.
원본·실패 보존, TensorBoard 생략 유지, Google Drive0. 관련1–3개 시험파일 초록 후
커밋·push, Co-Authored-By: Codex. PR405 DRAFT/병합0, force/reset/삭제0.
