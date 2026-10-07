# explore9 — public_ros_v6 관측 raytrace 수정 (실행 전 등록)

시작 SHA `8d4c2eaa`, PR #409. 사용자가 지정한 평가기/관측 어댑터 수정이며 탐색 튜닝이 아니다.
기존 `public_ros_v5` 및 그 93개 frozen source/settings를 수정하지 않는다. 새 옵션
`public_ros_v6`만 관측점까지 Bresenham free clearing → 현재 hit marking을 수행한다. 기본 off,
off 출력 bytes 동일. 카메라 v3 FOV·4m·가림·바닥 표본0.10m·자기 격자0.05m·회복·frontier 비용·
B v3·900 modeled s/40m/300관측 예산을 유지한다. MuJoCo·렌더·모델 호출 금지.

## 변경 계약과 출처

[REFERENCES](REFERENCES.md)의 pinned Nav2 ObstacleLayer 순서를 그대로 사용한다. 바닥 끝점은
clearing-only, 벽 끝점은 clearing+marking이다. 광선 사이의 면을 임의 보간하지 않는다.
시야 밖 과거 hit는 관측 광선이 통과할 때만 지우고 static authored 벽층은 그대로 유지한다.
카메라 원점은 **해당 관측의 명령 팔 자세+기존 고정 보정**이며, 실제 GT 카메라/물체 좌표가 아니다.
기존 두 팔 자세의 합쳐진 점 목록에 각 점의 명령 카메라 원점을 붙이는 평가기 어댑터를 추가한다.
센서 endpoint/patch/가시성/난수 순서는 그대로인지 비교한다. 원점·끝점은 자기 pose로 함께 변환한다.
Grid의 free provenance에도 ray 통과를 기록하되, coverage는 기존 평가기의 **실제로 본 바닥 표본**만
세므로 ray clearing으로 coverage 점수를 부풀리지 않는다. 2D ObstacleLayer 포트이며 VoxelLayer
3D 높이 판정/ROS 전체 서버 구현은 아니다. 관측에서 숨은 기하를 제어기로 전달하지 않는다.

## 순서와 변경 없는 관문

1. 이 README·출처를 관련 시험 통과 후 먼저 커밋. 구현/단위시험/소스 커밋 뒤 개발 진단.
2. `8d4c2eaa`의 K/L32 실패를 **개발용**으로만 사용: 저장된 첫 관측과 같은 endpoint/patch를
   재구성하고 v5/v6 costmap의 출발4-connected 성분 크기, 전체 성분 수, frontier 후보별 실제
   NavFn 경로 수를 비교한다. 성공은32개 모두 출발 성분>36칸이며 유효 후보 경로≥1이다.
   전체 임무를 개발에서 재실행하거나 결과를 보고 설정을 바꾸지 않는다. 실패하면 그대로 중단.
3. 개발 통과 시 새 M/N32쌍을 사전 생성·커밋·해시 봉인한 뒤 frontier 오라클 **1회**.
   s1–s8 × M/N × seed7701/7702. S2 도크 순서를 `Random(7700+scenario)`로 섞고
   `.025+.10*k`m(k=0…5) 전진 격자에서 footprint/inflation이 유효한 첫 위치, 처음2도크 선택.
   기존 A–L 시작과 같으면 HOST_SETUP_ERROR로 중단하며 B 가시성/경로/성과로 선별하지 않는다.
   seed 두 개는 오라클에서 같은 궤적일 수 있어 독립32표본으로 주장하지 않는다.
   같은 새 쌍의 static_map 기준선도1회 기록하여 효율 분모로만 사용한다.
4. 최초 B/C/E §2 및 explore8의 **다섯 기준을 그대로** 적용한다:
   입력/off 회귀·소스 동결, 참 B≥26/32·거짓0, 공통 성공 frontier/static 거리·시간비 중앙 각각≤2,
   직접 본 reachable free coverage 중앙≥40%, 충돌/잘못된 문/거짓 passage0·문 시도≥1.
   HOST_ERROR/ENOSPC 포함32분모 유지, 공통 성공0이면 효율 실패. 이번 GT pose는 명시된 오라클만 예외.
5. 5/5 통과 시에만 s1050–s1051 실측 잡음 출처/상관·주입법을 별도 등록·커밋한 뒤 현실 잡음.
   B v3 원 recall79.41% 유지. 필요한 실측 분포가 없으면 대체 사전값을 만들지 않고 한계를 보고한다.
   실패 시 추가 튜닝·재실행·현실 잡음0, 유형 분해와 원본/그림/표만 기록하고 멈춘다.

raw는 `/Users/changmin/projects/ugrp/outputs/mapfree-raytrace-v6/`에 새로 저장한다.
한 관리 session으로 pure2D 실행, 시간 성능 비교가 아니므로 timing lock 불필요. 부하·디스크 기록,
자신의 프로세스만 정리. 이전 raw·사용자 미추적4파일·다른 worktree 보존. 시험 후 커밋/push와
`Co-Authored-By: Codex <noreply@openai.com>`, PR #409 DRAFT 유지·병합/강제 push/reset 금지.
TensorBoard는 이전 사용자 면제, Drive는 프로젝트 예외 유지. 결과는 별도 RESULTS.md에 기록한다.
