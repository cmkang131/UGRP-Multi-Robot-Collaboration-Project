# ras1 초록 벽·점박이 바닥 DEV

2026-11-18 사용자 방향에 따른 시뮬레이션→실물 연결 범위와 최신 T01–T13 계약의
차이는 [Sim2Real 대응 기록](SIM2REAL.md)에 정리했다. 아래는11/12 실행 당시 기록이다.

사용자 요청(2026-11-12): 초록 벽, 회색 점박이 바닥. 바닥 점을 특징점으로
차체를 움직이며 벽을 인식하고 지도를 만들고, 터미널 실행 명령을 제공한다.

PR405 기반 작업 브랜치의 K/D와 명령 카메라 체인을 재사용하는 별도 DEV
색/접점 프런트엔드다. 기존 PR405 ego map 전체, 엄격한 수직 3-D 평면 검증기,
metric SLAM의 실물 성공을 승계하지 않는다. 초록색은 사용자가 지정한 벽의
후보이며, 실제 바닥이 바로 아래 보이는 접점만 투영한다. 바닥 Shi–Tomasi
특징점→전후 LK→RANSAC homography로 현재 바닥을 첫 관측에 정합한다.
추적 실패 시 누적 지도를 고정하고 다음 차체 명령을 내지 않는다.

카메라 자세는 기존 POSE_SEARCH(2000/740/2320/1320/1500)로 고정한다.
초기45프레임 노출 안정화 뒤, LK 전후 일치가 부족하면 ORB Hamming 상호 대응과
0.75 ratio로 같은24개/2.45px/공간분포 기하 관문을 다시 검사한다.
35의 전후100ms는 기존 하드웨어 실행 범위 안의 짧은 명령이며
명령을 실제 이동 거리로 환산하지 않는다. 기본은 정지 관측이고 --move가
명시된 경우에만 유한한 이동을 한다. 커널 actuator lease, SIGINT/HUP/TERM,
90초 호스트 watchdog, 각 펄스와 전체 finally 정지를 사용한다.

바닥 homography를 K로 분해해 영상 기반 회전·이동/카메라 높이를 얻고,
명목 카메라-차체 오프셋을 사용한 상대 차체 위치를 별도 표시한다.
수치 위치의 원점은 첫 명목 차체 위치(0,0)이고, 지도 화면은 현재 로봇을 항상
(0,0)·정면으로 두고 저장 접점/궤적을 반대로 옮긴다. 단위는 **카메라 높이**다.
카메라-차체 외부 파라미터·거리 축척·초록 물체의 수직 평면 여부는 미검증이다.
표시된 점은 관측한 초록/회색 접점이고 미관측 영역은 unknown이다.
HSV·연결 면적·분포 범위는 DEV 휴리스틱으로 명시하며 일반화 채택값이 아니다.
24 floor inliers와 2.45px reprojection은 기존 strict-wall 경로와 같다.

원본은 ras1 ~/green-wall-runs/<run>/에 보존하고, Mac에는 요약/대표 영상·그림만
회수한다. 새 대량 로컬 녹화는 Mac 여유7.6GiB로 하지 않는다.

공식 방법 참고:
- https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html
- https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html
- https://docs.opencv.org/4.x/dc/dc3/tutorial_py_matcher.html
- Malis & Vargas, Deeper understanding of the homography decomposition for
  vision-based control, INRIA RR-6303 (2007), https://hal.inria.fr/inria-00174036
- Campos et al., ORB-SLAM3 (2021), https://arxiv.org/abs/2007.11898
  (특징점·fisheye 모델 참고, 이 DEV를 ORB-SLAM3 실행으로 표현하지 않음).

실물 첫 전후6회는550–592 floor inliers와0.17–0.20px 중앙 재투영 오차를
얻었으나 nominal floor normal과 관측 방향이 약30deg 어긋나 pose는 전부 거부됐다.
fit_floor_normal.py는 그6개 DEV homography에서 공통 법선을 추정한다.
동수의 다른 법선 해가 있으면 거부하며, 새 촬영 전에 프로필을 고정한다.
이것은 RGB 기반 바닥 기울기 보정이며 렌즈 전체 재보정/미터 축척 확정이 아니다.

