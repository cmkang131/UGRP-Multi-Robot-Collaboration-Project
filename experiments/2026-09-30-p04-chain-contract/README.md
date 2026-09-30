# P04 — 한 실행의 전이·실패·교사 경계 계약

상태: DRAFT, 전이 계약 검사. 실제 연쇄·학생 운반 성공·봉인·병합 없음.
기준은 배정 `codex/chain-contract`의 `d17ca4345affef8cf027e121cf1f3197b36c23e0`이다.
사용자 프롬프트의 `a8094cc14e098a55483f53a3c49bf6a0b116043d` 이후 최신 main을 fetch하여 확인했다.
Refs #219, #221, #225. 상위 설계는 [PR #298 READINESS S03–S08/S15](https://github.com/kcm0127-dotcom/ugrp/pull/298).

## 구현 범위

- `harness/pair_execution_contract.py`: 기존 `m2_controller`를 감싸는 선택형 output-only 기록기. 새로운 FSM이나 제어 결정을 만들지 않는다. production controller/threshold/물리/카메라/gate·registry·봉인 파일은 변경하지 않았다.
- `tests/test_zone_pair_chain_contract.py`: fake own-port/provider/clock 위에서 실제 PairExecution, M2 상태 handler, ArmSequence, STATUS, host 취소 경로를 연결한다. make_plan의 전체 8-leg 경로를 그대로 쓴다.
- CI 목록에 해당 테스트 1행을 추가한다. P02 혼합 job/scene, P03 provider 생명주기, P06 `run_loop/write_outputs/referee`, #292/#293 소스는 수정하지 않는다.

기존 `PairAlignRelook._cp_open → M2DoorStudent._cp_open`이 leg를 증가시키고
`PairGraspRelook._queue_grasp`로 p20 관측을 시작한다. 새 fix 뒤 open descent,
close GO, grasp, lift GO, carry GO가 이어진다. 마지막 leg에서는 cp_open 대신
released → done이 된다. 완료는 기존대로 `PAIR_SEQUENCE_DONE / unconfirmed`이며
목적지 배송 판정은 별도다. `ArmSequence`는 발행 PWM의 보간 helper이며 import만으로
교사 GT 접근이라고 판단하지 않는다.

## 기록기 사용과 의미

코디네이터가 최종 소스에 합성할 때 host 생성 시 다음처럼 명시적으로 연결한다.
이는 아직 등록 workflow나 봉인 manifest 변경이 아니다.

```python
trace = PairRunTrace(run_id, scope="student_run")
host.enable_pair_carry(..., controller_factory=trace.factory(m2_controller))
# 성공/예외/예산 종료 모두 기존 host 취소 경로를 마친 뒤:
record = trace.record()
verification = verify_trace(record)
```

`scope`는 `transition_contract`, `stage_probe`, `student_run` 중 반드시 명시한다.
한 trace는 단일 pair 새 출발(r1/r2 각각 job 1개)을 대상으로 한다. 같은 기록기에
여러 pair job을 누적하면 `PAIR_INCOMPLETE`로 거부한다. P02 혼합 작업 전체의
분모/여러 job 추적을 이 단일 pair 결과로 대신하지 않는다.
각 robot/job의 state 시작·종료 receipt는 동일한 run/task/job/robot/leg와
자기 frame ID/SHA/capture 시각, report/fix 시각, pair 시작 이후 명령 수,
소비 프레임 수, STATUS sequence를 연결한다. `commands`는 발행 명령 원문과
단조 ordinal을, `frames`는 반복 소비까지 기록한다. 외부 포트의 실제 이동을
측정한 값이 아니다. provider/PF 객체 교체는 관측한 callback 경계에서 센다.
DelayedPoseSource의 고정 facade, GuardedLocalizerV3와 FailClosedLoc 뒤의 실제 필터
참조까지 비교하되 report/estimate/update를 호출하거나 입력 큐를 비우지 않는다.
이 카운터만으로 GT 접근·동일 객체 내부의 prior reset 부재를 입증하지 않는다.
그 부분은 아래 별도 boundary audit가 필요하다.

