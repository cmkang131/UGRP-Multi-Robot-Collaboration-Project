# UGRP 독립 검토 — 8차 추가 결과 (2026-10-04)

**[8차 요약과 우선순위](round8/README.md)부터 읽으세요.** 최신 개발 경계를 다시 확인하고 현재 경로의 새 문제 3개와 표준 연구 평가의 새 문제 1개를 합성 반례로 재현했습니다. 분야 담당과 별도 검토자가 핵심 반례·부정 대조를 확인했습니다. 구현 코드는 변경하지 않았습니다.

**게시 직전 #371 `a009112f`까지 반영했습니다.** 기존 own_status 시간축·`__CHARS__` 문제는 [수정 검증](round8/frontier-followup.md)으로 해소를 확인했고, 새 비용·finalization finding은 [관련 경로 동일성](round8/runtime-currentness.md)을 확인했습니다. 옛 본문의 미해결 표현을 최신 head에 적용하지 않습니다.

| 구분 | 이번에 확인한 결과 | 상세 |
|---|---|---|
| 신규 P2 · #371 | 전송 뒤 실패한 모델 호출에서 이미지의 deterministic SIM 비용 누락 | [모델 실행·비용](round8/runtime.md) |
| 신규 P2 · #371 | 단일 finalization 실패의 `HOST_ERROR`와 영속 ledger의 `finished`/분류 누락 불일치 | [결과 기록 경계](round8/runtime.md), [별도 재검증](round8/runtime-finalization-validation.md) |
| 신규 P2 · #363 | ROI에 잘린 beam 색띠를 실제 lower edge로 받아들여 기준 영상 available 처리 | [영상 기하](round8/geometry.md), [수정 수용 기준](round8/geometry-acceptance.md) |
| 신규 P2 · 표준 zone-study | 미래 물체 이동이 이미 끝난 발화의 사실성 점수를 뒤집음 | [평가 코드](round8/evaluation.md) |
| 기존 지적 재확인 | peer abort 뒤 같은 tick dispatch는 #363에 남음 | [현재 개발 경계](round8/frontier.md) |
| 새 수정 인정 · #371 | own_status 시간축과 prompt slot 문제는 a009에서 해소 확인 | [최신 수정 검증](round8/frontier-followup.md) |
| 수정 인정 | #363 새 start-relief 검사가 알려진 R2 접근 candidate를 실제로 거부함 | [수정 재현과 진도](round8/frontier.md) |

작은 반례가 실제 운반의 실패율·빈도를 알려 주지는 않습니다. 정상 비용·전송 전 환불·공급자 사용량 보존·blank image 거부·최종 배송률 같은 통과 대조와, 실제 caller/부분 추출/stub의 한계를 각 문서에 함께 적었습니다. 조건부 quota body 분류와 선택 `slot_states` API 문제는 우선 발견과 별도 부록으로 남겼습니다.

## 막힌 부분을 좁히는 연구 검토

[관련 연구와 적용 조건](round8/research.md)은 HIGH의 이상치·ROI 잘림·참조 초기화를 구분하고, 위치 추정의 편향과 좁은 공분산, 다음 관측의 결정 가치, blind 시간의 가정을 다룹니다. [primary source 확인표](round8/research-sources.md)에는 논문 6편과 OpenCV 공식 문서, 직접 읽은 범위와 사용할 수 없는 입력 가정을 기록했습니다. [별도 연구 검증](round8/research-validation.md), [종합 독립 검증](round8/independent-validation.md)도 포함합니다.

## 시점과 보존 범위

8차 기준은 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`, #363 `0d7c5eb3ca3643ead2a0b50dd133a1188f06f572`, #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`입니다. #371의 합성 비용/종료 재현은 `1883c56`에서 수행했고 새 head에서는 관련 파일 바이트·메서드 AST 동일성을 확인했습니다. #372 `f676889f39df2de0679cc4e82e067565dcc5a775`는 source/test 변경 여부만 대조했습니다. 공개 DEV 진행은 작성자 보고로 구분하며 이후 SHA에 판정을 자동 적용하지 않습니다.

**1–7차 원문 13개는 2026-10-03 17:53 UTC의 동결 기록을 바이트 그대로 보존했습니다.** [종합 원문](publication/final-index-issue.md), [원문 전체 목록](publication/README.md), [선별 7차 근거](evidence/README.md). 그 안의 “현재/최신”은 당시 시점이며, 최신 개발 진도는 8차 문서를 우선하세요. 게시 전에 확인했던 #363 `e05776b4` 이후를 재검토하지 않았다는 1–7차 기록은 역사적 사실이고, 이번 8차가 명시한 범위의 후속 검토를 추가합니다.

이 PR은 문서만 담습니다. 코드·설정·실험을 수정하거나 새 물리·렌더·LLM·학습·실기기 실행, raw·heldout outcome 열람을 하지 않았습니다. 전체 저장소 전줄 정독·전체 테스트 실행 보고가 아닙니다. Markdown에 남은 재현 파일명·절대경로는 출처 기록이며, GitHub 문서에 스크립트와 source snapshot 전체가 포함된다는 뜻은 아닙니다. 합성 재현 스크립트와 작은 결과는 별도 Mac 전달본에 보존합니다.
