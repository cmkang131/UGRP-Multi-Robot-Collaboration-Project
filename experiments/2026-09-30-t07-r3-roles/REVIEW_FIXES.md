# #323 Batch F 수정

검토 대상 `1a17829e79cdf7771ee2d09ca25e444c39cf37be`,
[독립 지적](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/323#issuecomment-5912561494).
물리/SIM/렌더/외부 모델 실행은 하지 않았다. 아래는 코드·fake 포트 검증이다.

## F1 — 현재 v6e 소스 봉인 파손

`zone_own_team_host.py`, `zone_own_executor.py`, `zone_pair_executor.py`,
`zone_pair_status.py`, `zone_study_integration.py`를 main의 원본 바이트로 복구했다.
`prereg_v6e.json`의 해시를 갱신하지 않았다. 현재 v6e 전체 source_sha256과
복구한 파일의 바이트를 대조하고, 기존 admission 테스트를 그대로 실행한다.

새 구현은 다음 세 opt-in 모듈에 격리했다. 기존 모듈에서 이 모듈들을 import하지 않는다.
전역 class/function 교체·robot ID 교체·기존 등록의 자동 migration은 없다.

- `harness.zone_pair_role_executor`: sealed 정적 계획의 역할 이름 재배정,
  역할별 schedule, PairExecution/PairTeam. 기존 lifecycle/poll/abort는 상속한다.
- `harness.zone_pair_role_host`: `RoleAwareHostMixin` 및 `OwnCamTeamHost`.
  기본 executor 객체의 자기 job admission만 새 dispatcher에서 처리한다.
- `harness.zone_pair_role_integration`: `executor_plan`, `PairStatusBus`, `IntegratedTrial`.
  기존 study 상태·입력·기록 로직을 상속하고 명시적 role 요청만 새 경로로 전달한다.

새 executor profile은 `zone_pair_role_executor_v1`이며 역할 profile은
`zone_pair_roles_v1`이다. 새 세션의 제어 소스 영수증은 세 어댑터 모두를 root로 삼는다.
기존 v6e bundle의 실행 승인을 새 경로에 승계하지 않는다. 새 runnable/workflow ID 없음.

추가 회귀는 5개 소스별 고정 해시와 opt-in/legacy host·study 동시 사용을 검사한다.
기존 source-pinning/registered-source 검사는 삭제하거나 완화하지 않았다.

## F2 — 같은 구현을 정답으로 쓴 금지 영역 검사

역할별 `make_plan()`과 같은 함수의 legacy 결과를 비교하던 geometry assertion을
독립 숫자 기대값으로 교체했다. 공개 sheet `[1, 0, 0]`에서 봉의 half extents는
`[.36, .08]`(봉 `[.30, .02]` + grid pad `.06`), 상대 station/prestation의
half extents는 `[.17, .17]`이다. end_neg의 상대 station/prestation x는
`1.425/1.725`, end_pos는 `.575/.275`다. 값은 production helper로 계산하지 않는다.

6배정 각각에서 계획의 3개 영역·padding·정적 출처를 검사하고, 실제
`GuardedPairApproach` 객체의 `keepouts`와 목적 자세까지 같은 고정값으로 검사한다.
기존 실제 schedule/운반 부호 검사는 유지한다.

`mutation_checks.py`는 임시 snapshot에만 변이를 적용한다. 전체/각 영역 제거,
봉/상대 padding 제거, 잘못된 역할의 계획 및 driver 전달, driver 전체 영역 제거를
검사한다. F1은 각 파일에 검토 당시의 봉인 파손 bytes를 되넣어 개별 회귀가 실패하는지
검사한다. 정상 baseline과 복구 후에는 모두 통과해야 하며, 변이는 import/collection
오류 없이 선택된 검사 전부의 assertion failure여야 인정한다.

## 실행과 인계

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-30-t07-r3-roles/offline_checks.py
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-30-t07-r3-roles/mutation_checks.py
```

main #328의 최신 지침에 따라 오프라인 테스트의 공용 잠금은 선택 사항이다.
이 작업은 wall 성능 측정이 아니며 thread 1·no-physics guard를 유지한다.
정상 GitHub CI를 실행한다. workflow 수정·취소·CI 건너뛰기를 하지 않는다.
CI 테스트 목록의 main 충돌은 양쪽 항목을 유지해 해결했다.
최종 수치·소스와 raw 해시는 `review_fixes_verification.json`에 기록한다.
raw는 primary `outputs/t07-r3-roles/`의 새 경로에 보존하며 로컬 보관이다.
실험/학습/물리 평가 결과가 없으므로 TensorBoard snapshot은 만들지 않는다. Drive 작업 없음.

#324는 검토 당시의 #323 `1a17829e…` 위에 T12 delta가 있다. 이 수정의 최종 head로
rebase한 뒤 아래 import 경계를 반영하고 합성 검사·정상 CI를 다시 실행해야 한다.
최종 head SHA는 #323 PR 코멘트에 적는다.

- 역할 `PairTeam`, `make_plan`, `m2_controller`, `controller_source_record`는
  `harness.zone_pair_role_executor`에서 import한다.
- role 인자를 받는 host는 `harness.zone_pair_role_host`에서 선택한다.
- `executor_plan(..., role_assignment=...)`와
  `IntegratedTrial(..., pair_role_assignment=...)`는 `harness.zone_pair_role_integration`에서 선택한다.
- fake 통합 fixture는 `tests.test_zone_pair_role_exchange.setup`을 사용하거나
  `RoleAwareHostMixin`을 자기 fake host에 명시적으로 결합한다.
- 기존 봉인 파일을 재수정하거나 기존 등록 해시를 덮어쓰지 않는다.

수정 후 독립 재검토와 실제 물리 인수는 별도이며 이번 작업은 물리 실행 권한을 포함하지 않는다.

## 검증 결과

- 관련 17개 파일 **536 passed, 0 failed/errors/skipped**. 새 T07 145개,
  registered source 22개, study source pin 34개, door relaxation 보호 20개 포함.
  먼저 실행한 좁은 201개는 이 536개와 겹치므로 합산하지 않는다.
- 새 회귀 18개 baseline/복구 후 모두 통과. **15개 변이 전부 검출**:
  전체·봉·상대 station·상대 prestation 영역 제거와 계획 역할 뒤바꿈,
  봉/상대 padding 제거는 각각 12개 assertion 실패;
  driver 영역 제거/반대 역할 전달은 각각 6개;
  봉인 파일 5개 각각 되돌리기와 전체 legacy API 분리 해제는 각각 1개.
  import/collection 오류·다른 예외·skip은 모두 0이다.
- 작업 트리의 v6e source 85개와 scene source 12개가 등록 해시와 일치한다.
  등록 JSON은 검토 당시 원본과 바이트 동일하다. 정상/변이/복구 로그와 JUnit은
  `review_fixes_verification.json`의 경로·SHA-256으로 식별한다.
- 시작 시 main `38c5bb61`을 먼저 합성한 뒤 수정했고, 작업 중 추가된 main
  `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`도 병합했다. 마지막 합성 검사
  **279 passed + 280 subtests passed**, 실패·오류·skip 0.
  소스 고정 56개는 앞 검사와 겹친다. CI host-lock/sharding/fast-path,
  agent-lock 및 main의 P07 manifest 검사를 함께 확인했다.
  역할 제어 의존 소스 201개와 앞서 검증한 코드·테스트 해시는 모두 그대로다.
  T07/P08/P07은 각각 CI 목록과 전체 shard에 정확히 한 번 들어간다.
