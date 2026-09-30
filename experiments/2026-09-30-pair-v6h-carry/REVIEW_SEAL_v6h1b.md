# b-v6h1 봉인 P1 수정 독립 재검토

**판정: SEAL OK.** 앞선 `77b6b94c`의 P1 두 반례가 새 입력 검사에서 올바른 이유로 차단된다. 검사를 제거하면 같은 합성 자료가 다시 잘못된 PASS를 내며 두 회귀 검사가 실패한다. 이번 수정 범위에서 개봉 전에 고칠 P0/P1/P2는 발견하지 못했다. 실제 inventory와 raw의 일치, 코호트 결과, 물리 성공을 확인한 판정은 아니다. 개봉·병합은 수행하지 않았다.

- PR #292 delta: `266118d2c2337bbf1cff507690da131c63e2db11` → `9e13c76b0ead36ace257e05cab7cb5e60d42df72`.
- 새 분석 봉인: `5be4330eca9b23d2cbde3657dcbb215ee1923b25`; 실행 기준: `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`.
- 메타데이터는 허용된 `e78ef70f`의 RUN_MANIFEST·plan·placements와 `0b77ae4b`의 pointer·generator·driver·build_plan Git blob만 대조했다. 실제 raw 및 실제 inventory의 목록·내용·해시는 접근하지 않았다.
- 대상은 `git archive origin/codex/pair-v6h-register | tar -x -C <scratch>`로 추출했다. Git 객체 검사용으로 scratch 안에 별도 `.git`과 원본 objects를 읽는 alternates를 만들었고 HEAD를 대상 SHA로 고정했다. 공유 저장소 설정이나 구현 파일은 바꾸지 않았다.

| 요청 항목 | 독립 검증 결과 |
|---|---|
| (a) 고정값 | 새 봉인의 inventory SHA-256은 `d7ceca9824d4098956c7bfc5cbd7298ee5b0cfa5dacdb12586d07c2ee07ec03f`, 파일 수 104415, 총 1916385247 bytes. RUN_MANIFEST의 기존 raw manifest 해시는 `07f623b7b30374da25cd0a8d2df62a70bbfdcae47b80279be6e310d7def27950` 그대로다. Git 메타데이터의 일치 검사이며 실제 inventory 재해시는 하지 않았다. |
| (b) 필수 검사 | `apply_sealed_analysis.py:55–130`에서 inventory 바이트 해시→schema/raw 경로→집계/entry 검사→RUN_MANIFEST→raw manifest 두 해시 확인 후 classifier를 호출한다. 모든 소비 입력의 미등록·누락·변경을 차단하고 `INVALID / NOT_ANALYSED`만 반환한다. CLI는 종료 코드 2, classifier 파일·gate summary 없음까지 합성 검사했다. |
| (c) 두 반례·변이 | 정상 자료 PASS 후 inventory를 삭제하면 `MISSING_EVIDENCE`; B가 FAIL인 자료에서 PF x만 1→0으로 바꾸면 첫 trace의 `ACQUISITION_HASH_MISMATCH`. manifest·inventory·plan·cases·72개 commands의 해시는 그대로 유지했다. 검사 제거 변이는 두 경우 모두 PASS를 내며 정확히 마지막 무결성 assertion에서 실패했다. |
| (d) 보존·재현 | 기존 prereg 및 `analysis/seal/` 19개 파일은 바이트 동일. 실행 pin 274개는 기존 봉인과 같으며 `4c6b439f` Git 객체의 SHA-256/Git blob SHA와 모두 일치. 분석 pin 293개도 **`5be4330e` Git 객체**에서 두 해시를 재계산해 전부 일치. `build()`의 60+12 사례 literal JSON 해시는 `f476c3d3103daa86fcab4553e9e2cfaf3b0abf500b71b6151554de7cbd2a4269`로 committed plan과 같다. |
| (e) 시점·mtime 공개 | `REGISTRATION_PLAN.md:7–15` 및 `seal_v2/disclosure.json`은 기록 후·개봉 전 생성임을 밝히며 기록 당시 바이트의 소급 증명을 부인한다. pointer의 최대 +0.1016초는 별도 진술이고 generator의 late counter 기준은 +1.0초다. +0.11초 근거와 혼동하지 않는다. mtime·집계 및 결과를 보지 않았다는 진술 자체를 독립 검증한 것으로 확대하지 않는다. |
| (f) 개봉 명령 | `REGISTRATION_PLAN.md:46,52,59–64`의 seal commit은 `5be4330e`, prereg는 `analysis/seal_v2/prereg_v6h.json`, inventory는 지정된 `…-inventory/acquisition_inventory.json`이다. **봉인 commit의 작업 경로에서 실행**하도록 명시한다. HEAD 문서 변경을 허용한다는 뜻으로 분석 pin 검사를 생략하지 않는다. 실제 명령은 실행하지 않았다. |
| (g) generator 호환 | 허용된 generator blob의 SHA-256 `cf7c618c1bcc43c8e737690c6e6b186a217aa5843f7431f439bec4e2ff6452c4`를 확인하고 그 바이트를 그대로 compile/exec했다. 첫 I/O 직전 RAW/OUT 전역값만 합성 경로로 바꿨다. generator가 실제 생성한 읽기 전용 inventory로 정상 분석·두 반례·두 변이를 검증했다. 작성자의 모사 fixture만으로 형식 일치를 추정하지 않았다. |

## 파일 읽기 경로 추적

위치 기준은 새 봉인 및 대상 HEAD의 동일한 분석 코드다.

