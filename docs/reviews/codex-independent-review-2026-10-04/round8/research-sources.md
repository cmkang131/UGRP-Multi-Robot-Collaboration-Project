# 8차 연구: primary source 확인표

확인일: 2026-10-04 UTC. 범위는 HIGH edge reference, guard 추정 불확실성, 관측 동작의 결정 가치, blind final approach의 증거 유효성이다. 7차의 통신 인과효과·실패 witness·공통지식 문헌 요약을 반복하지 않는다. 아래 원문을 직접 읽었으나 외부 코드를 실행하거나 논문 결과를 재현하지 않았다. 문헌의 수치를 UGRP 성능으로 옮기지 않는다.

| ID | 출처와 정확한 URL | 직접 읽은 범위 / 이 메모에 쓰는 주장 | UGRP에 승계할 수 없는 조건 |
|---|---|---|---|
| R8-1 | Torr & Zisserman, **MLESAC: A New Robust Estimator with Application to Estimating Image Geometry**, CVIU 78:138–156, 2000. [저자 Oxford PDF](https://www.robots.ox.ac.uk/~vgg/publications/2000/Torr00/torr00.pdf), [저자 기관 목록](https://www.robots.ox.ac.uk/~vgg/publications/index.php?idAuthor=123&pg=-1). | PDF §3의 Gaussian+uniform contamination model와 least-squares 초기값의 취약성, §4의 sample consensus, §5의 likelihood scoring, §7의 비교 설명 일부, 결론의 multiple-class 확장 한계. 강건한 초기 가설과 재적합은 단순 OLS→한 번 trim과 다르다. | image correspondence·fundamental matrix/homography 연구. UGRP lower-edge 검출기나 crop boundary를 해결한 논문이 아니다. uniform outlier 가정이 구조적 두 경계·검열된 ROI 끝을 참 경계와 구별해 주지 않는다. 수식의 일부 PDF 텍스트 추출이 깨져 복잡한 식을 그대로 전사하지 않았다. |
| R8-2 | **OpenCV 4.13.0 fitLine 공식 문서**, [Structural Analysis and Shape Descriptors](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html). | `fitLine` 항목 전체: L2/L1/L12/FAIR/WELSCH/HUBER 목적함수, 반복 가중 최소제곱 설명, `(vx,vy,x0,y0)` 출력. 표준 구현을 검토할 때 비교 후보가 존재한다는 근거. | `fitLine`은 입력 점이 실제 beam 경계인지 검증하지 않는다. robust loss의 존재는 수렴·정답 경계 선택·UGRP 내 성능 보장이 아니다. 사용 제안은 후보 비교이며 의존성 추가나 코드 변경을 수행하지 않았다. |
| R8-3 | Blackmore & Ono, **Convex Chance Constrained Predictive Control without Sampling**, AIAA GNC 2009. [MIT 저자 PDF](https://groups.csail.mit.edu/mers/old-site/papers/BlackmoreOnoGNC09.pdf). | §III의 linear discrete-time system, Gaussian initial state/noise와 비상관 가정; §IV-A/B의 joint constraint를 나누는 bound와 projected scalar Gaussian variance, Eq.11–14; §II의 finite-horizon와 receding-horizon 보장 범위 구분. | 현재 UGRP PF의 작은 covariance가 calibrated distribution이라는 보장은 없다. 개별 법선 방향의 margin과 전체 경로 충돌 확률도 다르다. nonlinear robot geometry, biased/multimodal posterior, guard cap/group relief의 확률 보장을 이 논문에서 얻지 않는다. |
| R8-4 | Blackmore & Williams, **Finite Horizon Control Design for Optimal Discrimination between Several Models**, CDC 2006. [MIT 저자 PDF](https://groups.csail.mit.edu/mers/old-site/papers/Blackmore-Williams-CDC06-paper.pdf). | §§I–II의 입력에 따른 모델 구별, §III의 Bayes risk bound 설명과 Gaussian case, §IV의 finite-horizon formulation 일부. 관측 동작은 어떤 경쟁 설명을 구별하는지와 허용 제약을 함께 정해야 한다는 근거. | 알려진 유한 model set·likelihood·Bayes classifier·linear dynamic formulation을 쓴다. UGRP 후보 설명의 사후확률이나 실제 위험 bound를 계산한 것이 아니다. 제약이 expected state에 걸리는 부분을 물리 안전의 무조건 보장으로 표현하지 않는다. |
| R8-5 | Zhang et al., **Affordance-Driven Next-Best-View Planning for Robotic Grasping**, CoRL 2023 / PMLR 229:2849–2862. [공식 게재](https://proceedings.mlr.press/v229/zhang23i.html), [저자 원문 v2](https://arxiv.org/html/2309.09556v2). | §§3–4의 depth/TSDF·view-aware grasp objective·NBV stop criteria·training, §5 setup, Appendix D의 grasp prediction 오류 사례. 전체 장면 coverage보다 다음 grasp 결정과 연결된 관측 목적을 쓰는 접근. | depth camera·3D bounding box·TSDF·학습된 grasp/novel-view network·GT grasp supervision을 쓴다. OpenCV own-RGB의 즉시 사용 baseline이 아니다. view/grasp 방향의 일치는 보편 최적성 정리가 아니다. repo 코드는 읽거나 실행하지 않았다. |
| R8-6 | Falanga, Foehn, Lu & Scaramuzza, **PAMPC: Perception-Aware Model Predictive Control for Quadrotors**, IROS 2018. [저자 기관 PDF](https://rpg.ifi.uzh.ch/docs/IROS18_Falanga.pdf), [arXiv record](https://arxiv.org/abs/1804.04811). | §§III-C/IV의 pinhole projection·image-plane velocity와 목적함수, §VI setup의 onboard VIO, §VII의 perception objective가 hard constraint가 아니라 cost라는 설명. 시야 확보뿐 아니라 움직임 중 영상 품질과 행동 목적 충돌을 다룬다. | quadrotor dynamics·3D point of interest·고정 extrinsic·VIO를 사용한다. 현재 팔 명령을 실제 camera twist로 치환할 수 없다. 'visibility 보장', 'collision 보장', 'wrist look은 항상 안전'의 근거로 쓰지 않는다. |
| R8-7 | Cui et al., **Imagine then Verify: Affordance-Targeted Active Perception for Task-Oriented Grasping in Cluttered Scenes**, [arXiv 2609.23504v1](https://arxiv.org/html/2609.23504v1), 2026-09-20. **preprint**, 게재 확인 없음. | §§III–IV 전체와 §V-A setup. RGB-D+EE pose 입력, 여러 registration hypothesis, 실제 depth로 verification, surrogate disambiguation gain, feasible-view checks, verification와 entropy를 함께 쓰는 종료 규칙 확인. | measured EE pose·RGB-D·VLM/SAM/shape completion/AnyGrasp를 포함한다. 등록 score softmax와 surrogate binary likelihood는 UGRP calibrated posterior가 아니다. 새 신경망 도입·정보량 수치 계산·성공 보장의 근거로 쓰지 않는다. 코드 공개/재현은 확인하지 않았다. |

## 확인이 제한된 출처

- PR #363에서 인용한 **Blackmore, Ono & Williams, Chance-Constrained Optimal Path Planning With Obstacles, T-RO 27(6), 2011, DOI 10.1109/TRO.2011.2161160**: [IEEE 공식 record](https://ieeexplore.ieee.org/document/5970128/)의 초록/서지에서 linear-Gaussian scope는 확인했지만, 이번에 2011년 전문을 확보하지 못했다. 위 R8-3은 같은 계열의 **다른 2009년 논문**이며 2011년 전문 확인을 대신했다고 표기하지 않는다.
- **Risk-Aware Active Perception and Control in Sensing-Constrained Environments**, Zhu, Simeon & Cognetti, [ICRA 2026 ASAB workshop OpenReview](https://openreview.net/forum?id=80KLnouc62): 공식 목록/제목을 찾았으나 PDF 접근이 verification page로 끝났다. 본문을 읽지 못했으므로 기술 주장이나 보장을 근거로 사용하지 않는다.
- MLESAC의 Oxford URL은 첫 직접 open에서 timeout, 공식 목록 PDF 링크 재시도로 원문을 확보했다. Oxford ORA mirror는 403이었다. 403 mirror의 전문을 읽었다고 하지 않는다.

## 코드/공개 보고의 시간 경계

- 읽은 코드: PR #363 `0d7c5eb3ca3643ead2a0b50dd133a1188f06f572`. 관련 파일은 `harness/own_beam_edge.py`, `zone_pair_highpose_runtime.py`, `zone_pair_highpose_blind_close.py`, `zone_pair_highpose_lookaround.py`와 자세 정의. `zone_pair_highpose_start_relief.py`의 거부 분기 및 `tests/test_highpose_start_relief.py`의 과거 8.7초 회귀검사도 대조했다. 전체 변경 diff를 이 연구 에이전트가 재검토한 것은 아니다.
- [PR #363](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363) body는 frontier 에이전트가 공식 GitHub fetch로 저장한 `pr363_data.json`을 읽었다. `raise_high_align`의 REACHED와 `align_to_carry`의 edge timeout은 **작성자 공개 보고**다. 우리 물리 재현이 아니다.
- `0865a788`의 시작 완화와 `9.0s inside_pair_deeper` 보고를 최신 head의 실행 결과로 옮기지 않는다. frontier가 확인한 `0d7c5eb3`의 수정은 과거 첫 `8.7s` 명령을 `start_outside_pair_enters`로 거부하는 회귀검사를 포함한다.
- geometry 에이전트의 `geometry-repro.json`은 합성 RGB로 실제 검출기/트래커를 실행한 코드 증거다. 실제 HIGH 영상의 clipping 빈도나 public timeout의 원인을 그 결과로 확정하지 않는다.

## 조회 위치 기록

웹 도구 retrieval refs는 출처의 제목/버전/직접 읽은 범위를 대체하지 않는다. root가 최종 답변에서 웹 citation을 쓰면 해당 URL을 직접 open/find해야 한다. 문서 본문에는 위 canonical URL을 쓴다.

- R8-1: `turn137view2`, `turn139view3`, `turn140view0`; 기관 record `turn136view2`.
- R8-2: `turn135view1`, `turn136view3`.
- R8-3: `turn136view0`, `turn137view0`, `turn138view1`, `turn140view2`.
- R8-4: `turn136view1`, `turn137view1`, `turn139view0`, `turn140view1`.
- R8-5: `turn121search15`, `turn123view1`, `turn125view0`, `turn134view1`.
- R8-6: `turn123view2`, `turn132view0–2`, `turn134view0`.
- R8-7: `turn122search14`, `turn123view0`.

본문은 요약과 검토자의 추론이며, 논문 원문을 길게 옮기지 않았다.
