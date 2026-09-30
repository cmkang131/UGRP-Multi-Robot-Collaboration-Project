# PR #323 수정 재현 검토 — 323B

검토자 Codex, 2026-10-01, `codex/review-323b`.

## 판정: MERGE

**`ad22566311cf1efb2911af69ee2b8e4c9c650dd0`의 명시적 opt-in 역할 확장 코드 범위에서 MERGE.**
기존 F1/F2와 CI 목록 충돌은 해소됐다. 이번 범위에서 새 P0/P1/P2 지적은 없다.
이것은 코드 검토 의견이며, 물리 인수·정식 코호트·실물 성공 판정이 아니다.
이번 요청은 독립 검토·기록·push·댓글이며 대상 PR을 병합하지 않았다.

- 현재 후보: #323 `ad22566311cf1efb2911af69ee2b8e4c9c650dd0`.
- 수정 전: `1a17829e79cdf7771ee2d09ca25e444c39cf37be`.
- 앞선 리뷰: #327 `887b4d5e73823733a39d10060734080e46668548`,
  [`REVIEW_E2E_BATCH_F.md`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/887b4d5e73823733a39d10060734080e46668548/experiments/2026-09-30-e2e-readiness/REVIEW_E2E_BATCH_F.md).
- PR에 합성된 main: `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`.
- 검토 브랜치 시작: `d7ee112e22018055ec08e1098c3f33a7a06cb420`.
- 마지막 합성 비교 main: `6f766ecaa590b21d3d4b8763ee88a8c2eea4b67d`.

AGENTS.md·README.md·docs/current_status.md·CONTRIBUTING.md와 T07 원문을 읽었다.
후보 두 개는 `git archive`로 각각 `/private/tmp/review-323b-head`,
`/private/tmp/review-323b-before`에 풀었다. 새 worktree를 만들지 않았다.
작성자의 코드, `.github/workflows`, primary checkout을 수정하지 않았다.
로컬 물리/SIM step·렌더·추론·모델/provider 호출은 0회다. #328에 따라
오프라인 테스트에 공용 호스트 잠금을 잡지 않았고, 성능 비교를 하지 않았다.

## 기존 지적의 수정 확인

| 지적 | 현재 구현과 독립 증거 | 판정 |
|---|---|---|
| F1, 기존 v6e 소스 봉인 파손 | 기존 5파일이 봉인 및 PR base 바이트와 일치. v6e source 85개, scene source 12개 전부 SHA-256 일치. 두 목록은 겹치므로 97개 고유 소스라고 합산하지 않는다. 과거 `prereg_v6e.json`은 수정 전과 바이트 동일. | 해소 |
| F2, 같은 `make_plan()`을 정답으로 쓰는 검사 | 고정 숫자 기대값 및 실제 `GuardedPairApproach` 전달 검사로 바뀜. 작성자의 15변이 전부 assertion으로 검출. 다른 세 위치/각도×6배정의 독립 기하 검사도 통과. | 해소 |
| main의 CI 목록 충돌 | 최신 main과 `git merge-tree`가 충돌 없이 tree `0ba66e44f5fae7cecf85235b234612179763b060` 생성. T07/P08/P07 파일이 후보와 합성 tree의 CI 목록에 각각 정확히 한 번 포함. | 해소 |

F1의 새 경계는 `harness/zone_pair_role_executor.py:14`, `:52`, `:204`,
`harness/zone_pair_role_host.py:5`, `harness/zone_pair_role_integration.py:12`다.
기존 5파일은 `zone_own_team_host.py`, `zone_own_executor.py`, `zone_pair_executor.py`,
`zone_pair_status.py`, `zone_study_integration.py`다. 새 모듈을 명시적으로 선택해야
역할 기능을 쓰며, 기존 host와 r1/r2 3인자 API를 함께 검사했다.
글로벌 클래스/함수/로봇 ID를 교체해서 봉인 검사를 우회하지 않는다.

