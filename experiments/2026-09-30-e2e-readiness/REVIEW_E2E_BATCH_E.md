# E2E Batch E 독립 반대 검토

작성: Codex, 2026-09-30. 물리·MuJoCo step·렌더·실제 모델 호출 없음.
검토 브랜치: `codex/review-e2e-batch-e`, 시작 main: `c12796676802ab54cad2f0635e3e96e911691c76`.

## 판정과 범위

| PR | 고정하여 검토한 HEAD | 판정 | 핵심 이유 |
|---|---|---|---|
| #316 P04 전이·실패 기록 | `8d755a5a69dd03fd9eb202407665b2b0890ed54d` | **MERGE AFTER FIXES** | 실제 기존 상태 전이와 취소 경로를 검사하지만, 종료 기록의 모순과 누락된 프레임 연결을 verifier가 거부하지 않는다. |
| #306 측면 오차 분석 | `aae9343ae59eb3ee834c42bc4c23e4fd3d465e38` | **MERGE — 탐색적 오프라인 분석으로 한정** | 조건부 예측·관측률·확증 분모를 구분하고 코호트/시드 의존성을 다룬다. 실행 승인이나 E2E 성공 판정은 아니다. |

BLOCKER는 발견하지 않았다. #316의 MAJOR 2건은 수정·반례 재검사 후 다시 검토해야 한다.
`MERGE`는 내용 검토 판정이며 실제 병합을 수행하거나 CI/소유자 절차를 대신한다는 뜻이 아니다.

요청에는 “세 PR”이라는 표현이 있지만 검토 대상으로 번호가 명시된 것은 #316/#306 두 개다.
이 두 개와 비교 대상으로 지정된 #292/#299/#301을 조사했다. 세 번째 검토 대상을 임의로 추가하지 않았다.
P04 원문은 [`task_prompts/P04_chain_contract.md`](task_prompts/P04_chain_contract.md)이다.
해당 main의 `task_prompts/`에는 P01–P09만 있고 #306 전용 과제 원문은 없다.
#306은 이번 요청에 명시된 통계·경계·probe 기준과 PR 본문의 주장으로 평가했으며, 존재하지 않는 원문의 완료를 인증하지 않는다.

## #316 — MAJOR E316-1: 모순된 마지막 종료 기록도 전체 PASS에 사용된다

근거: `harness/pair_execution_contract.py:209`, `:233`, `:261`, `:290`, `:337`, `:343`.
아래 모든 줄 번호는 위 표의 해당 PR HEAD 기준이다.

시작/종료 receipt 쌍은 edge·phase·leg·시간 순서를 검사하지만 종료 `outcome`은 검사하지 않는다.
terminal은 outcome의 두 enum과 비어 있지 않은 reason, 마지막 receipt보다 빠른지만 검사한다.
terminal의 phase·leg가 마지막 종료와 같은지, 성공 경로 reason이 `PAIR_SEQUENCE_DONE`인지,
terminal 시각이 유한한지는 확인하지 않는다. summary는 terminal outcome이 `unconfirmed`이면
연쇄 완료로 취급하여 별도 목적지 PASS와 합쳐 전체 PASS를 낼 수 있다.

재현은 원본 해시를 확인한 `validation-04/full_trace.json`의 복사본을 사용했다.
작성자 자신의 양성 schema 시험(`tests/test_zone_pair_chain_contract.py:465`)처럼
scope를 `student_run`으로 설정하고 run/job이 맞는 합성 evaluator와 boundary audit를 제공했다.
이는 검증기 양성 대조일 뿐, 합성 자료를 학생 성공으로 보고한 것이 아니다.

- 마지막 `done/end` receipt의 `outcome` 하나만 `failed`로 바꾼다.
- 별도 변형으로 terminal `phase="approach"`, `leg_index=999`, 또는 실패 reason
  `PREGRASP_NOT_READY`를 넣고 outcome은 `unconfirmed`로 둔다.
- terminal 시각에 NaN을 넣은 변형도 검사했다.

