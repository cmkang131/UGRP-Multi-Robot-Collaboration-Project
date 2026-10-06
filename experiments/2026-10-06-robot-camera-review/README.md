# S2(v106) 손목 카메라 검토

상태: **v2 공식 SDK 샘플까지 비교했지만 실물의 거의 안 보임과 불일치. draft 유지·병합 금지.**
기준 main `b07f33aba278fda7434acaed0974c3d38f7b9ef0`.
모델 호출·실물 명령·동적 임무 재실행 없음. 기존 v106과 기본 프로필은 바꾸지 않는다.
원본은 `/Users/changmin/projects/ugrp/outputs/camera-review-20261006/`에만 보존한다.

**최신 결론:** 사용자가 순정 카메라에서 물건이 거의 안 보였음을 확인했다. 기존 전제를 실물의 일반적 특성으로 사용할 수 없다. v2에서도 동적 가림31.47%가 남았으며 아래 v2 절에 원인 분해와 재검증 목록을 기록했다.

**v1 당시 판정:** “cyan을 들면 실물에서도 앞이 가려진다”는 전제를 확인하지 못했다.
기존 시뮬레이션의 가림은 실제 저장 영상으로 확인되지만, 현재 장착값은 순정 도면과 다르고
우리 개체에서 검증되지 않았다. 별도 도면 후보에서는 가림이 줄었으나 일부 cyan은 계속 보인다.
실물에서 블록이 안 보였다는 관찰을 부정할 근거도, 내려놓기를 바로 없앨 근거도 없다.
현재 v106의 내려놓기는 **기존 SIM 프로필을 위한 우회 동작**으로만 해석한다.

![기존 기록과 같은 명령 자세의 두 카메라 비교](comparison.png)

## 조사로 먼저 고정한 비교

| 항목 | 현재 v106 | 새 진단 프로필 |
|---|---|---|
| ID | `ugrp1-icspring-fisheye-centered-mount-provisional-20260831` | `masterpi-camera-drawing-mount-review-v1` |
| 붙어 있는 곳 | `r3__gripper`, 손목 끝 집게 몸체 | 같음 |
| 손목 기준 렌즈 x/y/z | 67 / 0 / 13.6 mm | 도면 약 53.0 / 0 / 28.2 mm |
| 광축 | 공구축보다 **위로** 약 7.46° | 도면 명목 평행(0°) |
| 신뢰 범위 | 구조 추정, 한 자세의 옛 영상 적합; held-out 미완료 | 렌즈 전면의 도면 판독; 광학 중심·실물 장착각 미확인 |
| K·왜곡·해상도 | 아래 수치 | 그대로 유지; 순정 렌즈 전체를 재현했다고 하지 않음 |

새 위치는 기존 공개 사양 조사에 기록된 픽셀로 계산한다. `x=(407.5-283)*343/806` mm,
`z=(831.5-765)*185/437` mm. 약 ±2 mm는 도면 판독 오차이며 제조 공차가 아니다.
y=0은 기존 중앙 배치를 유지한 가정이다. 정확한 좌우 위치는 도면에서 가려져 있다.
각도는 공식 옆 도면의 평행 배치를 따른 명목값이다. 가림을 줄이려고 수치를 탐색하지 않는다.
기존 주석의 down-pitch와 달리 MuJoCo의 `-Z` 광축을 계산하면 국소 +z 방향 약 7.46°이다.

## 코드와 실물 기록

- `sim/masterpi_scene_v2.xml`: `robot → arm_base → shoulder_link → elbow_link → wrist_link → gripper → robot_cam`.
  `sim/masterpi_model_v3.py`와 `masterpi_robot_models.py`는 이 카메라를 그대로 유지한다.
- `sim/masterpi_camera_profile.py`: 640×480, fx=619.519454, fy=622.165488,
  cx=287.689106, cy=218.696866. fisheye D=(-0.01998195,-0.17075936,-0.25683182,0.96509334).
  K 기준 각도는 약 가로 54.5°, 세로 42.1°이며 raw fisheye 전체를 단일 FOV로 표현할 수 없다.
  MuJoCo `cam_fovy`는 센서 중심 기준 약 42.188°; 주점 비대칭 K의 상하 각도 합과 다르다.
- `sim/multi_masterpi_production.py`는 매 렌더 전에 기존 mount를 다시 설정하고 fisheye remap을 적용한다.
  따라서 XML만 새 후보로 바꿔 기존 실행기에 넣는 것은 유효한 이관이 아니다.
  이번 프로필은 독립된 **진단 XML 변환**에만 사용하며 기존 실행기에 연결하지 않는다.
