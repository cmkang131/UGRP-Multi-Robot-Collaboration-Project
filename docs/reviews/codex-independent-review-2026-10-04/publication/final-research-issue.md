2026-10-03 독립 연구 검토. **현재 우선순위는 최신 영상→특징→fix→운반의 연결과, 그 위에서 메시지가 바꿀 수 있는 허용 결정 하나입니다. 통계 계약은 본실험 freeze 전에 닫을 항목입니다.** 관련 #216 #219 #222 #223 #224.

main `f2577bb5121748644df31eb0fc5a1c1b94b80d80`과 고정 PR 소스를 검토했습니다. 아래는 설계·수학·문헌 분석이며 새 실험·학습·실제 모델 실행 또는 prereg 변경을 하지 않았습니다. 실제 DEV/heldout 원자료·outcome을 열지 않았고, 합성 수치는 UGRP 관측치·예상 성능·권장 N이 아닙니다.

## 1. 서로 다른 연구 계약을 합치지 않습니다

| 대상 | 현재 해석 | 동결/결과 주장 전에 확인할 것 |
|---|---|---|
| 역사적 4조건 본연구 DRAFT | PAR2 primary, H=1800 SIM초, 성공 elapsed·실패2H. 독립 외부 pilot의 label-blind pooled success<.30이면 delivery_rate로 한 번 전환하는 미동결 제안. binary success는 핵심 보조 | primary/심판/분모/반복/추론을 함께 고정. .30은 검증된 보편 문턱이 아님 |
| v100 가능성 pilot (v99 후속) | 2로봇·고정 역할·one beam, rule/no_comm/peer_nl, config 기본 H=300 SIM초·현재 live smoke≤60 SIM초, DRAFT_UNSEALED·research_result=false | 역사적 3로봇·4조건·한국어 설계와 별도 버전. leader/structured/자유 역할 분담의 효과를 시험했다고 하지 않음 |
| v100에도 유지된 잠정 geometric judge | lift≥3cm, 마지막 높이≤초기+5cm, 중심 zone. release·안정 지속시간·전 물체 점유를 확인하지 않음 | 4cm 든 물체도 set_down이 될 수 있는 공개 PROVISIONAL 한계. 실제 ‘안정 배송’ 주장에는 그 판정기를 별도로 연결하거나 명칭을 좁힘 |
| #365/#372 engineering scoring | consumer Criterion B/reprojection·새 시작점 보정 인수 | PF posterior·운반 성공·새 지도 일반화의 판정이 아님. #372의 기존 승인과 블라인드 절차 유지 |

근거: [미동결 PREREG_DRAFT](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/experiments/2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md), [v100 config](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/configs/pair_llm_v100.json), [잠정 evaluator](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_eval.py). 이번 최신성 동결은 #3711883c56이며 e0ad→a148에 이어 a148→1883의 관련 source delta만 확인했습니다. 새 테스트/운반/모델 실행은 없고 #363 rebase 전 초안 범위입니다. 이전 v99 결과와 새 입력/행동/청구의 v100을 같은 처리로 합치지 않습니다.

## 2. 관측 진단은 무엇이 실패했는지 가릅니다

현재 계약은 고정 wrist RGB·OpenCV·정적 지도/보정·자기 발행 명령·실제 메시지, tags0·weldOFF, grip 기록 전용입니다. #363 새 head는 영상 문턱과 staged gate를 바꿨으므로 과거 SELF_INVALID_IMAGE가 지금도 blocker라고 쓰지 않습니다. 이미 채택한 변경을 원복하는 권고도 아닙니다.

**최신 공개 DEV 요약의 종료 경계:** [17:01Z 공개 DEV 요약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5971355260)은 코드 `3358372e`/기록 head `73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`에서 두 로봇의 opening look이 7.8초에 끝나 합류를 통과했다고 보고합니다. `raise_high`는 approach의 `PAIR_COLLISION_GUARD`, `raise_high_align`은 `wait_close`까지 진행한 뒤 `BEAM_UNCERTAIN → PREGRASP_NOT_READY`로 멈췄습니다. HIGH staged 두 경로는 적재 상태 오류가 사라졌으나 `gate_ok=false`/명령0으로 입장 전 미도달입니다. floor staged 두 경로는 폐기하고 정상 opening look을 유지하는 align 진입으로 바꿨습니다. P03은 미시작입니다. **저자의 공개 요약이며 raw 독립 검증·운반 성공 확인이 아닙니다.** staged loaded 복원은 source에서 인정하며 과거 unloaded:HIGH 반례를 현재 결함으로 반복하지 않습니다.


