# warp7 — RUNNING

`claude/warp5` / PR #550의 후속. 사용자 2026-10-16: 모두 MJWarp로 실행.
CPU 결과 동일성은 통과 조건에서 제외한다. MJWarp 자기 RGB를 평가 전용 visible geom 라벨과 대조해 화물/구역별 정탐·누락·오검출, 픽셀 precision/recall을 기록한다. 라벨·실시간 정답은 검출기/제어 입력에 전달하지 않는다. 기존 RGB 전처리·면적·기하 관문을 유지한 첫 분포를 먼저 보존한다. 정적 관문은 위치추정/임무 성공이 아니다.

순서: 평가 라벨 색 검출 → 출발 enclosure 거부 분포 → N16 운반·place·완주·xy/yaw p95·입력 감사 → CoreWeave fp4 E2E 첫30 SIM초. reloc21 progress/complete 기본 off 유지. 반복 제거 수정의 새 물리 검증은 아직 없다. cap_end/HOST_ERROR 별도, 같은 결함 3라운드면 중단한다.

PR #553의 CoreWeave fp4 설정/중계/공급 감시 변경을 cherry-pick했다. 원본 미병합 warp3 공통 backend는 main의 다른 버전으로 교체하지 않았다. 제출 직전 공급 감시와 OpenRouter 잔액을 다시 확인한다. 모델 키는 Mac 중계에만 둔다.

호스트: gcp2 L4 shared-load(warp3·beamact3 임대 보존), 분석 gcp2 n4-highcpu-64. 원본은 호스트 영속디스크, Mac에는 요약·몽타주·실패 프레임만 회수. CPU/타호스트/이전 렌더 후보와 합산 금지.

방법 근거: [OpenCV HSV inRange](https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html), [MJWarp segmentation object ID/type](https://mujoco.readthedocs.io/en/latest/_modules/mujoco_warp/_src/render_util.html). 설치된 pinned API와 RGB/PWM 생산 검출기를 사용한다. 새로운 색 상수는 첫 분포 확인 전 넣지 않는다.
