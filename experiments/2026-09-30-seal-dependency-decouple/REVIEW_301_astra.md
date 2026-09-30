# PR #301 독립 반례 검토

판정: **BLOCK**. v2를 제어기 동작의 완전한 봉인으로 사용하면 안 된다. 자동 import 추적 안에서도 동작이 달라졌는데 원래 digest가 계속 유효한 경로가 있다. 기존 봉인 보존과 새 v2 계약의 건전성은 별개다. 확인한 결함은 **BLOCKER 2건, MAJOR 4건**이며, 문서화된 선언·환경 경계는 따로 기록한다.

- 검토 대상: `2ff92e9fbeff1b90b0aa35104a9766753e67f94e`, `codex/seal-dependency-decouple`, PR #301.
- 비교 기준: merge base `d17ca4345affef8cf027e121cf1f3197b36c23e0`.
- 검토 브랜치: `codex/review-301`. 이 검토에서는 제품 소스·등록·봉인을 수정하지 않는다.
- 범위: 소스 독해, 임시 폴더의 작은 Python 프로그램, JSON/XML 변조, 기존 오프라인 회귀. 물리·MuJoCo 모델 생성/step·렌더·모델 요청·학습·병합 없음.

## 재현 방식

`tests/test_seal_v2_review_301.py`는 변경 **전** receipt와 외부 기대 digest를 저장한다. 같은 프로그램을 독립 Python 프로세스에서 실행하여 출력 변화를 확인하고, 그 뒤 원래 기대 digest로 `verify_contract`가 변경을 거부해야 한다고 검사한다. pyc를 만들거나 재사용하지 않아 타임스탬프 캐시로 결과가 섞이지 않는다.

실제 누락은 `strict=True, raises=SealAccepted` xfail이다. 초기화 실패, import 실패, timeout 등 다른 오류는 xfail에 숨지 않는다. xfail은 결함 재현이며 통과나 수정 완료가 아니다. B1/B2는 아래에 명시한 선언·admission 경계이며, R1–R6의 추적 결함과 구분한다.

## 발견 사항

### R1 — BLOCKER: `from pkg import *`로 자동 로드되는 하위 모듈을 누락한다

위치: `harness/python_source_closure.py:69-72`, 새 호출 지점 `harness/execution_dependency_contract.py:162`.

최소 반례:

```python
# entry.py
from pkg import *
print(child.COMMAND)
# pkg/__init__.py
__all__ = ['child']
# pkg/child.py: 봉인 뒤 STOP을 MOVE로 수정
COMMAND = 'STOP'
```

`entry.py`, `pkg/__init__.py`는 고정하지만 Python이 `__all__`에 따라 가져오는 `pkg/child.py`를 고정하지 않는다. 파일 하나를 바꾸면 출력은 STOP → MOVE인데 원래 v2 receipt가 통과한다. `__init__`의 일반 부수 효과를 고정하는 기존 검사로는 막히지 않는다. `eval`이나 사용자 loader가 필요 없는 정상 import 문법이다.

재현: `test_star_import_child_changes_command_without_invalidating_seal`.

수정 조건: 새 v2 경로에서 `__all__`의 로컬 하위 모듈을 보수적으로 포함하거나, 분석할 수 없는 wildcard import를 명시적으로 거부한다. 기존 closure 파일 자체를 바로 고치면 오래된 봉인도 바뀌므로 legacy 경로를 보존해야 한다.

### R2 — BLOCKER: 일반적인 동적 import 간접 호출을 추적하지도 거부하지도 않는다

위치: `harness/execution_dependency_contract.py:97-115`, `170-176`.

다음 네 줄거리 모두 `plugin.py`의 `COMMAND = 'STOP'`을 `'MOVE'`로 바꾸면 동작이 달라지지만 v2는 이를 놓친다.

```python
import importlib
load = importlib.import_module
mod = load('plugin')
# 또는 mod = getattr(importlib, 'import_module')('plugin')
# 또는 from builtins import __import__ as load; mod = load('plugin')
# 또는 import builtins; mod = builtins.__import__('plugin')
print(mod.COMMAND)
```

