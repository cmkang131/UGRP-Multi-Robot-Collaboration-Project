# PR #299 세 번째 독립 검토 — 2026-09-30

**판정: BLOCK.** 현재 분류기는 #292의 실제 기록 형식과 호환되지 않으며,
HOST_ERROR를 실패로 바꾸는 새 규칙은 등록 쪽 문서와 다르다. 이전 안전 위반
누락·잘린 파일 반례는 막혔지만, 완료된 handover 실패를 HOST_ERROR 재시도로
지우는 경로와 서로 모순되는 기록의 전체 PASS가 남았다.

| 대상 | 고정 SHA / 범위 |
|---|---|
| 분류기 #299 | `f32d5fd9afc54ca57ed49860843f54d6b5ca174d` |
| 등록 러너 #292 | `4c6b439f3f7c9a147c901f8b260a1e214d4eb396` |
| 등록 초안 #285 | `76e0f9ce793f8cbbff2349b2be2bbaa359250a42` |
| 이전 리뷰 | `de16cbc96becf19755f09197b9ef139609f00fe9`, `9a3a338fa784555969b913b2196892a252eaf8d6` |
| 공개 acceptance 소스 | `3c4fe30e2197518443b195392212b0341507ac59` |
| 리뷰 브랜치 | `codex/review-299c`만 변경·push |

`C`는 `experiments/2026-09-30-pair-v6h-carry/analysis/classify_placements.py`다.
줄 번호는 검토 SHA 기준이다. `CLASSIFY_NOTES.md`, `SEALED_INPUT.md`, PR 마지막
재설계 코멘트, 두 이전 리뷰와 양쪽 원격 브랜치의 `PREREG_DRAFT.md` /
`REGISTRATION_PLAN.md`를 대조했다. 물리·SIM step·렌더·모델 호출은 하지 않았다.
진행 중인 confirmatory raw는 디렉터리 열거·파일 읽기 모두 하지 않았다.

## P1 R1 — 실제 등록 러너에 없는 필드를 필수화해 정상 기록을 INVALID로 만든다

