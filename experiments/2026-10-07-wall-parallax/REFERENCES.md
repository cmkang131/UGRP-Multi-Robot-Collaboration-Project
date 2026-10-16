# 표준 방법 비교와 적용 경계

| 후보 | 근거·비용 | 이 자료에 대한 판단 |
|---|---|---|
| (a) bearing-only 지연 초기화 | [Bailey ICRA2003](https://www-personal.acfr.usyd.edu.au/tbailey/papers/icra03.pdf), Eq2/6 및 §III–V: 삼각측량의 조건과 자세 간 상관을 유지해야 함 | 적은 수직 선 특징에 가볍지만 대응이 어려움. 수평 pixel 방위의 pitch 불변성을 보장하지 않음. 원 논문도 known association 검증이며 영상 의미 분류기는 아님 |
| (b) SVO depth filter | [저자 공개 코드](https://github.com/uzh-rpg/rpg_svo/blob/master/svo/src/depth_filter.cpp), Vogiatzis–Hernández2011 인용. inverse depth와 inlier/outlier 혼합, epipolar patch search, pixel각도→깊이 분산 | 텍스처 약한 곳의 gradient에 유리하나 aperture/잘못된 대응이 남음. 원 tau는 주어진 SE3에 조건부이므로 우리 개루프 pose 불확실성은 별도 확장 필요. 이번에는 미구현 |
| (c) 점/선 triangulation | [ORB-SLAM2 CreateNewMapPoints](https://github.com/raulmur/ORB_SLAM2/blob/master/src/LocalMapping.cc), [PL-SLAM 저자 코드](https://github.com/rubengooj/pl-slam), [논문](https://arxiv.org/abs/1705.09479) | 선택: 점 DLT만 OpenCV로 실행. 단일 카메라 시차가 작으면 거부하는 검사와 공분산을 명시하기 쉬움. PL-SLAM 공개판은 stereo·g2o 등 의존성이 있어 그대로 설치하지 않음. sparse recall 부족 가능성을 관문에 남김 |

구체적으로 [OpenCV LK 공식 예제](https://github.com/opencv/opencv/blob/4.x/samples/python/lk_track.py)의
Shi–Tomasi 초기화/LK 왕복 검사를 기존 OpenCV API로 사용한다. [triangulatePoints 공식 문서](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)는
K[R|t] 두 카메라와 대응 픽셀을 입력으로 받으며 바닥 평면을 요구하지 않는다.
ORB-SLAM2의 cos(parallax)<.9998, cheirality, χ²(2)95%=5.991 재투영 검사를 참조한다.
원 ORB vocabulary/BoW/BA/loop closure/scale pyramid/카메라 pose 추정기를 이식하지 않는다.
저해상도 연속 영상에는 LK, metric scale/상대 pose에는 자기 command DR를 쓰는 제약 변경이다.

기존 벽의 픽셀 ROI를 사용하므로 일반 물체 의미 분할을 해결한 것은 아니다. floor로 깊이를 정하는
연산은 삼각측량에 없으나 ROI의 기존 horizon/range 제한과 카메라 외부 보정은 남는다.
pitch 오차가 같은 팔 자세에서 공통이어도 ray 방향·baseline 좌표 해석에 영향을 줄 수 있다.
따라서 공통 pitch nuisance와 상관된 두 DR pose를 포함해 JΣJᵀ로 불확실성을 전파한다.
3°는 현 기록의 잔여 오차를 포괄하는 보수적 모델 가정이며 새 실측 calibration이 아니다.

원문 조회 revision/sha256은 [SOURCES.json](SOURCES.json). OpenCV Apache-2.0,
ORB-SLAM2 GPLv3, PL-SLAM GPLv3. ORB/PL 코드 복사·링크/배포는 하지 않고 공개 수식/검사만
독립 구현한다. LK는 설치된 OpenCV 함수를 호출하며 source 원문 bytes는 출처 해시로 기록한다.
확인한 SVO `LICENCE`도 GPLv3이며 이번에 dependency로 추가하지 않는다.
기존 `harness/self_odom_grid.py` M1 평균과 `harness/self_map_prob.py` V7 구조 사전 covariance를
재사용하며 실제 encoder/servo 측정을 가진 것처럼 표현하지 않는다.
