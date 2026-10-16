# 현재 상태와 실행 경로

## 2026-10-16 warp7 — MJWarp 자기 영상·운반 배치 NOT_READY

사용자 "모두 MJWarp로 바꿔서 하게"에 따라 CPU 색 결과 동일성 관문을 평가용 visible geom 정탐·오검출 측정으로 교체했다. MJWarp88장 상자 accepted52/52·B4/4·목적지4/4 정답, 오검출0; 상자30건의 전체 검출 누락은 색·윤곽 뒤 바닥 투영 거부다. N16 세 실제 rollout은 초기0.3–0.4SIM초에서 처리량 문제가 반복돼 세 번째 라운드 중단 규칙을 적용했다. 운반/place/완주 유효 시행0, 첫30SIM초·LLM E2E 미완료. [관문표·모든 HOST_ERROR·재현/원본](../experiments/2026-10-16-warp7/README.md). 아래 기록은 각 날짜 당시 상태다.

## 2026-10-01 b-v6h1 분석 봉인 — 독립 검토 필요

PR #292에서 EXECUTION 274파일을 블라인드 기록 소스 `4c6b439f`에, 최종 classifier/adapter/gate를 별도 봉인 커밋에 고정했다. CURRENT_REVISION=v6h, v83/2.16.0 유지. 기록이 봉인보다 앞선 `unsealed_stage_probe`였음을 공개하며 실행 전 등록으로 소급하지 않는다. 이번 작업은 raw·outcome 열람이나 물리/렌더를 하지 않았다. 48/60(941)과 첫12곳 민감도(943), HOST_ERROR/ENOSPC/누락 UNCLASSIFIED를 고정했다. [봉인과 재현 경계](../experiments/2026-09-30-pair-v6h-carry/REGISTRATION_PLAN.md). 독립 검토·개봉·PR 병합은 남아 있다.

아래 첫 절은 2026-09-30 저녁 진행 요약이고, 이전 9/30·9/29 절도 당시 기록 그대로 보존한다. 앞으로의 연구 우선순위와 완료 기준은 [연구 TODO](research_todo.md)(2026-09-26 개정: §0 로드맵, 마일스톤 "E2E 첫 파일럿" 이슈 #216–#226)를 따른다. 통신 효과가 주 질문이며 ACT·Jev·맵 확대는 관련 보조 과제로 구분한다. 아래 검증 수치는 각 기록 당시의 범위를 유지한다.