- `sim/navigation_camera_profile.py`의 차체 고정 `nav_cam`은 별도 simulator-only 카메라다.
  S2는 `sim/solo_cyan_v106.py → CameraRobotPort.capture()`의 `robot_cam`을 사용한다.
- `harness/zone_pair_highpose.py`: HIGH={3:896,4:2035,5:1894,6:1500}, 집게 닫기 1500.
  명령 FK는 집게 중심 (203.21,0,149.86) mm, 공구축 -40.05°다. 명령은 실제 관절 측정이 아니다.
  `harness/zone_final_pair_vision.grasp_postures()`의 hover는 {3:807,4:1897,5:2187,6:1500},
  마지막 바닥 파지는 {3:1269,4:2052,5:2494,6:1500}; 그 사이 7단계 하강을 유지한다.
- 공식 MasterPi 조립 사진과 도면은 카메라가 집게 위에서 팔과 함께 움직이는 구조를 보여 준다.
  `codex/masterpi-public-specs` 원격 브랜치는 현재 목록에 없지만 그 조사 기록은
  [기존 README](../2026-09-28-masterpi-public-specs/README.md)에 보존돼 있다.
- `calibration/masterpi/hand_eye_trials.jsonl`의 24개 관측은 측정값이 비어 있고,
  `static_measurements.json`에도 실측 출처가 없다. [#385](https://github.com/kcm0127-dotcom/ugrp/pull/385)는
  Windows의 JPEG 수신·팔 dry-run 기록이며 운반 자세/카메라 외부 보정 증거가 아니다.
  그 Windows 원본 사진을 이 Mac에서 확인한 것으로 보고하지 않는다.
- 순정 HBVCAM-V2101의 공식 170°는 H/V/대각 축이 불명이다. 170°를 MuJoCo fovy로 넣지 않는다.
  공개 SDK의 일반 5계수 보정값도 현재 4계수 fisheye와 호환되지 않는다.

## 방법·실행 계획 (결과 전에 고정)

고전적인 eye-in-hand 식은 `A X = X B`이며, 표준 OpenCV는 Tsai–Lenz/Park–Martin 등으로
여러 자세의 카메라-손목 변환을 구한다. 공식 MuJoCo의 부모 몸체 기준 위치와 -Z 광축,
OpenCV의 K/왜곡 모델을 각각 확인한다. 최근 Wise 등의 RWHEC 연구도 관측의 식별 가능성을
따로 다룬다. 좋은 영상 한 장 또는 보정 목적함수의 최적값은 실물 일치를 증명하지 않는다.
이번에는 새 물리 자료가 없으므로 보정 알고리즘으로 임의 수치를 적합하지 않는다.

1. 기존 `s2-graduation-fae1fc4a-s1026-P2-2-place`의 controller `carry` 상태이면서 HIGH 명령인
   **모든 저장 프레임**을 읽어 기존 cyan HSV 마스크로 면적을 잰다. 원본 JPEG 해시 전부 확인.
   전체 640×480과 remap의 유효 픽셀을 각각 분모로 사용한다. cyan 이외가 모두 벽은 아니다.
2. 기존 표준 `Scene`이 저장한 `scene.xml`을 재사용한다. t=105/180/270초에서 기록된
   로봇 위치·yaw와 화물 자세를 사후 진단으로 넣고 팔은 동일한 HIGH 명령 자세로 고정한다.
   실제 관절·base roll/pitch가 저장되지 않아 원본의 정확한 물리 재생은 아니다.
3. 현재 mount와 도면 후보만 비교한다. K/D/렌더 크기·near clip·물체·접촉·조명 동일,
   카메라의 massless visual만 함께 옮긴다. `mj_forward`와 정지 RGB 6장, `mj_step=0`.
   `agent_lock.py status == null`일 때만 자기 PID로 acquire하고 `finally`에서 자기 잠금만 release.
4. 새 소스는 관련 시험 통과 후 먼저 commit/push한다. raw와 결과에는 실행 SHA·입력 해시를 남긴다.

## 참고 자료 (2026-10-06 확인)

- [Hiwonder MasterPi 공식 제품](https://www.hiwonder.com/products/masterpi),
  [공식 치수도](https://cdn.shopify.com/s/files/1/0084/2799/5187/files/masterpi_01173667-020d-4baa-8ec8-6ff4a45b6220.jpg?v=1716200111):
  제품 페이지 열람·도면 새 다운로드·직접 시각 확인. 이미지 원본은 로컬에만 보존.
- [Hiwonder 조립·부품 문서](https://docs.hiwonder.com/projects/MasterPi/en/latest/docs/1.getting_ready.html): 본문 확인.
  조립 팔 개별 이미지의 web fetch는 실패했으나 공식 URL을 직접 다운로드해 시각 확인했다.
  [집게 위 카메라 사진](https://docs.hiwonder.com/projects/MasterPi/en/latest/_static/media/1.getting_ready/1.1/image1.png).
- [MuJoCo camera 공식 문서](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-camera):
  부모 좌표계·-Z 광축·principalpixel·focalpixel·resolution 규칙 확인.
- [OpenCV calib3d](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html):
  `calibrateHandEye`와 Tsai–Lenz/Park–Martin 표준 구현 확인.
- [Wise 외, IJRR 2026 / arXiv v2](https://arxiv.org/abs/2507.23045v2),
  [저자 공개 코드](https://github.com/utiasSTARS/certifiable-rwhe-calibration):
  초록·README·입력 형식 확인; 식별 가능성과 전역 최적성 구분. 코드 실행/우리 로봇 적용은 미실행.
- [Hiwonder Camera.py 고정 SHA](https://github.com/Hiwonder/MasterPi/blob/11b0cb04ada14be7c391e6c865ac705f903a95e7/Camera.py):
  이번 웹 본문 접근은 두 경로 모두 cache miss라 **재확인 미완료**, 추가 재시도 중단.
  SDK 수치 비교는 기존 공개 사양 기록에 한정하며 새 실물 증거로 취급하지 않는다.

## 재검증 범위

실물 렌즈 모델·장착 위치·각도를 먼저 측정하고, HIGH/hover/파지·여러 pan에서 보정용과
독립 확인용 영상을 모아야 한다. 새 mount를 채택하려면 위치 추정의 카메라 원점/광선,
벽-바닥선 추출·PF, cyan 접근/바닥 투영·파지 확인·blind-close 기준을 모두 다시 확인한다.
화물이 화면 밖이면 RGB 화물 추적/미끄러짐 감지는 약해질 수 있다. 안 보임을 낙하로 판정하면 안 된다.
기존 v92/v98 카메라 보정과 v106 결과를 새 프로필의 성공으로 승계하지 않는다.
내려놓기 제거 여부는 새 프로필에서 벽 관측·위치 오차·파지 유지·문 통과·최종 놓기를 확인한 뒤
**새 실행 번들**에서 결정한다. 이번에는 제어기·기존 번들·정지 정책을 바꾸지 않는다.

## 실행 기록

- `965f2f31`: 관련 10시험 통과 후 commit/push. 저장 프레임 1,320장 해시 확인 성공.
  전체 화면 cyan 중간값 82.3525%, 유효 렌즈 픽셀 기준 99.9849%.
- 첫 정지 렌더는 `shoulder_pitch`라는 잘못된 진단 관절 이름 때문에 이미지 생성 전에 실패했다.
  기존 모델은 `shoulder`/`elbow`를 쓴다. `render-v1/`의 부분 XML·잠금 반환 기록을 보존했다.
  기존 NamespacedMasterPi의 이름표를 따르고, 실제 v3 XML과 대조하는 시험을 추가했다.
  값·자세·카메라 후보는 바꾸지 않았다. 동일 원인 재발 시 추가 실행하지 않는다.
- `ff6a3aaa` (`render-summary.json`에 전체 SHA): 관련 **11시험 통과**, commit/push 후
  정지 렌더 6장 완료. 렌더 작업 약0.88초, 잠금 점유 약1.86초, 반환 뒤 `status=null`.
  각 쌍의 qpos SHA-256가 같아 자세·물체 차이 없이 mount만 비교했음을 확인했다.
  `mj_step=0`, 모델 호출0, 제어 명령0. 동적 운반·실물 성공률은 측정하지 않았다.
- 결과 포장 첫 시도는 기존 venv의 matplotlib 부재로 중단했다. 환경을 늘리지 않고
  기존 Pillow로 원본 RGB를 그대로 나란히 배치했다. 부분 `comparison.json`도 보존했다.
  이는 렌더 실패 재발이나 카메라 수치 변경이 아니다.

## 측정 결과와 해석

| 자료 / SIM 시각 | 프레임 수 | cyan / 전체 영상 | cyan / 유효 렌즈 픽셀 |
|---|---:|---:|---:|
| 실제 저장 HIGH carry 전체, 중간값 | 1,320 | 82.3525% | 99.9849% |
| 정지 재구성 기존 mount, 105초 | 1 | 61.3363% | 74.5668% |
| 정지 재구성 도면 mount, 105초 | 1 | 21.7503% | 26.3753% |
| 정지 재구성 기존 mount, 180초 | 1 | 60.9219% | 74.0634% |
| 정지 재구성 도면 mount, 180초 | 1 | 21.3734% | 25.9159% |
| 정지 재구성 기존 mount, 270초 | 1 | 60.3317% | 73.3490% |
| 정지 재구성 도면 mount, 270초 | 1 | 20.8903% | 25.3303% |

유효 픽셀은 remap 좌표가 입력 영상 안에 완전히 들어오는 251,679개다(전체307,200).
테두리 보간 픽셀은 전체 면적에는 들어가지만 유효 분모에서는 제외한다.
전체 저장 구간의 유효 가림 범위는99.9825–99.9885%다. 각 원본 JPEG 해시·시각·면적은
`frames-audit/frames.jsonl`에 있다. 사전 등록된 새 확증 코호트가 아니라 과거 DEV 영상의 사후 분석이다.

**정지 기존 mount도 원본99.98%를 재현하지 못했다.** 측정 관절·차체 roll/pitch·손가락 접촉 자세가
없어 HIGH 명령값을 사용한 한계이며 정확한 원인은 아직 분리하지 못했다. 따라서 원본99.98%와
후보25–26%를 직접 비교해 실물 개선율이라고 말하면 안 된다. 비교 가능한 두 정지 조건의
평균은73.9931%와25.8738%다. 완주·wall 관측 성공·위치 추정 정확도 결과가 아니다.

카메라와 물체가 집게에 대해 고정돼 있다면 팔을 들어도 둘 사이 상대 배치는 유지된다.
시야 안팎은 운반 높이 자체보다 **렌즈 높이·방향·파지 깊이·블록 크기**로 결정된다.
도면 후보는 렌즈를 손목 기준14.02 mm 뒤·14.55 mm 위로 옮기며, 이 HIGH 자세에서는
바닥 높이가약172.9→193.1 mm, 광축은아래32.59→40.05°가 된다. 블록 위쪽이 화면 아래로
내려가 배경이 더 보이지만 가까운 바닥을 더 보게 돼 먼 벽 관측까지 좋아진다고 할 수 없다.
공식 구성품은3×3 cm 블록이며 SIM cyan은34×40×32 mm이다. 실제 사용 물체 치수는 미확인이고
이번 비교에서는 물체를 바꾸지 않았다. 이 차이도 실물 영상과 대조해야 한다.

## 재현과 보존

```sh
# 공통 세션으로 실행하며 render 모드는 내부에서 공용 잠금을 확인/획득/반환한다.
python3 scripts/ugrp_session.py run camera-review-render-NEW -- \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python scripts/review_masterpi_camera.py render \
  --source /Users/changmin/projects/ugrp/outputs/s2-graduation-fae1fc4a-s1026-P2-2-place \
  --output /Users/changmin/projects/ugrp/outputs/camera-review-NEW
```

`analyze` 모드는 원본 이미지 읽기만 한다. `export_review.py`는 기록을
기존 native TensorBoard 변환기에 넘기고 event를 다시 읽어 수치를 검증한다.
완료된 snapshot은 덧쓰지 않는다. 같은 호스트에서 재포장할 때 새 출력 경로를 정해야 한다.
공유 보기 root는 `/Users/changmin/projects/ugrp/outputs/tensorboard`, 새 snapshot은
`1006-camera-review-v1`이다. saved-1320 / static-old / static-drawing / render-error를
서로 다른 조건으로 표시한다. raw MP4는 이번 정지 진단에 없고 동영상 등록도 없다.
정지 RGB·입력 XML·실패 흔적·공식 이미지·해시·세션 로그는 로컬 보관이며 원격 백업이 아니다.

## TensorBoard와 최종 확인

- [저장된 비교 대시보드 링크](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fvalid_fraction%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Ffull_fraction%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fframes%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%5D&smoothing=0&runFilter=%5E1006-camera-review-v1%2F#timeseries). 새 이벤트 readback 및 기존 서버 scalar API 전체 수치 일치.
- 기존 `tensorboard-s2-grad` 서버 PID52016, 공용 logdir 확인; 서버 시작/재시작/종료 없음.
- Chrome 강에서 링크를 열었으나 최초 로드와 1회 새로고침 모두 빈 화면이었다. 2회 같은 표시 문제로 UI 확인 중단.
- 새 카드 표시·pin 적용·HParams 열 재적용은 **미확인**. `tensorboard-view.json`에는 자기 키만 추가했다.
- `delivery-verification.json`, `tensorboard-readback.json`, `raw-manifest.json`에 검증 경계와 로컬 원본 해시 보존.
- 새 번들 ID·workflow 번호 없음. 기존 표준 Scene 산출물을 읽는 진단이며 실행 가능한 연구 프로필로 등록하지 않았다.


## 2026-10-06 사용자 실물 관찰에 따른 v2 추가 검토

사용자는 **순정 MasterPi 카메라였고, 들고 있을 때 물건은 거의 안 보였다**고 확인했다.
이는 실물 관찰 근거다. 당시 원본 영상·서보값·물건 치수는 없으므로 수치 가림률이나 특정 자세의 측정값으로 바꾸지 않는다.
기존 파일의 `icspring` 이름을 다른 카메라를 사용했다는 증거로 취급하지 않는다.

실행 전 고정한 새 후보 `masterpi-camera-official-sdk-sample-review-v2`는 v1 도면 mount와
공식 SDK `11b0cb04ada14be7c391e6c865ac705f903a95e7`의 Camera.py/NPZ가 만드는 **출력 영상**을 조합한다.
Camera.py 원문은 이번에 공식 GitHub raw로 확보해 확인했다(이전 웹 cache miss 기록은 당시 이력).
Brown-5 + getOptimalNewCameraMatrix(alpha=0) + initUndistortRectifyMap이다. ROI slice는 없으며,
시뮬레이터는 이 보정된 출력 광선을 직접 렌더한다. 기존 fisheye D4를 섞지 않는다.
공개 NPZ는 개체·보정 품질이 미확인이라 **사용자 실물 보정 프로필이 아니라 공식 샘플 진단 후보**다.
공식 170°는 축/투영식이 없어 fovy로 사용할 수 없다. 출력 K에서 약29.23°×21.49°가 계산되지만
170° 렌즈와의 관계·공개 샘플의 적합성은 미확인이다. 원하는 가림률을 얻기 위한 파라미터 탐색은 하지 않는다.

실행 계획: 기존 standard Scene XML의 동일 HIGH 정지 3개 및 동일 상대 화물 자세를 유지한 공식 lift 3개를
baseline / 위치만 / v1 / v2로 비교한다. 그 뒤 고정 fixture에서 **집게 닫기·들기 1회**만 실시한다.
기존 접촉·물체 34×40×32 mm·질량·마찰·관절·기본값·번들은 유지한다. 강체 파지 가정은 정지 진단에만 쓰고
동적 실행에서는 weld/화물 추종/상태 보정 없이 정상 접촉으로 진행한다. HIGH 대기는 진단용1초로 단축하므로
S2 carry 인수로 인정하지 않는다. 차체 구동0, 모델0, 실물 명령0, S2 실행0. wall 예산45초, 잠금1분 이내 목표.

공식 color_sorting.py의 lift 요청은 `(0,6,18) cm, pitch=0°, 1500 ms`다.
공식 IK 수학 부분만 격리 계산한 nominal PWM (3,4,5,6)=(695,2413,782,1500)에
공식 Deviation.yaml (54,53,89,64)을 더하면 **(749,2466,871,1564)**다.
HIGH=(896,2035,1894,1500), 공구각−40.05°와 같지 않다.
공식 init 요청 `(0,8,10), -90°`는 범위 탐색 결과−58°이며, nominal=(508,2414,1238,1500)이다.
예제는 open=2000, close=1500을 쓰지만 **lift→open→close** 순서이며 바닥 접근·들고 주행하는 표준 절차를
제시한 것으로 읽으면 안 된다. “MasterPi 유일한 기본 운반 자세”는 확인 못 했다.
SDK tool=100 mm, v3 pad centre=86.85 mm, shoulder 기준도 달라 SDK 목표 높이18cm를 SIM 실제 높이로 치환하지 않는다.

### v2에서 추가 확인한 자료

- [공식 카메라 사양 그림](https://cdn.shopify.com/s/files/1/0084/2799/5187/files/7e29db14e5705c63b085c49c4e34136d.jpg?v=1716199523): 직접 판독, HBVCAM-V2101 V11/640×480/170°(축 미지정), 초점거리 범위30cm–무한대.
- [공식 Camera.py](https://github.com/Hiwonder/MasterPi/blob/11b0cb04ada14be7c391e6c865ac705f903a95e7/Camera.py), [MasterPi.py](https://github.com/Hiwonder/MasterPi/blob/11b0cb04ada14be7c391e6c865ac705f903a95e7/MasterPi.py): 원문 전체 확인. 처리된 cam.frame이 MJPEG로 전달됨.
- [공식 color_sorting.py](https://github.com/Hiwonder/MasterPi/blob/11b0cb04ada14be7c391e6c865ac705f903a95e7/functions/color_sorting.py), [공식 IK](https://github.com/Hiwonder/MasterPi/blob/11b0cb04ada14be7c391e6c865ac705f903a95e7/masterpi_sdk/kinematics_sdk/kinematics/arm_move_ik.py), [역기구학](https://github.com/Hiwonder/MasterPi/blob/11b0cb04ada14be7c391e6c865ac705f903a95e7/masterpi_sdk/kinematics_sdk/kinematics/inversekinematics.py): 수학·서보 매핑·sequence 확인, 보드 호출 없음.
- 표준 방법: OpenCV Brown 보정/출력 K 및 hand-eye의 좌표 변환을 그대로 사용. 위 OpenCV·MuJoCo 문서와 Wise2026 논문/공개 코드를 다시 확인했다. 새로운 최적화나 파라미터 fit은 하지 않았다.
- raw 출처/해시/계산: `/Users/changmin/projects/ugrp/outputs/camera-review-20261006/references-v2/{manifest,derived}.json`.

### v2 결과: 실물 관찰과의 차이가 남았다

실행 SHA **ac54bb5496f8d675c2527dc5489d1a4a9cd6ee13**, MuJoCo3.12.0, OpenCV5.0.0.
19.20 SIM초 / 15.68 wall초, 76,800 step, 고정 팔 단계6개, 동적 시각102개와 정지6개를
각4조건으로 렌더했다(**432 PNG 전부 해시 확인**, 동시각 qpos 해시4개 일치).
잠금은 자기 PID72461로 얻고 정상 반환했다. 종료 후 status=null, 자기 session 종료 확인.
실물 실행·S2 재실행·차체 구동·모델 호출·weld는 모두0. 다른 프로세스/PR/worktree 변경 없음.

아래는 **cyan / 유효 영상 픽셀**이다. old 렌즈의 검은 테두리는 제외했으며,
v2는 공식 remap 유효 범위(전체의99.9733%)로 별도 계산했다. 다른 분모를 섞지 않는다.
전체 영상 기준 비율도 [comparison-v2.json](comparison-v2.json)에 함께 저장했다.

| 조건 | 이전 mount/K | 위치만 도면 | v1: 위치+방향 도면 | v2: 도면+SDK 출력 |
|---|---:|---:|---:|---:|
| 정지 HIGH 3장 평균 | 73.993% | 8.577% | 25.874% | 23.489% |
| 동적 HIGH 단계 12장 평균 | 97.889% | 12.564% | 30.203% | **31.467%** |
| 동적 공식 lift 단계 16장 평균 | 97.933% | 12.603% | 30.226% | **31.467%** |

v2 정지3장의 범위22.436–24.428%; 동적 HIGH/lift28장 모두31.4667%였다.
동적 단계에는 이동 중과 유지 시각이 포함된다(5Hz와 단계 끝 표본; 중복 시각 없음).
기존 S2 실제 저장 운반1320장의 중간값99.9849%와 새 고정 팔 fixture는 **서로 다른 실행**이다.
그 기록의 수치를 새 후보 성능으로 바꾸지 않는다. 새 실행에는 주행이 없어서 하중 이동 성공도 아니다.
화물 중심은 바닥 약15.89mm → HIGH140.57mm → 공식 lift212.21mm로 올라갔고,
끝의 손목 좌표는(92.164,0.00036,0.189)mm로 유지됐다. 정상 접촉으로 한 번 든 진단 결과이며
파지 안정성·보존 시간·새 조건 성공률의 검증은 아니다.

![같은 qpos의 카메라 비교](comparison-v2.png)

### 25–26%가 남은 기하적 이유

1. **렌즈 위치:** 기존(67,0,13.6)mm에서 도면(52.982,0,28.152)mm로 옮기면
   14.018mm 뒤/14.552mm 위로 간다. 방향+K 고정 시73.99→8.58%이므로 가장 큰 차이는 장착 위치다.
   이는 순차 요인 비교이며 위치·방향·K 효과를 독립적인 합계로 일반화하지 않는다.
2. **방향:** 기존 광축은 공구축 위7.459°이고 도면의 명목 축은0°다.
   도면 방향으로 바꾸면 시선이 상대적으로 내려가 블록 윗면이 더 들어온다(8.58→25.87%).
   “가장 잘 안 보이는” 기존 위쪽 각도를 채택하지 않았다. 실제 mount 각도는 여전히 미측정이다.
3. **물체와 거리:** t270 정지 재구성에서 화물 중심은 손목 기준(96.692,0.004,−2.385)mm,
   도면 렌즈에서는 약43.710mm 전방/30.537mm 아래다. 크기34×40×32mm의 모서리들은
   광축 아래 **11.475–60.429°**에 걸친다. 중심이 화면 밖이어도 윗모서리가 화면 아래쪽에 남는다.
   동적 HIGH에서는 더 깊게 잡혀 중심x92.166mm, 최상단 모서리9.765°가 된다.
4. **FOV/주점:** old의 K-pinhole은54.54×42.15°, 원영상은 별도 fisheye remap이다.
   v2 K'는 fx1227.187/fy1252.122/cx323.714/**cy113.402**이고 출력29.23×21.49°다.
   중앙 주점이 아니므로 아래쪽 시야는 atan((480−113.402)/1252.122)=**16.32°**까지다.
   9.765° 모서리가 투영되는 y≈329px부터 화면 끝까지 블록이 남는 것이 동적31.47%와 맞는다.
   단순히 “FOV가 좁으니 물건이 사라진다”는 결론도 틀렸다. 공식170°의 축·투영식·해당 NPZ의
   기기 연결 정보가 없으므로 실제 순정 영상의 광선을 확정하지 못했다.
5. **HIGH와 공식 자세:** 같은 상대 물체를 강체로 옮긴 정지 비교는 v1 평균25.874→25.889%,
   v2 23.489→23.497%로 거의 같다(조명/색 분할의 차이).
   눈-손/물체 변환식 `T_camera_object = inverse(T_gripper_camera) * T_gripper_object`에서
   팔의 세계 변환은 상쇄된다. 팔을 높이거나 수평으로 펴는 것만으로 가림이 없어지지 않는다.
   다만 세계 광축은 HIGH−40.05°와 공식0°가 달라 **벽·바닥이 보이는 범위는 크게 달라진다**.
   실제 동적 후보의 마지막 각도는 HIGH−42.65°, 공식−1.38°로 명령값과도 차이가 있다.
6. **집게 크기:** v3는 도면 끝94.0mm/패드14.3mm/패드 중심86.85mm/열린 폭46.7mm를 사용한다.
   SDK의100mm는 닫힌 끝을 가리키는 가상 IK 길이여서 패드 위치와 혼용할 수 없다.
   [공식 구성품](https://docs.hiwonder.com/projects/MasterPi/en/latest/docs/1.getting_ready.html#packing-list)은
   3×3cm 블록으로 적혀 있다. S2의34×40×32mm와 다르지만 사용자 물건의 크기/3번째 치수는
   미확인이므로30mm 정육면체로 바꾸지 않았다. 큰/비스듬한 윗면과 잡힌 깊이가 남는 가림에 관여한다.

**결론:** 공식 근거만 반영한 후보는 실물의 “거의 안 보임”을 재현하지 못했다.
31.47%를 성공으로 판정하지 않는다. 실제 출력 raw/보정 여부와 K/D, 렌즈 중심·각도,
실제 블록 크기와 잡힌 깊이/관절 자세가 남은 차이의 확인 대상이다. 렌즈의 공식 초점 범위는
30cm–무한대인데 들린 물체는 수cm 거리다. 현재 렌더는 실제 근거리 흐림을 모사하지 않으며,
근거 없는 blur/가림 마스크로 물체를 지우지 않았다.

### v106 내려놓기 OFF 옵션 후보와 재검증

설계 후보(미구현): 새 번들의 `carry_relook=off_candidate`, 기존 값은 `setdown_relook_v1`.
새 프로필/보정 해시가 맞을 때만 후보를 선택하고, 체크포인트의 중간 내려놓기/재파지만 건너뛴다.
목적지의 최종 놓기는 유지한다. 현재 분기는 `harness/zone_solo_cyan_v106.py:453`에서
가림률과 무관하게 체크포인트마다 호출된다. 현재 기본값·제어기·v106 번들은 바꾸지 않았다.
`runtime_admitted=false`인 이번 v2는 운영용 선택/활성화가 불가능하며 별도 새 번들이 필요하다.

- **카메라/위치:** 실제 순정 raw와 처리된640×480 화면을 함께 보존하고 K/D, 주점, mount를
  여러 자세에서 보정; 독립 자세/정적 지도의 벽·코너로 검증. old fisheye ray/PF 보정 재사용 금지.
  `_sync_real_camera_mount()`가 old를 덮어쓰는 production 경로도 새 버전 adapter에서 분리해야 한다.
- **파지:** 변경된 픽셀→로봇 투영으로 접근·정렬·집기부터 다시 검증. 공식 PWM 편차·yaw 원점·
  SDK tool/물리 패드 차이 확인. 물체가 안 보임을 낙하로 간주하는 hold/loss 검사를 재검토한다.
- **하중 이동:** HIGH 및 수평 lift 각각의 벽 관측, 지연, 위치 오차, 파지 유지/미끄러짐,
  가감속·회전·문 여유·최종 놓기를 OFF/기존 ON 조건과 새 증거로 비교한다.
  먼저 짧은 하중 구간에서 검증하고 S2 전체는 별도 요청/계획에서 시행한다. 이번에는 실행하지 않았다.
- **판정:** 전면이 조금 더 보인다는 것과 신선한 위치 추정 성공은 별개다. 이번 결과만으로
  내려놓기가 필요 없어졌다고 결론내릴 수 없다. 사용자 실물 관찰은 기존 보편적 가림 전제를 반박하지만
  새 프로필 채택과 OFF 정책의 임무 성공까지 증명하지 않는다.

### v2 보존·검증

바뀐 프로필/진단의 시험 `tests/test_masterpi_camera_review_v2.py` **5 passed** 뒤 commit/push,
그 SHA로 실행했다. 시뮬레이션 재시도0. 원본/이전v1/다른 번들은 보존했다.
raw는 `/Users/changmin/projects/ugrp/outputs/camera-review-20261006/render-v2/` 로컬이며 원격 백업이 아니다.
[계산/요약/원본 해시](comparison-v2.json), [공식 소스 해시](official-sdk-manifest.json),
[공식 수치 계산](official-sdk-derived.json)을 Git에 보존한다.

TensorBoard 신규 `1006-camera-review-v2` 11개 run은 같은 한 번의 실행에서 나눈 진단 뷰이며
독립11회 실험이 아니다. 이벤트 재읽기·기존 서버 scalar API 전부 일치.
비교 영상은432장 중 동적102시각을4열로 묶은5fps 파생 영상으로, SIM 시각 자막이 기준이다.
102프레임 재디코드, 미디어 등록과 HTTP200 확인. 모델 응답시간은 호출이 없으므로 미측정.
`lift-sequence` commands=6은 고정 팔 단계 수이며 76,800개 내부 목표 갱신과 구분했다.
[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1006-camera-review-v2%2F#timeseries),
[비교 영상](http://127.0.0.1:6007/video/5061cfca0c0d4067d5b9).

CI `ac54bb54` shard4는 MuJoCo 없는 offline 환경에서 시험 파일의 top-level 모델 import로 수집 실패했다.
[pytest 공식 optional dependency 방법](https://docs.pytest.org/en/stable/how-to/skipping.html#skipping-on-a-missing-import-dependency)과 기존 모델 시험을 따라 모델 XML 시험3개만 함수 안에서 importorskip한다. 광학/좌표/마스크 시험은 계속 실행한다. 물리값·프로필·시뮬레이션 코드는 바꾸지 않았다. 실패 로그를 raw에 보존했다.

최종 관련 시험2파일: MuJoCo 있는 환경 **16 passed**, 없는 환경을 재현하면 **13 passed / 3 skipped**.
새 Chrome 강 탭에서5개 고정 카드와 run 목록 표시까지 확인했다. run 선택 중 native UI가
noWindowsAvailable을 반환했고 재조회에서 다른 작업의 활성 탭이 확인돼 추가 UI 조작을 중단했다.
화면의 숫자 선택/HParams 열 재적용은 미완료다. 서버/다른 탭 설정은 변경하지 않았다.
