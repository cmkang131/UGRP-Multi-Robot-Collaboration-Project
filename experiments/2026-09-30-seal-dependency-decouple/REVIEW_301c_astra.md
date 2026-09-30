# PR #301 독립 검토 — runtime provenance

검토일: 2026-09-30~2026-10-01 KST. 대상은 **`cea627c539873b60775db6df146254ab077cec0c`**,
검토 브랜치는 `codex/review-301c`다. 첫 검토 `d21e0147fbc0829da3c9878877b4c5f5c83f865f`,
두 번째 검토 `13afa3dc04fa15630248716b580d776a7e6cb1d7`,
[작성자 답변](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/301#issuecomment-5913785558)과
`docs/runtime_provenance.md`를 대조했다. PR 소스는 `git archive`로 추출해 고정했다.

판정: **BLOCK**. 새 경로는 예전 정적 분석의 12개 반례를 실제 파일 읽기로 포착한다.
하지만 지원한다고 한 일반 Python 파일 읽기에서도 **실제로 읽은 파일 대신 다른 파일을
봉인하는 P1 결함 C1**이 남는다. 정상 스크립트의 `__main__`을 잘못 구성하는 **P2 C2**도
재현했다. 아래 두 건을 한 묶음으로 수정·재검토하기 전에는 현재 후보의 병합을 권하지 않는다.

**native/자식 추적과 실제 runner 연결을 다음 작업으로 미룬 것 자체는 차단 사유가 아니다.**
기존 실행기와 분리된 opt-in 오프라인 도구로 한정해 병합하는 설계는 가능하다.
다만 C1/C2는 그 좁힌 범위 안의 문제다. 현재 도구의 `OK`를 전체 재현성 보장,
#292 봉인 승인 또는 물리 실행 허가로 사용해서는 안 된다.

## C1 — P1: symlink 뒤의 `..`을 먼저 없애 실제 입력을 누락

위치: `harness/runtime_provenance.py:43-50`, `:275-286`.
`file_state`의 45행과 `_Audit.read`의 278행이 모두 `os.path.abspath`를 사용한다.
이 함수는 symlink를 따라가기 전에 `..`을 문자열 수준에서 정리한다. 운영체제의
파일 열기는 symlink를 먼저 따라간 뒤 상위 디렉터리로 이동하므로 두 경로의 의미가 다르다.
[Python 공식 경로 문서](https://docs.python.org/3.12/library/os.path.html#os.path.normpath)도
이 정리가 symlink를 포함한 경로의 의미를 바꿀 수 있다고 설명한다.

```text
root/alias -> deep/sub
root/deep/payload.txt = STOP     # 프로그램이 실제 읽는 파일
root/payload.txt = UNUSED       # 프로그램이 읽지 않는 파일

command = open("alias/../payload.txt").read()
```

canonical trace와 변경 전 sealed run은 모두 STOP을 읽고 `OK`다. 그러나 receipt에는
`root/payload.txt`가 관측 파일로 들어가고 실제 `root/deep/payload.txt`와 지나간
`alias` 링크는 빠진다. receipt를 JSON 왕복 저장하고 외부 기대 digest를 고정한 다음:

- 실제 `deep/payload.txt`만 STOP→MOVE로 바꿔도 **`OK` + MOVE**다.
  `open`, `Path.read_text`, `os.open`→`os.read` 세 경로에서 재현했다.
- `alias`를 `other/sub`로 다시 연결하고 `other/payload.txt=MOVE`를 읽게 해도
  **원래 digest로 `OK` + MOVE**다. 파일 바이트 변경이 없는 링크 선택 변경이다.
- 반대로 사용하지 않는 `root/payload.txt`만 바꾸면
  **`HOST_ERROR(seal-violation): sealed file drift: .../payload.txt`**가 된다.
  실제 읽는 값은 여전히 STOP이다. 같은 원인으로 변경 누락과 불필요한 차단이 함께 생긴다.

모든 변경은 두 실행 사이에 끝냈다. 동시 수정, audit 없는 native I/O, custom loader, 환경 우회,
자식 정책 프로세스가 없다. 따라서 문서의 TOCTOU·metadata·native 제외로 설명할 수 없다.
실제로 관측한 읽기의 경로를 잘못 기록하는 문제이며 실행 전 검사와 실행 중 가드가
같은 오해를 공유한다.

수정 조건: 운영체제가 여는 대상과 동일한 경로 의미를 보존하고, 중간에 실제로 지난
symlink binding도 고정해야 한다. 구현상 보장할 수 없는 조합이면 canonical 단계에서
명시적으로 거부해야 한다. 다른 경로의 hash나 부재 상태로 대체하면 안 된다.

재현: `test_symlink_dotdot_consumed_file_drift` 3개,
`test_symlink_dotdot_binding_drift`, `test_symlink_dotdot_irrelevant_file_must_not_block`.
총 **5 strict xfail**이며 마지막 것은 같은 원인의 P2 과잉 차단 증거다.

## C2 — P2: 실제 스크립트 대신 추적기가 `__main__`으로 남음

위치: `harness/runtime_provenance.py:371-373`.
정책은 임시 dict에서 `exec`하지만 `sys.modules['__main__']`는 추적기 모듈 그대로다.
`__name__='__main__'`만 지정해도 정규 Python script의 모듈이 되지는 않는다.

아래 두 프로그램은 같은 Python·`-I -S -B`·cwd·빈 환경으로 직접 실행하면 정상 종료한다.

```python
COMMAND = "STOP"
import __main__
assert __main__.COMMAND == COMMAND
```

```python
import pickle
class Command:
    pass
assert isinstance(pickle.loads(pickle.dumps(Command())), Command)
```

canonical worker에서는 각각 `AttributeError`, `PicklingError`로 봉인 생성이 실패한다.
추가 audit marker로 `__main__.__dict__ is globals()`가 worker에서 거짓임도 확인했다.
파일·환경 변경, 사용자 import machinery, 비표준 native extension·자식 실행이 없는 정상 read-only
Python/stdlib 프로그램이다. 변경 검출기가 프로그램의 실행 의미를 바꾸면서 막고 있다.

수정 조건: 정책의 전역 dict와 실제 `__main__` 모듈을 일치시키고, 추적기 상태는 별도로
유지해야 한다. 직접 script 실행과 canonical/sealed 실행을 비교하는 회귀 검사가 필요하다.
재현: `test_normal_script_main_module_semantics`의 **2 strict xfail**.

## 이전 지적의 처리 범위

새 runtime suite의 원래 R1–R6 **10사례**, 301b의 N1–N7 **12사례**를 다시 실행했다.
추적 경로는 import 문법마다 예외를 붙이지 않고 실제 `open/import/compile/exec` 접근을
받으므로 같은 파일에 도달하는 loader 재수출 형태에 일반화된다. 독립 대조군도 추가했다.
다만 C1 때문에 이를 모든 경로의 정확한 포착으로 일반화할 수는 없다.

| 이전 지적 | 이번 확인과 한계 |
|---|---|
| R1 wildcard, N6 내부 symlink package | 실제 import가 여는 소스를 봉인하고 변경을 거부한다. 경로 정규화의 C1은 별도로 남는다. |
| R2 loader 별칭, N1 재수출 4개, N4 `importlib.__import__` 2개 | 기존 형태 모두 포착한다. 추가한 **두 모듈을 거친 재수출**도 정적 목록에는 plugin이 없지만 runtime에는 있으며, 변경 시 `_child` 호출 전에 거부한다. |
| R3 script sibling, N7 symlink script sibling | 실제 target 부모를 import 경로에 넣어 해당 sibling을 포착한다. 모든 script 실행 의미가 같은 것은 아니며 C2가 남는다. |
| R4 JSON 순서, N2 Decimal, N5 schema 부재/null | 실제 읽은 JSON 전체 바이트를 고정하여 세 차이를 검출한다. 선택 항목 parser 자체를 고친 결과가 아니다. |
| N3 같은 바이트의 source/XML symlink 두 형태 | 직접적인 링크 대상 변경은 binding 검사로 거부한다. `symlink/..` 조합까지 일반화되지는 않는다(C1). |
| R5 다른 workflow 행의 유효성 | 전체 catalog validator와 runtime whole-file pin이 누락 entry·중복 id 변경을 거부한다. |
| R6 공통 launcher | 정적 필수 source와 runtime 관측으로 launcher 변경을 거부한다. 공통 runner의 실제 admission 연결 완료를 뜻하지 않는다. |
| B1 일반 데이터·XML include·registry 참조 | Python이 읽은 원본을 포착한다. XML은 stdlib 소비자이며 NPZ 검사는 bytes read다. MuJoCo/NumPy의 실제 reader 검증으로 세지 않는다. |
| B1 subprocess worker | 이 offline profile에서는 시작을 거부한다. 자식의 의존성을 수집·강제하는 기능이 구현된 것은 아니다. |
| B2 환경·Python/설치 identity | Python 환경 adapter의 값·존재 변경과 봉인된 abort/warn 정책을 검사한다. 설치 변경 검사는 mock identity이며 실제 업그레이드 증거가 아니다. C getenv는 제외다. |

원본 `tests/test_seal_v2_review_301b.py`도 `13afa3dc`에서 그대로 가져와 별도로 실행했다.
**14 passed / 13 strict xfailed**다. 13개는 정적 v2의 미해결 12사례와 기존 B1 참조 경계이며,
runtime 경로의 수정 성공과 섞어 세지 않는다. 정적 API만 사용하면 이전 누락은 그대로다.

## 과잉 차단과 명시된 제외 범위

- 읽지 않은 일반 Markdown 파일을 바꿔도 통과하고, 명시적으로 전달했지만 읽지 않은
  설정값 변경도 통과한다. 이 두 정상 대조군은 새 검토 suite에서 확인했다.
- 전체 JSON을 읽는 소비자는 선택하지 않은 행을 바꿔도 실행 전에 거부한다.
  독립 대조군으로 확인했고, 문서 `:88-92`가 의도적으로 철회한 허용 범위다.
  **무관한 catalog 편집에 따른 재봉인 감소는 이번 구현에서 달성하지 못했다.**
- 정적 wildcard의 전체 subtree, bootstrap 파일, 설치 distribution 전체 목록도
  보수적으로 묶는다. 특히 `identity():62-67`은 사용한 package만 가리지 않는다.
  불필요한 재봉인 비용이 있으며 최소 의존성 집합이라고 부를 수 없다.
- C1의 무관 파일 차단과 C2의 정상 script 차단은 위의 의도된 보수성으로 설명되지 않는다.

**B1 경계 재현 2개:** 빈 `settings/`를 `os.listdir` 또는 `Path.glob`로 조회한 뒤,
`move.cfg`라는 이름의 파일을 추가하면 STOP→MOVE가 되지만 원래 봉인이 `OK`다.
이때 파일 내용은 열지 않는다. `os.listdir`/`os.scandir` 이벤트 수는 남지만 조회 결과는
dependency state에 없다(`runtime_provenance.py:304-334`). 두 API의 audit event 존재는
[CPython 공식 목록](https://docs.python.org/3.12/library/audit_events.html)에서도 확인했다.

이는 `docs/runtime_provenance.md:77-83,105-107`에서 제외한 metadata/directory 의미의
구체적 사례로 분류하며 **새 결함 C1/C2 수에 합산하지 않는다**. 해당 strict xfail 두 개는
범위 경계를 보존한다. 파일 open 가드만으로 새 분기의 모든 의미 변화가 막히지는 않는다.

native read/C getenv, OS 수준 자식 추적·제한, metadata와 동시 수정, 불변 입력 강제,
custom import machinery·subinterpreter, 실제 sim_cli/worker admission과 canonical 물리
trace는 여전히 범위 밖이다. ReproZip/Sciunit을 설치하거나 그 수준의 수집을 검증하지 않았다.
이 제외를 유지한 오프라인 개발 도구의 병합은 C1/C2 수정 뒤 검토할 수 있다. 실제 실행기
연결 때는 OS backend와 모든 descendant에 대한 강제를 별도로 인수해야 한다.

## 기존 봉인·실행기 보존

기준 `d17ca4345affef8cf027e121cf1f3197b36c23e0`, 대상 Git blob, 추출한 실제 파일을
독립 스크립트로 바이트 비교했다. **총 76/76 동일**이다.

- v6~v6e 등록 JSON **5/5**.
- 기존 RGB 봉인 JSON **65/65**.
- 기존 closure·bundle·검증기·실행기 source **6/6**.
- 대상 v6e 등록의 `v6_contract.source_sha256` **85/85 일치**.

`harness/`, `sim/`, `scripts/`, `config/`, `configs/` 검색 결과 제품 호출자는 새 도구와
명시적 CLI뿐이다. 기존 실행기의 v2 fallback·자동 전환·기존 registration 재작성은
발견하지 못했다. 구형 receipt 거부와 기존 출력 덮어쓰기 거부도 관련 회귀 범위다.
PR의 merge-base 대비 `.github/workflows` 변경은 없다. 최신 main에 이후 변경이 있어
현재 main과의 양쪽 tip 비교가 같다는 주장은 하지 않는다. 이 검토도 workflow를 수정하지 않았다.

## 실행 기록과 재현

최종 관련 suite: **349 passed / 1 failed / 1 deselected**(350개 실행).
새 runtime suite의 **56/56**은 모두 통과했다. 실패한 것은
`test_ci_host_lock.py::test_child_observes_live_lock_and_normal_exit_releases_it[7]`이며,
더미 Python 자식의 종료 뒤 `Owned test group cleanup unconfirmed`를 반환했다.
같은 소스의 해당 검사만 재실행하면 **1 passed**다. 이 종료 확인 코드에는 PR 변경이
없지만 실패 원인은 확정하지 않았다. 전체 실행을 모두 통과했다고 바꾸어 보고하지 않는다.
오류 로그와 단독 재실행 로그를 모두 보존했다. 임시 worktree를 만드는 검사 한 개는
사용자 범위를 지키기 위해 제외했다.
새 검토 suite: **5 passed / 9 strict xfailed**, 일반 skip·error·XPASS 없음.
9개는 **C1 5개 + C2 2개 + 문서화된 B1 경계 2개**다. 예상 실패는 통과가 아니다.
`--runxfail`로 해당 9개를 다시 실행하면 **9 failed / 5 deselected**이며,
모두 의도한 `SealAccepted`, `IrrelevantFileRejected`, `NormalScriptRejected`에서 실패한다.
수집/setup 오류를 xfail로 감추지 않도록 `raises=`를 제한했다. 반복 실행은 합산하지 않는다.

기존 Mac 환경 `.venv-sim-worker-mac`, Python 3.12.13, pytest 9.1.1,
macOS 27.2 arm64를 사용했다. NumPy 2.5.2·MuJoCo 3.12.0은 metadata 조회값이며
이 검토에서 해당 엔진·물리·렌더·모델 호출·학습을 실행하지 않았다. 공용 호스트 잠금은
사용하지 않았다. 잠금 단위 테스트는 임시 디렉터리와 더미 Python 프로세스만 사용했다.

추출 디렉터리는 `/private/tmp/ugrp-review-301c.T4d3Z3`이다. 역사 blob을 읽는 기존
검사를 위해 여기에만 `git clone --bare --shared --no-hardlinks`로 로컬 객체 참조를 붙이고
`core.bare=false`, 별도 `review-snapshot` HEAD를 대상 SHA로 설정했다.
프로젝트 worktree를 추가하거나 공유 저장소의 HEAD를 바꾸지 않았다.
임시 worktree 생성 단위 테스트 한 개도 아래처럼 제외했다.
초기 검사는 그 조건과 역사 조회 환경을 정리하려고 45 passed에서 중단했으며 최종 수에 합산하지 않는다.

```sh
# 검토 worktree에서 추출; 실행 소스는 위의 고정 SHA와 일치 확인
review_scratch=$(mktemp -d /private/tmp/ugrp-review-301c.XXXXXX)
git archive cea627c539873b60775db6df146254ab077cec0c | tar -x -C "$review_scratch"
git clone --bare --shared --no-hardlinks /Users/changmin/projects/ugrp "$review_scratch/.git"
git --git-dir="$review_scratch/.git" config core.bare false
git --git-dir="$review_scratch/.git" update-ref refs/heads/review-snapshot cea627c539873b60775db6df146254ab077cec0c
git --git-dir="$review_scratch/.git" symbolic-ref HEAD refs/heads/review-snapshot
git show 13afa3dc04fa15630248716b580d776a7e6cb1d7:tests/test_seal_v2_review_301b.py > "$review_scratch/tests/test_seal_v2_review_301b.py"
cp tests/test_seal_v2_review_301c.py "$review_scratch/tests/"
cd "$review_scratch"
export PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1
review_python=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$review_python" -m pytest -q \
  tests/test_seal_runtime_provenance.py tests/test_execution_dependency_contract.py \
  tests/test_seal_v2_review_301.py tests/test_seal_v2_fail_closed.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_pair_v6.py tests/test_rgb_execution_bundle.py \
  tests/test_ci_sharding.py tests/test_ci_host_lock.py \
  --deselect=tests/test_ci_host_lock.py::test_linked_worktrees_share_primary_lock_but_other_clones_do_not
"$review_python" -m pytest -q -rx tests/test_seal_v2_review_301b.py
"$review_python" -m pytest -q -rx tests/test_seal_v2_review_301c.py
"$review_python" -m pytest -q --runxfail --tb=short tests/test_seal_v2_review_301c.py \
  -k 'symlink_dotdot or normal_script or directory_query'
"$review_python" -m pytest -q \
  'tests/test_ci_host_lock.py::test_child_observes_live_lock_and_normal_exit_releases_it[7]'
```

원본 로그·JUnit·보존 감사와 스크립트는
`/Users/changmin/projects/ugrp/outputs/review-301c-cea627c5-20260930/`에 보존했다.
raw는 로컬 보관이며 원격 백업으로 표현하지 않는다. 새 테스트는 기존 CI 목록에
추가하지 않았으므로 위 명시적 명령으로 실행해야 한다. 조회 당시 대상 SHA의 GitHub
`offline-regressions`는 SUCCESS였지만 새 반례를 검사한 결과는 아니다.

| 파일 | SHA-256 |
|---|---|
| `tests/test_seal_v2_review_301c.py` | `4c549118a8741aabd3c0214b892343bd39b0df4ec01bbe207e8e2da5470820de` |
| `baseline-final.log` | `1b1b5590c2fb3a6d7ff95a6307feb6a3dd8e2d5a80a9b576ac3bcada663c4657` |
| `baseline-final.xml` | `9ee0f8f0c9bac866c89bda8c820278f9dd4d1b4f82bd9653ecf77c8aaccda2a0` |
| `host-lock-recheck.log` | `3dd8a455f93386b2d78b9d5605f1c2f52fd55f0962f89b0bd7d602cae0ead952` |
| `review-301c-final.log` | `b0b7973c9822dcf74e0411981ae995d6a72e0c7cc30f77a5961284a2349df1c5` |
| `review-301c-final.xml` | `bd19b85edd46f68dc276a11398541fb1b7a386953002438f5bd4db214a359bad` |
| `review-301c-unmarked.log` | `add045ca4c48ddf0f8debf191821829032ce64ba927b53c3ea6ed3865cfc7973` |
| `prior-301b.log` | `2153cadeb2d1b16ebd15c56a4042ee9f32028e9888b686aa58812a3ab27536c3` |
| `legacy-preservation.json` | `2625ed1453edfa5c38d9bdc3e674613fd739556f871dbe7afd4adc2425996ece` |

변경은 이 보고서와 독립 검토 테스트뿐이다. PR 제품 소스·기존 봉인·`.github/workflows`·
기본 checkout은 수정하지 않았다. 연구 실험 결과가 없어 TensorBoard 변환·화면 작업은
하지 않았고, UGRP 예외에 따라 Google Drive 작업도 없다. 병합은 수행하지 않는다.