기대 동작은 손상/모순을 `evidence_incomplete`로 남기고 분모 1, 전체 PASS 0으로 유지하는 것이다.
실제 재현 결과는 아래 검증 절에 기록했다. 원본 실패/완료 기록의 조합이 잘못된 경우를
그대로 배송 PASS에 쓰는 문제이며, 제어기에서 새 물리 행동을 발생시키는 문제는 아니다.

수정 조건: terminal을 모든 다른 row와 동일한 타입·유한 시간·leg 범위 검사에 포함하고,
마지막 종료 receipt·terminal phase/leg/outcome/reason 사이의 일관성을 정의한다.
특히 마지막 종료가 실패인 기록은 `unconfirmed` 완료로 받아들이지 않는다.
각 변형에서 verifier 실패와 summary 분모 보존·PASS 0을 함께 검사한다.

## #316 — MAJOR E316-2: 재파지 receipt의 프레임 연결이 없어도 검증을 통과한다

근거: `harness/pair_execution_contract.py:125`, `:216`, `:270`, `:280`, `:296`.

기록기는 receipt에 `frame_id/frame_sha256/captured_at_s`를 넣지만 verifier는
별도 `frames` 배열의 개별 형식만 검사한다. receipt의 세 필드 존재·형식이나
기록된 입력과의 연결은 확인하지 않는다. fresh fix 판정도 `last_fix_t`와 명령 수만 본다.

같은 양성 schema 기록에서 r1의 leg 1 `grasp/start` receipt의 세 프레임 필드를 삭제하거나,
존재하지 않는 frame ID와 다른 SHA로 바꾼다. 기존 frame 배열은 그대로 둔다.
이런 누락/불일치가 있어도 현재 verifier는 거부하지 않는다. 따라서 “이 재파지에서
어떤 자기 프레임/새 fix를 사용했는가”라는 P04의 핵심 연결을 유효하다고 인증할 수 있다.

수정 조건: phase별 필수 프레임 필드와 참조 대상(전체 capture 또는 소비 frame)을 명시하고,
새 fix가 필요한 checkpoint에서는 해당 입력의 ID/SHA/capture/fix 시각 연결을 검증한다.
초기 프레임 전의 합법적인 null과 필드 누락은 구분한다. 누락 필드와 존재하지 않는 참조에 대한
반례를 추가하고, verifier 실패·전체 분모 보존·PASS 0을 검사한다.

## P04 완료 기준과 경계

| 과제 원문 기준 | 확인한 범위 | 판정 |
|---|---|---|
| 1. 접근→목적지와 단계별 receipt | 실제 M2 handler·ArmSequence·PairExecution·STATUS를 fake host에서 연결하고 8개 leg를 검사한다. 영상/clearance/도착은 fixture라고 명시한다. | 전이 계약 범위 충족 |
| 2. identity·PF·명령 이력·교사 경계 | run/task/job, provider/PF 교체, 명령 ordinal, privileged world/prior reset sentinel과 양성 대조가 있다. | 구현은 유의미하나 E316-2 때문에 기록 검증 완료는 아님 |
| 3. 8종 실패에서 취소·양쪽 정지 | invalid/black/stale, heartbeat, partner abort, preclose, provider, budget을 실제 host 취소 경로로 검사한다. | fake 통합 범위 충족 |
| 4. 분모·stage PASS 승격 금지 | 없는 trace와 손상 scope도 분모에 남고 stage/fake scope는 PASS를 얻지 못한다. | E316-1/2의 불완전한 student-run 증거 수용 때문에 미완료 |
| 5. 새 출발 3회 raw·경계·cap | README:127 이하에 3×900 scene-SIM초 제안, 기존 720초 job cap 우선, ENOSPC/HOST_ERROR·raw 목록이 있다. | 문서 범위 충족; 실행은 미수행 |

관련 시험 근거는 `tests/test_zone_pair_chain_contract.py:159`(금지 import/network/worker),
`:197`(fixture guard), `:262`(전체 전이), `:298`(실패), `:376`(sentinel 양성 대조),
`:401`(변형 검사), `:453`(별도 evaluator/audit), `:523`(GT failure의 control 재유입 없음)이다.
정상 경로의 guard/beam/holding 판정이 주입되므로 실제 파지·clearance·provider 성능을 검증한 것은 아니다.
그 한계는 과제 원문이 허용한 범위이며 그 자체를 결함으로 세지 않았다.

