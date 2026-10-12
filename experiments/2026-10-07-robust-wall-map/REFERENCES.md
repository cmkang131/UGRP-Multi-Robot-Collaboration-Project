# egomap21 출처 (2026-10-07 확인)

1. Sünderhauf & Protzel, **Switchable Constraints for Robust Pose Graph SLAM**, IROS2012.
   [저자 PDF](https://nikosuenderhauf.github.io/assets/papers/IROS12-switchableConstraints.pdf),
   [저자 구현 안내](https://nikosuenderhauf.github.io/projects/switchableConstraints/).
   §II 식(1): loop switch와 switch prior의 공동 최적화. §II-A: 선형[0,1] switch;
   §IV-A: 모든 prior 분산1을 권고/실험에 사용. §IV-B: 이진 판정은 평가용이며 실제는 연속값.
   [Vertigo 공개 원본](https://github.com/OpenSLAM-org/openslam_vertigo/tree/e57e88cbc1756070f37c6c32f87be947e7a72bb8)
   `src/g2o/edge_se2Switchable.cpp:94–102`(SE2 오차×s),
   `edge_switchPrior.cpp:25–31`(prior−s), `vertex_switchLinear.cpp:42–51`([0,1] 제한)를 대조했다.
   [OpenSLAM 라이선스 안내](https://openslam-org.github.io/vertigo.html)는 GPLv3.
   C++ 소스 복사/링크/설치 없이 논문의 목적함수를 기존 NumPy/SciPy로 독립 구현한다.
   기존 잔차의 병진은 submap frame이므로 측정 frame 잔차로 바꿀 때 공분산도 같은 회전으로
   바꾸어 Mahalanobis 비용을 보존한다. 원본 g2o 대신 SciPy의 bounded sparse TRF를 쓰는
   solver 차이를 명시한다. 이미 있는 Huber/score 값을 새로 맞추는 방법은 선택하지 않는다.

2. [Cartographer TSDF range inserter 원본](https://github.com/cartographer-project/cartographer/blob/877157a0d91788a7700221d87232d412cb3c1ef4/cartographer/mapping/internal/2d/tsdf_range_data_inserter_2d.cc)
   `44–46` Gaussian, `156–179` ray/법선 각도, `187–206` scan당 cell1회·거리 weight,
   `209–220` 가중 평균 SDF와 weight 포화를 대조했다.
   [공식 기본값](https://github.com/cartographer-project/cartographer/blob/877157a0d91788a7700221d87232d412cb3c1ef4/configuration_files/trajectory_builder_2d.lua#L94-L106):
   truncation .3m / maximum_weight10 / 두 kernel .5 / range exponent0 / update_free_space=false.
   Apache2.0. 알고리즘 수식 독립 구현, C++/Ceres 설치0. 기존 점유 격자와 별도로
   관측 support를 기록하는 적용이며 Cartographer 전체 TSDF SLAM을 이식했다는 주장은 아니다.
   시선 원형 분산은 각도 표본의 통계 요약이고 TSDF 공식 weight와 섞지 않는다.

3. [egomap20](../2026-10-07-arena-wall-map/README.md): 고정 후보/자기 관측 lineage와 기존
   metric 정의. [기존 SPA 출처](../2026-10-05-ego-wall-map-probe/README.md#22)는 그대로 유지.
   이 DEV 두 건에 대한 새 calibration fitting, 모션 재적합, GT-assisted loop 선별은 하지 않는다.
