# R9 신규 primary source 증거표

열람일: 2026-10-04 UTC. R1–R8의 기존 논문 요약을 반복하지 않고 정보의 출처·시간·공통성을 판별하는 데 필요한 다섯 원문을 선택했다. 전문을 모두 읽었다는 뜻이 아니다. 아래 명시 범위를 직접 열람했다. UGRP의 실제 실험 결과·novelty 증명으로 사용하지 않는다.

| ID | 정확한 원문 / 버전 | 직접 읽은 범위 | 확인한 좁은 주장 / 가정 | UGRP에 승계할 수 없는 것 |
|---|---|---|---|---|
| P1 | Lee-Ling Ong, Ben Upcroft, Matthew Ridley, Tim Bailey, Salah Sukkarieh, Hugh Durrant-Whyte. **Decentralised Data Fusion with Particles**, ACRA 2005. [저자 소속기관 PDF](https://www-personal.acfr.usyd.edu.au/tbailey/papers/acra2005particleddf.pdf); [저자 publication list](https://www-personal.acfr.usyd.edu.au/tbailey/publications/publications_all.htm) | PDF pp.1–4, 특히 §4.1 Eq.(5), 초록·DDF 구성·channel filter | 통신한 posterior의 공통 정보를 추적/제거하는 channel filter로 중복 계수를 피한다. 서로 다른 particle 집합을 그대로 나누기 어려워 연속 표현을 사용한다. | 현재 LLM 자연어는 calibrated density가 아니다. 이 원문으로 LLM 동의를 posterior 곱으로 계산하거나 UGRP repeat_rho 값을 정당화하지 못한다. |
| P2 | Abhijnan Nath, Hannah VanderHoeven, Nikhil Krishnaswamy. **CRAFT: Grounded Multi-Agent Coordination Under Partial Information**, [arXiv v1, 2026-03-26](https://arxiv.org/html/2603.25268v1). [저자 코드](https://github.com/csu-signal/CRAFT) | §3/Thm3.3 조건, §4.1–4.3, §5.2, §6.2, Appendix E의 SG/MM/PS judge 정의 | 3명의 director가 서로 다른 고정 2D target projection을 갖고, builder는 메시지·board와 최대 5개 oracle progress move 후보를 받는다. 개별 메시지 평가와 collective sufficiency를 구분한다. 이론은 명시된 base-speaker/ToM 가정에 의존한다. | oracle 후보를 주는 동기식 construction과 UGRP own-wrist RGB/비동기 실행은 입력·권한이 다르다. judge 점수는 인과 attribution·독립 센서 확인·로봇 안전 보증이 아니다. |
| P3 | Kale-ab Abebe Tessera et al. **Benchmarking Open-Ended Multi-Agent Coordination in Language Agents**, [arXiv v1, 2026-06-06](https://arxiv.org/html/2606.08340v1). [저자 프로젝트](https://alem-world.github.io/), [코드](https://github.com/alem-world/alem-env) | §3.4, §4.1, §4.2.2, Appendix C.5, Appendix I의 lexical metrics 정의·한계 | alem LLM 평가는 text observation, explicit legal actions, coordination requirements, teammate 상태와 메시지를 제공한다. communication/memory/reasoning ablation을 분리한다. lexical 지표는 저자 스스로 proxy라고 명시한다. | pixel-capable 환경이라는 이유로 해당 LLM baseline을 own-RGB-only라고 부르면 안 된다. 메시지 단어·길이·ack 수가 의미의 사용 또는 task 정보 획득을 증명하지 않는다. |
| P4 | Yiheng Yao, Chelsea Zou, Robert D. Hawkins. **Talk is Cheap, Communication is Hard: Dynamic Grounding Failures and Repair in Multi-Agent Negotiation**, [arXiv PDF v2, 2026-05-12](https://arxiv.org/pdf/2605.01750v2) | PDF pp.1–4(task/선정), §5.1–5.2, §5.7, 관련 Table9/Appendix F 문단 | private project를 가진 두 agent가 대화 후 독립 allocation을 제출한다. 평가 시나리오는 모든 대상 모델이 full-info 단독 pass@1을 통과한 pool로 제한된다. full-transparency 비교에서도 일부 coordination 문제는 남는다. | 본문상 under-review preprint이다. 선택된 symbolic resource game의 잔여 gap을 UGRP의 순수 “grounding 결함”으로 단정할 수 없다. full-info 개입은 UGRP 실행 입력 계약에 넣지 않는다. |
| P5 | Hachem Madmoun, Salem Lahlou. **Communication Enables Cooperation in LLM Agents: A Comparison with Curriculum-Based Approaches**, EACL 2026 Short Papers, pp.307–321. [공식 metadata](https://aclanthology.org/2026.eacl-short.23/), [공식 최종 PDF](https://aclanthology.org/2026.eacl-short.23.pdf), DOI 10.18653/v1/2026.eacl-short.23 | §3.2, §4.1, Appendix E.1/E.2의 실제 communication/action prompt | 4-player Stag Hunt에서 one-word broadcast를 보내는 별도 단계 후 받은 단어를 넣어 action을 결정한다. 환경 사실을 추가 측정하지 않아도 의도 조정에 메시지가 쓰이는 구성이다. | 통신 조건은 별도 call/stage와 history도 갖는다. 순수 의미 내용만의 효과 또는 물리 시간 비용이 같은 대조라고 이 논문만으로 해석하지 않는다. 다른 preprint 요약의 숫자 대신 공식 최종판을 기준으로 삼았다. |

## 원문 기반 연결과 우리 추론의 경계

- P1은 통계적 common information 문제의 근거다. **UGRP 메시지에 event provenance를 붙여 읽자**는 분석 제안은 본 리뷰의 추론이며 P1이 자연어에 대해 입증한 결과가 아니다.
- P2/P3는 비교 시 input/actuation/oracle disclosure를 먼저 대조해야 한다는 근거다. UGRP가 이보다 우월하거나 처음이라는 결론은 내리지 않는다.
- P4/P5는 정보 전달, 의도 합의, 약속 이행을 동일한 현상으로 뭉뚱그리기 어렵다는 관련 사례다. 두 원문의 model/과제/선택/시간 구조가 UGRP와 달라 정량 효과를 이전하지 않는다.
- PF 지수의 정적 Gaussian 계산은 `pf-theory.md`의 직접 유도이다. P1을 그 지수의 보장으로 인용하지 않는다.

## 확보하지 못했거나 사용하지 않은 자료

- Uhlmann의 *Covariance Consistency Methods for Fault-Tolerant Distributed Data Fusion* (2003): 저자 publication list 링크는 확인했으나 PDF fetch 502. 본문을 읽은 것처럼 CI 정리를 인용하지 않았다.
- Julier–Uhlmann ACC1997: 서지 확인만 했다. 현재 산출물에서 원문 정리의 적용을 주장하지 않는다.
- Kish 1965: 최신 UGRP 소스의 서지 주석만 확인했다. 원문 책을 열람하지 않았으며 `c_K` 해석은 본 리뷰에 전개한 수학으로 한정한다.
- I2C NeurIPS2020, When2com CVPR2020: 후보로 찾았으나 핵심 원문 충분 열람을 완료하지 않아 이번 비교표에 포함하지 않았다.
- 공개 논문 사이트의 수치·저자 진술은 해당 과제의 공개 보고이며 독립 재현 결과가 아니다. 이 문서 작성 중 새 LLM/physics/hardware 실험은 실행하지 않았다.

## UGRP 코드 증거 묶음

상위 policy/request: PR #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`. `research-source/manifest.json`에 다섯 직접 사본의 hash를 기록했다. PF: PR #363 `6727751b`의 `vision-source/zone_pair_highpose_pf_consistency.py`. main/current PR/old public trace를 섞지 않는다. 공개 thread의 실행 결과를 읽어 연구 효과로 재분석하지 않았다.
