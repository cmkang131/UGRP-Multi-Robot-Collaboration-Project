# 실행 관측 기반 봉인: PR #301 후속 설계

상태: **오프라인 Python 추적기·검사 실행기 구현, 물리 실행 admission 미구현**.
2026-09-30의 두 번 BLOCK 뒤 정적 import 분석 보강을 중단했다. 기존 v2 정적 계약은
관측 집합에 더하는 보수적 입력 목록으로만 사용한다. 이 문서는 `REVIEW_301_astra.md`
(R1–R6)와 `REVIEW_301b_astra.md`(새 7종 12사례)의 전체 런타임 문제를 정적 문법
규칙 추가로 해결했다는 주장을 대체한다. 구형 봉인·제어기·workflow는 바꾸지 않는다.

## 참고 자료와 채택한 방법

2026-09-30과 2026-10-01에 아래 원 논문·공식 문서·구현을 확인했다. 도구들을 설치하거나 실제 실험을
이 도구로 실행한 것은 아니다. 채택한 것은 관측 입력 + 선언 입력 + 실행 시 강제라는
설계 방법이다. 새 Python 구현의 검증 범위는 오프라인 테스트로 별도 표시한다.

| 자료 | 확인한 방법과 이 PR의 적용 |
|---|---|
| [ReproZip, NYU, TaPP 2013](https://www.usenix.org/conference/tapp13/technical-sessions/presentation/chirigati), [개발 안내](https://docs.reprozip.org/en/latest/developerguide.html) | 시스템 호출 추적으로 입력·라이브러리를 발견하고 실행별 provenance를 보존한다. 실제 native 실행의 후속 수집 backend로 삼는다. Linux packing과 Mac Python hook을 동등한 것으로 취급하지 않는다. |
| [ReproZip 경로 수집](https://github.com/VIDA-NYU/reprozip/blob/master/reprozip/reprozip/tracer/trace.py), [링크 순회 구현](https://github.com/VIDA-NYU/reprozip/blob/master/reprozip-core/reprozip_core/utils.py), [Python realpath/normpath](https://docs.python.org/3.12/library/os.path.html#os.path.realpath) | 접근 경로와 최종 대상을 구분하고 중간 symlink도 의존성으로 보존한다. 이 구현은 `path_used`를 그대로 남기고 링크를 순서대로 확장한 뒤 `..`을 처리하며, `os.path.realpath`와 결과를 대조한다. 먼저 `abspath`로 줄이면 `alias/../file`의 의미가 바뀌므로 그렇게 정규화하지 않는다. |
| [coverage.py 실행기](https://github.com/coveragepy/coveragepy/blob/main/coverage/execfile.py), [runpy.run_path](https://docs.python.org/3.12/library/runpy.html#runpy.run_path) | `ModuleType('__main__')`을 `sys.modules`에 등록하고 그 모듈의 전역 공간에서 실행한다. 이 도구는 별도 자식에서 실행하므로 entry 모듈을 종료 콜백까지 유지한다. `run_path`가 반환할 때 원래 모듈을 복구하는 동작을 그대로 호출하지 않는다. |
| [CDE, USENIX ATC 2011](https://www.usenix.org/conference/usenixatc11/cde-using-system-call-interposition-automatically-create-portable-software) | 시스템 호출 가로채기로 실제 실행의 의존 파일을 묶는다. Python AST 밖의 native/자식 접근도 OS 계층에서 다뤄야 한다는 근거다. |
| [Sciunits: Reusable Research Objects](https://arxiv.org/abs/1707.05731) | 코드·자료·과거 실행·출처를 재실행 가능한 단위로 보존한다. case별 trace 및 외부 등록 digest를 연결한다. |
| [noWorkflow](https://github.com/gems-uff/noworkflow) | Python 스크립트의 실행 provenance를 수집한다. Python 관측기를 먼저 작은 fixture에서 검증하되 전체 OS 실행의 증거와 구분한다. |
| [PEP 578](https://peps.python.org/pep-0578/), [sys.addaudithook](https://docs.python.org/3/library/sys.html#sys.addaudithook), [audit event 목록](https://docs.python.org/3/library/audit_events.html) | `open`, `import`, `compile`, `exec`, `os.*` 이벤트를 받는다. hook은 재현성 확인용 관측 지점이며 보안 sandbox가 아니다. C 직접 I/O 및 환경 읽기의 완전성을 주장하지 않는다. |
| [Bazel hermeticity](https://bazel.build/basics/hermeticity), [sandboxing](https://bazel.build/docs/sandboxing) | 선언된 입력·도구·환경과 외부 접근 제한이 함께 있어야 한다. 관측하지 않은 분기도 런타임 제한으로 다룬다. 단순 해시 목록이나 trace만으로 hermetic 실행이 되지 않는다. |
| [Nix store building](https://github.com/NixOS/nix/blob/master/doc/manual/source/store/building.md), [Nix glossary](https://nix.dev/manual/nix/2.25/glossary.html?highlight=closure) | 입력 closure와 불변 store의 역할을 구분한다. input addressing과 content addressing도 구분한다. 이 PR은 Nix sandbox를 설치하거나 제공하지 않는다. |
| [Bazel remote caching](https://bazel.build/remote/caching) | action의 입력·명령·환경을 구분하고 결과 파일은 CAS로 참조한다. 새 seal digest는 같은 입력 확인용이며 검증 결과 캐시나 실행 승인으로 자동 재사용하지 않는다. |

## 구현한 오프라인 경로

`harness/runtime_provenance.py`와 `scripts/trace_execution_dependencies.py`만 명시적으로
선택한다. schema는 `ugrp.execution_runtime_seal.v2`, profile은
`python-audit-offline-v1`이다. 기존 `ugrp.execution_dependency_contract.v2`만으로는
관측 봉인이 아니며 기존 runner에서 자동 선택하지 않는다.

1. 검토한 정적 v2 receipt와 그 **외부 기대 digest**를 대조한다. 선언 진입점에 속한
   canonical `entry`/`args` 사례 목록을 명시한다. 실제 실행이므로 임의의 정책을
   자동 발견 목적으로 실행하지 않는다. coordinator가 사례를 선택한다.
2. 사례마다 새 CPython `-I -S -B` 프로세스를 시작한다. user site, `.pth`,
   `PYTHONPATH`, 기존 프로세스의 `sys.modules`를 물려받지 않는다. script의 실제
   symlink target 폴더와 저장소 root를 import 경로로 명시한다. hook은 정책의 첫
   파일 read/compile/exec 전에 설치한다.
   entry의 전역 공간과 `sys.modules['__main__']`는 같은 모듈이며 정상 스크립트의
   자기 import, `__main__` 클래스 pickle, 종료 콜백에서도 이 관계를 유지한다.
3. `open` 이벤트의 파일, import origin, compile/exec의 실제 파일명을 기록한다.
   존재하지 않는 open 시도도 부재 상태로 고정한다. bootstrap에서 이미 읽은 모듈은
   관측 read와 구분해 seed로 넣는다. 파일은 SHA-256뿐 아니라 사용 경로(`path_used`),
   realpath, 중간 링크 및 링크 target 안의 symlink까지 고정한다. 경로 guard는
   실제 대상을 비교하므로 같은 대상의 다른 `./`·`..` 표기는 허용하지만 새로운
   symlink binding은 허용하지 않는다. 해석할 수 없는 parent traversal은 명시 거부한다.
   `os.listdir`·`os.scandir`(Path.glob 포함)는 별도 `directories`에 이름·종류·링크
   target과 디렉터리 부재를 고정한다. 읽지 않은 파일의 내용은 이 목록에 넣지 않는다.
4. **최종 파일 집합 = 모든 성공한 case의 관측 ∪ 정적 source/input 집합 ∪ bootstrap**.
   case마다 이벤트 횟수와 관측 파일 목록을 남긴다. 파일·환경이 case 사이에 다르거나
   실패/timeout이면 부분 봉인을 반환하지 않는다. 수집 뒤 정적 receipt와 모든 파일을
   다시 검사한다. 조회한 디렉터리도 case별 합집합과 사후 비교에 포함한다.
   새 사례가 실패한 채 이전 trace를 완성본으로 쓰지 않는다.
5. 부모의 Python 버전/구현/cache tag/실행 바이너리·플랫폼·설치 distribution 이름과
   버전, 추적기/CLI 소스 identity를 고정한다. 설치 버전 목록은 native 실행을 관측한
   결과가 아니며 라이브러리 바이너리 완전성을 증명하지 않는다.
6. 환경은 명시한 **비밀이 아닌 설정 이름만** 자식에 전달한다. `os.environ`,
   `os.environb`, `os.getenv`의 읽기를 Mapping adapter로 기록한다. CPython에는
   getenv 읽기를 모두 통지하는 audit event가 없기 때문이다. 기대값은 존재 여부와
   SHA-256이며 원문은 receipt에 넣지 않는다. credential 형태 이름은 전달 자체를
   거부한다. 명시하지 않은 호스트 환경은 제거되므로 원래 unrestricted 실행과
   동일하다고 간주할 수 없다.
   `os.environ.copy()`와 `os.environb.copy()`는 각각 문자열·bytes 키/값의 독립된
   `dict`를 반환하며 복사한 모든 항목의 읽기를 기록한다. 복사본을 바꿔도 환경은
   바뀌지 않으며, 복사 당시 읽은 설정의 변경은 기존 abort/warn 규칙을 따른다.
7. `run`은 외부 등록의 최종 digest, 정적 receipt, 전체 파일·조회 디렉터리와 symlink,
   runner identity를 먼저 검사한다. 같은 hook을 정책 실행 중에도 유지한다.
   새로운/변경된 파일 읽기나 디렉터리 조회는 작업 전에 `HOST_ERROR(seal-violation)`을 기록하고
   자식 프로세스를 종료(code 86)한다. `except BaseException`으로 잡아도 계속하지
   못하도록 Python 예외 대신 `os._exit`을 사용한다. signal/timeout/보고 누락도
   성공으로 처리하지 않는다.
8. 환경 값과 설치 identity의 변경은 봉인된 `abort`/`warn` 정책을 따른다. 기본은
   abort다. warn은 사유를 필수로 기록하고 실행 report에 남긴다. 새 환경 이름 읽기와
   새 파일 읽기에는 warn을 적용하지 않는다. 실행 명령에서 정책을 느슨하게 덮어쓰는
   옵션은 없다.

이는 신뢰하는 Python 정책의 의도하지 않은 의존성 변경 검출기다.
hook 객체·부모 프로세스·report FD의 무결성은 신뢰 전제로 남는다.

### 도구 출력의 명시적 제외 규칙

CLI는 추적을 시작하기 전에 `--output`과 그 실패 보고서 경로
`<output>.failed.json` 두 곳을 **도구 전용 출력**으로 선언한다. 이 정확한 경로의
사용 위치·실제 위치·중간 링크를 `output_artifacts`에 넣어 외부 digest로 봉인한다.
이름이나 확장자 패턴으로 추측하지 않으며 다른 폴더의 동명 파일, 비슷한 이름,
출력의 상위 폴더 전체는 제외하지 않는다. 부모 폴더는 미리 존재해야 하고 출력은
일반 파일 또는 아직 없는 파일만 허용한다. CLI는 기존 seal을 덮어쓰지 않는다.

이 두 출력은 디렉터리 의존성 snapshot뿐 아니라 자식의 `os.listdir`·`os.scandir`
(Path 열거 포함) 결과에서도 제외한다. 따라서 저장 전후 목록 길이에 의존하는 코드도
같은 입력 목록을 본다. bytes 경로도 같은 규칙을 따른다. 출력 내용을 입력으로
읽거나 정적 입력으로 겸용하면 추적/재실행을 거부하며, symlink를 통한 읽기도 같다.
출력을 디렉터리·symlink로 바꾸거나 중간 링크를 변경하면 재실행 전에 거부한다.
직접 API는 `output_artifacts`에 명시한 파일에만 이 규칙을 적용하며 기본은 빈 목록이다.
파일 존재·stat 등 audit 밖의 metadata 조회에는 아래 지원 한계가 그대로 적용된다.

## 일부러 좁힌 지원 범위와 남은 틈

- 오프라인 read-only Python/stdlib fixture만 지원한다. subprocess/fork/exec,
  ctypes, socket, 파일 쓰기·변경, mmap 등은 audit 단계에서 거부한다. NumPy/MuJoCo와
  비표준 native extension은 OS backend가 필요하다. 따라서 이 PR의 CLI로 coordinator가
  canonical 물리를 바로 실행할 수 없다. 기존 물리 runner도 수정하지 않았다.
- 표준 라이브러리 및 이미 로드된 native bootstrap은 신뢰 경계다. native `fopen`,
  C `getenv`, 일부 파일 metadata/stat/존재 확인, audit 없는 API는 완전 추적되지 않는다.
  디렉터리 조회는 이름·종류·링크 목록만 지원하며 열거 순서, `DirEntry.stat`, 링크
  대상의 metadata까지 재현한다고 주장하지 않는다. FD를 통한 조회는 명시 거부한다.
  import가 디렉터리를 조회하면 그 목록도 보수적으로 묶이므로 새 무관 파일 추가가
  재봉인을 요구할 수 있다. 원래 파일 내용 변경 허용과는 다른 경계다.
  `os.environ` adapter 우회, custom import machinery, 스레드·subinterpreter도 완전한
  격리를 보장하지 않는다. 지원할 때는 OS 강제 계층이 필요하다.
- 파일 hash 확인과 실제 open 사이의 동시 수정(TOCTOU)을 이 Python prototype이
  닫지 않는다. coordinator는 불변 staged tree를 사용해야 하고, 실제 admission에는
  OS 차원의 읽기 전용 mount/입력 복사 snapshot이 필요하다.
- 절대 경로/root binding은 의도적이다. 다른 checkout으로 receipt를 옮기면 거부한다.
  이동 가능한 CAS 경로 매핑은 후속 OS backend에서 설계한다.
- 저장소의 기존 `.pyc`를 읽으려 하면 거부한다. 소스와 캐시의 일치가 추정에 기대지
  않도록 별도의 깨끗한 staged source를 쓰며, 사용자의 기존 cache를 자동 삭제하지 않는다.
- 관측 데이터는 실제 읽은 파일의 바이트 전체를 고정한다. JSON을 전체 읽는 소비자가
  있으면 공용 catalog도 whole-file로 들어간다. Decimal 정밀도, schema 부재/null,
  키 순서, 선택 행 밖 defaults 문제는 이 경로에서 빠지지 않는다. **무관한 catalog
  편집 허용은 이번 구현의 보장이 아니다.** 축소하려면 소비자에게 고정한 JSON slice만
  제공하는 별도 adapter와 그 실제 사용 증거가 먼저 필요하다.
- 성능 비교, 물리 trace, 자식 worker 전파, sim_cli/admission 연결, 원시 trace CAS 저장,
  테스트 결과 캐시는 구현하지 않았다. 초기 호스트 환경과 외부 package inventory가
  같다는 사실도 물리 실행 허가나 과거 성능 승계가 아니다.

## coordinator 후속 절차 (이번 작업에서 실행하지 않음)

1. 신규 등록의 짧은 정상·실패·복구·평가/저장 case와 고정 입력을 먼저 정한다. 기존
   v6~v6e/RGB 봉인을 수정하지 않고 새 후보만 선택한다.
2. Linux의 검토된 실행 환경에서 ReproZip 계열 OS 추적으로 자식 process tree,
   native open/openat, XML include/mesh/texture, 실제 interpreter/shared library를
   관측한다. OS 환경 전달은 선언 allowlist로 제한한다. Mac 결과와 Linux 결과를
   같은 환경의 증거로 합산하지 않는다.
3. 정적 집합과 관측 집합의 union을 불변 staged tree/CAS로 만든다. 상대 경로,
   symlink, directory/stat, 실패한 read도 의미에 포함한다. 일회 관측을 근거로
   정적 입력을 빼지 않는다. 내용이 같아도 링크 대상 변경을 허용하지 않는다.
4. 정책·worker **시작 전** OS sandbox에 허용된 입력만 노출한다. 모든 descendant에
   같은 입력 제한을 적용하고 deny 사건을 `HOST_ERROR(seal-violation)`으로 연결한다.
   trace-only 결과를 enforce 완료로 승격하지 않는다. runtime 기록 쓰기는 별도
   출력 mount로 분리하며 출력이 새 입력이 되는 경우에는 명시한 provenance가 필요하다.
5. 새 sim_cli 어댑터/admission에 외부 등록 digest, run SHA, clean tree, 승인·예산,
   환경 비교, worker case 검사와 위 OS backend receipt를 함께 연결한다. native
   backend/관측 자료가 없으면 실행을 거부한다. 기존 경로 fallback은 두지 않는다.
6. unknown native read·미선언 자식·C 환경 read·실행 중 링크 변경 반례와 전체 canonical
   trace를 독립 검토한다. 그 뒤에만 새 cohort를 봉인하며 물리 결과/TensorBoard는
   coordinator가 실제 결과를 얻은 뒤 별도로 기록한다.

## 오프라인 사용법

아래 예는 이미 존재하는 `candidate-static.json`의 기대 digest를 외부 등록에서
받고, `cases.json`은 `[{"entry":"entry.py","args":[]}]`처럼 준비한 경우다.
기존 시뮬레이션 실행을 대신하는 명령이 아니다. credentials를 인자/환경에 넣지 않는다.

```sh
python -m scripts.trace_execution_dependencies --root /absolute/staged-root trace \
  --static-contract candidate-static.json --expected-static-sha256 APPROVED_STATIC_DIGEST \
  --cases cases.json --env NONSECRET_SETTING --output new-runtime-seal.json
python -m scripts.trace_execution_dependencies --root /absolute/staged-root run \
  --seal new-runtime-seal.json --expected-sha256 APPROVED_RUNTIME_DIGEST --case-index 0
```

환경 경고를 의도하면 `--policy`에 아래 JSON 파일을 trace 시 한 번 지정한다. 새 입력이나
파일 불일치는 여전히 abort이며, 정책 자체도 최종 digest에 포함된다.

```json
{"environment":"warn","identity":"abort","reason":"승인된 환경 차이 진단"}
```

구체적인 테스트 결과와 원래 리뷰 사례 대응은
[작업 기록](../experiments/2026-09-30-seal-dependency-decouple/RUNTIME_PROVENANCE.md)을 따른다.
세 번째 검토의 경로·`__main__`·디렉터리·종료 확인 수정은
[301c 답변과 검증 기록](../experiments/2026-09-30-seal-dependency-decouple/REVIEW_RESPONSE_301c.md)을 따른다.
