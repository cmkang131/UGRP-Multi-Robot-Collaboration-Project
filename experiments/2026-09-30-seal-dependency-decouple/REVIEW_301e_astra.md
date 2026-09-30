# PR #301 두 P2 수정의 독립 재현성 검사

검토일: 2026-10-01 KST. 검토 대상은
**`52d2d994295894cdf68de5d22b880822c8a2348c`**, 비교 대상은
`b7f53d34e56407d64aea5ef74e41a07b46706911`이다.
검토 브랜치 `codex/review-301d`의 기존 `c463b667` 위에 기록만 추가한다.

판정: **MERGE** — [301d 검토](REVIEW_301d_astra.md)의 **D1·D2 P2 두 건은
수정됐다.** 원래 반례 3개가 같은 단언으로 통과하고, 해당 수정 기능을 제거하면
대응 단언에서 다시 실패한다. 이번 좁은 변경 범위에서 남은 P0/P1/P2는 없다.
이 판정은 명시적으로 선택하는 오프라인 Python 재현성 검사 도구의 병합에 한정된다.
물리 실행이나 #292 봉인 승인을 뜻하지 않으며 이 검토 작업에서는 병합하지 않는다.

## 변경과 반례의 재현성 검사

`git fetch origin`, `git diff b7f53d34 52d2d994`,
`git archive origin/codex/seal-dependency-decouple`로 원격 head와 추출 소스를 확인했다.
두 커밋 사이의 main 병합 `c8e3fe06`과 실제 수정 커밋 `52d2d994`를 구분했다.
main에서 병합된 별도 기능의 설계는 다시 검토하지 않았다.

| 항목 | 확인한 수정과 재현성 검사 |
|---|---|
| **D1 — CLI 자체 출력 때문에 첫 재실행 거부** | `scripts/trace_execution_dependencies.py:33-37`이 성공 봉인과 실패 보고서의 정확한 경로를 추적 전에 선언한다. `harness/runtime_provenance.py:108-140,241-276,301-315`가 경로·실제 대상·링크를 digest에 넣고 디렉터리 snapshot에서 해당 출력만 제외한다. `:441-462,532-533`은 자식의 목록에도 같은 제외를 적용한다. 원래 root 안 출력 반례와 root 밖 대조군 모두 STOP을 관측했다. |
| **D2 — 환경 복사 API 누락** | `harness/runtime_provenance.py:323-346`의 `copy()`는 `dict(self)`로 기존 읽기 hook을 거친다. 문자열·bytes의 직접 Python 실행과 trace/run이 모두 STOP을 관측하고, 복사한 설정을 MOVE로 바꾸면 환경 변경 때문에 거부된다. 독립 dict의 변경은 원래 환경에 영향을 주지 않는다. |

검토 원본 `c463b667`과 수정본의 `test_seal_v2_review_301d.py`를 비교했다.
함수·클래스 **16개의 본문 AST가 동일**하며 변경은 설명과 세 xfail 표시 제거뿐이다.
반례를 약하게 바꾸거나 다른 실패를 통과로 처리하지 않았다.

새 테스트는 root 안 출력 1개, 문자열/bytes 환경 복사 2개를 모두 일반 통과로 요구한다.
별도 격리 복사본에서 **원래 b7f53d34의 runtime·CLI 두 파일만 복원**하면
**3 failed / 1 passed**다. D1은 `ReceiptInvalidatedBySaving`, D2는
`EnvironmentCopyRejected`에서 실패하고 root 밖 대조군은 통과한다.
수집·setup 오류나 xfail로 수정 효과를 대신하지 않았다.

## 수정의 일반화와 변이 재현성 검사

작성자 추가 검사 15개와 별도로, 독립 fixture **13사례**를 확인했다.

- 임의의 한글·공백 출력 이름, 상대 경로, symlink인 부모 경로의 CLI trace/run 3사례.
  문자열 listdir·bytes scandir의 입력 목록이 출력 저장 전후 같고, 실패 보고서를
  나중에 생성해도 같다. 같은 CLI로 재저장하면 기존 봉인을 덮어쓰지 않는다.
- 정적 source와 출력의 겸용은 거부한다. 출력 예약이 없는 직접 API는
  `runtime-seal.json`이라는 이름도 일반 디렉터리 변경으로 계속 검사한다.
- 문자열/bytes × abort/warn × 복사한 미사용 항목의 값 변경/삭제 8사례.
  한글 값도 hash로 기록되고, 복사만 했던 항목의 변경을 entry 실행 전에 검출한다.
  abort는 STOP 전에 거부하고 warn은 명시한 경고와 함께 STOP을 관측한다.

