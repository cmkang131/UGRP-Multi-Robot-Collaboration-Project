# PR #371: a148 → 1883c56 좁은 게시 최신성 검토

대조 기준: 이전 동결 `a1487266804860b88478fc68dbe3df6fea3a943d`, 새 고정 snapshot **`1883c56a749dc89597d57f570d4a2243cbb9595d`**. 공식 GitHub compare는 **ahead 2 commits / changed 12 files**, merge-base=a148이다. 아래 판정은 새 head/rebase에 자동 승계하지 않는다.

읽은 범위는 두 SHA의 `harness/pair_llm_billing.py`, `pair_llm_case.py`, `pair_llm_dispatch.py`, `pair_llm_prompts_ko.py`, `pair_llm_status.py`, `tests/test_pair_llm_status.py`, `docs/execution_versioning.md`, 공개 `experiments/2026-10-03-pair-llm-viability/README.md`다. 4개 retired config 내용은 열지 않았고 보존 해시는 독립 검증하지 않았다. README에 인용된 공개 요약은 작성자 설명이며 원자료가 아니다. raw/blind/outcome, 실제 request archive, 물리·모델·test 실행, GitHub write/browser 사용 없음. 최종 payload/manifest도 수정하지 않았다.

## 판정

| 항목 | 새 snapshot 판정 | 게시 원고 조치 |
|---|---|---|
| peer_nl `__CHARS__` 미치환 | **남음. 해결 아님** | 기존 finding 유지; 아래 새 SHA/줄로 갱신 |
| e0ad 전체 POST model_usage 개선 | **유지** | broad 비용 소실 주장을 되살리지 않음 |
| 이미지당1490 SIM 청구 | **유지 + 보관행 재검증 개선** | stored policy v1/v2 분기와 현재 writer의 require=v2 인정 |
| own_status의 partner 비간섭 주장 | **문서 정정 인정, runtime builder 동일** | 원문 이유 이름은 숨겨도 자기 결과·시간 정보가 남음을 명시; 완전 비간섭 주장 금지 |
| look_around의 실제 위치 복구 | **미검증, prompt 단정 완화됨** | recovery 보장 없음 인정; 허용 행동/기존 guard 계약은 유지 |
| 두 SIM 시계 | **명시 필드 추가 인정** | clock 오류 해결을 실험 검증했다고 하지 않음 |
| v97/v99 보존·v100 경계 | **문서·test 소스 추가 확인** | 새 retired bytes의 독립 동일성 확인으로 승격하지 않음; v100 미실행 유지 |

## 1. __CHARS__는 그대로 남는다

