# 7차 독립 검증 / redteam

2026-10-03. 코드 수정·물리·렌더·모델·GPU·하드웨어 실행 및 외부 게시 없음. raw/blind/held-out/outcome 파일을 열지 않았다. `AGENTS.md`, `README.md`, `docs/current_status.md`, `CONTRIBUTING.md`를 먼저 읽었다. 로컬 main 기준은 `f2577bb5121748644df31eb0fc5a1c1b94b80d80`; PR #371 검토 고정점은 `1883c56a749dc89597d57f570d4a2243cbb9595d`다. source snapshot을 현재 저장소 HEAD의 실행 결과로 표현하지 않는다.

## 1. own_status 시계 혼합 — confirmed, P2

**실제 호출 경로의 의미 계약 오류는 확인했다. 합성 재현의 특정 시간 조합이 native 물리/실제 모델 실행에서 발생한 빈도와 행동·성능 영향은 확인하지 않았다.** `no_comm`·`peer_nl`의 자기 상태 모델 입력이 대상이며, `rule` arm은 이 상태 생성 경로를 쓰지 않는다.

### 발견자 출력과 독립적으로 확인한 호출 경로

| 근거 | 확인한 의미 |
|---|---|
| [case200–213](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L200-L213) | reset 후 `start=backend.now`; `PairLink(origin_s=start)`를 만든다. origin을 0으로 강제하지 않는다. |
| [dispatch138–171](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L138-L171) | frame/clock에는 origin을 빼지만 `gate_view()`는 gate의 원값을 반환한다. |
| [dispatch183–195](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L183-L195), [runtime63–91,103–111](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_runtime.py#L63-L111) | claim 허가 시 `_abs_now`를 저장한다. gate의 permit 시각과 submission outcome 시각은 backend absolute SIM이다. |
| [case225–245](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L225-L245), [dispatch321–328](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L321-L328) | own event를 `at_s=elapsed`로 전달한다. `_last_end.sim_s`는 reset-relative delivery time이다. 다음 runtime step 이전에 scheduler를 진행한다. |
| [dispatch305–319](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L305-L319), [status89–105](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py#L89-L105) | view와 last_end가 공통 시간축으로 변환되지 않은 채 `max((sim_s, rank))`에 들어간다. |
| [dispatch335–354](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L335-L354), [inputs383–411](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_inputs.py#L383-L411) | status는 로그 전용이 아니라 payload에 들어가고 그 body가 모델 user JSON이 된다. inputs는 a148 사본을 직접 읽었으며 a148→1883 unchanged 범위에 근거한다. |

별도 source 추적으로 nonzero origin이 실제 설계임도 확인했다. main의 `sim/final_pair_v3.py:66–76`은 base reset을 호출하고, `sim/final_environment_checks.py:43–44,57–62`는 `world.data.time`을 반환하며 setup 후 시간을 되감지 않는다. `sim/session_scenes.py:227–228`의 표준 자세 이동 `.6`초와 settle `.4`초가 시간을 소비한다. v3 constructor의 표준 `.30`초 경과도 `sim/zone_final_v3_scene.py:41–42`에 명시되어 있다. 따라서 현재 source의 nonzero reset은 staged preroll을 가정해서 만들어 낸 현상이 아니다. **5초는 reset 상한이며 native 실행에서 정확히 origin=5였다는 증거가 아니다.**

### 별도 수식 검증과 반례 경계

gate 사건의 reset-relative 시각을 a, 더 나중 own-end의 **전달** 상대 시각을 b, origin을 o>0이라 하자. 의미상 a<b이지만 현재 비교는 a+o 대 b다. 따라서 `0 < b-a < o`이면 과거 gate 사건이 최신 outcome으로 선택된다. 모든 timestamp에 같은 상수를 더하거나 모두 relative로 맞추면 사건 순서가 불변이어야 하는데 현재 builder 입력은 그 성질을 위반한다. 동률 rank 효과는 이 엄격 부등식 반례에 필요 없다.

발견자의 원본 AST fake 재현은 다음 상태를 보인다. 이 표는 그 JSON을 확인한 것이며 독립 native 실행은 아니다. 위 부등식과 actual caller 확인이 독립 검증이다.

| 상대 own history | origin | 현재 선택 | gate만 relative로 정규화한 대조 |
|---|---:|---|---|
| refused10, look-end14 | 0 / 1.3 | `look_around_ended` | `look_around_ended` |
| refused10, look-end14 | 5 | `claim_rejected` / WRONG_PAIR_DESTINATION | `look_around_ended` |
| pending permit10, look-end10.5 | 0 | `look_around_ended` | `look_around_ended` |
| pending permit10, look-end10.5 | 1.3 | `claim_released` | `look_around_ended` |

refusal total와 since_claim 값은 이 순서 오류를 검출하지 않는다. schema 검사도 각 enum/값 범위를 검사하므로 잘못 선택된 합법 enum을 받아들인다. 반대로 현재 job이 pair/look이면 builder의 running override가 우선하므로 항상 오류가 나지는 않는다. origin=0 또는 gate와 end 간격이 origin보다 크면 이 반례의 역전도 없다.

### adapter 도달 가능성과 과대 주장 방지

1. `zone_study_integration.executor_plan:271–285`는 유효한 pair claim을 look job 때문에 차단하지 않는다. `PairLink.call:191–195`도 **pair_carry job**만 busy 거절하고 look 중 permit은 허용한다.
2. 단, 모든 모델 호출이 look 중 가능한 것은 아니다. main `zone_study_decisions.py:25–31`은 busy일 때 message/event lane을 유예한다. 반면 common/start lane은 같은 차단을 받지 않으며 busy reask도 따로 존재한다(`zone_study_integration.py:586–598`).
3. 최초 common/start call 후 `zone_final_pair_runtime.py:56–67`은 초기 look을 자동 시작한다. 모델 call의 SIM charge 해제와 look 종료가 겹칠 수 있는 제어 구조다. `zone_own_executor.py:643–657`의 look 종료는 자체 software event이며 물리 파지 성공이 아니다.
4. `zone_own_contract.py:29`는 job_done을 idle wake로 매핑한다. case238–245의 event drain→scheduler→runtime 순서에서 종료 직후 모델 snapshot이 pending permit의 다음 제출보다 먼저 생기는 것을 금지하지 않는다.

그러므로 fake 입력이 API상 불가능한 상태를 강제로 만든 것이라고 반박할 근거는 찾지 못했다. 그러나 **10→10.5라는 특정 timing 자체는 fake endpoint**다. 실제 sweep 지속시간·call 토큰비용·모델 답변·idle wake admission을 모두 통과하는 native rollout을 재현했다고 표현하면 안 된다. 물리/모델 실행을 요구하지 않고 source 의미 계약을 고치는 P2로 전달하는 것이 적절하다. 수정 후 공통 시간축의 순서 불변성 및 실제 adapter의 fake scheduler 경로를 검사하면 된다. end가 event occurrence가 아니라 delivery time이라는 기존 의미는 별도로 유지·명시해야 한다.

### 증거 파일과 해시

- 발견자 원본: `review-notes/tmp/round7-runtime-contract-repro.py`, `review-notes/tmp/round7-runtime-contract-repro.json`.
- exact1883 snapshot: `review-notes/tmp/runtime-round7-source/harness/` 아래 3파일. 원격 고정 SHA fetch/사본 제공 provenance는 runtime/currentness 담당에게 받았고, 본 검토자는 실제 파일 본문·해시를 독립 확인했다.
- `pair_llm_dispatch.py`: `f53c31b61c6cecee3112d0c31d744f8b55ef8a1b64b429c7903ab3eac0b67dc9`
- `pair_llm_runtime.py`: `5b08cb392e41346d3aad0162f5688bc641c7014dfaeaddf2acfbc3048a52b791`
- `pair_llm_status.py`: `984b440be9c53fe6e610279ad9207a5598a697dda673d52183385a101dab0dd1`
- caller `/tmp/pr371-round7/head/harness/pair_llm_case.py`: `3d3fa03d344b6d7acf4a04469dede71c05d1a570f502852df76951d435d7b2cc`
- 로컬 `git cat-file`의 exact1883 object 확인은 partial-clone의 원격 접속 실패로 완료되지 않았다. git ref/working tree 변경 없음. 이를 source fetch 성공으로 세지 않는다.

## 2. 연구 신규 세 축 독립 QA

아래 평가는 `round7-research-insights.md`의 2026-10-03 수정본을 대상으로 한다. 논문은 저자/공식 출판 원문을 별도로 열어 확인했다. 새 효과 크기나 연구 결과를 계산한 것은 아니다.

### A. 통신 허용 × 선택적 look 허용 — confirmed, 식별조건 명시 후

`μcs=E[Y(c,s)]`, `ΔC(s)=μ1s−μ0s`, `I=μ11−μ01−μ10+μ00`는 두 권한 정책의 의도된 배정 효과와 outcome 척도별 interaction이다. S는 필수 low-level scan이 아니라 추가 look 선택권이며, 그 권한이 prompt/행동 가능성/시간/비용을 함께 바꾸는 total policy contrast다. 자연 간접효과를 식별하지 않는다.

초기 초안의 “양의 배정확률”만으로는 잠재 outcome과 assignment의 교환가능성이 성립하지 않는다. 작성자가 최신본에 결과 독립 무작위화, all-four block의 실행순서 무작위화, 리셋 및 run간 피드백/상태 비전달, 고정된 좁은 instance set의 주장 범위를 추가한 것을 직접 확인했다. 이 조건하에 설계 설명은 적절하다. 대화 중 “결과 독립”은 관측 Y와 assignment가 무상관이라는 뜻이 아니라 **배정이 잠재 outcome을 보고 결정되지 않는 randomized intervention**을 뜻한다.

선택 편향의 별도 논리 반례: C와 사전 난도 U를 독립 Bernoulli(1/2), 성공 Y=1−U, actual-look A=1{C=1 또는 U=1}로 두면 통신의 진짜 총효과는 0이다. 그런데 A=1에 제한하면 C=0은 모두 어려운 사례(Y=0), C=1은 반이 쉬운 사례(EY=.5)이므로 가짜 +.5 통신효과가 나온다. 실제 look 횟수/사후 busy 조정만으로 직접효과가 되지 않는다는 경고를 지지한다. 이런 subgroup를 기술 통계로 제시하는 것까지 금지하는 정리는 아니다.

[Imai–Keele–Tingley pp.312–313, Assumption1](https://imai.fas.harvard.edu/research/files/BaronKenny.pdf)을 독립 확인했다. treatment randomization과 mediator ignorability가 별도이고, 후자는 randomized treatment만으로 보장되지 않는다. 본문이 이 논문을 네 cell의 natural mediation 식별 근거로 확대하지 않은 점도 적절하다.

### B. KoP / readiness 유효기간 — confirmed as 제한된 해석

[Moses Thm3.1/4.3](https://arxiv.org/html/1606.07525v1)의 전제는 해당 runs model의 모든 point에서 만족하는 행동 필요조건, local state가 행동 여부를 결정하는 conscious action, 그리고 Thm4.3의 반드시 동시에 수행되는 행동이다. 이 조건에서의 지식 필요성을 UGRP 모델 발화의 사실성, 고수준 메시지 필요성, 실제 motor 동시성 보장으로 바꿀 수 없다. 초안은 이 확대를 피하고 있다.

[Halpern–Moses §11 pp.572–574](https://groups.csail.mit.edu/tds/papers/Halpern/JACM90.pdf)의 ε-common knowledge와 stable fact 구별을 직접 확인했다. 현재 시점을 포함한 ε구간의 서로 다른 시점에 사실을 아는 것과 현재 모두에게 참인 것은 다르다. 별도 간단한 반례: r1 readiness 유효구간 [0,1), r2 [1.1,2.1)이면 1.1초 간격의 두 ready 발화가 있어도 overlap은 없다. timestamp가 있는 메시지 자체도 sender 진술의 진실성·clock 단위·신뢰모델을 증명하지 않는다.

main `zone_pair_status.py:154–206`을 직접 읽었다. frame/source time 검사, observed+TTL, 최소 expiry, 공통 control-grid 후보 GO, 늦거나 만료된 GO 거절이 이미 구현되어 있다. `zone_pair_executor.py:331–335`는 상대의 GO 소비 확인을 추가로 한다. 그러므로 이 연구 축은 **새 TTL 결함이나 새 barrier 구현 요구가 아니다.** software validity와 physical truth를 나누고 어떤 조율을 측정할지 정하는 질문이다. 새 runtime 시계 finding은 상위 own_status의 독립 문제이며 이 low-level TTL 구현 전체가 깨졌다는 근거가 아니다.

### C. frozen artifact / selected witness / adaptive procedure — confirmed, 분류 보강 권고

[Cawley–Talbot §5](https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf)와 [Ladder §2–3](https://proceedings.mlr.press/v37/blum15.pdf)를 독립 확인했다. selection까지 포함한 방법을 평가할 때 selection을 외부 평가마다 다시 수행하는 논리와, raw label 없이도 이전 점수로 적응하면 검증 독립성이 무너질 수 있다는 경고는 초안과 부합한다. Ladder의 bounded-loss/iid/특수 score disclosure 보장을 로봇 개발에 그대로 승계하지 않았다.

독립 반례: 쉬운/어려운 두 영역이 같은 비중인 원래 D에서 policy 성공률이 각각 1/0인데 DEV를 보고 쉬운 영역을 witness target으로 고르면 새 seed에서 100%를 받아도 D의 성공률50%를 100%로 바꿀 수 없다. 이때 새 결과는 고정된 selected-target 분포에 대해서는 유효할 수 있다. 선택과 새 평가가 독립이라는 조건을 명시하면, DEV에서 후보를 골랐다는 이유만으로 frozen F 평가가 전부 부정되는 것은 아니다.

보강 권고 두 개:

- **F와 W는 배타적 분류가 아니다.** 최종 artifact F를 선택된 witness 분포 D_W에서 평가할 수 있다. F는 평가되는 정책을, W는 선택된 조건/target을, P는 선택절차 자체를 구별하는 표지라고 한 문장 추가하면 혼동이 줄어든다.
- P를 outer block마다 평가할 때 outer 평가 피드백을 보고 사람/LLM이 다음 block의 수정 규칙을 바꾸면 같은 고정 개발방법의 반복이 아니다. 개발 규칙과 정보·예산을 먼저 고정하거나, cross-block 학습까지 포함한 별도 adaptive procedure라고 명시해야 한다. F 평가에 nested 재개발을 강제할 이유는 없다.

작성자가 두 권고를 연구 메모 §3과 최종 축약 문장에 반영한 최신본을 직접 다시 읽었다. B의 finite trace 통과와 모든 indistinguishable run에 대한 knowledge 증명을 구별하는 추가 문장도 확인했다. **이 두 권고는 해결됨; 세 연구 축의 현재 표현은 독립 QA 통과다.** 위 보강은 새 실험·중단 요구가 아니다. 세 축 모두 과거 확증 설계를 소급 바꾸거나 추가 센서/GT/강제 고정장치를 도입하는 근거가 아니다.

### 독립 원문 retrieval

직접 연 primary refs: Moses `turn118view0` / `turn119view0–1` / `turn120view0`; Halpern–Moses `turn118view1` / `turn119view2` / `turn120view1`; Imai `turn118view2` / `turn119view3`; Cawley `turn118view3` / `turn119view4` / `turn120view3`; Ladder `turn118view4` / `turn119view5` / `turn120view2`. 위 문헌 설명과 논리 반례는 별개이며, 반례는 본 검토자의 구성이다.

## 3. legacy SIM catalog 횡이동 기본값 — confirmed, 현재 작업 P3 부록

main `f2577bb5121748644df31eb0fc5a1c1b94b80d80`의 actual caller를 별도로 읽었다. `harness/cli.py:38–47`의 명시적인 `--actions scripts/sim_actions.py`는 `default_registry`를 구성한다. `scripts/robot_actions.py:102–105`의 횡이동 speed65가 SIM schema에 그대로 복사되고(`sim_actions.py:18–29`), catalog118–164→registry169–174에서 생략 인자에 삽입된다. loop1777–1783→catalog198–200은 이 값을 실제 runner에 넘긴다. `sim_actions.run_for_robot:334`는 bridge health/POST보다 먼저 `_validate_params`를 호출하고 191–205의 31..40 검사에서 65를 거절한다. 실패는 loop1786–1801의 TOOL_EXCEPTION 응답이다.

따라서 actual registry 경로의 no-args 횡이동이 실패한다는 source 결론에 동의한다. 반증 범위도 확인했다. **직접 `sim_actions.run('move_left')`를 인자 없이 호출하면 validator 자체 default는35다.** 그러므로 “SIM의 모든 무인자 횡이동이 실패”가 아니라 **공개 catalog가 기본값을 주입하는 경로**의 불일치다. speed35의 fake 통과는 실제 횡이동 성능이나 안전 추천값을 입증하지 않는다.

현재 pair #363/#371 경로에는 이 catalog→legacy SIM bridge chain이 없으므로 E2E 차단 항목으로 올리지 않는다. 보존 경로의 기능 correctness는 coverage 담당의 P2 표현도 가능하지만, 이번 전체 작업 우선순위는 root 지침의 P3 부록이 맞다. `docs/browser_ui_retirement_20260923.md:8–15`도 보존 내부 API와 현재 표준 진입점을 구별한다. 발견자의 `round7-coverage-repro.py`는 읽었으나 전체53개 test나 fake 재현을 다시 실행하지 않았다. observer/slot 결과는 이번 독립검증 범위에 포함하지 않는다.

마지막 로컬 `git status --short`는 빈 출력이었다. 본 검토가 새로 만든 파일은 이 검토 메모뿐이며 저장소 소스·실험·Git refs를 변경하지 않았다.
