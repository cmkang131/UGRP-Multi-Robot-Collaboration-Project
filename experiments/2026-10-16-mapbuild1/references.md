# mapbuild1 조사 (2026-10-16 열람)

원문 저장소·논문·공식 API를 확인했다. 아래 적합성은 우리 입력 경계에 대한 설계 판단이며, 구현 간 성능 비교 결과가 아니다. 9/25·9/26 조사에서의 태그 권고·GPU 제외·옛 무질감 장면 판단은 현행 결정으로 대체한다. v91 검증 자료는 사용하지 않는다.

| 후보 | 확인한 원문과 방식 | 이 조건에서의 적용·제약 |
|---|---|---|
| ORB-SLAM3 | [공식 코드](https://github.com/UZ-SLAMLab/ORB_SLAM3), [논문](https://arxiv.org/abs/2007.11898). ORB, bundle adjustment, 장소 재인식·다중 지도, 단안·어안 지원 | CPU 고전 비교. 실제 camera-v3 K/D로 설정, 단안 척도는 별도 해결. IMU·스테레오를 가정하지 않는다. GPLv3 및 C++/Pangolin 의존성. 설치·실행 결과는 아직 없음 |
| OpenCV VO/PnP | [calib3d](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html), [solvePnP](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html), [LK](https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html). LK/ORB, 기하 검증, 3D–2D PnP | 최종 계열(10/3 사용자 결정). 기존 `natural_floor_slam`·`e2e_rgb_vo.ground_pair` 재사용. PnP에는 미터 단위 3D 랜드마크가 먼저 필요하며 정답 지도를 넣어 해결하지 않는다. 초기 바닥 평면과 고정 카메라 보정으로 척도를 정하고 팔 움직임은 발행 PWM만 사용 |
| GMapping | [저자 페이지](https://openslam-org.github.io/gmapping.html), Grisetti 등 T-RO 2007. Rao–Blackwellized PF, 입자별 점유 격자, 관측을 사용한 제안분포와 선택적 재표본화 | 원 구현 입력은 laser range와 odometry. RGB를 그대로 넣을 수 없다. 색 경계→방위별 벽 바닥 접점의 가상 스캔, 자기 명령 예측으로 개념 재사용. 초음파 한 방향을 LiDAR 전체 스캔처럼 취급하지 않는다 |
| Cartographer | [저자 논문 설명](https://research.google/pubs/real-time-loop-closure-in-2d-lidar-slam/), [공식 알고리즘 문서](https://google-cartographer.readthedocs.io/en/latest/algo_walkthrough.html). submap 정합·분기한정 loop closure | 벽 경계 스캔을 누적하고 작은 지역 지도를 닫은 뒤 재정합하는 구조 참고. 원 논문 5cm 격자는 참고 값이며 우리 정확도 보장이 아니다. IMU 없는 자기 RGB 설정으로 그대로 사용 가능한 것으로 보고하지 않는다 |
| DROID-SLAM | [공식 코드](https://github.com/princeton-vl/DROID-SLAM), [논문](https://arxiv.org/abs/2108.10869). 학습한 dense correspondence와 recurrent bundle adjustment | 비교 전용. README는 demo 추론 GPU ≥11GB, 학습 ≥24GB를 구분한다. L4 총 용량만으로 공유 임대를 승인하지 않는다. 어안 영상을 고정 K/D로 보정하고 잘라낸 FOV를 기록. 단안 결과를 정답 Sim(3) 척도로 맞춘 수치와 허용 입력 척도 수치를 분리. async 비결정성 주의 |
| MASt3R-SLAM | [공식 코드](https://github.com/rmurai0610/MASt3R-SLAM), [논문](https://arxiv.org/abs/2412.12392). 3D 재구성 사전과 매칭, dense 지도 | 비교 전용. CUDA 빌드·외부 가중치와 라이선스·자산 해시를 고정해야 한다. L4에서의 실제 메모리/속도/정확도는 미측정. 학습 사전의 척도를 우리 장면의 실제 거리로 확정하지 않는다 |

## 선택과 척도

최초 실험은 기존 OpenCV ORB 희소 지도와 LK 증분 추정을 각각 재생한다. 추적 실패를 영변위로 채점하지 않으며 `unknown`/`command_only`를 유지한다. 평면 교차의 척도는 고정 카메라-몸체 보정과 지면 가정에서 나온다. 명령 이력 기반 예측은 이동 측정이 아니며 실제 주행에서 별도 오차를 잰다. 초음파는 명시적 ON 번들에서만 보조 거리로 쓰며, 먼저 OFF로 분리한다. 경사·하중·팔 이행 중 평면 가정의 오차는 별도 관문이다.

새 수용 오차·상수를 임의로 만들지 않는다. 원 모듈의 수치·근거 파일과 분포를 함께 기록하고, 새 조정은 다른 보정 자료에서 도출해 기본 off 후보로 다시 잰다. ORB FAST7은 warp5 R3 정적 88장 조사에서 실제 특징 수 분포를 확인한 비교값이며 기본 FAST20을 대체하지 않는다. 제어 성능 채택에는 별도 holdout이 필요하다.