1883c56 [prompt113–117](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_prompts_ko.py#L113-L117)에서 `text는 __CHARS__자 이내` literal을 유지한다. [prompt150–173](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_prompts_ko.py#L150-L173)의 open `messages` 선택은 165줄 `.strip('\n')`뿐이고, 170–173줄 system_prompt는 named parts를 join 후 그대로 반환한다. a148→1883의 prompt 변경은 76–79,87줄 look_around 표현뿐이다. 따라서 e0ad 실행 재현→a148 source 동등성→1883 source 동등성의 제한된 연결을 유지한다. 이번에는 함수를 실행하지 않았다.

새 [tests533–554](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/tests/test_pair_llm_status.py#L533-L554)는 두 arm block 차이와 look_around 문구를 검사하며 미치환 placeholder 검사는 없다. 선택된 cap 숫자를 최종 system text에 넣고 2조건×2로봇을 확인하자는 수용 조건은 여전히 유효하다. 새 정책으로 240을 강제할 이유는 없다.

## 2. 청구 수정: 과거 행은 자기 정책, 현재 writer는 v2 강제

[billing65–80](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_billing.py#L65-L80)의 text+1490×images 계산은 변하지 않았다. 새 [billing83–119](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_billing.py#L83-L119)는 v1/absent policy를 이미지0으로, v2를1490으로 검증하고 unknown policy를 거절한다. v1에서 없는 image keys는 허용하고 존재하는 값은 v1 계산과 대조한다. [case130–133](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L130-L133)는 현재 실행의 저장행에 `require=billing.IMAGE_BILLING_VERSION`를 넘겨 v1-shaped row로 다운그레이드해서 통과시키지 않는다.

기존 [dispatch356–377](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L356-L377)의 정상/파서 거절 Attempt에 `total_billed` 연결과 [case296–303](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L296-L303)의 model_usage 출력은 동일하다. compare에서 pair_llm_live.py 변경은 없다. 이미지0·전체 실패usage 소실이라는 옛 주장을 재개할 근거가 아니다. 1490은 여전히 request-shape 잔차 보정 상수이고 순수 provider 이미지 토큰 측정값은 아니다.

새 [tests472–498](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/tests/test_pair_llm_status.py#L472-L498)는 v1/v2/strip/unknown 사례를 담는다. [501–506](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/tests/test_pair_llm_status.py#L501-L506)의 실제 과거 archive 검사는 하드코딩한 작성자 로컬 경로가 존재할 때만 실행되는 skipif다. 이번 검토가 과거 12행 무문제를 재현했다고 쓰면 안 된다.

## 3. own_status: schema/runtime는 동일, 통신 없는 조건의 정보 경계 설명을 바로잡음

[status23–33](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py#L23-L33)와 [144–149](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py#L144-L149)는 이유 이름을 `other`로 접어도 partner-caused 거절/작업 종료와 시간이 자기 결과로 보인다고 명시한다. 두 arm에 동일하게 노출됨을 인정하지만 no_comm이 동료에 관한 아무 정보도 얻지 못한다고 하지 않는다. 이전 문서의 강한 차단 설명을 수정한 것이며 **OUTCOMES/SELF_REASONS/build/end_class의 실제 코드는 a148와 동일**하다. 새 정보 노출을 이번 diff가 만들어 냈다고 쓰지 않는다.

작성자 문구의 “ONE bit … with the time”은 형식적 정보량 상한 증명이 아니다. 게시 원고에는 시간·횟수가 포함된 자기 결과 신호가 남는다고 쓰고 정량 1bit bound를 독립 보증하지 않는 편이 정확하다.

[tests419–438](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/tests/test_pair_llm_status.py#L419-L438)는 mismatch의 양 arm 동일 status trace를, [441–459](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/tests/test_pair_llm_status.py#L441-L459)는 partner 미제출의 job-end class를 검사한다. 후자는 docstring상 fake의 실제 원인이 INVALID_OWN_IMAGE이며 실제 rendezvous timeout까지 loop에서 도달하는 test가 아니다; timeout 문자열의 class mapping은 81–92줄의 별도 unit source다. 이는 새 test의 존재·설계를 읽은 것이고 통과/완전 비간섭을 검증한 것이 아니다.

## 4. 재관측 문구·시계·버전 경계

[prompt76–87](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_prompts_ko.py#L76-L87)는 “같은 claim 반복해도 풀리지 않는다” 단정을 삭제하고 제자리 sweep이 위치 재추정에 도움이 될 수 있지만 보장되지 않는다고 말한다. 실행 중 job 없음 조건은 그대로다. wait/release의 자기 RGB 위험 근거와 기존 executor 경로는 이 diff에서 변하지 않았다. readme74–77도 실제 회복효과 미검증 및 #363 이후 재확인을 명시한다. v100 미실행 초안이므로 PROMPT_VERSION v3는 그대로이며 template hash만 달라졌다는 공개 설명이다.

[dispatch59–68](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L59-L68)의 CLOCKS와 [321–328](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L321-L328), [449–458](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L449-L458), [505](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L505)는 reset-relative, absolute, reset offset, delivered-at 필드를 기록한다. scheduling 자체를 새로 바꾼 diff가 아니다. 이벤트의 own_status end time은 전과 같은 harness at_s이고 새 필드는 그 의미를 명시한다. [tests511–528](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/tests/test_pair_llm_status.py#L511-L528) 추가는 읽기만 했다.

[execution_versioning317–319](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/docs/execution_versioning.md#L317-L319), [README3–5](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/experiments/2026-10-03-pair-llm-viability/README.md#L3-L5)는 v97/v99 retired 보존과 **v100 물리·모델 실행 기록 없음, DRAFT_UNSEALED/research_result=false, #363 rebase 전 병합 금지**를 명시한다. retired bytes/hash를 이번에 독립 확인한 것은 아니다. 공개 README263–267은 condition label 노출의 잠재 단서 효과도 인정하며 본연구 등록 때 중립 label 선택을 논의한다. 이것을 새 runtime 변경 또는 새 측정 효과라고 부르지 않는다.

## 최종 원고 최신성 편집 대상

- `final-pr371-comment.md` 1/3–5줄: a148/1commit21file을 새 source cutoff와 대조 범위로 갱신. __CHARS__는 유지. archive policy·own event/timing 설명 정정·look 문구 완화·clock 명시를 인정.
- `final-execution-issue.md` E4 84–103줄: 같은 SHA/줄/범위를 갱신; `billing65–106` 묶음은 계산65–80과 verifier83–119로 분리. model_usage 줄은296–303. status 의미는 코드40–110 및 새 설명23–33.
- `final-index-issue.md` 22/45/53줄, `final-research-issue.md` 14/43/45/61/71줄, `final-research-causality-comment.md` 93줄: cutoff와 source anchors 갱신. 현존 prompt finding의 결론은 유지. own_status의 명시적 자기 결과 신호를 반영하되 새 handler가 이를 만들었다고 하지 않음.
- `final-publication-manifest.md`는 편집 담당이 SHA/범위/파일 hash를 갱신해야 한다. 본 subreview는 수정하지 않았다.
- 기존 동결의 v100 H300/live≤60·PROVISIONAL judge·v88/physical_ready=False는 이 compare에 관련 소스 변경이 없어 이전 판단을 유지할 수 있다. 이번 좁은 검토가 다시 직접 실행·전범위 검증한 것처럼 쓰지 않는다. #363 staged own-command history 문제와 v100 own_status는 계속 별개다.

남은 신규 미검증: 새 test 독립 통과, 실제 smoke1 archive 재검증, retired JSON byte identity, look_around 복구·loaded 안전, 실제 운반, 보정상수 타당성, 전체 경로 비간섭. 새 실험/모델/raw 없이 이 항목들을 “해결”로 승격하지 않는다.