- `apply_sealed_analysis.py:115–125`: inventory와 외부 RUN_MANIFEST를 신뢰 기준으로 검사한 후 raw `manifest.json`을 inventory 및 기존 RUN_MANIFEST 양쪽 해시와 대조한다.
- `classify_placements.py:1173–1203,1299–1315,1355–1359`: 주입된 reader로 cases, plan, 각 result/trace/case/commands를 읽는다. 미등록 시도의 result/trace도 같은 reader다. `EvidenceReader.read:1127–1155`가 읽은 정확한 바이트를 해시하고 파싱한 다음 `AcquisitionReader.read:89–102`가 원래 inventory 해시를 대조해야 호출자에게 반환된다.
- `recorder_v4c6b.py`는 전달받은 객체와 command 해시만 검사한다. 파일을 열지 않는다. gate의 summarize/summarize_sigma, `chain_analysis`의 hard_limit_violated/contacts_in/wilson, `gain_cohort_analysis.signed_error`, `pair_chain_probe`의 leg 함수들도 객체 계산이다. `door_relax_analysis.case_dir`는 경로 문자열 조합이다.
- 별도 historical CLI 및 `load_sealed_manifest`의 파일 읽기는 이 sealed entry point에서 호출되지 않는다. chain/gain 분석기의 독립 `analyse()`에 있는 직접 open도 호출하지 않는다. import 때 읽는 정적 지도와 분류기 source 해시는 저장소 분석 pin 대상이다.
- `EvidenceReader.verify:1157–1168`의 재해시는 이미 검증한 바이트의 중간 변경을 잡는다. classifier 종료, gate 직전, gate 직후에 수행되므로 중간 변경 시 report와 판정을 모두 버린다.
- 정확한 generator의 정상 72-case 합성 입력에서 Python audit로 실제 raw open을 추적했다. 고유 파일 **291개 = raw manifest/plan/cases 3개 + 72×4**, 모두 reader의 `read` 또는 `verify` 안에서 열렸고 inventory/report 해시 목록에 있었다. 우회 open 0개. 이는 이 봉인 경로의 정적 추적과 합성 실행 확인이며 임의 외부 호출자의 안전성 보증으로 확대하지 않는다.

## 검증 기록

기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 사용했다. 물리·렌더·모델·네트워크 실행은 없고 공용 lock을 잡지 않았다. 테스트 로그와 JUnit, Git 검증 요약은 [analysis/review_seal_v6h1b/](analysis/review_seal_v6h1b/)에 있다.

- 독립 재검사: **4 passed, 2 xfailed**. 두 xfail은 `strict=True, raises=AssertionError`인 **검사 제거 변이**다. 수정본 두 반례는 일반 PASS다. 준비 오류와 예상 외 mutant 동작은 `pytest.fail`로 처리하여 xfail로 숨기지 않는다.
- `--runxfail -k remove-check`: **정확히 2 failed**, 모두 `removed acquisition check emitted PASS_A_B_SAFETY` assertion. 변이가 살아남거나 import/준비 오류로 실패한 것이 아니다.
- 관련 회귀: **736 passed, 10 xfailed**. acquisition reader·기존 두 반례·봉인·source pinning·v6h·classifier·recorder·blinded manifest·299–299g 검사다. 10 xfail은 과거 `58dc07e7`의 기존 299d 반례이며 이번 수정본 실패가 아니다. 최초 실행 한 번의 집계이고 독립 검사 4개와 합산하지 않았다.
- 새 봉인 CLI 감사: 실행 274개·분석 293개·사례 72개, `outcomes_read=false`.

독립 테스트 초기 실행에는 검토 도구 자체의 오류가 있었다. 보존 파일 수를 7개로 잘못 기대한 검사 1건과, generator의 첫 I/O 줄을 한 줄 늦게 지정한 준비 실패 5건이다. 후자는 기존 실제 inventory 폴더에 `os.makedirs(..., exist_ok=False)`를 호출하여 **5건 모두 FileExistsError로 종료**했다. 파일 열기·목록 조회·해시 계산·생성/변경은 없었다. 이를 성공 검사에 합산하지 않고 `independent_initial.*`에 보존했다. 첫 I/O 위치를 AST에서 찾도록 고치고, 실제 경로의 mkdir/open/list/scandir/remove/chmod를 호출 전에 막는 guard를 추가했다. 수정한 검토 도구로 위 전체 독립 검사를 재실행했다. 최종 검사 guard의 블라인드 읽기·물리·렌더·모델·네트워크 시도는 모두 0이다.

재실행은 대상 archive에 이 리뷰의 `tests/test_review_seal_v6h1b.py`를 복사한 뒤 다음과 같이 한다. Git 관련 검사를 위해 archive의 별도 Git HEAD와 객체 접근을 위 설명대로 설정한다.

```sh
V6H_FIX_ARCHIVE=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -B -m pytest -q -rx \
  -p tests.pose_provider_no_physics -p tests.v6h_seal_offline_guard \
  tests/test_review_seal_v6h1b.py
# 변이의 실제 실패 확인: 위 명령에 --runxfail -k remove-check 추가
```

변경은 리뷰·독립 테스트·검증 기록뿐이다. `.github/workflows`, 구현, 기존 봉인, raw는 변경하지 않았다. scratch archive는 검사 종료 후 삭제하고 부재를 확인했다([cleanup.json](analysis/review_seal_v6h1b/cleanup.json)). 새 실험 결과가 없으므로 TensorBoard를 변환/표시하지 않았고 UGRP의 Google Drive 제외 규칙을 지켰다. #292에 한 번의 한국어 댓글로 전달한다.
