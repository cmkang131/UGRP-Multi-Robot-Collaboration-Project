# 원본 방법·라이선스·실제 변경

- Yamauchi 1997 frontier 방법의 실제 실행은 [explore_lite 원본 frontier_search](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/src/frontier_search.cpp),
  BSD-3. PR409 `ed2fa0e9` Python 어댑터/C++/원본94파일의 전체 해시는 `navigation-source.json`.
  navfn BSD-3, PythonRobotics MIT, Nav2 Apache-2.0. `third_party/*/SOURCES.json`과 라이선스를 그대로 복사.
  PR409의 v8 기본값(.33Hz frontier, 1Hz replan, .75m frontier, 30s progress, 1.2s collision horizon)은 변경하지 않았다.
- [Stachniss, Grisetti, Burgard RSS2005](https://www.roboticsproceedings.org/rss01/p09.pdf),
  정보이득 식(11–22), frontier/재방문 후보. 공개 논문 알고리즘을 이 저장소 RBPF에 구현한 것이며 원저자 코드 실행 주장은 아니다.
  구현은 `harness/active_information_gain.py`. 원본의 가중 대표 입자 하나와 복사본 갱신을 유지한다.
  지도 entropy는 셀 면적(0.01m²) 가중, 궤적 entropy는 공통 frame ancestry의 방문 칸별 평균.
  공분산 행렬에 수치 jitter 1e−10, unknown ray gain은 기존 p_hit=.7 한 번의 Bernoulli entropy 감소.
  카메라/FOV·계산 후보수·v122 motion noise 변환·α 고정은 README에 적은 어댑터 차이.
- [Switchable Constraints](https://nikosuenderhauf.github.io/assets/papers/IROS12-switchableConstraints.pdf),
  [egomap21 대조](../2026-10-07-robust-wall-map/REFERENCES.md)의 동결 구현 그대로. pose graph는 map→odom TF를 만들고 local frontend를 덮어쓰지 않는다.
- [Nav2 collision monitor 원본](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_collision_monitor/src/polygon.cpp).
  v122는 연속 축소 속도가 아닌 고정 펄스만 보정됐다. 0.2s 예측 변위가 연속 요청에 가장 가까운
  펄스(정지 포함)를 선택하고 그 실제 mean_curve footprint와 TTC를 확인한다. 축소가 필요한 미지원 펄스는 정지한다.
  제어 loop는 5Hz, 원본 v8의 10Hz `active_t` progress clock은 어댑터에서 실제 경과 시간으로 보완한다.
- 사진은 [ambientCG PaintedPlaster017](https://ambientcg.com/view?id=PaintedPlaster017),
  실제 Surface Photogrammetry, [CC0-1.0](https://docs.ambientcg.com/license/).
  `assets/photo-source.json`의 원본 JPG/ZIP 해시. Plaster002/Concrete031는 절차 생성이므로 채택하지 않았다.
  기본 HTTP 다운로드가403, 정상 명시 User-Agent curl 다운로드는 성공. Poly Haven은 검토만, 자산 사용0.
  각 면에 비반복 단일 crop을 전체면 크기로 인쇄(원 사진 비율 확대/축소, 실물 재질의 치수 재현 주장은 아님).
- DIC [iDICs Good Practices Guide](https://www.idics.org/guide/DICGoodPracticesGuide_PrintVersion-V5h-181024.pdf)
  대비·비반복 점무늬 원칙. 코드 재사용 없음. 다중 지름6/12/24mm, seed22001+벽면 SHA,
  독립 Poisson 위치, 겹침 허용, 기대 검정 면적50%. 카메라 거리에 따라 3px 이하 점의 aliasing 가능.
  원본 점 크기 권고를 모든 거리에서 만족한다고 주장하지 않는다.
- 카메라: [egomap18 FK/규약 감사](../2026-10-07-camera-frame-audit/README.md),
  [egomap19 강성](../2026-10-07-servo-stiffness/README.md). 마운트/K/D 그대로, 손목 PWM858만 추가.
  B v3 함수의 code object/문턱은 그대로며 dependency injection으로 command FK와 body mask 투영만 교체.

## 제어에 전달되지 않는 정보

`ActiveMapper.receive`는 robot_id/time/frame_id/RGB/servo/자기 검출값만 받는다.
`inputs/static_map.json`, `eval_only`, 실제관절/pose/접촉은 scoring/물리 실패 abort 외에는 읽지 않는다.
가상 raycast는 해당 로봇의 RBPF 입자 지도에만 한다. 본체 footprint clearing은 관측 면적으로 세지 않는다.
카메라 바닥 free는 기존 접점 아래 실제 저채도 픽셀만, 검출 없는 열은 외삽하지 않는다.
첫20s/최대1회전은 좁은 FOV의 초기 관측 획득만 허용하며 위치 waypoint는 없다.
