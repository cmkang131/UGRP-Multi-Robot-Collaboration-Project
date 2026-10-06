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

## 5. 고정 후보 결과 (성공 아님)

예측 소스 **`7e6c887d`**, 사전 등록 **`6bb14930`**. 개발 s1042·s911-r1/r2 →
[`freeze.json`](freeze.json)의 코드/옵션 해시 봉인 → 확인 7건. 개발/확인 모두 같은 설정이며 튜닝 0회다.
원본 전체 **779개 2 s 표본**을 재생했다. 이는 10개 녹화의 개발 진단이고 신규 확증 코호트가 아니다.

**B가 실제 보인 양성 표본이 없다.** s1045 346개 + legacy 252개는 저장된 실제 camera pose를 이용한
640×480 전체 광선/정적 벽 가림 검사에서 B 가시 픽셀 상한이 **매 프레임 0 px**다. 동적 물체의 가림은
이를 늘릴 수 없다. s1042–1044 181개는 RGB 접촉표 수동 판독 음성이며 실제 camera pose가 없어 같은
기하 보증은 없다. 축소 판독/단일 검수자 한계 때문에 작은 양성의 누락 가능성은 별도 남긴다.

### 현행 카메라 v3 녹화 (구 녹화와 합산하지 않음)

| 녹화·역할 | 표본 / B 가시 | TP / FP component | precision | B-frame recall | patch 투영 median / P95 (m) | own-odom 오차 (m) | 최초 참 확인 / 최초 거짓 확인 (s) |
|---|---:|---:|---:|---:|---:|---:|---|
| s1042 pick·개발 | 70 / 0¹ | 0 / 3 | 0% | N/A | N/A | N/A | 없음 / 없음 |
| s1043 pick·확인 | 56 / 0¹ | 0 / 1 | 0% | N/A | N/A | N/A | 없음 / 없음 |
| s1044 pick·확인 | 55 / 0¹ | 0 / 1 | 0% | N/A | N/A | N/A | 없음 / 없음 |
| s1045 S2 full(place)·확인 | 346 / 0² | 0 / 12 | 0% | N/A | N/A | N/A | 없음 / **13.3** |

¹ RGB 수동 음성. ² 실제 camera trace·정적 벽 가시성 상한 0. 시간은 녹화의 sim timestamp이며 재생 wall 시간이 아니다.
s1045는 세 후보 중 **2개가 거짓 확인**됐다(13.3 s와 601.3 s). 같은 바닥·벽을 3회 이상 다른 시점에서
보는 것만으로 목적지 의미를 검증할 수 없었다. s1045가 full `place` 단계까지 진행한 사실은 B 바닥이
자기 카메라에 들어왔거나 목적지 도착을 검증했다는 뜻이 아니다.

### 구 카메라·구 구동 녹화 (지도 튜닝 자료로 재사용하지 않음)

| 녹화·역할 | 표본 / B 가시 | TP / FP component | precision | recall | 투영 median / P95 (m) | own-odom 오차 (m) | 최초 참/거짓 확인 |
|---|---:|---:|---:|---:|---:|---:|---|
| s911-r1·개발 | 48 / 0 | 0 / 2 | 0% | N/A | N/A | N/A | 없음 / 없음 |
| s911-r2·개발 | 48 / 0 | 0 / 0 | N/A | N/A | N/A | N/A | 없음 / 없음 |
| s912-r1·확인 | 39 / 0 | 0 / 2 | 0% | N/A | N/A | N/A | 없음 / 없음 |
| s912-r2·확인 | 39 / 0 | 0 / 2 | 0% | N/A | N/A | N/A | 없음 / 없음 |
| s913-r1·확인 | 39 / 0 | 0 / 2 | 0% | N/A | N/A | N/A | 없음 / 없음 |
| s913-r2·확인 | 39 / 0 | 0 / 0 | N/A | N/A | N/A | N/A | 없음 / 없음 |

빈 분모는 0/100%로 채우지 않았다. **precision 문턱은 평가 가능한 8건 모두 실패, 2건 N/A**.
recall·투영 정확도는 전부 판정 불가이며 전체 성공으로 판정한 녹화는 없다. 거짓 확인 0 기준은 9건에서
만족하고 s1045에서 실패했다. 양성 GT mask가 필요한 자료에 대해 현재 evaluator는 추측으로 TP/오차를
만들지 않고 `unscored`를 낸다. 이 코호트에서는 그런 미판정 프레임도 0개다.

