# E2E Batch J 독립 재현 검토

검토자 Codex, `codex/review-e2e-batch-j`, 2026-10-01 KST.
후보 구현은 수정하지 않았다. 지정 SHA를 `git archive`로 추출하여 검사했다.
새 worktree, 물리/SIM step, 렌더, 모델 호출, host lock은 모두 0회다.
이 판정은 아래 구현 범위의 코드 병합 의견이며 물리 인수 완료를 뜻하지 않는다.
대상 PR은 병합하지 않았다.

## 판정과 고정 소스

| PR | 검토 SHA | 판정 |
|---|---|---|
| #324 T12 | `521bcceb04ea1699a5378786017b47e8fc97aa35` | **MERGE** — 제출 대기·명시적 재배정·취소 경계에서 신규 차단 결함 없음. Batch F의 F1/F2 수정 재현, 447개 통과, 변이 5종 검출. |
| #336 T06 | `98ff3a1e3f3ecf7df18b339ae2e476327ac63ddd` | **MERGE AFTER FIXES** — J1: 두 안전 경계를 제거해도 crate 검사 전체가 통과한다. 회귀 검사 보완과 변이 재검출이 필요하다. |

시작/최종 비교 main은 `fb8ee9fbde4f5a458d1c9c7efa625110dd196edc`다.
`AGENTS.md`, `README.md`, `docs/current_status.md`, `CONTRIBUTING.md`,
`experiments/2026-09-30-scenario-capabilities/REQUIREMENTS.md`와 `TASKS.md`의 공통/T06/T12 계약을 읽었다.
기본 checkout은 올바른 origin의 깨끗한 main이며 이미 이 SHA였다. 갱신할 변경은 없었다.

이전 검토는 `origin/codex/review-e2e-batch-f`의 `887b4d5e73823733a39d10060734080e46668548`,
`REVIEW_E2E_BATCH_F.md`를 직접 읽었다. #323의 수정 head
`ad22566311cf1efb2911af69ee2b8e4c9c650dd0`는 #324의 조상이며,
main 병합 SHA는 `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`다.

## 한 묶음의 지적

### J1 — P1, #336: 운반 중 상대 holding·GO 누락 방어를 제거해도 기존 검사 55개가 모두 통과

근거는 후보 SHA의 `harness/zone_crate_skill.py:241`–`:245`, `:281`–`:284`와
`tests/test_zone_own_executor_crate.py:191`–`:232`, `:263`–`:273`이다.
각 조건문을 독립적으로 `if False:`로 바꿔 **전체 crate 파일**을 실행했다.
각각 **55 passed, 0 failed/errors/skipped**였으며 원본 복원 뒤에도 55개가 통과했다.
작성자의 7개 변이가 검출됐다는 기록을 부정하는 결과는 아니다. 추가한 두 변이가 살아남는다.

두 변이가 실제 안전 판단을 바꾸는 것도 별도 반례로 확인했다.

1. 양쪽이 정상적으로 `carry`에 들어간 0.90초 뒤, 0.95초에 상대가 최신 `not_ready` enum을
   전달한다. heartbeat는 살아 있지만 holding 증거가 없다. 자기 RGB는 자기 lug holding=yes,
   목적지 미도착이다. **원본은 `PARTNER_HOLDING_UNCONFIRMED`로 hold·종료**한다.
   `:281` 방어를 제거하면 **`carry_to_zone`을 내고 계속 실행**한다.
   기존 holding-loss 검사는 상대 skill이 스스로 abort하는 흐름을 검사해서 이 독립 wire 경계를 놓친다.
2. 양쪽이 close-ready를 보낸 뒤 r1만 0.30초의 close GO를 소비하고, r2의 그 tick을 생략한다.
   0.35초에도 r2 heartbeat는 유효하다. **원본은 `PARTNER_MISSED_GO`로 hold·종료**한다.
   `:241` 방어를 제거하면 **종료하지 않고 다음 barrier에서 대기**한다.
   기존 late-GO 검사는 양쪽이 모두 GO 시각을 놓치므로 한쪽만 소비한 경계를 검출하지 못한다.