새 runtime 모듈은 출력 전용이다. GT·상대 실시간 좌표·접촉/성공 판정을 controller에 전달하는 경로나
weld ON 변경은 발견하지 못했다. `ArmSequence` import는 명령 helper이며 교사 GT 사용으로 세지 않았다.
실제 러너 연결은 README:23–24가 인계 범위로 남겼다. 한 trace는 pair 1회만 지원(README:35)하므로
P02 혼합 작업의 전체 분모나 여러 job을 이 결과 하나로 대체하면 안 된다.

## #306 — 통계와 추가 probe

1. **1,384끝점은 회귀 독립 표본 수가 아니다.** 모든 수집 끝점은 1,384개, 실패/누락을 포함한
   케이스 표는 1,472개다. 실제 적합은 반복 시드를 묶고 중복 station을 제거한 40조건,
   주 예측은 C/S/X의 30조건이다(`analyze.py:195`, `:222`, `:433`).
2. **LOCO의 외부 코호트가 자신의 적합/구간 보정에 직접 들어가는 경로는 발견하지 못했다.**
   cohort 전체 및 같은 geometry를 제거(`analyze.py:83`), 내부 holdout 재계산(`:110`, `:157`),
   seed 편차도 외부 training에서만 만든다. tX1/tX1b는 같은 X 모집으로 묶는다.
3. **독립성은 한정되어 있다.** geometry 제거는 0.1 mm/0.01° 기준이다. 서로 다른 family에
   C/N07–S/S01이라는 9.899 mm·0.24° 근접 쌍은 남는다. 같은 prior·공통 seed,
   C의 lag OFF/고정 sheet와 S/X의 lag ON/coarse 차이도 있다. 따라서 이 결과는 독립 확증이나
   모집단 coverage 보장이 아니다. README:124–180은 이런 설계/선택/의존성 한계를 설명하며,
   90% 대역을 보장된 신뢰구간으로 부르지 않는다. 추가 거리 묶음 민감도는 후속 보완점이다.
4. **L0/L1 결합을 보존한다.** 두 leg 잔차를 같이 추출하고 두 Euclidean gate를 AND로 검사한다
   (`analyze.py:291`, `:326`). 59.14/60은 bootstrap 기대 통과 수이며 관측 성공 횟수가 아니다.
   모형 밖의 guard/접촉/파지/방출/이후 leg/E2E 실패를 README:189–197에서 명시적으로 제외한다.
5. **추가 시험은 확증 분모와 분리되어 있다.** 신규 6개는 3개 geometry×2 prior 조합이다.
   S07/X01 2개는 이미 본 인수 재검사이며 새 독립 probe로 셀 수 없다. 별도 JSON의 선택적
   prior_10 두 조합까지 포함해도 확증 60배치와 거리 <1 cm AND yaw 차 <0.5° 겹침은 없다.
   README:221–261이 탐색 자료로 남기고 확증 배치를 먼저 실행하지 않도록 한다.
   seed 951 및 예상 시간은 계획이고 실행 결과가 아니다.

GT 끝점·prior 오차는 오프라인 설명/예측의 입력이다(`extract.py:109`, `analyze.py:458`).
controller로 연결되는 import/callback을 추가하지 않으므로 AGENTS 입력 경계 위반은 발견하지 못했다.
제안된 teacher chain은 stage probe이며 E2E가 아니다. weld OFF도 명시되어 있다(README:250–253).

새 코드의 단위 검사는 단순 수치 일치만 확인하지 않는다. 목표 cohort의 y를 바꿔도 자기 예측이
변하지 않는지, geometry 중복 제거, joint event가 marginal 곱과 다른 반례, shared prior 추출,
hash 변경 거부를 검사한다(`tests/test_carry_lateral_error_model.py:50`, `:61`, `:107`, `:142`).
다만 14개 합성 시험만으로 실제 분포·독립성·꼬리 모형을 검증했다고 말할 수 없다.

## 두 PR과 #292/#299/#301의 충돌

