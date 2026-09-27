# PR #194 C3 BASE 잠금 회귀 수정 — 2026-09-27

기준 HEAD는 `eedc093116262d3985f42d9f2af32d681ed3effa`다. 테스트만 수정했으며
커밋·push·물리 실행·모델 호출은 하지 않았다. 새 연구 코호트나 TensorBoard 결과는 없다.

## 원인과 변경

`test_planning_packet_is_blocked_and_pins_current_c_policy_without_approving_it`의
수정 전 실패를 재현했다. C3 packet의 `base_component_sha256`은 과거 BASE의
파일 해시인데, 테스트는 일부 파일을 현재 작업 트리와 비교하고 있었다.

packet에 이미 기록된 `base_source_sha`는
`357e1f2e66dcae20c54f669711308ed18cf03966`이다. 이제 `git show <BASE>:<path>`의
바이트를 SHA-256으로 계산해 **기록된 10개 구성요소 전부**와 대조한다.
기존 검사에서 제외한 B/D 구성요소도 검사한다. BASE가 없으면 실패하며 현재 파일로
대체하거나 검사를 건너뛰지 않는다. `offline-regressions`는 이미
`fetch-depth: 0`으로 전체 이력을 받는다. 현재 C 정책·실행 차단·예산 검사는 유지한다.

`docs/research_parallel/c3-provider-packet.json`은 HEAD와 바이트가 같고 SHA-256은
`2b103933113666d25006fa1f557b50efc1fdbcdd773ee2748f8a7e9110f4d0f0`이다.
과거 해시나 기존 실행 번들을 갱신하지 않았다.

## 다른 고정 해시 검사 감사

저장소의 테스트·소스·설정·문서에서 두 파일 경로, BASE 필드, 과거/현재 해시를
검색했다. 테스트 전체의 64자리 해시 상수 및 `load_bundle`, `source_files_sha256`,
`source_identity`, `verify_registry_immutable` 사용처도 확인했다.

- 같은 원인으로 잘못 비교하는 추가 테스트는 찾지 못했다.
- R9의 공통 완료 정책 분리 및 R10의 채택/상류 미검증 정책을 반영한 현재 소스는
  이미 `rgb-standard-dispatch-v62`에 고정돼 있다. `gemini_proxy.py`의 과거 BASE는
  `4929db654deae9c505548f7f9665879681753549312a356581c2a90498dbeeee`,
  현재 값은 `1f9dd59c7280a80c4c51f361a0c8e92aef69ff54fd2e5e0f3fd37aacdce4ea2c`다.
- `llm_completion.py`의 현재 값은
  `6558a24b8b16d34672e29ae41dec364458e616b3e2662aace407745634a820d4`이며
  v62의 전체 소스 의존성 174개에 포함돼 있다.
- 과거 번들은 현재 소스와 대조하지 않고 보존하며 실행을 거절한다. R10 테스트의
  v61 파일 자체 고정 해시는 그대로 통과한다. 새 파일럿 manifest의 source identity는
  현재 파일에서 계산하고 R9/R10 테스트가 다시 대조한다.

## 검증

| 검사 | 결과 |
|---|---|
| 수정 전 실패 테스트 | 예상한 proxy 해시 불일치로 1 failed |
| provider budget·RGB bundle·R9/R10·Gemini 관련 6개 모듈 | 203 passed, 26 subtests passed, 1 deselected (28.68초) |
| BASE 파일 대조 | 10/10 일치 |
| 인메모리 반례 | 12/12 거절: 각 구성요소 해시 변조 10개, 없는 BASE 1개, 과거 proxy 해시를 현재 값으로 교체 1개 |
| `verify-current --id rgb-standard-dispatch-v62` | 통과, 번들 SHA-256 `6601192a6da7ac018dd3a7104364065bb9afb9dce0d61e79021f824648b07f69` |
| `verify-registry --base origin/main` | 통과, 로컬 원격 참조 기준 기존 번들 보존 |
| packet·두 runtime 파일·기존 번들 | HEAD 대비 변경 없음 |

실행 명령:

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_rgb_communication_provider_budget.py tests/test_rgb_execution_bundle.py \
  tests/test_zone_study_review_r9.py tests/test_zone_study_review_r10.py \
  tests/test_gemini_transport_policy.py tests/test_gemini_reasoning_effort.py \
  --basetemp=./.pytest_tmp -q \
  -k 'not existing_registry_bytes_cannot_change_or_disappear' \
  --junitxml=/private/tmp/pr194-base-lock-pytest.xml
```

제외한 `test_existing_registry_bytes_cannot_change_or_disappear`는 임시 Git 커밋을
생성한다. 사용자 요청에 따라 실행하지 않았고 실제 레지스트리를 읽기 전용 명령으로
검증했다. 모든 pytest에 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 적용했으며
종료 후 `.pytest_tmp`를 삭제했다. 사용자 허용 범위의 오프라인 검사만 잠금 없이 실행했다.
상세 해시·검색 대상·JUnit 요약은 [verification.json](verification.json)에 남겼다.

전체 CI를 다시 실행한 결과는 아니다. `git fetch`는 공용 Git 디렉터리 쓰기 제한으로,
`gh`는 네트워크 오류로 실패했고 GitHub connector도 저장소 접근 오류(422)를 반환했다.
원격 최신 PR/CI는 재확인하지 못했으며, 모든 검증은 위 로컬 HEAD와 미커밋 수정 기준이다.
