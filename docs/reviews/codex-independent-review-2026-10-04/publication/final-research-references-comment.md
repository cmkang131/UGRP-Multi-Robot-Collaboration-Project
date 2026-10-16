연구 이슈의 참고 댓글 1/2 — 원문과 적용 범위. 논문 성능을 UGRP와 직접 비교하거나 외부 코드를 재현했다고 주장하지 않습니다. 아래 표의 기여는 연구 후보이며 현재 입증된 novelty가 아닙니다.

## A. 통신·계획 문헌 14편: 가져올 것과 가져오면 안 되는 것

논문 성능 수치를 UGRP와 직접 비교하지 않습니다. 아래는 primary 원문·저자 공식 자료를 읽은 적용 판단이며 외부 코드 재현 결과는 아닙니다. 2026 preprint 두 편은 심사된 확정 결과로 취급하지 않습니다.

| 원문 | 현재 연구에 유용한 점 | UGRP 적용 한계 |
|---|---|---|
| [CoELA, ICLR 2024](https://arxiv.org/html/2307.02485v2) | 모듈 분리, 부분관측, 통신 제거 기준선. 저자는 AI끼리 통신 제거에서 뚜렷한 하락을 관찰하지 못했다고 보고합니다. | RGB-D/semantic map 및 고수준 실행. 자연어 통신의 필요성이나 통계적 동등성을 증명한 것으로 인용하지 않습니다. |
| [RoCo, ICRA 2024](https://arxiv.org/html/2307.04738v1) | 거절 이유를 활용한 재계획과 bounded retry. | 확인한 상세판은 v1. 정확한 perception/oracle state와 중앙 multi-arm RRT가 있어 완전 분산 RGB 공동운반과 다릅니다. |
| [SMART-LLM, IROS 2024](https://arxiv.org/html/2309.10062) | task decomposition, coalition, capability/선행관계 검사. | 중앙 상위 pipeline입니다. `No Comm. & Summ.`는 코드 comments/summaries 제거이며 로봇 통신 제거가 아닙니다. |
| [PARTNR, ICLR 2025](https://arxiv.org/pdf/2411.00081) | oracle/learned skill·인식 경로를 분리해 실행 병목을 측정합니다. | world graph/skill abstraction. UGRP에서 실행기 진단을 먼저 하자는 것은 이 비교를 적용한 검토자의 추론입니다. |
| [EMOS, ICLR 2025](https://arxiv.org/html/2410.22662v2) | embodiment capability와 논의/실행 분리, 성능과 토큰 비용 동시 보고. | GT world 정보, 중앙 group discussion, physics/collision OFF 및 snap-grasp. no-discussion은 계획구조도 달라지는 단순 baseline이며 pure channel effect가 아닙니다. |
| [LiP-LLM, RA-L 2025](https://arxiv.org/html/2410.21040v1) | skill DAG와 할당 feasibility 검사. | 알려진 위치·중앙 LP; 한 skill에 최대 한 robot인 가정은 두 carrier 공동 파지와 다릅니다. 공식 코드 재현 없음. |
| [World Models Through Dialogue, SIGDIAL 2026](https://aclanthology.org/2026.sigdial-1.21.pdf) | 대화로 충돌이 줄어도 성공이 나빠질 수 있다는 부정 결과. | oracle motor skills. N=100/공통 종료 N=80 보고 차이와 nontermination 제외에 주의하며 보편 법칙으로 쓰지 않습니다. |
| [MECoBench, 2026 preprint](https://arxiv.org/html/2606.31966v1) | 계획된 no_comm/peer/leader 비교와 비용축에 가깝지만, structured와의 동일 의미 비교는 별도입니다. | visible candidates/bbox/metadata로 action grounding. 단순 프로토콜 비교만으로 새로움을 주장하기 어렵습니다. |
| [CoCoBench, 2026 preprint](https://arxiv.org/html/2608.28266v1) | allocation/ordering/mutual exclusion/handoff별 실패 분류. | scene metadata로 실행 가능한 action menu 생성. 영상이 입력에 있다는 것만으로 시각 grounding을 검증한 것은 아닙니다. |
| [TarMAC, ICML 2019](https://proceedings.mlr.press/v97/das19a.html) | 수신 대상·통신 횟수를 구분해 비교하는 원칙. | 학습된 연속 message와 MARL task; 즉시 쓸 LLM/RGB 운반 baseline이 아닙니다. |
| [IC3Net, ICLR 2019](https://arxiv.org/pdf/1812.09755) | 학습된 통신 여부 gate와 침묵 선택. | symbolic observation/학습 gate·reward가 함께 바뀝니다. 재학습을 현재 선행조건으로 두지 않습니다. |
| [A Cordial Sync/FurnMove, ECCV 2020](https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123500460.pdf) | 공동 물체 이동의 동기화 연구이며, 무대화 기준선도 실행 가능해야 한다는 UGRP 설계에 참고합니다. | 시작부터 물체를 들고 이산 coordinated moves를 사용하므로 자연 파지·접촉 성능 증거가 아닙니다. |
| [CBBA, T-RO 2009](https://dspace.mit.edu/entities/publication/b0bf0a05-be3b-433b-9f4b-ce314ed5178b) | 작은 명시적 claim/ack 또는 local-cost 할당 baseline의 필요성. | scoring/connectivity 가정, coalition 확장 필요. 초록/저자 자료 확인이며 PDF 전문 미확보. exact CBBA를 구현하지 않으면 그 이름을 붙이지 않습니다. |
| [Pitfalls of Measuring Emergent Communication, AAMAS 2019](https://ifaamas.org/Proceedings/aamas2019/pdfs/p693.pdf) | 메시지와 행동의 상관, 상대 행동에 대한 인과영향, 성공 개선을 분리합니다. | 작은 게임 연구. logprob 없는 LLM에서 CIC 값을 흉내 내지 않고 상태를 맞춘 deliver/drop의 행동 분포·결과 차이를 별도 진단합니다. |

가능한 기여는 **허용된 정보가 실행 단계까지 유지되는 연속 접촉 공동운반에서, 통신의 이득·손해를 실패/비용/비대칭 관측과 함께 측정**하는 것입니다. 현재 입증된 novelty가 아니라, 위 비교표와 실제 인수 결과가 갖춰졌을 때 검증할 주장입니다.

## B. 위치추정·공동운반 문헌을 현재 병목에 적용하는 방법

OpenCV 특징, known-map 기하, 자기 명령 예측, 관측 가능한 자유도만의 국소 보정은 현재 경계 안의 후보입니다. 어떤 기법도 실제 관측이 없는 프레임을 성공 측정으로 바꾸어 주지는 않습니다.

| 원문/공식 구현 | 바로 쓸 수 있는 질문 | 제한 |
|---|---|---|
| [Shi–Tomasi 1994](https://publications.ri.cmu.edu/storage/publications/pub_files/pub2/shi_jianbo_1994_1/shi_jianbo_1994_1.pdf), [OpenCV LK/ECC](https://docs.opencv.org/4.13.0/dc/d6b/group__video__track.html) | 단색/한 방향 edge/분산된 corner 중 무엇인가? 최소 고유값·추적 status·공간 분포를 기록합니다. | 좋은 tracking corner도 지도 대응이나 pose 관측 가능성을 보장하지 않습니다. 같은 선의 많은 픽셀은 독립 위치 정보가 아닙니다. |
| [Chaumette–Hutchinson 2006](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf) | 필요한 2–3 자유도에 대해 feature Jacobian의 rank/conditioning이 충분한가? | IBVS는 calibration/depth와 무관하지 않으며 camera twist를 PWM으로 바로 치환할 수 없습니다. |
| [Malis 등 1999, 2.5D servoing](https://www.cs.jhu.edu/~hager/Public/teaching/CS600.641/Malis2-1-2DTRA99.pdf) | 같은 평면의 비퇴화 natural correspondence가 실제로 있는가? | 문/빔의 선 하나는 homography를 위한 네 비퇴화 대응점이 아닙니다. 여러 벽·바닥·움직이는 빔에 단일 평면을 가정하지 않습니다. |
| [Collins–Bartoli 2014/IPPE](https://link.springer.com/article/10.1007/s11263-014-0725-5), [저자 구현](https://github.com/tobycollins/IPPE), [OpenCV PnP](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html) | 알려진 자연 평면 특징이 있을 때 두 pose 가설/positive depth/reprojection를 보존할 수 있는가? | low reprojection 하나만 고르고 좁은 covariance를 부여하면 ambiguity를 숨깁니다. IPPE_SQUARE는 임의 문 모양용이 아닙니다. |
| [Evangelidis–Psarakis 2008/ECC](https://doi.org/10.1109/TPAMI.2008.113) | 겹침이 충분한 같은 평면 ROI의 국소 정렬이 가능한가? | 초록·저자 자료·OpenCV API까지 확인. 높은 ECC는 metric pose나 파지 성공이 아닙니다. clipped/단색 ROI에 만능 대안이 아닙니다. |
| [Spica 등 2017](https://journals.sagepub.com/doi/10.1177/0278364917728327) | 승인된 작은 관측 동작이 불확실한 방향에 새 정보를 주는가? | 초록·서지까지 확인. 논문의 active controller 전체 도입을 권하지 않으며 손목 동작의 파지 영향 확인이 선행됩니다. |
| [Verginis 등, force/torque 측정 없는 cooperative manipulation](https://arxiv.org/html/1710.11088v4) | 두 grasp point 목표가 하나의 rigid-body twist에 맞는가? | force/torque 측정을 쓰지 않는다는 뜻이지 joint feedback도 없다는 뜻은 아닙니다. joint feedback/rigid grasp 가정의 안정성 보장을 no-weld own-command 경로에 승계할 수 없습니다. |
| [Zhang 등 2025, dual-arm IBVS](https://arxiv.org/html/2410.19432v4) | 상대 영상 잔차를 동기화 품질 지표로 쓸 수 있는가? | 상대 wrist AprilTag 4 corners와 joint feedback을 사용하므로 marker0 계약에 직접 이식 불가. 자연 edge로 바꾸면 관측 rank도 다시 검증해야 합니다. |

## C. 관측·통신 판단의 추가 primary 근거

| 원문 | 이번 판단에 사용한 범위 | 승계하지 않는 가정 |
|---|---|---|
| [Hermann–Krener 1977](https://www.math.ucdavis.edu/~krener/1-25/10.IEEETAC77.pdf), §III·Theorem3.1 | local weak observability rank의 충분조건. 단일 rank 부족과 비선형 불가능을 구분 | finite noise·unknown calibration·global map alias 자동 해결 |
| [Huang 등 RSS2009](https://www.roboticsproceedings.org/rss05/p9.pdf), §II/IV | unobservable 방향의 허위 covariance 수축과 cross-correlation 구분 | odometry/relative EKF를 UGRP PF의 동일 모형으로 치환 |
| [Lynch–Park, Modern Robotics §12.2.3](https://hades.mech.northwestern.edu/images/2/2e/MR-largefont-v2.pdf) | force-closure wrench cone과 충분한 실제 내부 힘은 별개 | no-weld RGB 기하만으로 squeeze/slip margin을 복원 |
| [Cover–Thomas §2.8](https://onlinelibrary.wiley.com/doi/10.1002/0471200611.ch2) | data-processing의 조건부 적용; 같은 joint history의 transcript 분포 보존 | 출판사 chapter summary 확인이며 책 전문을 새로 확보한 것은 아님 |
| [Glasserman–Yao 1992](https://business.columbia.edu/sites/default/files-efs/pubfiles/4261/glasserman_yao_guidelines.pdf) | 같은 seed만으로 CRN 분산 감소를 보장 못함. 대응 event/covariance 중요 | logical-event key 설계는 UGRP를 위한 검토자 제안이며 논문의 로봇 구현 처방 아님 |
| [Goldman–Zilberstein, JAIR2008](https://arxiv.org/pdf/1111.0065) | costly/null message와 언제 공유할지의 오래된 질문 | transition/observation 독립성과 joint observability를 공통 beam에 그대로 대입 |
| [Balch–Arkin 1994](https://repository.gatech.edu/entities/publication/5e906853-3f08-4611-aafd-70b41ef8bfa0) | 공식 abstract의 task별 통신 불필요/단순 채널 가능성 | PDF 추출 불량으로 수치·개별 task 표는 인용하지 않음 |
