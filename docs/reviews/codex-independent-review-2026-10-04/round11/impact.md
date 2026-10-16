# R11 — 확인된 구현 문제에서 연구 해석까지의 영향 경계

**지금 재분류할 수 있는 것은 비용·시도·회수의 기록 의미이며, 그 숫자만으로 통신의 성능 효과를 보정할 수는 없다.** 아래 표는 확인된 구현 경로, 조건부 장부 차이, 실제 연구 결과에서 아직 알 수 없는 차이를 분리한다. 실제 raw/held-out outcome을 읽거나 새 모델·물리 실행을 하지 않았다. 버전이 다른 pilot을 합치거나 과거 bias의 크기를 추정하지 않는다.

| 확인된 경로 | 직접 입증한 영향 | 기존 기록에서 우선 붙일 해석/확인 | 아직 입증하지 않은 결과 |
|---|---|---|---|
| #371 a009, v2 이미지 청구의 전송 후 transport 실패 | 해당 Attempt의 이미지 입력 항 누락. 기본값에서는 고정 요청의 raw+0.596s, grid charge+0.5 또는+0.6s가 맞는 대조 | source·billing policy·cost params·실제 send·failure/censor 상태를 같은 call ID로 연결. API/host-invalid 실행과 정상 정책 실패를 구별 | 어느 arm에 실제 몇 회 있었는지, 후속 action/성공률 차이, 유효 코호트의 bias |
| #371 a009, 본문 완료 후 finalization 오류 | case HOST_ERROR와 SQLite finished/failure_class=None 모순이 가능한 실제 경로 | 반환 status와 finalization error를 원장 상태와 함께 보존. finished만으로 실행 유효성 판정하지 않음 | 실제 occurrence, 물리 task verdict가 바뀌었다는 주장, 저장 실패 자료의 복구 가능성 |
| main b23, 선택적 Colab/Jev 회수 | 선언된 phase의 listing 부재가 로컬 계획 집합을 줄여4/5 회수도 complete로 판정; cleanup predicate까지 연결 | 원격 선언/고정 protocol의 기대 집합과 검증된 checkpoint 집합을 구분. 회수 incomplete와 execution complete를 별도 표시 | 현재 pair pilot에 이 collector가 연결됐다는 주장, 실제 원본 삭제, missing outcome의 방향 |
| main b23, 선택적 visual-team renderer | 종료 attempt receipt가 있는데 child marker가 없으면 report attempted0/pending | runner의 attempted/started_runs/exit를 보고서보다 우선. physical verdict 없음은 unknown | 현재 P06 분모 오염, success/completed 성공률이 부풀었다는 주장 |

## 1. 이미지 누락의 정확한 산술 범위