`record()`는 분리한 JSON 복사본을 반환한다. GT 입력 API가 없고 평가 결과를
컨트롤러로 돌려주지 않는다. `summarize_attempts`도 실행 종료 뒤에만 호출한다.
시작별 목록에는 입장 거부·접근 미도달·HOST_ERROR도 넣는다. 누락 trace는 오류이며
분모에서 제외하지 않는다. 접근/파지 미도달과 목적지 실패/미검증,
기록 불충분(evidence_incomplete)을 구분한다. scope별 분모도 함께 남긴다.
stage PASS와 합성 전이 통과는 전체 PASS가 될 수 없다. student_run도 연쇄 receipt,
동일 run/job의 목적지 release 심판 PASS와 완료된 boundary audit 없이는 전체 PASS가 아니다.

## 합성 시험의 한계

성공 경로는 관측/clearance를 주입하여 전이를 강제한다. 접근 driver의 도착 관측,
정렬 beam fit, grip/co-motion 판정, 정적 sweep/standoff/preclose certificate가 fixture다.
실제 영상의 파지 정확도·위치 추정·clearance 성능 시험이 아니다. 상태 handler,
팔 queue/timing, frame gate, fix freshness 검사, barrier GO/TTL, 중단/취소는 기존 코드를 쓴다.
provider는 지연 0.16초인 fake fix와 append-only 명령 이력을 사용한다.
실제 VisionPoseSource/DelayedPoseSource 내부 PF 수치·worker 결과는 P03의 별도 증거다.

world는 time/timestep만 허용하는 sentinel이다. simulator/학습 모델 import,
네트워크 연결과 worker subprocess 시작도 시험 범위에서 차단한다. qpos/body/robot/physics 등의 접근과
학생 실행 후 PF 교체·prior reset은 즉시 예외다. sentinel 양성 대조도 포함한다.
물리/시뮬레이터 step·렌더·비전/LLM 모델 호출은 없다. 테스트 clock의 초를 실제 SIM
처리량이나 운반 시간으로 보고하지 않는다. 원본 JPEG fixture는 기존 파일을 읽기만 한다.
사용한 고정 영상은 `tests/fixtures/m2_pair_door_v3/lift_824_r2_00759.jpg`다.
양쪽 fake stream에 같은 bytes를 쓰고 robot/frame ID·시각만 별도로 발행한다.
자기 영상 분리·다양성의 실증이 아니며, 지도는 `maps/zones/zone_wide_door_tags_v2.json`,
보정은 `experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json`을 재사용한다.

## 검증 중 발견한 fixture 오류

초기 개발 검사는 11개 통과(205.46초)였으나, 이후 identity·누락·실패 이유 검사를
확장했으므로 최종 검증 수로 합산하지 않는다. 초기 검사에는 별도 JUnit이 없다.
`validation-01`은 전체 8-leg 전이 1개 통과 뒤 invalid-frame 시험에서 중단했다
(1 passed / 1 failed). 취소 대상인 미래 host macro를 fault보다 먼저 넣어
host의 정상 `not slot.timeline` 제어 호출 조건이 막혔고, invalid-frame 대신
`PARTNER_SILENT / PARTNER_ABORT`로 실패했다. 이 결과를 해당 fault의 검증으로 세지 않는다.
fixture의 미래 macro/arm/drive 명령 주입을 최초 abort 직전으로 옮겼다.
각 fault의 원래 이유, 양쪽 취소 수 > 0, 예약 queue 비움, 자기 최종 사건 1개를 함께 검사한다.
원본 JUnit과 성공 경로 trace는 `outputs/p04-chain-contract-20260930/validation-01/`에 보존했다.
controller·heartbeat/frame 기준은 변경하지 않았다.
`validation-02`의 실패 경로만 선별한 재검사는 8 passed / 27 deselected(3.78초)이다.
중간 `-k`를 runner 인자로 준 한 번의 호출은 인자 파싱에서 거부되어 검사가 시작되지 않았다.
실제 선별은 `PYTEST_ADDOPTS`로 전달했다. 잠금 경합 시에도 보호 실행기가 pytest 시작 전에 거부했다.
`validation-03`은 관련 9개 모듈 274 passed(337.90초)다. 이후 정적 검토에서
non-string scope의 `Counter` 키와 실패 trace의 non-string phase 집합이 summary에서
예외를 낼 수 있는 경로를 발견했다. scope를 `invalid`로 분류하고 phase 형식을
검증하여 둘 다 기록 불충분으로 전체 분모에 남기도록 보완했다. 이 3개 회귀를 추가한
최종 소스는 별도 `validation-04`로 검증하며 이전 결과를 덮어쓰지 않는다.

