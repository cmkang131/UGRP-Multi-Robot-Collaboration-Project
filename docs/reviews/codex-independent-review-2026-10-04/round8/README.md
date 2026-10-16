# UGRP 8차 독립 검토 — 2026-10-04

**현재 경로에서 새로 재현한 문제 3개, 표준 연구 평가에서 1개를 찾았습니다. 기존 peer-abort 문제는 최신 코드에서도 남아 있고, #363의 start-relief 수정은 알려진 반례를 실제로 차단합니다.** 아래 판정은 명시한 SHA와 합성 검증 범위에 한정합니다.

**전달 직전 #371 갱신 반영:** 새 `a009112f`는 이전 own_status 시간축과 `__CHARS__` prompt slot 문제를 고쳤습니다. [수정 검증](frontier-followup.md)을 우선하세요. 새 비용·finalization finding의 관련 경로는 바이트/AST 동일하여 유지됩니다([좁은 최신성 대조](runtime-currentness.md)).

| 우선순위·구분 | 대상과 확인한 사실 | 다음에 확인할 작은 경계 |
|---|---|---|
| **P2 · 신규 · 현재 모델 경로** | #371 전송 뒤 실패 시 image 2×1490 SIM token이 빠집니다. 정상/잘못된 schema 응답에는 포함됩니다. | request의 image 포함 bill과 exception Attempt를 대조하고 정상·invalid·post-send error·pre-send failure를 함께 확인 |
| **P2 · 신규 · 현재 결과 기록 경로** | #371 단일 finalization 오류가 `status=HOST_ERROR`로 남아도 `failure_class=None`, budget run `finished`로 기록될 수 있습니다. | 본 실행·기록·정리 단계의 실패 분류를 일치시키되 요청 뒤 재실행 금지와 공급자 비용 보존은 유지 |
| **P2 · 신규 · 현재 HIGH 경로** | #363 beam mask가 ROI 바닥 밖으로 이어지면 crop의 마지막 행을 실제 edge로 인정합니다. ±0.04인 합성 edge 둘 다 slope≈0, 90 inlier, tracker available이 됩니다. | 마지막 채택 row 다음에도 foreground가 이어지는지, 관측한 경계와 잘린 run을 구분 |
| **P2 · 신규 · 표준 zone-study 평가** | 동일한 과거 발화가 미래 물체 이동에 따라 truthful_share 1→0→1로 바뀝니다. 종료 배송률은 이 반례에서 정상입니다. | final standing과 발화 시각의 truth evidence를 별도로 만들어 미래 suffix 변경에 과거 판정이 불변인지 확인 |
| **기존 지적 · 현재도 재현** | #363 같은 tick peer abort 뒤 미리 모인 non-hold 명령이 issue됩니다. 다음 0.05초 hold에서 멈춥니다. | 실제 issue 직전에 전체 terminal/abort 상태와 반환 batch를 다시 대조 |
| **수정 인정 · 알려진 반례 차단** | #363 새 `enters` 검사는 공개 0865의 첫 8.7초 R2 candidate를 현재 거부합니다. | 이전 9.0초 DEV 실패를 현재 head 결과로 재사용하지 않고 수정 이후 새 첫 거절 경계부터 확인 |

P2는 다음 변경·인수 전에 확인할 구체적인 정확성 문제라는 뜻이며, 실제 물리 사고나 연구 효과크기를 측정했다는 뜻이 아닙니다. 공급자 실제 사용량 보존, 정상 비용 경로, 전송 전 환불, blank image 거부, 최종 배송 판정처럼 **통과한 대조도 함께 남겼습니다.**

## 읽는 순서

1. [현재 #363의 변경과 blocker 판별](frontier.md)
2. [#371 모델·SIM 비용 경계](runtime.md), [HIGH image geometry](geometry.md)
3. [연구 평가의 시간 의미](evaluation.md)
4. [표준 방법·관련 연구와 적용 조건](research.md), [primary 출처·읽은 범위](research-sources.md)
5. [독립 반증·재실행 기록](independent-validation.md) → [게시 직전 #371 수정](frontier-followup.md), [비용·종료 경로 현재성](runtime-currentness.md)

## 검토한 시점

| 대상 | 고정 SHA | 이번 범위 |
|---|---|---|
| main | `b23fc0875b72f4b55f399a252a1575b7e8b43cb5` | 표준 zone-study evaluator/referee와 실제 기록 caller |
| PR #363 | `0d7c5eb3ca3643ead2a0b50dd133a1188f06f572` | 기존 검토 이후 변경, 공개 진단 요약, guard·dispatch·edge 경계 |
| PR #371 | `a009112ff5fb18c6b64f58d8cd6392c58d4c028c` | `1883c56` 합성 재현 + 새 head의 변경범위/관련 경로 동일성 대조, clock/prompt 수정 재검증 |
| PR #372 | `f676889f39df2de0679cc4e82e067565dcc5a775` | source/test 변경 유무만 대조; 새 raw·점수는 보지 않음 |

source snapshot과 공개 저자 보고를 구분했습니다. 새 source cutoff 이후 변경에 판정을 자동 승계하지 않습니다. 1–7차 원문은 2026-10-03 17:53 UTC에 동결한 역사적 기록으로 바이트 그대로 보존했습니다. 새 판단은 이 8차 문서가 우선합니다.

## 막힌 부분에 대한 연구 인사이트

- **관측창 잘림과 이상치는 다른 문제입니다.** robust fit은 소수 이상점에 대한 대안이지만, ROI 끝에서 만든 완벽한 가짜 직선은 관측의 유효성부터 확인해야 합니다.
- **작은 표준편차는 작은 실제 오차를 보장하지 않습니다.** 모형 조건·편향·벽 법선 방향 오차·시간 구간의 위험을 따로 다뤄야 합니다. 공개 과거 DEV의 숫자로 최신 head의 보정 정확도를 확정하지 않습니다.
- **다음 관측의 목표를 구체화합니다.** 단순히 더 많이 보는 것과 현재 가설들을 구별하는 것은 다릅니다. 최신 active perception 연구의 설계 원리는 참고하되 RGB-D·측정 pose 등 UGRP에 없는 입력 가정은 가져오지 않습니다.
- **오래 보지 않아도 되는 시간과 물리적 안전시간은 다릅니다.** scheduler에서 계산한 TTL과 연속 두 프레임은 각각 외란 상한이나 독립 관측을 입증하지 않습니다. 현재 명령·frame·epoch와 적용 가정을 함께 기록하는 것이 먼저입니다.

상세 문서는 현재 first-E2E에 필요한 작은 판별을 제시합니다. 새 대규모 실험·추가 센서·학습 모델 도입을 완료 조건으로 추가하지 않습니다.

## 검증과 한계

분야별 담당과 별도 편집자가 핵심 합성 반례·부정 대조를 재실행했습니다. 원래 함수/클래스 또는 변경하지 않은 AST 본문, 가짜 wire·명령 sink·합성 RGB·fake referee truth를 사용했습니다. 일부 optional import는 차단하거나 stub으로 분리했으며, 이 범위는 각 문서에 명시했습니다. 실제 물리·렌더·모델·학습·실기기 실행, 과거 raw·heldout outcome 열람은 하지 않았습니다. 모든 파일 정독·전체 테스트 완료로 보고하지 않습니다.

GitHub에는 읽을 문서만 추가합니다. Mac 전달본에는 합성 재현 스크립트와 작은 결과 JSON/검증 로그도 포함합니다. 각 스크립트는 정확한 source snapshot·의존성이 필요할 수 있으며 저장소 전체나 실행 환경을 번들로 복제한 것은 아닙니다.
