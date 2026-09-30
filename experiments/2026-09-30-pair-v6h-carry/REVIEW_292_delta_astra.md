# PR #292 독립 delta 검토 — 2026-09-30

**판정: SEAL AFTER FIXES. `3c4fe30e`를 그대로 봉인하지 않는다.**

대상 HEAD: `3c4fe30e2197518443b195392212b0341507ac59`. 주 delta는 `3afc61b00f2c127ac3fbe2be5e7bb57da989b15a..3c4fe30e`이며, 이전 `origin/codex/review-292`의 `REVIEW_292_astra.md` 지적 1–5도 다시 확인했다. 제어기 구현에 참여하지 않은 독립 검토다. 작업 브랜치는 `codex/review-292b`; 제어기·봉인·원본 실험 파일은 수정하지 않았다. 작성물은 이 리뷰와 `tests/test_zone_pair_v6h_review_delta.py`의 반례뿐이다. 이 검토의 물리·렌더·모델 호출은 0회다.

현재 **pair 실행 경로의 sigma 범위는 probe k1g와 맞는다.** 새로 probe보다 약해진 가드는 발견하지 못했다. 다만 이전 지적 3의 의존성 고정은 아직 완전하지 않으며, 이전 지적 2는 요청대로 #299 통합까지 미해결이다. 검증 통과와 새 HEAD의 실제 인수 재생은 별도다.

## 발견 사항

### R292-D1 — MAJOR: 실제 plant·영상 입력 두 파일이 268개 pin 밖이다 (이전 지적 3 부분 해결)

- `scripts/zone_pair_v6_contract.py:86`의 폐쇄 계산은 Python import만 따라간다. 비 Python 입력은 명시 목록이어야 한다(`:89`, `:138`–`:183`). ArmSequence와 변경된 sigma 전달 모듈은 들어갔지만 **`sim/masterpi_dynamics_calibration.json`, `sim/masterpi_scene.xml`은 없다.** 둘 다 Git 추적 파일이다.
- 실제 실행 경로는 `harness/zone_own_team_host.py:88` → `sim/multi_masterpi_production.py:624`, `:644` → production template이다. 기본 `use_calibration_manifest=True`이며 `sim/masterpi_dynamics_v2.py:141`, `:150`, `:816`–`:821`에서 동역학/하드웨어 값을 읽어 적용한다. `sim/masterpi_dynamics_v2.py:107`, `:596`은 원본 XML을 읽는다. `floor_light_v1`은 그 XML의 일부 시각 속성만 바꾼다(`sim/render_profile.py:115`).
- 반례 1: 메모리에서 JSON의 `parameters.max_forward_force_n`을 현재 null에서 `3.3`으로 바꾸면 실제 순수 loader가 이를 fitted 값으로 읽는다. 반례 2: XML의 `znear=.002`를 `.02`로 바꾸면 `build_v2_xml()` + `floor_light_v1`의 결과 XML이 달라진다. **두 경우 모두 같은 합성 봉인의 `validate_plan()`이 그대로 통과했다.** `--runxfail`에서 각각 `DID NOT RAISE ValueError`로 재현했다. 원본 파일은 쓰지 않고 `Path.read_text/read_bytes`만 패치했다.
- 반례 위치: `tests/test_zone_pair_v6h_review_delta.py:39`, `:57`. `strict=True` xfail이며 예상 실패는 admission의 **DID NOT RAISE**에 한정했다. 모델 생성·물리·렌더를 사용하지 않는다.
- 실행 manifest의 전체 fingerprint와 깨끗한 HEAD 검사는 유용하지만, 이 입력의 변경을 **기존 봉인과 대조해 거부하는 검사**를 대신하지 않는다. 새 커밋/SHA로 실행할 때 같은 봉인이 다른 plant/영상을 허용할 수 있다. 기존 입력 누락을 이번 검토에서 찾은 것이며 sigma delta가 두 파일을 새로 읽기 시작했다는 뜻은 아니다.
- 최소 수정: 두 파일을 명시 pin하고 같은 seal에 대한 바이트 변조 거부를 검사한다. 새 경로의 동적 import·비 Python 입력도 실제 읽기 지점과 대조한다. preview/최종 seal을 갱신하고 이 반례가 통과하도록 xfail을 제거한다.

