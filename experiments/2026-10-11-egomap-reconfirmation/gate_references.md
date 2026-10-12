# 자기 RGB 재확인 게이트: 조사·적용 범위

2026-10-11 PR #405 DEV 후보. 고전·최근 방법의 **후보 제안 → 기하 검증 → 별도 관측에서 재검증** 순서를 적용한다. 제어기는 자기 RGB, 고정 카메라 보정, 자기 발행 명령과 기존 자기 추정 궤적만 읽는다. GT·실시간 정답 지도·LLM 입력은 없다.

## 확인한 1차 자료

- Campos et al., [ORB-SLAM3, arXiv:2007.11898](https://arxiv.org/abs/2007.11898), 2020/2021. 기존 관측과 현재 영상의 장소 후보를 기하적으로 검증하는 방식. 실제 저자 [LoopClosing.cc](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/master/src/LoopClosing.cc)의 `NewDetectCommonRegions`, `DetectAndReffineSim3FromLastKF`를 확인했다. 반복 후보마다 Sim3를 재검증하며 3회 일치 후 수락하고, 실패가 누적되면 후보를 버린다. 이 후보는 그 3D/Sim3 추정기를 구현하거나 동일 성능을 주장하지 않는다.
- Mur-Artal et al., [ORB-SLAM2 Initializer.cc](https://github.com/raulmur/ORB_SLAM2/blob/master/src/Initializer.cc), `CheckHomography`: 양방향 투영 오차를 검증한다. 현 저장소 `own_rgb_homing`의 ORB 1000개·상호 ratio .75·최소15·RANSAC 3px·300회·.99와 2D χ² 5.991 octave 분산을 재사용한다. 양방향 각각의 2D 잔차 게이트이며, 같은 표본에서 추정한 H나 상관 프레임에 대해 정밀한 전체 오수락률을 주장하지 않는다.
- [OpenCV calib3d: findHomography/decomposeHomographyMat](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html): RANSAC 외점 제거, 평면 호모그래피 및 가능한 회전 분해를 사용한다. 명령 yaw만 변한 경우를 두 관측으로 세지 않도록 분해 후보들 중 최소 광학 회전각도 3° 이상을 요구한다. 분해 실패는 거부한다.
- [MPRF: Multi-modal Loop Closure Detection with Foundation Models in Severely Unstructured Environments, arXiv:2511.05404](https://arxiv.org/abs/2511.05404), 2025. 초록에서 확인한 최신 구조는 후보 검색과 명시적 6-DoF 기하 검증 분리다. LiDAR·기반 모델·별도 학습은 현재 입력 경계와 무LLM 비교에 필요하지 않아 가져오지 않았다. 초록 이상 세부·성능 수치는 이 후보 근거로 사용하지 않는다.
- 기존 저장소의 [VT&R keyframe 출처](../2026-10-09-teach-capture/README.md): 자체 재튜닝 없이 기존 최소 회전 3°, 카메라 half-FOV 27.25°, 기존 부분회전 시간 10초를 재사용한다. 관련 ASRL 소스의 이 회전 상수 이력은 해당 기록의 출처이며 이번에 별도 재검증하지 않았다.

## 적용과 차이

`rgb_reconfirmation=two_view_rgb_v1`은 기본 OFF이며 OFF는 입력 조회·래퍼조차 추가하지 않는다. 새 B 확인 이벤트/graph/cue 쓰기, B 도착, accepted corridor graph-node 정합, 귀환 선언 직전에 켠다. 저장 checkpoint의 B는 과거 가설이므로 없애거나 과거 판정을 소급 수정하지 않으며, 이번 도착은 재확인해야 한다. corridor는 이미 기억한 graph node 정합이며 새 자유공간·통로를 인증한다는 뜻이 아니다.

1. **B:** 현재 frame 시간·candidate ID·중심 연계가 맞는 자기 RGB patch, 기존 B/pickup hue와 전체 metric extent 기준을 만족해야 첫 관측이 된다. 63004와 같은 pickup 색 오인을 B로 통과시키지 않는다. 두 번째 다른 각도에서도 같은 후보와 첫 영상 사이 ORB 기하가 맞아야 확인한다. 도착 시 원래 .20m·5현재프레임도 유지한다.
2. **통로·귀환:** 과거 자기 RGB keyframe과 현 영상을 검증한 후, 같은 과거 reference를 고정하고 다른 각도에서 다시 검증한다. 새 graph node의 RGB 특징은 해당 frame의 모든 판정이 끝난 뒤 추가해 미래 관측만 참조하게 한다. 귀환 home bank는 checkpoint 전 자료로 고정하며 새 near-home 추정으로 확장하지 않는다. 최초 current frame이나 동일 SHA 영상만으로 통과할 수 없다. 기존 graph matcher가 거부한 후보는 이 게이트도 승격하지 않는다.
3. **능동 관측:** 기존 finite pulse/coast host로 +half-FOV, -half-FOV를 한 번씩, 총 최대20초 시도한다. 병진 명령은 내보내지 않는다. 소진 뒤 DEV 주행은 재개하되 미확인 선언은 계속 거부한다. 새 가설은 별도 기록하며 위치 불확실 정지와 섞지 않는다.
4. **한계:** H는 평면/회전 영상 확인이며 깊이·거리·metric loop closure를 보장하지 않는다. 반복 무늬 alias·texture 부족·partial B는 남는다. egomap68 PnP의 최소50 유효3D점 부족에 따른 home0/3171 기록을 감안해 PnP 대신 2D 확인을 쓰지만, 실제 귀환 향상은 새 짝 비교에서만 판정한다. 좌표 보정이나 공분산 축소를 하지 않는다. 한 번 통과한 가설도 현재 semantic/기하 검증을 계속 통과해야 하고 20초 또는 .30m 이동 후에는 새 두 관측이 필요하다.

구현: `harness/own_rgb_reconfirmation.py`, `harness/own_route_reconfirmation.py`. 독립 covariance inflation 토글과 별도로 켤 수 있다. 하위 에이전트는 관련 시험을 작성했으며 실행·통합·클라우드 결과는 루트 조정자가 기록한다.