**분류기 위치:** `C:104–126,721–723,894–902,958–964`.
**기록기 위치(#292):** `scripts/run_pair_stage_probes.py:488–513,653–697,879–884,1270–1279,1300–1307`.

허용된 공개 원본
`/Users/changmin/projects/ugrp/outputs/v6h1-acceptance-3c4fe30e-claude-20260930`
11건을 읽었다. 10건은 lag-on 인수 사례이고 1건은 lag-off sanity다.
`scripts/run_pair_stage_probes.py`는 acceptance 소스와 #292 소스가 **바이트 동일**하며,
파일 SHA-256은
`531c420696ccb4c7d53fbfd17d1b96f3851730fd1f6881951b3c0892edc97c63`이다.
acceptance manifest에 기록된 실행 파일 fingerprint와도 일치한다.

| 분류기 필수 필드 | 공개 원본 / #292 writer 확인 |
|---|---|
| `result.evidence_sha256` | **11/11 없음**. `finish_result`가 저장하지 않음 |
| `result.evaluation_coverage.start_sim_s`, `.end_sim_s`, `.trace_count` | **11/11 부모 객체부터 없음** |
| `result.wall_contact.coverage.start_sim_s`, `.end_sim_s`, `.sample_period_s`, `.max_gap_s`, `.sample_count` | **11/11 부모 객체부터 없음**. writer는 `episodes`, `steps`, `note`만 저장 |
| `result.execution_identity`의 `source_sha`, `policy_id`, `bundle_id`, `source_files_sha256` | **11/11 없음**. 등록 worker도 이 객체를 쓰지 않음 |
| runtime `manifest.execution_identity` | 공개 acceptance에는 없고, #292 표준 manifest 생성 코드에도 없음. 표준 러너의 `source.source_sha`/`source.execution_tree.files`는 존재하므로 이것들까지 없다고 주장하지 않음 |
| runtime `plan.execution_identity` 및 평가 seal의 plan 형식 | 표준 writer는 `{labels,cases}`를 저장. 분류기의 plan/seal 형식으로 연결하는 adapter가 없음 |
| seal의 원 case에 요구하는 `source_sha`, `bundle_id`, `prior_id` | 공개 case 11/11 없음. 등록 `cases_for_plan()`은 기존 envelope case에 `registration_run_id`, 렌더·추적 옵션을 추가하고, 실행 때 `registration` receipt를 추가함. 위 이름의 필드는 추가하지 않음 |
| HOST_ERROR 시 `termination={outcome:"HOST_ERROR",sim_s:...}` | 조건부 호환성 문제. #292 `except`는 `result.host_error`만 쓴다. 정상 종료 전에 예외가 나면 termination은 없고, cleanup 예외 뒤에는 이전 termination이 남을 수 있음 |

등록 admission의 `registration` receipt 및 `execution_source_sha`는 분류기가 요구하는
`execution_identity`와 다른 구조다. #292 builder의
`ugrp.zone_pair_v6h_confirmatory.DRAFT.v1`/`sealed` 계약과 분류기의
`ugrp.v6h_confirmatory.v1`/`state="sealed"`도 직접 호환되지 않는다.
실제 진행 중 코호트의 wrapper나 봉인을 열어 이 차이가 보완됐다고 추측하지 않았다.

나머지 필수 기록은 독립적으로 확인했다. 모든 공개 사례에 row identity·chain L0/L1 및
미실행 후속 legs·명시적 first_failure·저장 안전 요약·두 로봇 failures·정상 termination·
trace의 t/tilt/lift/네 집게·접촉 episodes가 있다. result.row와 cases 행은 11/11 일치한다.
handover와 종료 창 검사는 11/11 통과하고, 도달한 L0/L1의 PF 쌍도 11/11 유효하다.
각 필드 목록과 실제 입력 36파일의 전후 SHA-256은
[recorder_audit.json](analysis/review_299c_validation/recorder_audit.json)에 있다.

**직접 판정:** 원본을 수정하지 않고 `adjudicate_attempt(..., confirmatory=True)`에 넣으면
11/11 **INVALID / FAIL**이며, 최초 오류는 `EVIDENCE_DIGEST_MISMATCH`와
`record start: ... None`이다. `historical_endpoints`에서는 lag-on 10건이 PASS이고
lag-off sanity는 FAIL이다. 따라서 정상 공개 인수 결과 10건을 필드 누락 때문에
실패로 낮추는 호환성 결함이 실제로 있다. historical PASS를 확증 PASS로 승인하거나,
11건을 새 확증 표본으로 쓰자는 뜻은 아니다.

**수정 조건:** 현재 수집기의 실제 계약과 판정기 계약을 먼저 연결하고 공개 acceptance로
검증해야 한다. 원 raw에 coverage나 기록 시점 해시를 나중에 지어 넣으면 안 된다.
존재하는 다른 provenance에서 유도할 수 있는 identity와 애초에 측정하지 않은
coverage를 구별해야 한다. 호환성 실패는 과제의 물리 실패율로 집계하지 말고 명시적으로
판정 불가로 남겨야 한다. 지금 수집 중인 자료에 새 필수 기록을 소급 적용하지 않는다.

**재현:** `audit_recorder.py` 및
`test_registered_recorder_produces_required_fields` 4개 strict xfail.

## P1 R2 — HOST_ERROR 규칙이 등록 문서와 달라졌다

**위치:** `C:745–762,799–815,1014–1026`.

- `origin/claude/b-v6h-gain`의 `PREREG_DRAFT.md:167–168,191–193`은 HOST_ERROR와
  주 시드 누락을 **미분류**로 보존하고 완료/성공을 막으며, FAIL로 억지 변환하지 않는다고 정한다.
- `origin/codex/pair-v6h-register`의 `PREREG_DRAFT.md:148–150`도 ENOSPC를
  **성공/실패에 넣지 않는다**, 동일 배치·시드 재실행은 1회라고 정한다.
- `REGISTRATION_PLAN.md`는 분류 정의 확정과 평가/실행 pin을 봉인 전 단계로 둔다.
  일반적인 보수성이나 상태 머신 도입을 근거로 실행 중 평가량을 바꾸라는 규칙은 없다.
- #299 자신의 수정 초안은 반대로 `INVALID→FAIL`을 명시한다. 숨긴 변경은 아니지만
  **등록 쪽과 합의된 동일 규칙도 아니다**. `EVALUATION_PROTOCOL`의 정확 일치 검사는
  구 seal에 새 규칙이 몰래 적용되는 것을 막을 뿐, 두 계약을 호환시키지 않는다.

완전하고 안전하며 과제 실패도 없는 HOST_ERROR를 재시도 없이 넣으면 사건은
`HOST_SAFE`, EOF에서 `INVALID`, 최종 class는 **FAIL**, `unclassified_reason=None`이다.
trace가 없는 ENOSPC도 FAIL로 센다. 입장 명부 60곳을 보존하는 것과 과제 실패로
대치하는 것은 별개다. 현재 구현은 호스트 기록 장애를 controller 성능에 섞고,
한 건만 있어도 코호트 전체를 `FAIL_A_B_SAFETY`로 만든다.

**수정 조건:** 등록된 HOST_ERROR·누락·확정 과제 실패를 분리한다. 알려진 하드 위반은
모든 시도에서 계속 보존하고, 미해결 오류는 성공 선언을 막는다. 실패 대치나 새 재시도
적격성을 채택하려면 실행/평가 계약의 명시적인 변경으로 다루며 이번 분류기 패치가
기존 등록을 바꾼 것으로 취급하면 안 된다.

**재현:** `test_unresolved_host_is_unclassified_under_registered_rule` 2개 strict xfail.

## P1 R3 — 완료된 handover 실패는 여전히 cleanup HOST_ERROR로 지워진다

**위치:** `C:651–678,716–717,732–754`.

`confirmed_task_failure`는 실패 이벤트와 leg 끝점 검사만 본다. 내려놓기·재파지·
teacher restaging 판정은 `not host`일 때만 실행한다. 다음은 L0/L1 끝점과 전체
trace·coverage·PF가 완전한 세 원본이다.

1. L0→L1 전이 창 내내 빔이 들려 있고 네 집게가 닫힘: `rest_release=False`.
2. L1 시작 직전 r1 두 집게가 열림: `regrasp_lift=False`.
3. `restaging_between_legs=True`라고 명시됨.

HOST_ERROR를 붙이기 전에는 각각 FAIL/INVALID다. 동일한 과제 증거에
`category=HOST_ERROR:ENOSPC`, `host_error=cleanup`, `termination.outcome=HOST_ERROR`를
붙이고 사전 허용된 성공 재시도를 추가하면 원본이 **HOST_SAFE**가 된다.
세 경우 모두 **73시도 / 72선택, 60/60, invalid 0, 하드 위반 0,
PASS_A_B_SAFETY**다. 원본의 실패를 보존하거나 모순으로 거부해야 한다.

두 번째 리뷰의 END_ERROR 예제는 고쳐졌지만, “완료된 과제 실패는 흡수 상태”라는
일반 조건은 아직 성립하지 않는다. HOST 중단 때문에 실행하지 못한 미래 handover와,
L1까지 완료해 실패가 이미 확정된 handover를 구별해야 한다. 과거 등록의 setdown
관문 선택과 별개로, 이것은 #299가 자신의 필수 성공 조건을 일관되게 적용하지 않는 문제다.

**재현:** `test_cleanup_host_cannot_replace_completed_handover_failure` 3개 strict xfail.

## P1 R4 — 원 기록과 요약의 모순을 해시가 대신 검증하지 못한다

**위치:** `C:265–274,651–678,681–701,716,739–742`.

완전한 60+12 합성 코호트의 C01/941만 다음 두 방식으로 바꿨다.

- **result에 HOST_ERROR:** 실제 러너 필드인
  `result.host_error={type:"OSError",classification:"HOST_ERROR",enospc:true}`가 있는데
  row와 termination은 정상 완료다. 분류기는 result의 host_error를 읽지 않아 PASS다.
- **동일 시각 원 endpoint와 derived leg의 모순:** r1/r2의
  `chain_raw.*.leg_end["1"].gt`는 둘 다 `t=3.01,lift_m=0,jaws=모두 false`다.
  같은 시각의 row leg는 `lift_m=.05,jaws=모두 true`다. 기울기는 모두 정상이다.
  raw GT에서는 tilt만 수집하므로 파지/들림의 명백한 모순은 무시된다.

각각 **60/60, invalid 0, PASS_A_B_SAFETY**다. 시각이 다른 표본을 단순 비교하거나
허용 오차를 지나치게 좁힌 반례가 아니다. 두 번째는 정확히 같은 시각·두 로봇의 원 기록이다.

합성 recorder는 이 **서로 모순되는 객체를 저장할 때** 해시를 만든다. 해시를 기록한 뒤
몰래 파일을 바꾸거나 여러 원본을 일관되게 위조한 사례가 아니다. SHA 일치는 보존된
바이트의 동일성을 증명하지만 요약과 원 관측이 논리적으로 일치함을 증명하지 않는다.

**수정 조건:** 실제 recorder의 source→derived 관계와 HOST 상태 사본을 검사한다.
모순은 INVALID로 남기며, 비동기 GT의 다른 값은 시간/출처를 고려해 구별한다.

**재현:** `test_contradictory_evidence_cannot_pass_entire_cohort`의
`result_host_error`, `endpoint_gt` strict xfail.

## P1/P2 R5 — 전체 범위 metadata의 자체 모순을 허용한다

**위치:** `C:96–123`, teacher 관측은 `C:267`에서 tilt만 읽는다.

- **P1 teacher 앞부분 누락:** `teacher.gt_after_lift.t=.10`, `gt_at_entry.t=.10`을
  남기고 trace는 `.25`부터 저장한다. coverage도 `.25`부터라고 명시한다. L0 시작은
  `.25`이므로 leg 경계 검사는 통과한다. `include_teacher=True`인데도 이미 저장된
  teacher 시각과 전체 기록 시작을 대조하지 않아 **60/60 PASS**다.
- **P2 불가능한 접촉 추적 범위:** wall coverage가 `start=-100,end=1000`,
  `sample_period=.05,max_gap=.05,sample_count=66`이라고 주장해도 **60/60 PASS**다.
  음수 SIM 시간과 1100초/66표본의 모순을 거부하지 않고, count를 wall 자신의 창이 아닌
  3.25초 evaluation 창과만 비교한다.

전체 trace를 “L0 이전 어디서든 시작했다”고 선언하는 것과 teacher 포함 전체 창을
덮었다는 증거는 다르다. 관측된 경계와 collector의 시작/끝을 연결하고 coverage의
자체 시간·표본수 일관성을 먼저 검사해야 한다. 실제 recorder가 내지 않는 필드를
추가하는 것만으로 이 문제는 해결되지 않는다.

**재현:** 같은 parametrized 테스트의 `missing_teacher_prefix`,
`impossible_contact_coverage` strict xfail.

## 이전 지적과 상태 머신의 일반성

| 이전 지적 | 이번 판단 |
|---|---|
| #299 R1 비동기 끝점 16° 누락 | 끝점/GT와 trace의 합집합에서 HARD 우선. 원 L0/L1 반례와 다른 시각/미세 초과값 검사 유지 |
| #299 R2 재시도에서 원본 위반 삭제 | 원본·재시도·거부 시도 전체의 안전 증거와 해시 보존. 주/보조 시드 위반 거부는 수정됨 |
| #299b P1-1 row.wall_contact 누락 | cases와 result.row의 저장 최대값 모두 검사. 누락 파일·양쪽 불일치에도 양성 위반 유지 |
| #299b P1-2 정상 줄 뒤 trace 절단 | 원본에도 coverage/count/order 검사를 적용하고 해시 손상도 차단. 단, 처음부터 모순된 coverage/수집 시작 경계는 R5 |
| #299b P1-3 확정 FAIL→cleanup→PASS | END_ERROR/controller 기록은 종단 실패로 유지. **handover/restaging으로 일반화하면 R3가 남음** |

명시된 6상태×5사건 전이표에는 빈 칸이 없다. 새 테스트는 빈 시도열과 길이 1–3의
모든 사건열 **155개**, 다섯 malformed-container 입력을 검사한다. HARD 우선과
이미 **FAIL 사건으로 올바르게 만들어진** 결과의 비복구성은 확인한다.
그러나 사건을 만드는 함수가 완료 실패를 HOST_SAFE로 잘못 만들면 완전한 전이표도
잘못된 PASS를 막지 못한다. 10,000 생성 테스트 통과와 입력 의미의 완전성은 별개다.

## 과도한 엄격성·검증 범위

새 정상 양성 대조는 원 정상 기록, 미실행 L2–L7 포함, 정확히 5 mm인 접촉,
수치적으로 아주 작은 음수 바닥 높이의 네 경우다. 모두 통과해야 한다.
이 테스트와 실제 공개 인수의 정상 10건을 구분해 확인했다. 가장 직접적인 부당
탈락은 **R1의 실제 기록 양식 불일치**, 등록 규칙을 벗어나는 집계는 **R2**다.
missing evidence를 무조건 PASS로 고치라는 제안은 아니다.

새 파일은 **27개 테스트**다. 이 중 **7개 전체 false-PASS 반례**, **2개 등록 규칙
불일치**, **4개 recorder 필수 필드 부재**만 `strict=True, raises=AssertionError`로
xfail을 붙였다. 서로 다른 버그 13개라는 뜻은 아니다. 나머지 14개는 정상 양성 대조,
이전 지적 일반화, 전체 전이표, 손상 입력의 반환 상태다.

관련 전체 **337 passed, 13 xfailed**(기존 323 + 새 정상 검사 14 + 새 반례 13)를
직접 확인했다. 10,000개 생성 검사도 이 실행에 포함된다. xfail을 해제한 실행은
**13 failed, 14 deselected**이며 모두 위 기대값의 실제 AssertionError다.
import 오류·예상 밖 예외를 xfail로 숨기지 않았다. `git diff --check`와 검사 전후
소스 해시 동일성도 확인했다. 전체 저장소 CI 통과나 분류기 승인을 뜻하지 않는다.
최종 로그는 [검증 기록](analysis/review_299c_validation/)에 보존한다.

```sh
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_v6h_classify_placements.py tests/test_classify_review_299.py \
  tests/test_classify_review_299b.py tests/test_v6h_classifier_properties.py \
  tests/test_ci_sharding.py tests/test_chain_analysis_hard_limit.py \
  tests/test_pair_chain_probe.py tests/test_b_v6h_gain.py tests/test_classify_review_299c.py

PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q -p no:cacheprovider \
  --runxfail -m xfail tests/test_classify_review_299c.py

PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-pair-v6h-carry/analysis/review_299c_validation/audit_recorder.py \
  --output /tmp/review299c-recorder-NEW.json
```

이전 worktree의 CONTRIBUTING은 모든 pytest의 호스트 잠금을 요구했지만, 최신
main의 #328 (`17be518e`, 2026-09-30 14:07:12 UTC 병합)은 오프라인 시험을
잠금 없이 실행하도록 바꿨다. 최신 규칙에 따라 단일 스레드 JSON/수치 시험만 수행했고,
다른 작업의 잠금·프로세스는 변경하지 않았다. 검사 전후 소스 해시와 명령은
`provenance.json`에 기록했다.

기존 308건 전체의 재변환은 이번 범위가 아니다. 공개 acceptance 원본 36파일은
검사 후에도 해시가 일치한다. 새 물리·학습·평가 코호트를 만들지 않았으므로
TensorBoard 재변환이나 viewer 실행 없이 기존 snapshot을 보존했다.
새 테스트는 명시한 명령으로 실행하고, 공용 CI 목록·분류기·등록·제어기를 변경하지 않는다.
원본은 로컬 보관이며 작은 감사 기록의 push를 raw 원격 백업으로 표현하지 않는다.
Drive 작업, PR 병합, 기본 checkout 갱신도 하지 않는다.
리뷰 브랜치의 push는 `[skip ci]`로 광범위한 자동 물리/SIM workflow를 시작하지 않는다.
pytest 원 로그는 `outputs/review-299c-astra-f32d5fd9/`에 보존했고, 커밋한 로그에서는
행 끝 공백만 제거했다. 양쪽 해시는 `provenance.json`에 있다.
