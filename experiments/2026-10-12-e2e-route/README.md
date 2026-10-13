# E2E17 경로 거부 원인 정리 (Refs #453)
- 코드 변경 없음, 번들 ID 등록 없음. 새 토글 대신 **이미 있는 `coverage=native_v1`(DEV 전용, 기본 off)을 권고**: 권고값 `native_v1`.
- 거부 위치: `harness/e2e_boundary_views.py` `observed_path_clear`→`observed_sweep_clear`. 기본 sweep 검사 외에 `Costmap.pose_clear`로 footprint 안 **미지(255) 칸**을 추가로 거부한다(확인 영상 전용 강화 검사). 경로 36점 중 자세 (0.625,-0.225,-45°)의 footprint에 미지 1칸(점유 0)이 있어 strict만 실패, native는 통과(`view-path-replay-native.json`, 저장 입력 17.0 SIM초, 자세 차이 0·명령 차이 0).
- 이유: 기준 v8 UnknownCostmap/NavFn은 미지 통과를 허용하지만 확인 영상은 "관측된 공간만" 요구해, 기하상 유효한 경로도 얇은 미지 칸 하나로 `B_view_path_lost`가 된다.
- v213(native_v1, 6실행 azure3/4) 결과: 이 거부는 사라짐(마지막 check strict·native 모두 clear). 그러나 view 3~4회 완료 후에도 B 미확정 6/6. 영상 윤곽 사유가 `not_convex_quad` 409–694, `white_islands_not_three` 127–251, accepted 0–1(`../2026-10-12-e2e-idle/v213-view-diagnosis-*.json.zst`). 다음 막힘은 경로 게이트가 아니라 B 표식 검출(지각)이다.
- 새 토글을 또 만들면 같은 동작의 중복이라 만들지 않았다. 확인 범위: 저장 입력 재생(이전 에이전트) + `tests/test_e2e_boundary_views.py` 12 passed(이번 실행). 새 물리·시뮬레이션 실행 없음, 경로 생성·운반 성공은 확인 안 됨.
- 참고(표준 방법, 모두 미확인=기억 기반, 원문 미열람): Nav2 planner/controller 분리와 costmap unknown 처리(`allow_unknown`, docs.nav2.org), Yamauchi frontier 탐색(1997), 후보 조건부 view planning/SAP-Nav(코드 주석의 REFERENCES.md 참조), 불완전 coverage 시 재계획하는 informative path planning. 요지: unknown을 gate에서 hard reject하지 않고 비용·재계획으로 처리.
