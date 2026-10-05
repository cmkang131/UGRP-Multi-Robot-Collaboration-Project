# #371 v100 판단 층 구현 기록 (2026-10-05)

범위: 가짜 응답·기록 재생·단위 시험만. 실제 LLM 호출, 물리·렌더링 실행, 병합은 하지 않는다.
이 기록은 새 운반 실험이나 확증 결과가 아니다. TensorBoard에 변환할 새 실험 결과가 없다.

## 1. 재기반

- 원래 머리: `11ee964b3db8a5257987b0c477e927e8888b5aac`.
- fetch 후 #363 머리: `14ba8b5e0b8e58fc6bc9d4b97c5efb337a0c76db`.
- `scripts/run_ci_tests.py`의 추가 항목 충돌은 #363 시험 목록과 #371 패턴을 모두 보존했다.
  자동 병합된 workflow 시험의 예상 등록 수는 양쪽 추가를 합쳐 49 → 50으로 고쳤다.
- main과 열린 PR 11개를 조회했다. `RUNNABLE_ID`만으로는 분리된 등록 파일의 번호가 빠져서
  `configs/`의 ID·workflow 버전도 대조했다. 상세 SHA는 `implementation_20261005_scan.json`.
  최대 번호는 #376의 보정 경로 v101(1.0.0), 최대 workflow 버전은 #371의 3.12.0이다.
  이미 예약된 `zone-pair-llm-v100` / `3.12.0`과 충돌하는 다른 등록은 없고 v100 실행 기록도 없으므로 유지한다.
  v97·v99 은퇴 등록 파일은 바이트 그대로 보존한다.
- 시험 명령은 `nice -n 10 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest ...`를
  한 번에 한 묶음 사용한다. 이 실행 환경은 `setpriority: Operation not permitted`를 출력했다.
  우선순위가 10으로 변경됐다고 주장하지 않는다.
- 첫 넓은 묶음은 호스트 부하 평균 144에서 685.49초 동안 **170 passed**까지 진행한 뒤
  내가 중단했다(exit 2). 전체 통과로 세지 않는다. 이후 단계별 관련 시험으로 범위를 좁힌다.
- workflow 전체 묶음에서도 환경 제약을 확인했다. `test_parent_exit_cleans_background_child`의
  `ps` 실행이 `PermissionError`로 거절됐다. 이 묶음은 **1 failed, 39 passed, 280 subtests passed**에서
  중단했다. 제품 코드나 시험을 우회하도록 바꾸지 않았으며, 프로세스 정리 확인은 이 환경에서 미검증이다.

## 참고 자료 (이번 구현에서 확인한 범위)

