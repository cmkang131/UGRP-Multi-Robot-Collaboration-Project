# E2E batch A 독립 반례 검토

2026-09-30, Codex. 물리·시뮬레이션·렌더·학습·실제 모델 호출 없이 검토했다.
판정은 아래 SHA의 **각 작업 프롬프트 범위**에 대한 기술 검토다. E2E/PHYSICAL 승인이나 실제 병합이 아니다.
보고서와 작은 재현 자료만 리뷰 브랜치에 추가했다. 검토 대상 코드는 수정하지 않았다.

## 판정과 소스

| PR / 프롬프트 | 검토 HEAD | 판정 | 핵심 이유 |
|---|---|---|---|
| #303 / P06 | `cbac1dfca5d0a1d8f18e4ff2633626d4cadf2af8` | **BLOCK** | 다른 시행·시나리오·seed·주문 ID를 섞어도 성공 event 발행. v6e 등록 검사도 실패 |
| #304 / P08 | `247c264a7ff53963c7e62bd083e0b825e87d2739` | **MERGE** | 기본 OFF·관찰/fake 계약이라는 제한 범위 충족. 실제 D1 연결·중단 활성화 승인은 아님 |
| #305 / P01 | `5a852fbfde3b0df836f3a423be29a774a9c54614` | **MERGE AFTER FIXES** | 정적 연결·미검증 조합 거절은 적절. 기존 dock 지도 거절 회귀, v6e 등록 호환, #292 합성 의존성 봉인을 고쳐야 함 |

- 기준 main: `c12796676802ab54cad2f0635e3e96e911691c76`; 리뷰 브랜치 시작: `6594536b1a1afec6d9d109b35dd85a8426142d01`. 보고서 커밋 전 자신의 리뷰 브랜치만 위 main으로 fast-forward했다. 검사한 PR archive는 바꾸지 않았다.
- #304 테스트 실행 SHA는 `0cfe29df04abead833940420f08bdd0acefdb556`이다. 검토 중 추가된 `247c264a`는 `ci: run normal checks` 빈 커밋이며 두 tree가 모두 `9356464cad46653da807545b08f11fed3adee3e7`임을 확인했다. 소스 변화 없는 CI 재실행을 새 코드 검증으로 합산하지 않았다.
- 연관 PR: #292 `3c4fe30e2197518443b195392212b0341507ac59`, #299 `c86d9bac62036904ecc641db5e59e79edb58dec2`, #301 `2ff92e9fbeff1b90b0aa35104a9766753e67f94e`, #293 `d86cc82eedbe0c6693eaf808c54ce43387723f1d`.
- `AGENTS.md`, 기본 checkout의 최신 `AGENTS.md`, `README.md`, `docs/current_status.md`, `CONTRIBUTING.md`, P01/P06/P08 원문, 변경 코드와 관련 테스트·의존성을 읽었다. 날짜가 붙은 과거 결과를 현재 성능으로 승계하지 않았다.

## 검증 결과

`git archive`로 각 정확한 SHA를 `/tmp/ugrp-review-e2e-a/`에 풀었다. `git worktree add`는 사용하지 않았다.
기존 Mac Python 3.12 환경과 `scripts.run_ci_tests.run_locked`의 공용 잠금을 사용했다.
다른 작업 점유 시 exit 3으로 검사를 시작하지 않았고, 소유 잠금·프로세스를 변경하지 않았다.
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, OMP/BLAS/MKL/VECLIB 스레드 1을 사용했다.

| 대상 | 실제 실행 범위 | 결과 |
|---|---|---|
| #303 | `test_zone_study_evidence` 47 + `test_zone_study_eval` 71 + `test_tensorboard_export` 58; 아래 등록 검사 6 | **176 passed, 6 failed** |
| #304 | `test_stall_observation_contract` 40 + `test_zone_pair_status` 16 | **56 passed** |
| #305 | `test_zone_environment_registry` 38 + `test_zone_study_source_pinning` 33; 아래 등록 검사 6 | **71 passed, 6 failed** |
| 기준 main | 같은 등록 검사 6개 | **6 passed** |