`tests/test_zone_pair_registered_source.py`는 수정 전과 바이트 동일하다.
`tests/test_zone_study_source_pinning.py`는 PR base와 동일하고, 수정 전과의 유일한
차이는 main에서 들어온 `zone_study_llm_transport.py` 의존성 검사 1개 추가다.
검사 삭제·완화나 등록 해시 재작성으로 통과한 결과가 아니다.

F2의 독립 숫자 기대값은 `tests/test_zone_pair_role_exchange.py:152`–`:187`,
실제 driver 전달은 `harness/zone_pair_role_executor.py:188`–`:198`에서 확인했다.
금지 영역 전체/봉/상대 station/상대 prestation 제거, 계획의 역할 뒤바꿈,
봉/상대 padding 제거 7종은 각각 12개 assertion 실패였다.
driver 영역 제거/반대 역할 전달 2종은 각각 6개 실패,
봉인 소스 되돌리기 5종과 legacy API 격리 제거 1종은 각각 1개 실패였다.
15종 모두 collection/import error·skip 없이 검출됐다. 정상·복구 후 18개는 모두 통과했다.

## 수정 전 코드에서의 재현

| 실행 | 결과 |
|---|---|
| 수정 전 원본 T07 + 요청한 pin 2파일 | **177 passed, 5 failed**, error/skip 0. 앞선 리뷰의 결과와 동일. |
| 현재 원본 관련 17파일 | **536 passed**, failure/error/skip 0. T07 145, 등록 22, study pin 34, door-relax 20 포함. |
| 보존한 F1 반례를 수정 전에서 실행 | **5 strict xfail**; `--runxfail`이면 **5 assertion failed**, error/skip 0. |
| 보강한 기하 검사만 수정 전 원본에 이식 | **12 passed**. F2는 원본 기하 오류가 아니라 검출력 문제였으므로 이것이 정상이다. |
| 수정 전 `keepouts`를 모든 참가자의 빈 배열로 변이, 옛 T07 전체 | **127 passed**. 기존 사각을 독립 재현. |
| 같은 수정 전 변이, 보강한 기하 검사 | **12 assertion failed**, error/skip 0. production 코드를 고치지 않고도 보강된 검사가 손상을 검출. |
| 수정 전 archive의 production 바이트 복구 후 | **12 passed**, 원래 executor SHA-256 복구 확인. |
| 이번 리뷰의 최종 `tests/test_review_323b.py`, 현재 후보에서 실행 | **59 passed**, failure/error/skip/xfail 0. |

536개와 59개는 서로 다른 실행이며 검증 의미가 겹친다. 고유 검증 수로 합산하지 않는다.
17파일은 후보의 `experiments/2026-09-30-t07-r3-roles/offline_checks.py::DEFAULT`와 같다.
두 pin 파일을 후보 tree 자체에서 실행했으며, 역사 Git blob 조회에만 기존 object DB를 제공했다.

F2 이식은 새 모듈 이름을 수정 전의 `zone_pair_executor`/`zone_study_integration`으로
바꾸고 새 host mixin을 빈 mixin으로 바꾼 테스트 호환 처리뿐이다. 수정 전 host에는
원래 역할 API가 있다. `fixed_beam_and_partner_exclusion_geometry`와
`fixed_role_exclusion_geometry` 12개만 선택했고, production 계산/기대 숫자는 바꾸지 않았다.
변이 위치는 수정 전 `make_plan()` 반환의 `'keepouts': keepouts` 한 곳이다.

최종 리뷰 파일의 F1 반례는 **알려진 수정 전 host 바이트에서만**
`xfail(strict=True, raises=AssertionError)`다. 현재 후보에서는 일반 테스트로 통과한다.
수정 전 코드 전체를 xfail 처리하거나 현재 실패를 가리지 않는다.
역할 모듈이 없는 리뷰용 main에서는 5 passed/54 skipped이며, 이 실행을 후보 검증에 세지 않았다.

