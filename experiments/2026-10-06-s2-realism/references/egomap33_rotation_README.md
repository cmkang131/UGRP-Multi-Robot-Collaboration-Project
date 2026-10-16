# egomap33 — 사용자 결정: 좌회전만 v122 재적합

2026-10-08 구현·지도 on 재생 전 등록. 사용자가 egomap32 결과를 보고 명시한 새 후보다.
egomap32의 양방향 후보 미달 기록은 보존하며 성공으로 바꾸지 않는다.
새 물리 측정0. 기존 seed32001/110펄스의 반복1–3 적합/4–5 확인을 그대로 쓴다.
이미 본 확인 자료이므로 독립 확증으로 재명명하지 않는다.

## 방법·기준 고정

UMBmark 양방향 평균/산포 분리(§3.2–3.4, [확인한1995 공개판](https://www.cs.columbia.edu/~allen/F17/NOTES/borenstein.pdf))와
egomap32의 원점 통과 최소제곱을 재사용한다. 메카넘 단발·연속 회전만의 축소 진단이며
완전 사각 UMBmark의 바퀴 간격 보정 공식을 이식하는 것이 아니다.

- `motion_model=s2_pulse_v122_rotL_v1`, 기본off(기존 동작).
  무하중 `0:turn:0.35:0.10` profile의 yaw mean curve/endpoint만
  반복1–3 적합 gain으로 변경한다. CW·하중·XY·시간곡선 표본시각·분산·다른 명령 profile은
  v122 bytes 동일. v122 원본 JSON/#406 파일 수정0. 모델 추정·펄스 경로 예측에 같은 profile 적용.
- 적합 관문은 egomap32 그대로: CCW gain95% CI 하한>1, 단발/연속 gain 차이≤5%,
  반복4–5 확인 yaw RMSE 감소. CW는 **사용자 결정대로 원본 동일이면 통과**.
  분할/종료 horizon .20초/가중치/문턱/모션 잡음/RBPF/graph/탐색 설정 변경0.
- 통과 시 egomap31 seed31001 전체891 제어프레임, 자기 RGB/저장된 자기 검출/자기 명령만으로
  off/on을 각각1회 재생한다. off 전체 trace bytes 골든, GT는 두 예측을 봉인한 뒤 평가만.
  on에서도 새 제안 명령을 실행하지 않고 실제 녹화 명령을 넣는다(폐루프 물리 성공 아님).
- egomap32의 후속 물리 관문 그대로: **yaw RMSE·종료 XY오차·과신 비율 감소,
  영역P/R·전체 덮임 비감소, 벽RMSE 비증가** 모두 만족해야 한다.
  graph 결과와 frontend σ를 섞지 않으며 frontend 관문/graph 지표를 나란히 기록한다.
  미달이면 추가 물리0, 결과 후 문턱/옵션 변경0.
- 통과 시에만 아직 실행하지 않은 **seed32002/180초 물리1회**. egomap31의 tape/SEARCH/
  강성/v122/RBPF100/±20°/insertion/selective/Manhattan/switchable/recovery/Nav2 .05m
  구성에 이 motion 옵션만 추가. agent_lock null 대기→단독/dev_light/ugrp_session,
  S2 물리 동시 금지, freeze0/모델0. 소스는 실행 전 커밋·push.

오프라인 raw `outputs/pulse-rotation-left-v1`, 조건부 물리 예산500MiB/30분,
디스크 여유10GiB 미만 및 ENOSPC=HOST_ERROR. 원본 보존/삭제0.
기존 TensorBoard 생략 유지, PR405 DRAFT/병합0. 시험 후 커밋·push,
PR406에 결과 코멘트만 공유. 단계마다 supervisor 재확인.