**최종 결과: 9개 모듈 277 passed / 0 failed / 0 skipped(317.60초), 그중 새 계약 검사 38개.**
검사 전후 소스·fixture 19개 파일의 SHA-256이 일치한다.
[VERIFICATION.json](VERIFICATION.json)에 모듈별 수, 실패 이력, 환경, 소스·raw의 전체 해시를 기록했다.
raw는 `/Users/changmin/projects/ugrp/outputs/p04-chain-contract-20260930/`의 로컬 보관이며
원격 백업이 아니다. 실제 물리/시뮬레이션 step·렌더·모델 호출은 0회다.
이 통과는 합성 전이·오프라인 계약 검증이며 실제 운반 성공을 뜻하지 않는다.

재현 시 새 출력 경로를 사용한다. 검증은 공용 잠금을 획득하는 기존 보호 실행기를 쓴다.
`validation-04`의 대기 wrapper도 같은 `run_ci_tests.run_locked`를 호출하며,
선별한 9개 파일의 중복/누락과 환경 정리를 기존 runner와 동일하게 적용했다.

```sh
P04_TRACE_DIR=/Users/changmin/projects/ugrp/outputs/p04-chain-contract-NEW \
PYTEST_ADDOPTS=-x /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python - <<'PY'
import os
from scripts import run_ci_tests as r
r.TEST_PATTERNS = (
    'tests/test_zone_pair_chain_contract.py', 'tests/test_pair_chain_probe.py',
    'tests/test_zone_pair_executor.py', 'tests/test_zone_pair_status.py',
    'tests/test_zone_study_integration_pair.py', 'tests/test_zone_pair_grasp.py',
    'tests/test_zone_pair_preclose.py', 'tests/test_zone_pair_review7.py',
    'tests/test_ci_sharding.py',
)
raise SystemExit(r.main(['--junitxml', os.environ['P04_TRACE_DIR'] + '/junit.xml']))
PY
```

새 물리·학습·평가 코호트가 없으므로 TensorBoard snapshot 변환/서버/UI는 실행하지 않았다.
기존 GitHub 자동 workflow에는 실제 모델·물리·렌더 검사가 포함되므로 이 Draft는
`[skip ci]`로 push하고 전체 CI 통과를 주장하지 않는다.

## 코디네이터에게 넘기는 3개 새 출발 명세 — 실행 승인 아님

전체 접근부터 목적지 release까지 **새 출발 3개 × 최대 900 scene-SIM초 = 2,700초(0.75 SIM-h)**를
제안한다. 900초는 READINESS C4의 전체 M2 cap 제안이며, C2의 3×300초 문 연쇄와 다른 분모다.
기존 phase/job deadline은 그대로 유지한다(현재 pair job 기본 720초).
그 한도가 먼저 오면 즉시 실패하며 900초 제안이 기존 한도의 연장 승인은 아니다.
첫 teacher lift를 쓰는 `pair_chain_probe`는 stage probe로 계속 분리한다.
3회 성공이 독립 test gate나 본연구 검증 완료를 뜻하지 않는다.

1. 실행 전: 최종 지도/robot 모델/카메라/렌더/접촉/가중치·보정/정책/기억/초음파 OFF,
   초기 배치·own dock prior의 출처·불확실도, seed 3개, job·route·cap·성공 조건을
   source/bundle hash로 고정한다. P01/P02/P03/P06 및 #292/#293 미해결 사항을 확인한다.
   별도 권한과 검토 전에는 봉인·실행하지 않는다. 공용 잠금, 단일 소유 세션,
   10 GiB 여유와 부하를 확인한다. cap은 reset/settle부터 끝나며 로봇 수를 곱하지 않는다.
