봉인 전 검사에서 조정자 지시 3번의 **중단 조건**을 확인했습니다. classifier/main 병합을 시작하거나 커밋하기 전에 멈췄습니다. HEAD는 `4c6b439f3f7c9a147c901f8b260a1e214d4eb396` 그대로이며 어느 쪽 소스도 조용히 채택·복원하지 않았습니다.

`V6H_EXTRA_SOURCE_PATHS` 6개를 포함한 **274개 pin 전부**를 `git show 4c6b439f:<path>`의 바이트로 SHA-256 재계산했습니다. **274/274 현재 파일·preview 해시 일치**입니다. 그러나 fetch한 main `318f03731b4c0ba649faccc0bedd6b14c5da6a97`은 공통 조상 `a8094cc14e098a55483f53a3c49bf6a0b116043d` 이후 다음 4개 pin을 변경했습니다.

| 고정 파일 | main 변경 |
|---|---|
| `harness/zone_main_budget.py` | `known_total()`이 읽기 전용 `Mapping` 사용량도 검증 (`380a676c`) |
| `harness/zone_study_llm_driver.py` | provider 사용량 필수 표시, `max_retries=0` 강제와 발송 후 scheduler 재시도 거절 (`8d01d02c`) |
| `harness/zone_study_llm_transport.py` | 응답·실패의 usage 판정을 엄격한 provider 카운터로 통일 (`380a676c`) |
| `scripts/agent_lock.py` | `timing_sensitive` 잠금 필드와 CLI 옵션 추가 (`17be518e`) |

추가 조건 충돌도 있습니다. `scripts/zone_pair_v6_contract.py`, `build_prereg_v6h.py`, `PREREG_DRAFT.md`, `REGISTRATION_PLAN.md` 자체가 274개 pin 안에 있습니다. 따라서 **모든 pin 바이트 동결**과 **CURRENT_REVISION 변경·builder 봉인 기능·문서 disclosure 추가**는 현재 형태로 동시에 만족할 수 없습니다. 조정자 결정 없이 이 파일들을 동결 대상에서 빼지 않았습니다. incoming classifier 브랜치 `1f0e4eb5`에도 원본과 다른 pin 11개가 있어 그대로 병합하지 않았습니다(두 tip 비교이며 실제 병합 결과는 아님).

요청한 두 회귀 파일 `tests/test_zone_pair_registered_source.py`, `tests/test_zone_study_source_pinning.py`: **57 passed (124.74초)**. 기존 no-physics 플러그인으로 physical step / 실제 vision worker / network 시도 **0 / 0 / 0**을 확인했습니다. host lock 없이 실행한 변경 전 소스 검사이며 봉인·물리 성공 증거가 아닙니다.

파일별 전체 해시, 재현 스크립트, main 변경 커밋, JUnit과 중단 보고서는 worktree의 `experiments/2026-09-30-pair-v6h-carry/analysis/seal_preflight/`에 **미커밋 로컬 기록**으로 남겼습니다. 블라인드 raw는 목록·내용 모두 접근하지 않았고 결과도 계산하지 않았습니다. `.github/workflows` 수정 및 `/private/tmp` 추출 디렉터리 생성은 없습니다.

봉인 JSON·classifier/main 병합·commit/push·새 CI는 미수행입니다. 봉인을 완료하지 못했으므로 제목/본문을 “봉인 — 독립 검토 필요”로 바꾸지 않았습니다. PR #292는 병합하지 않았습니다.