`dynamic_imports={}`인 채로 build와 verify가 성공한다. 직접 `importlib.import_module` 호출은 잡으면서 함수 대입 별칭·문자열 getattr·builtins 별칭은 탐지 대상에서 사라진다. 문서 `docs/execution_versioning.md:44-48`의 일반 별칭 추적 및 불명확한 경계 거부를 충족하지 못한다. 특히 `from builtins import __import__ as load`는 임의 코드 실행이 아닌 일반 import 별칭이다.

재현: `test_dynamic_loader_changes_command_without_invalidating_seal`의 네 매개변수.

수정 조건: 지원하는 별칭/문자열 getattr를 따라가거나 미해결 loader 참조를 v2 생성 단계에서 거부한다. 단순히 직접 호출만 검사하고 “동적 import가 없다”고 판단하면 안 된다. 선언된 모듈 목록도 가능한 분기 전체를 검토해야 하며, 파일당 선언 한 개가 다른 미해결 호출의 안전성을 증명하지 않는다.

### R3 — MAJOR: 파일로 실행하는 script의 같은 폴더 import를 root 기준으로만 찾는다

위치: `harness/python_source_closure.py:25-30`, `56-58`; `harness/execution_dependency_contract.py:128-129`.

`jobs/entry.py`는 `import helper; print(helper.COMMAND)`, `jobs/helper.py`는 `COMMAND='STOP'`이다. `entry_points=['jobs/entry.py']`로 봉인하고 `python -B jobs/entry.py`로 실행한다. helper만 MOVE로 바꾸면 Python은 변경을 읽지만 closure는 저장소 루트의 `helper.py`만 찾아 원래 봉인이 통과한다.

재현: `test_script_directory_import_changes_command_without_invalidating_seal`.

영향 범위: 파일 경로로 시작하는 script/자식 프로세스 경로. 항상 저장소 루트에서 `python -m jobs.entry`를 사용하는 경로에 이 반례를 적용했다고 주장하지 않는다. 그러나 현재 spec에는 실행 방식·import 경로 계약이 없고 파일 entry를 받아들인다.

수정 조건: 실행 형태와 import 검색 경로를 봉인에 포함하여 해석하거나, 지원하지 않는 직접 script 진입을 거부한다. 기존 AST가 저장소 루트에서 못 찾은 이름을 모두 외부 패키지라고 간주해서는 안 된다.

### R4 — MAJOR: 선택한 JSON 값의 객체 순서를 지워 실행 의미 변화가 사라진다

위치: `harness/execution_dependency_contract.py:27-29`, `90-91`, `203-204`.

`registry.json`의 선택된 `policy.commands`를 `{"STOP":0,"MOVE":1}`에서 `{"MOVE":1,"STOP":0}`로 바꾼다. 소비 코드는 `json.loads` 후 `next(iter(row['commands']))`를 실행한다. 첫 명령은 STOP → MOVE로 바뀌지만 canonical hash와 Python dict 동등 비교는 모두 순서를 무시하므로 같은 봉인이 통과한다. 누락된 파일이나 selector가 없는 반례이며 **선택 행 내부** 변경이다.

재현: `test_selected_entry_key_order_changes_first_command_without_invalidating_seal`.

수정 조건: 선택 값의 key 순서를 보존하거나, 항목 pin을 사용할 registry의 소비 코드가 같은 canonical 표현만 읽도록 제한하고 검증한다. JSON 객체를 의미상 무순서로 취급하려면 실제 실행기도 그 계약을 따라야 한다. 현재 UGRP workflow 행이 이 순서에 의존한다는 주장은 하지 않는다. 일반 selector API의 보장 범위 결함이다.

### R5 — MAJOR: 실제 workflow 소비자는 선택하지 않은 행에도 의존한다

위치: `harness/execution_dependency_contract.py:78-85`, 실제 소비자 `sim/workflow_manager.py:163-180`.

실제 `workflow_manager._row`는 선택 행을 돌려주기 전에 **모든** 행의 id 중복·필수 필드·entry 파일 존재를 검사한다. `used`와 `unused`가 있는 유효한 catalog에서 used만 pin하고, unused의 entry를 존재하지 않는 `missing.py`로 바꾸거나 unused 행을 복제한다. 선택 행은 동일하지만 공통 실행기는 각각 `workflow entry missing`, `distinct workflows`로 시작을 거절한다. v2의 selector는 used에 해당하는 행만 검사하므로 이 소비 의존성을 표현하지 못한다. 두 변조 모두 원래 외부 digest로 검증이 통과했다.