독립 fixture 첫 실행은 **12 passed / 1 failed**였다. 실패는 검사 코드가
`os.listdir(".")`의 오류 경로를 `<root>`로 기대했지만 실제로는 사용한 경로
`<root>/.`를 보존하기 때문이었다. 거부 자체는 정확했다. 이 문자열 기대값만
고친 해당 1개는 **1 passed / 12 deselected**다. 최초 로그와 수정 내역을 모두
보존하며 저장소 수정이나 제품 결함 수정으로 세지 않는다.

변이는 작성자 스크립트의 이번 수정에 해당하는 5종만 골라 별도 소스 복사본에서
독립 실행했다. 정상 대조군은 **14 passed**, 변이는 **5/5 검출**이다.

| 제거한 기능 | 의도한 실패 |
|---|---|
| 출력 경로 예약 | root 안 출력 반례 1개 실패, root 밖 대조군 1개 통과; 원래 `ReceiptInvalidatedBySaving` 재현 |
| 자식 목록에서 출력 제외 | listdir/scandir/Path의 문자열·bytes 열거 6개가 저장 뒤 출력 노출 때문에 실패 |
| 출력을 입력으로 읽는 것 차단 | 직접 읽기·symlink 읽기 2개에서 기대한 `TraceFailure`가 발생하지 않아 실패 |
| 환경 `copy()` API | 문자열·bytes 2개에서 원래 `EnvironmentCopyRejected` 재현 |
| 복사 시 읽기 hook | 문자열·bytes 2개에서 기록한 키 집합이 비어 있어 단언 실패 |

변이 JUnit의 실패 본문까지 확인했다. 오류·skip은 0이며 정상 대조군·변이·수정 전
재현의 반복 수를 아래 관련 회귀 통과 수에 더하지 않는다.

## 관련 회귀와 보존 재현성 검사

관련 **15개 suite: 426 passed / 13 strict xfailed**, 857.54초.
실패·오류·일반 skip·deselect는 0이며 전체 저장소 회귀 통과를 뜻하지 않는다.

| 재현성 검사 | 이번 결과 |
|---|---|
| 기존 관련 13개 suite | **401 passed / 13 strict xfailed** |
| 301d 원본 반례·대조군 | **10 passed**; 기존 반례 3개 포함 |
| 작성자 출력·환경 복사 추가 검사 | **15 passed** |

13개 xfail은 수정하지 않은 301b 정적 API의 기존 한계이며 runtime 수정 통과로
합산하지 않았다. runtime 68개, 301c 14개, 등록/소스 봉인, bundle, CI 목록과
임시 잠금 단위 검사는 모두 통과했다. 이번 delta에서 바뀌지 않은
`test_ugrp_session.py`의 이전 Mac 권한 문제를 새로 검증했다고 주장하지 않는다.

별도로 대상 head의 기존 GitHub check **33/33 SUCCESS**와 draft·OPEN 상태를
조회했다(`github-checks.json`). 내가 새 CI를 시작한 결과나 로컬 통과 수로 세지 않는다.

기존 기준 `d17ca4345affef8cf027e121cf1f3197b36c23e0`, 이전 검토 head,
새 head의 Git blob과 실제 archive 파일을 대조했다.

- 등록 **5/5**, RGB JSON **65/65**, legacy source **6/6**,
  합계 **76/76 바이트 동일**.
- v6e `v6_contract.source_sha256` **85/85**가 새 Git blob과 archive 양쪽에서 일치.
- `.github/workflows`의 파일 목록과 모든 바이트가 확인한 origin/main
  `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`와 동일. workflow 편집 없음.
- 새 runtime 호출자는 기존처럼 새 CLI와 관련 재현성 검사뿐이다.
  이 수정이 기존 runner를 자동 전환하는 호출은 없다.

합의한 보수적 입력 묶음과 native/자식 전체 추적·metadata·동시 수정·불변 입력·
실제 runner 연결의 후속 범위를 다시 차단 사유로 삼지 않았다.
현재 검사는 그 후속 범위의 완전성을 입증하지 않는다.

## 재현 방법과 기록

기존 Mac Python 3.12.13·pytest 9.1.1 환경을 재사용했다. 공용 호스트 잠금은
사용하지 않았다. 잠금 관련 단위 검사는 임시 경로와 더미 Python 프로세스만 쓴다.
물리·렌더·모델 호출·학습을 시작하지 않은 로컬 오프라인 재현성 검사다.