## 일반성·입력 경계·명령 전달

이번 리뷰의 추가 54개는 다음을 검사한다. 원본/변이 소스 검사 5개를 더한 파일 합계가 59개다.

- **기하 18개:** 원래 `[1,0,0]` 사례 대신 `[.8,0,-.174533]`, `[1,.1,0]`,
  `[1.1,.1,.174533]`의 공개 sheet를 여섯 배정에 적용했다. production geometry helper를
  정답으로 쓰지 않고 봉의 회전된 직사각형 경계·상대 station/prestation을 직접 계산해
  계획과 실제 접근 driver 양쪽을 대조했다.
- **실제 제어 객체 6개:** 모든 route leg에서 역할에 맞는 forward/left 부호와 양의 시간을
  검사했다. controller·status·카메라 메타데이터·arm/명령 port가 같은 실제 robot ID를
  유지하며, 전역 `m2.ROLES`/`DOOR_PLAN`은 변하지 않는다. 기존 T07의 24개 host port 검사와
  함께 r3 쌍의 외부 로봇에 arm/mecanum이 새지 않는 것을 확인했다.
- **네 조건 6개:** `condition_invariant_config()`를 정답으로 재사용하지 않고 raw config의
  키를 직접 비교했다. 조건·topology·encoding·leader·대화 채널/발화 한도만 제외했다.
  실제 M2 객체의 policy·보정 해시·계획·controller 계층·driver 종류·heartbeat/TTL도 동일했다.
- **제출 전 비공개 상태 24개:** 상대의 정지, holding, 위치/영상 불확실, busy 상태를 바꿔도
  첫 호출자의 역할·계획·admission·로컬 명령이 같았다. 상대 job은 대신 제출하지 않았다.
  기존 T07의 제출 후 비공개 상태 변조 24개도 통과했다.

역할은 `zone_pair_roles.py:34`–`:69`의 공개 robot ID와 요청 role에서 정한다.
`zone_pair_role_executor.py:237`–`:347`은 자기 readiness와 제출된 주문·role·정적 plan을
대조하며 상대 pose/holding/contact/평가 결과를 읽어 배정하지 않는다.
`role_door_schedule()`의 legacy ID는 순수 schedule 계산용 view에만 있고(`:72`–`:86`),
실제 port와 controller ID에는 적용하지 않는다(`:188`–`:198`).
상태 메시지의 FIELDS/STATES를 확대하지 않았으며 네 조건에서 같은 enum 채널을 쓴다.
완료는 기존 `PAIR_SEQUENCE_DONE`/`unconfirmed`이고 심판의 배송 성공을 제어기로 전달하지 않는다.

## CI·합성·남는 범위

[GitHub CI 36730315648](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36730315648)는
head `ad22566311cf1efb2911af69ee2b8e4c9c650dd0`, **33/33 jobs success**를 다시 확인했다.
작성자 보고를 인용한 수가 아니라 GitHub run/jobs와 head를 조회한 결과다.
현재 대상은 Draft·REVIEW_REQUIRED이며 GitHub mergeable/mergeStateStatus는 UNKNOWN이었다.
따라서 텍스트 합성 가능과 GitHub 병합 준비 상태를 동일시하지 않는다.

새 역할 경로의 정적 Python 의존 소스는 201개이며 receipt digest는
`5c6ecc05f5a7e7d5fab44e5fd7d8151cc42d72da09d308f3fe83436da71aeecf`다.
최신 main과의 합성 tree에서도 이 201개 바이트의 차이는 0개였다.
후보 CI 목록 335파일, 합성 목록 337파일이며 T07/P08/P07이 각각 한 번이다.
이는 source/목록 합성 검사이고 최신 main 합성 tree의 전체 pytest/CI를 실행했다는 뜻은 아니다.

