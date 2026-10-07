# explore6 — s4·s5 정지 기하와 회복 종료 진단

## 계산·수정 전 등록 (2026-10-07)

시작 `b494873c`, PR #409 `claude/mapfree-explore`. 이전 public_ros_v3의 유효6건 중 참 B2,
거짓0·s4/s5 회복 소진4건을 보존한다. 사용자 요청대로 s4/G·s5/G×4701/4702만 집중한다.
같은 oracle 궤적의 두 seed는 별개 독립 증거로 합산하지 않는다. MuJoCo·모델·렌더 호출0.

1. 저장 own observation/명령 DR를 재생해 첫 follow 충돌 예측 지점과 최종 정지의 grid/raw/inflated
   costmap을 복원한다. 최종 own_grid bytes와 대조한다. 실제 벽·물체는 평가용 그림/SAT/경로 존재
   진단에만 사용하며 actor에 전달하지 않는다. 원 녹화·실행을 덮거나 새 B 확인 성능이라고 부르지 않는다.
2. passage 폭, footprint의 축방향/회전 최대 폭, padding 및 soft inflation을 분리한다.
   사각 SAT와 보수적인 외접원 장애물 거리/A* 경로를 평가용으로만 사용한다. 경로의 연속 선분을
   조밀하게 검사하고 clearance 하한도 보존한다. 경로 미발견을 물리적 불가능의 증명이라고 하지 않는다.
3. 실제 MasterPi 공식 치수·기존 평가 치수·Nav2 코드 기본값/bringup 예시를 대조한다.
   inflation radius 전체를 lethal robot radius로 더하지 않는다. 기하 불가능이 드러나면 원본 근거로
   새 default-off 옵션을 만들고, 이전 v1–v3는 유지한다. 성공에 맞춘 폭 축소·문 확대는 금지한다.
4. 기하 통과 가능한 실패는 pinned RoundRobin의 마지막 child 분기 및 explore_lite ABORTED→
   blacklist→다음 frontier와 줄 단위 비교한다. 정적 B를 임의 frontier로 바꾸지 않는다.
   원본과 이미 같고 동일 실패가 남으면 추가 튜닝/재실행 없이 원인만 기록하고 중단한다.

개발 관문은 이전 정의 그대로: 시작 겹침4건은 HOST_SETUP_ERROR, 유효6건 참 B6·거짓0·회복 소진0,
접촉 회복 처리. 이전 s8의 접촉 집계 제한도 완화하지 않는다. 수정 후보가 생기면 시험/커밋 뒤 개발10을
한 번 재생하며, 전부 통과할 때만 기존 미개봉 I/J×5701/5702 32쌍을 oracle static 한 번 실행한다.
≥30/32·거짓0 및 기존5기준 불변. 개발 실패면 새32/후속 frontier/현실 잡음은 개봉하지 않는다.

raw `/Users/changmin/projects/ugrp/outputs/mapfree-stop-geometry-v1/`, 작은 요약·그림은 이 실험에.
CPU timing 비교가 아니므로 lock 불필요. 기존 venv/plot deps 사용, 새 설치0. TensorBoard/Drive 생략은
앞선 사용자 결정을 따른다. 시험 통과 후 커밋, Codex trailer, 강제 push/reset/삭제/다른 worktree 수정0.
PR #409 DRAFT 유지·병합 금지. PR #405 카메라 투영 실패 결과는 건드리지 않는다.

### 절차 오류 기록

최초 기존 시험은 sparse checkout에 빠진 `sensor-errors.npz` 때문에11통과/1실패였다. 그 비동기
시험 결과를 확인하기 전에 사전 등록 문서 `a9f3218e`를 커밋한 순서 오류가 있었다. 시험 후 커밋
규칙을 지킨 것으로 소급 표시하지 않는다. tracked 원본 blob을 복원했고 SHA256
`2a28ff187d04dfe1573d87555071f36b6c633f8597f0e1578b8a824da9cf183b` 일치, 기존12시험 재통과했다.
수치/후보 변경 없이 새 진단3시험까지15통과를 확인했다. 이후 코드는 시험 통과를 읽은 뒤 커밋한다.

첫 진단 실행은 live odometry의 read-only `pose` property에 저장 DR를 할당해 AttributeError로
첫 snapshot 이전 중단됐다. 평가 재생 전용 record로 바꾸고 실제 관측 입력을 통과시키는 회귀 시험을
추가했다. 제어기/센서/기하/관문 수정은 아니며 최초 `audit/`와 오류 기록은 보존, 재생은 `audit-v2/`다.

## 원본 차이 한 건: v4 구현 전 고정

`d0c77eaa` 복원과 `95441095` 기하 증명에서 첫 follow1초 구간의 사각 연속 여유 하한은
s4 0.02836m/s5 0.03129m였지만 raster 비용 지도는 각각0.70s/0.95s부터 거부했다.
원 Nav2 외곽 LineIterator를 대조하면 s4의7개 거부 표본은 그대로, s5의2개는0개다.
폭0.50m > padded 최대 회전 폭0.36878m이며 s4는 padding을 포함한 B 경로도 확인했다.
몸체/문 치수 불가능이 아니므로 치수·padding·inflation 반경을 변경하지 않는다.

**`navigation=public_ros_v4`, 기본 off**: filled polygon 대신 Nav2 FootprintCollisionChecker의
외곽 LineIterator와 최대 비용 판정만 이식한다. static/own obstacle memory, 예측 horizon/주기,
RoundRobin/explore_lite, 센서/B/v7, footprint240×200mm+padding20mm, inflation0.5m/10은 불변.
카메라 미관측 셀/맵 밖은 기존 입력 경계대로 통과시키지 않는 차이를 명시한다. 원본 전체 ROS 실행은 아니다.
v1–v3 byte 보존, 작은 regression 통과 후 구현 commit/push → 기존 개발10을 한 번만 재생.
원6/6 개발 기준을 그대로 사용하고 s4 또는 s5가 다시 막히면 추가 변경 없이 멈춘다.
새 I/J32는 개발 관문 실패 시 실행 금지. 작은 확인을 성공률에 합산하거나 s8의 접촉 gate를 완화하지 않는다.

구현 후 관련3파일27시험 통과. 첫 v4 시험의 두 fixture 오류(내부 픽셀을 외곽이라고 기대,
임의 noise 배열에서 차이가 반드시 생긴다고 기대)는 실제 s5 거부 셀의 작은 수치 반례와 외곽
corner fixture로 고쳤다. estimator/임계값 변경 없음. v1–v3 원본 bytes와 off 객체 bytes 동일.
이전 CI 목록에서 빠진 recovery/persistent 시험 및 새 진단 시험을 등록했다.
