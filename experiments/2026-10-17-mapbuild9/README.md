# mapbuild9 — 정적 지도 AMCL 저장 재생 후보

판정 진행 중. 기본 off `selfmap_map_correction_v1`의 새 method `static_amcl_v1`. 자기 지도는 기록하고 보정 우도에는 사용하지 않는다. 전역 자유 공간 균일 초기화, spawn/정답 입력 금지. 입자 분포 미수렴 때 인계·운반 금지.

수정 전 분포: [이전 거부표](prior-rejection_table.json). 자기 서브맵 비영 보정 오채택4/4, 초기 정적 등록 모호2/3·고잔차1/3.

## 먼저 읽은 참고 자료와 라이선스

- [Fox 2001 KLD-Sampling](https://papers.neurips.cc/paper_files/paper/2001/file/c5b2cebf15b205503560c4e8e6d1ea78-Paper.pdf), §2–3·식7: 알려진 지도에서 이동/관측 갱신과 다봉 전역 위치추정, 점유 bin에 따른 입자 수.
- [Thrun/Burgard/Fox Probabilistic Robotics](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/), 5장 sample_motion_model_odometry·6장 likelihood field·8장 MCL/AMCL/전역 초기화 및 kidnapped recovery. 출판사 서지만 확인; 책 본문 전체 신규 열람 아님. 코드에 대응하는 교과서 쪽136은 아래 Nav2 원문의 주석으로 확인.
- [Nav2 공식 AMCL](https://docs.nav2.org/configuration/packages/configuring-amcl.html): 이동 상수·우도장·관측 간격·recovery/입자 설정.
- [Nav2 고정 소스](https://github.com/ros-navigation/navigation2/tree/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl): differential_motion_model.cpp의 순방향/역방향 대칭 odometry, likelihood_field_model.cpp의 `1+sum(pz^3)`, pf.c의 KLD 다항 재표본화·평균 우도 recovery를 줄 순서대로 NumPy로 옮긴다. 소스·원저작권·LGPL-2.1-or-later 전문·SHA는 `harness/mapbuild_amcl_vendor/`에 함께 보존. 기존 UGRP AMCL 포트와 비교하되 새로운 scan matcher를 만들지 않는다.

라이다 실험 성능은 자기 RGB 가상 스캔 성능으로 승계하지 않는다.