source 고정점은 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`다. [R8 원인·실제 경계 재현](../round8/runtime.md)과 [a009 source 동일성](../round8/runtime-currentness.md)이 근거다. a009의 `pair_llm_inputs.py:247–251,353–356`은 own wrist와 map의 정확히2개 이미지를 만들고, `pair_llm_billing.py:65–80`의 v2는 이미지당1490토큰을 더한다. 정상·schema-invalid 답변의 `PairTrial.finish_call`은 total_billed를 쓰지만 transport `_failure`는 total_text_billed를 쓴다.

그 **동일 요청·동일 실패 outcome·동일 output/utterance·동일 cost params**에서 빠진 입력은2980토큰이다. 기본 `input_token_s=0.0002`, scale1이면 빠진 raw 항은

\[
\delta = 2\times1490\times0.0002 = 0.596\ \mathrm{SIM\ s}.
\]

실제 cost는 attempt별 raw를 소수6자리로 정리한 뒤 call 전체를0.1s grid로 올림한다(`zone_sim_cost.py:253–295`). current pair는 max_retries=0이므로 이 검토의 default call은 하나의 wire attempt를 갖는다. 아래 차이는 완료·검열 상태를 고정해 보는 **그 한 call의 전체 청구액 재계산**이다. horizon에 잘린 elapsed time이나 로봇의 이동 시간 차이가 아니다.

원래 raw를x, q=0.1이라 하면 코드의 작은 float tolerance를 포함한 Q를 써서 정확한 비교는 `Q(x+0.596)−Q(x)`다. 기본값에서 이는 **0.5 또는0.6초**다. 이상적 grid 표현으로는 `q·floor(δ/q) ≤ ΔQ ≤ q·ceil(δ/q)`이며, 이 δ와 q에서는 양 끝이 각각0.5/0.6이다. 현재 token 계수·등록 scale에서는6자리 raw 정리 때문에 이 결과가 달라지지 않는다. 임의 새 quantum/계수에는 실제 round/quantize를 다시 적용해야 한다.

| cost scale만 바꾼 산술 대조 | raw 복원 | 한 call grid 복원 가능값 |
|---:|---:|---:|
| 0 | 0s | 0s |
| 0.5 | 0.298s | 0.2 또는0.3s |
| 1 | 0.596s | 0.5 또는0.6s |
| 2 | 1.192s | 1.1 또는1.2s |
| 4 | 2.384s | 2.3 또는2.4s |

이는 등록된 scale 값으로 계산한 조건부 산술이며 그 sweep를 실행했다는 뜻이 아니다. `billing-impact-arithmetic.py` (Mac 전달본 증거)는 exact a009 cost 함수·class를 수정 없이 적재해 정수 입력 token residue, error/timeout, output/utterance가 다른20,000개 작은 산술 경우를 확인했다. 데이터나 모델 request를 생성한 실험이 아니다. 기본값에서 text3000은 grid+0.6, text3001은+0.5인 대조가 나온다. 이 text 값들은 grid 위상 확인용 숫자이지 실제 prompt의 token 수가 아니다. `billing-impact-arithmetic.json` (Mac 전달본 증거), `impact-source/manifest.json` (Mac 전달본 증거)를 보존했다.

R8 transport fixture의 text100+이미지2장 사례는 grid 차이가0.6s였다. 이 역사적 합성 결과를0.5s로 정정한 것이 아니라, **그 예시의0.6을 모든 요청으로 일반화하지 않도록 범위를 완성**한 것이다. timeout의20s 고정항도 그대로 남고 여기에 input 항을 더해야 한다. wall API latency와 제공자의 실제 청구 토큰은 이 SIM 식과 다른 기록이며 여기서 바꾸지 않는다.

## 2. 조건별 노출 가능성과 고정 집합의 장부 차이

`no_comm`과 `peer_nl`은 모두 같은 PairInputs/transport/billing 경로를 쓴다. rule은 이 모델 요청을 만들지 않는다. 따라서 이미지 항 누락은 explicit-message arm만의 경로가 아니다. 다른 조건의 prompt·대화 기회·event lane이 call 수나 응답 형태를 바꿀 수 있어 실제 exposed count가 같다는 보장도 없다. 이 리뷰는 각 arm의 오류 빈도를 읽거나 추정하지 않았다.

다음 구별이 필요하다.

| 사건 | 이미지 누락 노출 여부 | 연구 해석 |
|---|---|---|
| 전송0인 request 준비 실패 | 없음; 원본 경로는 refund | 요청 초안 수를 노출 count로 쓰지 않음 |
| 정상 API/정상 pair reply | 정상 full bill | 이 결함의 적용 대상 아님 |
| 정상 completion이나 wrong request ID/unknown action 같은 schema-invalid | 정상 full bill | 정책/프로토콜 실패와 transport 실패를 합치지 않음. [health 대조](../round10/runtime.md) 참조 |
| 전송 후 timeout/HTTP error/비정상 completion/일부 저장 경계 예외가 `_failure`로 진입 | 이미지 항 누락 경로 | 원장의 POST, Attempt, failure와 연결해 노출을 판정. occurrence는 실제 기록 확인 전 unknown |
| 역사적 v1의 이미지0 정책 | 그 버전대로0 | v2 failure-only 누락과 같은 결함으로 소급 분류하지 않음 |

고정된 동일 call 집합에서 exposed call 수가e이면 default raw 복원 합은 정확히0.596e, 각 call을 따로 quantize한 charge 복원 합은0.5e–0.6e다. 이것은 **그 집합에 저장된 요청을 다시 비용 계산한 값**이다. call 집합이나 censor 상태가 바뀌면 같은 bound를 그대로 총 run time에 대입할 수 없다.

두 arm의 고정 집합에서 exposed 수가e_P와e_N이면, charge 총합 contrast `peer−no_comm`에 더해지는 양은 다음 범위다.

\[
0.5e_P-0.6e_N\ \le\ \Delta C_P-\Delta C_N\ \le\ 0.6e_P-0.5e_N.
\]

arm별 **고정 run 집합의 평균 call-cost 합**을 비교한다면 해당 arm의 분모로 나눠야 한다. 평균 trial, call당 평균, wall completion time을 같은 estimand로 바꾸지 않는다. e_P=e_N이라도 raw 차이는0인 반면 grid 위상 때문에 charge contrast는 반드시0이 되지는 않는다. 이는 가능한 장부 차이의 범위이며 통신 효과의 confidence interval이나 measured bias가 아니다.

## 3. 나중에0.6초씩 더해도 action trajectory가 복구되지 않는 이유

actual scheduler는 `finish = started_sim_s + cost.sim_s`에 call_done을 배치한다(`zone_event_scheduler.py:954–968`). 실패 reply는 비용을 내고 action/message를 실행하지 않는다. current pair의 max_retries=0도 유지된다. **따라서 이 문제를 실패 모델 응답이 잘못 실행되거나 유료 retry가 생기는 문제로 설명하면 틀린다.**

call_done은 thinking reservation을 해제하고 `_resume_deferred(call)`을 부른다(:1416–1487). 대기한 event가 있고 다른 제한도 통과하면 후속 call_start가 달라질 수 있다. PairTrial snapshot은 call start의 own frame·command history·inbox를 잡으므로 그 시각이 바뀌면 요청 내용도 달라질 수 있다. 이 실제 연결이 총 비용 보정과 정책 trajectory 보정을 구분해야 하는 이유다. 반대로 대기한 call도 이후 관련 event도 없다면 비용 차이가 실제 action 차이로 이어졌다고 주장할 근거가 없다.

현재 PairTrial의 scheduler 생성(:301–306)은 on_action과 bus를 연결하지만 **on_hold callback을 executor에 연결하지 않는다.** scheduler의 hold/thinking 장부만으로 “물리 로봇이0.6초 덜 정지했다”고 말할 수 없다. 기존 executor job의 동작과 다음 모델 결정의 admission은 다른 경로다. 이 리뷰는 실제 로봇 hold 행동을 측정하지 않았다.

또한 live health가 즉시 중단시키면 후속 의사결정 영향이 제한된다. `pair_llm_live.check_health`는 rate/quota를 중단시키고 공유 health는 fatal/budget/정상 응답0 등을 검사한다. 앞서 정상 응답이 있었던 모든 일반 API error가 즉시 같은 중단을 일으키는 것은 아니지만, 최종 `trial_failure_class`는 API error가 있는 실행을 infra:API로 분류한다(`zone_study_llm_driver.py:514–554`). 그래서 이 결함을 **현재 유효 연구 코호트의 통신 효과가 실제 편향됐다는 증거**로 쓸 수 없다.

### horizon과 겹친 call은 별도로 읽는다

여기 actual a009 live caller는 `LIVE_MAX_CAP_S = SMOKE_MAX_S = 60s`를 강제하고, 일반 pair case의 등록 상한은300s다(`pair_llm_live.py:49,231–232`, `pair_llm_contract.py:40–42`). 이 bundle은 DRAFT_UNSEALED/research_result=False로 기록된다. 아래 horizon은 해당 호출이 받은 cap이며, 별도 본실험의 horizon이나 결과 자격을 이 경로에 대입하지 않는다.

`OfflineTrial.cost_summary():616–655`는 completed call의 전체 charge와 censored call의 horizon까지 elapsed를 분리한다. scheduler의 `_censor_outstanding`에는 `charged_sim_s`/`would_release_sim_s`가 따로 있고, censored contract의 `sim_cost_s`는 elapsed다. 이 구분은 실제 source 의미이며 누락 청구와 별도의 정상 설계다.

* 이미 censored인 동일 call의 full charge는 재계산할 수 있어도, **고정 horizon−start인 elapsed에** 복원 delta를 그대로 더하면 안 된다.
* 원래 finish가horizon 안이었으나 복원 후 밖이라면 completed/censored 집합 자체가 바뀐다. 기존 `call_sim_s`에 상수를 더하는 계산은 그 membership 변화를 재현하지 못한다.
* actor/lane이 겹치므로 call charge 합은 run makespan이 아니다. 다른 call·message·guard event와의 순서가 바뀌는지 별도 증거가 필요하다.

관측된 완료 시각·action을 유지한 채 비용만 다시 계산한 결과는 **fixed-trace accounting**이라고 표시할 수 있다. 이를 “수정된 controller를 실행했을 때의 성능”으로 표시할 수는 없다. 기존 `zone_sim_cost.sensitivity/recost`도 고정 attempt log의 재가격 계산을 approximate로 표시하고, 다른 시각에 관측·행동할 수 있어 새 setting의 실행 결과로 보고하지 말라고 명시한다(:566–599). 이후 요청과 action이 같다는 추가 가정 또는 그 결정 시점에 필요한 증거가 없으면 반사실 trajectory와 task outcome 효과는 미식별이다. 이 문서는 이를 알아내기 위한 새 유료/물리 실행을 요청하지 않는다.

## 4. 회수 누락과 종료 분류는 비용 문제와 다른 층이다

### Colab/Jev missing phase: 기대 집합의 분모가 사라진다

[실제 producer→collector→controller 감사](../round10/collection.md)는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 선택적 경로다. 원격이5개 phase 각1건의 완료/계획을 명시한 fixture에서 한 listing의 FileNotFound가 protocol download까지 건너뛰게 만들어, 로컬4/4로 complete가 된다. 즉 archive4개의 hash가 맞아도 **기대5개 중1개가 회수되지 않았다는 사실**은 사라지지 않는다. empty-list 대조에서는 cohort_complete=False여도 collection_complete=True로 cleanup predicate가 열린다.

직접 확인한 것은 incomplete set을 complete로 표시하고 deadline 전 cleanup 허용 조건을 충족한다는 것까지다. actual endpoint stop, 실제 삭제, 특정 missing outcome은 확인하지 않았다. current pair live/P06이 이 collector를 쓴다고 연결하지도 않는다.

기존 기록에 붙일 유용한 구분은 `remote execution ended`, `remote declared completed/planned`, `expected checkpoint identities`, `verified retrieved identities`, `missing phase/IDs`, `collection status`다. 이는 새 연구 조건이 아니라 원래 선언한 자료 집합을 식별하는 항목이다. 누락자료를0점으로 채우거나 로컬 계획4개를 원래 계획으로 바꾸지 않는다. cohort complete를 보류하더라도 개별 회수 archive4개의 검증 사실은 유지한다.

위 fixture의 회수 coverage는 선언된5건에 대해4/5다. 이80%를 task success rate로 부르거나 development/holdout/regression/ablation/continuous를 하나의 성능 분모로 합치면 안 된다. missingness가 성공/실패와 관련되는지는 이 source 반례로 알 수 없다. 원래 **같은 estimand에 속하는 고정N**과 누락 ID를 별도로 안다면 unknown outcome을 포함한 식별 범위를 논할 수 있지만, protocol 자체가 미회수인 현재 반례에서 N이나 arm 구성까지 임의로 채우지 않는다.

### finalization/renderer: 실행 여부와 물리 verdict를 따로 복구한다

[R8 finalization 증인](../round8/runtime.md)은 final artifact write/close 오류를 case에서 HOST_ERROR로 보존하지만 failure_class를 갱신하지 않아 상위 SQLite run이finished가 되는 경우다. CLI는 HOST_ERROR로 exit1을 낼 수 있으므로 실패가 완전히 숨겨진 것은 아니다. finalization 이후의 metadata 모순을 고친다는 이유로 이미 POST한 실행을 다시 보내면 안 된다. source의 model_requests==0 재시도 제한과 provider usage는 보존해야 한다.

이 오류가 물리 loop 이후 발생했다면 **이미 일어난** 동작을 다시 바꾼다고 말할 수 없다. 문제는 artifact 완결성과 유효성 증거의 일치다. 보존된 case/error/attempt receipt로 operational label을 맞출 수 있는 경우와, 필수 artifact 자체가 없어 결과 검증이 불가능한 경우를 구분한다. ledger finished만으로 success/valid를 결정하거나, HOST_ERROR를 임의의 physical task failure로 바꾸지 않는다.

[visual-team renderer 반례](../round10/reporting.md)는 또 다른 main의 선택 경로다. authoritative cohort receipt에는 attempt1/exit1이 있지만 child marker가 없으면 report attempted0/pending으로 보인다. 기존 receipt로 attempt/lifecycle 표시는 바로잡을 근거가 있고 physical success는 unknown으로 남는다. 실제 renderer의 success 표는 successful/completed를 쓰므로, 이 finding이 그 성공률을 부풀렸다고 확대하지 않는다.

## 5. 버전과 유효성 라벨을 붙이는 최소 판별

아래 이름은 검토용 분류이지 현재 코드의 새 enum이나 자동 수정안이 아니다. historical artifact를 덮어쓰거나 raw를 열지 않았으며, 저장된 version/receipt로 가능한 판단 순서만 제시한다.

| record 조건 | 지금 가능한 해석 | 별도 증거가 필요한 주장 |
|---|---|---|
| v1 image policy로 보존된 v97/v99 smoke | 그 버전의 이미지0 청구를 역사적 정책으로 유지 | v2였으면 timing/action/성공이 어땠는지. v2 failure-only defect를 소급 적용하지 않음 |
| v2/sourcea009 + send된 transport failure + cost/Attempt 보존 | 고정 요청의 누락 토큰/raw/grid delta 산술 확인; API/host validity class와 별도로 비용 일치 여부 표시 | 수정 controller의 후속 image/message/action 및 outcome |
| v2 정상/schema-invalid call | 이 이미지 누락 finding의 exposed case가 아님 | healthy API가 의미적으로 옳은 행동이라는 해석 |
| 1883→a009 사이 own_status clock/prompt 변경 | code SHA/prompt template hash/정책 버전을 구분. 해당 이전 finding의 수정 사실 유지 | 이 변경 전후 pilot을 동일 정책 표본으로 pool해 통신의 효과만 추정 |
| returned HOST_ERROR + ledger finished | phase별 오류와 실제 attempt receipt를 우선해 operational contradiction 표시 | 누락 artifact 복구·task verdict·실험 유효성의 자동 확정 |
| remote declared set보다 retrieved set가 작음 | collection incomplete/coverage unknown 부분 명시; 다운로드된 archive hash 검증은 유지 | 누락 outcome의 값/방향, 전체 cohort의 확정 효과 |
| renderer pending이나 runner terminated receipt 존재 | attempt가 있었다는 사실과 종료 class 보존 | 물리 task가 실패/성공했다는 판단 |

우선순위는 **(1) 비교하려는 기록의 source/billing/cost/phase identity를 확인하고, (2) POST와 attempt·회수 집합의 완결성을 분리한 뒤, (3) 고정 기록에서 재계산 가능한 수치만 고치고, (4) 변한 정책 trajectory의 효과는 unknown으로 남기는 것**이다. 실제 occurrence가0인 cohort까지 결함 존재만으로 무효라고 선언하지 않는다. 반대로 version/phase 정보가 없는데 최신 규칙으로 추정해 valid로 복구하지도 않는다.

## 근거와 재현 범위

새 산술 script는 `impact-source/`와 함께 임시 디렉터리에 복사해 `python billing-impact-arithmetic.py`로 실행한다. Python 표준 라이브러리만 쓴다. 원본 cost source SHA256을 확인하며 결과는 복사된 script 옆에 쓴다. billing 상수와 두 이미지/current no-retry는 위 pinned caller에서 확인한 전제다. 실제 API, simulator, 기존 raw 결과, held-out score는 접근하지 않았다.

R8 runtime finding의 actual transport/SQLite fixture, R9 collection/renderer의 actual caller fixture, R10 health/terminal accounting 검토와 연결했으며 서로 다른 경로를 하나의 새 발견으로 합치지 않는다. 새 가치는 **어디까지 숫자로 보정 가능하고 어디부터 새 증거 없이 결과를 바꿀 수 없는지**를 경로별로 정한 것이다.

evaluation 독립 검토자가 cost source Git blob 일치, 산술 재실행의 JSON 동일성, pair on_hold 미연결과 case loop, no-retry/censor 경계, fixed-set contrast 식 및 본문 해석을 확인했다. [독립 QA](validation.md)에 검사 범위가 남아 있다.