등록 검사 6개는 `tests/test_zone_pair_registered_source.py::test_v6e_records_current_scene_and_full_source_closure`, `::test_v6_rejects_stale_or_inherited_source_contracts`의 4개 매개변수, `tests/test_zone_pair_door_relax.py::test_registered_sources_are_not_touched_by_this_change`다. 모두 dict/파일 해시 검사이며 Scene/World를 만들지 않았다.
`test_zone_study_referee.py` 전체는 실행하지 않았다. 새 P06 테스트가 사용하는 synthetic helper만 호출했다.
전체 로컬 회귀·물리 인수·실제 provider 정산은 실행하지 않았다. 작성자들의 203/122/278 통과를 이번 독립 검사의 통과 수로 사용하지 않았다.

GitHub CI도 #303과 #305에서 같은 등록 검사 6개 실패를 보였다: [#303 실행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36707914710), [#305 실행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36708158816).
#304는 최초 HEAD에 `[skip ci]`가 있었고 이후 빈 커밋으로 일반 CI를 다시 요청했다. 최종 확인 상태는 `review_batch_a/VERIFICATION.md`에 기록한다. 기술상 MERGE 의견이 필수 CI 통과를 대신하지 않는다.

## #303 — BLOCK

### A303-1 · BLOCKER — raw/bundle과 trial의 신원이 연결되지 않아 다른 시행의 성공을 수입한다

근거: `scripts/tensorboard_tools/zone_study.py:34`, `:110`, `:115`, `:119`, `:157`.
`verify_raw()`는 manifest/result의 run ID와 bundle digest만 비교한다. `export_study()`는 end_reason/end_sim_s/condition/failure_class 등을 비교하지만 **trial_id, scenario, seed, 주문 식별자**를 원본 bundle·result·심판의 주문과 대조하지 않는다.
따라서 파일 해시가 모두 맞아도 내용 사이의 잘못된 연결은 통과한다.

독립 반례는 PR의 `synthetic_source()`가 만든 정상 성공 자료에 다음 변경만 하고 파일 inventory/hash를 다시 계산했다. 연구 raw는 사용하거나 수정하지 않았다.

1. trial의 `trial_id='unrelated-trial'`, `scenario='unrelated-scenario'`, `seed=987654`로 변경; result/bundle/evaluation/요청은 그대로 유지.
2. 별도 복사본에서 trial의 모든 `order_id`만 `unrelated-order-0/1/2`로 변경; bundle 주문과 evaluation의 주문 ID는 그대로 유지.

**두 경우 모두 예외 없이 export되었고 EventAccumulator에서 `evaluation/reported_success=1.0`이었다.** 첫 경우 HParams 출처인 metadata의 case/seed까지 바뀌었다. 실행 묶음·요청·심판과 다른 시행의 성공을 보여 줄 수 있으므로 P06의 증거 연결 완료 기준을 충족하지 않는다.

수정: result/manifest에 논리 시행 ID와 실제 attempt/run ID의 명시적 관계, scenario/seed/주문 sheet 식별값을 저장하고 exporter가 교차 검증해야 한다. 현재 정상 경로도 raw `run_id`와 `trial_id`의 이름이 다르므로 문자열을 무조건 같게 만들라는 뜻은 아니다. 심판의 per-order 결과와 bundle의 주문도 같이 검증해야 한다.

기존 `tests/test_zone_study_evidence.py:281`의 `trial_join` 반례는 이름과 달리 **end_reason만** 바꾼다. 이번 ID 교환 반례는 검출하지 못한다. 새 실패 테스트는 위 두 변경에 대해 event 미발행을 확인해야 한다.

