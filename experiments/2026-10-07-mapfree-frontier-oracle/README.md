# explore8 — 동결 public_ros_v5 frontier 오라클 확인

## 새 쌍 실행 전 사전 등록 (2026-10-07)

시작 `ef8f5a7a`, PR #409 `claude/mapfree-explore`. 선행 explore7 정적 오라클 I/J32의 참 B32/32,
거짓0을 원본 결과·동결 hash로 검증한 뒤에만 진행한다. `public_ros_v5` 알고리즘·설정·기존 환경
93개 source hash와 B v3는 explore7 freeze 그대로다. 해상도0.05m, footprint/padding,
회복/blacklist, FOV/가림/사거리, B 시간 누적,900 modeled s/40m/300관측 예산을 변경하지 않는다.
MuJoCo 실행·렌더·모델 호출0. 새 실측/튜닝/패키지 설치 없음.

### 새로운 확인 쌍과 오라클 입력

- s1–s8 × S2 도크 규칙의 새로운 시작 K/L × seed6701/6702 = **32쌍**.
  `spawn_layout`의 도크 y를 `Random(6700+scenario)`로 섞는다. 각 도크에서 출발 전진 위치를
  `.05 + .10*k`m(k=0…5)의 사전 격자로 검사한다(이전 I/J의 `.10*k`와 다른 위치).
  기존 S2의 유효 사각 footprint·costmap 조건만으로 처음 유효한 위치를 선택하고 처음2도크를 K/L로 한다.
  B 시야/경로/성과로 선택하지 않는다. 유효 도크2개가 없으면 HOST_SETUP_ERROR로 중단하며 대체하지 않는다.
  이미 본 A–J 시작 자세와 정확히 중복되면 실행을 거부한다. 후보/탈락/선택 및 source hash를 cohort.json에 저장한다.
  seed만 바꿔 새 기하로 부르지 않는다. 오라클의 짝 seed는 같은 궤적일 수 있어 독립32표본으로 주장하지 않는다.
- frontier는 **자기에게 보인 floor/wall/B 관측만**, 정적 지도/정답 B/다른 로봇 지도 전달0.
  카메라 v3의 원 FOV·4m·가림을 유지한 완전 가시 검출/오차0 조건이다. 전역 완전 지도를 관측으로 주지 않는다.
- 사용자 지정 GT 자세 오라클은 평가기에서 start-relative xy/yaw만 매 명령/관측 시각 주입한다.
  접촉으로 몸체가 정지한 뒤에도 이 조건을 지킨다. 이전의 잡음0 명령 DR과 구별해 `oracle_gt_pose_v1`로 기록한다.
  navigator/센서/정적 기준선 알고리즘을 수정하지 않는다. GT pose 이외의 동적 진실은 actor에 주지 않는다.
- 거리·시간비의 같은 쌍 분모를 위해 새32쌍 각각에서 static_map 기준선과 own_frontier를 **각1회** 수행한다.
  선행 I/J32를 재실행/합산하지 않는다. 새로운 static 기준선도 같은 GT 자세와 같은 센서를 쓴다.

### 관문 — 최초 B/C/E §2의 다섯 기준 그대로

| 기준 | 변경 없는 판정 |
|---|---|
| 입력/회귀 | off bytes 동일, frozen source/settings 동일; GT는 이번에 명시 허용한 자세만, peer 지도/MuJoCo/모델 입력0 |
| B 확인 | frontier 참 B ≥80%(32중≥26), 거짓 확인0 |
| 효율 | 양쪽 참 B 확인 쌍의 frontier/static 거리·modeled time 비율 중앙 각각≤2; 공통 성공0이면 실패 |
| 탐색량 | 직접 본 reachable free coverage 중앙≥40% |
| 안전 | 충돌0·잘못된 문 시도0·거짓 passage 시도0, 실제 문 통과 시도≥1 |

기준의 GT 접근0은 이 진단 조건에서 사용자 지정 **GT pose만 예외**이며, 실제 추정 성능 통과를 뜻하지 않는다.
static의 ≥30/32는 선행 평가기 관문이고 frontier의 원 ≥80%를 임의로 바꾸지 않는다.
HOST_ERROR/ENOSPC/시작 오류도 분모에 남긴다. 첫 B 확인 거리/시간과 실패 종료 거리/시간을 분리한다.
32쌍 전체를 개봉한 뒤 위5개를 판정한다. 실패하면 재실행·튜닝 없이 유형/관측·경로·회복 원장만 분석하고 종료한다.

**5/5 통과할 때만** 다음 현실 잡음 단계로 간다. 그때 PR #406 s1050–s1051의 저장 RMSE/오류 표본·검출
오인율을 읽기 전용으로 가져와 provenance/해시/시간 상관·주입법을 별도 등록·커밋한 후 실행한다.
B는 동결 v3 recall79.41% 원표를 쓰고, FP는 관측된 오인 분모를 분리한다. 구 카메라 통계나 미측정 v7
과정 사전값을 S2 실측이라고 대신 넣지 않는다. 실측에 필요한 분포/상관이 없으면 그 한계에서 멈춘다.
실패 시 현실 잡음 실험/새 noise parameter 선택은0이다.

raw `/Users/changmin/projects/ugrp/outputs/mapfree-frontier-oracle-v1/`에 새로만 기록.
원본·미추적4파일 보존, pure2D 관리 session 하나만 사용. 속도 비교가 아니므로 timing lock 없음,
modeled time과 CPU wall 시간을 혼동하지 않는다. 원본 및 결과 hash·전체 표·진단 그림은 로컬 프로젝트에 보존.
시험 통과 후 commit/push·Codex trailer, #409 DRAFT/병합 없음/강제 push·reset 없음/다른 worktree 수정 없음.
TensorBoard/Drive는 앞선 사용자 면제·프로젝트 예외 유지.

## 출처

- [최초 B/C/E 기준](../2026-10-07-mapfree-explore/README.md#2-실행-전-사전-등록): 관문/효율/coverage/안전 분모.
- [public_ros_v5 고정값·정적32 결과](../2026-10-07-mapfree-s4-final/README.md), [freeze](../2026-10-07-mapfree-s4-final/freeze.json).
- [공개 NavFn/explore_lite 출처](../2026-10-07-mapfree-public-navigation/REFERENCES.md),
  [영속 장애물/progress/blacklist](../2026-10-07-mapfree-navigation-persistence/REFERENCES.md),
  [Nav2 footprint](../2026-10-07-mapfree-stop-geometry/REFERENCES.md): 이번엔 원문이나 어댑터를 수정하지 않는다.