### R292-D2 — MAJOR, 기존 미해결 의존성: 분류기·평가 입력 연결은 #299 이후 재검토 필요

- 이 HEAD에는 `analysis/classify_placements.py`가 없고 `V6H_EXTRA_SOURCE_PATHS`에도 없다(`scripts/zone_pair_v6_contract.py:78`–`:83`). `REVIEW_RESPONSE.md:18` 이후의 TODO는 그대로다. 이를 새 sigma 결함으로 중복 계산하지 않았다.
- 조회한 #299는 OPEN/DRAFT, head `c86d9bac62036904ecc641db5e59e79edb58dec2`, base `claude/b-v6h-gain`이다. 단순히 그 PR이 병합됐다는 사실만으로 #292에 들어온 것은 아니다.
- 특히 해당 SHA의 `analysis/SEALED_INPUT.md:9`–`:23`은 별도 봉인 schema/실행 identity와 `evaluation_coverage`, `wall_contact.coverage`를 요구한다. 현재 builder의 schema(`build_prereg_v6h.py:59`) 및 raw writer(`scripts/run_pair_stage_probes.py:688`–`:698`)와 바로 같은 형식이 아니다. **파일 복사·pin 추가에 더해 builder/recorder → classifier의 실제 입력 호환 검증이 필요하다.** #299 원문도 러너 어댑터를 후속으로 명시한다.
- 이 검토에서 #299 코드를 통합·수정하거나 승인하지 않았다. 확정 평가 정의, 72건/시드별 판정, 전체 창 접촉·하드 한계와 누락 증거 거부까지 연결한 뒤 봉인해야 한다.

### R292-D3 — MINOR: 현재 workflow와 통합 문서에 폐기한 좁은 sigma 범위가 남았다

- `configs/simulation_workflows.json:742`는 v83을 여전히 `loaded-motion-only 1-sigma margin`이라고 설명한다.
- `docs/zone_study_integration.md:1`은 현재 후보에 대해 “접근·팔 스윕은 2σ”라고 쓴다. 실제 `PairPolicy`(`harness/zone_pair_v6_policy.py:148`–`:153`)와 반대다.
- README·REGISTRATION_PLAN·current_status의 수정은 확인했다. 이전 지적 5의 문서 일관성은 이 두 진입점까지 고쳐야 완료다. workflow registry는 source pin에도 포함되므로 최종 봉인 전에 정정한다.

## 모든 margin 호출과 probe의 대응

probe는 `harness/zone_pair_door_relax.py:85`–`:87`의 같은 연산 순서로 `SweepGuard.margin` 자체를 바꾼다(`:100`). 등록은 `harness/zone_own_guards.py:276`–`:280`의 인스턴스 값으로 선택한다. 아래 표의 1/1은 **자기 위치 sigma 두 항**이다.

| 직접 호출 위치 | 도달 경로·클래스 | probe / 등록 b-v6h1 |
|---|---|---|
| `zone_own_guards.py:288` | `SweepGuard.arm_clearance`; PairSweepGuard의 자기 팔·손가락 검사도 상속 | 1/1 = 1/1, unloaded/loaded 모두 |
| `zone_own_guards.py:305` | `SweepGuard.chassis_clearance`; translation/backoff, pair motion에서 호출 | 1/1 = 1/1 |
| `zone_own_guards.py:350` | `SweepGuard.transition_diagnostic`; 각 PWM 샘플 | 1/1 = 1/1 |
| `zone_own_guards.py:418` | `SweepGuard.plan`의 기록 margin; 실제 후보는 transition/arm 검사 | 1/1 = 1/1 |
| `zone_pair_geometry.py:94` | `PairSweepGuard.arm_clearance`의 전체 운반 빔 | 1/1 = 1/1 |
| `zone_pair_geometry.py:75` | `PairSweepGuard.stationary_beam_clearance`, preclose | 자기 위치 1/1 = 1/1; 같은 줄 다음의 빔-fit 불확실성은 양쪽 모두 **2σ** |
| `zone_pair_geometry.py:35`–`:36` | PairSweepGuard의 super 전달 | probe의 기본 2/2 인스턴스는 교체된 두 인수 함수를 호출; 등록은 `loaded=True`로 1/1 선택. 수식·caps 동일 |
| `zone_pair_global.py:218` → `:205` | `GlobalPairSweepGuard.certificate`와 margin override | 양쪽 모두 기존 **2σ**, caps 초과/잘못된 값은 inf. probe가 override를 교체하지 않음 |

