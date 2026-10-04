# UGRP 독립 검토 — 2026-10-03 고정 스냅샷

**검토 동결: 2026-10-03 17:53 UTC. 이 문서 PR은 당시 검토 기록을 보존하는 단일 역사적 스냅샷입니다.**

13개 본문(이슈 형식 4개·댓글 형식 9개)은 **확정 원고의 바이트를 그대로** 보존했습니다. 형식과 원래 게시 대상은 원고의 이력이며, 이 PR은 개별 이슈·댓글 게시를 실행하지 않습니다. 폴더의 2026-10-04는 전달 날짜입니다. 이번 PR은 문서만 추가하며 저장소 코드·설정·실험을 변경하지 않습니다.

| 검토 대상 | 동결한 SHA |
|---|---|
| main | `b23fc0875b72f4b55f399a252a1575b7e8b43cb5` |
| PR #363 | `73429982ea3088f2569c26cf7a4b5b74a1e6c1a6` |
| PR #371 | `1883c56a749dc89597d57f570d4a2243cbb9595d` |

**원문에 남은 “최신”, “현재”, “게시 전”은 위 동결 시점 또는 각 근거 메모에 적힌 검토 시점을 뜻합니다. 이후 main·PR head에 판정을 자동 적용하지 않습니다.** 일부 심층 검토는 이전 main `f2577bb5121748644df31eb0fc5a1c1b94b80d80`에서 수행했고, 최종 동결까지의 좁은 대조 범위는 [7차 현재성 기록](evidence/review-notes/round7-publication-currentness.md)에 명시했습니다. 이번 문서 PR을 준비하며 최신 main의 구현·실행을 다시 검증하지 않았습니다.

2026-10-04 게시 준비 중 GitHub head metadata를 읽어 #363이 `e05776b428e323d75115349f0b144684c50cfea5`로 진행한 사실을 확인했습니다. **이 원고는 #363 `73429982` 스냅샷에 한정하며, 이후 수정은 재검토하지 않았습니다.** main과 #371의 head 표시는 위 동결 SHA와 같았지만, 이는 metadata 대조이며 새 구현 검증이나 실행 결과가 아닙니다.

## 읽는 순서

1. [종합 검토·우선순위·검토 범위](publication/final-index-issue.md)
2. [동결 시점 blocker와 다음 진단](publication/final-round7-blocker-comment.md) → [실행·증거 신뢰성](publication/final-execution-issue.md)
3. [연구설계](publication/final-research-issue.md) → [추가 연구 세 축](publication/final-round7-research-comment.md)
4. 필요할 때 [선택·레거시 경로](publication/final-optional-issue.md), [13개 원문 전체 목록](publication/README.md), [선별한 7차 근거 목록](evidence/README.md)을 확인합니다.

## 동결 시점의 우선 문제와 인정한 개선

- **own_status 시각 혼용: P2.** #371 `1883c56`에서 gate의 absolute SIM 시각과 own-end의 reset-relative 전달 시각을 섞어 최신 사건을 잘못 선택할 수 있습니다. `no_comm`·`peer_nl` 양쪽 모델 입력의 의미 계약 문제이며 `rule`은 제외합니다. 실제 caller와 합성 반례를 확인했지만 native 실행 빈도·모델 행동·성능 영향은 확인하지 않았습니다. [독립 검증 §1](evidence/review-notes/round7-independent-validation.md), [PR #371 원문](publication/final-pr371-comment.md)
- **legacy SIM catalog: 현재 작업 우선순위 P3.** catalog가 무인자 횡이동에 speed65를 주입하지만 SIM validator는 31–40을 허용합니다. 직접 `sim_actions.run('move_left')`의 기본값35 호출은 이 반례에서 제외하며, 현재 pair #363/#371의 blocker가 아닙니다. [독립 검증 §3](evidence/review-notes/round7-independent-validation.md), [선택 경로 O16](publication/final-optional-issue.md)
- **해소·개선을 인정합니다.** #363 `73429982`의 staged loaded 이력 복원과 공용 `zone_pair_vision.py`의 main 바이트 복구를 확인했습니다. 이는 전용 gate/둘러보기의 전체 인수나 운반 성공 확인은 아닙니다. #371의 live/model_usage·이미지 청구·own_status·idle-only look 추가도 인정하며, 예전의 비용 전체 소실/이미지 비용 미연결 주장을 최신에 적용하지 않습니다. [최신성 대조](evidence/review-notes/round7-publication-currentness.md), [PR #363 원문](publication/final-pr363-comment.md), [PR #371 원문](publication/final-pr371-comment.md)

## 동결 시점 blocker → 다음 작은 진단