재현 소스/실제 출력: [P06 재현 코드](review_batch_a/REPRODUCERS.md#p06), [P06 출력](review_batch_a/VERIFICATION.md).

### A303-2 · MAJOR — 현재 v6e 등록 소스를 바꾸면서 과거 등록으로 분리하는 변경이 없다

근거: `scripts/run_zone_study_integration.py:587`, `:599`, `:665`; 기존 `scripts/zone_pair_v6_contract.py:285`; `tests/test_zone_pair_registered_source.py:114`, `:143`; `tests/test_zone_pair_door_relax.py:49`.

v6e의 `prereg_v6e.json`이 고정한 runner SHA-256은 `85508cc58e1cba0f1fc11e3b7ef656c0c7648202ff1086c274c3dbaa64a99edd`인데, #303은 `84e90031d0c31b67a43719585687b386b8973873a2e8932f670572a859071fe0`이다. 기존 등록 파일은 보존되었지만 현재 main의 `load_config`는 `v6 source contract/hash mismatch`로 실패한다. main의 같은 6개 검사는 통과했다.

이는 **조용히 옛 봉인을 통과한 상황은 아니다**. 검사가 안전하게 거절하고 있으나, 이 PR만 main에 병합할 수 있는 상태도 아니다. #292의 v6e 역사화와 합성하거나 독립된 호환 정리를 먼저 하고, 옛 등록 bytes는 그대로 Git blob으로 검증하며 새 소스는 별도 후보로 취급해야 한다. 기대 해시만 현재 값으로 덮어쓰는 수정은 안 된다.

### A303-3 · MINOR — terminal 표식의 생략 허용을 명세에 드러낼 필요

근거: `scripts/tensorboard_tools/zone_study.py:108`, `:121`.
result의 `terminal` 및 raw manifest의 `terminal`을 모두 제거해도, 나머지 성공 기록이 있으면 변환된다. 독립 반례에서 성공 scalar가 1이었다. 이전 같은 schema의 산출물을 수입하려는 호환성일 수 있어 이것만으로 가짜 완료라고 단정하지 않는다. 다만 명시적 terminal 표식을 필수로 할지, 어떤 구형 완료 증거로 대체할지 정하고 해당 테스트를 추가해야 한다. 새 미완료 자료의 marker 누락이 구형 기록으로 취급되지 않아야 한다.

### 완료 기준·입력 경계·테스트 평가

| P06 기준 | 판정 |
|---|---|
| 1. 전체 발자국/종류/개체·주문 join/held/정착/늦은 완료/초기 HOST_ERROR | synthetic 개별 심판 검사는 통과. 파일 사이의 주문/시행 join은 A303-1로 미완료 |
| 2. eval truth·TOP·hidden event만 바뀌어도 payload/request/wake 불변, 완료 통보 없음 | 새 4조건 fake 검사는 통과. 실행 loop의 심판 결과는 run 종료에만 사용. 실제 숨은 사건의 물리 효과는 미검증 |
| 3. terminal 분모·cap·미상 비용·누락·해시 | 6개 terminal 합성 분모, cap, unknown/lower bound, 파일 변조 거절은 통과. ID 교차 검증과 terminal 호환 명세는 남음 |
| 4. event readback·TOP JSON/영상/GT 구분·요청 이미지 보존 | scalar/HParams readback과 typed 영상 등록 검사 통과. A303-1 때문에 원본과 같은 시행이라는 보장은 불충분 |
| 5. D1 0.1초/1초와 결측 metric | `docs/tensorboard.md:179` 이후 명시. 미상 값을 0으로 채우지 않는 검사 통과 |
| 6. 실제 첫 결과 인수 절차 | `docs/tensorboard.md:191` 이후 snapshot/readback/logdir/video/pin/HParams 절차 있음. 실제 화면 완료 주장은 없음 |

추가 음성 대조: request archive의 image_refs를 없애고 원본 JPEG까지 지운 경우는 `TrialError`로 거절됐다. 요청 digest/token 재검사가 동작한다. 파일 변조, source 변경 중 export, 일반 exporter 우회 방지 테스트도 실질적이다. 다만 정상 trial에 다른 종료 이름을 붙인 fixture가 실제 실행 중 host/provider 실패를 재현한 것은 아니다.

GT/sim truth를 controller payload·단계 전환·robot 성공 통보에 새로 전달하는 변경은 찾지 못했다. 심판 v2→v3와 공통 효율 지표의 성공/미상 해석은 바뀐다. 재변환은 새 exporter SHA·새 snapshot으로 구분해야 하며 과거 성공 수치에 소급 덮어쓰면 안 된다. 원본 파일/기존 snapshot을 덮어쓰는 새 경로, weld ON, 학생 교사 보정은 찾지 못했다.

## #304 — MERGE, 관찰/fake 계약 범위에 한정

BLOCKER/MAJOR는 찾지 못했다. #293의 승인된 실시간 인터페이스가 없을 때 실제 binding을 만들지 않은 것은 P08의 조건부 범위에 맞는다. `ObservationAdapter(enabled=False)`가 기본이며 detector/생산자/제어기로 연결된 소비 경로도 없다.

| P08 기준 | 확인 |
|---|---|
| 1. 자기 wrist RGB·자기 명령, unknown/미무장 분모 | `observation_contract.py:30`, `:90`, `:99`, `:120`의 자기 ID·카메라·시각·shape 검사, 명령 선등록, NO_CHECKS 보존. GT/peer/joints 슬롯과 import 없음. #293의 짧은 명령/잘못된 시각 집계 문제를 REVIEW에 정확히 별도 차단점으로 적음 |
| 2. 시작 정체 6개와 30/60·90%, 18/18 구분 | `REVIEW.md:20` 이후: 24/30=80% 및 기전별 실패, 탐색/확증·보조 threshold 분리. 새 감도 결과라고 주장하지 않음 |
| 3. provenance 로그·관찰 불변 | `observation_contract.py:171` 이후 frame/command hash, baseline age/noise/state/alarm 기록. ON/OFF bytes·난수 및 입력 RGB 보존 검사 통과 |
| 4. 가짜 중단 순서와 다음 결정 | `fake_stop_contract.py:35`의 cancel→hold→기존 STATUS v5 abort→own job_failed→eligibility. 실제 scheduler의 2초 간격·예산 차단까지 fake wire로 검사. 실제 중단은 아님 |
| 5. 인수 handoff | `HANDOFF.md:6` 이후 최종 조합, 30/60+별도3흐름, 0.1초/1초, r2 뒷바퀴/divider 양성 대조 한계, p2f 0/208, 미래 10,800+360 SIM초와 복구 별도 명시 |

### A304-1 · MINOR — 4조건 매개변수는 실제 조건을 바꾸지 않는다

`tests/test_stall_observation_contract.py:218`의 `condition` 매개변수는 함수 본문에서 사용하지 않는다. 동일한 PairStatusChannel/FakePort 검사를 네 번 반복하므로 4조건 전체의 실제 scheduler 연결 검증이라고 읽어서는 안 된다. 현재 PR은 공통 enum/fake 계약이라고 제한하고 있어 비차단이다. 중복 매개변수를 없애거나 후속 연결 검사에서 조건별 실제 설정을 사용하면 검증 범위가 더 분명해진다.

관찰 어댑터는 입력 소유자 라벨을 검사하지만 라벨이 진짜 자기 카메라 픽셀이라는 것까지 인증하지 않는다. 이 한계를 모듈과 REVIEW가 명시하고 실제 생산자 승인을 미뤘다. 새로운 실시간 partner 정보, 정답, 측정 관절, weld, teacher 사용·기본 활성화·기존 봉인 변경은 없다. 이번 MERGE 의견으로 실제 D1 alarm/정지 경로를 켜면 안 된다.

## #305 — MERGE AFTER FIXES

### A305-1 · MAJOR — 기존 pair 도크 지도를 Scene 생성 전에 거절한다

근거: `sim/zone_own_scene_provider.py:6`, `harness/zone_environment_registry.py:61`, `:65`, `sim/zone_landmarks.py:290`. 도크 전용 분기는 여전히 `sim/zone_own_scene_provider.py:47`에 있지만 도달하지 못한다.

`zone_wide_door_tags_v2_dock_v3`는 기존 `DockTaggedCargoZoneScene`/`sim.zone_start_dock.dock_map()`이 처리하는 지도다. 새 resolver는 registry에 없는 모든 landmark 지도를 일반 `tagged_map(map_id)`로 검사한다. 이 ID는 일반 `ALL_TAGGED_MAPS`에 없으므로 `ValueError: unknown tagged zone map: zone_wide_door_tags_v2_dock_v3`가 난다. #292 합성의 정적 반례 준비 중에도 실제로 이 예외가 먼저 발생했다.

[기존 도크 경로 재현 코드](review_batch_a/REPRODUCERS.md#p01-legacy)는 `DockTaggedCargoZoneScene.from_tagged_cargo`만 fake로 바꾸고 같은 `own_scene(spec, 'cargo_noslip_v1')`를 main/#305에서 비교한다. Scene/World는 만들지 않는다. **main은 fake factory 호출 1회로 통과했고 #305는 호출 0회·위 ValueError로 거절됐다.** 출력은 [검증 기록](review_batch_a/VERIFICATION.md#p01-legacy)에 보존했다.

수정: 도크의 기존 `dock_map()` 검증을 resolver에서 유지하고 factory까지 도달하는 positive test를 추가한다. 새 final-map 거절 검사를 완화해 해결하지 않는다. 기존 38개 새 정적 테스트의 legacy 사례는 일반 tagged map뿐이어서 이 경로 회귀를 잡지 못했다. 지도/보정 bytes가 같아도 기존 실행 경로가 보존된 것은 아니다.

### A305-2 · MAJOR — 현재 v6e 봉인과 충돌하는 두 소스 변경

근거: `scripts/run_zone_study_integration.py:355`, `sim/zone_own_scene_provider.py:4`; 기존 `scripts/zone_pair_v6_contract.py:285`, `:287`.
A303-2와 같은 6개 등록 검사가 실패했다. v6e가 고정한 두 파일 중 runner의 현재 SHA-256은 `6f9ef85dedf10d84d0ec2f1779a14d225e3853e98fc3e6696aff3f4676e26833`, scene provider는 `2f77857b76edc6608741d5facfcc49fc6b37b2f60b9eed46ea9f5ab9882e0556`이다.

#249의 legacy source pins·원래 지도3/시나리오6/catalog가 보존된다는 검사는 맞지만 **그것이 v6e의 더 넓은 등록 소스 보존을 뜻하지는 않는다**. #292의 역사화 정리와 합성하고 새 후보로 검증해야 한다. 옛 등록·실험 파일을 현재 해시로 다시 봉인해서는 안 된다.

### A305-3 · MAJOR · 합성 차단 — #292의 후보 봉인에 새 환경 JSON 의존성이 빠진다

근거: #305 `harness/zone_environment_registry.py:25`, `:37`, `sim/zone_own_scene_provider.py:5`; #292 `scripts/zone_pair_v6_contract.py:86`, `:132` 이후의 `candidate_contract()` 명시 파일 목록.

#305는 legacy tagged map도 Scene 선택 전에 새 registry를 읽는다. 자기 integration `run_bundle`에는 registry/catalog를 넣었지만(`#305 scripts/run_zone_study_integration.py:72`, `:81`), #292의 별도 후보 생성기는 Python import closure와 자체 명시 파일만 수집한다. Python이 JSON을 읽는다는 사실만으로 그 JSON이 자동 봉인되지 않는다.

**독립 반례에서 registry status 변경 전후 후보 계약이 동일했다.** 269개 source에 resolver Python은 있지만 새 registry/final catalog JSON은 없다. 같은 변경으로 정상 legacy map의 resolver는 `invalid unsealed environment registry`로 거절됐다. [실제 출력](review_batch_a/VERIFICATION.md#p01-and-p292)을 보존했다. 재현 스크립트는 [P01/#292 재현 코드](review_batch_a/REPRODUCERS.md#p01-and-p292)다. 두 PR의 merge-tree를 임시 디렉터리에 풀고 새 registry의 status만 바꾼 다음 후보 계약과 resolver 결과를 비교하며, 끝에 원래 바이트를 복구한다.

수정: #292 최종 봉인 전에 새 registry·선택 catalog/map 및 동적 scene module을 후보의 명시 입력으로 추가하고 각각의 mutation을 거절하는 검사를 넣는다. 이 지적은 **미봉인 후보의 합성 문제**이며, 이미 봉인된 v6h 실행이 있었다는 주장이 아니다. #301은 새 명세를 받아 검증하는 도구이므로 합치기만 해서는 이 누락을 채워 주지 않는다.

### 완료 기준·입력 경계·테스트 평가

- P01-1: map→파일/정적 hash→Scene/model/provider/calibration 연결을 구현했다. `provider_binding()`의 거절은 factory보다 앞선다. 새 두 지도·로봇 v3를 v2 보정으로 허용하지 않는다.
- P01-2/3: 원래 지도3/시나리오6·#249 legacy bytes와 옛 tagged 공개 입력은 검사상 보존됐다. 새 등록은 `DRAFT_UNSEALED`, `research_result:false`다. v6e 등록 경로는 A305-2로 미완료이며 기존 도크 동작은 A305-1로 회귀했다.
- P01-4: fake factory·renderer/World/worker/network 차단 검사와 unknown map, 잘못된 model/hash/calibration, tagged→tag-free 반례가 실질적이다. 6시나리오 bundle 테스트는 provider 지원과 host_spec을 fake로 바꾸므로 **실제 6시나리오 실행 지원 증명은 아니다**. 문서도 이를 밝힌다. 실제 factory로 만든 XML/reset/카메라는 검사하지 않았다.
- P01-5: `experiments/2026-09-30-e2e-p01-env/README.md:34` 이후 3×30 SIM초 reset/겹침/카메라 후속 계획과 v3 보정 미확인을 기록했다.

정적 지도를 controller에 제공하는 허용 범위 안이다. GT pose/contact/success/partner 실시간 정보, weld ON, 교사 기반 학생 행동 보정을 새로 연결하지 않는다. 새 최종 지도를 기본값으로 선택하거나 미검증 provider를 자동 활성화하지 않는다. 단, legacy 경로도 새 registry 파일에 의존하게 되므로 배포/봉인의 새 의존성을 빠뜨리면 안 된다.

## PR 사이의 충돌과 합성 순서

`git merge-tree --write-tree`로 검토 대상의 12개 관련 쌍을 검사했다. 실제 브랜치를 병합하거나 worktree를 만들지 않았다. **12/12 텍스트 충돌 없음**이며, 이는 결합 테스트 통과나 봉인 적합성 판정이 아니다.

| 조합 | 텍스트 겹침 | 의미상 확인/남은 일 |
|---|---|---|
| #303 ↔ #305 | runner, CI 목록 | runner의 기록부와 bundle부로 수정 위치는 분리됨. 합성된 최종 source/bundle hash와 evidence roundtrip은 다시 검사해야 함 |
| #303/#305 ↔ #292 | CI 목록 | #292가 v6e를 역사화하는 방향은 A303-2/A305-2와 관련됨. 도크 회귀 A305-1은 #292도 막음. 새 후보 봉인은 최종 합성 뒤에만. #305의 새 JSON 의존성은 A305-3 |
| #303/#304/#305 ↔ #299 | CI 목록 | classifier/사전 등록 파일 직접 겹침 없음. #299는 pair-stage 판정이며 #303 study referee와 별도 schema/분모라 결과를 자동 합산하면 안 됨 |
| #303/#304/#305 ↔ #301 | CI 목록 | v2 dependency contract는 명시 도입용이며 legacy verifier를 자동 교체하지 않음. #305의 동적 `importlib.import_module(module)`은 새 명세의 `dynamic_imports`에 선언해야 함(`#301 harness/execution_dependency_contract.py:170`). registry 전체 파일과 선택 entry를 동시에 pin하면 `:181`에서 거절됨 |
| #304 ↔ #303/#305/#292 | CI 목록 | 운영 소비 경로 없는 prototype이고 enum/번들/workflow 신규 ID가 없어 직접 정책 충돌 없음. D1 실제 연결은 #293 승인·별도 controller PR이 필요 |

공통 결론: #292를 무조건 먼저 병합하라는 승인이 아니다. 그 PR의 독립 검토·물리 인수·CI 조건은 별도다. 두 evidence/environment PR은 과거 등록을 보존하는 호환 정리와 함께 다시 검토받고, 최종 봉인에서 새 입력을 빠뜨리지 않아야 한다.

## 기록·재현·남은 확인

- [검증 기록](review_batch_a/VERIFICATION.md)에 정확한 SHA, 선별 테스트, JUnit/log 해시, 합성 반례와 CI 상태를 남겼다. fake raw/event는 OS 임시 폴더에서만 만들었고 공용 TensorBoard에 게시하지 않았다.
- `reproduce_p06.py`는 #303 archive를 cwd/PYTHONPATH로 하여, `reproduce_p01_p292.py`는 기록된 합성 tree archive를 대상으로 **공용 잠금 아래** 실행한다. 기존 `.venv-sim-worker-mac/bin/python`을 사용한다. 실제 결과/등록부를 대상으로 실행하지 않는다.
- 실제 첫 실험의 TensorBoard snapshot·영상·pin/HParams UI 확인은 남아 있다. 이번에는 연구 실험 결과를 새로 만들지 않았으므로 공용 viewer를 열거나 snapshot을 변환하지 않았다.
- 실제 provider 호출·비용 정산, D1 30/60·중단3, 최종3지도 reset/충돌/카메라, E2E/PHYSICAL은 모두 미검증이다. 기존 raw·학습 모델·봉인 파일·snapshot을 삭제하거나 덮어쓰지 않았고 Drive 작업도 하지 않았다.
