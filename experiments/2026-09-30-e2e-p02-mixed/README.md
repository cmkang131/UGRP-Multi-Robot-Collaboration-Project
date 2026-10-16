# P02 — cyan와 공동 봉의 정적 혼합 연결

상태: DRAFT, 임무 물리 실행·모델/교사 호출 결과 없음. B1 후속 검사에서 잘못 선택한
native 테스트 1개가 렌더러 생성 중 sandbox 오류로 차단된 기록은 `FIX_B1.md`에 남긴다. 전체 s1–s6 지원이나
자율 파트너 선택의 결과가 아니다. 시작 source는 `d17ca4345affef8cf027e121cf1f3197b36c23e0`,
작업은 `codex/mixed-jobs`와 배정 worktree `e2e-p02-mixed`에서만 수행했다.

## 변경

새 opt-in `mixed_cyan_beam_fixed_r12_r3_v1`은 `beam-order → beam_dev`와
`cyan-order → cyan_dev`를 분리해 고정한다. setup/eval에는 정확한 배치가 있지만
공개 OrderSheetSource는 기존 닫힌 스키마의 종류/수량/개체 ID/초기 slot만 사용한다.
주문별 일대다 정적 매핑 helper는 fungible 주문도 검증하지만 실행 profile은 각 1개만 허용한다.

새 `MixedGeometryCargoZoneScene`은 기존 표준 Scene subclass로 cyan replica와 long_beam을
한 inventory에 보존한다. World 없이 fake parent config로 resolver·inventory를 검사한다.
누락·중복 ID·종류/배치 불일치·질량 override를 거절하고 World 생성 전 준비 config도 대조한다.
기존 `sim/zone_geometry_scene.py`, cargo Scene, PairTeam/M1 executor, OrderSheetSource 파일은
바꾸지 않았다. 옛 pair-only 경로의 placeholder 제거는 유지한다.

r1/end_neg·r2/end_pos는 각자 자기 API로 같은 주문을 제출해야 하고 r3는 cyan 단독 배송만
허용한다. 직접 API에도 제한을 적용하며 상대 claim 자동 생성, pair 실패로 r3 취소,
GT 기반 양보는 추가하지 않는다. r3 pair/비cyan/heavy_crate/새 경로·policy는 거절한다.
현재 fake 검증 대상은 geometry v2, 기존 coarse pickup·cyan A/beam B 경로·v5h다.
최종 v3와 무표식 provider, v6h1은 별도 이관·검증 전 미지원이다.

`evidence_join`은 call_id/actor/order_id → ack job_id → 자기 terminal event → 별도 평가
item_id/종류/목적지를 연결한다. API `job_done/unconfirmed`를 평가 도착으로 승격하지 않는다.
GT/TOP 평가 자료 변이는 네 조건에서 공개 자기 요청/명령을 바꾸면 실패하도록 검사한다.

## 검증과 증거

독립 검토 B1 수정은 [후속 기록](FIX_B1.md)을 따른다. 기존 공용 소스 3개는 v6e의
등록 해시와 같은 바이트로 복원하고, 혼합 연결은 `scripts.zone_mixed_study_adapter`와
`harness.zone_mixed_host/zone_mixed_integration`으로 분리했다. 기존 등록·검사는 그대로다.
이후 합성은 [새 진입점](COORDINATOR_HANDOFF.md#b1-이후-진입점-2026-09-30)을 사용한다.
기존 integration CLI가 혼합 주문을 직접 실행하는 경로는 제공하지 않는다.

아래 254건은 수정 전의 검사 기록이며 B1 소스 고정 검사를 포함하지 않았다.
코드 source `c76e67dbc8c4d97cd96447ed7d9d4b344c2dd869`의 최종 관련 회귀 **254 passed** (신규 혼합 26건 포함),
`git diff --check`, Python 7파일 구문 검사, 원본 14파일 바이트 보존 확인이 통과했다.
exact source/환경/해시와 실패한 초기 검사도 `VERIFICATION.json`에 기록했다.
공용 잠금은 `run_ci_tests.run_locked`로 정상 획득·반환했다. 검사 시간은 성능 비교가 아니다.
구문 검사·원본 파일 보존·pytest는 각각 분리해 보고한다. 실패한 첫 검사도 원본 JUnit에 남긴다.
raw 검증 파일은 `/Users/changmin/projects/ugrp/outputs/e2e-p02-mixed/`에 로컬 보관한다.
Git에 있는 해시는 raw 원격 백업이 아니다. 기존 raw·bundle·snapshot을 삭제하거나 덮어쓰지 않는다.

## 인계·남은 일

[코디네이터 실제 검증 명세](COORDINATOR_HANDOFF.md)를 따른다. 같은 seed·scene spec으로
초기화부터 cyan A·봉 B까지 4조건 × 1800 SIM초 cap(총 7200초 상한)을 새로 검증해야 한다.
이번 작업은 실행하지 않았으며 source/bundle/workflow 번호를 예약·봉인하지 않았다.
P01 최종 scene과 P03 provider/model/calibration, P04/P05/P06 합성과 최종 M1/M2 검증이 남는다.

새 물리/학습/평가 cohort가 없으므로 공용 TensorBoard snapshot·서버·UI는 변경하지 않았다.
실제 결과의 TensorBoard 변환/readback/영상/화면 검증은 코디네이터와 P06의 후속 범위다.
UGRP 예외에 따라 Drive 작업은 없다. PR은 draft로 전달하고 병합하지 않는다.

## 참고 자료

- [READINESS S04/S13, PR #298](https://github.com/kcm0127-dotcom/ugrp/pull/298)
- [파일 소유 조율](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/298#issuecomment-5909726330)
- [#219](https://github.com/kcm0127-dotcom/ugrp/issues/219), [#221](https://github.com/kcm0127-dotcom/ugrp/issues/221), [#223](https://github.com/kcm0127-dotcom/ugrp/issues/223)
- [지침](../../AGENTS.md), [개발/공용 잠금](../../CONTRIBUTING.md)
