# PR #229 / #235 통합 파일 편집 기록 (2026-09-27)

물리 실행 0회, 외부 모델 호출 0회, 연구 결과 아님. Git 쓰기·add·commit·push·병합은 하지 않았다. 코디네이터가 진행 중인 merge 작업의 파일만 수정했다. 완료 판정은 코드 배선과 비물리 회귀에 한정한다.

- 충돌 5파일을 합쳤다. workflow 양쪽 ID의 합집합은 중복 없이 36개다. 테스트 등록과 양쪽 테스트 의도도 보존했다.
- 팀 주문 claim을 실제 host API → PairTeam → zone_pair_status_v4에 연결했다. r1/r2의 독립 제출, 준비/GO 메시지, 양쪽 명령, 자기 abort를 네 조건에서 검사했다. 별도의 사용되지 않는 짝 채널은 제거했다.
- GeminiProxyCompleter의 실제 요청 작성 경로를 가짜 wire로 검사했다. 로봇별 다른 자기 포트 JPEG가 요청까지 전달되고 모든 요청 원문이 보존된다. 통신 3조건은 inbox/수신 후 재호출, no_comm은 자기 타이머로 다회 호출한다.
- 연구 시나리오 6종을 cargo_noslip_v1로 맞췄다. bundle의 예상 옵션과 manifest의 실제 적용 기록을 분리했다. 고정 인식 지연 0.16 SIM s는 report와 loc 양쪽에 적용한다.
- tags_temporary 유지. #237의 등록·자기 도크 init_prior·close 연결점, 태그 없는 Scene 및 M2 재위치 추정 adapter가 남는다는 점을 문서화했다.

검사 명령은 기존 Mac sim 환경의 python -m pytest에 OMP_NUM_THREADS=1과 --basetemp=./.pytest_tmp를 사용했다.

1. 확장 회귀: 1,050 passed, 3 deselected (regression.txt). 통합/계약/입력/시나리오/프로토콜/오프라인/평가/스케줄러/비용/자기 실행기/짝/워크플로 검사. 이후 추가한 지연 reset/provider 수명 코드는 아래 검사로 다시 확인했다.
2. 짝·실제 adapter 관련 회귀: 378 passed (adapter-regression.txt). 통합, pair executor/reviews, core r7 transport와 r8 budget/네트워크 경계 포함.
3. 최종 소스 통합 검사: 110 passed (final-integration.txt). provider 수명, Scene 구성, manifest 실제값 기록 검사까지 포함. 이 수들은 중복되므로 합산하지 않는다.

물리 검사 2개는 요청에 따라 제외했다. test_parent_exit_cleans_background_child는 처음 실행에서 샌드박스의 ps 금지(PermissionError)로 확인하지 못했으며 확장 회귀에서 제외했다. 테스트를 약화하거나 해당 검사를 삭제하지 않았다.

남은 물리 검증: 새 소스와 bundle 고정·예산/잠금 → pair dev 4조건 전체 시도 → 실제 JPEG/프로필/weld 감사 → 고정 지연에서 readiness·불확실성 → 파지·문 통과·방출·abort·거짓 확인. 실제 LLM 파일럿, 태그 0개 provider 교체도 별도다. 새 물리/학습/평가 결과가 없어 TensorBoard 전환·서버 실행은 하지 않았다.

상세 연결 규약과 근거는 [통합 문서](../../../docs/zone_study_integration.md)를, 파일·증거 해시는 verification.json을 따른다. .pytest_tmp 삭제를 확인했다. 숨김·ignored 파일을 포함한 worktree 텍스트 전체 재검색에서 충돌 표시 0건이고, 기록한 소스 해시를 모두 재확인했다.
