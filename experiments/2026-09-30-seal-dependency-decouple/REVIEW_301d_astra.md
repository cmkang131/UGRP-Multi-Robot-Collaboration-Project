# PR #301 네 번째 독립 검토 — 301c 이후 차이

검토일: 2026-10-01 KST. 대상 **`b7f53d34e56407d64aea5ef74e41a07b46706911`**,
검토 브랜치 `codex/review-301d`, 시작 main `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`.
301·301b·301c 원본 검토와
[301b 답변](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/301#issuecomment-5913785558),
[301c 답변](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/301#issuecomment-5914624491)을 대조했다.
PR은 `git archive`로 추출하여 고정했고 물리·렌더·모델 호출·학습은 실행하지 않았다.

판정: **MERGE AFTER FIXES**. 301c의 경로 P1과 `__main__` P2는 수정됐으며,
이번에 확인한 일반화 사례에서도 통과했다. 새로 재현한 것은 정상 사용을 막는
**P2 두 건(D1·D2), strict xfail 세 사례**다. 지원 범위 안에서 변경된 파일을
그대로 받아들이는 새 P1은 이번 검사에서 발견하지 못했다. 완전성 증명이라는 뜻은 아니다.

**native/자식 추적과 실제 runner 연결을 후속으로 둔 범위는 병합 가능한 경계다.**
기존 경로에 자동 적용하지 않는 오프라인 개발 도구로 유지하고 아래 두 문제를 고친 뒤
병합할 수 있다. 이 판정은 #292 봉인 승인·물리 실행 허가·전체 OS 재현성 보장이 아니다.
이번 검토에서는 병합하지 않는다.

## 새 지적 한 묶음

### D1 — P2: CLI가 저장한 봉인 파일 때문에 첫 재실행이 실패한다

위치: **`scripts/trace_execution_dependencies.py:43-46`**,
연관 검사 `harness/runtime_provenance.py:280-282`.

```python
# entry.py
import helper
# helper.py
COMMAND = "STOP"
```

root 안에 `static.json`·`cases.json`을 준비한 뒤 문서의 trace/run 절차처럼
`--output <root>/runtime-seal.json`으로 저장한다. 로컬 helper를 찾는 표준 import가
root를 열거하므로 `directories[root]`에는 저장 전 이름 목록이 들어간다.
trace는 성공(code 0)하고 digest를 반환하지만, CLI가 그 뒤 새 파일을 추가한다.
소스·입력·설정에 아무 편집을 하지 않은 첫 `run`은 다음처럼 거부된다.

```text
HOST_ERROR / seal-violation / sealed directory drift: <root>
```

봉인 파일만 root 밖으로 옮기면 **같은 receipt·같은 외부 digest**로 STOP이 통과한다.
처음부터 출력 파일을 root 밖에 저장한 독립 대조군도 통과한다. 현재 CLI 왕복 검사는
이미 bootstrap된 pathlib만 사용하므로 이 정상적인 로컬 import 조건을 검사하지 못했다.
디렉터리 목록을 보수적으로 봉인하는 합의는 유지할 수 있다. CLI가 출력 위치를 입력
snapshot과 분리하도록 안내·검사하고, 즉시 무효가 되는 봉인을 성공 결과로 내보내지 않아야 한다.
정책이 출력 위치를 제한하는 방식이라면 그 거부와 문서 예제도 함께 검증해야 한다.

재현: `test_cli_receipt_save_and_first_run[output-inside-root]` **strict xfail 1개**.
`output-outside-root-control`은 통과. `raises=ReceiptInvalidatedBySaving`으로
정확한 오류와 출력 이동 후 정상 실행을 확인한 경우만 예상 실패로 센다.

### D2 — P2: 읽기 전용 환경 복사에서 정상 Python 코드가 실패한다

위치: **`harness/runtime_provenance.py:295-314`**, 교체 지점 `:446-447`.

```python
command = os.environ.copy()["REVIEW_MODE"]
# 또는 os.environb.copy()[b"REVIEW_MODE"].decode()
```

같은 Python·`-I -S -B`·cwd·명시 환경 `REVIEW_MODE=STOP`으로 직접 실행하면 둘 다
STOP을 읽고 종료한다. 추적기에서는 `_Environment`가 `Mapping`의 세 기본 메서드만
구현하고 `.copy()`를 제공하지 않아 **`canonical-case-failed / AttributeError`**가 된다.
파일 쓰기·환경 변경·adapter 우회·native getenv를 쓰지 않는 정상 읽기다.

`dict(os.environ)` 대조군은 정상 추적·실행되고 STOP→MOVE 변경도 거부한다.
환경 읽기를 기록하면서 Python 환경 객체의 읽기 전용 복사 API를 보존해야 한다.
수정 후에는 문자열·bytes 복사 각각의 정상 실행과 복사한 설정의 변경 검출을 확인해야 한다.

재현: `test_readonly_environment_copy_keeps_python_semantics[environ/environb]`
**strict xfail 2개**. 직접 실행 통과·정확한 AttributeError·adapter의 copy 부재를
확인한 뒤에만 `EnvironmentCopyRejected`를 발생시킨다.

## 이전 지적과 수정의 일반화

| 대상 | 독립 확인 |
|---|---|
| 301c C1 경로 식별·과잉 차단 | 기존 `open`/Path/os.open·링크 변경·무관 파일 대조군 모두 통과. 새로 **절대 symlink target 안의 상대 링크와 `..`**을 조합해 실제 바이트 변경 및 같은 최종 대상을 유지한 중간 링크 변경을 검사했다. 둘 다 `_child` 호출 전에 거부했다. |
| 같은 대상의 경로 표기 | 기존 `./`·`..` 동등 표기 허용 검사 통과. 추가로 바이트와 실제 대상은 같지만 **봉인하지 않은 symlink를 새로 사용하는 표기**는 실제 read 전에 거부한다. 대상 비교가 링크 검사까지 생략하지 않는다. |
| 301c C2 `__main__` | 원래 자기 import·pickle 2개와 종료 콜백 검사 통과. 추가한 dataclass 정의·pickle 왕복·종료 콜백의 전역 공간 일치도 직접 Python 실행과 canonical/sealed 실행 모두 통과했다. |
| 301c B1 디렉터리 조회 | 이름 추가·삭제·종류·링크·부재 변경과 읽지 않은 내용 변경 허용 검사 통과. 새 `view/../settings` 조회도 실제 디렉터리 변경을 자식 시작 전에 거부한다. D1은 이 검사와 CLI 출력 저장의 결합 문제다. |
| R1/R2/R3, 301b N1/N4/N6/N7 | wildcard·모듈 간 loader 재수출 4형태·표준 `importlib.__import__` 2형태·내부 링크 package·symlink script sibling 등 실제 import 접근을 기록한다. 301c의 두 모듈을 거친 재수출과 실행 전 변경 거부도 통과했다. 문법별 예외를 추가하는 방식으로 되돌아가지 않았다. |
| R4/R5/R6, 301b N2/N3/N5 | JSON 원본 바이트로 순서·Decimal·schema 부재/null을 구분하고, 실제 링크 binding과 표준 workflow 전체 유효성·공통 launcher를 검사한다. 기존 runtime의 해당 사례가 모두 통과했다. |
| 원래 B1/B2 경계 | Python이 실제 읽은 일반 자산·XML child·registry 참조는 whole-file로 포착한다. 미선언 자식은 거부한다. 환경은 worker에서 entry 실행 전에 검사하고, 파일·디렉터리는 부모의 `_child` 호출 전에도 검사한다. 설치 identity 변경 검사는 mock이며 실제 패키지 업그레이드 증거가 아니다. |

원래 301b의 새 7종 **12사례는 runtime 경로에서 모두 통과**한다.
원본 정적 API 검토 파일은 `origin/codex/review-301b`와 바이트 동일하며,
별도 결과 **14 passed / 13 strict xfailed**를 유지한다. 정적 v2 단독의 미해결 한계를
runtime 수정 성공으로 합산하지 않는다. 13개는 12사례와 기존 registry 참조 경계다.

301c 검토 파일은 원본에서 xfail helper/장식자를 제거한 것을 확인했다.
함수·클래스 **21개 AST를 비교**하여 본문·단언은 그대로임을 확인했고 **14/14 통과**했다.
새 파일·환경 읽기를 막는 기존 런타임 검사도 유지된다.

## 종료 확인과 세션 검사

`scripts/run_ci_tests.py:341-365`는 leader wait 뒤 실제 그룹 소멸을 최대 5초까지
확인하고, 확인되지 않으면 잠금을 유지한다. 가짜 시계의 지연된 소멸/끝내 미확인과
종료 코드 0/7 조합 **4/4 통과**를 독립 실행했다. 별도 임시 복사본에서 한 번만
조회하는 이전 방식으로 돌리면 **지연된 소멸 2개가 RuntimeError로 실패**, 미확인
2개는 계속 통과한다. 수집/setup 오류로 변이 검출을 대체하지 않았다.
정상 더미 프로세스 0/7 검사도 관련 suite에서 통과했다. 이 결과는 원래 일회 실패
순간의 OS errno를 확정하거나 모든 종료 지연이 5초 이내임을 보장하지 않는다.

요청한 `test_ugrp_session.py`를 이 Mac에서 다시 실행했으나 **7 passed / 6 failed**다.
별도의 최소 `/bin/ps` 호출도 `PermissionError: [Errno 1] Operation not permitted`다.
실패한 6개는 작성자 기록과 같다.

- `test_allow_low_disk_and_explicit_floor_override`: `/bin/ps` PermissionError.
- `test_immediate_success_does_not_race_session_setup`: 이번 실행에서는 3초 timeout.
- `test_stop_command_terminates_session`, `test_term_ignoring_child_is_killed_after_grace`,
  `test_wrapper_allows_child_to_write_result_after_sigint`,
  `test_wrapper_signal_cleans_up_child_process_group`: 세션 기록 대기 실패.

따라서 6개 모두에서 직접 PermissionError를 관측했다고 표현하지 않는다.
실행기·테스트 바이트는 대상 SHA와 같고 PR 변경 대상이 아니다. 현재 도구 권한으로는
`ps`가 허용된 Mac 재실행을 할 수 없으며, 제한을 우회하거나 성공으로 바꾸지 않았다.

보완 근거로 **동일 head SHA의 기존 Ubuntu CI**
[run 36738568597 / shard 5](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36738568597/job/109966830079)의
artifact `11110105223`(`offline-shard-5`, `shard-5.xml`)을 내려받아 확인했다.
세션 **13/13**, 위 6개 **6/6**, 종료/잠금 **24/24**가 실제 JUnit에서 passed다.
기존 CI 증거를 회수한 것이며 내가 새 Ubuntu 실행을 시작한 결과나 Mac의 통과로 세지 않는다.
CI checkout은 PR의 임시 병합 커밋 `76dc0bc2e7adca8f80ed2d0d12d9cbae74af0450`
(`b7f53d34` + main `394f9cda`)이다. 이를 fetch해 세션 실행기·세션/종료 테스트가
검토 head와 동일함을 확인했다. CI runner 목록에는 main에서 더해진 두 suite 차이가 있다.

## 보존·호출 경계

최초 기준 `d17ca4345affef8cf027e121cf1f3197b36c23e0`의 Git blob, 대상 Git blob,
추출한 실제 파일을 직접 비교했다. 등록 **5/5**, RGB JSON **65/65**, legacy source
**6/6**, 합계 **76/76 바이트 동일**이다. v6e의 `v6_contract.source_sha256`도
Git blob과 실제 파일 양쪽에서 **85/85 일치**한다.

`harness/ sim/ scripts/ config/ configs/` 호출자 검색상 새 정적 빌더와 runtime CLI만
명시적으로 이 경로를 사용한다. 기존 등록의 자동 v2 전환·기존 runner의 fallback·봉인
재작성은 발견하지 못했다. PR merge-base 대비 `.github/workflows` 변경도 없다.
검토 worktree에는 이 문서와 새 테스트만 추가한다.

전체 JSON read, 정적 wildcard subtree, 전체 설치 inventory, import가 조회한 디렉터리
목록을 보수적으로 묶는 설계는 이번 검토에서 다시 차단 사유로 삼지 않는다.
무관한 catalog 편집에 따른 재봉인 감소와 최소 의존성 집합은 여전히 보장하지 않는다.
읽지 않은 파일 내용·설정 변경을 허용하는 대조군은 통과한다.

native I/O·C getenv, OS 수준 자식 추적과 제한, stat/metadata·열거 순서, 동시 수정,
불변 입력 강제, custom import machinery·완전한 thread/subinterpreter 격리,
sim_cli/worker admission과 canonical 물리 trace는 후속 범위다. 실제 runner에 연결할 때
OS backend와 모든 자식의 제한을 별도로 인수해야 한다. 지금의 OK를 그 근거로 쓰면 안 된다.

## 재현·검증 기록

| 실행 | 이번 결과 |
|---|---|
| 관련 12개 suite | **394 passed / 13 strict xfailed / 1 deselected**, 556.57초 |
| 새 301d suite | **7 passed / 3 strict xfailed**, 18.35초 |
| 새 반례 `--runxfail` | **3 failed / 7 deselected**, 모두 D1/D2의 의도한 단언에서 실패 |
| session + agent_lock 별도 | **13 passed / 6 failed** = session 7/6, agent_lock 6/0 |
| 종료 확인 정상/단발 조회 변이 | **4 passed** / **2 passed + 2 failed**, 각각 20 deselected |

첫 관련 suite에서 임시 `git worktree add`를 수행하는 검사 하나는 사용자 범위를 지키기
위해 명시적으로 제외했다. 일반 skip·수집 오류·XPASS는 없다. 반복·변이·기존 CI를
위 통과 수에 더하지 않는다. xfail은 결함 재현이며 수정 완료가 아니다.

기존 Mac Python 3.12.13·pytest 9.1.1·macOS 27.2 arm64를 사용했다.
NumPy 2.5.2·MuJoCo 3.12.0은 metadata 조회값이며 엔진을 실행하지 않았다.
공용 호스트 잠금은 사용하지 않았다. 잠금 단위 검사는 임시 경로와 더미 Python만 사용한다.

```sh
review_scratch=$(mktemp -d /private/tmp/ugrp-review-301d.XXXXXX)
git archive b7f53d34e56407d64aea5ef74e41a07b46706911 | tar -x -C "$review_scratch"
# 역사 blob을 읽는 검사만을 위한 독립 Git 객체 참조; 프로젝트 worktree 추가 없음
git clone --bare --shared --no-hardlinks /Users/changmin/projects/ugrp "$review_scratch/.git"
git --git-dir="$review_scratch/.git" config core.bare false
git --git-dir="$review_scratch/.git" update-ref refs/heads/review-snapshot b7f53d34e56407d64aea5ef74e41a07b46706911
git --git-dir="$review_scratch/.git" symbolic-ref HEAD refs/heads/review-snapshot
cp tests/test_seal_v2_review_301d.py "$review_scratch/tests/"
cd "$review_scratch"
export PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1
review_python=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$review_python" -m pytest -q -rx \
  tests/test_seal_runtime_provenance.py tests/test_execution_dependency_contract.py \
  tests/test_seal_v2_review_301.py tests/test_seal_v2_review_301b.py \
  tests/test_seal_v2_review_301c.py tests/test_seal_v2_fail_closed.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_pair_v6.py tests/test_rgb_execution_bundle.py \
  tests/test_ci_sharding.py tests/test_ci_host_lock.py \
  --deselect=tests/test_ci_host_lock.py::test_linked_worktrees_share_primary_lock_but_other_clones_do_not
"$review_python" -m pytest -q -rx tests/test_seal_v2_review_301d.py
"$review_python" -m pytest -q --runxfail --tb=short tests/test_seal_v2_review_301d.py \
  -k 'output-inside-root or readonly_environment_copy_keeps'
"$review_python" -m pytest -q --tb=short tests/test_ugrp_session.py tests/test_agent_lock.py
```

실제 scratch: `/private/tmp/ugrp-review-301d.WAh3sZ`.
로그·JUnit·환경/보존 감사·변이 스크립트·CI artifact는
`/Users/changmin/projects/ugrp/outputs/review-301d-b7f53d34-20261001/`에 보존한다.
raw는 로컬 보관이며 보고서·테스트의 GitHub push와 구분한다. 새 검토 파일은 기존 CI
목록을 수정하지 않았으므로 위 명시적 명령으로 실행한다. 연구 실험 결과가 없어
TensorBoard 변환·서버 작업은 없고, UGRP 예외에 따라 Drive 작업도 없다.
검사 후 PR 변경 파일 26개의 추출본이 대상 Git blob과 그대로 같은 것도 확인했다.

| 증거 파일 | SHA-256 |
|---|---|
| `test_seal_v2_review_301d.py` | `15d8c9e3e1dacad974a5134228f104f4ddd167219d1d58bdaf60c7b7581605cc` |
| `baseline.log` | `7ae4357a720f06f950a7c2a4096d2ebc53098ae5c8376bc05ab1137539a23528` |
| `baseline.xml` | `a6db1b4833f21f6a010629875e0ae143d4bd12f88ef0878b5ba43c034c3389c8` |
| `review.log` | `2960cb07917b9a2b95d25ed2c7a1ef9be937f8e6d78a0af65d9f98596f34a9d9` |
| `review.xml` | `e6b7579fb5e2c9b7ff2c5d4041390002d9d9d2ac9660d22ee8e26bebb88f321f` |
| `counterexamples.log` | `404879f04dce8393fd625bc8214577171589aecd2f5c735320529e39a65c3b0e` |
| `session.log` | `db35e8eccde83903d3c26cc02ed9bd1de2b8fb342a098c945d66c9e090454d3a` |
| `session.xml` | `18518f5f3d5743aed31ede859ccfd42bdf49beb4489b8ae0d139ef1b4a45a114` |
| `cleanup-control.log` | `0380c6f725b77cb3d682f5c2c63892abaadecc75c046b1406173c902edc8ae24` |
| `cleanup-one-probe-mutant.log` | `cbb5c010014bfbd5b52c5e9d9862384bf761af39bbc19d385384c3cbb5ea7c08` |
| `preservation.json` | `26edb811d2168e3fc16daa14955a84aa4d820cbdbb3fea53fde261fbe10be92e` |
| `review-301c-ast.json` | `5b824129582f2353464f98d27dff018225d665382871d0061719f3cee6fec8b0` |
| `archived-source-check.json` | `3fb37c5fbd386ab311483231bfc8594296c0dd791b0c29f8029eb3b60f5c8302` |
| `ci-offline-shard-5.zip` | `63f6df8e124f5cf3f7bcfeada59a2cefc8f15a290c12a15c63b73e061f34b3f2` |
| `ci-run.json` | `ba23bb47f7b2c601054b5c49e971016e81f348c97d2dfe1eb419585bb9df54a0` |
| `ci-session-checks.json` | `0db90a19e1213ff9ec72400c86b544e70aaeaffa14e09b440ea878f35fb9a834` |
