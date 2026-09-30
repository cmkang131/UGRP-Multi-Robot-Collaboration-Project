# P08 — D1 검토와 관찰·fake 중단 계약

Refs #216, #221, #293. **DRAFT · 미봉인 · 제어기 미연결 · 병합 금지**.

요청 기준 main은 `a8094cc14e098a55483f53a3c49bf6a0b116043d`, 배정된
`codex/stall-contract`의 실제 시작점은 그 후손 `d17ca4345affef8cf027e121cf1f3197b36c23e0`이다.
작업 폴더는 `/Users/changmin/projects/ugrp-wt/e2e-p08-stall` 하나만 사용했다.
#293 검토 head는 `d86cc82eedbe0c6693eaf808c54ce43387723f1d`다.

**판정:** 관찰 기록과 가짜 중단 순서를 검토할 초안은 준비했다. D1의 실시간 연결·실제 정체 검출·물리 정지·복구는 미검증이다.
#293은 DRAFT이며 승인 리뷰가 없고, 참조 API도 명령 구간 전체를 받는 오프라인 `detect()`다.
따라서 이 변경은 승인된 실시간 adapter 구현이 아니다. detector를 복제·import하지 않고
실험 폴더에만 fake-check 계약을 뒀다. 실제 binding은 별도 인터페이스 승인 뒤 작성해야 한다.

