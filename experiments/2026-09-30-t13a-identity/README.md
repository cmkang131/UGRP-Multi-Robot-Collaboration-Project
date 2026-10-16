# T13a — 자기 관측 identity/count와 하위 target job

Refs #221, #222, #223, #224. PR #302의 R6/T13a 후속이다.
**DRAFT / 오프라인 논리 구현 / 물리 준비 안 됨 / 병합 요청 아님.**
시작 main/HEAD는 `c12796676802ab54cad2f0635e3e96e911691c76`이다.

## 구현한 관계

`harness/zone_identity_jobs.py`의 `IdentityJobs`는 한 로봇만 소유하는 별도 opt-in 모듈이다.
기존 study `_order` 정규화를 재사용한다. 입력은 공개 주문행, 자기 영상에서 얻은
`OwnFrame`/`Detection`, 자기 release 명령 기록뿐이다. 정답/scene/world/peer/referee를
받는 인수가 없다. 조건별 설정이나 host target/partner 선택도 없다.

- `order_id`는 주문행, `requested_item_id`는 공개 specific 요청, `detection_id`는
  현재 자기 영상의 임시 식별자, `local_token`은 자기 연속 관측 기억이다. 서로 대체하지 않는다.
- **specific item은 현재 공개 입력으로 식별 불가다.** 주문에는 `cyan_1`이라는 이름·색·초기
  slot만 있다. 이 정보나 영상에 cyan이 하나만 보인다는 이유로 동일성을 주장하지 않는다.
  `resolved_item_id=null`, `unknown/SPECIFIC_IDENTITY_UNGROUNDED`를 반환한다. 서로 다른
  자기 관측 3개에서도 풀리지 않으면 `failed/IDENTITY_RELOOK_LIMIT`로 끝난다. 반복 API
  호출은 관측 횟수를 늘리지 않는다. 기존 slot을 사건 후 현재 위치처럼 갱신하지 않는다.
- fungible cyan은 같은 장면에서 서로 겹치지 않는 bbox와 이전 프레임 후보의 유일한
  일대일 연결로 local token을 이어 간다. `previous`에는 가능한 후보를 전부 넣어야 한다.
  split/merge/가림/프레임 누락은 불확실이다. 색/동일 tracker 이름만으로 재식별하지 않는다.
- 새 token은 그 색의 **지금까지 본 모든 token과 동시에 구별되는 경우만** 만든다.
  이미 배송했거나 소실된 물체의 token도 지우거나 재사용하지 않는다. 따라서 물체가 사라진
  후 새 이름으로 돌아왔을 때 count2의 두 번째 물체로 셀 수 없다. 이 보수성 때문에 시야 밖
  순차 배송·재탐색의 진전이 막힐 수 있다. 실제 appearance re-ID는 구현/검증하지 않았다.
- actor가 선택한 detection만 `TargetJob`으로 하위 `submit_target`에 보낸다. 주문/목적지,
  요청 item, local token, detection, frame sequence/원본 SHA가 함께 전달된다. 이후 매 프레임
  target을 갱신하며 소실·모호성·잘못된 프레임이면 cancel한다. 하위 오류/거절도 성공이 아니다.
  cancel 실패는 backend fault로 잠그고 새 job을 받지 않는다.
- 기존 `ZoneOwnExecutor.deliver(order, zone)`는 target 인수를 받지 않는다. 새 모듈은 이 API로
  fallback하지 않고 `TARGET_API_UNSUPPORTED`를 반환한다. 이번 PR은 기존 executor/P02 dispatch를
  수정하거나 등록된 실행 번들을 바꾸지 않는다. 실제 target-aware backend 연결은 물리 시험의
  선행 조건이다. cyan 외 품종/team 실행은 해당 소유 작업의 몫으로 거절한다.

## 완료 주장과 정보 경계

job 시작 뒤 자기 영상으로 해당 token의 holding을 보고, 그 최신 관측 뒤 **자기 open 발행**을
기록해야 한다. 이후 같은 token이 목적지에서 비파지·정지/바닥 상태라고 자기 영상이 판단한
관측이 1초 이상 간격으로 2개 있어야 `observed_count`를 늘린다. 미파지, release 전에 낙하한
관측, 오배송, 다른 job의 open, 관측 1개, unknown은 완료가 아니다. 하위 `job_done`은
`AWAITING_OWN_OBSERVATION`일 뿐이며 카운트를 바꾸지 않는다.

`claim()`은 마지막 자기 관측에 근거한 **자기 믿음**이다. 물리 성공/심판 receipt가 아니다.
이후 자기 영상에서 물체가 소실되거나 다른 구역으로 보이면 credit을 철회한다. 관측 없이
peer의 실제 배송 상태만 바뀌면 claim은 바뀌지 않는다. peer 메시지를 증거로 자동 승격하지
않으며 P05의 수신·원장·통신 규칙은 변경하지 않는다. `job_status()`는 최근 job 종료 이력이고
현재 주문 믿음은 `claim()`으로 읽는다. 새 상태들은 로컬 내부 상태이며 기존 peer enum
채널에 추가하지 않았다.