`transition_clear`(`zone_own_guards.py:326`), `translation_clear`(`:367`), `backoff`(`:423`), `PairSweepGuard.motion_clear`(`zone_pair_geometry.py:103`)는 위 호출로 내려간다. 접근 driver의 look/pan/복귀·후진은 `GuardedPairApproach`의 작업별 가드 복사본(`zone_pair_guards.py:91`–`:100`)을 쓰고, pair 명령·시야 후보는 `sweep_guard()`(`:262`–`:272`; `zone_pair_executor.py:171`)를 쓴다. preclose도 이제 같은 정책 가드다(`zone_pair_guards.py:469`).

**차이가 남는 클래스/범위:** 활성 b-v6h1 pair 경로에서는 발견하지 못했다. 하지만 프로세스 전체가 동일한 것은 아니다. 원래 `ZoneOwnExecutor.guard`의 독립 `SweepGuard`는 2/2로 남는다(`zone_own_executor.py:138`; 새 테스트 `test_zone_pair_v6h.py:250`). 같은 프로세스에서 별도 solo look/delivery를 실행하면 전역 probe의 1/1과 다르다. 이는 다른 정책·뒤의 단독 작업을 바꾸지 않기 위한 명시적 격리이며 이 72건 chain에는 그런 job이 없다(`zone_own_executor.py:529`–`:565`). `SweepGuardV3`도 독립 인스턴스라면 전역 패치의 영향을 받지만, 현재 v2 chain에서 쓰지 않고 v3 pair는 host가 거부한다(`zone_own_team_host.py:83`). 별개 모듈 `owncam_sweep_collision.SweepGuard`는 probe의 패치 대상도 아니며 양쪽에서 그대로다. `GlobalPairSweepGuard`는 위처럼 차이가 없다. b-v6h1의 `beam_relative`와 `stationary_bootstrap`은 모두 False다.

S03 기록 자세의 0개 → 7개 후보 검사는 실제 `ranked_look_pans()`를 호출하고 probe와 후보·점수를 비교한다(`test_zone_pair_v6h.py:272`). 관찰 점수는 고정값이고 반올림된 자기 추정 fixture이므로 영상/PF/전체 commands 재생 증거는 아니다.

## 하드 한계와 기존 18개 정책

- delta에서 바뀐 가드는 sigma 선택과 인스턴스 전달뿐이다. 고정 35 mm, `.15 m/.20 rad` caps, geometry, 전이 샘플, translation의 표본 간 여유, motion의 명령 변위 pad와 `finally` 복구가 유지됐다(`zone_own_guards.py:277`, `:315`–`:384`; `zone_pair_geometry.py:111`–`:144`). probe k1g에도 없는 추가 2σ를 되돌린 것이며, **probe가 갖고 있던 guard를 제거한 변경은 발견하지 못했다.**
- preclose의 신선한 자기 추정·카메라 명령 일치·beam 추정 거부 조건은 그대로다(`zone_pair_guards.py:450`–`:467`). 상대 모드의 preclose는 `:456`에서 먼저 반환하므로 새 `:469` 호출로 GlobalPairSweepGuard 선택이 바뀌는 회귀도 없다. 빔-fit 2σ, global override, anchor/정합의 K_SIGMA(`:364`, `:392`)도 유지한다. k0/advisory 우회는 등록하지 않았다.
- penetration >5 mm / tilt >15°는 **평가 한계**다(`scripts/run_pair_stage_probes.py:320`, `:369`–`:391`). 이 값은 제어기가 즉시 멈추는 센서 기반 방어가 아니다. 해당 코드와 chain recorder는 sigma delta에서 변경되지 않았다. 전체 연쇄의 올바른 분류·누락 거부는 R292-D2로 남는다. p2f fail-open도 기존 명시된 한계이며 새 안전 정지 성능을 주장하지 않는다.
- `off_golden.json`은 최초 구현 `52264828`에서 추가된 뒤 수정 이력이 없다. 이전 리뷰 head `2c863fda`, admission 수정 `3afc61b0`, 현재 `3c4fe30e`에서 모두 SHA-256 **`697d4ed88dbccff5b00e8d8ddf940bbbbb0fa053af784020703ba0e5a64bd53d`**다. 이번 수정에 맞춰 기대값을 재생성하지 않았다.
- 기존 PF 검사는 동결된 `a8094cc1` carry 모듈을 별도 namespace/provider로 실행하고 localizer/beam-edge blob도 확인한다(`test_zone_pair_v6h.py:30`–`:87`). 새 기본 필드는 18개 정책에 2/2·`loaded_base_motion`이며, 옛 필드 골든도 별도로 비교한다. 기존 guard 골든은 4개 정책의 짧은 장면이라는 범위가 있다(`:142`).
- 검증 범위의 제어 출력 동등성과 전체 API/기록 바이트는 구별한다. 새 scope 필드·bundle/정책 메타데이터가 추가되므로 직렬화한 policy dict 자체까지 과거와 바이트 동일하다는 주장은 하지 않는다. 임의 입력·전체 에피소드의 완전 동등성도 이 오프라인 검사의 결론이 아니다.