비교 SHA: #292 `3c4fe30e2197518443b195392212b0341507ac59`,
#299 `8a1631b9cf6f9d658961fcb80339539e87541d3d`,
#301 `2ff92e9fbeff1b90b0aa35104a9766753e67f94e`.
#299의 PR base는 `claude/b-v6h-gain`이다. 이 비교를 #299 단독 main 병합 승인으로 해석하지 않는다.

| 조합 | 텍스트 합성 검사 | 의미상 남은 연결 |
|---|---|---|
| #316 + #306 | 충돌 없음; 공통 변경은 CI 목록 | 성공/분모 정의가 다르므로 trace 배송 PASS와 끝점 조건부 예측을 합산하지 않는다. |
| #316 + #292 | 충돌 없음 | fake 전이 검사를 최종 등록 정책·provider에 다시 연결해야 한다. 이 검사는 #292 물리 인수를 대신하지 않는다. |
| #306 + #292 | `experiments/README.md` 충돌 | 두 인덱스 행 모두 보존. #306의 6/10 정지는 구 후보 `3afc61b0`의 관측이다. #292의 위 HEAD는 guard scope를 바꿨으므로 새 후보 실패율로 승계하지 않는다. |
| #316/#306 + #299 | 두 조합 모두 충돌 없음 | #299는 봉인된 60+12·teacher 준비부터 종료까지 안전 추적·L1 종료·σ 기준을 요구한다. #316의 목적지 evaluator 필드나 #306 끝점 모형으로 이를 대체할 수 없다. |
| #316/#306 + #301 | 두 조합 모두 충돌 없음 | v2 dependency API는 별도 opt-in이다. P04 observer와 최종 평가 어댑터를 실제로 연결한 소스는 새 closure에 포함해야 한다. 기존 봉인을 자동 이관하지 않는다. |

**MINOR E306-1 — 병합 순서에 따른 인덱스 충돌.** 근거는 두 PR의 `experiments/README.md:3`.
`git merge-tree --write-tree <#306 SHA> <#292 SHA>`가 exit 1과 이 파일의 content conflict를 반환했다.
나머지 표의 여섯 쌍은 exit 0이다. 인덱스 양쪽 행을 유지하고 CI 목록의 양쪽 테스트를 보존하면 된다.
이 정적 합성 검사는 합성 트리의 runtime 검증이 아니다.

#292의 범위 변경 근거는 `experiments/2026-09-30-pair-v6h-carry/SIGMA_SCOPE_CORRECTION.md:5`, `:25`;
#299의 구별되는 입력 계약은 같은 실험의 `analysis/SEALED_INPUT.md:5`, `:10`, `:15`, `:27`이다.
#301 자체의 안전성/다른 검토 지적을 이 보고서에서 재인증하지 않는다.

## 기존 결과·기본값·봉인 보존

main 대비 #316은 새 모듈/시험/기록과 CI 목록 1행만, #306은 새 분석 폴더/시험 및 인덱스/CI 목록만 바꾼다.
기존 제어기·지도·카메라·센서·weld·registered JSON·배치·번들 ID를 수정하지 않는다.
#316은 production runner가 아직 import/호출하지 않으므로 현재 실행 기본값을 자동 변경하지 않는다.
#306은 고정 `source_list.json`을 기본으로 읽어 나중 raw를 자동 합산하지 않는다(`extract.py:264`).

분석 CLI를 직접 다시 실행하면 해당 분석의 `results/` 파생 표를 쓴다(`analyze.py:424`, `extract.py:264`);
새 draw/입력으로 실행할 때는 별도 결과 경로/새 버전을 사용해야 한다. 이번 검토는 새 raw 경로와
`/tmp` archive를 사용했고, 검토 대상의 기존 결과·sealed bytes·등록 파일을 고치지 않았다.

## 직접 검증과 미검증

공용 잠금은 기존 `scripts.run_ci_tests.run_locked`로 획득했다. 다른 작업의 잠금이 비워질 때까지
대기했고, 종료 후 자기 잠금 반환을 확인했다. 기존 Mac Python 3.12.13/NumPy 2.5.2 환경,
`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`을 사용했다.
추가 worktree 없이 정확한 PR SHA를 `git archive`로 `/tmp/review-e-fixed/<PR번호>`에 풀었다.

