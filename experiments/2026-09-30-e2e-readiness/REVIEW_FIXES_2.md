# E2E 수정 검증 2 — 독립 재검토

2026-10-01 KST, 검토자 Codex. 대상 PR 구현과 분리한 검토이며, 로컬 물리·렌더·실제 비전/LLM 호출은 없다.

## 판정

| PR | 판정 | 이전 지적 | 남은 일 |
|---|---|---|---|
| #310 | **MERGE AFTER FIXES** | C310-1 해결: 실제 관리 진입 경로에서 실행 전에 거절 | P1 F310-1: 복원된 workflow와 모순되는 CI 테스트·안내 수정 |
| #312 | **MERGE AFTER FIXES** | C312-1 해결: 기존 봉인 소스 복원, P03 후보 분리 | P1 F312-1: 새 host의 평가 전용 경계 검사를 기존 규칙에 포함 |
| #314 | **MERGE AFTER FIXES** | D1 해결: 양쪽 carrier 누락을 독립 형상 검사가 검출 | P1 F314-1: CI 정책 테스트·안내 수정, 최신 base 통합 확인 |
| #315 | **MERGE** | D2 해결: 빈 carrier/arm 및 chassis 누락 9가지 변이를 모두 검출 | 정적 초기 자세 계약 범위의 의견이며 물리 실행 승인이 아님 |
| #316 | **MERGE** | E316-1/2 해결: 종료 일관성·소비 프레임 참조 검증 | 출력 기록 검증기 범위의 의견. 전체 fake suite 시간 초과와 취소 CI 재검증은 미완료 |

새 P0/BLOCK 사유는 발견하지 않았다. `MERGE`는 이전 검토와 같은 **내용 검토 의견**이며,
실제 병합·전체 CI 통과·물리 인수를 뜻하지 않는다. 대상 PR의 소스나 브랜치를 수정하거나 병합하지 않았다.

## 고정 소스와 이전 지적

검토 시작 기준 main: `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`.
실행 재개 시 확인한 최신 main: `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`.
최종 fetch 기준 main: `26bfcf8e2977e85132845d7704fe1070f277dd13`.
검토용 브랜치: `codex/review-fixes-2`. 대상 브랜치는 수정하지 않았다.

| PR | 재검토 HEAD | 이전 지적 |
|---|---|---|
| #310 | `5d363335a286247a58d19652771b7ecddb21ef05` | C310-1: corridor 거절 factory가 실제 진입 경로에 연결되지 않음 |
| #312 | `b38c1d5905fdf798dcfd34d215c7e82d0a0cf296` | C312-1: 현재 v6e가 고정한 공용 소스를 변경하여 기존 준비/검사가 깨짐 |
| #314 | `994b269d97d05dd2159c1a78f2b9eae9955790f9` | D1: 뒤쪽 운반자 형상 누락 변이가 신규 검사 62개를 모두 통과 |
| #315 | `86847071f0332c23e5858c93607e2b0bbeb6dc98` | D2: carrier/arm 형상이 비면 sweep 검사도 비어 신규 검사 56개를 모두 통과 |
| #316 | `21d138ac65b00d5a206f444bd7be9511b01dd55d` | E316-1/2: 모순된 종료와 누락·가짜 재파지 프레임을 전체 PASS에 사용 |

이전 판정 원문은 `origin/codex/review-e2e-batch-{c,d,e}`의
`experiments/2026-09-30-e2e-readiness/REVIEW_E2E_BATCH_{C,D,E}.md`다.
수정 전 코드 기준은 각각 `2bfb9dce`, `919f78ef`, `e9ee23ea`, `823ca2ce`, `8d755a5a`다.
새 Git worktree를 만들지 않고 고정 SHA를 `git archive`로 `/tmp/ugrp-review-fixes-2-20260930/`에 풀었다.
실행에 필요한 소스·설정·보정·fixture는 포함하고 무관한 대용량 실험 미디어는 추출하지 않았다.

## 소스와 workflow 보존

각 PR에서 다음을 직접 대조했다. 기준 main과의 PR diff 및 tip-to-tip diff를 구분했다.

- `.github/workflows`는 다섯 PR 모두 PR diff(merge-base부터의 변경)에서 **0개**다.
  시작 main과의 tip-to-tip diff도 0개였다. 대기 중 main에 #332의 Ubuntu simulation
  timeout 10→15분 변경이 들어왔으므로 최신 main과 직접 비교하면 `tests.yml` 한 파일의
  두 timeout만 다르다. 이는 대상 PR이 도입한 workflow 변경이 아니다.