## 이전 지적의 처리 상태와 봉인 조건

| 이전 지적 | 이번 확인 |
|---|---|
| 1 BLOCKER — 72건 admission 없음 | 구현은 해결. `zone_pair_v6h_admission.py:38`–`:71`이 실제 72 worker case와 builder 전체를 비교하며 `run_pair_stage_probes.py:1221`, `:399`에 연결됐다. 60×941 + 첫12×943, prior·배치·정책·floor_light_v1·L1 종료·PF/contact trace와 parser 옵션을 검사한다. 실제 CURRENT_REVISION 승격/봉인/실행은 아직 하지 않았다. |
| 2 MAJOR — 평가 정의·분류기 없음 | 미해결, 요청대로 #299 이후로 유보. R292-D2의 schema/recorder 연결까지 필요. |
| 3 MAJOR — 실행 의존성 누락 | ArmSequence 및 Python 전이 import 보강은 해결. 새 sigma 경로의 파일도 pin됨. R292-D1의 실제 JSON/XML 입력이 빠져 있어 전체 지적은 아직 닫지 않는다. |
| 4 MAJOR — 잘못된 timing params를 놓치는 테스트 | 고정 일정·0.1초 정지 tick을 실제 RoutedM2와 비교하는 검사로 보강됨(`test_zone_pair_v6h.py:441`–`:481`). 기대 수치는 호출부와 같은 helper로 재계산하지 않는다. M3 변이 재검증은 아래 기록. |
| 5 MINOR — loaded 범위·chain 팔 동작 설명 | README/REGISTRATION_PLAN은 lower/open/재파지/lift와 모든 not-approach yaw/p2f 범위를 정확히 나눈다. 좁은 sigma 구현은 실패 인수 뒤 승인된 probe 범위로 바뀌었다. R292-D3의 두 진입점은 아직 오래됐다. |

새 head의 commands 바이트/SHA, leg 검사, 전체 접촉·하드 한계 판정 인수는 조정자가 별도로 완료해야 한다. `68219d91`의 4/10 실패·7/7 원인 확인을 이 HEAD의 재생 성공으로 승계하지 않는다. 60+12건의 신선한 확증 성능·E2E·실물 결과도 이 검토에 없다.

## 이번 검증 기록

공용 잠금을 획득한 뒤 다음 검사를 순차 실행했다. 검사 소스 HEAD는 모두 `3c4fe30e2197518443b195392212b0341507ac59`이며, 원본 코드의 메모리 내 변이는 별도 프로세스에 한정했다.