- 고전: Sha, *Using simplicity to control complexity*, IEEE Software 18(4), 2001,
  [저자 소속 기관 서지](https://experts.illinois.edu/en/publications/using-simplicity-to-control-complexity/).
  서지 확인, 본문 **U(미확인)**. 단순 제어기가 복잡한 판단 층의 허용 범위를 지키는 구조를 참고한다.
- 고전 구조: [CMU SEI의 Simplex 설명](https://insights.sei.cmu.edu/history-of-innovation/setting-a-foundation-for-software-architecture/).
  설명 확인. 판단 층과 제어기의 책임 분리만 참고하며, 우리 제어기가 형식 검증됐다는 뜻은 아니다.
- 최신: Shi 외, *Hi Robot*, 2025,
  [논문 HTML](https://arxiv.org/html/2502.19417v1). 초록·계층 구조 설명 확인.
  상위 언어 판단과 하위 동작을 분리한다는 구조만 참고한다. 우리 10초 창·상한 수치의 근거로 쓰지 않는다.
- 다중 로봇: Mandi·Jain·Song, *RoCo*,
  [저자 논문 초록](https://arxiv.org/abs/2307.04738). 서지·초록 확인, 본문 **U**.
  대화와 자기 행동 계획의 분리를 참고하되 상대 추정치를 자기 추정기에 합치지 않는다.
- 적용하는 구체적 계약: 설계 노트 v3.1(e1–e9, 12절), #363 코멘트
  [5980026688](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5980026688),
  [5982047194](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5982047194),
  [5982637588](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5982637588),
  [5983174345](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5983174345),
  [5983763178](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5983763178).
  전부 직접 읽음. 뒤 코멘트와 현재 코드가 앞 제안을 대체한 부분은 별도로 명시한다.
- 재기반 최종 관련 검사: workflow 등록·읽기 전용 계획 2개 + `test_ci_fast_path.py` + 은퇴 번들 바이트 시험,
  **13 passed, 280 subtests passed**(10.61초, exit 0). 위 두 중단 묶음과 구분한다.

## 2. 설계 v3.1 값·비용·분류

- 세 조건 사례 상한 900 SIM초, 실제 호출 경로의 최대 허용값도 900초로 맞췄다(호출하지 않음).
- 호출 36/36/72와 등록 `max_calls_total=72`를 대조하며 어긋나면 거절한다.
  발화 6/12는 peer_nl에만 적용하고 no_comm 채널의 실제 상한은 0/0/0이다.
- 판단 창 10초·`look_again` 정지점당 1회/로봇당 사례 1회는 #363 실제 상수와 대조한다.
  `wait`·`give_up`은 짝 응답 검증에서 거절한다. 봉인 검증기는 바꾸지 않았다.
- 호출별 `token_measurement`와 `llm/token_measurements.jsonl`에 입력/출력 텍스트의 로컬 계수,
  고정 이미지 청구량, 제공자 사용량을 분리한다. 응답·사용량이 없으면 null이며 0으로 만들지 않는다.
  이미지 2장의 2,980은 고정 청구량이지 제공자 이미지 토큰 실측이 아니다.
- 아래 분류는 평가 후에만 적용한다. 원래 기하 판정은 `success_provisional`에 보존한다.

| 조건 | 실제 기록 라벨 | 분류·지표 |
|---|---|---|
| 호출 상한 | `budget` / `http_budget` / `episode_call_cap`, 끝 `budget_exhausted` | `LLM_CALL_CAP_REACHED`, LLM 성공에서 제외, 완주하면 `completed_by_rule_default` |
| 코호트 토큰 상한 | `pilot_budget_exhausted`, `infra:API` | 채점 제외; 호출 상한과 혼동하지 않음 |
| 규칙 기본값 비율 > 0.5 | 정지/둘러본 뒤 결정 기록 | `LLM_INERT`, LLM 조건 증거 제외(정확히 0.5는 제외하지 않음) |
| 판단 창 마감 초과 | `DEADLINE_PASSED` | 유효 결정 아님, 규칙 기본값; 호출/토큰 기록은 보존 |

M2의 실제 제공자 수치는 이번에 새로 얻지 않았다. 후속 실제 실행은 설계 9.6절의
rule → no_comm → peer_nl 순서와 실측 기반 예산 확인이 필요하다. 코호트 1.1M은 유지한다.

2단계 시험: `test_pair_llm_decisions.py`, `test_pair_llm_eval.py`, 실제 경로/CLI 상한 거절,
look_around 검증, 번들 기록 검사 **26 passed**(8.58초). 실제 요청은 0회이며 제공자 사용량 시험은 가짜 응답이다.

## 3. 판단 창 범위의 수신 깨움 — 편차(deviation)

조정자 e7 승인 편차다. 짝 층의 `own_job` 콜백은 자기 판단 창이 열린 동안만 None을 돌려준다.
실제 작업 상태·바쁜 작업 재질문 타이머·봉인 스케줄러는 그대로다.
`pair_progress.detail.kind`가 정지/둘러본 뒤 창이면 `idle`로 깨우며,
창 전에 도착해 기다리던 글도 기존 `available()` API로 풀어 준다.
시각은 제어기 절대 시각에서 원점을 빼고, 마감 시각부터 닫힌 것으로 읽는다.
나머지 5개 연결점 사건은 기록만 하며 새 봉인 사건 종류를 만들지 않는다.

시험: `test_pair_llm_windows.py` + `test_pair_llm_decisions.py` **30 passed**(3.53초).
가짜 제어기·실제 스케줄러/전송 계층을 사용했다. 창 안 호출 2·호출 중 수신 대기열·창 밖 억제,
rule/no_comm의 변경 전후 명령 바이트와 no_comm의 실제 중단 명령 시각 동일,
원점 0/1.3/2.6/7.0과 정확한 마감 경계를 확인했다. 물리 궤적이나 실제 모델 증거가 아니다.

## 4. #363 정지 결정 어댑터

- v100 기본 실행기를 #363 `zone_pair_highpose_runtime.Runtime`(규칙) 및 그 위의
  `GatedHighRuntime`(LLM)으로 바꿨다. 종전 v88 gate 클래스는 과거 회귀 시험 경로에 보존한다.
  번들의 하위 기술·물리 설정도 v98을 가리킨다. 실측 보정 검사에는 HIGH의 D5 admission을 사용하며
  v88 보정으로 재표기하지 않는다. 기존 합성·블라인드 경로는 계속 배관 확인 전용이다.
- `pair_llm_stop_adapter.py`는 해당 로봇 실행기의 제어기만 참조한다. 7개 사건을 받되 깨움에는
  사건 이름·창 시간만 넘긴다. 원시 사건·`rule_would_do`·결정 주체는 평가 기록에만 쓴다.
  호출 입력은 닫힌 자기 추정 5필드와 현재 창 4필드만 허용한다(입력 v3, 프롬프트 v4).
- 두 명령의 `kind`/`choice`를 검사한 뒤 기존 봉인 검증기의 나머지 검사를 그대로 사용한다.
  호출 시작 시 창 번호를 고정하므로 늦은 응답이나 이전 정지점 응답이 다음 창에 적용되지 않는다.
  #363의 `OVER_BUDGET`·`LOOK_OVER_BUDGET` 및 one-shot 거절은 그대로다.
- 새 자기 재시도 제어기로 바뀌어도 사례당 `look_again=1` 사용량을 이어 간다.
  자기 명령 이력은 봉인 어휘의 `noop`/`reason_code`에 닫힌 명령·확인 코드만 저장하며,
  실제 실행 상세는 `llm/dispatch.jsonl`에 보존한다. 명령 수락을 작업 성공으로 바꾸지 않는다.
- `stop_hook_events.jsonl`·`stop_decisions.jsonl` 및 result에 평가용 정지 결정을 누적하고,
  LLM_INERT 계산까지 연결한다. 결정 시각은 사례 상대 시각과 `_absolute` 원시 시각을 함께 기록한다.
- #363 v6(양쪽 내려놓기·둘러보기, 추가 둘러보기 사례당 1회)을 따른다. e4의 한쪽 생략과
  v5의 keep-hold 제안을 복원하지 않는다. HIGH rendezvous의 실제 30초를 프롬프트에도 반영했다.
- 중간 검사: 입력·창·상수 **55 passed**(16.29초). 다음 묶음은 **27 passed, 1 failed**(85.89초):
  기능 시험은 통과했고, 기존 런타임 시험 하나가 메서드의 직접 정의 위치를 가정했다.
  공통 mixin과 v88 메서드 상속이 그대로인지 검사하도록 갱신한 뒤 최종 묶음을 다시 실행한다.

남은 한계: 실제 호출·물리·렌더링 0회, 제공자 M2 사용량 미측정. 새 v100 운반 결과·확증 결과 없음.
#363의 실측 HIGH 보정 admission과 최종 판정기 결합은 완료 주장하지 않는다. 현재 평가는 계속
잠정 기하 판정이다. 최신 재고정 전체 경로의 900초 상한·1.1M 토큰 예산 적합성은 실제 실행 전에 확인할 항목이다.
조정자에게 새 구현 선택을 요청할 필요는 없으며, 실행 재개·비교 코호트는 별도 단계다.

- 확장 중간 묶음: **91 passed, 2 failed**(165.17초). 새 CLI 시험의 필수 SHA 인자 누락을 고쳤다.
  다른 하나는 확장된 프롬프트의 SIM 청구 시간 때문에 12초 가짜 사례에서 두 번째 응답이 잘린 경우다
  (호출 시작 8.85초, 12초에 censored, 최초 응답 4.7초). 전달 완료를 검사하는 공유 fixture만
  14초로 늘렸으며 비용 모델·타이머·실제 사례 상한은 바꾸지 않았다. 요청 보존 시험을 포함해 다시 확인한다.
- 코드 검토 중 정지 기록 저장 실패가 자원 정리를 건너뛰지 않도록 finally의 기록 오류를 처리했고,
  가짜 기록 쓰기 오류에서도 자기 backend/runtime을 닫는 회귀 시험을 추가했다.

- 최종 제품 코드의 확장 묶음: **115 passed, 3 failed**(400.94초). 어댑터·스케줄러·입력 경계·실제 훅
  가짜 응답 연결·재시도 한도·시각·보존·평가 시험은 모두 통과했다. 남은 세 시험은 옛 기대값이었다.
  두 곳의 301초 초과 거절을 새 900초 상한에 맞춰 901초로 갱신했다. HIGH 기본 실행기의
  자동 재관측 중에는 모델의 `look_around`가 `BUSY:look_around`로 거절되는 것이 올바르다.
  이전 v88의 수락 기대를 이 동작으로 갱신하고, 같은 자기 작업이 계속되어 정상 종료하며
  거절이 자기 명령 이력에 남는지도 검사한다. 이 뒤 제품 코드는 바꾸지 않고 세 시험만 재실행한다.

최종 재검사 **3 passed**(28.81초, exit 0). 따라서 동일한 최종 제품 코드의 관련 118개는
확장 묶음 115개 통과 + 기대값을 갱신한 3개 통과로 확인했다. 단일 전체 묶음의 118 passed 줄은
만들지 않았고, 앞의 실패 기록은 그대로 보존한다. `git diff --check` 통과.

확장 묶음 파일: `test_pair_llm_stop_adapter.py`, `test_pair_llm_windows.py`, `test_pair_llm_inputs.py`,
`test_pair_llm_decisions.py`, `test_pair_llm_runtime.py`, `test_pair_llm_eval.py`, `test_pair_llm_case.py` 전체;
status의 프롬프트/새 행동 검증/둘러보기 실행 2개/번들/조건 차이/은퇴 바이트 7개와
live의 입력 경로 분리 1개. 재검사 명령(동시 실행 없음):

```sh
nice -n 10 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q --tb=short tests/test_pair_llm_case.py::test_every_arm_has_the_same_case_cap_and_a_larger_one_is_refused tests/test_pair_llm_case.py::test_cli_plans_without_running_and_refuses_missing_calibration_and_unfrozen_source tests/test_pair_llm_status.py::test_high_runtime_refuses_a_model_look_while_its_own_bounded_recovery_is_running
```

최종 소스 대조: #363 `14ba8b5e` 대비 봉인 `zone_event_scheduler.py`, `zone_study_decisions.py`,
`zone_study_protocol.py`, `zone_study_contract.py`와 #363 `zone_pair_highpose_refix.py`의 차이는 없다.
이번 테스트 결과는 로컬 프로젝트에만 기록하고 UGRP 지침에 따라 Drive에 보내지 않는다.

## 4b. 요청 기본 발화 상한과 HIGH 상태 회귀 보완

커밋 `665dcfc0` 후 마무리 검사 4개에서 **1 passed, 3 failed**(47.58초)를 확인했다.
실제 PairTrial은 이미 6/12를 넘겼지만, 직접 `build_request`를 쓸 때는 봉인 채널의 기본 2/6으로
되돌아가는 곳이 남아 있었다. 요청 기본값도 짝 계약의 6/12로 맞췄다.
HIGH의 자동 재관측이 거절보다 최신이면 모델에 최신 자기 작업 종료와 별도 거절 횟수가 보이는 것이
맞으므로 그 동작을 검사한다. 입력 청구 하한 시험은 미완료 호출을 섞지 않도록 가짜 사례를 12→16초로
늘렸다(비용 모델 변경 없음). 원점 0/1.3/4.9의 실제 가짜 루프 상태 순서 시험은 변경 없이 통과했다.

보완 후 입력 파일·판단 창 파일 전체와 위 세 회귀 검사 **42 passed**(47.10초, exit 0).
앞 118개 결과와 중복되는 검사가 있으므로 합계 성공 건수로 더하지 않는다.
실제 모델 호출·물리·렌더링·병합 없음.