| 직접 확인한 항목 | 결과 |
|---|---|
| #316 새 계약 suite | **38 passed**, 223.89초. 작성자의 277개 전체 관련 suite를 재실행한 것은 아님 |
| #306 단위 검사 | **14 passed** |
| #316 손상 반례 | 양성 대조 1개 정상. 서로 다른 손상 8개가 모두 `valid=true`, 분모 1, `overall_pass=1`을 반환해 결함 확인 |
| #306 기존 모형의 LOCO 95% L1 포함률 | **0.6176470588 = 21/34** 재현 |
| #306 목표 모형 L1 보류 RMSE | **19.0778392 mm** 재현 |
| #306 headline, seed 20260930·2,000 bootstrap draw | **59.1377776553/60**, 5–95 분위수 **58.3214990681–59.8548727603**; 저장된 주 모형 forecast 전체 dict와 정확히 일치 |
| #306 raw 입력 | **3,661개 전부 재해시**, 누락/불일치 0 |
| #306 분석 provenance | 분석·입력·파생 파일 **33개 SHA 일치** |
| #316 검사 기록의 소스/fixture | **19개 SHA 일치**; 반례에 사용한 원본 trace SHA도 일치 |
| 신규 probe 6 + 선택적 prior 2 | 고정 확증 60배치와 지정 근접 기준 겹침 **0** |

손상 8개는 carry/end 실패, 마지막 done/end 실패, checkpoint frame 참조 불일치,
terminal NaN/잘못된 leg/잘못된 phase/실패 reason, checkpoint 프레임 필드 누락이다.
기존 38개 suite가 모두 통과하므로 그 suite만으로 E316-1/2를 막았다고 할 수 없다.
이번에 실제로 적용한 핵심 변형은 다음과 같다(각각 독립 복사본에 적용).

```python
record['robots'][0]['receipts'][-1]['outcome'] = 'failed'

grasp = next(r for r in record['robots'][0]['receipts']
             if r['leg_index'] == 1 and r['phase'] == 'grasp' and r['edge'] == 'start')
for key in ('frame_id', 'frame_sha256', 'captured_at_s'):
    grasp.pop(key)
# 둘 다 verify_trace(record) == {'valid': True, 'errors': []}
# run/job이 맞는 합성 audit/evaluator를 넣으면 summary overall_pass == 1
```

재현 driver·stdout·JUnit·변형별 JSON·원격 PR 스냅샷·merge-tree 결과는
`/Users/changmin/projects/ugrp/outputs/review-e2e-batch-e-20260930/`에 보존했다.
`review-e-counterexamples.py`와 `review-e-statistics.py`가 구체적인 실행 입력/절차다.
로컬 산출물 무결성 식별값:

| 파일 | SHA-256 |
|---|---|
| `counterexamples.json` | `1c353f4269c901fd44133e83ece487856a27cf39410eb5da53505940642404db` |
| `statistics.json` | `eb2889867230b686d38f613676ed540fcce77638d207f5967312c19c02b48e5d` |
| `pr316-junit.xml` | `a3ba79467a36ad53c0304100e0657a6b491cae001595e153c1c77740fa6b3d33` |
| `merge-tree.json` | `55acc1d03f55df43ca3da77c83ed219b04f9c5a8b43c9031febf198322251271` |
| `manifest.json` | `96f50be96ad11f03635552ccacbec2e2c4e10ed2e0bb14dea50256a67497cadd` |

조회 시 원격 checks는 #316 queued 32개, #306 success 64개였다. 이는 해당 조회 시점의 상태이며
#316의 원격 CI 완료를 주장하지 않는다. 검토 끝에 두 대상 PR의 HEAD가 위 표와 같은 것도 다시 확인했다.
이번 보고서 PR 역시 draft로만 제출한다.

물리·렌더·실제 provider/모델 호출·최종 제어기 인수·확증·봉인·병합은 수행하지 않았다.
새 실험 결과가 없는 독립 코드/통계 검토이므로 TensorBoard snapshot/서버/화면 작업도 수행하지 않았다.
Google Drive 작업은 하지 않았다. raw는 로컬 보관이며 원격 백업으로 표현하지 않는다.

Generated with Codex