동일 frame hash/time에 `출처/형식/fresh/settled → observer_called → usable_columns → likelihood_applied → informative_fix`를 연결하고 loaded/camera key를 남깁니다. 별도 과거 실행의 scan400/measured0은 **scan application400·admitted absolute fix0**입니다. 그 400회가 해당 source counter라면 initialized/observer/최소 column을 이미 통과했으므로, 전부 ‘특징 없음’으로 설명할 수도 없습니다. inlier fraction/prior support/curvature 중 실제 거절 위치가 필요합니다.

근거: [scan quality/install](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_final_pair_scan.py#L14-L49), [PF apply_scan](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/experiments/2026-09-26-vision-loc/vision_pf.py#L158-L187), [accepted-fix checks](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/owncam_time.py#L22-L39).

| 독립 수학 반례 / 구별 | 어떤 관측이 필요한가 | 금지할 확대해석 |
|---|---|---|
| 균일 벽 X=L의 floor row `v=cy+fy*h*(cosθ−a sinθ)/(L−x)`에는 벽 평행 y가 없음 | wall end/corner/다른 방향 경계 등 현재 허용 시야에서 대칭을 깨는 특징. 같은 ray 증가만으로 누락 축이 생기지 않음 | 현 finite map의 모든 ray/prior도 대칭인지 확인하기 전 현재 실패 원인/영구 불가능이라고 하지 않음 |
| beam 상대변환은 camera/object에 공통 SE(2)를 곱해도 같음. 두 relative yaw는 세 yaw의 common rotation을 구별 못함 | 최소 한 독립 map anchor와 유효한 상대관계 | relative-yaw spread 유지가 버그라는 주장, 대화·particle 수만으로 common gauge를 해결했다는 주장 |
| camera pose=`base pose × extrinsic` | commanded posture의 고정 보정과 실제 nuisance 범위를 구분. floor edge만이면 h/D 동일값을 구별 못하지만 wall top을 함께 보면 깨질 수 있음 | commanded PWM을 measured joint truth, camera localization을 무조건 정확한 base pose라고 표현 |
| local rank가 충분해도 반복 map mode가 둘 이상 남을 수 있음 | 허용 대체 pose의 실제 feature 예측·association을 비교 | curvature/ESS 하나를 global uniqueness·calibrated uncertainty로 승격 |
| rigid common-twist 명령 잔차가 작아도 실제 squeeze force/slip margin은 별도 | `vi=vo+ω×ri`는 명령 정합성 검사. actual twist에는 독립 시각 근거와 시간 정렬이 필요 | no-weld 기하 일치·빔 추적·grip 기록으로 force closure/안정성을 증명 |

표는 현재 실패를 측정한 결과가 아닌 명시적 반례입니다. raw RGB에 정보가 있어도 현재 column/edge 축약이 잃을 수 있고, global state가 완전히 식별되지 않아도 남은 모든 가설에 공통으로 유효한 행동이 있으면 작업은 가능합니다. near clipping 진단의 beam11.90–15.41mm<near22.225mm는 해당 #359 기하의 증거이며 별도 staged SELF_INVALID_IMAGE 원인으로 연결하지 않습니다.

관측 rank는 단위·noise를 고정한 `J=Σz^(-1/2) H D`로 읽어야 합니다. 단일 Jacobian rank 부족만으로 비선형 불가능을 증명할 수는 없습니다(`x³`는0에서 미분0이어도 injective). 위 불가능 반례는 관측을 보존하는 변환으로 제한했습니다. [Hermann–Krener 1977 §III](https://www.math.ucdavis.edu/~krener/1-25/10.IEEETAC77.pdf)는 국소 weak observability의 충분조건이며 map alias·보정오차를 자동 해결하지 않습니다.

## 3. 통신이 바꿀 수 있는 결정부터 확인합니다

v100은 고정 low-level paired skill 위의 claim/continue/wait/release에 idle-only look_around와 닫힌 own_status 입력을 추가했습니다. ‘claim 시점만 조절’은 e0ad까지의 좁은 설명이며 최신 전체 권한의 설명이 아닙니다. 공통 map/order/fixed roles·fixed-enum sync는 남습니다. 수신 메시지가 추가 판단·새 이미지 시점·5 SIM초 rendezvous 정렬을 바꿀 수 있습니다. 따라서 peer↔no_comm은 정책 묶음의 총효과입니다. no_comm을 정보/동기화가 전혀 없는 조건이라고 하지 않습니다. raw reject reason이나 executor pair-status가 LLM prompt에도 전부 노출된다고 가정하지 않습니다.

사적 정보의 가치 witness는 **같은 receiver legal history → sender만 구별하는 합법 증거 → 시간/대상/불확실성 정합 → receiver의 서로 다른 가치 있는 허용 행동**까지 있어야 합니다. 현재 [prompt65–87](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_prompts_ko.py#L65-L87)는 자기 wrist RGB에 위험 근거가 있을 때만 wait/release를 허용하므로 peer-only hazard→receiver abort를 준수 행동으로 요구할 수는 없습니다. 반면 idle-only look_around는 이미 허용된 새 선택이므로 legal-action witness에 재관측 선택을 고려할 수 있습니다. stopped/busy executor는 거절하고 busy pair를 중단하는 권한은 아닙니다. loaded 자체를 새로 금지하지는 않고 기존 loaded guard를 따릅니다. 이 재관측의 실제 정보·복구 효과는 아직 검증하지 않았으며1883 prompt도 회복을 보장하지 않도록 문구를 좁혔습니다.

[own_status](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py)는 자기 claim 결과·거절 누계·job 상태/종료의 닫힌 네 필드(last_outcome, reason, since_claim_s, refusals_since_last_call)이며 좌표·측정 관절·접촉·성공 판정 입력이 아닙니다. 양쪽 LLM 조건에 연결됐으며, 최신 [설명23–33](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py#L23-L33)은 partner-caused 자기 결과·시간 신호가 남음을 명시합니다. reason을 닫힌 값으로 접어도 timing/count까지 완전한 정보 비간섭이 성립한다고 하지 않습니다. 이 노출을 이번 diff가 새로 만든 것은 아닙니다. 재관측으로 새 view를 얻는 효과는 고정된 기존 history 사이의 메시지 정보효과와 구분해야 합니다.

고정 prefix에서 joint histories까지 같은 두 상태는 메시지만으로 구별할 수 없습니다. 반면 각각 혼자 모른다는 사실만으로는 충분하지 않습니다(독립 bits A,B에서 A XOR B). 정보가 늘어도 같은 허용 행동만 남으면 task benefit은 없을 수 있습니다. 공유 map/prior/이전 메시지에서 온 오류를 독립 새 증거로 중복 계산하지 않습니다.

| 질문 | 최소 비교 | 해석 한계 |
|---|---|---|
| 전체 운영 정책 효과 | 시작부터 peer 대 no_comm; 같은 사전 task 분포·실행기 | prompt·추가 호출·timing·메시지·실패·비용 총합. 내용만의 효과가 아님 |
| 고정 prefix의 delivery 효과 | 이미 생성된 동일 message/own action에서 deliver 대 drop | 그 reached-prefix 이후 continuation. 초기 no_comm 정책의 전체효과가 아님 |
| 내용/결정 기회 | real / 외생 고정 schedule envelope-only / no-delivery | 빈 문자열·‘준비됨’도 timing/intent 정보일 수 있음. schedule을 sender event로 정하면 무정보 대조가 아님 |
| 형식 추가가치 | 같은 source-time·uncertainty·fact bank의 NL 대 structured | cost-fixed 의미 진단과 각 형식 실제 비용 비교를 분리. 자유 NL 전반의 우월로 일반화하지 않음 |
| staleness/비용 | 유익 후보가 있을 때 같은 내용/source-time의 timely 대 stale | image capture→실제 사용의 age와 SIM wait를 보존. wall latency는 현 초안의 참고지표 |

full continuation에는 physics뿐 아니라 belief/history, permits/FSM, clocks, inbox/ack, queued jobs, budget, RNG까지 restore 검증이 필요합니다. 그 전 next-action replay를 physical counterfactual이라고 하지 않습니다. 성공한 episode·도착한 메시지만 사후 선택하지 않고 prefix 도달률·drop/parse/timeout도 보고합니다. 같은 seed는 같은 외생 event의 randomness 또는 같은 LLM 응답을 보장하지 않습니다.

F1 witness→F2 timing/opportunity를 먼저 고른 뒤 F3 형식/F4 complementary view/F5 age 중 필요한 질문만 택하는 것이 가장 작습니다. 새 지도·모델·센서·실험 실행 지시가 아니며, 작은 진단의 비유의성을 동등성으로 해석하지 않습니다. primary 문헌과 반대해석/음성결과 분기는 후속 참고 댓글에 정리합니다.

SIM 효율과 실제 wall latency, provider tokens와 표준 SIM 청구는 별개입니다. v100의 [billing65–80](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_billing.py#L65-L80)→[dispatch356–377](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L356-L377)는 이미지당1490을 text에 더한 total_billed를 연결하므로 과거 image-prefill 미연결 질문은 최신에서 개선을 인정합니다. 그 상수는 request-shape 잔차 보정이며 provider의 순수 이미지 토큰 측정값은 아닙니다. 비용 모델의 타당성/실패경로 전체 QA는 이 source delta 확인으로 보증하지 않습니다. 1883의 [정책 검증83–119](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_billing.py#L83-L119)은 보관행 v1/v2를 구분하고 현재 writer는 v2를 요구하며, dispatch는 absolute/reset-relative SIM 시각을 명시합니다. 이는 과거 archive 재실행 또는 wall latency 모델 검증이 아닙니다. logical-event CRN을 택한다면 정책과 독립적인 외생 event/time/entity에 난수를 대응시키고, ‘각 arm의 세 번째 발화’를 같은 사건으로 자동 간주하지 않습니다. 이는 검토자의 선택적 설계 제안입니다.

## 4. 본실험 freeze 전 통계 계약

| 항목 | 확인 근거 | 닫는 기준 |
|---|---|---|
| **S1. 평균 성공률과 binary McNemar 충돌** | [사전등록 초안 146–152](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/experiments/2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md#L146-L152)는 반복을 짝 전에 평균하지만 [205–214](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/experiments/2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md#L205-L214)는 성공에 exact McNemar/paired-binomial CI를 지정합니다. 성공/실패 두 반복 평균은 0.5로 binary pair가 아닙니다. | 성공의 binary 보조분석은 사전 지정 첫 시행을 사용하고 추가 반복은 안정성 분석으로 분리하거나, 반복을 보존하는 분석으로 검정·CI·표본수를 함께 바꿉니다. 결과를 보고 선택하지 않습니다. |
| **S2. pilot 결과 목록과 고정 배정 분모의 연결** | [eval 1862–1876](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_study_eval.py#L1862-L1876)/[report 420–428](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/zone_study_report.py#L420-L428)는 존재하는 기록을 요약합니다. 합성 3행(no_comm seed1, peer seed1/2)→n_pairs=1, excluded=0; 조건별 반복 1/2회도 평균해 짝을 만듭니다. 이는 의도된 pilot 동작입니다. | **기존 P06 fixed-plan admission을 재사용**합니다. [cohort 110–149](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/zone_study_evidence_cohort.py#L110-L149)와 [join 406–478](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/zone_study_evidence_join.py#L406-L478)는 missing raw도 admitted 분모에 남깁니다. 이를 실제 runner와 본실험 통계 입력까지 연결하고 condition/repeat/attempt 회수 목록을 대조해야 합니다. 새 admission이 전혀 없다는 지적이 아닙니다. |
| **S3. 표본수 상한이 자체 계산값을 자릅니다** | [초안 160–174](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/experiments/2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md#L160-L174), [design_calc 13–36](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/experiments/2026-09-28-main-study-prereg-draft/design_calc.py#L13-L36)의 공식에 rho=0이면 n_raw=134→18배수 올림144→cap108입니다. | 108을 80% power 확보값으로 부르지 않습니다. 144도 이 근사식의 값이지 검토자가 검증한 최종 권장 N이 아닙니다. 예산 cap/미달 가능성을 표시하고, 성공의 binary 보조분석을 별도로 설계할 때는 의미 있는 성공률 차이와 discordance 또는 CI 폭으로 설계합니다. 상수 결과·정의 불능 상관의 처리도 고정합니다. |

S2의 실제 연결 미완료는 [tensorboard 문서 219–226](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/docs/tensorboard.md#L219-L226)에도 synthetic 계약 검증과 runner 연결을 구분해 적혀 있습니다. [v100 runner](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/scripts/run_pair_llm.py)와 [v100 case 출력](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L296-L303)도 DRAFT/개별 case 결과 경로이며 P06 연결을 완료했다고 선언하지 않습니다. missing/unattempted/HOST_ERROR를 조용히 없애거나 임의의 성공/실패로 바꾸지 말고, 고정 프로토콜 규칙과 판정 불능 상태를 함께 보존합니다.

추가 **조건부 설계 위험**: 정규 OBF 경계+순열 p+중간 alpha 재분배+[반복 CI 요구](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/experiments/2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md#L178-L214)는 단일 분석 구현으로 결합 검증이 필요합니다. 이번 검토가 실제 FWER 위반을 입증한 것은 아닙니다. 첫 좁은 확증을 고정 N·주 대비 하나·최종 한 번 분석으로 단순화하는 방안을 권합니다. 여러 primary contrast를 유지하면 검정 가족과 전체 효과 주장을 먼저 정합니다.

방법론 근거: [Fagerland 등 2013, paired binary/McNemar](https://link.springer.com/article/10.1186/1471-2288-13-91), [2014 paired binomial CI](https://onlinelibrary.wiley.com/doi/abs/10.1002/sim.6148), [Lan–DeMets 1983](https://academic.oup.com/biomet/article-abstract/70/3/659/247777), [Maurer–Bretz 2013](https://doi.org/10.1080/19466315.2013.807748), [Nosek 등 2018 사전등록](https://www.pnas.org/doi/10.1073/pnas.1708274114). 일부 유료 논문은 초록·방법 범위까지만 확인했으며 해당 증명을 재현한 것은 아닙니다.
### 평균 효과 null과 sign-flip null을 구별합니다

PAR2는 `Y=T*success+2H*failure`, `E[Y]=p μ+2H(1−p)`인 **유계 혼합분포**입니다. 실패 atom·비대칭·paired joint structure가 중요하며 무한분산이라고 설명하지 않습니다. 같은 성공률 차이도 PAR 차이를 보장하지 않고, 성공률이 낮아져도 빨라진 성공시간 때문에 PAR이 좋아질 수 있습니다.

미동결 초안의 평균 D sign-flip은 pair label의 joint exchangeability 또는 difference 대칭이 뒷받침하는 null과 단순 `E[D]=0`을 구별해야 합니다. 합성 iid block에서 .95 확률 `(B,V)=(.20H,.10H)`, .05 확률 `(.10H,2H)`이면 양쪽 평균은 .195H지만 D는 −.1H/+1.9H라 대칭이 아닙니다. N36에서 전부 −.1H일 확률만 `.95^36=.157779`, 이때 exact sign-flip p=`2^(1−36)`입니다. 따라서 평균-null만으로 finite-sample level .05를 보장하지 못합니다. 전체 정수합의 기각확률은 .159587입니다.

**이것은 실제 UGRP type-I error·OBF/Holm FWER의 추정이 아니며 exchangeability null의 반례도 아닙니다.** 현재 pilot bootstrap API가 McNemar/sign-flip을 잘못 실행했다는 뜻도 아닙니다. MC 횟수 증가는 null 가정을 고치지 않으며, 큰 표본의 근사 타당성은 별도 근거가 필요합니다. 질문이 mean policy effect라면 그 estimand에 맞는 추론 근거를 outcome 전에 고정해야 합니다. [SciPy 공식 paired permutation 설명](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html).

### 합성 민감도가 요구하는 최소 구분

| 고정한 합성 가정 | 계산 결과 | 설계상 함의 |
|---|---|---|
| pB=.5,pV=.6, iid binary N108, 양측 exact McNemar α=.05/3 | discordance q=.1/.3/.6/.9의 power .9237/.2532/.1177/.0814 | 같은 +10%p라도 joint cells가 필요. primary PAR2의 power로 대체 불가 |
| 독립 N108 block·동일 반복분산, 1/3 block 추가 반복·block 평균 동일 가중 | 반복 difference ICC0/.5/.8/1일 때 Neff129.60/117.82/111.72/108 | 총144 paired 관측을144 독립 block으로 세지 않음. 실제 ICC/Neff 추정 아님 |
| DRAFT 4조건·N108·1/3 추가반복 | main episode576 (=4N+4N/3) | 요약432는 최초4N만. 외부 pilot·추가진단은 별도 |
| d=.4, arm 상관.8, SD ratio1/2/3 | dz=.6325/.4714/.3922 | 기존 변환은 등분산 조건. 상관 하한 하나로 failure mixture를 대신 못함 |
| 6개 fixed scenario와 새로운 scenario 모집단 | 후자로 일반화할 때만 between-scenario 분산이 추가 | seed 수만 늘려 새로운 map 일반화라고 하지 않음 |
| episode 내 J개 주문 | item ICC가 있으면 delivery fraction 분산 증가. 같은 심판의 J=1이면 binary | 주문 수를 독립 episode 수로 세지 않음. one-beam 산술로 v99/v100과 본심판을 동일시하지 않음 |
| 분석 endpoint가 모든 block에서 같은 상수(예: PAR 모두 실패) | 상관·표준화 effect는 undefined | rho=0이나 충분한 power로 조용히 대체하지 않음. fallback도 모든 배송0이면 정보없음 |
| cap/API/HOST 등의 알려진 protocol failure | 사전 endpoint 실패로 포함 | missing/unknown verdict와 구별. 불리한 비용 실패를 제외하면 estimand가 달라짐 |

정확 이항/조합합·닫힌식으로 계산했고 binary power는 독립 multinomial 합, sign-flip은 별도 정수 DP, lognormal moment는 수치 적분으로 교차 확인했습니다. **고정 N 단일 대비의 가정별 예시**이며 전체 순차·다중·pilot N 재추정 절차의 인증이 아닙니다. 108/144 어느 숫자도 최종 권장 N으로 제시하지 않습니다.

## 5. 다음 결정과 음성 결과의 처리

1. 최신 고정 source에서 처음 미도달한 영상/명령/운반 경계를 닫습니다. 한 번 E2E 통과는 feasibility입니다.
2. 현재 합법 행동 안의 정보·intent·timing witness 하나를 고릅니다. 공통 실행기에서 선택 전에 모두 실패하면 통신 무가치 결론을 보류합니다.
3. 새 live 연결의 인수에서는 model_usage의 실패·미상 completeness와 request→message→own claim→paired job→판정을 한 trace로 정산합니다. 현재 live 구현이 없다는 요구가 아닙니다.
4. 본실험으로 올리기 전에 P06의 **이미 있는** 배정/고정 분모를 writer→runner→분석으로 연결합니다. PAR2/fallback/binary보조, effect margin, null, 반복·attempt, cap/missing, N/순차/다중/CI를 한 버전으로 고정합니다.
5. 유효 구간이 사전 차이 margin을 지지하는지, 동등성 margin을 충족하는지, 둘 다 아닌 미정인지 구분합니다. 대화가 추가 비용만 들면 그 지원 범위의 음성 결과도 결과입니다.

새 모델학습·mapless SLAM·카메라/FOV·태그·grip gate 변경이나 대규모 코호트는 이 검토의 선행조건이 아닙니다.