예: ras1에서 `python3 ~/green-wall-mapper-20261112/green_wall_mapper.py --move --pairs 3 --floor-profile ~/green-wall-mapper-20261112/floor-profile-dev-181359.json`.
overlay-map.avi는 정지 관측 순서의 3fps 요약이며 연속 실시간 영상이 아니다.
소스·시험·실제 이동/실패 결과는 summary.json으로 별도 기록한다.

## 새 고정 프로필 검증 결과

`91e2a8ed3394e68c13a29d87a1c54cb25a193102` / mapper SHA256
`7ade1ab0799c8a90743ba265530e6f1dc989e3a95e54f72068b78583d8383b50`
와 고정 floor-profile SHA256
`c7eee2314d66a4b6b27d652704ee8ad08535dedaf3209fc6bc9083e5e61d3862`로
새 실제 촬영 `ras1:/home/ras1/green-wall-runs/20261112-182136`을 실행했다.
전후 명령3쌍(6펄스),7정지 관측,6/6 floor homography 및 상대 pose 기하 관문을
통과하고 마지막 정지를 확인했다. inliers534–583, 중앙 재투영0.155–0.198px.
마지막 추정(+0.0154,-0.0248,+0.0445deg)은 카메라 높이 단위이며 외부 정답
위치/정확도/원점 복귀 오차를 측정한 값이 아니다.

전후 명령에 대해 이동은 주로 카메라 옆축에 나타났다. 실제 차체 축과 카메라
yaw/바퀴 명령축 정합은 미검증이며, 발행 명령에 맞춰 영상 추정을 강제 수정하지
않았다. 수직 벽 평면 검증도 여전히 false다. 과거 엄격한 벽 검증 성공을 승계하지
않고, 초록색/회색의 보이는 접점만 사용자 지정 목표 후보로 표시한다.

렌즈 역변환/기지 homography/기지 카메라 오프셋을 포함한 pose/법선 합의/추적 실패
동결/접점 구분의 시험6개가 ras1에서0.640초에 통과했다. 그 뒤 변경은 egocentric
화면 표시 및 저장된 overlay·pose 재생이다. 새 물리 실행으로 소급하지 않는다.
render_run.py는 저장7프레임/6pose만 재생했으며 추론을 다시 계산하지 않았다.

Linear HAN-36에 원인·실물 결과·한계와 대표 접점/지도/특징점 이미지를 기록했다.

## 머리 고정·벽에 접근/후퇴·설계 cm 지도 (사용자 후속 요청)

사용자는 실측 높이 대신 **모터값과 설계도**를 쓰라고 지정했다. 같은 팔 명령
2000/740/2320/1320/1500과 동결 기구 체인으로 계산한 카메라 높이는
23.0860865cm다. `wall_distance.py`는 이 높이로 RGB floor-motion과 벽 접점을
cm로 환산한다. 모터 속도나 명령 시간을 이동 거리로 환산하지 않는다.
독립적인 실제 cm 정확도 검증은 여전히 하지 않았으며 화면에도 design-scale로 표시한다.

`run_wall_distance.py`는 서보 쓰기를 전혀 하지 않고, 첫 짧은 차체 이동의
**관측 벽 거리 변화**로 어느 구동 패턴이 벽에서 멀어지는지 정한다. 이번에는
기존 API `left`가 후퇴, `right`가 접근으로 관측됐다. 이름으로 실제 방향을
가정하거나 전역 wheel map을 바꾸지 않는다. 첫 관측 normal fraction0.99945로
옆 이동이 아닌 벽 법선 방향 이동을 확인했다. 최대8 설계 cm 목표·유한 펄스,
특징점/접점/머리명령 일관성 검사·각 펄스/최종 정지·actuator lease를 유지한다.

