# P07 검증 기록

- 배정 경로: `/Users/changmin/projects/ugrp-wt/e2e-p07-manifest`
- 브랜치: `codex/run-manifest`
- 시작 HEAD/origin/main: `d17ca4345affef8cf027e121cf1f3197b36c23e0`
- 감사 main: `a8094cc14e098a55483f53a3c49bf6a0b116043d`
- 두 기준 사이 `harness/ sim/ scripts/ configs/ maps/` 변경 없음. 별도 작업의
  문서/기록 추가만 있으며 이 작업은 해당 SHA를 물리 재검증으로 해석하지 않는다.

AGENTS.md·README.md·docs/current_status.md·CONTRIBUTING.md, READINESS §4,
#254 초안, pair/multiturn draft, runner `run_bundle/check_run_source`, workflow,
pair v6/authorization/registered-source, study contract와 지정 테스트를 읽었다.
fetch와 열린 PR #285/#292/#293 및 #294의 feature 병합 상태를 확인했다.
조회한 head는 manifest의 `reference_pr_heads`에 역사적 참고로 기록한다.

## 검증 범위

실행한 것은 정적 JSON/AST/해시와 오프라인 테스트다. 물리 step·시뮬레이션·렌더·
비전 추론·LLM 호출·worker 시작·실제 DB 생성·봉인·병합은 수행하지 않는다.
새 실험 결과가 없어 TensorBoard 변환/서버/화면 기동은 해당하지 않는다. Drive 없음.

검사 대상은 다음 네 파일이다.

```text
tests/test_zone_e2e_manifest.py
tests/test_zone_study_source_pinning.py
tests/test_zone_pair_authorization.py
tests/test_ci_sharding.py
```

`test_zone_study_source_pinning.py::test_registered_speech_caps_and_llm_driver_are_pinned_in_the_run_bundle`
한 건은 실제 임시 SQLite DB를 생성하므로 이번 사용자 범위에 따라 **제외**한다.
이 테스트를 통과했다고 보고하지 않는다. 나머지 source/authorization 테스트는
런타임 진입을 가짜 객체로 막으며, GitHub 승인 조회도 fake를 사용한다.

Mac의 기존 Python3.12 환경에서 OMP/BLAS 스레드1로
`scripts.run_ci_tests.run_locked(..., local_lock_root())` 보호를 사용한다.
P03/#292가 보유한 공용 잠금 때문에 최초 호출은 **종료 코드3, pytest 미시작**이었다.
다른 잠금을 해제하거나 테스트를 우회하지 않았다.

첫 실제 pytest는 **258 passed / 1 failed / 1 deselected**였다(61.31초).
실패는 센서 ON 구성에서 동적 import 대상인 `sim/ultrasonic_input.py`가 소스
closure에 없던 경우다. `harness/ultrasonic_input.py::RUNTIME_MODULES`의 리터럴을
AST로 읽어 ON 구성의 closure에 넣도록 수정했다. runtime import는 추가하지 않았다.
첫 실패 JUnit도 보존하며 최종 통과 수에 합산하지 않는다.

이후 공개된 P01 v1 계약의 정적 reader와 기존 P03 provider 등록부 검사를 보완했다.
P01 파일이 배정 소스에 없으면 unavailable, 알 수 없는 스키마/변조 catalog·보정은
거절한다. 기존 v2 map allow-list만으로 v3 전체 조합을 허용하지 않는다.
최종 보호 pytest는 **267 passed / 0 failed / 1 deselected**, 83.78초로 통과했다.
2026-09-30 20:51:24 KST에 `codex/run-manifest`/PID94841가 잠금을 확보했으며
종료 후 자기 잠금을 해제했다. 최종 JUnit·실행 중 lock 원본은 아래 로컬 경로에 남겼다.
대기 중 종료 코드3 또는 자체 대기 중단130은 pytest 결과로 세지 않는다.
선별 명령은 `python -m pytest -q`에 위 네 파일,
`-k 'not test_registered_speech_caps_and_llm_driver_are_pinned_in_the_run_bundle'`,
`--junitxml=/tmp/p07-tests-final.xml`을 넘겼다.

[verification.json](verification.json)에 최종 검사 소스의 SHA-256, JUnit 및 보호
파일 목록 해시, 초안/요약 파일 해시를 기록했다. World/worker/network/process/DB/write
sentinel, 거짓 완료/승인, null/enum, 축소 분모, 재해시한 변조, source/map drift,
P01 catalog·보정 변조, v2/v3 거절과 기존 raw 충돌 반례를 포함한다.

자동 CI의 `ubuntu-simulation-runtime`, `ubuntu-simulation-scenarios`,
multi-object 장면 작업은 실제 물리/렌더를 시작한다
([workflow](../../.github/workflows/tests.yml)). 이번 사용자의 실행 금지를 지키기 위해
커밋에 `[skip ci]`를 사용한다. **전체 GitHub CI 통과 주장은 하지 않는다.**
이 PR은 draft/미봉인 상태이며 병합 관문을 우회하지 않는다.

## 보존과 공용 파일

- 기존 사전 등록/지도/시나리오/provider/bundle/workflow/모델/raw는 수정하지 않는다.
- 새 파일 외 공용 수정은 `scripts/run_ci_tests.py`의 P07 테스트 등록1행이다.
- bundle/workflow ID 예약 없음. #292의 v83/2.16.0는 참조만 한다.
- DRAFT 생성은 실행 승인/physical_ready가 아니다. 물리 준비 미충족 목록은
  [README](README.md)와 manifest의23개 claim에 기록한다.

2026-09-30 11:33 UTC 정적 대조에서 보호 대상60파일은 시작 SHA와 bytes가 같았다.
목록/해시와 최초 실패 JUnit 원본은
`/Users/changmin/projects/ugrp/outputs/e2e-p07-manifest/verification-20260930T1133/`에
보존한다. 로컬 보관이며 원격 raw 백업 주장이 아니다.

[manifest_DRAFT.json](manifest_DRAFT.json)은 runtime267파일·근거73파일·23claim을
연결한다. [dry_run_DRAFT.json](dry_run_DRAFT.json)은 다섯 출력 필드와37개 미충족
조건을 보존한다. 총 SIM cap212,250초는 제안이고 실제 실행량은0초다.
raw 목적지228개 및 계획 root는 생성되지 않았음을 확인했다. P01/P03 합성 전의
차단 상태이며 source/설정 합성 뒤에는 새 초안을 생성해야 한다.
