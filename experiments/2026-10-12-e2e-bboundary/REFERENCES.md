# 확인한 표준 방법과 적용 범위

2026-10-12, 브라우저 UI 없이 원문·공개 코드 조회. 구현 전에 frontier/NBV 절차를 조사했고, 최신 AVV의 구체 샘플링 규칙을 대조해 후보를 정리했다. 외부 코드를 실행하거나 모델을 호출하지 않았다.

- **Yamauchi (1997), A Frontier-Based Approach for Autonomous Exploration.** [원문 PDF](https://biorobotics.ri.cmu.edu/papers/sbp_papers/integrated1/yamauchi_frontiers.pdf). 알려진 자유 공간과 미지 공간의 경계로 이동해 관측을 확장하는 고전적 탐색. 목표 경계의 의미·표식 확인은 별도 임무다. PDF 6쪽의 회수 가능성·서지 확인; 스캔 본문 텍스트 추출은 실패했다. 원문의 세부 문장은 **미확인**이며, 실제 frontier 정의·연결 탐색은 다음 공개 코드에서 확인했다.
- **explore_lite, hrnr/m-explore.** [frontier_search.cpp](https://raw.githubusercontent.com/hrnr/m-explore/master/explore/src/frontier_search.cpp), [explore.cpp](https://raw.githubusercontent.com/hrnr/m-explore/master/explore/src/explore.cpp). 자유 공간에 인접한 unknown 성분을 모아 크기·거리로 정렬한다. centroid를 목표로 보내고, 진행 시간 초과/ABORTED이면 blacklist에 넣는다. 남은 성분 또는 비차단 성분이 없으면 종료한다. 종료가 특정 물체·영역 확인을 뜻하지 않는다. 저장소의 vendored 코드·`bridge.cpp`와 대조: 최소 frontier 길이 .1 m, 비용은 raw grid와 inflated NavFn을 각각 사용한다.
- **McGreavy, Kunze, Hawes (2017), Next Best View Planning for Object Recognition in Mobile Robotics.** [출판 원문](https://ceur-ws.org/Vol-1782/paper_6.pdf), [저자 소속기관 서지·초록](https://ora.ox.ac.uk/objects/uuid%3A2e0178b3-f9fe-4ed6-bb1a-1b88d497329f). 후보를 먼저 찾은 뒤, 로봇이 도달할 수 있는 관측점에서 대상·식별 특징의 가시성을 평가하고 다음 관측점을 선택한다. 출판사 검색 초록과 기관 서지를 확인했다. 원문 전체는 도구 크기 제한으로 **미확인**; 본문의 수치·코드 구현을 그대로 이식했다고 주장하지 않는다.
- **Bajpai et al. (2025), Uncertainty-Informed Active Perception for Open Vocabulary Object Goal Navigation.** [원문 §IV-A](https://arxiv.org/html/2506.13367v1), [공개 코드 README](https://raw.githubusercontent.com/PRBonn/uiap-ogn/main/README.md). 탐색과 목표 검출 후 point-goal 접근을 구분한다. 이 논문의 RGB-D·알려진 pose 전제를 UGRP 제어에 가져오지 않았다.
- **Pei et al. (2026-08-13), SAP-Nav, arXiv:2608.12707v1.** [원문 AVV §3, Eq. 4–6](https://arxiv.org/html/2608.12707v1). 관측이 부족하면 후보 주변 동심원 (.8/1.2/1.6/2.0/2.4 m, 각 24방향)을 표본화하고, 탐색된 자유 공간·시야 조건으로 거른 뒤 가시성을 비교한다. 관측점에 도달해 다시 확인하며 재배치는 3회로 제한한다. 본문을 확인했다. 논문은 acceptance 뒤 공개 코드 예정이라고 명시하므로, 이 연구의 공개 구현은 **미확인**이다.

표준 절차는 **후보 검출 → 현재 관측 충분성 검사 → 도달 가능한 관측점 선택 → 접근·대상 쪽 정렬 → 새 관측 → 독립 확인 → 부족하면 다른 관측점/탐색 재개**다. 탐색 완료나 후보 색 기억만으로 확인을 승인하지 않는다.

`candidate_views_v1`은 SAP-Nav의 동심원·각도·3회 제한을 그대로 사용한다. UGRP에서는 허용된 자기 RGB 지도·자기 발행 명령 위치만 사용하고, unknown 주행과 알려진 장애물 시선 차단을 거부한다. 깊이·2.5D 정답 높이·새 VLM은 사용하지 않아 실제 가시성 최적화 대신 경로 길이·거리·unknown 시선 셀의 명시적 대용 점수를 쓴다. 이는 전체 SAP-Nav 재현이 아니다. 30 SIM초/관측점 제한은 기존 explore_lite 유한 진행 제한을 재사용한다. 도착 후 3개 새 관측은 자료 수집이며, 기존 `ArrivalGate`의 경계·기하·공분산 조건을 통과시켜 주지 않는다.

## B 흰 표식 판정 (`contrast_v1`)

브라우저 없이 원문 조회(2026-10-12).

- **OpenCV 형태학 연산 튜토리얼** ([원문 소스](https://raw.githubusercontent.com/opencv/opencv/4.x/doc/py_tutorials/py_imgproc/py_morphological_ops/py_morphological_ops.markdown)): 열림=침식 후 팽창, 닫힘=팽창 후 침식, `cv.morphologyEx`, Top Hat/Black Hat. 구조 요소보다 작은 밝은(어두운) 부분을 지운 배경과 비교하는 표준 절차다. 원래의 차분 대신 비율로 바꿔 노출 배율 불변을 얻은 것은 우리 쪽 변경이다. docs.opencv.org는 403이었고, 같은 문서의 GitHub 원문을 확인했다.
- **OpenCV 임계값 튜토리얼** ([원문 소스](https://raw.githubusercontent.com/opencv/opencv/4.x/doc/py_tutorials/py_imgproc/py_thresholding/py_thresholding.markdown)): Otsu는 두 봉우리(bimodal) 히스토그램을 전제한다. 조명이 고르지 않으면 적응 임계를 쓴다. B 내부는 체커 두 톤과 표식이 있어 봉우리가 셋 이상이고, 표식은 면적 수 %다. 그래서 전역 Otsu 대신 지역 배경 비교를 택했다.
- **scikit-image `segmentation.clear_border`** ([API 문서](https://scikit-image.org/docs/stable/api/skimage.segmentation.html)): 영상(영역) 경계에 연결된 객체를 지운다. MATLAB `imclearborder`와 같은 표준 절차다. 경계는 B 내부 영역 테두리로 바꿔 적용했다.
- **MuJoCo XML reference, geom `rgba`** ([원문 소스](https://raw.githubusercontent.com/google-deepmind/mujoco/main/doc/XMLreference.rst)): rgba는 색과 투명도를 지정한다. 표식 알파 .35가 렌더에서 아래 색과 섞이는 원인이다. 블렌딩 수식은 실측 픽셀 역산으로만 확인했다. 원문의 블렌딩 수식은 **미확인**이다.
- **Gonzalez & Woods, Digital Image Processing (형태학 장의 top-hat 배경 보정)**: 교과서 원문은 이번에 확인하지 못했다(**미확인**). 근거는 위 OpenCV 문서로 한정한다.
- 채도 S=(max−min)/max는 max가 작을 때 불안정하다. 그래서 V<50 픽셀의 채도를 배경에서 뺐다. 정의에서 바로 나오는 성질이며 별도 문헌 인용은 없다.
