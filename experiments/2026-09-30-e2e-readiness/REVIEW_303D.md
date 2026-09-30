# PR #303 네 번째 독립 재현 검토

**판정: BLOCK.** 대상은 `3a46de0b7d3c1c295335355b106e95502839cb87`이다.
기존 반례의 수정은 확인했지만, 종료 창 밖의 재배송이 과거 배송을 되살리는 문제와
고정 심판 정책·정착 시간의 검증 누락으로 성공 분자가 여전히 커진다.
새 반례 11개에서 정상 시행 1개와 부적합 시행 1개를 합친 결과가 모두
**성공 2/2, INVALID 0, TensorBoard 성공률 1.0**이었다. 허용 가능한 성공은 최대 1/2다.
고정 분모 자체가 줄어드는 새 반례는 찾지 못했다.

2026-10-01 KST, 독립 검토자 Codex, `codex/review-303d`.
시작 main/리뷰 HEAD는 `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`.
물리·렌더·학습·실제 모델 호출 없이 PR archive에서 검사했다.
생산 코드, 등록 자료, `.github/workflows`를 수정하지 않았다.
아래 네 지적을 한 묶음으로 전달한다.

## D303-1 · P1 — 종료 창 밖의 마지막 배송을 빼면, 이미 취소된 예전 배송이 성공으로 되살아남

위치: `harness/zone_study_eval.py:915–925`,
`scripts/zone_study_evidence_contract.py:239–265`,
`harness/zone_study_referee.py:274–275`.

`delivery_state()`는 종료/cap 밖의 confirmation을 먼저 버리고 남은 행 중 마지막을
선택한다. 심판 원본 재구성은 현재 standing인 개체의 **모든 과거 confirmation**을
trial 배송 행으로 돌려주지만, 그 사이의 departure는 최종 지표 계산에 전달하지 않는다.
따라서 최신 confirmation이 늦었다는 이유로 탈락하면 과거에 취소한 배송이 복구된다.

독립 반례는 순수 `Referee.observe()`와 생산 `apply_to_record()` 및
`evaluation_block()`으로 만든다. 성공 flag를 수동으로 올리지 않았다.