정상 소스는 두 반례를 안전하게 막는다. 발견한 결함은 회귀 검사의 검출력이다.
T06의 한쪽 holding 누락·실패 전파·동시 실행 계약을 보존하려면 위 두 경우를 원래 crate suite에
추가하고, 각 방어 제거가 실제 assertion 실패로 검출되도록 해야 한다. 정상 소스의 방어를
완화하거나 봉인 파일/기대 해시를 바꿀 이유는 없다. 최종 변경 SHA에서 관련 검사와 정상 CI를 다시 확인한다.

`tests/test_review_e2e_batch_j.py`에 원본 안전 판단 2개, 변이의 행동 변화 2개,
**회귀 suite가 변이를 검출해야 한다는 strict xfail 2개**를 남겼다.
`raises=MutationSurvived`로 예상 실패를 제한하여 import/collection/실행 오류를 xfail로 숨기지 않는다.
후보 아카이브를 자동 생성·제거하는 기본 경로에서도 **4 passed, 2 xfailed**를 확인했다.
수정된 suite가 변이를 검출하면 strict XPASS가 나므로 검토자가 xfail을 제거해야 한다.

## Batch F 재검증 — #324

- **F1 해소:** 각 PR tree에서 요청한 `test_zone_pair_registered_source.py` 22개와
  `test_zone_study_source_pinning.py` 34개, 합계 **56/56** 통과.
  v6e full source 85개 및 scene source 12개를 등록 SHA-256과 직접 대조해 불일치 0개다.
  현재 실행 소스 검사와 역사 Git blob 검사를 모두 통과했다. 등록을 현재 해시로 다시 쓰지 않았다.
- **F2 해소:** 새 역할 모듈의 keepout을 모두 비우면 독립 기하 검사 **12개 실패**,
  실제 접근에 반대 역할의 keepout을 넘기면 **6개 실패**한다.
  이전에 keepout을 비워도 127개가 통과했던 검출 공백이 닫혔다.
- T12가 구형 host fixture를 다시 사용하도록 바꾸면 역할 불일치 거절 검사 **1개 실패**다.
  role-aware host 연결과 기존 봉인 host의 역할 API 거절을 구분한다.
- stale 취소 방어 제거 **18개 실패**, rendezvous timeout 제거 **32개 실패/16개 통과**.
  실제 fake-port host에서 양쪽 old job/queue/arm schedule 제거, 새 job 보호, 독립 양쪽 제출을 확인했다.
- `tests/test_zone_pair_rendezvous.py:144`의 `plant_attempts`는 실제 명령 경로에 연결되지 않은
  목록이고, `test_zone_pair_rendezvous_t07.py:133`–`:159`는 hold 주입 없이 제출을 늦춘다.
  이 이전 제한은 그대로다. **40초 실제/연결된 fake 구동 불응, 자기 RGB 인지, 물리 재집결 증거는 아니다.**

## TASKS 충족 범위와 입력 경계

| 항목 | #324 T12 | #336 T06 |
|---|---|---|
| 구현 범위 | 자기 port의 submit/cancel/replace/poll. r3 양끝·두 partner, deadline 전/경계/후, 실패 취소 후 새 제출 차단, old job fencing, r3 solo 구분. | 별도 `CrateLugSkill`: r1 west/r2 east, 900 g, lug ±.10 m/높이 .024 m, 두 actor close/lift/carry/lower/open 판단과 실패 전파. |
| 요구의 남은 부분 | 기본 study actor 연결 및 실제 hold에 연결된 관측·구동 시험은 미완료. `active`는 제출 참여만 뜻한다. | J1 검사 보완 필요. 실제 JPEG 판독기·arm/navigation 어댑터·runner 연결은 미구현. T06의 실행 가능한 전체 수행 완료는 아니다. |
| 제어 입력 | `PairRequest`의 공개 주문/zone/role/partner, 자기 job ack/status·자기 clock, 명시된 pair의 전달 enum 기록. hidden event 시각이나 partner executor를 입력받지 않는다. | `OwnRGB`의 자기 camera/ID/시각/bytes, 검증한 자기 명령 이력, 공개 order/role·정적 지도/lug 기하, 전달 enum만 판독 seam에 제공한다. |
| GT/private 경계 | private peer pose/holding/event 변경 시 자기 기다림·취소 trace 불변 검사 통과. host가 새 상대를 선택하거나 대신 제출하지 않는다. | 측정 관절/상대 pose를 command history에 넣으면 거절. foreign/top/future/replayed RGB, malformed perception도 거절. 새 GT/sim/referee 접근 경로 없음. |
| 네 조건 | condition/leader/event 입력이 recovery에 없다. 동일 timeout·source·enum으로 검사하고 role hash를 분리 기록한다. | condition 분기 없이 같은 skill/config/enum 사용. 조건 이름과 접근 불가 private fixture를 바꿔도 trace 동일. |
| 기존 API/봉인 | 기존 r1/r2 봉인 경로 유지. role-aware port는 새 `zone_pair_role_host`에만 연결. | opt-in `zone_crate_dispatch.executor_plan/PairTeam`에서만 명시적 kind dispatch. beam 위임·단회 order iterator 회귀 통과. 기존 봉인 진입점 그대로. |

