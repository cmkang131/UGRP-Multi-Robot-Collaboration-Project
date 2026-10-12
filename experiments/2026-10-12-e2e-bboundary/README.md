# E2E B 경계 실패·frontier 고갈 오프라인 진단

기준 소스 `31f4f41ac7594ebc82c8cfc089c64ef50f65c57c`, 작업 브랜치 `codex/e2e-bboundary`. 9–12차의 36개 시도를 전부 기록했다: HOST_ERROR 24, EARLY_STOP 12. 이 중 trace 회수 28, 실제 이동 자료 24, r1 B 경계 기억·경로 생성은 0/24다. 시작 오류 12개도 제외하지 않고 summary에 남겼다. 새 시뮬레이션·물리·렌더·VM 접속·모델 호출은 모두 0이다.

## 조건별 관측값

`own_map_B_generated`는 `floor_color_v3`의 부분 색 후보 기억이고, `own_B_boundary_remembered`는 별도의 완전 경계 RGB가 자기 후보 중심에서 .20 m 이내에 있을 때만 생성하는 anchor다. 후자는 **1개의 완전 관측**으로 기억된다. 3프레임·ORB·공분산은 이후 재계획/도착 검증의 조건이며 anchor 생성의 조건이 아니다.

회수 RGB는 10차 A61001/A61002의 선택 JPEG 394장(그중 r1 152장)뿐이다. 모든 JPEG의 원 프레임 SHA-256을 대조했다. 아래 픽셀 최댓값은 r1 152장에 한정되며, B 물체의 정답 분할이 아닌 blue 성분의 계측이다.

| 판정 조건 | 실제 문턱 | 회수 자료의 값·범위 |
|---|---|---|
| 부분 색 후보 픽셀·면적 | 64 px, .005 m² | 전체 프레임의 해당 계측은 미저장. 후보 기억의 관측 횟수 최댓값 11, bounds 면적 최대 1.95 m²는 첫 확정 메타데이터/누적 bounding box이며 단일 관측 면적이 아님 |
| blue contour 면적 | ≥100 px² | 최대 176,728.5 px², 386개 성분 통과 |
| 완전 볼록 4각형 | 꼭짓점 정확히 4 | area 통과 성분의 꼭짓점 수 최대 9; 321개 성분은 4각형/볼록성에서 탈락 |
| 화면 경계·자기 몸체와 분리 | border ≥3 px, 팽창 영역 mask overlap=0 | 이후 단계 도달 65개, border 9–46 px, overlap 최대 0 |
| 흰 표식 | S<55, **V>180**, 면적 ≥9 px의 성분 정확히 3개 | 65개 모두 흰 성분 **0/3**. 낮은 채도 픽셀은 최대 5,524개지만 밝기 최대 **166**, 문턱 180을 넘지 못함 |
| 바닥 투영 | 유효 모서리 4/4, accepted 영역 정확히 1개 | 표식 단계에서 모두 탈락: 투영은 미도달, 완전 경계 0/152 |
| 경계 중심–부분 후보 중심 | ≤.20 m | 완전 경계가 없어 미측정 |
| 재계획 시 재관측 | 3개 fresh frame, span ≥.2 s, gap ≤.5 s, age ≤.25 s | B anchor 0이므로 판정의 선행 조건 불충족. 실제 history 계측은 미저장 |
| ORB/RANSAC | mutual/inliers ≥12, inlier 비율 ≥.6, coverage ≥.04 | B anchor가 없어 실제 anchor 비교값 없음 |
| 도착 위치 불확실도 | 거리+3σ≤.20 m | 12차 A61001 r1 저장 keyframe σ=.076924–.288248 m; 최솟값조차 3σ=.230771 m. 거리 0이어도 .20 m 초과. 이 값은 115개 keyframe 표본이며 전체 프레임 최댓값 아님 |

따라서 선택된 RGB에서는 작은 관측 면적보다 **4각형 형태와 흰 표식 밝기/개수**가 먼저 경계를 막는다. 다른 실행 전체에 같은 탈락 사유를 소급하지 않는다. 전체 trace에는 픽셀·current boundary·anchor matching 실패 이유가 저장되지 않아, 모든 라운드의 조건별 실제 최댓값을 복원할 수 없다.

## 위치 오차와 후보 기억

평가 전용 trajectory를 각 frame의 원래 capture 시각에 맞췄다(시각 차이 최대 0초). 12차 B61002 r1 위치 오차 최대 **8.971823 m**, heading 오차 최대 **179.844802°**를 재확인했다. 이 실행의 기록된 후보 중심은 그대로라 실제 기억 좌표 직경은 **0 m**다. 위치 오차가 후보를 여러 곳에 새로 생성했다고 주장할 수 없다.

같은 기억 중심을 각 로그의 자기 pose에서 body 좌표로 옮긴 다음, 평가 pose로만 사후 재투영하는 진단에서는 중심 이동 최대 **10.020634 m**, 재투영 중심 직경 **12.770461 m**였다. 이는 stale 기억을 포함한 좌표 일관성의 반사실 수치이며, 실제 검출 위치 산포나 제어 보정값이 아니다. 12차 A61001 r1은 각각 .579739 m/ .741500 m. 평가 좌표는 진단 함수만 읽고 제어·재생 입력으로 넘기지 않는다.

## Frontier 종료의 의미