고정 소스 `65e42db68891937c1ee4224c7a494e338f9ef0f8`, 실제 실행
`ras1:/home/ras1/wall-distance-runs/20261112-195538/`:

- 머리/팔 명령0회, 초기/최종 명령 자세 동일. 차체5펄스·6거리 관측·최종 정지.
- 카메라 기준 벽 거리 추정(cm): **17.563→19.993→22.776→20.400→18.299→17.353**.
  최대 증가5.213 설계 cm. 실제 물리 거리/원점 복귀 오차를 외부 정답으로 잰 값이 아니다.
- 40개 연속 RGB 원본(실제 시간 범위3.540초)과 명령 시작/정지 시각을 보존.
  render_distance.py는 실제 원본 시각 순서와 각 시점까지 얻은 측정 checkpoint만
  표시한다. 중간 pose 보간이나 가상의 움직임은 넣지 않았다. 원본 표시 영상은
  마지막 프레임 약0.5초 유지 포함4.08초, 별도3배 느린 재생본을 제공한다.
- 최초 실행은 checkpoint 경로 포맷 오류로 **차체0명령**에서 정지했다.
  수정 후 정지 촬영 smoke 통과, 같은 고정 소스로 위 실제 왕복을 수행했다.
- 관련 시험은 두 파일9개가 ras1에서0.775초에 통과했다. 거리 단위 변환,
  접점 이상치, 옆 이동 거부/관측 방향 선택을 포함한다.

결과·실패·raw 위치는 wall-distance-summary.json. 원본과 해시는 ras1에 보존하고
Mac에는 summary/대표 연속 영상/최종 그림만 회수했다.

다시 실행(ras1, 현재 고정 팔 자세가 일치할 때):
```sh
cd ~/green-wall-mapper-20261112
python3 run_wall_distance.py --floor-profile floor-profile-dev-181359.json --move --excursion-cm 5
```

## 실물 관측을 ActiveMapper에 연결

[릴리스의 ActiveMapper](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/models-20261112-solo-pair-status-v1/harness/active_wall_mapping.py)는
영상에서 얻은 관측을 명령 기반 위치와 함께 지도에 넣는다. 이 실물 경로는 같은
`ActiveMapper`의 `visual_odometry_v1` 모드에 자기 카메라에서 얻은 상대 위치와
벽·바닥 관측을 공급한다. 지도 원점은 첫 카메라의 바닥 투영점이다.
왜곡 보정과 색 마스크, 점박이 바닥의 LK/ORB 대응, 바닥 호모그래피는 기존
ras1 `Mapper`를 사용한다. 원본 RGB 경로에서 접점 아래의 관측된 바닥 픽셀만
자유 공간 근거로 기록한다. 새 위치나 접점이 없으면 이전 위치와 지도를
유지한다. 이 지도 검증 실행기는 매 프레임 `hold`를 반환한다.

저장소 루트에서 원본 프레임이 있는 위치를 지정한다. 실행은 저장된
`result.json`, `frames.jsonl`, JPEG를 읽으며 프레임의 SHA-256을 확인한다.

```sh
python experiments/2026-11-12-green-wall/replay_active_map.py \
  ~/wall-distance-runs/20261112-195538 --output active-map.json
```

요약 `result.json`만 회수한 경우는 `--source checkpoints`로 영상에서 이미
산출된 카메라 위치와 벽 접점만 사용한다. 이 모드에는 바닥 픽셀이 들어 있지
않으므로 자유 공간을 추가하지 않는다. 출력에 프레임별 위치·갱신 여부와
셀별 관측 근거를 기록한다.

