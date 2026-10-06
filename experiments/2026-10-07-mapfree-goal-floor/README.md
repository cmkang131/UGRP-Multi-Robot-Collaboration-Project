# D — 자기 RGB의 바닥 색 목적지 B (2026-10-07, 오프라인)

## 1. 작업 경계·선행 지도 동결

사용자 요청에 따라 PR #405 지도 알고리즘은 `f3eeb6bf`에서 동결한다. s911–s913 구 녹화 기반 지도 튜닝을
중단하며 현행 v7·카메라 v3 녹화가 준비되면 별도 재검증한다. 이번 작업은 설계서
`/Users/changmin/projects/ugrp/outputs/mapfree-design-20261006/DESIGN.md` §6(D), §9의 바닥 색 모듈이다.
다른 worktree·기존 지도 알고리즘·시뮬레이션·카메라·환경 색을 수정하지 않는다.

PR #405의 추적 파일이 깨끗하고 HEAD=원격=`f3eeb6bf`임을 확인한 뒤, `origin/main=b07f33ab`에서
`claude/mapfree-goal-floor`를 만들었다. 자기 명령 DR/좌표·메모리 경계를 재사용하려고 #405를 병합했다
(`1d3f16cd`, 관련 시험 51 passed). 기존 미추적 4개 파일은 해시를 기록하고 보존했다.
새 PR은 #405 위에 쌓는 DRAFT이며 둘 다 병합하지 않는다.

## 2. 구현 전 성공 기준·자료 분리

**이 절을 구현 전에 커밋한다.** 검출은 자기 RGB와 명시적 목적 색, 고정 K/D·mount 및 자기 팔/이동 명령,
자기 출발점 기준 추정 pose만 사용한다. 정적 지도·평가 pose·다른 로봇 관측/지도·깊이·segmentation·ray
정답을 검출기에 넣지 않는다. 예측 산출물을 저장한 뒤 별도 평가가 정답을 읽는다.

현재 기록의 B는 공개 팔레트상 blue다. pickup도 비슷한 파랑이므로 색만으로 의미를 구분할 수 있다고
가정하지 않는다. 새로운 고유 색으로 환경을 바꾸거나 GT 위치로 둘을 구분하지 않고 오검출로 집계한다.
완전히 다른 hue인 cyan·A/C도 음성 대조로 남긴다. 전체 목적지 윤곽은 알려주지 않으며 관측된 patch의
중심·범위만 누적한다. 확신도는 색/투영/반복 관측의 휴리스틱 점수이고 보정된 확률이라고 부르지 않는다.

| 기준 | 사전 문턱·분모 |
|---|---|
| off 호환 | 기본/명시적 `goal_detection=off`의 기존 memory·정적 B 반환 bytes 동일 |
| 입력·기하 | 외부 로봇/중복·역순/비유한 입력 거부; optical z>0·floor t>0; 비정착/먼 점 제외; GT 제어 입력 0 |
| B 검출 | 평가 가능한 표본에서 component precision ≥0.90 및 B 가시 프레임 recall ≥0.80, 녹화별 별도 판정 |
| 중심 투영 | 참 B component의 보이는 patch 중심에 대한 카메라 투영 오차 median ≤0.20 m, P95 ≤0.40 m |
| 누적 위치 | 출발 GT 변환 1회만 적용한 자기 odom 후보 중심 오차도 별도 보고; 투영 오차와 합산 금지 |
| 최초 확인 | 충분한 서로 다른 자기 관측 3개·≥2 s·시점 이동 ≥0.05 m 또는 5° 이후 확인; 거짓 B 확인 0 |
| 자료 부족 | B 가시 양성/참 검출/독립 camera GT가 없으면 recall/중심 오차 N/A, 통과로 대입하지 않음 |

