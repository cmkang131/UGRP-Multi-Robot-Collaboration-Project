# egomap34 — 감독 승인 rotL DEV 1회 / 선분 지도 비교

2026-10-08 구현·결과 전 사전 등록. egomap33의 **5/7 미달은 그대로**다.
사용자/감독이 명시적으로 승인한 DEV 확인이며 기존 관문 통과에 따른 실행이 아니다.

## 새 물리 (한 번)

- 미사용 seed32002, 180 SIM초, egomap31 tape/SEARCH/강성real_v1/frontier_rbpf_v1/
  public_ros_v8/recovery/±20°/insertion/selective/Manhattan/switchable 구성 그대로,
  `motion_model=s2_pulse_v122_rotL_v1`만 변경. 선분 지도는 **물리 제어에 켜지 않는다**.
- agent_lock null 확인 후 단독 acquire→ugrp_session/dev_light→release. S2 점유 시 대기.
  freeze0, 모델0, 새 보정 측정0. source commit/push 후 고정, 실행 중 소스 변경0.
- 종료오차/σ/과신, yaw·경로 오차, 영역P/R·전체 덮임·벽RMSE, 칸/벽/프레임 표본수,
  이동/footprint 면적/hold, 삽입·거부 사유, B 자기 확인/GT도착·벽접촉을 기록한다.
  손목 RGB | 그 시각 자기 지도와 추정/실제 경로의4배속 영상. GT는 평가/그림만.
- 새 seed와 egomap31은 다른 궤적이므로 paired 개선 확증으로 합산하지 않는다.
  물리 예산30분/500MiB, ENOSPC·공간<10GiB는 HOST_ERROR. 실패 시 추가 실행0.

## 오프라인 선분 지도 (결과 전 고정)

`wall_map=segments_v1`, 기본off. 기존 격자/추정기/탐색은 변경하지 않는 별도 자기 지도 표현.
egomap31과 egomap33은 **같은 seed31001 녹화의 off/on 추정**임을 명시한다.
각각 기존 삽입47/50프레임만 사용하고, 동일 RGB의 기존 카메라/검출 열 접점을 재투영한다.
보간한 선분 점을 독립 측정으로 세지 않는다. 자기 pose/공분산과 관측 신뢰도만 사용한다.

- Nguyen et al. 2005의 split-and-merge 계열을 공개 BSD-3-Clause
  `kam3k/laser_line_extraction` commit `34de3e9d7560c04bec29e97f07339407c0bca6a6`와 대조한다.
  endpoint split→짧은/성긴 선분 제거→공분산 가중 선 적합→χ² 병합 순서.
  원본 기본값 split .05m, gap .4m, 최소길이 .5m, 최소9개 실제 열 표본,
  outlier .05m, χ²<3, 최적화 수렴1e-4를 고정한다.
  기존 카메라의 양의 깊이/최대4m, 최소range .4m(공개 기본)을 사용.
- 레이저 고정 잡음 대신 기존 카메라 1px 투영 Jacobian·영상 contrast/sharpness/settling으로
  점 공분산을 만든다. 자세 공분산은 프레임 공통항으로 선 공분산에 한 번 더한다.
  weighted orthogonal least squares는 동일 목적식을 SciPy로 계산(추가 의존성0).
- 여러 프레임 선 병합은 같은 χ²<3 및 관측 extent gap≤.4m. 상관된 자기 pose를 독립으로
  곱해 과신하지 않도록 표준 covariance intersection(고정 ω=.5)을 쓴다.
  Manhattan 기준축은 첫 자기 scan의4중 원형평균이며 GT축0°로 고정하지 않는다.
  가장 가까운90° 축으로 정렬하되 축/자세 불확실성을 보존한다.
  신뢰도는 공분산·서로 다른 프레임 수이며 점유 log-odds를 벽 확률로 부르지 않는다.
- 지도 정확도 평가는 기존 .15m 벽 허용거리·329개 GT벽 표본·잠재가시 정의 그대로.
  선분은 .05m 간격 길이표본 P와 같은 .1m 격자 raster P를 **둘 다** 기록한다.
  전체/가시R와 벽RMSE, 선분 개수·총길이·점/프레임 수를 같이 보고 분모 변경 착시를 막는다.
  기존 칸의 거짓점 중 벽거리>.15+.1√2/2인 비율도 계산한다: 이들은 셀 중심 양자화만으로
  설명할 수 없다. 격자 사용이 주원인이라는 것은 아직 가설이며 결과로 판단한다.

사용자의 '기준에 가까워지면'은 결과 전 다음처럼 적용한다: 두 추정조건 모두에서
선분 **전체 P·R·벽RMSE의 기존 목표(.90/.70/.15m)에 대한 양의 미달량이 비증가하고,
각 조건에서 하나 이상 감소**해야 내보내기 함수 구현에 착수한다.
이는 새 완화 합격선이 아니라 개발 착수 조건이다. 기존 egomap20 절대관문은 별도 그대로 보고,
미달 함수는 F 준비완료/LLM 투입 성공으로 보고하지 않는다. 비교는 raster P/R/RMSE로 판정하고
연속 선 표본값을 보조로 남긴다. 미달이면 원인만 기록, 문턱/옵션 사후변경0.

raw `/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1`, 기존 raw 보존.
기본off bytes 골든·관련1–3개 시험파일 통과 후 커밋·push. PR405 DRAFT/병합0.
TensorBoard 생략 유지, Drive0. 단계마다 supervisor 확인.

## 출처

- [Nguyen et al. 2005, IROS, DOI](https://doi.org/10.1109/IROS.2005.1545234): 비교 기준.
  세부 구현은 아래 공개 코드로 확인하며 이 논문의 수치를 우리 결과로 인용하지 않는다.
- [공개 구현·라이선스](https://github.com/kam3k/laser_line_extraction/tree/34de3e9d7560c04bec29e97f07339407c0bca6a6):
  `src/line_extraction.cpp` 21–55,150–244,246–355 및 `src/line.cpp` 155–244.
- [CI의 SLAM 적용, Julier & Uhlmann 2007](https://doi.org/10.1016/j.robot.2006.06.011):
  알려지지 않은 상관관계의 공분산 결합. ω=.5는 유효한 고정 convex weight이며 적합하지 않는다.
- Manhattan 축 계산은 기존 `harness/rbpf_manhattan.py:19–35`의4중 원형평균 재사용.

구현 연결: `harness.self_wall_memory_segments.SelfWallMemory(wall_map="segments_v1", ...)`의
`observe_wall(..., wall_points=contact_points(rgb, servo))`/`snapshot()`에서 사용할 수 있다.
기본off는 기존 memory에 위임하며, 이번 물리 실행기는 이 새 표현을 사용하지 않는다.
원본 C++ iterator의 끝점 누락은 Python inclusive corner split으로 옮겼고,
자세를 공유하는 프레임의 상관관계·카메라 잡음·extent gap 처리는
[이식 차이](../../third_party/wall_segments/NOTICE.md)에 명시했다.
문헌 DOI는 Crossref 제목 대조로 확인했다. Nguyen 원문 전문은 이 환경에서 열지 못했고
알고리즘 세부/수치는 공개 코드로 확인했다. 초기 단위시험의 NumPy 2D cross API 오류와
빈 관측 fixture 누락은 결과 개봉 전에 수정했으며, 이후 관련8시험 통과.