두 후보의 인터페이스/변경 코드를 검사한 범위에서 새 GT·심판값·상대 private state 누출은 발견하지 않았다.
네 조건 검사는 오프라인 모듈 수준이다. 아직 연결되지 않은 runner를 통한 네 조건 E2E 동등성이나
실제 영상 인식 성능을 검증한 것으로 넓히지 않는다.
#336의 `PairTeam.start`는 긍정 FakeM2를 넣어도 `CRATE_PHYSICAL_ADAPTER_UNAVAILABLE`을 반환하며
`physical_supported=False`를 유지한다. `sequence_complete_unconfirmed`도 배송 성공 통보가 아니다.

## 실행 결과와 변이

기존 Mac Python 3.12 환경을 재사용했다. simulator/model import와 network/render/provider 진입을
막은 pytest guard 아래 실행했다. #328에 따라 오프라인 테스트의 host lock은 잡지 않았다.
아카이브의 역사 pin 검사에는 기존 Git object DB를 읽도록 환경만 제공했고 Git 설정은 수정하지 않았다.

| 원본 PR tree의 검사 파일 | 결과 |
|---|---|
| #324 rendezvous 161 + T07 합성 45 + role exchange 145 + pair executor 40 + pin 56 | **447 passed**, 오류/skip 0 |
| #336 crate 55 + pair executor 40 + status 16 + pin 56 | **167 passed**, 오류/skip 0 |

두 행에는 공통 검사 96개가 있으므로 고유 회귀 수로 합산하지 않는다.

| 변이 | 실제 결과 | 판단 |
|---|---|---|
| #324 stale cancel 방어 제거 | 18 failed | 검출 |
| #324 timeout 제거 | 32 failed, 16 passed | 검출 |
| #324 keepout 제거 | 12 failed | 이전 F2 해소 |
| #324 반대 role keepout 전달 | 6 failed | 이전 F2 해소 |
| #324 legacy host fixture 복원 | 1 failed | 검출 |
| #336 상대 ready 없이 자기 ready만 허용 | 3 failed | 검출 |
| #336 grasp gate 제거 | 1 failed, 1 passed | 검출 |
| #336 초기 holding gate 제거 | 1 failed, 1 passed | 검출 |
| #336 heartbeat 방어 제거 | 6 failed | 검출 |
| #336 lug 대신 body | 1 failed | 검출 |
| #336 운반 중 상대 holding 확인 제거 | **55 passed** | **J1 미검출** |
| #336 상대 GO 소비 확인 제거 | **55 passed** | **J1 미검출** |

변이 실행의 collection/import errors와 skips는 모두 0이다. 검출된 변이는 실제 assertion 실패다.
원본 복원 후 #324 변이 관련 **79 passed**, #336 **55 passed**를 확인했다.
각 아카이브의 harness/scripts/tests/sim/configs/maps **2,177개 Git blob**도 원본과 전부 일치했다.

## CI·보존·물리 인계

