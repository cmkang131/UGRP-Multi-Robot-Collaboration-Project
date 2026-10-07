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
