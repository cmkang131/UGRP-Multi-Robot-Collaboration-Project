# R19 — 새 1차 문헌의 버전·열람 기록

확인일: 2026-10-04 UTC. 문헌/공식 메타데이터 열람만 수행했다. 논문 코드·훈련자료·calibration dataset·UGRP 원본 결과는 열지 않았다. 제목/초록만으로 포함하지 않았고 아래 세 편의 방법·평가·제한을 읽었다. 성능 수치를 재현하거나 순위를 매기지 않는다.

| ID | 정확한 1차 원문·메타데이터 | 최신/게재 확인 수준 | 실제 읽은 범위 |
|---|---|---|---|
| P19-1 | [CHORUS arXiv 2606.12352v1 HTML](https://arxiv.org/html/2606.12352v1), [arXiv 기록](https://arxiv.org/abs/2606.12352), [저자 프로젝트](https://chorus-model.github.io/) | arXiv v1 제출 2026-06-10. 저자 프로젝트는 CoRL 2026이라고 표기한다. 이번 검색에서는 공식 proceedings/final-version 동일성을 별도로 확인하지 못했다. 본문 비교는 v1에 한정한다. | §3.1–3.3 local tuple/visibility/deployment, §4–5 평가·제한, Table 1, Appendix A–D 및 Fig.7 camera views. 특히 App.B의 synchronized basket 예외, App.B의 partial credit을 대조했다. |
| P19-2 | [CommCP arXiv 2602.06038v1 HTML](https://arxiv.org/html/2602.06038v1), [arXiv 기록](https://arxiv.org/abs/2602.06038), [저자 프로젝트](https://comm-cp.github.io/) | arXiv v1 제출 2026-02-05. arXiv comment와 프로젝트는 ICRA 2026으로 표기한다. 공식 최종 proceedings 본문과 v1의 동일성은 별도 확인하지 못했다. | §III observation/task, §IV-A–E 전체 방법, Eq1–2, §V-A–D benchmark/ablation/implementation/results. 특히 §IV-B label/확률 사건과 §V-B object-count control을 읽었다. |
| P19-3 | [Planned synchronization for multi-robot systems with active observations — Springer 공식 원문](https://link.springer.com/article/10.1007/s10514-025-10225-4), [DOI](https://doi.org/10.1007/s10514-025-10225-4), [저자 출판 목록](https://cse-robotics.engr.tamu.edu/dshell/pubs.html) | 공식 publisher가 VoR 2025-12-24, Autonomous Robots 50, article 5 (2026)를 표시한다. accepted 2025-10-16. journal 본문을 직접 읽었다. | §3.1–3.2 formulation, §4.3–4.4, §5 hardware/evaluation, §6.1–6.1.2 비이상성, §7 conclusion. observation 불일치와 hold/동기화, uncoupled/no-drift 가정을 확인했다. |

## 근거를 쓰는 범위

- P19-1: local conditioning, 시연 중 가시성, own proprioception, task-specific score. 무통신 일반 우위나 UGRP 관측 충분성의 증거로 쓰지 않는다.
- P19-2: 관련 내용을 고르는 통신 대조와 CP label/표본의 적용 조건. CP 수식을 UGRP의 메시지 사실 확률·안전 확률로 바꾸지 않는다. quantile을 95% coverage로 고쳐 쓰지 않는다.
- P19-3: 관측·rescheduling 비용을 포함한 계획, 공동 상태 복구 및 하드웨어 감지 조건. UGRP의 fixed barrier/부분 pose fix를 완전 joint state로 가정하지 않는다.

[비교·최소 반증 설계](research.md)의 probe는 이 검토자의 제안이며 논문의 실행 실험이나 이미 존재하는 UGRP 결과가 아니다. [geometry QA](validation.md#geometry-scope)와 [통계 QA](validation.md#statistical-scope)는 별도 원문 열람이며 실행 검증이 아니다.

## 중복 제거와 검색 한계

초기 문헌/최종 참고문헌 목록, `round7-primary-evidence.md`, R8/R9의 `primary-source-evidence.md`, 이후 R13/R15/R16 자료를 대조하고 세 제목·식별자의 중복을 `rg`로 확인했다. 기존 CoELA/RoCo/PARTNR/EMOS, CRAFT/AgentComm, active-perception/ATAP, common-information/knowledge-of-preconditions 등은 이번에 새 항목으로 다시 세지 않았다.

2025–2026 multi-robot decentralized local observation, communication ablation, active observation synchronization을 검색한 뒤 공식 arXiv·저자 프로젝트·Springer 원문으로 좁혔다. RoboTalk/AirCopBench 등 제목 수준 후보는 깊은 비교에 넣지 않았다. 검색 coverage의 완전성이나 ‘가장 최신 세 편’은 주장하지 않는다. CHORUS와 CommCP의 venue는 저자 표기까지 확인된 수준을 유지하며, 검색에서 proceedings를 찾지 못한 사실은 미게재의 증거가 아니다. 세 선정 원문 모두 HTML 본문에 접근했고 접근 불가 절을 추정으로 채우지 않았다.
