# v6h 봉인 전 중단 기록 (2026-10-01, Codex)

**판정: 봉인 불가 — 작업 지시 3번의 중단 조건 충족.** main 변경이 274개 고정 파일 중 4개에 걸친다. 어느 쪽 바이트도 채택하거나 되돌리지 않았으며, classifier/main 병합 자체를 시작하지 않았다. HEAD는 `4c6b439f3f7c9a147c901f8b260a1e214d4eb396` 그대로다. 이 기록은 미커밋 로컬 작업 기록이며 봉인 또는 실행 승인 기록이 아니다.

## 비교 기준과 검사

- 작업 브랜치: `codex/pair-v6h-register`, PR #292.
- 원본: `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`.
- fetch로 확인한 main: `318f03731b4c0ba649faccc0bedd6b14c5da6a97`.
- 원본/main 공통 조상: `a8094cc14e098a55483f53a3c49bf6a0b116043d`.
- 분류기 브랜치: `origin/claude/b-v6h-gain`, `1f0e4eb501a8f1b87077df943382fc1f0777dc69`.
- `candidate_contract('v6h')`의 274개 경로를 모두 `git show 4c6b439f:<path>`로 읽어 SHA-256을 다시 계산하고 현재 파일 및 candidate 해시와 비교했다. **274/274 일치**, `V6H_EXTRA_SOURCE_PATHS` 6개 모두 포함.
- 재현 스크립트: [verify_frozen_sources.py](verify_frozen_sources.py). 실행 결과 [frozen_sources.json](frozen_sources.json)에 각 파일의 원본/현재/preview 해시, main 변경 파일의 원본/main 해시와 변경 커밋을 보존했다. 종료 코드 **3**은 의도된 `STOP_MAIN_PIN_DRIFT`이다.

## main이 변경한 고정 파일

공통 조상 이후 main의 변경을 검사했다. PR #292에서만 추가한 변경을 main의 변경으로 잘못 세지 않았다.

| 파일 | main의 변경 성격 | 변경 커밋 |
|---|---|---|
| `harness/zone_main_budget.py` | `known_total()`이 `dict` 외 읽기 전용 `Mapping`도 받아 provider 토큰 사용량을 검증한다. | `380a676cf4a2613f062cc7853ed290766fe3652a` |
| `harness/zone_study_llm_driver.py` | provider 사용량을 필수로 표시하고, scheduler의 발송 후 재시도를 막기 위해 `max_retries=0`이 아닌 연결을 거절한다. | `8d01d02ca231181d95cc1706c026fe4e65f14e7b` |
| `harness/zone_study_llm_transport.py` | 본연구 응답·실패의 usage 판정에 엄격한 provider 카운터 검증을 적용한다. | `380a676cf4a2613f062cc7853ed290766fe3652a` |
| `scripts/agent_lock.py` | 잠금에 `timing_sensitive` 필드 및 `--timing-sensitive` 옵션을 추가하고 과거 잠금에는 기본 `False`를 적용한다. | `17be518e42b0436dca27726a4dd06ccaee54cfc0` |

물리 실행에서 실제 호출되지 않는 파일이더라도 이번 지시는 **274개 전부의 바이트 동결**이므로 임의로 예외 처리하지 않았다.

## 추가로 확인한 조건 충돌

봉인을 위해 고치라고 요청된 다음 파일도 274개 pin 안에 이미 있다.

- `scripts/zone_pair_v6_contract.py`: `CURRENT_REVISION='v6e'`이며 이것을 `v6h`로 바꾸거나 classifier pin을 추가하면 파일 해시가 달라진다.
- `experiments/2026-09-30-pair-v6h-carry/build_prereg_v6h.py`: 현재는 봉인을 쓰지 않는 preview 전용 builder다.
- 같은 실험의 `PREREG_DRAFT.md`, `REGISTRATION_PLAN.md`: disclosure를 추가하면 파일 해시가 달라진다.

따라서 main 변경 외에도 **274개 전부 동결**과 **위 파일을 수정해 봉인**은 현재 형태로 동시에 만족할 수 없다. 제어 실행 바이트와 봉인/분석 메타데이터의 변경 허용 범위를 조정자가 결정해야 한다. 이번 작업에서는 경계를 재정의하지 않았다.

분류기 incoming 브랜치에서 공통 조상 이후 변경했고 원본과 바이트가 다른 pin은 11개다. 이는 **병합 결과가 아니라 두 tip의 비교**다: 위 main 4개, 두 등록 문서, `make_confirmatory_placements.py`, `harness/pair_stage_probe.py`, `harness/zone_pair_door_relax.py`, `harness/zone_pair_progress_relax.py`, `scripts/run_pair_stage_probes.py`. 전체 목록은 JSON의 `classifier_incoming_different_pins`에 있다. 분류기 코드를 가져오기 위해 이 파일들을 조용히 덮어쓰지 않았다.

## 검증과 보존 범위

요청된 `tests/test_zone_pair_registered_source.py`, `tests/test_zone_study_source_pinning.py`를 기존 Python 환경에서 host lock 없이 실행했다. **57 passed (124.74초)**. 물리 step·실제 비전 worker·network 호출을 거절하는 기존 `tests.pose_provider_no_physics` 플러그인을 적용했고 각 시도 수는 모두 **0**이다. 결과는 [source_tests.txt](source_tests.txt), [source_tests.xml](source_tests.xml)에 보존한다. 봉인 후 회귀 통과가 아니라 변경 전 `4c6b439f`의 오프라인 소스 고정 회귀다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-30-pair-v6h-carry/analysis/seal_preflight/verify_frozen_sources.py
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q -p tests.pose_provider_no_physics tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py
```

블라인드 raw 경로의 목록·내용을 열지 않았고 결과를 계산하지 않았다. 물리·렌더링을 실행하지 않았다. 허용된 blinded-run 메타데이터도 이번 중단 판단에는 필요하지 않아 읽지 않았다. `.github/workflows`를 수정하지 않았으며 `/private/tmp`에 추출 디렉터리를 만들지 않았다. 신규 실험 결과가 없으므로 TensorBoard 변환·서버 작업은 없다. UGRP의 예외에 따라 Google Drive는 사용하지 않는다.

봉인 JSON, classifier 병합, main 병합, commit/push, CI, PR의 봉인 제목/본문 변경은 **미수행**이다. PR에는 [한국어 댓글 하나](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/292#issuecomment-5916797374)로 중단 사유를 전달했고 API 재조회로 본문 일치를 확인했다. PR #292는 OPEN, 원격 head도 `4c6b439f` 그대로이며 병합하지 않았다. 확인 영수증은 `PR_COMMENT_RECEIPT.json`에 있다.