재현: `test_unselected_workflow_row_can_disable_selected_workflow`의 두 매개변수. manager 소스도 명시적으로 entry point에 넣어 runner 누락과 분리했다. 실제 `_row` 함수만 호출하며 프로세스/물리를 시작하지 않는다.

수정 조건: v2 검증과 실제 소비자가 같은 catalog 유효성 규칙을 사용하도록 하거나, 새 실행 경로가 검증한 선택 slice만 소비하도록 바꾼다. 유효한 무관 행 편집을 허용하는 것은 유지할 수 있다. 기존 whole-file admission을 끄기 전에 이 차이를 해결해야 한다.

### R6 — MAJOR: `workflow_spec`이 공통 launcher를 항상 고정하지 않는다

위치: `harness/execution_dependency_contract.py:213-227`; 빠지는 부모 실행기 `sim/workflow_manager.py:357-383`.

실제 `communication` workflow의 `entry`/`runner`로 만드는 closure를 임시 폴더에 복사한다. 이 선택에서 `workflow_spec`은 실행 대상만 root로 넣으며, 대상을 subprocess로 실행하는 공통 manager는 자동 root가 아니다. manager의 반환 명령을 `[python, '-m', runner, ...]`에서 `[python, '-m', 'alternate', ...]`로 바꾼 결과, 선택된 호출 대상이 `scripts.evaluate_rgb_communication` → `alternate`로 달라졌지만 원래 외부 digest의 검증은 통과했다.

재현: `test_real_communication_workflow_omits_standard_launcher`. 실제 catalog 행·전이 소스와 `_runner_command`를 사용한다. 생성된 명령의 변화만 확인하며 해당 명령을 실행하지 않는다. 기존 222-source fixture에 manager가 들어간다는 사실을 모든 workflow로 일반화할 수 없다.

수정 조건: 표준 관리 workflow 계약은 공통 launcher와 필요한 표준 CLI를 필수 root로 넣거나, 명시적 launcher 선언이 없으면 완전한 workflow 계약으로 생성하지 않는다. 자식에서 부모를 역으로 import할 때 우연히 포함되는 것에 의존해서는 안 된다.

## 선언·실행 승인 경계: API가 자동으로 보장하지 않는 부분

이 항목은 PR 문서가 이미 호출자 책임으로 둔 부분이다. 단순한 선언 누락을 전이 import 구현의 새로운 회귀라고 세지 않는다. 다만 “동작을 바꾸는 모든 편집은 봉인을 깨뜨린다”는 전체 목표와 #292 도입 승인에는 반드시 별도 입증이 필요하다.

