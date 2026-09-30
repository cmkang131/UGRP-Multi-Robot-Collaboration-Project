# PR #301 독립 재검토

검토 대상: `e25d7509d78af711b9a33ae62bd5c103a425200e`. 비교 기준은 최초 PR의
`d17ca4345affef8cf027e121cf1f3197b36c23e0`, 리뷰 브랜치는 `codex/review-301b`다.
[첫 검토](https://github.com/kcm0127-dotcom/ugrp/blob/d21e0147fbc0829da3c9878877b4c5f5c83f865f/experiments/2026-09-30-seal-dependency-decouple/REVIEW_301_astra.md)와
`REVIEW_RESPONSE_301.md`에 대한 후속 검토다. 제품 소스·기존 봉인·#292는 수정하지 않았다.

판정: **BLOCK**. 기존 R1·R2·R3 수정은 내부 symlink와 모듈 간 loader 재수출까지
일반화되지 않았다. 추가 검토는 **새 누락 7종의 사례 12개**, 이미 문서화된 registry
참조 경계 1개를 구분한다. 각 누락은 원래 receipt와 외부 digest를 그대로 둔 채 재현한다.
기존 봉인 보존은 확인했지만 새 v2의 변경 검출이 충분하다는 뜻은 아니다.
아래는 v2 단독 변경 검출기의 false negative다. 보존된 Git HEAD·dirty-tree·외부 admission
검사까지 우회해 실제 실행이 승인된다는 주장은 아니며, 그 실행은 하지 않았다.

## 원래 6개 결함의 수정 범위

| 지적 | 재검토 판단 |
|---|---|
| R1 wildcard 자식 누락 | **부분 수정.** 일반 디렉터리의 전체 Python 하위 트리, 계산된 `__all__`, namespace/상대 wildcard를 포함한다. script+상대+계산된 wildcard 대조군도 추가했다. 내부 symlink 디렉터리는 N6에서 빠진다. |
| R2 동적 loader 별칭 | **부분 수정.** 같은 파일의 대입·getattr·builtins 별칭, 미해결 함수 전달의 거부는 보강됐다. 파일을 넘어 다시 내보낸 함수/모듈 네 형태(N1), `importlib.__import__` 두 형태(N4)는 추적도 거부도 하지 않는다. |
| R3 script 폴더 import | **부분 수정.** root와 선언한 script 부모 폴더의 모든 후보 및 전이 import를 포함한다. symlink script의 실제 target 폴더는 N7에서 빠진다. |
| R4 선택 객체 순서 | **원래 결함 수정 확인.** 중첩 객체·배열 속 객체의 순서 hash와 receipt 순서 재검사를 포함한다. 다만 일반 JSON selector에는 숫자 정밀도(N2)와 자동 고정 schema의 존재 여부(N5) 경계가 남는다. |
| R5 다른 workflow 행의 유효성 | **원래 결함 수정 확인.** `selected_entry`가 실제 `workflow_manager.catalog`를 호출한다. 중복/누락 id, 필수 필드, entry 삭제의 거부와 유효한 무관 행 편집 허용이 함께 유지된다. |
| R6 공통 launcher 누락 | **원래 결함 수정 확인.** manager·CLI·session·shell을 필수로 고정하고 Python 전이 소스를 따라간다. launcher 네 파일 각각의 변경/삭제 검사와 실제 communication 명령 생성 회귀를 포함한다. |

## 재현 범위

새 `tests/test_seal_v2_review_301b.py`는 임시 폴더의 작은 Python·JSON·XML 파일과
그 폴더 안의 symlink만 다룬다. **fixture 자식 프로세스, 네트워크, 환경 변수·설치 패키지·
권한·mtime·bytecode 변경, `sys.path`/`sys.modules` 교체는 없다.** 중단 전 초안과
원래 24개 검사의 JUnit은 로컬 raw에 보존했지만, 범위 밖의 권한/캐시/환경 조작 시험은
최종 suite·결함 수에 포함하지 않았다.

JSON/XML/경로 사례는 고정된 작은 소비 함수를 별도 namespace에서 호출해 STOP→MOVE를
확인한다. import 사례는 CPython `PathFinder`에 검색 폴더를 직접 주어 실제 소스 경로를
확인하고 그 파일의 `COMMAND` 리터럴 변경, stdlib loader의 identity를 검사한다.
**후자는 import 해석·소스 증거이며 전체 entry나 실제 로봇 제어기를 실행한 결과가 아니다.**
symlink script 사례에서는 Python 파일 실행의 실제 script 디렉터리 규칙을 명시적으로 적용한다.

변경 전 build/verify 성공 후 receipt를 JSON 왕복 저장하고 외부 digest를 고정한다.
변경 후 `verify_contract`의 거부를 기대한다. 예상 실패는
`strict=True, raises=SealAccepted`만 허용하므로 준비/관측/해석 오류는 xfail로 숨지 않는다.
xfail은 **누락 재현**이며 성공·수정 완료가 아니다.

## 새 누락 사례

### N1 / R2 — P1: 다른 모듈이 다시 내보낸 import 함수·모듈을 누락

위치: `harness/python_source_closure_v2.py:100-121,123-154`,
`harness/execution_dependency_contract.py:157-167`.

```python
# bridge.py
from importlib import import_module as load
# entry.py
from bridge import load
print(load('plugin').COMMAND)
# plugin.py: COMMAND = 'STOP' -> COMMAND = 'MOVE'
```

`bridge.py`는 closure에 있지만 binding 정보는 파일마다 초기화한다. 소비자에서는
`load`를 loader로 인식하지 않고, 내보내는 쪽에서도 import 문 자체를 escape로 거부하지
않는다. 함수 재수출, `bridge.load`의 builtins 재수출, importlib 모듈 재수출,
wildcard 재수출 **4개**가 같은 누락을 보인다. 같은 파일의 대입 별칭 수정으로는 닫히지 않는다.

재현: `test_reexported_loader_drift`. 네 경우 모두 `modules=['plugin']` 대조군이 있다.
로컬 import/export 경계를 넘어 binding을 전달하거나 해석하지 못한 export를 거부해야 한다.

### N2 / R4 — P2: 선택된 JSON 숫자의 정밀도 손실

위치: `harness/execution_dependency_contract.py:59-66,102-103`.

선택한 `policy.gain`을 `9007199254740992.0`에서 `9007199254740993.0`으로 바꾼다.
봉인 parser는 같은 float로 읽지만, 봉인된 소비자는 `json.loads(..., parse_float=Decimal)`로
구분하여 STOP→MOVE를 반환한다. **선택 행 내부** 수정이며 누락 selector가 아니다.

재현: `test_selected_json_decimal_precision_drift`. 전체 파일 pin 대조군도 검사한다.
정밀도를 보존하거나 동일 parser를 쓰는 소비자로 selector의 지원 범위를 제한·검사해야 한다.
현재 UGRP workflow가 Decimal로 읽는다는 주장은 아니다.

### N3 — P1: 모두 선언한 파일도 symlink 대상 선택은 봉인되지 않음

위치: `harness/execution_dependency_contract.py:35-43,174-177`.

- 바이트가 같은 `stop/main.py`와 `move/main.py`를 모두 선언하고 `entry.py` 링크만
  바꾼다. `Path(__file__).resolve().parent.name`이 STOP→MOVE를 선택한다.
- 바이트가 같은 scene XML 두 개, 서로 다른 body XML 두 개 **모두**를 inputs에 넣고
  `scene.xml` 링크만 바꾼다. 실제 경로 기준 상대 include가 다른 body를 읽어 STOP→MOVE가 된다.

선언된 파일 내용은 전부 그대로이고 원래 digest가 통과한다. `local_file`은 경로가 저장소
안인지 확인하지만 대상 경로/링크 종류는 저장하지 않는다. XML 사례는 stdlib 소비자로만
재현했고 MuJoCo include 해석·모델 생성·물리를 실행하지 않았다.

재현: `test_declared_source_symlink_target_drift`,
`test_declared_xml_symlink_selects_different_declared_child`.
경로를 구성하는 symlink의 대상을 고정하거나 이런 입력을 거부해야 한다. 단순히 “참조 자산을
모두 선언”하라는 B1 문서만으로는 막히지 않는다. 이 내용 hash의 한계는 기존 방식에도
있을 수 있으며, 이번 PR이 새로 도입한 회귀라고 주장하지 않는다.

### N4 / R2 — P1: `importlib.__import__`는 추적도 거부도 하지 않음

위치: `harness/python_source_closure_v2.py:114-119,147-154,190-198`.

```python
from importlib import __import__ as load
print(load('plugin').COMMAND)
# 또는 import importlib; print(importlib.__import__('plugin').COMMAND)
```

둘 다 표준 importlib가 제공하는 loader다. 사용자/native loader나 별도 검색 경로가 아니다.
현재 분석기는 importlib에서는 `import_module`, builtins에서는 `__import__`만 인식한다.
`plugin.py`의 STOP→MOVE를 두 문법 모두 놓친다. 이미 import한 stdlib json에 대한 loader
호출과 `PathFinder`의 로컬 plugin 소스 선택을 별도로 확인한다.

재현: `test_importlib_builtin_loader_drift`. 두 경우 모두 명시적 module 대조군이 있다.
이 표준 loader도 같은 호출 분석에 연결하거나 지원하지 않는 importlib loader 접근을 거부해야 한다.

### N5 — P2: 자동 고정하는 schema의 누락과 null을 같게 처리

위치: `harness/execution_dependency_contract.py:98-103`.

`{"policy":{"command":"STOP"}}`에 `"schema":null`만 추가한다. 소비자의
`document.get('schema', 'legacy')`는 legacy→None으로 달라지고 STOP→MOVE를 고른다.
봉인기는 `document.get('schema')`로 두 경우를 모두 None으로 저장한다. 자동으로
고정한다고 명시한 catalog schema의 상태가 바뀌었는데 원래 digest가 유효하다.

재현: `test_catalog_schema_presence_drift`. 전체 파일 pin은 변경을 거부한다.
존재 여부를 함께 저장하거나 모든 지원 registry에 문자열 schema를 필수로 요구해야 한다.
표준 workflow catalog는 별도 validator가 이 입력을 거부하므로 **일반 selector API**의 결함이다.

### N6 / R1 — P1: wildcard 순회가 내부 symlink package를 건너뜀

위치: `harness/python_source_closure_v2.py:44-49`.

```text
entry.py: from pkg import *; print(child.COMMAND)
pkg/__init__.py: __all__ = ['child']
pkg/child -> ../child_impl
child_impl/__init__.py: COMMAND = 'STOP' -> 'MOVE'
```

`Path.rglob('*.py')`는 이 디렉터리 링크 안으로 내려가지 않는다. CPython은 pkg의 child
package를 해당 링크에서 찾지만 target source는 봉인 목록에 없다. 저장소 외부 경로는 없다.

재현: `test_wildcard_symlinked_child_package_drift`. `modules=['pkg.child']` 대조군도 둔다.
내부 링크의 순환·중복을 관리하며 탐색하거나 이런 wildcard 입력을 빌드 단계에서 거부해야 한다.

### N7 / R3 — P1: symlink script의 실제 import 폴더 누락

위치: `harness/execution_dependency_contract.py:148-153`,
`harness/python_source_closure_v2.py:15,31-37`.

```text
entry.py -> jobs/start.py
jobs/start.py: import helper; print(helper.COMMAND)
jobs/helper.py: COMMAND = 'STOP' -> 'MOVE'
entry_points = ['entry.py']
```

Python 파일 실행은 symlink를 해석한 jobs 디렉터리에서 sibling import를 찾지만 v2는
선언 문자열의 부모만 검색 폴더에 넣는다. source 내용 hash는 target을 따라가면서 import
검색 폴더는 따라가지 않는 불일치다. `sys.path`/`PYTHONPATH`를 바꿀 필요가 없다.

재현: `test_symlinked_script_sibling_import_drift`. 실제 target도 entry로 선언한 대조군을 둔다.
실제 실행 경로를 해석해 포함하거나 symlink script 진입을 명시적으로 거부해야 한다.

## 다섯 제외 범위는 번들에 기록되어 실행 때 검출되는가

**현재 v2 receipt에서는 그렇지 않다.** receipt 키는 `schema`, `declaration`,
`source_sha256`, `registry_entries`, `sha256`뿐이다. declaration에는 여섯 spec 필드만
허용하고 `environment`·`exclusions`·`admission`을 넣으면 거부한다
(`execution_dependency_contract.py:106-109,174-177`). 선언한 파일/모듈 목록은 봉인되지만,
빠뜨린 입력 목록·제외 사유·실환경 기대값·외부 admission 증거는 저장하지 않는다.

| 문서의 제외 | 현재 기록/검출 범위 | 남은 조건 |
|---|---|---|
| 문자열 subprocess worker | `entry_points`에 선언한 worker의 내용과 추적 가능한 import만 검사한다. 미선언 자식은 receipt에 없다. | 실제 생성 명령의 worker/주입 runner가 선언과 일치하는 등록·실행 검사 필요. |
| XML include/mesh/texture | `inputs`에 선언한 파일 내용만 검사하며 참조를 자동 탐색하지 않는다. | 모든 참조를 선언해도 N3처럼 경로 선택이 달라지는 경우를 막아야 한다. |
| registry defaults/참조 행 | selector로 추가한 값만 검사한다. | `policy.preset → presets.safe.command`의 끝 값을 바꾸는 추가 B1 반례는 미선언이면 통과하고 별도 selector 선언 시 거부한다. |
| live 환경 변수 | 값을 캡처/대조하지 않는다. 기대값 파일을 inputs에 넣어도 파일 해시만 남는다. | 비밀이 아닌 실제 실행 설정과 외부 기대값의 비교가 필요하다. 이번 재검토는 환경 변수를 변경하지 않았다. |
| Python/NumPy/MuJoCo 버전·플랫폼 | v2에 현재/기대 버전이 없다. 공통 manifest의 `environment_identity()`는 실제 값을 기록한다. | 기록과 드리프트 거부는 다르다. 패키지 업그레이드 시험은 하지 않았고 기존 identity mock은 설치 변경 증거로 세지 않는다. |

B1 재현: `test_registry_reference_chain_boundary`의 xfail 1개와 선언 대조군.
receipt의 실제 필드는 `test_v2_receipt_has_no_environment_or_exclusion_admission_fields`로 검사한다.
B1은 **이미 문서화된 제외**라서 새 자동 import 결함 7종에 합산하지 않는다.

실제 공통 환경 기록은 `sim/workflow_manager.py:120-128,467-478`에 있다.
현재 v6 경로의 `scripts/run_zone_pair_dev.py:69-70,120-122`는 등록된 장면/설정 environment를
확인하고, `:362-363`에서 설치 identity를 수집한다. 이를 Python/NumPy/MuJoCo 기대 버전과
실값의 비교로 간주해서는 안 된다. v2의 제품 호출자는 명시적 빌더/검증 CLI뿐이며 기존
실행 admission과 연결되지 않았다. 문서도 #292 연결을 후속 작업으로 남겼다.
따라서 제외 목록의 문서화는 **현재 번들의 실환경 드리프트 검출 구현**이 아니고 #292 실행 승인
근거로 사용할 수 없다. 이 미연결 자체를 새로 도입한 회귀로 세지는 않았다.

## 기존 봉인과 조용한 v2 선택

기준 commit blob, PR HEAD blob, 현재 checkout을 직접 비교했다. v6~v6e 등록 **5/5**,
RGB JSON **65/65**, 기존 closure/검증기/실행기 **6/6**이 바이트 동일하다.
현재 v6e 등록 소스의 hash도 **85/85** 일치한다. 전체 비교 목록과 hash는 로컬
`legacy-preservation-resume.json`, 재현 스크립트는 `audit_legacy_resume.py`에 있다.

`harness/`, `sim/`, `scripts/`, `config/`, `configs/`에서 v2 호출자를 검색했다.
제품 호출자는 v2 모듈과 명시적 `scripts/build_execution_dependency_contract.py`뿐이다.
기존 실행기에서 v2 import/fallback/migration 호출은 찾지 못했다. 옛 등록 JSON을 v2 API가
거부하는 검사, CLI가 기존 출력 파일을 덮어쓰지 않는 검사도 회귀 범위에 포함한다.
새 빌더의 기본 v2 선택과 기존 실행기의 조용한 v2 선택은 다르다.

## 실행 기록과 재현

최종 결과: **288 passed / 13 strict xfailed / 164.17 s**, 종료 코드 **0**.
301개 중 새 suite는 **14 passed / 13 xfailed**, 기존 8개 suite는 **274 passed**다.
기존 R1–R6 반례 10개도 통과한다. 예상하지 않은 failure/error, 일반 skip, XPASS는 없다.
시간은 검사 실행 기록이며 속도 비교가 아니다. xfail 13개는 새 누락 7종의 사례 12개와
문서화된 B1 경계 1개이고, 통과 수에 포함하지 않는다.

중단 전 초안의 24개 검사 결과는 최종 결과에 합산하지 않았다. 재개 후
`resume-validation-01`~`04`는 공용 잠금 점유로 pytest를 시작하지 않고 code 3으로 끝났다.
`resume-validation-05`는 잠금 대기 뒤 전체 301개를 한 번 실행했다. 검사 중 자기 잠금의
branch/PID를 기록했고 종료 코드 0 및 자기 잠금 반환을 확인했다. 다른 작업의 잠금·프로세스는
변경하지 않았다. 이후 수정은 보고서뿐이며 테스트 source는 아래 hash와 같다.

| 파일 | SHA-256 |
|---|---|
| `tests/test_seal_v2_review_301b.py` | `0b6c51f52f9400fb7fd836ebc22f037331a8fc20a052e059ae59036e063090da` |
| `resume-validation-05.log` | `c6472fb631cccc96d49f259d482622c045e825a9ae6133bbde1de566fb0ce1b7` |
| `resume-validation-05.xml` | `876626f15026f428f1f90fa1ed96ccebd8ffd87f3984f92b0cd8f8057ce04721` |
| `legacy-preservation-resume.json` | `f5bae5abb576a11a64842ba3ee007697c0952c84ad1c99db5c9422993c40efcb` |

상세 집계는 raw의 `resume-validation-05-summary.json`, 실제 잠금 취득 기록은
`own-validation-lock.json`이다. 로그에는 잠금 대기도 포함되지만 위 시간·분모는 실제 pytest
실행 결과다. `git diff --check`도 통과했다.


환경: 기존 Mac `.venv-sim-worker-mac`, Python 3.12.13, NumPy 2.5.2,
MuJoCo 3.12.0, pytest 9.1.1, macOS 27.2 arm64. 패키지 버전은 metadata로 조회했다.

```sh
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python - <<'PYTEST'
import os, sys
from scripts.run_ci_tests import local_lock_root, run_locked
files = [
    'tests/test_seal_v2_review_301b.py',
    'tests/test_execution_dependency_contract.py',
    'tests/test_seal_v2_review_301.py',
    'tests/test_seal_v2_fail_closed.py',
    'tests/test_zone_pair_registered_source.py',
    'tests/test_zone_study_source_pinning.py',
    'tests/test_zone_pair_v6.py',
    'tests/test_rgb_execution_bundle.py',
    'tests/test_ci_sharding.py',
]
env = {k: v for k, v in os.environ.items()
       if not k.endswith('_API_KEY') and k != 'GOOGLE_APPLICATION_CREDENTIALS'}
env.update(CI='true', PYTHONDONTWRITEBYTECODE='1')
raise SystemExit(run_locked([sys.executable, '-m', 'pytest', '-q', '-rx', *files],
                            env, local_lock_root()))
PYTEST
```

공용 잠금이 점유 중이면 code 3으로 끝나며 pytest를 시작하지 않는다. 새 반례를 일반 실패로
보려면 pytest 인자에 `--runxfail`과 대상 `-k`를 추가한다. 새 리뷰 파일은 제품의 CI 목록을
바꾸지 않았으므로 위처럼 명시적으로 지정한다. 기존 suite에는 작은 Python fixture를 실행하는
검사도 있으나 새 suite는 프로세스를 생성하지 않는다. 전체 저장소 CI 성공을 주장하지 않는다.

raw 경로: `/Users/changmin/projects/ugrp/outputs/review-301b-astra-e25d7509-20260930/`.
raw는 로컬 보관이며 보고서·테스트의 GitHub push와 구분한다. 물리·MuJoCo 모델 생성/step·
렌더·모델 호출·학습·과거 봉인 재작성·병합은 없다. 새 연구 실험 결과가 없어 TensorBoard
변환/서버 작업은 없으며, UGRP 예외에 따라 Drive도 사용하지 않는다.