- 기존 prereg JSON **53개**와 그 안에서 참조한 소스 경로 **87개**에 PR 변경이 없다.
- 각 PR tree의 현재 v6e 고정 소스 **85/85개**가 등록 SHA-256과 일치한다.
- 지정한 두 소스 고정 pytest는 **각 PR에서 22+33=55개 전부 통과**했다.
- 실행 전후 등록 파일·참조 소스·지정 테스트 **710개 파일(142개×5 tree)**의 해시를 대조했고 변경은 0개다.

원본 대조: `outputs/review-fixes-2-20260930/source-audit.json`, `final-main-workflow-audit.json`,
각 attempt의 `protected-differences.json`.

## 수정 내용과 새로 확인한 회귀

### #310

C310-1은 `sim/workflow_manager.py:391`의 표준 `zone-study-integration-run` admission으로 연결했다.
`sim/zone_study_admission.py:16`은 선택한 episode의 실제 지도 내용을 읽고, 문이 없으면
기록 폴더·subprocess·host 생성 전에 거절한다. 이름에 corridor가 없는 지도, 두 지도 폴더,
네 통신 조건, plan/run 및 잘못된 선택을 검사하는 새 테스트가 있다.
봉인된 생성자 직접 호출은 그대로이며 상위 admission으로 해결한다는 범위는 앞선 검토가 허용했다.

**P1 F310-1 — workflow 복원 뒤 남은 CI 테스트가 preflight를 깨뜨린다.**
`tests/test_ci_fast_path.py:20–26`은 단일 run ID group과 자동 취소 OFF를 요구하지만,
workflow는 main의 PR별 group/자동 취소 정책으로 복원되어 있다.
같은 HEAD의 [ci-preflight](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36719543454/job/109904519253)가
이 assertion으로 실패했다. `CONTRIBUTING.md:58–62`에도 반대 설명이 남았다.
이 PR의 범위를 벗어난 테스트·현재 안내를 main과 맞추고 정상 CI를 다시 실행해야 한다.
workflow를 다시 바꾸라는 요구가 아니다. 과거 검증 로그는 과거 기록으로 보존한다.

### #312

C312-1의 공용 runner·pose source·delay source는 원래 바이트로 복원됐다.
신규 `_p03` 모듈과 `vision_zero_tag_v2_p03_v1`을 분리하고 기존 factory/registry를 재연결하지 않는다.
새 preview는 실행 번들 ID가 null이며 `runnable=false`, `physical_ready=false`다.
후보 JSON과 참조 자산의 해시가 preview에 포함되고 저장 이후 변경을 거절하는 테스트가 있다.
이 구분은 #292의 역사 이관에 의존하지 않는다.

**P1 F312-1 — 새 host 파일이 기존 평가 카메라 경계 검사에서 누락됐다.**
`scripts/zone_study_provider_p03.py:22,155–156`은 평가 카메라 모듈을 새 host에서 사용한다.
`tests/test_zone_eval_top.py:172–187`의 허용 orchestration 파일은 기존 runner 하나뿐이어서,
같은 HEAD의 [shard 6](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36719609772/job/109905923359)가
새 P03 파일을 보고 실패한다. 현재 코드는 `self.eval_static`과 `self.eval_only['top_camera']`에만
설정을 쓰며, 이 실패 자체가 GT의 제어 유입을 입증하는 것은 아니다.
새 host도 기존 `assert_eval_only_uses` 검사에 포함해야 한다. 경계 검사를 삭제하거나
새 파일을 검사 없이 무시해서는 안 된다.

### #314

D1 보완은 planner가 반환한 형상과 독립적인 literal v3 cargo/chassis/arm 기준을 사용한다
(`tests/test_zone_own_executor_door_routes.py:19–57`). 두 문·두 통과 방향·두 heading의
문 통과 후 옆 이동을 모든 후보 경로에 대해 연속 sweep으로 확인하며, 각각의 carrier만
닿는 고정 벽을 둔다(`:145–192,215–233`). production planner는 이전 검토본과 같다.
원래 62개 테스트는 end_neg 누락을 모두 놓쳤다. 새 76개 테스트에서는 end_neg 누락 시
8개, end_pos 누락 시 9개가 실패했다. 실패는 실제 누락 역할의 차체·팔 충돌 및 잘못 허용한 경로 assertion이다.

**P1 F314-1 — #310과 같은 CI 정책 테스트 잔여 회귀.**
`tests/test_ci_fast_path.py:20–26`과 `CONTRIBUTING.md:58–63`이 복원된 main workflow와 모순된다.
같은 HEAD의 [ci-preflight](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36724382660/job/109917356583)가
이 assertion으로 실패했다. workflow는 그대로 두고 범위 밖 테스트·현재 안내를 복원해야 한다.

### #315