| 검사 | 실제 결과 |
|---|---|
| 관련 18개 테스트 파일 | **643 passed, 2 xfailed**, 150.64 s. 두 xfail은 새 R292-D1 반례이며 예기치 않은 실패·skip은 0개다. |
| 새 반례만 `--runxfail` | **2 failed**, 각각 `DID NOT RAISE ValueError`. 사전 loader/XML 변경 assertion은 통과했다. |
| M3: 실제 `door_schedule()`의 `timing_calibration(...)`을 원본 `params`로 치환 | 고정 0.25/0.55/0.85 m 일정 검사 **3 failed**. 현재 소스에서는 세 검사 모두 통과한다. 이전 지적 4의 미검출은 해소됐다. |
| frozen `a8094cc1` 대 현재 HEAD, 별도 프로세스 | **18개 PF particle/난수/loaded params + 288개 일정 + 252개 fake guard 출력** JSON 바이트가 정확히 같다. 예외 0개. |
| builder·생성 worker 입력 | **72건 / 268개 pin**, case ID 중복 0개, 60×941 + 12×943, 모든 case의 L1 종료·두 trace·floor_light_v1 확인. 저장된 미봉인 source delta와 재계산 값도 같다. 실제 봉인·승격은 하지 않았다. |

pytest의 물리 step / 실제 vision worker / 네트워크 / 렌더 차단 카운터는 세 실행 모두 **0 / 0 / 0 / 0**이다. 시간은 실행 기록이며 속도 비교가 아니다. 이 숫자는 다른 작업의 인수 재생이나 PR 작성자의 검사 수와 합산하지 않았다.

- 18개 파일: `test_zone_pair_v6h`, `test_zone_pair_registered_source`, `test_zone_pair_v6`, `test_pair_stage_probe`, `test_pair_chain_probe`, `test_ci_sharding`, `test_zone_pair_v6h_review_delta`, `test_zone_pair_door_relax`, `test_zone_pair_preclose`, `test_zone_pair_grasp`, `test_zone_pair_executor`, `test_zone_pair_v6c`, `test_zone_pair_v6d`, `test_zone_pair_v6e`, `test_zone_pair_v6e_yaw`, `test_zone_pair_v6g`, `test_zone_own_executor_guards`, `test_owncam_bootstrap_v6b` (모두 `tests/<이름>.py`).
- off 대조 출력 SHA-256: **`fecacddb331628c1aeafb1f2f60f4954bb12a8e729faa3a2258d32743bb866c4`**. baseline harness는 현재 사본에서 변경된 10개 파일을 정확한 `a8094cc1` Git blob으로 복원했고 각각 바이트를 확인했다. 이전 독립 리뷰의 출력 해시와도 같다.
- 72 worker case JSON (`sort_keys=True`) SHA-256: `29c52b8d66aec8a2f8e8dcc1f78890b866615ace1b1cd75a64fd733341f62b97`.
- S03 fixture SHA-256: `2b91530c8c7ce1b173a8f3519e067cfd77f6e7b83540607db30ce098686b3d64`. 그 안에 적힌 원본 3개 파일의 해시도 3/3 일치했다. 0→7 후보/probe 점수 비교는 위 통과 검사에 포함된다.
- 기존 Mac 가상환경의 Python을 사용했다. `PYTHONDONTWRITEBYTECODE=1`, OMP/OpenBLAS/MKL/VECLIB 각각 1 thread, pytest cache off. `scripts.run_ci_tests.run_locked()`로 자기 PID의 잠금만 획득·반환했다. 전체 CI·실제 SIM 인수·새로운 확증 성능은 검증 범위 밖이다.

로컬 기록 경로: `/Users/changmin/projects/ugrp/outputs/review292b-delta-3c4fe30e/`. `validation.json`에 정확한 실행 명령·종료 코드·해시, `related-tests.log/xml`, `counterexamples-runxfail.log`, `M3-timing.log`, `off-*.log`에 원본 출력을 보존했다. margin 호출 목록, 골든·baseline receipt 및 보조 실행 스크립트도 같은 폴더에 있다. 동결 harness는 `/private/tmp/review292b-delta/`에 있다. 새 실험/학습 결과를 만든 작업이 아니므로 TensorBoard 변환·서버·화면 작업은 하지 않는다. UGRP의 Drive 제외 규칙을 적용했다. 리뷰와 반례는 지정 브랜치로 push하지만 로컬 로그 전체의 원격 백업을 뜻하지 않는다.