12차 A61001 r1의 종료 **이벤트는 83.2 SIM초**, 저장 trace 상태가 `exploration_finished`로 바뀐 첫 프레임은 **84.0초**다. frontier 선택 4개 중 방문 2개, 진행 시간 초과 blacklist 2개다. 79.2초 navigation layer reset에서 570개 기존 hit가 8개 current hit로 재구축됐고, 80.4초 blacklist, 80.6초 마지막 선택, 83.2초 방문·종료가 이어졌다. 직접 `frontier_unreachable_blacklisted` 이벤트는 0개다.

- 소스에서 `frontier_progress_v1`은 B 접근용 `static_goal`을 버린다(`harness/e2e_exploration.py:84`). E2E의 `_select`/`_arrival`도 disabled다. B 후보를 기억해도 확인용 접근 단계로 전환되지 않는 것은 확인됐다.
- costmap 해상도 .05 m, inflation 반경 .5 m, inscribed 반경 .12 m. frontier 검색은 **raw** grid, NavFn은 **inflated** grid를 사용한다. inflation이 frontier 검출 자체를 지우는 구조는 아니다. 단, 계획 불능은 가능하다.
- blacklist/visited는 각 축 차이 <5 cells=.25 m인 후보를 제거한다. centroid가 inflated cost 253/254이면 거절한다. v8 NavFn은 `allow_unknown=true`이며, 기존 `UnknownCostmap`도 unknown footprint 추적을 허용한다. 따라서 unknown만으로 frontier 경로가 차단됐다고 판단할 수 없다. 성분 최소 길이는 .1 m.
- 종료 시점 원 costmap·전체 frontier 성분·blacklist/visited 좌표·navigation map TF가 저장되지 않았다. **B 방향 성분이 크기/팽창/연결성/blacklist 중 어느 항목에서 제거됐는지는 미측정**이다. 다른 worktree·VM에서 지도를 재생성하거나 정답 지도를 substitute하지 않았다.

## 수정과 저장 입력 재생

수정 토글은 **`boundary_views='candidate_views_v1'`**, 기본 **off**다. `make_goal`/`Robot` Python API에서 `exploration_progress='frontier_progress_v1'`과 함께만 켤 수 있다. 공개 실행 CLI에는 켜는 옵션을 추가하지 않았으며, 새 번들·workflow·실행 cohort는 등록/시작하지 않았다. 실행 후보로 승격하려면 별도 소스·bundle 고정과 인수가 필요하다.

후보 주변 표본 관측점에서 자유 셀·NavFn 경로·전체 swept footprint·정렬 회전을 검사한다. 알려진 장애물의 시선 차단을 거부하고, 한 관측점에서 30 SIM초/새 3프레임을 기다린다. 실패한 관측점은 별도로 기억하고 3회 뒤 기존 탐색으로 돌아간다. B 가설을 frontier blacklist에 넣거나 완전 경계·도착·release를 대신 승인하지 않는다. 토글을 켜면 `boundary_diagnostics`를 light ownmap trace에 남겨 후속 실행에서 픽셀 탈락 사유를 확인할 수 있다.

고정된 r1 기억 프레임의 **확인 대상 판정**은 off 0 → on **34,272프레임**이다. 같은 프레임을 여러 번 새 관측으로 세거나, 이를 실제 34,272번의 접근/요청으로 해석하지 않는다. 원 costmap이 없어 이 부분은 scheduling predicate 재생만 했다. 경로 선택기는 별도 합성 grid 시험으로 검증했고 저장 실행의 경로 성공은 미측정이다. RGB 394장에는 instrumentation off/on이 **394/394 동일**, 완전 경계 승인 **0→0**이다. closed-loop 개선·새 성공·실행시간/비용 개선은 검증하지 않았다.

관련 시험 파일 3개(`test_e2e_boundary_views.py`, `test_e2e_goal_route.py`, `test_e2e_explore_posefix.py`)의 최종 **57/57 통과**. 초기에 새 시험의 두 단언이 ‘현재 위치도 유효한 관측점’과 ‘zero mecanum’을 고려하지 않아 실패했고 단언을 고쳤다. 실제 소스 연결, 기존 unknown 추적과 새 관측점의 known filled-footprint 검사를 구분한 반례, 지도 갱신 후 coverage 상실 시 관측점 취소, 회전 충돌 거부, 3회 상한, 중복 프레임 거부, 기존 경계·공분산·기하 검사와 평가 좌표/시각 변환을 확인했다.

재현 명령(저장 자료 필요, 실행 아님):

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python scripts/diagnose_e2e_bboundary.py \
  --outputs /Users/changmin/projects/ugrp/outputs \
  --record experiments/2026-10-12-e2e-bboundary
```

`summary.json`은 모든 시도·측정 범위·소스 SHA·raw 위치를 포함한다. 상세 진단, 선택 RGB 계측, 전체 입력 hash manifest와 시험 JUnit은 `/Users/changmin/projects/ugrp/outputs/e2e-bboundary-20261012/`에 저장했다. 상세 JSON은 zstd 압축 뒤 해제 SHA를 확인했으며 원본 회수 자료는 수정하지 않았다. 해당 상세 자료는 **Mac 로컬 보관**이고 GitHub raw 백업은 아니다. [참고 자료](REFERENCES.md). Refs #433.
