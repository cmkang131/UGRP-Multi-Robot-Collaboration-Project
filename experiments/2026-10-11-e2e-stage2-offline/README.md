e2e stage 2: 코드·오프라인 검증만, 물리/모델 호출 0.
결과·원본·sha256: summary.json; 다음 Azure 계획: azure-plan.json(미제출).
기본 옵션: configs/e2e_stage2_options_v1.json 모두 off.
GoalRoute에 e2e_goal_route.attach 적용 → route_to_B → 실제 S4 proposal 수신·승인 → provider_plan.
전체 자기 지도 해시와 compact 대화 해시는 다르며 승인 시 바인딩한다.
펄스: S3 synchronized → e2e_pulse_budget.attach → integer 순서, ResidualPulsePort + pulse_authorizer 사용.
최종 장면: reobserve_setdown → 새 proposal/epoch → provider_plan 재설치 → attach_setdown_gate.
관련 3파일 86/86; 재생 6/6 개선은 선형 응답 예측이며 물리 성공이 아니다.
NEES 4.154배, 별도 seed 경계 초과 41/1260으로 보정 보장 없음; 연구/E2E 분모에 넣지 않는다.