현재 녹화 **s1042/1043/1044 pick** 및 **s1045 S2 full(place)**를 각각 평가하며 구 녹화
**s911/s912/s913 × r1/r2**는 별도 표로 둔다. 검출·누적은 첫 프레임부터 **2.0 s 간격으로 선택**하고
마지막 프레임도 포함한다. 이는 저장 RGB의 표본 재생이며 전체 20 Hz 처리 성능이 아니다.
최초 확인 시각도 이 표본열 기준이다. 분모·선택 프레임·누락을 manifest에 남긴다.

개발은 s1042, s911-r1/r2이며 설정을 먼저 고정한 뒤 나머지 자료를 확인 재생한다. 이미 보유한 자료이므로
신규 확증 실험이라 부르지 않는다. 같은 자료를 반복 튜닝하지 않는다. 양성 부족·오검출·보정 실패를
성공처럼 보고하지 않는다. v3 pick 3건은 실제 camera pose 기록이 없어 RGB 독립 수동 가시성 라벨을 쓰고
정확한 투영 중심 정답은 N/A로 남긴다. s1045의 별도 camera-pose 기록 및 구 녹화의 camera labels는
평가에서만 사용한다. 가림이 명확하지 않은 픽셀/프레임은 미판정으로 따로 집계한다.

## 3. 표준법·고정 초기 옵션

