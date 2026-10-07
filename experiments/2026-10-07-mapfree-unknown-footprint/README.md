# explore10 — public_ros_v7 footprint clearing / unknown 정책

## 구현·평가 전 사전 등록 (2026-10-07)

시작 `8ba29aa8`, PR #409. PR #405 최종 시차0/2 실패·트랙 종료 보고 후 복귀했다.
사용자 승인 범위는 2D 평가기/어댑터 수정이며 **MuJoCo·렌더·모델 호출0**이다.
기존 v1–v6 소스·관문·결과를 보존하고 새 `navigation=public_ros_v7`만 추가, 기본 off.

### 원본 확인과 적용할 차이

[REFERENCES](REFERENCES.md)의 pinned 원본·기본 설정을 확인했다.
- Nav2 ObstacleLayer `footprint_clearing_enabled=true`: 매 update에서 **현재** 변환 footprint
  polygon을 FREE_SPACE로 쓴다. 비 rolling layer에는 지난 update의 free 값이 남지만,
  미래/예측 footprint를 미리 지우거나 과거 전체 궤적을 매번 다시 지우지는 않는다.
- NavFn `allow_unknown=true`(코드/YAML), global costmap `track_unknown_space=true`.
  unknown255를 그대로 보존하면서 planner가 높은 비용으로 통과할 수 있다. free 관측으로 만들지 않는다.
- explore_lite는 가까운 free에서 flood, free와 인접한 unknown을 frontier로 삼고 centroid를
  move_base goal로 보낸다. launch에 별도 allow_unknown 파라미터는 없다.
- Nav2 RPP는 tracking-unknown costmap에서 footprint_cost255를 충돌로 간주하지 않는다.
  원 어댑터의 무조건 unknown 거부와 관측-free standoff 강제를 v7에서 해제한다.
  known lethal254와 map 범위 밖은 계속 거부한다(범위 밖은 Nav2 경고 후 허용과 다른 기존 카메라 제한).

v7은 실제 자기 추정 pose의 현재 padded rectangle(.28×.24m)을 각 관측/10Hz 제어 update에
Nav2 Bresenham outline+column fill로 지운다. 관측층에 그 free 상태를 유지하고 static authored
wall층은 복원한다. 이후 새 hit가 지나온 칸을 차지하면 다시 occupied가 된다. footprint free는
직접 RGB floor provenance나 coverage 점수에 추가하지 않는다. 2D 단일 costmap 어댑터라 global
unknown 정책을 follower에도 일관되게 적용하며 ROS global/local 서버 전체의 재현이라고 부르지 않는다.
원 NavFn/explore_lite 코어·회복·blacklist·레이·센서/난수/예산·inflation 계수는 변경하지 않는다.
frontier 비용/크기 등 이번 범위 밖의 기존 v6 값도 유지한다. unknown의 높은 비용과 centroid 목표만
원본 정책으로 연결한다. GT 물체 위치·B·타 로봇 지도는 actor에 주지 않는다.

### 순서와 동결 기준

1. 이 계획/원문 근거를 기존 관련 시험 통과 후 먼저 commit한다. 구현 시험·소스 commit/push 후 실행.
2. 기존 K/L32는 개발 진단으로만 사용한다. v6와 똑같은 첫 관측을 재구성해 연결 성분과
   동일 후보 NavFn 경로/첫 footprint 연결 성공을 비교한다. **32/32 모두 연결>36칸 및
   유효 후보 경로≥1**이라는 이전 개발 관문 그대로다. 실제 선택 centroid의 경로·첫 명령도 기록한다.
   전체 개발 임무는 재실행하지 않고 이 결과로 임계값을 튜닝하지 않는다. 미달이면 중단한다.
3. 개발 통과 시 미생성·미개봉 상태인 M/N32를 새로 생성·commit·해시 봉인한다.
   s1–s8×M/N×7701/7702. 이전 등록과 같은 S2 도크 shuffle(7700+scenario),
   .025+.10*k m(k=0…5) 출발 격자에서 footprint/inflation 유효 첫 위치, 첫2도크.
   과거 A–L pose와 같으면 HOST_SETUP_ERROR로 중단; 성과/경로/B 가시성으로 고르지 않는다.
   seed2는 같은 오라클 궤적일 수 있어 독립32실험이라고 주장하지 않는다.
4. 동결 후 새쌍 **frontier oracle1회**와 같은쌍 static_map 효율 분모1회. 최초 B/C/E 다섯 기준 유지:
   입력/off·소스/32분모, 참B≥26/32·거짓0, 공통 성공 frontier/static 거리/시간비 중앙 각각≤2,
   직접 본 reachable free coverage 중앙≥40%, 충돌/잘못된문/거짓passage0·문시도≥1.
   HOST_ERROR/ENOSPC도32분모, 공통 성공0이면 효율 실패. GT pose는 명시적 oracle 평가 브리지에만.
5. 5/5일 때만 S2 s1050–1051 실측 오차/검출 분포를 출처와 함께 별도 등록·commit 후 현실 잡음.
   B v3 recall79.41% 유지. 실측 분포가 없으면 구조 사전값을 실측인 것처럼 대신 넣지 않는다.
   실패하면 튜닝·재실행·현실 잡음 없이 유형만 기록하고 중단한다.

raw `/Users/changmin/projects/ugrp/outputs/mapfree-unknown-v7/` 새 경로, 원본 보존.
관리 session으로 유한 pure2D 실행, 속도 측정이 아니므로 timing 잠금 없음. 디스크/부하 기록,
ENOSPC=HOST_ERROR. 실험 그림 각각1MiB 이하. 기존 venv 사용·새 패키지0.
다른 worktree/사용자 미추적4파일 보존, 시험 후 commit/push·Codex trailer,
PR #409 DRAFT·병합/force/reset 금지. TensorBoard 이전 면제·Drive 프로젝트 예외 유지.
