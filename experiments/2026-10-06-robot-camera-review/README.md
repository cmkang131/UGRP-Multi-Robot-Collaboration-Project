# S2(v106) 손목 카메라 검토

상태: **공식 도면 기반 후보, 실물 보정 미완료. draft 유지·병합 금지.**
기준 main `b07f33aba278fda7434acaed0974c3d38f7b9ef0`.
모델 호출·실물 명령·동적 임무 재실행 없음. 기존 v106과 기본 프로필은 바꾸지 않는다.
원본은 `/Users/changmin/projects/ugrp/outputs/camera-review-20261006/`에만 보존한다.

**결론:** “cyan을 들면 실물에서도 앞이 가려진다”는 전제를 확인하지 못했다.
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
