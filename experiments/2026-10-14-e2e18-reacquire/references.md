# 봉 재발견: 구현 전 확인한 참고 자료 (2026-10-14)

- **Yamauchi, CIRA 1997, A Frontier-Based Approach for Autonomous Exploration**: [저자 원문](https://www.robotfrontier.com/papers/cira97.pdf), [CMU 원문 사본](https://biorobotics.ri.cmu.edu/papers/sbp_papers/integrated1/yamauchi_frontiers.pdf). 알려진 빈 공간과 미탐색 공간 경계를 향하는 일반 탐색. 이미 본 봉을 기억 지점으로 재방문하는 목적과 다르므로 봉 기억이 없거나 후보가 실패할 때의 대안으로 사용한다. 저자 PDF 직접 열기는 실패했지만 검색 본문과 CMU PDF 확인.
- **Chaplot et al., NeurIPS 2020, Object Goal Navigation using Goal-Oriented Semantic Exploration (SemExp)**: [논문](https://arxiv.org/abs/2007.00643), [공개 코드](https://github.com/devendrachaplot/Object-Goal-Navigation). `main.py` 453–465: 목표 물체가 의미 지도에 있으면 일반 장기 탐색 목표를 물체 지도 목표로 교체. 지도 기억과 국소 경로 실행을 분리하는 구조를 따른다. 원 구현은 RGB-D·센서 pose를 쓰므로 입력을 그대로 가져오지 않는다.
- **Yokoyama et al., ICRA 2024, VLFM**: [논문](https://arxiv.org/abs/2312.03275), [공개 코드](https://github.com/rai-opensource/vlfm). `base_objectnav_policy.py` 112–128,158–162: 물체 지도에 목표가 있으면 pointnav, 없으면 explore. 관측 시마다 보이는지와 지도에 기억되어 있는지를 구분한다. RGB-D·GPS/heading에 기대는 pointnav는 그대로 이식하지 않는다.
- **Shen et al., AAAI 2025 / extended 2025, MCoCoNav**: [논문](https://arxiv.org/abs/2412.18292), [공개 코드](https://github.com/FrankZxShen/MCoCoNav). 의미 지도로 관측을 합치고 frontier/과거 노드를 선택하는 다중 로봇 구조. 공유 의미 지도는 본 실험의 통신 조건을 우회하므로 채택하지 않는다. 짝 단서는 허용 채널의 실제 전달 문장만 판단 모델에 제공한다. 논문 초록·공개 저장소 확인; 코드 전체 재현은 미검증.
- **Bajcsy 1988 Active Perception**: [대학 보관 원문](https://repository.upenn.edu/server/api/core/bitstreams/14686d28-7a8a-4554-beee-991eec61cbdd/content). 원문 요청 403으로 세부 주장은 미확인. 이 문헌만 근거로 특정 next-best-view 구현을 정하지 않는다.

## 적용 범위와 후보

자기 RGB에서 얻은 물체/관측 지점은 파지 허가와 분리해 유지한다. 기억 지점으로 돌아가 보기, 그곳을 향해 관측하기, 기존 일반 탐색을 거리·예상 시간과 함께 제시하고 Gemma(v405와 같은 모델·provider·JSON 설정)가 선택한다. 기억만으로 파지/성공/단계 통과를 허용하지 않는다. 물체 좌표와 관측 지점은 자기 추정 지도 좌표이며 정답·짝 지도는 읽지 않는다. 같은 선택이 무진전 3회면 후보 제거하고 진행 가능한 탐색 대안을 남긴다. 상대 정보가 없는 조건에서는 어떤 상대 상태도 추가하지 않는다.

검증되지 않은 부분: 기존 자기 위치 오차는 해결됐다고 보지 않는다. 기억된 물체 좌표로만 직진하지 않고 기존 자기 지도 경로 생성·장애물 필터를 사용하며, 관측 당시 자기 위치로 돌아가는 후보도 비교한다. 새 체크포인트는 튜닝 3개와 분리한다.

## 사용자 범위 확장: 최초 관측부터 시선 유지

- **Chaumette & Hutchinson 2006, Visual Servo Control Part I**: [MIT 원문 사본](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf), [저자 그룹 ViSP 공개 예제](https://github.com/lagadic/visp/blob/master/tutorial/visual-servo/ibvs/tutorial-ibvs-4pts.cpp). 영상 측정 또는 영상으로 추정한 위치와 목표의 오차를 줄이는 폐루프 제어. 본 구현은 기존 카메라 보정과 팬 한계 안에서 자기 관측 물체 방위를 추종한다. 기억 점을 향한 팬 명령은 시야 유지 보장이 아니므로 실제 봉 가시성·팬 범위 초과를 별도 계수한다.
- **Fu et al. FLAF 2024 / revised 2025**: [논문](https://arxiv.org/abs/2409.03457). 이동 경로 추종과 PTU 시선 계획을 분리해 관측 가능한 지도 특징을 유지한다. 대상은 물체 파지가 아닌 visual teach-and-repeat이며 본 작업에 직접 성공률을 이전하지 않는다. 초록 확인, 공개 코드·전체 방법 재현은 미확인.

확장 옵션은 파지 조건에 못 미치는 몸체 관측의 기억 갱신, 경로 회전·접근 시 기억 방위 팬 추종, 잃은 경우 기억 지점 재방문 및 순서 있는 주변 시야 훑기를 함께 포함한다. 탐지·기하·팬 제어·커버리지는 코드가 수행하고 LLM은 제안된 스킬만 고른다. 신선한 파지 관측의 승인 경로는 변경하지 않는다.

- 실행 접속: Python socketserver 공식 문서 https://docs.python.org/3.11/library/socketserver.html — request_queue_size 기본 대기열 5와 subclass 확장. 게이트 동시 접속 3건 ConnectionReset은 대기열 포화 추정(직접 socket 계측 미확인); 64로 확대하고 유료 호출 동시 수 4는 유지. 종료 응답은 실행하지 않고 영수증만 저장.
