# R15 — 성공 정의/평가 분리에 관한 1차 근거와 읽은 범위

2026-10-04. 핵심 질문은 현재 UGRP의 명령 절차 완료와 별도 과제 판정의 연결이다. 기존 R1–13의 provisional judge, 부분 관측, communication causal review를 새 연구 결과처럼 반복하지 않았다. 아래는 모두 저자·학회·공식 프로젝트 원문이다. 실제 UGRP 결과/GT 자료는 읽지 않았다.

## P1. BEHAVIOR: Benchmark for Everyday Household Activities in Virtual, Interactive, and Ecological Environments

- 저자/서지: Sanjana Srivastava et al.; CoRL 2021, PMLR 164:477–490, 2022.
- 원문: https://proceedings.mlr.press/v164/srivastava22a/srivastava22a.pdf
- 읽은 깊이: abstract/introduction, §4–6 및 §7의 observation/reward/actuation 조건과 관련 논의. PDF 14쪽 중 해당 본문 4–8쪽을 parsed text로 직접 읽었다. appendix 전체나 구현 repository를 전수 읽은 것은 아니다.
- 원문에서 확인한 범위: §4의 initial/goal state와 declarative goal 구분; §5의 sensor/action와 simulator predicate 평가; §6의 goal 만족/partial score; §7의 RGB·depth·proprioception과 Q reward 사용.
- UGRP에 적용하는 추론: 동일한 제어 실행의 절차와 goal predicate를 따로 검사할 수 있다. GT evaluator를 썼다는 것만으로 RGB 정책이 GT를 입력받았다고 결론내리지 않는다.
- 적용하지 않는 주장: 이 논문이 UGRP의 task 성공 기준을 결정한다거나, 그 실험과 UGRP가 같은 input/reward 계약이라는 주장. 성능 수치·접촉 모델·실물 전이를 옮겨오지 않는다. BDDL 도입도 요구하지 않는다.

## P2. BEHAVIOR 공식 Benchmark Setup 문서

- URL: https://stanfordvl.github.io/behavior/setups.html
- 읽은 깊이: 페이지 전체, 특히 Original Setup / Changing Observations / Changing Actuation.
- 확인한 주장: 공식 문서는 onboard sensor와 control command를 기본 설정으로 놓고, localization·scene graph·full simulator observability 및 다른 action primitives를 별도 설정으로 구분한다.
- UGRP에 적용하는 추론: 평가 convenience를 이유로 privileged state를 현재 정책에 추가하면 관측 계약 변경이다. primitive 이름뿐 아니라 실제 구현과 주어진 권한을 함께 비교해야 한다.
- 한계: 문서의 센서 종류·주기·primitive를 UGRP에 그대로 적용하는 권고가 아니다.

## P3. Vision-Language Models as Success Detectors — 범위 선별만 수행

- 저자/서지: Yuqing Du et al.; CoLLAs 2023, PMLR 232:120–136.
- 공식 landing/abstract: https://proceedings.mlr.press/v232/du23b.html
- PDF: https://proceedings.mlr.press/v232/du23b/du23b.pdf
- 읽은 깊이: **공식 abstract와 서지만 직접 읽었다. PDF는 도구의 크기 제한으로 열지 못했으므로 full-text 검토라고 보고하지 않는다.**
- 선별한 내용: 저자들은 pretrained VLM과 human reward annotation을 이용한 success detection을 별도의 VQA 문제로 연구한다.
- 이번 문서의 증거 사용: 핵심 source 판단이나 detector 성능 주장에 사용하지 않았다. 현 OpenCV final 경로에 VLM을 넣으라는 제안도 아니다. 원문 방법·데이터 분할·정량 성능을 확인하지 못한 상태이므로 관련 수치는 전하지 않는다.

## 코드와 논문을 결합할 때의 경계

[success-evidence-contract.md](research.md)의 구체적인 C/unknown/provisional 판정과 timing은 UGRP exact source 근거다. 문헌은 goal specification·observation/action 설정의 분리라는 설계 맥락만 보완한다. 제안한 동일-input/다른-eval-label 대조는 아직 실행하지 않았으며, 현재 정상 dataflow와 protocol-invalid abort를 분리해서 검사하도록 작성했다. 새 결함 수나 실험 성공 수는 이 문헌 검토로 늘리지 않는다.