- [읽기 전용 검토표](REVIEW.md): 입력/분모/30·60/연결 차단점과 정확한 소스 위치.
- [coordinator handoff](HANDOFF.md): 새 물리 자료, 최종 환경, raw, 중단 흐름과 예산.
- [검증 기록](verification.json): 실행 소스·환경·잠금·테스트·해시·원본 위치.
- [관찰 계약](observation_contract.py), [fake 중단 계약](fake_stop_contract.py),
  [검사](../../tests/test_stall_observation_contract.py), [#293 재현기](review_d1.py).

## 관찰 전용 초안

`ObservationAdapter(robot_id, enabled=False)`는 기본 OFF다. 명시적으로 켜도 자기 로그만 쓴다.
`harness/`, host, runner에서 이 모듈을 import하거나 호출하지 않는다. 제어기/상태/난수 핸들,
파일 경로, GT, 실제 관절, peer 영상, 모델 client를 받는 슬롯이 없다. stop/notify callback도 없다.
모든 `record()` 반환은 `None`이며 기록된 경보가 동작을 실행하지 않는다.

| 입력/기록 | 계약 |
|---|---|
| 자기 발행 명령 | robot/command ID, `[start,end)`와 일정한 forward/left 속도. 명령 발행 시 `register_command()`로 먼저 등록. 동일 ID의 구간 변조 거부. 저속 수치 cutoff 없음 |
| 자기 영상 | robot ID 일치, `wrist_rgb`, frame ID, 유한·증가하는 촬영 시각, RGB uint8 480×640×3. 복사본 해시만 기록하며 원래 배열/쓰기 flag 불변 |
| check | 명시적 `FakeCheck`만 사용. D1 점수/threshold/ROI 계산을 구현하지 않음. 현재/1초 이전/0.1초 이전 선택 frame ID는 fake 생산자가 제공하며 연결·순서를 검증 |
| 자기 로그 | command window·해시, frame ID·촬영 시각·RGB 해시, 검사 예정/결정 사용 가능 시각, baseline 값·나이, noise floor, state, alarm 시각, unknown 사유, 분모 포함 여부 |
| 기준 나이 | `scheduled_s − baseline_end_s`. 기준을 확보한 마지막 시각으로부터의 나이이며 실제 관절/이동량과 무관. baseline이 없으면 null |
| 경보 시각 | `alarm_s=scheduled_s`, 결과가 소비 가능한 시각은 별도 `available_s`. 실제 연산 지연 측정값이 아님 |
| unknown | REFERENCE, 기준/신호/coverage 부족, ROI 무효, 결측, 짧은 명령, 잘못된 시각·provenance를 모두 보존. `NO_STALL_SUSPECT`도 실제 정상 진행 판정이 아님 |
| 사후 관측 적합성 | `interval_status`를 check state와 따로 기록. INSUFFICIENT_COVERAGE라도 이미 발생한 인과적 alarm을 지우지 않고 unknown으로도 표시. 무장 여부와 관측 적합성은 별개 |
| 분모 | 영상 검증 전에 자기 명령을 등록. 검사가 전혀 없는 명령도 `NO_CHECKS`, `unarmed=true`로 남김. check 수·unknown 수·한 번도 무장하지 않은 구간을 별도 보고 |

출처 검사는 타입/metadata 경계다. 이미지의 robot ID를 거짓으로 붙이는 생산자를 인증하지는 않는다.
후속 binding은 자기 카메라/명령 생산자와 원본 프레임 해시를 독립 검토해야 한다. frame의 partial provenance도
검증 실패 상태로만 기록하며 detector에 전달하지 않는다. 이 초안은 주/보조 설정을 고르지 않는다.
기준 시각·noise floor·frame 선택을 실제 D1 출력에 매핑하는 작업도 아직 없다.

## fake 중단 순서

별도 `synthetic_alarm_flow()`에는 detector 출력이 들어가지 않는다. test-owned fake port에
synthetic alarm을 주입하여 **자기 예정 base/arm 명령 취소 → 자기 hold → 기존 `abort` enum →
자기 `job_failed` 사건 → 자기 다음 결정 자격** 순서만 검사한다. 잘못된 task/robot, 역행/비유한 시각,
중복 alarm, 취소/hold/enum/사건 단계 예외를 검사한다. 단계 실패 뒤 다음 결정이 가능했다고 기록하지 않는다.

짝은 자기 polling에서 기존 enum만 읽고 자기 큐를 정리하며 `PARTNER_ABORT`를 자기 사건으로 남긴다.
host가 peer의 사적 상태·RGB·D1 이유/점수/기준을 전달하거나 peer 사건을 대신 만들지 않는다.
네 조건 `no_comm / peer_ko / leader_ko / structured`에서 같은 `zone_pair_status_v5`의
`abort`와 기존 wire 필드를 사용한다. 새 enum/상태 schema/실행 번들/workflow 번호는 없다.
관찰 로그 schema `p08.observation.draft.v1`은 비공개 실험 기록 형식이며 pair wire 버전이 아니다.

실제 `DecisionScheduler`에는 fake `ReplayTransport/ScriptedWire`만 연결하여 자기 `failure`가
다음 결정 자격에 도달해도 최소 호출 간격/예산 관문이 유지되는지 확인한다. fixture에서는 이전 호출 3.0,
자기 사건 4.1, 다음 fake 결정 시작은 5.0이다(예산 소진이면 새 호출 없음). 실제 LLM 호출·응답·복구가 아니다.
취소 성공/hold 적용에 걸리는 실제 시간·제동 거리·짝의 polling 지연은 여기서 측정하지 않는다.

## 변경 범위와 검증 경계

공용 잠금을 획득한 최종 표적 검사 **122/122 통과**: P08 40개, 기존 pair STATUS 16개,
CI 분할 66개. `review_d1.py`의 합성 반례와 `fake_examples.py`의 자기 로그/중단 trace 생성도 통과했다.
첫 실행은 121 passed/1 failed였다. import 검사에서 기존 설정 문자열 `observation_contract`를 잘못
잡았고, 실제 import AST와 실험 경로 참조를 검사하도록 고쳐 재실행했다. 최초 실패도 보존했다.
최종 원본은 `/Users/changmin/projects/ugrp/outputs/p08-stall-contract-20260930-check11/`,
최초 검사 실패는 같은 접두사의 `check7/`이다. 다른 대기 폴더는 잠금 거부/대기 종료이며 검사를 시작하지 않았다.

공용 파일 변경은 `scripts/run_ci_tests.py`의 테스트 목록 **한 줄**뿐이다. 기존 controller/status/runner,
#293 소스·사전 등록·threshold, 다른 P작업 파일, 공용 TensorBoard 설정은 변경하지 않는다.
검사는 기존 Mac 환경, OMP/BLAS 1, 공용 `run_locked` 보호에서 pure NumPy·fake 포트만 실행한다.
`tests/test_zone_pair_executor.py`는 읽기만 했다. 그 파일의 실제 비전/제어기 재생은 이 작업의 범위 밖이다.

새 실험/평가 코호트와 새 영상이 없어 TensorBoard 변환·서버 시작·대시보드 재열기는 하지 않는다.
단위 검사 수를 성공률 카드로 만들지 않는다. 후속 실제 코호트는 실패·미완료·무장 여부와 함께
[TensorBoard 지침](../../docs/tensorboard.md)을 적용해야 한다. raw는 삭제·덮어쓰기·Drive 전송하지 않는다.

로컬 물리·렌더 금지는 GitHub의 정상 CI에 적용하지 않는다. 렌더/시뮬레이션 및
ACT/local-model job을 포함한 일반 CI를 정상 실행하며, CI를 취소하거나
`[skip ci]`로 건너뛰지 않는다(2026-09-30 사용자 지시 반영).
로컬 표적 검사와 전체 CI는 구분하며
전체 CI 통과/병합 준비로 보고하지 않는다. 필수 Co-Authored-By trailer는 유지한다.

## 참고 자료

- [#293 최신 head](https://github.com/kcm0127-dotcom/ugrp/pull/293),
  [D1 detector](https://github.com/kcm0127-dotcom/ugrp/blob/d86cc82eedbe0c6693eaf808c54ce43387723f1d/experiments/2026-09-30-stall-detector-d1/d1_detector.py),
  [사전 등록 초안](https://github.com/kcm0127-dotcom/ugrp/blob/d86cc82eedbe0c6693eaf808c54ce43387723f1d/experiments/2026-09-30-stall-detector-d1/PREREG_DRAFT.md).
- [#291 연구](../2026-09-30-stall-detection-research/README.md),
  [#283 접촉 양성 대조](../2026-09-30-door-relax-envelope/README.md),
  [#285 p2f](https://github.com/kcm0127-dotcom/ugrp/blob/76e0f9ce793f8cbbff2349b2be2bbaa359250a42/experiments/2026-09-30-b-v6h-gain/README.md).
- [READINESS S09 / #298](https://github.com/kcm0127-dotcom/ugrp/blob/b4cd7e28c8167fd8d75e89f29b3fd6d6b907d10b/experiments/2026-09-30-e2e-readiness/READINESS.md),
  [기존 pair 상태](../../harness/zone_pair_status.py), [pair executor](../../harness/zone_pair_executor.py),
  [자기 executor](../../harness/zone_own_executor.py), [통합 실행기](../../scripts/run_zone_study_integration.py).