- 최종 fetch에서 두 대상 head는 지정 SHA 그대로다. 두 PR 모두 정상 CI **33/33 SUCCESS**다.
  [#324 CI](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36748779477),
  [#336 CI](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36743414321).
  #324의 처음 관측한 집계 queued는 최종 조회에서 성공으로 바뀌었다.
  #333의 과거 설치 timeout을 이 두 PR의 코드 실패로 사용하지 않았다.
- `git diff origin/main <candidate> -- .github/workflows`는 양쪽 모두 비어 있다.
  원본 s1–s6의 두 시나리오 디렉터리도 diff 0이다. 리뷰 브랜치에서도 workflow를 수정하지 않았다.
  두 PR은 draft/BEHIND 상태이며 실제 병합 전 최신 base 반영 및 최종 변경 범위 검증은 담당자가 수행한다.
- #324 `COORDINATOR_HANDOFF.md`: 정상1+원본 r3 12–52초 hold1, **각 900/총 1,800 SIM초**.
  seed623·leader=r3·end_neg=r1/end_pos=r3, staging/대기/취소 포함, 실제 hold/인지/재개와
  pair-delay 성립 분모를 구분한다. 완성 CLI/기존 성공 승계 주장이 없고 P01/P03/T08b/actor 합성이 관문이다.
- #336 `PHYSICS_HANDOFF.md`: s2 crate `(1.275,-2.15,0)`, west/east 실제 접근→B 정상1+
  동쪽 실제 미파지1, **각 900/총 1,800 SIM초**. final v3/walls_v3/tag0/weld OFF/noslip,
  staging·운반 전 holding 1.5초·판정·실패 주입·cap 실패·ENOSPC·보존을 명시했다.
  현재 native adapter 부재로 물리 인수 차단이라고 명시한다. 하중/마찰/실제 양측 holding은 미측정이다.
- 오프라인 회귀 결과로 물리 성공률/TensorBoard snapshot을 만들지 않았다. 두 물리 인계 모두
  실제 결과가 생긴 뒤 실패 포함 raw hash·native TensorBoard readback/영상/화면 검증을 요구한다.
  UGRP 예외에 따라 Drive 조회/업로드는 하지 않았다.
- raw 로그·JUnit·실행 명령·변이·CI metadata는
  `/Users/changmin/projects/ugrp/outputs/review-e2e-batch-j/`에 로컬 보관한다. 원격 raw 백업은 아니다.
  직접 만든 `/private/tmp/review-e2e-j-324-a2zkfway`, `/private/tmp/review-e2e-j-336-8tis6522`를 삭제하고
  부재를 확인했다. 재현 테스트의 자체 temporary archive도 context 종료 시 제거됐다.

## 재현과 증거 해시

검토 브랜치에서 아래 명령은 고정 후보 SHA를 임시 추출하고 종료 시 정리한다.
`UGRP_REVIEW_J_CRATE_REF=<fetch한 수정 SHA>`로 수정된 suite를 재검토할 수 있다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  -q tests/test_review_e2e_batch_j.py -p no:cacheprovider
# 현재 고정 후보: 4 passed, 2 xfailed
```

| 로컬 raw 파일 | SHA-256 |
|---|---|
| `324_baseline.xml` | `ed84da0949b49e1c15c760227277c15831d9d50da3d06d4c037231f1b8b91b57` |
| `336_baseline.xml` | `407e57937ef5f9a817ddf9821f4244bef16b47586e4dd33bc981093feb0fe20e` |
| `336_peer_holding_removed.xml` | `147a427bb75035f6a1b06b08525a2718aa14d672a48da9e083fe74ca80be1d9a` |
| `336_missed_go_removed.xml` | `5e09b106d1c29e2982b71269bab4bbaadc79dc5c9ecb7a49614bc215c666b388` |
| `review_counterexamples_self_contained.xml` | `0ca54f23a8c29bc11dc974ae43c1c5ed3c497dd2654308e74118180239f0a78b` |
| `archive_restored.json` | `be3da38a9d90a1e06bd2c556e16b02b7760bbe23235ec0ea313c713c57b62528` |
| `ci_final.json` | `631f146cb31f79743adb53e436bbe831e8065fd78e0e78d2d1d15597eee612c3` |
| `cleanup.json` | `83c4d5e06e2ce6d409960f0ff0e213c4152bf0373c5e78af0c6d651a1e8e75f7` |
| `artifact_manifest.json` | `8645566849eb240a39b557d1b31a3067997cb1c52fdf2fc68bf3d732c2da671f` |