| 검사 항목 | 반례 또는 확인 | 해석 |
|---|---|---|
| JSON/map/YAML/XML/MJCF 파일 | 읽는 값 STOP → MOVE; `inputs=[]`이면 원래 봉인 통과, 같은 파일을 `inputs`에 넣으면 거부 | B1: 실제로 읽는 파일 전체를 선언해야 한다. YAML fixture는 단일 scalar를 읽는 작은 소비자이며 YAML parser 전체의 검증이 아니다. |
| NumPy NPZ | `np.load('fit.npz')['gain']`의 1 → 9; 미선언이면 통과, 선언하면 거부 | B1: 모델/보정 파일 이름이 source에 있어도 자동 pin되지 않는다. |
| MuJoCo include/asset | 상위 `scene.xml`만 선언하고 `<include file='assets/body.xml'>`의 값을 변경하면 봉인 통과 | B1: 모든 include·mesh·texture까지 선언해야 한다. XML로 파일 참조 의미만 재현했으며 MuJoCo를 실행하지 않았다. |
| registry 공용 defaults | 선택 행은 그대로 두고 소비자가 fallback으로 읽는 `defaults.command`를 STOP → MOVE로 바꾸면 통과 | B1: 기본값/다른 참조 행도 selector에 포함해야 한다. |
| subprocess script | source는 그대로이고 문자열로 실행되는 worker의 STOP → MOVE가 통과 | B1: worker를 별도 entry로 선언해야 한다. |
| runner monkeypatch | `entry.COMMAND`를 덮는 runner를 누락하면 LEFT → RIGHT가 통과; runner를 선언하면 거부 | B1: policy만 고정해도 runner의 주입을 막는 것은 아니다. |
| 환경 변수 | 같은 소스로 `REVIEW_301_COMMAND=STOP` → `MOVE`인데 digest 동일 | B2: live 환경 값을 외부 등록과 실행 승인에서 비교해야 한다. |
| Python/NumPy/MuJoCo 버전 | `environment_identity()`의 세 버전 응답을 시험용 값으로 바꿔도 v2 검증 결과 동일 | B2: 실제 설치 교체가 아닌 identity seam 시험이다. v2는 버전을 해시/비교하지 않는다. `sim/workflow_manager.py:120-128`은 수집 함수이며 그 자체로 거부 관문은 아니다. |
| package 초기화·함수 안/조건부 import | 초기화 부수 효과나 상대 import 대상이 바뀌면 봉인 거부 | 정상 경로는 유지된다. R1/R2를 이 양성 대조로 구분했다. |
| 표준 workflow runner·scene | 기존 PR의 실제 UGRP fixture는 `sim/workflow_manager.py`, `sim/session_scenes.py`, ArmSequence/provider를 요구한다 | 해당 fixture의 closure 검사이며 모든 workflow가 완전하다는 증거는 아니다. |
| render profile | 실제 `sim.render_profile.apply_xml` 코드의 castshadow false → true 변경은 소스 pin이 거부한다 | XML 변환만 실행했다. `scripts/run_pair_stage_probes.py:426-428`의 profile **선택값**, case/CLI, scene/자산까지 선언하는 일은 별도다. 물리·영상 결과는 확인하지 않았다. |

관련 실제 데이터 소비 지점: `harness/owncam_carry_v6e.py:70-71,97-98`(fit JSON), `sim/session_scenes.py:116-121,134-155`(지도·suite 및 참조 파일). 이들을 담은 Python 파일을 pin하는 것만으로 파일 내용이 pin되지는 않는다.

B1/B2 테스트의 xfail은 문서화된 경계를 재현한 것이다. 임의 입력 탐색을 완전 자동화하라는 요구가 아니다. 새 등록 빌더가 필요한 파일·선택값·환경 비교를 빠짐없이 구성하고, 빠뜨린 등록은 실행 승인 전에 거부한다는 인수 검사가 필요하다. 기존 HEAD/dirty/승인 관문을 유지해야 하며, 이번 테스트는 그 관문까지 통과해 로봇을 실행했다는 뜻이 아니다.

## 기존 봉인과 자동 v2 전환

독립 실행한 검사에서 다음을 확인했다.

- v6/v6b/v6c/v6d/v6e 등록 JSON **5/5 바이트 동일**.
- 기존 RGB registry JSON **65/65 바이트 동일**.
- `harness/rgb_execution_bundle.py`, `harness/python_source_closure.py`, `scripts/zone_pair_v6_contract.py`, `scripts/zone_pair_registered_source.py`, `scripts/run_zone_pair_dev.py`, `scripts/run_zone_study_integration.py`도 기준 commit과 바이트 동일.
- 현재 v6e의 소스 **85/85 hash 일치**, 등록/scene 계약 동등성 검사 통과.
- 실제 옛 등록과 그 내부 계약을 새 API에 전달하면 각각 명시적 v2 spec/legacy verifier 오류로 거부한다.
- 관련 suite가 v3~v5h 역사 감사, v6~v6d commit blob 감사, 현재 v6e 및 RGB 번들의 기존 검사도 수행했다. 이 통과를 역사 등록의 현재 실행 승인으로 해석하지 않는다.

검색상 v2의 새 runtime 호출자는 CLI와 새 테스트뿐이다. 기존 v6/RGB 실행기에서 v2를 조용히 선택하는 fallback이나 migration 경로는 발견하지 못했다. “기존 등록이 보존됐다”와 “v2를 기존 admission에 연결했다”는 다른 결과다.

## 실행 기록