### 비슷한 색 오검출

accepted component 25개를 모두 RGB 윤곽으로 검수했고 작은 로봇 패치 2개는 원본 해상도에서 확대 확인했다.
[`false_components.json`](false_components.json)의 분류는 component의 지배적인 보이는 표면이다.
광선/정적 지도만으로 물체를 바닥으로 오분류하지 않도록 시각 검수와 정적 ray 분류를 별도로 저장했다.

| 코호트 | 바닥 체크무늬/pickup 계열 | 벽/벽 경계 | 로봇 | 별도 cargo | 합계 |
|---|---:|---:|---:|---:|---:|
| camera v3 4건 | 10 (58.8%) | 7 (41.2%) | 0 | 0 | 17 |
| legacy 6건 | 3 (37.5%) | 3 (37.5%) | 2 (25.0%) | 0 | 8 |

일반 바닥과 pickup의 파란 tint를 RGB만으로 확실히 구분하지 못해 묶어 표기했다. A/C 별도 구역을
검출했다고 단정하지 않는다. cargo 오검출 0은 이 표본의 accepted component 기준이지 물체 배제 성능
인증이 아니다. 중립색 둘레 연결과 반복 관측은 같은 색 바닥·벽·로봇 세부를 제거하기에 불충분했다.

![B가 아닌 바닥·벽·로봇의 accepted component](false-positives.jpg)

![s1045 자기 DR 경로와 관측 patch 후보](own-goal-candidates.png)

그림의 hull은 관측 범위를 보여 주는 외곽선이다. 메모리에는 그 내부 전체를 채우지 않고 관측 pixel이
실제로 투영된 0.1 m cell만 쌓았다. RGB는 원본 녹화의 평가용 복사 그림이며 원본을 수정하지 않았다.

## 6. 옵션·사용 경계·남은 검증

| 옵션/API | 기본값 | on 또는 동작 |
|---|---|---|
| `goal_detection` | `off` | `floor_color_v1`: 자기 색 patch와 후보 누적 |
| `self_map` | `off` | goal on은 `odom_grid_v1` 필요; 이 재생은 기존 M1 DR |
| `goal_detection_options` | §3 `FloorGoalOptions` | HSV/ROI/광선·연결/격자·association 문턱 명시; 이번 확인 중 변경 0 |
| `camera_profile` | 호출 시 명시 필수 | `legacy` / `camera_v3`; RGB 녹화 보정과 일치해야 함 |
| `observe_goal_rgb` | goal off면 아무 동작 없음 | RGB·self ID·frame ID·시각·commanded servo만 받음 |
| `goal_target(static_B)` | 기존 static_B 동일 객체 반환 | on에서는 자기 후보 또는 `unknown`, static fallback 없음 |
| `snapshot()['self_goal']` | off면 키 없음 | own-odom 중심/관측 범위/신뢰도/관측 수·시각·상태 |

메모리의 상태 흐름은 `unknown → visually_seen → locally_confirmed_region`이다. `heard_candidate`는
설계의 향후 대화 입력 경계로 남겼으며 이번 모듈에는 peer 지도/관측 주입 API가 없다. `locally_confirmed_region`
역시 **검출 규칙상 반복 확인**이지 GT 목적지 인증이나 도착 성공 판정이 아니다. 실시간 executor·LLM 요청·
이동 제어에는 연결하지 않은 오프라인 구현이다. 지도의 기존 pose correction과 함께 생성할 수 있지만 이번
증거는 보정 off뿐이며, 나중의 pose-graph 수정으로 과거 B patch를 재배치하는 기능은 포함하지 않는다.

검출기와 `SelfWallMemory`에만 새 option/API를 추가했다. 기존 정적 목적지 경로는 바꾸지 않았다.
단위 시험의 정상 투영·양의 깊이 통과는 실제 B 투영 정확도를 대신하지 않는다. **현재 조건에서는 배포/제어
사용 준비가 되지 않았다.** 다음에 필요한 증거는 실제 B가 보이는 자기 RGB와 독립 camera pose, 유사색
음성 라벨이다. 구 자료에 HSV 문턱을 더 맞추지 않았다. 자기 지도 #405는 별도로 동결 상태를 유지한다.