LLM이 대화 중 파트너를 동적으로 고르는 정책, runner CLI, 새 runnable/workflow,
T08 이후의 남북 빔 경로, 최종 v3 환경 물리 인수는 이 PR 범위 밖이다.
#324는 여전히 예전 T07 기반이므로 새 opt-in API로 이관하고 별도 합성 검증해야 한다.
과거 r1/r2 물리 성공을 다른 네 배정의 성공으로 승계할 수 없다.

## 재현과 원본 위치

Python 3.12.13, 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 사용했다.
일반 실행은 다음 환경에서 수행했다. `GIT_DIR`은 역사 blob 읽기용이며 archive를 checkout하지 않는다.

```sh
git archive ad22566311cf1efb2911af69ee2b8e4c9c650dd0 | tar -x -C /private/tmp/review-323b-head
cd /private/tmp/review-323b-head
export GIT_DIR=/Users/changmin/projects/ugrp/.git
export GIT_WORK_TREE=/private/tmp/review-323b-head
export PYTHONPATH="$PWD:$PWD/experiments/2026-09-30-t07-r3-roles"
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  -p offline_guard -p no:cacheprovider \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py
# 리뷰 파일을 이 archive의 tests/에 복사한 뒤:
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  -p offline_guard -p no:cacheprovider tests/test_review_323b.py
# 작성자의 15변이 재현; --worker의 출력 폴더는 새 경로를 선택:
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-t07-r3-roles/mutation_checks.py --worker /tmp/323b-mutations-NEW
```

no-physics plugin은 MuJoCo/torch/torchvision, socket connect, schematic render,
실제 vision worker 생성을 차단했다. 추가 54개에서는 고정 archive의 AST/소스 해시
receipt 계산만 캐시하고 실제 제어 객체·계획·상태·port는 매번 새로 만들었다.

raw는 `/Users/changmin/projects/ugrp/outputs/review-323b/`에 보존했다.
`f2_replay.py`에 수정 전 원본/변이/검사 이식/복구 명령을, `f2-replay.json`에 실행별
명령·종료코드를 남겼다. 모든 시도의 JUnit/log, 15변이 driver/결과,
`pin-audit.json`, `role-closure.json`, `ci-selection-final.json`, `ci-run.json`도 있다.
초기 리뷰 검사 실행에서 cwd 때문에 skip된 1회와 기존 helper가 거절하는 ±0.15 m 경계
fixture 12개를 고친 과정도 보존했다. 경계 fixture는 지원범위 내부 값으로 교체했으며
후보 production 코드를 변경하지 않았다. 최종 검증 수에는 성공한 최종 실행만 사용했다.

| 핵심 증거 | SHA-256 |
|---|---|
| `head-related.xml` | `136592de5ec6e7dcb1c3f92e9488855beda59d9b8e6d82e27a5e2ba5960f8d75` |
| `before.xml` | `2e1121be2b6904bab51cca58af0db51b36f35ec7f09aad3c71ff6f9863a28294` |
| `review-delivery.xml` | `72329dc69193003e3c21fcbe91c1efdb30bf7680a883af000b947fa0005eb67f` |
| `before-f2-mutant-original-tests.xml` | `5baa67ca9f0fb18c8948891f909a810d932d92d392a84867f47a5471996cd03a` |
| `before-f2-mutant-strengthened-tests.xml` | `022449c2ed8e2ff929cca0b048402f571f5ecb7dcde822fd814cbea8a7978c96` |
| `author-mutations/result.json` | `4b92a24ddf7fabd8c93616cfbc67c6291d2e28101f1cd2118c62f031008722fc` |
| `pin-audit.json` | `0bd1b01176197a2198aad438c26760a756143d0a8d05a1aaa80d99073914f6d9` |

원본은 로컬 보관이며 원격 raw 백업이 아니다. 실험·학습·물리 평가 코호트가 없으므로
TensorBoard snapshot/성공 지표를 만들지 않았다. UGRP 예외에 따라 Drive 작업도 하지 않았다.