2. 허용 입력: 자기 wrist RGB, 고정 지도/작업 지시/카메라 보정, 자기 발행 명령,
   선언한 통신 채널과 네 조건 공통 enum STATUS. TOP·GT pose/qpos/contact/성공 판정은
   평가 전용. 중간 교사 재배치·state restore·GT prior/정답 재초기화·다른 robot PF 주입 0회.
   내려놓기 후 기존 provider/PF/명령 이력을 이어받아 실제 p20 새 fix를 기다린다.
3. 최소 raw: manifest(소스·설정·환경·해시·시작/종료·cap·실패), 모든 자기 JPEG와
   frame ID/SHA/capture/release/drop 이유, 소비 trace, 명령 원문/시각/ordinal,
   provider/fix/posterior 요약·scan 요청·지연 큐·PF 연속성 audit,
   state/leg start-end receipts, ACK/API/개별 robot 사건, STATUS 발행/수신/거절·GO,
   취소된 host timeline/arm queue·양쪽 hold와 최종 job 실패/미확인 사건을 저장한다.
   전후 프레임 비교에 필요한 모든 입력을 보존하며 스크린샷 일부로 대체하지 않는다.
4. 평가 raw는 별도 `eval_only/`: TOP 동영상/프레임, GT 로봇·봉 pose,
   접촉/관절/목적지 release와 심판 기준·판정, checkpoint 전후 봉 이동과 pose 오차,
   boundary access audit. evaluator receipt는 제어 입력이나 성공/실패 알림으로 보내지 않는다.
   원문/프레임/trace를 manifest 해시로 연결하고 실패도 동일하게 보관한다.
5. 실패: invalid/black/stale frame, heartbeat 소실, 상대 abort, preclose 거절,
   own provider failure는 기존 제어 중단 기준을 유지한다. 예약 명령 취소·자기 사건·양쪽
   정지를 검증한다. 900초 도달은 `SIM_LIMIT` 실패이며 단계 성공으로 덮지 않는다.
   접근 미도달/파지 미도달/운반 중단/목적지 release 불성립을 분리하고 전체 분모는 3이다.
   예외/ENOSPC는 `HOST_ERROR`; 남은 자료와 누락 항목을 기록한다. 자동 재실행·cap 연장은 없다.
6. 결과 회수: 공용 `outputs/` 절대 경로에 raw를 보존하고 count/bytes/SHA를 검증한다.
   새 TensorBoard snapshot에 실패·미도달을 포함해 전체 분모, phase/leg 도달률,
   runtime·명령 수·모델 호출/응답시간(있는 값만)을 표시한다. 실제 데이터 로딩과
   공용 logdir·영상 등록·pin/HParams를 raw와 대조한다. Drive·raw 삭제·재압축 없음.

## 참고 자료

- PR [#260](https://github.com/kcm0127-dotcom/ugrp/pull/260), [#265](https://github.com/kcm0127-dotcom/ugrp/pull/265), [#278](https://github.com/kcm0127-dotcom/ugrp/pull/278), [#283](https://github.com/kcm0127-dotcom/ugrp/pull/283): teacher staging·정렬·운반·연쇄의 서로 다른 검증 범위.
- [문 완화 연쇄 기록](../2026-09-30-door-relax-envelope/README.md): checkpoint 뒤 진행 감시/편향, stage PASS 승계 금지의 근거. 이 작업에서 완화 코드는 실행하지 않는다.
- `harness/zone_pair_executor.py`, `zone_pair_status.py`, `zone_pair_grasp.py`, `zone_pair_align.py`, `m2_provider_adapter.py`, `pair_chain_probe.py`.
- `scripts/run_m2_pair.py`, `study_owncam_pair_beam.py`, `run_zone_study_integration.py::run_loop/write_outputs`.