[OpenCV HSV/inRange 공식 예제](https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html),
[평면 homography 설명](https://docs.opencv.org/4.13.0/d9/dab/tutorial_homography.html),
[fisheye undistortPoints](https://docs.opencv.org/4.13.0/db/d58/group__calib3d__fisheye.html)를 확인했다.
색 분할 뒤 연결 영역·morphological opening, 보정 광선의 바닥 교차, 자기 좌표 변환을 따른다.
raw 어안 영상에 직접 homography를 적용하지 않는다. SAM/모델 호출·새 라이브러리는 쓰지 않는다.

- 입력은 uint8 RGB, 내부 OpenCV H=0..179, S/V=0..255. 기본 목적 색 blue H=100..130, S≥35,V≥30;
  wrap hue도 지원한다. 3×3 opening, 최소 64 px. 수치는 팔레트 기반 개발값이며 문헌의 보편 문턱은 아니다.
- 바닥 ROI는 하단 65% 및 명령 카메라의 하향 광선. optical/평면 분모 양수 조건, 하향 성분 <−0.05,
  카메라 거리 ≤4 m를 만족해야 한다. 영역 둘레 중 저채도(S≤55,V≥30) 바닥 연결 ≥35%를 요구한다.
  이것이 같은 색 물체/벽의 완벽한 제거를 보장하지 않으며 오검출 종류를 평가한다.
- `harness.visual_arm.camera_extrinsics`와 `markerless_box._pixel_ground_point`의 FK/광선 처리 재사용.
  v3는 #401의 공개 고정 mount (52.982,0,28.152) mm·tool-relative +10°를 기존 FK에 합성한다.
  보정된 실제 mount라고 주장하지 않는다. 입력 RGB의 legacy/v3 profile은 명시적으로 구분한다.
- 자기 map pose는 #405 `CommandOdometry`의 M1 명령 모델(정답/측정 관절 없음)을 재사용한다.
  v7에 새로 맞춘 모델이 아니므로 v3 자료의 지도 좌표 오차는 별도 한계다. 위치 보정/지도 튜닝은 하지 않는다.
- 관측 patch convex hull·중심·AABB·품질/시각/frame ID를 자기 namespace에 저장한다. 관측된 0.1 m cell의
  합집합만 누적하고, GT B 크기·윤곽을 채워 넣지 않는다. 후보는 기존 bbox와 ≤0.30 m 근접한 관측끼리 묶는다.
  3회/2 s/시점 변화 조건을 채우면 `locally_confirmed_region`, 그 전은 `visually_seen`; 처음은 `unknown`.
  다른 로봇 말에 의한 `heard_candidate`는 별도 확장 경계이며 이번 구현에 peer 입력은 없다.

`goal_detection=floor_color_v1`은 opt-in, 기본 off는 기존 정적 지도 B 경로를 보존한다. on에서 unknown이면
정적 B로 fallback하지 않는다. 도착·배달 성공 판정이나 이동 명령은 만들지 않는다. simulation·render·model 0,
원본 보존, timing 측정 없이 진행한다. 같은 원인으로 두 번 막히면 멈추고 보고한다.

## 4. 구현 경계·평가 규약 고정 (재생 전)

- 구현 `harness/floor_goal.py`, 메모리 어댑터 `SelfWallMemory.observe_goal_rgb`/`goal_target`.
  `goal_detection=floor_color_v1`은 `self_map=odom_grid_v1`를 요구한다. 이번 재생은 보정 off의 기존 M1 DR만
  쓴다. 팔의 자기 명령·정착 게이트를 사용하고 실행기/이동 제어에는 연결하지 않은 오프라인 API다.
  off의 `goal_target(static_B)`는 동일 객체/바이트를 반환하고 snapshot에는 새 키도 생기지 않는다.
  on은 `self_goal`에 자기 namespace, 관측 patch 중심/범위/신뢰도/시각과 누적 후보를 넣는다.
- `tests/fixtures/floor_goal/pre_goal_snapshot.json`은 변경 전 `6bb14930`에서 생성한 기본/odom-grid snapshot이다.
  기본 off와 명시 off의 바이트 동일성, 정적 B bytes 동일성, 색·hue wrap·어안 왕복 투영·양의 깊이·정착·
  자기 관측/중복/역순·다중 시점 누적을 시험한다. venv는 기존 `.venv-sim-worker-mac`이며 설치 변경 0.
- 평가의 양성 프레임은 실제 가시 B가 **64 px 이상**인 표본이다. 참 component는 accepted pixel의 ≥50%가
  독립 B 가시 mask에 겹치는 경우다. frame recall 분모는 양성 프레임 전체(검출 ROI/정착/거리로 줄이지 않음),
  precision 분모는 모든 accepted component다. 픽셀 precision/recall과 혼동하지 않는다.
- 실제 camera pose가 있는 자료는 저장된 pose·K/D로 각 pixel 광선을 B 바닥 높이 0.0011 m와 교차시키고,
  저장 scene의 정적 벽 box가 앞을 가리면 제외한다. 이 **가시성 상한**에도 B가 없으면 다른 물체의 가림을
  추가해도 B가 생길 수 없으므로 음성 판정 가능하다. 상한에 B가 남으면 RGB에서 물체/로봇 가림을 별도 검수하며,
  검수가 없으면 그 프레임은 미판정이다. MuJoCo 로드/forward/render/ray 호출은 하지 않는다.
- 오류원은 GT camera가 있는 경우 component 광선의 첫 정적 벽/바닥 영역으로 나누고, 물체 가림 가능성은
  따로 검수한다. 실제 camera가 없는 pick 3건은 RGB 음성 라벨만 사용하여 위치 기반 오류원·거리 오차를
  만들지 않는다. `manual_visibility.json`은 단일 시각 검수자/축소 contact sheet 판독이라는 한계를 가진다.
- 중심 오차는 참 component의 **동일 관측 pixel**을 GT camera로 바닥 투영한 평균과 비교한다.
  현재 GT base pose로 변환한 카메라 오차와 출발 GT SE(2) 한 번만 적용한 own-odom 오차를 따로 낸다.
  GT 전체 B 중심까지 거리를 관측 patch의 투영 오차로 대체하지 않는다.
- `cases.json`의 개발 3건을 재생하고 소스/옵션 해시를 고정한 뒤 확인 7건을 재생한다. 개발 실패가 있어도
  이번 고정 후보를 자료에 맞춰 재튜닝하지 않는다. source/예측/mask/input RGB 해시를 저장하고 평가를 분리한다.
