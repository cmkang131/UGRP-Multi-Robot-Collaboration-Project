# 8차 평가 코드 감사 — 발화 시각과 종료 상태의 혼동

2026-10-04 UTC 독립 감사. 새로 확인한 핵심은 **지원 중인 4조건 zone-study 보고 경로에서, 미래의 화물 이동이 이미 끝난 발화의 사실성 판정을 뒤집는 P2 결함**이다. 현재 두 로봇 v100 가능성 pilot의 운반 차단 원인으로 주장하지 않는다. 구현은 바꾸지 않았다.

## 고정 소스와 열람 범위

| 대상 | 이번에 확인한 SHA / 범위 |
|---|---|
| 원격 main | `b23fc0875b72f4b55f399a252a1575b7e8b43cb5` |
| 실제 오프라인 실행 checkout | `f2577bb5121748644df31eb0fc5a1c1b94b80d80`; 두 SHA의 diff가 `AGENTS.md`와 docs 3개뿐임을 확인했으므로 아래 평가·심판 코드 바이트는 현재 main과 같다 |
| PR #371 | `1883c56a749dc89597d57f570d4a2243cbb9595d`; 앞 라운드 계약과 동일한 head임을 확인, 이번 발견의 적용 경로로 삼지 않음 |
| PR #372 | `f676889f39df2de0679cc4e82e067565dcc5a775`; 어댑터·관련 테스트 전체를 읽음. `b4cd1336…` 이후 diff는 결과 기록 4개 파일이며 어댑터/테스트는 변하지 않음 |
| 공개 이슈 | [#222](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/222), [#223](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/223), [#224](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/224)의 연구 뼈대·통합·본실험 요구를 확인 |

`AGENTS.md`, README, current_status, CONTRIBUTING과 이전 final research/reproduction 원고를 읽었다. raw, held-out 궤적, v95 채점 JSON은 열지 않았다. PR 변경 파일 목록과 커밋 메타데이터는 읽었지만 실제 점수·잔차·새 시작점의 결과를 검증한 것은 아니다. 물리·렌더·실제 LLM·하드웨어 실행은 없다.

## EVAL-8-1 · P2 · 발화 사실성에 미래의 최종 배송 상태가 섞임

**명시 계약:** [metrics 문서 190–202행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/zone_study_metrics.md#L190-L202)은 발화 시각의 심판 로그와 대조하고, `delivered(item, zone)`는 발화 전에 그 구역으로 기록된 배송을 참으로 판정한다. [check_claim 1452–1480행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_study_eval.py#L1452-L1480)도 `as of at_sim_s`라고 쓰며 미래 행을 제외한다. “실험이 끝날 때까지 영구히 배송 상태가 유지되었다”는 주장으로 정의하지 않는다.

**문제의 연결:**

1. [Referee.trial_rows 242–245행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_study_referee.py#L242-L245)은 종료 시 아직 `standing`에 있는 물건의 확인 행만 남긴다. 종료 배송율을 계산하는 목적에는 맞다.
2. [apply_to_record 282–290행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_study_referee.py#L282-L290)이 이 필터 결과를 `trial.referee.deliveries`로 쓴다.
3. 실제 [runner 677–689행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/run_zone_study_integration.py#L677-L689)이 이 함수를 호출하여 `study/trial_record.json`을 저장한다.
4. [report.build 420–429행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_study_report.py#L420-L429) → `summarise` → `dialogue_metrics` → `check_claim`은 같은 최종 배송 목록을 과거 발화의 진실값에도 쓴다. 목록이 존재하지만 비어 있으므로 `unverifiable`도 아닌 `false`가 된다. [조건별 truthful_share 집계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_study_eval.py#L1778-L1783)에 직접 반영된다.

**실행한 반례:** 실제 `Referee`, `apply_to_record`, parser, dialogue evaluator와 cohort summariser에 합성 정답 행을 넣었다. 주문은 2개로 두어 첫 물건 배송만으로 episode가 끝나지 않는다. t=0부터 정착한 `cyan-1`의 배송이 t=2에 확인되고, t=3에 “cyan-1을 A에 배달했습니다.”라고 말한다. t=3까지의 모든 증거와 문장은 같으며 이후만 바꾼다.

| t=3 이후 합성 사건 | t=3 발화 판정 | truthful_share | 종료 delivery_rate |
|---|---:|---:|---:|
| 물건이 계속 A에 있음 | true | 1.0 | 0.5 |
| t=4에 들려 떠남, 다시 놓지 않음 | **false** | **0.0** | 0.0 |
| t=4 떠남 → t=5 내려놓음 → t=7 재확인 | true | 1.0 | 0.5 |

종료 배송율의 0.5/0/0.5 변화는 정상이다. 결함은 발화 후의 사건 때문에 그 과거 발화의 점수가 1/0/1로 바뀌는 부분이다. 발화 시각을 확인 시각보다 늦게 잡았으므로 정착 시작 시각과 확인 완료 시각의 해석 차이로 이 반례를 설명할 수 없다.

**영향과 한계:** 4조건 zone-study 경로의 배송 관련 대화 사실성 지표가 후속 운반·재파지·방해에 따라 달라질 수 있다. 대화 품질과 최종 수행 결과를 함께 해석할 때 분리해야 할 두 결과가 섞인다. 어떤 실제 과거 cohort에서 발생했는지, 빈도와 조건별 편향 방향은 측정하지 않았다. PAR2·최종 delivery_rate·현재 #371 v100 scorer가 이 반례 때문에 틀렸다고 주장하지 않는다.

**수정 방향:** 최종 상태용 `deliveries` 필터를 그대로 유지하면서 발화 채점용 전체 확인/출발 이력을 별도로 전달하거나, 별도 `eval_only/referee.json`을 명시적으로 연결하고 해시를 확인한다. 이 전체 이력은 이미 [referee.record 247–258행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_study_referee.py#L247-L258)에 있고 [runner 606–627행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/run_zone_study_integration.py#L606-L627)이 별도 파일에 보존한다. 과거 발화 채점은 고정된 주장 의미에 맞춰 발화 시각까지만 조회한다. 전체 이력을 무조건 `deliveries`에 합쳐 종료 지표를 바꾸는 방식은 피한다.

**수용 기준:** 발화 전 prefix가 동일하고 발화 후 이동만 달라지는 세 기록에서 과거 발화의 진실값은 같아야 한다. 동시에 종료 delivery_rate는 여전히 0.5/0/0.5여야 한다. 과거 기록에 필요한 시간 이력이 없으면 판정 불능을 보존한다. 다시 채점할 때는 원본을 덮어쓰지 않고 평가 버전을 구분한다.

## EVAL-8-2 · 조건부 보조 · absent는 최신 상태 대신 첫 과거 행을 읽음

[check_claim의 absent 분기 1509–1521행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_study_eval.py#L1509-L1521)은 발화 시각 이하인 행 중 첫 일치 행에서 반환한다. `present=True@0 → False@2`이고 t=3에 “없습니다”라고 말하면 false다. 같은 두 행의 저장 순서를 바꾸면 true다. 반대 전이 `False@0 → True@2`도 true로 남는다. 단일 absent 행 대조는 true다.

동일 재현 스크립트로 검증했다. 다만 현재 통합 runner는 `slot_states`를 생성하지 않으며 없는 경우에는 올바르게 `unverifiable`이므로, 최신 실험의 실제 오류로 확대하지 않는다. 이 공개 metric API를 시간 이력에 사용할 때는 `sim_s <= 발화 시각`인 가장 최근 상태를 선택하고 동시각 상충·시각 누락 규칙을 정해야 한다. 별도 현재 차단 이슈로 우선순위를 올릴 근거는 없다.

같은 함수의 `holding`/`blocked`는 각 상태 구간이 발화 시각을 포함하는지 검사한다. 현재 writer에 해당 하위 로그가 없을 때 `unverifiable`로 남는 것까지 확인했으며, EVAL-8-1과 같은 미래 종료 projection 결함을 추가로 확정하지 않았다.

## PR #372의 새 확인과 부정 결과

최신 [어댑터](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f676889f39df2de0679cc4e82e067565dcc5a775/scripts/score_consumer_criterion_b_v95.py), [관련 테스트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f676889f39df2de0679cc4e82e067565dcc5a775/tests/test_score_consumer_criterion_b_v95.py)를 읽었다. 소스 SHA256은 각각 `f64016dd93a48bc54d1e50f17b592132e370a3d72204d6aa8dc6f34205d01e5a`, `ae0228d2546d00d81bbdb52691b3c47cbf0431ba9f364b44642e43bc5407130f`다.

- owner 작성자 확인과 정확히 하나의 adapter marker 검증이 존재한다. 과거 “해시를 문장에 포함하기만 해도 통과” 조건은 현재 결함으로 반복하지 않는다.
- binding에 기록된 모든 source를 다시 해시하며 마지막에 input을 재검증한다. 이 재해시가 없다는 과거 주장은 반복하지 않는다.
- r1 loader를 frozen loader와 대조하고, r2는 자기 명령/자기 pose와 비교한다. loaded 시기의 r2 부호 반전을 이번 unloaded 채점에 적용하지 않는다.
- 네 `(map, robot)` 조합을 정확히 요구하며, 축별 split/horizon의 수치 통과를 각각 유지한다. `combine`은 false 우선, 그다음 unknown을 보존한다. 지도 둘을 독립 시행으로 세지 않는 문구도 있다.
- `score`는 chronology 거부 사유 하나만 해제하며 후보 미존재·지원 부족은 unknown으로 둔다. 실제 점수·raw·본실험 성공은 이번에 재검증하지 않았다.

이 범위에서 **새 blocker를 찾지 못했다**. 어댑터 전체 테스트를 이번 환경에서 다시 실행하지 않았으므로 코드 읽기를 “29 tests 재통과”나 “held-out 검증 완료”로 표현하지 않는다. #372의 새 결과 기록을 실제로 읽지 않았고 그 주장의 참·거짓도 판정하지 않았다.

## 검증 기록과 반복하지 않는 지적

```sh
PYTHONPATH=/workspace/scratch/21cbee94d5d2/ugrp-colab \
  python /workspace/scratch/21cbee94d5d2/review-notes/round8/evaluation-truth-time-repro.py
cd /workspace/scratch/21cbee94d5d2/ugrp-colab
python -m unittest tests.test_zone_study_eval -q
```

재현은 모든 assertion을 통과했다. 기존 평가 단위검사는 **71개 실행, 70개 통과·1개 skip**이었다. `pytest`가 설치되지 않아 pytest 명령은 실행 전 import 오류가 났고, 해당 파일의 정식 unittest 경로로 검증했다. 새 패키지 설치는 하지 않았다. 이 검사는 실제 물리, 임의 미래 데이터, 전체 테스트 suite의 보증이 아니다.

재현: `evaluation-truth-time-repro.py`; 출력: `evaluation-truth-time-results.json`. 평가 코드 SHA256 `3f00d0bacffd5e581b3a11372169d0856f257cbf08db45b353e51de2c592be2f`, 심판 코드 SHA256 `7ab76e9dadb95cea7a7827d5baef392f2c22c1a1cd230a2c0b0382663f590456`.

기존 pairing·CI·unknown 처리도 재검토했다. singleton CI를 만들지 않는 처리, token completeness와 lower bound, matched seed 반복 평균, PAR2 실패 비용은 기존 의도를 확인했다. P06 고정 분모가 이미 있다는 점, main-study primary가 PAR2라는 점, 반복 binary 평균에 McNemar를 직접 적용할 수 없다는 앞 라운드 경계는 유지한다. 이 목록을 새 발견 수에 합산하지 않는다.