### 출처·환경

- 색 분할/연결 영역: [OpenCV `inRange` 표준 예제](https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html).
  표준 hue wrap과 S/V floor를 사용한다. 여기서 정한 수치 문턱은 문헌 보편값이 아니다.
- 투영: [OpenCV 평면 투영](https://docs.opencv.org/4.13.0/d9/dab/tutorial_homography.html),
  [fisheye 보정](https://docs.opencv.org/4.13.0/db/d58/group__calib3d__fisheye.html).
  `harness/markerless_box.py:_pixel_ground_point`와 같은 보정 광선·전방 평면 교차 원리다.
- FK: `harness/visual_arm.py:camera_extrinsics`, K/D: `sim/masterpi_camera_profile.py`.
  camera v3의 고정 mount는 #401의 `sim/masterpi_camera_review_v3.py` 및 각 녹화 `bundle.json.camera_v3`와
  일치한다. 사용자 관찰 목표/기존 K/D이며 독립적으로 검증된 실물 hand-eye 보정이라고 주장하지 않는다.
- DR: #405 `CommandOdometry`, `experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json`,
  SHA-256 `126cadaa9265ed2ae2b034f675e67c227193a2e1678f6b0c82dd53b186e6fc72`.
  v7 재보정/지도 튜닝을 하지 않았으며 위치 오차 보정 성공을 이 작업으로 주장하지 않는다.
- [환경](environment.json): 기존 venv 사용, 새 설치 0. 그림만 기존 `outputs/self-map-plot-deps`를 재사용.
  시뮬레이션·렌더러·모델 호출 0, timing 비교/잠금 0. TensorBoard 변환은 이 대화의 생략 요청을 유지했다.
  초기 접촉표 도구가 시스템 Python의 PIL 부재로 한 번 실패해 기존 venv로 실행했다. 의존성을 설치하지 않았다.

## 7. 재현·산출물·시험

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
$PY -m pytest tests/test_floor_goal.py tests/test_floor_goal_evaluation.py tests/test_self_wall_memory.py -q
$PY experiments/2026-10-07-mapfree-goal-floor/code/replay.py --cases experiments/2026-10-07-mapfree-goal-floor/cases.json --split development --output outputs/NEW-floor-goal-replay
$PY experiments/2026-10-07-mapfree-goal-floor/code/replay.py --cases experiments/2026-10-07-mapfree-goal-floor/cases.json --split confirmation --output outputs/NEW-floor-goal-replay
$PY experiments/2026-10-07-mapfree-goal-floor/code/evaluate.py --predictions outputs/NEW-floor-goal-replay --manual-visibility experiments/2026-10-07-mapfree-goal-floor/manual_visibility.json --false-labels experiments/2026-10-07-mapfree-goal-floor/false_components.json
```

- 로컬 관련 **28 passed**: off bytes 골든, 어안/광선, 옵션/입력 경계, 누적 확인, 가시성 상한의 벽 가림 검사.
  `scripts/run_ci_tests.py`에 새 2개 시험을 등록했다. 전체 로컬 suite/물리 시험은 실행하지 않았다.
- [결과 원장](results.json), [입력 코호트](cases.json), [고정 코드·옵션](freeze.json),
  [수동 가시성 라벨](manual_visibility.json), [오검출 라벨](false_components.json)을 커밋한다.
- 상세 예측/mask/누적 snapshot·평가는 이 worktree의 `outputs/mapfree-goal-floor-v1/`에 있고,
  [artifact hash 목록](artifacts.json)이 경로·크기·SHA-256을 연결한다. raw는 로컬 보관이며 원격 백업으로
  표현하지 않는다. 각 `manifest.json`은 사용한 모든 RGB·명령·프레임 인덱스 해시를 보존한다.
  평가가 예측 파일을 변경하지 않았고 10건 모두 source/options/prediction hash가 봉인과 일치함을 확인했다.
- 기존 미추적 4개 파일의 해시 불변, #405의 HEAD `f3eeb6bf`·DRAFT 유지. 새 DRAFT PR은 #405 위에 쌓는다.
  양쪽 PR 모두 병합하지 않는다.