`OwnFrame.rgb_sha256`와 연결 후보는 인식기 출력의 출처 계약이지 영상 인식 정확도 증명이
아니다. 현재 테스트는 사람이 작성한 합성 detection이다. 잘못된 인식기가 거짓 일대일
연결/holding/landing을 내면 논리만으로 정답을 알아낼 수 없다. 실제 오인식률·거짓 동일성·
거짓 완료 0건 주장은 아직 할 수 없다. 인식 단서를 임의 추가하거나 무표식 물체 외관을
바꾸지 않았다. 저장 영상으로 specific 구분이 안 되면 관측 정보 설계를 별도로 결정해야 한다.

## 선행 PR과 합성 경계

착수 시 다음 PR은 모두 OPEN/DRAFT이며 실제 `mergeCommit=null`이다.
정확한 head SHA와 조회 시 CI 요약은 [dependencies.json](dependencies.json)에 보존한다.
이들의 검사를 여기서 재실행하거나 T13a의 성공 분모로 합산하지 않았다.

| 선행 | 확인한 범위 | T13a와 연결/남은 일 |
|---|---|---|
| #302 P09 | 정식 6종 원본 요구·정적 감사와 task prompts | inventory/feasibility는 robot 입력으로 사용하지 않음 |
| #305 P01 | 지도/scene/provider 정적 resolver, 미지원 조합 거절 | 최종 v3 합성과 reset 검증은 별도; 지도 복제 없음 |
| #307 P02 | 주문→setup item binding, 제한된 cyan1+r1/r2 beam 개발 계약 | 이 binding은 scene/eval 전용. T13a는 그 정답 join을 입력받지 않음 |
| #308 P05 | 4조건 다회 fake 결정·원장/오류 처리 | 상태·통신 채널은 유지. target job의 action/ack 연결은 합성 때 검증 |
| #312 P03 | fake worker·provider 수명주기/지연·모델 pin | 실제 perception/model/보정은 T13a에서 생성·호출하지 않음 |
| #311 P07 | 실행 없는 DRAFT manifest/admission | 새 공통 source/config/role/인식 자료/기억 hash와 미지원 관문을 합성 때 추가 |

기존 s1–s6 두 버전, 지도, 과거 실험, 실행 bundle/사전 등록/seed/성공 기준은 수정하지 않았다.
공용 수정은 `scripts/run_ci_tests.py`의 새 fake 테스트 등록 한 줄이다. GitHub CI는 정상 실행한다.
새 번들 번호를 예약하지 않았고 `[skip ci]`, CI 취소, 병합, Drive 작업은 하지 않는다.

## 검증과 물리 인계

오프라인 결과와 소스/원본 보존 해시는 [verification.json](verification.json)에 기록한다.
구현 SHA `13e7958a2515dbdc0c8aa12359d6f37bad51b296`에서 관련 검사 **235 passed**
(T13a 새 반례 71개 + 입력45 + 공통 계약53 + CI 분할66), 1.75초다. 실행 속도 측정이 아니다.
원본 시나리오·지도·번들/워크플로 관련 58파일은 시작 SHA와 같음을 확인했다.
초기 공용 잠금 점유로 pytest 시작이 거절된 시도는 테스트 실패 분모가 아니라 미시작으로
구분한다. 테스트는 정상 count2, 중복 target, 소실/재등장/교환/가림, ID 혼동, 오배송·미파지·
완료 응답 오용, 오류/경계, 실제 공개 입력 생성기를 통한 4조건×3actor×private 변화 비간섭을
포함한다. 새로운 모델/물리/학습/렌더 실행은 없다.

[조정자 물리 검사](SIM_CHECKS.md)의 2×900=1,800 SIM초는 최소 진단 제안이다.
specific 정상 셀의 실행 가능성은 인식 단서 설계 및 target backend 연결 전에는 미확정이다.
추가 자료·인식 설계/개발 비용은 미산정이다. 이번 pytest는 물리/평가 실험이 아니므로
TensorBoard snapshot/서버를 만들지 않았다. 조정자의 실제 결과는 실패도 새 snapshot에 넣고
원본 hash·데이터 readback·영상·화면 값을 확인해야 한다.

## 참고 자료

- [P09 요구](https://github.com/kcm0127-dotcom/ugrp/blob/bd95530a2d5a8b8467620809749273068a7ed55d/experiments/2026-09-30-scenario-capabilities/REQUIREMENTS.md), [T13a](https://github.com/kcm0127-dotcom/ugrp/blob/bd95530a2d5a8b8467620809749273068a7ed55d/experiments/2026-09-30-scenario-capabilities/TASKS.md)
- [공개 입력 계약](../../harness/zone_study_inputs.py), [기존 executor](../../harness/zone_own_executor.py)
- [P02 PR](https://github.com/kcm0127-dotcom/ugrp/pull/307), [실행 버전](../../docs/execution_versioning.md), [TensorBoard](../../docs/tensorboard.md)
