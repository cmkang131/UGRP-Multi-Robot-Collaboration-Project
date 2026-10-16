# 8차 연구 문서 독립 검증

2026-10-04 UTC. 평가 감사 담당이 연구 담당의 `research-insights.md`, `primary-source-evidence.md`, `research-math-checks.py`, `research-math-results.json`을 별도로 검토했다. 구현·실험·raw 열람은 없다.

## 판정

두 표현의 모호함을 수정한 뒤, 검토한 범위에서 추가 차단 사유를 찾지 못했다. HIGH 검출 실패와 crop 경계를 참 경계로 받아들이는 잘못된 성공, 상대 yaw와 절대 heading, 운영상 기억 허용 시간과 실제 물리 오차 보장을 분리한 점이 타당하다. 다음과 같은 제한을 유지해야 한다.

- 0865a788의 접근 실패·44 mm/2.6 mm 공개 요약은 과거 witness다. 최신 0d7c5eb3의 실행 결과나 tail probability로 바꾸지 않는다.
- ROI 합성 반례는 검출기와 트래커의 코드 반례이며 실제 HIGH 영상에서의 빈도·공개 timeout의 원인을 추정하지 않는다.
- `Phi(-d/sqrt(n^T Sigma n))`는 명시된 무편향 Gaussian 단일 half-space 모형의 식이다. 현재 PF·cap·start relief·전체 경로의 확률 인증이 아니다.
- 두 오류 평균의 분산 예시는 동일 분산·상관 rho 가정 아래 정확하지만 production의 두 번 통과 gate를 평균 추정기로 치환하지 않는다.
- blind window의 운영 시간만으로 물리 오차 한계를 만들 수 없다. 선형 최악 오차식에는 실제 상대 속도·회전속도·lever·초기 오차 bound가 별도로 필요하다.
- 관련 논문의 depth, 측정 pose, 학습 모듈과 모델 likelihood 가정을 UGRP의 own-RGB·발행 명령 입력에 소급하지 않는다.

## 독립 확인한 근거

다음 7개 출처의 **사용 주장에 해당하는 부분**을 직접 열고 확인했다. 전문 전체 검토나 외부 구현 재현을 했다는 의미는 아니다.

| 출처 | 별도 대조한 핵심 |
|---|---|
| [MLESAC](https://www.robots.ox.ac.uk/~vgg/publications/2000/Torr00/torr00.pdf) | 최소제곱 초기값의 취약성과 강건 초기 추정의 필요성. 이를 crop/물체 동일성 해결책으로 승격하지 않는 해석 |
| [OpenCV fitLine](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html) | 여러 loss의 점집합 line fitting. 입력 점의 물리 의미를 보증하는 기능은 아님 |
| [Blackmore–Ono 2009](https://groups.csail.mit.edu/mers/old-site/papers/BlackmoreOnoGNC09.pdf) | Gaussian/선형 가정, projected scalar variance, 개별 제약과 joint risk allocation, finite-horizon 보장의 범위 |
| [Blackmore–Williams 2006](https://groups.csail.mit.edu/mers/old-site/papers/Blackmore-Williams-CDC06-paper.pdf) | 알려진 유한 모델 집합과 입력에 따른 구별 가능성, expected-state 제약을 물리 무조건 보장으로 바꾸지 않음 |
| [ACE-NBV](https://arxiv.org/html/2309.09556v2) | depth/TSDF·학습 affordance·GT supervision을 사용하는 next-view 목적 |
| [PAMPC](https://rpg.ifi.uzh.ch/docs/IROS18_Falanga.pdf) | visibility/image velocity가 perception cost이며 해당 구현의 hard visibility 보장은 아님 |
| [ATAP v1](https://arxiv.org/html/2609.23504v1) | RGB-D와 EE pose 입력, 실제 관측 verification와 surrogate disambiguation gain의 구별 |

`own_beam_edge.py`, `zone_pair_highpose_blind_close.py`, `zone_pair_highpose_lookaround.py`의 최신 고정 코드와 연구 문구도 별도로 대조했다. 합성 수학 스크립트를 다시 실행한 출력은 보관된 JSON과 바이트 단위로 같았다. geometry의 합성 검출 JSON은 읽었지만 해당 RGB 재현을 이 검토에서 다시 실행한 것으로 세지 않는다.

## 반영된 정정

1. “beam 자체의 common-mode 회전이 안 보인다”는 표현은 beam만 회전해도 안 보인다고 읽힐 수 있었다. 수정본은 **로봇과 beam이 같은 각도로 함께 도는 세계 기준 공통 회전**이 상대 측정만으로 구별되지 않는다고 적고, beam 단독 회전은 상대 yaw 변화임을 명시한다.
2. crop 다음 행의 색을 읽는 검사는 **색 마스크의 종료/검열**을 가른다. 그 자체가 원하는 beam이라는 물체 동일성을 인증하지는 않는다는 한계를 추가했다.

둘 다 논지를 정확히 한 수정이며 별도 신규 코드 결함으로 세지 않는다. 실제 안전성·실험 성공·논문 결과의 재현을 승인하는 문서가 아니다.