기존 Mac `.venv-sim-worker-mac`, Python **3.12.13**, NumPy **2.5.2**, MuJoCo **3.12.0**, pytest **9.1.1**, macOS **27.2 arm64**. 패키지 버전은 metadata 조회이며 MuJoCo를 실행하지 않았다. 첫 실행은 **226 passed / 12 xfailed / 75.30 s**였다. 이 가운데 새 검토 suite는 22 passed / 12 xfailed, 나머지 기존 관련 suite는 **204 passed**다. 시간은 검사 기록이며 성능 비교가 아니다.

| 관련 파일 | 통과 수 |
|---|---:|
| `test_execution_dependency_contract.py` | 33 |
| `test_zone_pair_registered_source.py` | 22 |
| `test_zone_study_source_pinning.py` | 33 |
| `test_zone_pair_v6.py` | 43 |
| `test_rgb_execution_bundle.py` | 7 |
| `test_ci_sharding.py` | 66 |

추가 사례를 포함한 최종 검토 suite는 **23 passed / 15 xfailed / 6.14 s**, 종료 코드 0이다. xfail 15개는 **R1–R6 결함 재현 10개 + 문서화된 B1/B2 경계 재현 5개**다. 기존 관련 204개와 최종 검토 38개를 구분하며, 첫 실행과 두 번째 실행의 중복 사례를 합산하지 않는다. 최종 테스트 파일 SHA-256은 `802873685f94d6ae23eb8a1dd3e261e1c43c1e1f159c2105c7a7ce5504086e3f`다.

재현 명령(이 worktree에서, Mac 공용 잠금 확보 후 실행; 점유 중이면 code 3으로 끝남):

```sh
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python - <<'PYTEST'
import os, sys
from scripts.run_ci_tests import local_lock_root, run_locked
files = [
    'tests/test_seal_v2_review_301.py',
    'tests/test_execution_dependency_contract.py',
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

실제 첫 실행은 위 7개 파일, 두 번째 실행은 최종 `test_seal_v2_review_301.py`만 재실행했다. 확인된 반례를 예상 실패 처리 없이 보려면 같은 명령의 pytest 인자에 `--runxfail`과 대상 `-k`를 추가한다. 리뷰 산출물만 추가했고 기존 CI의 `TEST_PATTERNS`는 변경하지 않았으므로 새 파일은 위 명시적 명령으로 실행해야 한다. GitHub CI 통과나 전체 저장소 회귀 통과를 주장하지 않는다.

원본 로그/JUnit은 `/Users/changmin/projects/ugrp/outputs/review-301-astra-2ff92e9f-20260930/`에 보존했다. 이 raw는 로컬 보관이며 Git 원격 백업이라고 표현하지 않는다.

| 파일 | SHA-256 |
|---|---|
| `pytest-01.log` | `2136a9ab13d40bbbde5c28ee71580b3d61122bbb3c6b202543ce203d528bc35a` |
| `junit-01.xml` | `1c359bb4553e9af52ce6d0fcec231d8dadcdb746d5f0edcb5748b37f9f8e631e` |
| `pytest-02.log` | `801032f9545cc6c4a0f93aca87cf4b65c83b622933a70e5532c560cb4094d075` |
| `junit-02.xml` | `9872680f8caed1e69fbb8973454ea17b65c34acf98c024c48ab123e3834b9b4a` |

두 실행 모두 `scripts.run_ci_tests.run_locked`의 잠금 획득·자식 종료·자기 잠금 반환을 확인했다. 공용 잠금의 다른 소유 작업을 중단하거나 풀지 않았다. 원본/봉인/학습 모델은 변경하지 않았다. 새 연구 실험 결과가 없으므로 TensorBoard 변환·화면 작업은 하지 않으며, UGRP 예외에 따라 Google Drive 작업도 없다.

## 다시 검토할 조건

R1–R6를 고치거나 허용 문법/소비자 계약에서 명시적으로 거부하고 위 반례가 정상 회귀 검사로 통과해야 한다. B1/B2는 #292의 실제 registration/admission 결합에서 완전성을 검증해야 한다. 예전 봉인을 바꾸는 공용 함수 수정 대신 새 v2 전용 경로를 사용하고, 기존 역사 감사·현재 v6e·RGB 검사를 다시 통과해야 한다. 그 전까지 **BLOCK**, 물리 실행이나 #292 봉인 승인은 없다.