D2 보완은 양 역할의 station/prestation과 차체·팔을 literal 기준으로 구성한다.
각 역할의 **두 끝점×차체·팔=4개 형상**을 먼저 요구하고 모든 꼭짓점을 확인하므로 빈 목록에서 루프가 생략될 수 없다
(`tests/test_beam_initial_pose_plan.py:116–134`). XY/yaw 오차와 접근 중간 지점의 기준 형상도
반환된 geometry에서 가져오지 않는다(`:151–170`). 양 역할 각각의 차체 모서리·접근 중·팔 envelope
벽을 SEARCH/반대 carrier/beam과 분리해 검사한다. production planner는 이전 검토본과 같다.
두 역할/각 역할의 carrier·arm·chassis 누락 9가지 변이를 모두 검출했다.
수정 전 56개 테스트는 양쪽 carrier를 모두 없애거나 팔만 없애도 각각 전부 통과했다.

| 제거한 형상 | 양쪽 제거: 실패 수 | end_neg만: 실패 수 | end_pos만: 실패 수 |
|---|---:|---:|---:|
| carrier 전체 | 18 | 12 | 12 |
| arm | 10 | 8 | 8 |
| chassis | 3 | 3 | 3 |

각 변이는 현재 테스트 64개에 적용했다. 단순 import/환경 오류가 아니라 형상 수·독립 꼭짓점·sweep·벽 거절 검사에서 실패했다.

### #316

E316-1은 중간 end의 outcome, 마지막 end와 terminal의 phase·leg·시각·결과 및 완료 reason을
일관되게 검사한다. terminal도 유한 시각·정수 leg·기록 범위 검사에 포함한다
(`harness/pair_execution_contract.py:299–369`).

E316-2는 receipt의 명시적 초기 null과 필드 누락을 구별한다. 재파지에서는 자기 leg에서
이미 소비한 frame의 ID·SHA·capture·report·fix를 연결하고, 지연 fix의 capture도 확인한다
(`:253–285,330–343`). 일반 abort receipt에 새 영상 TTL을 무조건 강제하지 않는 이유와
소비 frame/전체 capture의 구분은 `REVIEW_FIXES.md`에 명시돼 있다.
JSON 참조 검증이며 실제 JPEG 보존이나 provider 추정의 정확도를 대신하지 않는다.

현재 추가 회귀 검사 47개는 모두 통과했다. 같은 테스트와 같은 합성 입력에 수정 전 검증기만
메모리에서 대입하면 **40개 실패, 7개 통과**다(E316-1 16개, E316-2 24개 실패).
40개 모두 잘못된 기록을 `valid=true`로 받는 assertion에서 실패했다.
두 로봇×8개 leg 전체로 확장한 손상 124개도 수정 전에는 모두 허용하고 수정 후에는 모두
`evidence_incomplete`, 분모 1, 전체 PASS 0으로 남겼다. 정상 입력은 두 검증기의 양성 대조를 통과했다.

이 비교는 원본 manifest의 SHA를 재확인한 기존 **합성** trace를 같은 입력으로 재사용했다.
새 fake 전이 실행의 완료나 실제 학생 실행으로 보고하지 않는다. 46개 payload 검사의
`completed_chain` fixture만 저장 trace로 공급했으며, 테스트 본문·assertion은 바꾸지 않았다.
47번째 초기 null 허용 검사는 원래 초기화/종료 경로를 실행했다.

## 직접 실행 기록

기존 Python 3.12 환경에서 수치 연산 스레드를 1개로 제한하고 물리/모델 import·네트워크를 차단했다.
Git은 과거 blob/조상 관계 조회만 primary object store에서 읽고, 검사 대상 파일은 PR archive에서 읽었다.
별도 프로세스의 import 격리 테스트 두 개는 원문 코드 일치 조건으로만 허용하고 네트워크/추가 자식 실행을 차단했다.

| PR | 현재 코드에서 직접 통과한 범위 | 수정 전/변이 검사 | 새 회귀 |
|---|---|---|---|
| #310 | corridor 54 + 소스 고정 55 + 관리 계획 2 = **111 passed** | 수정 전 관리 모듈에 현재 admission 검사: 23개 중 22개 실패 | CI 정책 검사 1개 실패 |
| #312 | lifecycle·후보 pin·provider·관련 검사와 소스 고정 = **114 passed** | 수정 전 두 pin 파일: 61개 중 5개 실패 | 평가 경계 검사 현재 1개 실패 / 수정 전 1개 통과 |
| #314 | door route 76 + passage 44 + 소스 고정 55 = **175 passed** | 이전 검사 62개는 누락을 놓침; 새 검사는 두 역할 누락을 검출 | CI 정책 검사 1개 실패 |
| #315 | 초기 자세 64 + passage 44 + 소스 고정 55 + destination 1 = **164 passed** | 이전 검사 56개는 두 종류 누락을 놓침; 새 검사에서 9/9 변이 검출 | 발견한 새 P1 없음 |
| #316 | 저장 합성 trace 회귀 **47 passed**, 별도 소스 고정 **55 passed** | 수정 전 같은 회귀 40개 실패; 추가 손상 124/124 검출 | 아래 전체 fake suite·CI 미완료 범위 유지 |