- cap은 12초, 주문은 A로 보내는 두 개체다.
- item-0은 2초 정착 시작/4초 확인 후, 지속 파지로 **6초 departure**가 생긴다.
- item-1은 6.1초 정착 시작/**8.1초 확인**이다. 그때 item-0은 배송 상태가 아니다.
- item-0을 10.1초 또는 11초에 놓으면 재확인은 **12.1초 또는 13초**다.
  두 주문이 cap 안에 함께 충족된 적이 없다.
- 그런데 cap 밖 재확인만 제거하고 item-0의 2초 배송을 재사용한다.
  `apply_to_record()`가 `orders_complete`로 바꾸고 게시기는 성공으로 받아들인다.

같은 시간 관계 누락의 별도 반례도 있다. 정상 원본 심판은 8초에 오배송 상태이고
`orders_complete=false`인데, 이전 4초/5초 종료 기록과 결합하면 뒤의 오배송을
창 밖으로 버린 뒤 성공으로 게시한다. `last_sample_sim_s`와 terminal의 관측 종료
시각 사이를 대조하지 않기 때문이다. 외부 admission·plan SHA는 그대로다.

**4개 모두 실제 게시 결과 2/2, 기대 최대 1/2.** cap 안에 재배송이 확인된
9초→11초 및 정확히 cap인 10초→12초 대조군은 정상 성공으로 유지된다.
그 대조군의 history/deliveries/source 순서를 뒤집어도 통과한다.

수정 조건: 관측 종료/cap에 해당하는 상태를 confirmation과 departure를 함께
재생하여 계산하고, 마지막의 미확인/늦은 재배송 때문에 이전 배송이 되살아나지
않게 한다. terminal의 관측 종료와 raw 시간 범위도 연결한다.
배송 시각을 정착 시작으로 표시하는 기존 선택을 바꾸라는 지적은 아니다.

## D303-2 · P1 — 다른 심판 정책의 결과를 원래 고정 bundle의 성공으로 수입

위치: `scripts/zone_study_evidence_contract.py:257–260`,
`scripts/tensorboard_tools/zone_study.py:139–145`.
고정값의 생산 위치는 `scripts/run_zone_study_integration.py:399`다.

실제 실행 bundle은 `referee` profile 전체와 SHA를 담는다. 하지만 게시기는
evaluation의 `referee_profile_sha256`을 raw referee의 자기 주장 SHA와만 대조한다.
그 profile의 내용·해시를 **admission이 고정한 bundle의 referee**와 비교하지 않는다.

이번 대조군은 기존 최소 synthetic bundle에 실제 `zr.profile()`을 넣은 뒤
identity와 외부 계획을 먼저 고정했다. 이후 bundle/계획은 바꾸지 않고 원본 심판의
`settle_s`, `on_floor_max_z_m`, `settled_speed_m_s`, `held_depart_s`를 하나씩
다른 값으로 바꿨다. 해당 profile의 실제 해시를 다시 계산하고 evaluation이 같은
해시를 가리키게 했다. 파일 해시·관계 키·배송 내용은 일관되지만 두 정책은 다르다.

**4개 모두 원래 계획의 성공 2/2로 게시됐다.** 이 성공을 고정 정책의 근거로
인정할 수 없다. raw profile의 자기 해시와 외부에서 고정한 profile을 연결하고,
부재/불일치 시행은 분모에 남긴 채 INVALID로 처리해야 한다.
외부 pin까지 함께 고치는 공격이나 실제 물리 판정 재연을 요구하는 문제가 아니다.

## D303-3 · P1 — 2초 정착 정책에서 0초·0.1초·1.9초 confirmation도 성공 근거로 수락

위치: `scripts/zone_study_evidence_contract.py:212–218`.

시간 검사는 `confirmed_sim_s >= sim_s`와 마지막 표본 이전인지만 본다.
profile의 `settle_s=2.0`과 confirmation 간격을 비교하지 않는다.
bundle과 raw profile, profile SHA를 모두 그대로 둔 정상 성공 자료에서
history/deliveries/standing/trial의 같은 confirmation 시각만 각각 정착 시작 후
0초·0.1초·1.9초로 바꾸고 영수증 해시만 갱신했다. 성공 수치·주문·admission은 그대로다.

**3개 모두 성공 2/2로 게시됐다.** 선언한 판정 정책과 그 정책의 근거 행이
서로 모순된다. D303-2의 profile 동일성 검사만 추가해도 이 세 경우는 남는다.
고정한 profile의 정착 간격과 각 confirmation을 대조하되 기존 저장 시각의
반올림 허용오차는 유지해야 한다. 이 검사는 연속적인 물리 정착을 새로 증명하는
작업이 아니라, 기록 자체의 명백한 시간 모순을 거절하는 검사다.

## D303-4 · P2 — 새 필수 오프라인 검사가 CI 의존성에 없는 TensorBoard를 바로 import함

위치: `scripts/run_ci_tests.py:99–104`, `tests/test_review_303c.py:69`,
`requirements-test.txt:3–6`.

실제 제출 HEAD의 [Actions 36736874190](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36736874190)에서
offline shard 1/8, 3/8, 4/8이 각각 **5, 66, 13개 실패**했고, 84개 모두
`ModuleNotFoundError: No module named 'tensorboard'`다. 집계 `offline-regressions`도 FAILURE다.
Mac의 기존 환경에는 TensorBoard가 있어서 작성자/이번 로컬 묶음으로 이 배포 조건을
검사하지 못한다. 별도 `tensorboard-export` job의 성공도 이 shard 실패를 없애지 않는다.

새 필수 검사와 CI 설치 의존성을 맞춰 실제 readback을 실행해야 한다.
필수 반례를 skip 처리한 것을 검증 완료로 세면 안 된다.
검토자는 workflow나 의존성을 수정하지 않았다. 로컬 counterexample을 더 만든
항목이 아니라 해당 HEAD의 실제 CI 로그로 재현한 문제다.

## 이전 세 차례 지적의 수정과 검증 범위

다음 원문과 [작성자 답변](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/303#issuecomment-5914417967)을 읽었다.
`origin/codex/review-e2e-batch-a:.../REVIEW_E2E_BATCH_A.md`,
`origin/codex/review-fixes-1:.../REVIEW_FIXES_1.md`,
`origin/codex/review-303c:.../REVIEW_303C.md` 및 해당 반례 파일이다.

| 이전 지적 | 이번 독립 확인 |
|---|---|
| A303-1 외부 trial/scenario/seed/order 혼합 | frozen admission과 envelope/주문/요청의 연결 거절을 확인. 값·키·여러 행에 적용하는 일반 검사 유지 |
| A303-2 등록 runner 변경 | 원본 SHA `85508cc58e1cba0f1fc11e3b7ef656c0c7648202ff1086c274c3dbaa64a99edd` 유지. source 고정 검사와 85개 파일 직접 해시 대조 |
| A303-3 terminal 누락/타입 | 필수 true, terminal 필드, boolean completeness 검사 확인 |
| 혼합 시행 7건(F303) | 현재 7개 통과. 일반 내부 키/index의 중복·삭제·교환 검사도 유지 |
| C303-1 선택 집계 필드에 종속한 원본 검증 우회 | 해당 우회, history의 여섯 키, 필수 필드와 standing/orders 충돌 검사는 수정됨. 시간 창·profile까지 포함한 더 넓은 원본 성공 보장은 D303-1..3으로 미완료 |
| C303-2 dispatch/input 내용 충돌·전체 표 누락 | 기존 반례와 전체 키·프레임·시각·주문·역할·빈 필수 표 일반 검사가 통과 |
| C303-3 정상 행 재정렬 거절 | 독립 순열 216개, 실패/회복 이력 256개, raw 게시 순열 6개와 이번 cap 경계 정상 대조 통과 |

고정 계획과 여섯 열 복합키, 논리 trial과 실제 run의 구분, 사전 지정 attempt 하나,
출처를 모르는 고아를 보수적으로 거절하는 설계는 다시 문제 삼지 않았다.
12,000개 생성 사례는 정규화된 다섯 관계의 mix/duplicate/drop/reorder 각 3,000개다.
이 계층에서는 분모 탈락이나 성공 증가를 찾지 못했다. raw의 시간/정책 의미까지
검사하는 사례 수로 확대 해석할 수는 없다.

## 실행 결과와 보존

최종 집계는 `review_303d/verification.json`에 기록한다.

| 검사 | 실제 결과 |
|---|---|
| 제출된 offline selector 전체 | **525 passed / 0 failed / 0 errors / 0 skipped**. 등록 소스 22개·source pinning 34개 전체 포함 |
| 새 독립 반례와 정상 대조 | **5 passed / 11 strict xfailed / 0 errors** |
| 같은 파일 `--runxfail` | **11 failed / 5 passed / 0 errors**. 모두 판정 assertion 실패 |
| A303-1/3 vs `cbac1dfc` 판독기 | **34 failed / 1 passed / 0 errors**, 49 deselected. 옛 코드도 terminal=false는 거절 |
| A303-2 vs `cbac1dfc` runner 바이트 | **1 failed / 0 errors**. 의도한 source hash assertion 실패 |
| F303 vs `114349e0` 판독기 | **7 failed / 0 errors**. 잘못된 성공 이벤트 1.0을 읽고 실패 |
| C303 vs `f5566289` tree | **11 failed / 2 passed / 0 errors** |

음성 대조 실패는 현재 후보의 테스트 실패와 합산하지 않는다. 새 xfail은
`strict=True, raises=AssertionError`이므로 수정 시 XPASS로 실패하고, 예기치 않은
import/실행 오류는 기대 실패로 숨겨지지 않는다. 12,000 생성 사례도 pytest 항목 수에
더하지 않는다. 초기 C303 음성 대조는 archive에서 calibration fixture 하나를 빠뜨려
수집 오류가 났다. 해당 SHA의 정확한 파일을 추출한 뒤 다시 실행했으며 초기 로그도 보존했다.
A303 최초 selector에는 정상 retry 검사가 들어가 옛 metadata API의 KeyError가 났다.
그 항목은 결함 검출로 세지 않고, 실제 음성 대조만 선택한 별도 실행을 기록했다.

v6e 등록 소스 **85/85**, 수정 전 `f5566289`의 prereg 경로 JSON **57/57** 바이트를
확인했다. 지정한 source 고정 테스트 두 파일은 PR tree에서 전체 실행했다.
`origin/main`과 `.github/workflows`의 두 점/세 점 diff 모두 0개다.
최종 확인 시 PR은 OPEN/DRAFT, HEAD 동일, base보다 BEHIND이며 필수 CI 실패 상태다.

재현은 다음과 같다. 추가 worktree나 가상환경을 만들지 않았다.

```sh
mkdir -p /private/tmp/ugrp-review-303d/head
git archive 3a46de0b7d3c1c295335355b106e95502839cb87 | tar -x -C /private/tmp/ugrp-review-303d/head
cp tests/test_review_303d.py /private/tmp/ugrp-review-303d/head/tests/
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-e2e-readiness/review_303d/offline.py \
  /private/tmp/ugrp-review-303d/head tests/test_review_303d.py -rxX
```

전체 제출 묶음은 PR의 `redesign_test_driver.py`를 `GIT_DIR=/Users/changmin/projects/ugrp/.git`
환경에서 실행했다. driver는 MuJoCo·torch·물리 worker import를 막고 스레드를 1개로
제한한다. #328에 따라 host lock 없이 실행했으며 다른 작업의 잠금/프로세스는 변경하지 않았다.
반례는 정상 임시 원본을 만들고 그 사본만 바꾼다. 실제 raw와 기존 snapshot을 건드리지 않는다.

로그·JUnit·CI 로그 원본은 `/Users/changmin/projects/ugrp/outputs/review-303d/`, 합성
JSON/event는 OS 임시 폴더에 있다. 작은 검토 문서·테스트·재현 driver·해시 집계만 Git에
보존하며 로컬 로그 전체의 원격 백업을 주장하지 않는다. 연구 결과가 없는 독립 코드 검토이므로
합성 이벤트의 실제 EventAccumulator readback만 수행했다. 공용 TensorBoard
snapshot·서버·UI, Drive 작업은 없다. E2E·PHYSICAL·실제 provider 정산은 검토 범위 밖이다.
