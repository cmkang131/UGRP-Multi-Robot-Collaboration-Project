# 10차 독립 검증과 보존 범위

담당자가 작성한 반례를 다른 검토자가 다시 실행했다. 새 임시 폴더·합성 입력만 사용했고 결과 보존본을 덮어쓰지 않았다. 관련 구현 파일은 SHA256 guard와 pinned Git object 대조로 확인했다.

| 검증 | 결과 | 실제 실행과 대체 경계 |
|---|---|---|
| Colab collection 5조건 | 작성자 JSON과 완전 일치. 완료 선언 5개 대비 회수4개 오판·정상/손상/일부 계획 대조 확인 | 실제 collector/checkpoint writer/verifier/cleanup predicate, 원격 contents만 fake |
| Visual-team report 4조건 | 작성자 JSON과 완전 일치. marker 없는 시도 누락과 기록된 task failure 대조 | 실제 run_cohort/render, execute callback만 fake |
| Uncertainty fault tree 23분기 | evaluation 검토자 재실행이 보존 JSON과 byte-identical, source10개 de03/672 동일 | 실제 gate/admission/carry/look predicate, synthetic reports와 fake image validator; 실패 trajectory replay 아님 |
| Edge support | JSON 완전 일치. support 배치의 sensitivity3배, flat/count 부족 대조 | 원본 detector/fallback/tracker, authored RGB/고정 gain; 실제 yaw error 아님 |
| PF scan receipt | JSON 완전 일치. weak scan의 수치 갱신과 fix clock rollback, 실제 freshness facade 재계산 | 원본 likelihood/quality/scan/resampler, authored particles/expected rows와 time-only prediction |
| Timestamp/reset | 결과 동일. capture/release/reset floor/order/close 경계 | 원본 delay adapter, fake provider; RGB/물리 latency 미실행 |
| Runtime parser 9·health4·stop4조건 | 비결정적 wall latency를 제외한 전체 결과 동일 | 실제 completion/transport/ledger/scheduler/metrics와 원본 PairTrial AST, fake wire/world/action |
| R9 fixture fidelity 정정 | min_columns4→실제6으로 바꾼 사본도 wall-time 외 R9 결과 전체 동일 | positive8/negative3이라 분기·수치 유지. 공개 R9 파일은 그대로 보존 |

연구 원고는 다른 검토자가 metric 실제 caller 및 ACL2020·NeurIPS2023 primary 원문을 대조했다. frame 소비와 scan 적용, association note의 소유 함수, clipped curvature와 실제 covariance의 한계를 정밀화했다. 실제 모델의 자기보고 오류율이나 uncertainty 원인을 입증한 것으로 쓰지 않는다.

## R9 fixture의 작은 정정

R9 temporal 재현의 fake endpoint는 min_columns4였고 실제 frozen 기본값은6이다. 10차 사본에서6으로 맞췄다. positive8·negative3으로 구성한 기존 조건은 동일 분기를 지나 결과가 바뀌지 않는다. 보존된 9차 문서·코드·JSON·hash는 수정하지 않는다. 정정 스크립트와 별도 설명은 Mac `round10/evidence/vision-temporal-fixture-erratum.md`에 있다.

새 source 단위 fixture는 전체 provider/physics 인증이 아니다. AST를 쓰는 경우 원본 함수 몸체는 보존하고 heavy dependency 또는 환경 경계를 private namespace/stub으로 바꾼 부분을 각 원고에 적었다. 실제 결과/원자료 발생 빈도, CI 전체 통과, 성공률 효과를 보고하지 않는다.

## 재현과 출처

GitHub는 Markdown만 포함한다. Mac에는 작은 재현 스크립트·작성자/독립 결과·source manifest와 제한된 public source 사본을 포함한다. 실행 위치·의존성과 덮어쓰기 방지는 Mac `round10/evidence/reproduction-notes.md`를 따른다. full Git checkout이 필요한 스크립트와 standalone 작은 source 사본을 구분했다. 기존 원고13개와 1–9차 본문, 과거 manifest는 바이트 그대로 보존하며 최상위 탐색·checksum·압축본만 갱신한다.