#312의 수정 전/후 pin 파일 전체 개수 차이는 P03 전용 검사 6개를 별도 파일로 옮긴 데서 온다.
실제로 실패한 5개가 속한 `test_zone_pair_registered_source.py`의 바이트는 수정 전/후 동일하다.
모든 확정 실행은 error/skip 0개이며, 의도한 반례의 assertion 실패를 환경 오류와 구분했다.

실행 기록은 `attempt-02`(#310/#312/#314 현재), `attempt-03`(#314 변이/#315),
`attempt-04`(#316)에 있다. `verification-summary.json`과 각 `results.json`에
전체 명령·SHA·테스트 이름·종료 코드·JUnit·로그 위치를 남겼다.

### 실행 보정과 미완료 범위

- 첫 #310 실행은 검토 wrapper의 읽기 전용 `git merge-base` 차단 4건과
  archive에서 빠진 기존 `models.zip` 1건으로 실패했다. 해당 SHA의 ZIP을 `git archive`로
  추가하고 읽기 전용 명령을 허용한 뒤 111개를 다시 통과시켰다. 최초 로그는 보존했다.
- #314 수정 전 테스트의 임시 파일명이 CI glob 밖이어서 수집 경로 검사 1개가 실패했다.
  테스트 바이트를 그대로 두고 glob에 맞는 archive 내 별칭으로 실행해 62개 통과를 확인했다.
- #316 전체 fake 계약 85개와 pin 55개를 묶은 실행은 **검토 runner의 900초 제한으로 종료**됐다.
  pytest 완료 요약이나 새 full trace를 얻지 못했으므로 이 묶음을 통과로 세지 않는다.
  당시 호스트 load average는 약 284/309/346이었다. 시간 초과의 근본 원인을 코드 결함이나
  호스트 부하 하나로 확정하지 않았다. 출력 검증기 회귀와 필수 pin 검사는 위와 같이 별도로 완료했다.
- 재사용 합성 입력: `outputs/p04-chain-contract-20260930/validation-04/full_trace.json`,
  **12,887,887 bytes**, SHA-256 `943225b657f9289391513864eb4f53671c9c1969bf3749ac113aabeb25898eb9`.
  원본 `VERIFICATION.json`과 실제 파일이 일치하며 `attempt-04/trace-provenance.json`에 기록했다.
- 시작 당시 지침에 따라 공용 잠금을 기다렸다. 첫 실행의 자기 잠금은 반환했다.
  대기 중 main의 `17be518e`가 오프라인 테스트 잠금을 opt-in으로 바꿨음을 원격에서 확인한 뒤
  새 지침에 따라 후속 오프라인 검사를 진행했다. 다른 작업의 잠금·프로세스는 변경하지 않았다.

### 원격 CI와 실제 병합 조건

검증 뒤 PR HEAD가 위 표의 SHA와 모두 같음을 다시 확인했다.
#310/#314는 preflight 실패, #312는 평가 경계 검사 실패가 남아 있다.
#315는 원격 check **33개 모두 success**다. #316은 **31 success / 1 cancelled / 1 aggregate failure**이며,
취소 shard 로그에는 assertion 실패 대신 작업 취소가 기록돼 있다. CI를 임의로 재실행하지 않았다.
최신 main이 진행되는 동안 병합 가능 상태는 재계산/변경됐다(#314는 충돌 표시도 관찰).
실제 병합 전 최신 base의 충돌 해소·필수 CI 전체 통과를 다시 확인해야 한다.

## 범위와 보관

이 검토의 판정은 수정된 정적·fake 계약과 회귀 방어 범위에 한정한다. 실제 provider 추론,
물리 인수, E2E, 봉인, 병합은 수행하지 않는다. 새 실험 cohort가 없어 TensorBoard snapshot이나
서버를 만들지 않는다. UGRP 예외에 따라 Drive 작업도 없다.
원본 명령·로그·JUnit·소스 대조는 primary `outputs/review-fixes-2-20260930/`에 로컬 보관하며,
검토 문서의 push를 raw 전체 원격 백업으로 표현하지 않는다.
검증 시점의 로컬 증거 133개 파일(2,330,667 bytes)을 `evidence-manifest.json`에 목록화했다.
manifest SHA-256: `564367c9647b11b25532cd0effae6039449726228501447d0bee745aa17df06f`.