```sh
review_scratch=$(mktemp -d /private/tmp/ugrp-review-301e.XXXXXX)
git archive origin/codex/seal-dependency-decouple | tar -x -C "$review_scratch"
# 역사 Git blob 조회용 객체 참조만 추가한다. 프로젝트 worktree를 만들지 않는다.
git clone --bare --shared --no-hardlinks /Users/changmin/projects/ugrp "$review_scratch/.git"
git --git-dir="$review_scratch/.git" config core.bare false
git --git-dir="$review_scratch/.git" update-ref refs/heads/review-snapshot 52d2d994295894cdf68de5d22b880822c8a2348c
git --git-dir="$review_scratch/.git" symbolic-ref HEAD refs/heads/review-snapshot
git --git-dir="$review_scratch/.git" update-ref refs/remotes/origin/main 394f9cda5d67a9d1b94ad1688f39f5616fc00e7b
cd "$review_scratch"
export PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1
review_python=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$review_python" -m pytest -q -rx --tb=short -p no:cacheprovider \
  tests/test_seal_v2_review_301d.py tests/test_seal_runtime_outputs.py \
  tests/test_seal_runtime_provenance.py tests/test_execution_dependency_contract.py \
  tests/test_seal_v2_review_301.py tests/test_seal_v2_fail_closed.py \
  tests/test_seal_v2_review_301b.py tests/test_seal_v2_review_301c.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_pair_v6.py tests/test_rgb_execution_bundle.py \
  tests/test_ci_sharding.py tests/test_ci_host_lock.py tests/test_agent_lock.py
```

원본 로그·JUnit·독립 fixture·변이 드라이버·보존 감사는
`/Users/changmin/projects/ugrp/outputs/review-301e-52d2d994-20261001/`에 보존한다.
`run_delta_mutations.py <archive> <새 결과 경로>`가 변이 5종과 수정 전 재현을 실행한다.
`test_review_301e_generalization.py`는 archive에서 `PYTHONPATH=.:tests`로 직접 pytest 실행한다.
`check_preservation.py <archive> <결과 경로>`는 76개 파일·85개 hash·검토 AST·workflow를 대조한다.
이는 로컬 raw 보관이며 원격 백업이 아니다. 보고서만 검토 브랜치에 커밋·push한다.
연구 실행 결과가 없어 TensorBoard 변환·서버 작업은 없고, UGRP 예외에 따라 Drive 작업도 없다.

검사 종료 뒤 PR 변경 파일 **30/30**의 archive 바이트가 대상 Git blob과 같은 것을
다시 확인했다. 실제 임시 경로 `/private/tmp/ugrp-review-301e.s9TxeH`와 그 안의
임시 fixture·Git 객체 참조는 삭제했고, 경로가 없는 것도 확인했다.
변이용 임시 소스 복사본은 각 검사가 끝날 때 자동 정리됐다.

`evidence.json`에는 suite별 결과와 원본 33개 파일의 크기·SHA-256을 기록했다.

| 증거 파일 | SHA-256 |
|---|---|
| `evidence.json` | `93eb494e6cdcaac0ed8fd2dccb83a24f808650369cd733e96239e1c22f94fdb6` |
| `related.log` | `cac61eb4241394ca6d84d1b53e8cbc5574c10c1c1c4d64913b516f85c6c93ea3` |
| `related.xml` | `62b162f1b4b791a3474b3e076844dbf42d5408c498b119cc939384fff1d212a7` |
| `mutations/summary.json` | `52f7855ce425877c18693f04e4fabf8e8f8a6f33a1feb62520f552f5cd88239a` |
| `mutation-failures.json` | `fd6c54268e267d17aea2ff0a73056d10e3884ab0c72de284fad02416a8735292` |
| `generalization.xml` | `03aaa75b73d35928473cd69e9008d74a0f657751851ed3d8138908257e25a07e` |
| `generalization-corrected.xml` | `cc58a99dc05b92e659ed8a9cea747420f99f4c01db22a48d9857f768fa468cf6` |
| `harness-correction.json` | `5cfa2e157f7a144a7cdfc2b63cb45466b066e81fe0703400e09e5b4ca7af2053` |
| `preservation.json` | `e636bec2bbcddd61313fc44789d7f8f8ac079b6d5c814f197c351656e1620ec5` |
| `post-test-source-check.json` | `739172b7088d9ab7d5df10a7fb7c2d9b17449b0b1457fef70155617a4673b9f4` |
| `cleanup.json` | `d2e0e865de6064a9f3a39fb1cfc65c965637350609ad04948312bcc7151aef95` |