2026-11-18 확인 결과, 11/12 실물 기록
`wall-distance-runs/20261112-195538`의 저장 관측 6/6건이 지도에 반영됐다.
5cm 격자의 벽 후보 셀 6개에 총 350개 접점 표본이 들어갔다. 카메라 추정
전후 변위는 최대 5.23cm였고, 실물 환산은 설계 높이 23.086cm를 썼다.
입력 요약 SHA-256
`642701b57b901199d1743efc3c00e2470c8cb7da68b35a45e1967fb6b81e04b4`.
원본 JPEG 재처리는 ras1 SSH 연결 시간 초과로 미실행했다. RGB 경로의
왜곡 보정·벽/바닥 지도 갱신·해시 검증은 합성 입력으로 별도 확인했다.
이전 실물 결과의 거리 정확도와 수직 벽 확정은 여전히 미검증이다.

## 실물 관측을 현재 운반 실행층에 연결

현재 실행층의 운반 코드는 `harness/carry_nav_v1.py`의 `CarryNav`와
`harness/place_memory_v1.py`의 `PlaceMemory`를 쓴다. ras1의 정지 관측에서
이미 계산한 벽 접점과 상대 이동을 `Ras1PlaceObservations`가 첫 차체 기준으로
변환해 같은 `PlaceMemory`에 넣는다. 경기장 벽이 주어지지 않은 지역
경로에서는 `CarryNav`의 주변 장애물 조회가 이 기억의 벽 점을 읽는다.
출력의 `visual_pose`는 같은 지역 좌표계의 상대 위치다.

기록만 확인할 때는 위 재생기에 `--source checkpoints`를 넘긴다. 새 촬영에서
장소 기억도 함께 저장할 때는 저장소 루트에서 아래 명령을 쓴다.

```sh
python experiments/2026-11-12-green-wall/run_wall_distance.py \
  --floor-profile experiments/2026-11-12-green-wall/floor-profile-dev-181359.json \
  --place-memory
```

`result.json`의 `carry_place_observations`에 차체 기준 위치와 벽 점을 기록한다.
보관된 실물 관측 6/6건에서 장소 기억이 갱신돼 벽 점 6개가 남았다. 자동 테스트로
기존 `CarryNav`의 주변 장애물 조회가 같은 벽 기억을 읽는 것을 확인했다.
새 옵션의 실물 운반 주행과 카메라를 옮기는 동안의 관측은 미검증이다.

## ugrp1 실물 왕복 재생

ugrp1에서 현재 팔 명령 자세를 고정하고 후진·전진 60ms 펄스를 한 번씩
실행했다. 양쪽 펄스와 마지막 정지까지 제어기에 기록됐다. 서보 명령은 0회였다.

매끈한 바닥 기록에서는 벽 접점이 보였고, 이동 전후의 바닥 대응은 자세
갱신에 사용할 수 없었다. 점박이 바닥 기록에서는 왜곡을 보정한 뒤 바닥점을
고정 높이의 평면에 투영하고, 기준 프레임에서 평면 이동과 회전을 추정했다.
거리 변화나 회전이 현재 투영과 맞지 않거나 지지점이 부족하면 관측을
거부한다.

ugrp1에서 같은 영상을 다시 처리해 출발·후진·복귀 세 지점에서
`PlaceMemory`를 거쳐 `CarryNav`가 벽 점을 5개씩 읽는 것을 확인했다.
기기에 저장된 렌즈 보정값으로 얻은 카메라 기준 벽 거리는 설계 축척으로
22.97 → 23.46 → 23.04cm였다. 시작 좌표계에서 벽 위치가 변한 폭은
같은 축척으로 약 0.014cm였다. 이 수치는 영상 정합의 내부 일관성이며
실측 거리 오차를 재는 값은 아니다. 다른 렌즈 모델에서는 거리 수치가 달라졌다.
자율 운반과 외부 거리 기준을 이용한 보정은 검증 전이다.

```sh
python3 experiments/2026-11-12-green-wall/replay_ugrp1_fixed_floor.py <run-dir> <lens.json>
```

재생은 `result.json`과 정지 후 촬영한 JPEG의 해시를 확인한다. 렌즈
프로필에는 `model: opencv_pinhole`, `K`, `D`가 있어야 한다.
`--ras1-fisheye-candidate`는 두 모델을 비교하는 옵션이다.
이 명령은 기록을 읽기만 한다.
