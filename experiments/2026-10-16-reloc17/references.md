# 원문 조사 — 2026-10-16

확인한 원문/공식 코드와 우리 구현의 차이를 구분한다. 원문의 숫자는 우리 센서의 보정값이 아니다.

|자료|직접 확인한 방법·관문·공분산|적용 한계|
|---|---|---|
|[Nav2 AMCL 공식 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [pf.c](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c), [likelihood field](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp)|거리장 관측 likelihood와 이상치 혼합, 가중 입자·클러스터 통계. `pf_update_converged`는 모든 입자의 xy가 비가중 평균 ±dist_threshold 안인지 확인. 문서 sigma_hit .2m, z_hit/z_rand .5/.5는 레이저 기본값이다. 공분산 6배/3뷰를 전역 수용 필수조건으로 정하는 규칙은 이 원문에 없다.|RGB 경계의 투영 오차와 레이저 오차는 다르다. 모든 입자 convergence를 외부 pose 수용에 추가한 우리 어댑터와 Nav2의 published pose 선택을 혼동하면 안 된다. 우리 .2m가 적절하다는 검증은 없음.|
|[Boniardi et al., Robot Localization in Floor Plans Using a Room Layout Edge Extraction Network, 2019](https://arxiv.org/pdf/1903.01804), III-B/C 식(2)|알려진 평면 지도+단안+wheel odometry MCL. 지도에서 가시 벽/모서리/천장선을 투영하고 관측 edge mask까지 **픽셀 거리**를 포화·정규화해 log likelihood를 계산. sigma_z는 픽셀 noise, delta는 설명 안 되는 측정의 과도한 벌점을 막는다. Manhattan은 가시 지도선 구성에 사용한다.|측정 노이즈를 원본 영상 좌표에 두는 직접 관련 레퍼런스. 네트워크·천장선·Matlab Manhattan 전체 이식은 안 함. 우리 손목 카메라·명령 오도메트리의 likelihood/covariance는 별도 실측 필요. 저자 공개 실행 코드 위치는 이번 조사에서 **미확인**.|
|[ORB-SLAM3 공식 Tracking.cc](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/master/src/Tracking.cc), `Relocalization`|BoW 후보→15개 이상 대응→MLPnP RANSAC(.99,10,300,6,.5,5.991)→pose 최적화→투영 대응 보충→최종 good≥50. 고정 iteration 예산이며 큰 분산을 임의 배수로 부풀려 false match를 수용하지 않는다. [Optimizer.cc](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/master/src/Optimizer.cc)는 octave 정보행렬·Huber·mono chi² 5.991을 사용.|15/50은 해당 특징·지도 구현의 경험적 기준이다. 우리 floor line에 숫자만 복사하지 않는다. 공개 재위치 절차에서 수용 공분산의 통계적 calibration 보장은 **미확인**. 학습된 3D 포인트 지도가 필요한 방식이다.|
|[hloc 공식 localize_sfm.py](https://github.com/cvg/Hierarchical-Localization/blob/master/hloc/localize_sfm.py)|검색 이미지의 2D–3D 대응과 covisibility cluster를 모으고 pycolmap `estimate_and_refine_absolute_pose`로 RANSAC/재투영 최적화. estimation/refinement 설정을 명시적으로 전달한다.|사전 SfM 3D 지도가 필요하므로 현재 authored 2D 지도만 있는 경로의 즉시 교체품 아님. 호출된 COLMAP 내부 covariance 계산·현재 기본 RANSAC 문턱은 **미확인**, 이 래퍼만 확인.|

판단: convergence 실패와 기하·특징·공분산 불일치를 따로 재야 한다. 관문만 풀거나
표준의 레이저 sigma를 단안 경계에 그대로 맞다고 가정하지 않는다. 등록 후보가 올바른
세계 pose인지와 그 pose가 실행에 전달된 뒤 drift가 늘었는지도 별개로 비교한다.
참고 자료 조사는 수용 문턱을 바꾸는 근거 자체가 아니다. 원본 분포를 먼저 얻는다.