#363 공개 DEV 요약은 opening look/합류 통과를 보고합니다. 과거 rendezvous를 현재 첫 blocker로 반복하지 않습니다. 이는 **저자의 공개 보고이며 raw 독립 확인이나 운반 성공 재현이 아닙니다.**

| 공개 보고의 현재 경계 | 다음에 구분할 것 |
|---|---|
| approach의 `PAIR_COLLISION_GUARD` | 첫 거절 branch·발행 전 candidate·wall·raw/reserve clearance |
| align의 wait_close, `BEAM_UNCERTAIN → PREGRASP_NOT_READY` | 마지막 standoff→첫 wait_close의 frame/명령 일치와 단계별 RGB support; 직전 점9911은 현재 점0을 대신하지 못함 |
| HIGH staged의 `gate_ok=false`, 명령·accepted measurement0 | 입장 전 worker 미호출 / frame 거절 / scan 비정보성 구분 |

동시에 남아 있는 같은-tick peer abort 뒤 non-hold dispatch는 offline 최종 veto/hold 경계로 따로 확인합니다. 진단을 실제 실패 원인이나 수정 완료로 단정하지 않습니다. [진단 근거·판별 기준](publication/final-round7-blocker-comment.md), [실행 계약](evidence/review-notes/round7-runtime-contracts.md), [abort 재현 기록](publication/final-peer-abort-reproduction-comment.md)

## 연구 검토의 세 축

1. **통신 × 선택적 재관측:** 권한 배정의 total policy 효과와 상호작용을 구분합니다. 실제 look 횟수로 사후 분류한 비교를 직접효과로 해석하지 않습니다.
2. **준비 근거의 유효기간:** 메시지 발화·software validity·physical truth를 나눕니다. 기존 TTL/barrier 방어를 인정하며 finite trace 통과를 모든 가능한 실행에 대한 지식 증명으로 확대하지 않습니다.
3. **평가 대상 구분:** 고정 artifact F, 선택한 witness 분포 W, 후보 선택절차 P를 구분합니다. F와 W는 겹칠 수 있으며, 새 seed만으로 선택 분포 밖 일반화가 보장되지는 않습니다.

[추가 연구 본문](publication/final-round7-research-comment.md) · [primary 근거 메모](evidence/review-notes/round7-primary-evidence.md) · [독립 QA](evidence/review-notes/round7-independent-validation.md). 새 연구 결과·효과크기를 추정하거나 DEV를 새 실험 때문에 중단하자는 제안은 아닙니다.

## 검토 한계와 파일 사용

tracked tree/Python 1,585개 AST inventory와 **선택한 경계의 심층 검토**입니다. 약 38만 LOC의 전줄 정독·전체 테스트 실행 완료가 아닙니다. source·합성 fixture·제한된 표적 검증을 사용했으며 **새 physics/렌더/LLM/학습/실기기 실험 및 raw·heldout outcome 열람은 없었습니다.** 고정 main `b23fc087`, #363 `73429982`, #371 `1883c56` 이후 변경에 자동 승계하지 않습니다. [범위와 제외 사항](publication/final-index-issue.md), [7차 coverage](evidence/review-notes/round7-coverage-audit.md)

이 PR에는 13개 확정 원고, 선별한 7차 근거 Markdown 8개, 탐색용 README 3개만 포함합니다. 이전 차수의 전체 작업 메모, Python·재현 스크립트, raw·fixture·JSON·바이너리는 포함하지 않습니다. 원고와 근거 메모의 코드 블록·수치는 당시 기록이며, 이 PR에서 재실행한 결과가 아닙니다. 새로운 physics·렌더·LLM·학습·실기기 실험이나 raw·heldout outcome 검토를 수행하지 않았습니다.

**절대경로는 당시 검토 환경의 역사적 provenance(출처 이력)입니다.** 원문에 남은 `/workspace/...`, `/tmp/...` 등의 경로, 스크립트·로그·manifest 파일명과 검색 참조 ID는 과거의 증거 위치를 설명하며, 이 PR에 해당 파일이 포함되거나 현재 환경에서 실행·접근 가능함을 뜻하지 않습니다. 이 문서 묶음 안의 탐색은 [원문 목록](publication/README.md)과 [선별 근거 목록](evidence/README.md)의 상대링크를 사용하세요.

13개 원고와 8개 근거 Markdown은 로컬 전달본과 바이트가 같은지 확인했고, 세 README만 문서 PR의 범위·탐색에 맞게 편집했습니다. 보존한 원문이 해소된 과거 문제를 다시 현재 결함으로 주장하는 것으로 읽히지 않도록, 최종 원고와 [현재성 대조](evidence/review-notes/round7-publication-currentness.md)를 함께 읽으세요.
