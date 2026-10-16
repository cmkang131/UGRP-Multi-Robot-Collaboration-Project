# R13 1차 근거와 읽은 범위

2026-10-04 웹 원문 확인. 아래는 논문 성과를 UGRP에서 재현했다는 목록이 아니다. 공식 정의·모델 가정·provenance 설계에 필요한 부분만 읽었다. 원문 긴 인용은 하지 않았으며, 적용 열은 우리의 조건부 추론이다. 핵심 source 계약은 별도 [연구 메모](research.md)와 두 구현 감사에 있다.

## P1

**JCGM 200:2012, International Vocabulary of Metrology, 3rd edition (2008 version with minor corrections).**

URL: https://www.bipm.org/documents/20126/2071204/JCGM_200_2012.pdf

읽음: PDF43–46쪽(인쇄28–31쪽)의 §2.39 calibration, §2.41 metrological traceability와 관련 note, §2.44 verification, §2.45 validation의 영어 정의/설명. 전체108쪽 통독 아님.

근거: calibration의 측정 관계·불확실성과 verification/validation을 구별하며, validation은 intended use에 적절한 요구를 확인하는 개념이다. metrological traceability는 단순 파일 이력과 다르다.

UGRP 적용: hash와 `validated`를 곧바로 물리 정확도나 metrological traceability로 번역하지 않는다. 새로운 계측 인증 요구가 아니며, 현재21개 값의 실제 불확실성을 이 정의에서 산출할 수 없다.

## P2

**NIST Policy on Metrological Traceability**, 공식 정책 페이지, 표시된 마지막 갱신2024-06-17.

URL: https://www.nist.gov/calibrations/traceability

읽음: 정책의 VIM 정의 채택 항목1, responsibility 항목2–4 관련 본문, fitness-for-purpose 항목5, terminology note3. 검색 요약 대신 공식 본문 확인.

근거: traceability 자체로 측정 용도 적합성이 보장되지는 않으며, 필요한 측정에 충분한 uncertainty가 별도 관계된다.

UGRP 적용: 올바른 생성 이력과 적용 일치는 필수 연결 검증이지만 사용 domain에서의 성능 확인을 대신하지 않는다. NIST가 이 프로젝트의 자료를 인증했다는 뜻이 아니다.

## P3

**W3C PROV-DM: The PROV Data Model**, W3C Recommendation, 2013-04-30.

URL: https://www.w3.org/TR/prov-dm/

읽음: §2의 entity/activity/derivation 설명 중 사용·생성 연결의 필요/충분성, §5.2.1 Derivation과 generation/usage/activity 속성, §5.2.2 Revision. 예시의 관계 의미를 읽었고 전체 규격의 제약/추론 체계를 구현하거나 검사하지 않았다.

근거: derivation을 단순 동시 사용·생성보다 강한 관계로 표현하며, 입력·활동·산출물의 구체 연결과 revision을 기술할 수 있다.

UGRP 적용: 평가 생성 시점의 input→evaluation 연결이 필요하다는 설계 대응. W3C가 cryptographic hash, UGRP schema, 보정 gate 구현을 규정했다는 주장은 아니다. PROV 기록 자체가 실제 계산의 정직성을 증명하지도 않는다.

## P4

**NASA-STD-7009B, Standard for Models and Simulations**, 2024-03-05 최종 표준.

URL: https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf

읽음: §4.1.1.1 intended use; §4.2.1.1–3 data/software/units/frames, §4.2.1.9 guidance/obsolescence; §4.2.5–6 validation/domain/metrics/data; §4.3.1–2 proposed/permissible use, input pedigree, revision/calibration-domain 기록; AppendixE.3.2 data pedigree 및E.3.3 end-to-end verification/input echo 관련 부분. PDF88쪽 통독 아님. 검색된2026 handbook 초안은 채택하지 않았다.

근거: 모델의 사용 적합성, validation domain, 입력·자료 이력과 구성/결과 기록을 구별한다. 구성 확인과 empirical validation도 다른 단계다.

UGRP 적용: promotion에는 대상 domain, consumer에는 실제 적용 구성이 필요하다는 해석. NASA 준수 판정·등급 부여·UGRP에 표준 의무 부과를 하지 않는다.

## P5

**Klaus H. Strobl and Gerd Hirzinger (2006), Optimal Hand-Eye Calibration, IROS.**

공식 저자 PDF: https://www.robotic.dlr.de/fileadmin/robotic/stroblk/publications/strobl_2006iros.pdf

공식 서지: https://elib.dlr.de/45619/

읽음: 저자 PDF7쪽 중 abstract, §I의 목적과 frame 정의, §II Problem Description의 encoder/FK/camera pose 입력·AX=ZB/AX=XB·formulation 선택, §III 도입의 error metric/weighting 논의(PDF1–3쪽). 실험표·전체 알고리즘 유도·결과 section 통독 아님. repository landing page는 full text를 제공하지 않아 별도 공식 저자 PDF를 찾았다.

근거: 측정 오차가 놓인 변환과 그 stochastic model에 맞는 formulation/metric을 다룬다. 해당 hand-eye 입력은 calibrated FK와 joint encoder에 기초한다.

UGRP 적용: own issued commands는 그 측정값과 같지 않으므로 논문의 추정 보장을 직접 승계하지 않는다. 이름이 같은 hand-eye calibration이라는 이유로 현재 무태그 제어에 encoder/target을 새로 허용하지 않는다. 논문의 성능 수치·최신성·UGRP 개선량을 주장하지 않는다.

## 구현 source와 증거 구분

직접 읽은 원본은 Git object `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`다. exact callable/hash guard와 독립 실행 결과는 [stale audit](stale-metric.md), [consumer audit](consumer.md)에 있다. 이 연구 담당은 해당 합성 실행을 중복하지 않았다.

- [servo fitter](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/benchmarks/fit_masterpi_servo.py): 전체 함수, 특히 metric의 data/θ 의존과write.
- [recorder](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/benchmarks/record_masterpi_calibration_measurement.py): record/force/write.
- [validator](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/benchmarks/validate_masterpi_digital_twin.py): 전체validate/promote/CLI.
- [training CLI](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/train_masterpi_v2.py): 전체calibration_status/main.
- [core](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_dynamics_v2.py): loader141–176, constructor774–854.
- [environment](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_training_env_v2.py): constructor98–144; schema `sim/calibration_schema.py` 전체required21목록.

합성 수치는 실제 측정·실제 학습 성과가 아니다. 설계안의 추가 대조는 미실행이며, primary 문헌은 확인된 source wiring 결함의 발생 빈도나 과거 연구 영향의 증거가 아니다.
