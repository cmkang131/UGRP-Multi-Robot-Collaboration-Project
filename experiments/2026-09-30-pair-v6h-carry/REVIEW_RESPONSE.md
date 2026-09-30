# PR #292 독립 검토 대응 — 미봉인

검토 대상 원본: `2c863fda3fd2de2f0fc714c2367c3e81b440b530`.
검토 문서: `origin/codex/review-292`의 `eb7589750a32b1df40ed3e246947d7daaf46cb14`, `experiments/2026-09-30-pair-v6h-carry/REVIEW_292_astra.md`.
비교한 #285/#294 자료: `origin/claude/b-v6h-gain` `76e0f9ce793f8cbbff2349b2be2bbaa359250a42`.

작업 범위는 같은 `codex/pair-v6h-register`의 수정·오프라인 검사·커밋·푸시·PR 댓글이다. **봉인과 병합은 하지 않는다.** 물리·시뮬레이션·렌더·모델 호출 0회. 인수 재생의 잠금과 다른 작업의 소스는 건드리지 않았다. v83 / 2.16.0 / v6h, CURRENT_REVISION=v6e, 기존 v6e 등록 바이트를 유지한다.

| 지적 | 재현 Y/N | 처리 및 위치 | 검증 또는 남은 항목 |
|---|---|---|---|
| 1 BLOCKER: 72건 실행 계약 부재 | Y | 실제 builder 출력을 임시 파일에 쓰고 메모리에서만 CURRENT_REVISION=v6h로 바꾸어도 원본은 `v6 registration contract changed`로 거부했다. `scripts/zone_pair_v6h_admission.py:38`에서 72건 실제 worker 입력을 만들고 `:56`에서 봉인·설정·소스·배치/prior·scene/contact·floor_light_v1·L1 종료·trace를 전체 대조한다. `scripts/zone_pair_v6_contract.py:347` 및 `scripts/run_pair_stage_probes.py:1218`에 연결하고 worker도 `:395`에서 물리 import 전에 재검사한다. | `test_real_builder_72_case_admission_and_stage_probe_prepare`, `test_confirmatory_stage_options_cannot_override_seal`, `test_confirmatory_plan_tamper_rejected_even_with_recomputed_digest`, `test_worker_case_tamper_stops_before_physics`, `test_registered_execution_requires_source_and_one_bound_run`. 임시 fixture만 승격하며 실제 봉인은 없음. |
| 2 MAJOR: 최신 평가 정의·분류기 누락 | Y (정적 비교) | 이 브랜치에는 분류기·CLASSIFY 노트가 없고 PREREG_DRAFT §5.1은 구현 예정 문구다. #290은 main이 아닌 `claude/b-v6h-gain`에 병합됐다. 사용자 지시에 따라 이 지적의 코드/평가 정의는 **구현·병합하지 않음**. | **OPEN — 아래 정확한 병합/pin TODO가 끝나기 전 봉인 금지.** 다른 에이전트의 수정·시험을 이 작업의 결과로 세지 않는다. |
| 3 MAJOR: ArmSequence 및 명령 의존성 누락 | Y | 원본 104개 목록에 `scripts/zone_teacher.py`가 없었다. `scripts/zone_pair_v6_contract.py:80`에 ArmSequence를 명시하고 `:86`의 정적 import 폐쇄 검사로 전이 의존성도 고정한다. hold 판정·정적 충돌 형상·이벤트 스케줄러 등도 포함한다. 선택하지 않는 분기도 보수적으로 pin하지만 실행하지 않는다. | `test_real_chain_source_tamper_rejected`: ArmSequence의 CONTROL_S .1→.2 및 hold/keepout/scheduler 바이트 변경을 기존 봉인과 대조해 거부한다. Python 밖 입력·동적 import 진입점은 명시 목록에 남긴다. |
| 4 MAJOR: 잘못된 timing params 연결을 테스트가 놓침 | Y | 원본 호출의 `timing_calibration(...)`을 `params`로 바꿔도 기존 **64 passed**를 재현했다. 제어기 수식은 이미 맞으므로 바꾸지 않았다. `tests/test_zone_pair_v6h.py:300` 이후에 두 로봇의 실제 RoutedM2 일정·고정 수치·0.1초 `_carry()` 정지 tick을 추가했다. L0 .25/.55 m와 L1 .85 m, 서로 다른 PF x, κ 한 번 적용을 검사하고 기존 lateral 불변 검사를 유지한다. | `test_real_two_robot_schedule_and_carry_stop_ticks`. 수치는 독립 Decimal 50자리 역산과 검토자의 probe 수치로 고정했다. 동일 변이 재실행은 **3 failed, 101 passed**로 검출했다. 누락 pin 변이도 1 failed다. |
| 5 MINOR: loaded 범위·팔 동작 설명 | Y | 원본 REGISTRATION_PLAN의 “팔 스윕 완화를 한 번도 시험하지 않았다” 문구와 코드의 lower/open/재파지/lift를 대조했다. 파지 receipt 없는 align에서도 gate/p2f가 적용됨을 fake endpoint로 확인한다. `REGISTRATION_PLAN.md:33`, `README.md:12`, PR 본문에서 **σ는 confirmed-grasp base motion만, yaw/p2f는 모든 not approach 단계**로 나눠 썼다. 강화된 2σ arm/preclose 가드의 명령 영향은 인수 재생에서 확인해야 한다. | `test_scope_wording_matches_not_approach_gate_and_progress`와 기존 σ 범위 시험. 제어 범위를 넓히는 코드 변경 없음. 인수 목록은 #294의 5건으로 통일. |

## 지적 2 — 후속 병합과 봉인 입력 TODO

다음 경로의 수정이 `claude/b-v6h-gain`에 도착한 뒤 조정자가 **같은 검토 완료 SHA**에서 가져와야 한다. 현재 것은 복사하지 않았다.

- [ ] `experiments/2026-09-30-pair-v6h-carry/analysis/classify_placements.py`: 다른 에이전트가 고친 최종 분류기. `V6H_EXTRA_SOURCE_PATHS`에 이 경로 **한 줄** 추가. 일반 import 의존성은 자동으로 pin된다. 동적으로 읽는 `experiments/2026-09-30-door-relax-envelope/analysis/chain_analysis.py`와 그 분석 의존성은 이미 명시 pin에 있다.
- [ ] `experiments/2026-09-30-pair-v6h-carry/analysis/CLASSIFY_NOTES.md`: 같은 수정의 판정 설명. `V6H_EXTRA_SOURCE_PATHS`에 **한 줄** 추가. 전체 연쇄 접촉 창·중단·HOST_ERROR·보조 시드 안전 거부·하드 한계 우선순위를 코드와 대조한다.
- [ ] `experiments/2026-09-30-pair-v6h-carry/PREREG_DRAFT.md`: #294 최신 §5.1의 11개 정의와 후속 결정문을 병합. **이미 pin됨**. builder가 이 파일의 전체 원문·해시를 읽으므로 별도 admission 코드 수정은 필요 없다. 오래된 axial-OFF 문구도 이 후속에서 정리한다.
- [ ] `tests/test_v6h_classify_placements.py`: 분류기 수정의 회귀 검사를 함께 병합하고 로컬/CI 목록을 확인한다. 분류기 변이 거부 검사도 이 변경 뒤 수행한다.
- [ ] `experiments/2026-09-30-pair-v6h-carry/analysis/VALIDATION.md` 및 `analysis/PREREG_UPDATE_VALIDATION.md`: 해당 수정의 검증 출처와 SHA를 보존한다. 평가 정의를 담은 경우 그 경로도 명시 pin에 추가한다.
- [ ] 일반 setdown 관문(정의 6), teacher 준비와 실행 창 경계(정의 7), A=48/60 및 C=보고 전용의 최종 지위를 확정한다. 분류기가 최종 성공/σ 판정을 대신하지 않는다는 경계를 유지한다.
- [ ] 최종 입력에서 `source_changes_UNSEALED.json`을 갱신하고 전체 admission/분류기 검사를 다시 수행한 뒤 독립 검토와 인수 재생을 확인한다. 이 작업에서는 `prereg_v6h.json`을 만들거나 CURRENT_REVISION을 바꾸지 않았다.

## 인수 재생 목록

#294와 같은 **tS S01·S07 / tR hR2_04 / tX1 X01 / tX1b X06, seed 911**이다. 원문 `analysis/acceptance_replay_DRAFT.json`을 가져왔고 실행용 `acceptance_reference_DRAFT.json`도 같은 5건으로 맞췄다. 원본 commands/case/result 파일 15/15 해시를 읽어 확인했다. 실제 재생은 이 작업에서 하지 않았다.

요청의 “tS/tR/tX1b”와 달리 #294 원문 X01은 **tX1 (`f5d83fdb`)**이다. tX1b X01 raw는 찾지 못했다. 따라서 출처를 임의로 바꾸지 않고 #294의 정확한 5건을 유지했다. 조정자가 X01도 tX1b로 바꾸려면 그 원본 위치와 고정 해시가 필요하다.

명령 바이트/해시뿐 아니라 leg 검사 및 전체 기록의 접촉/하드 한계 판정까지 같아야 한다. 후자의 최종 정의/코드는 지적 2에 의존한다. 기준 해시 일치는 인수 재생 통과가 아니다.

## 검증 기록

기존 Python 3.12 환경에서 순수 PF·fake controller·합성 봉인만 검사한다. 스레드 수는 OMP/OPENBLAS/MKL/VECLIB 모두 1, `PYTHONDONTWRITEBYTECODE=1`, pytest cache는 끈다. 현재 인수 재생의 물리 잠금을 훼손하거나 가져오지 않는다. 아래 시간은 성능 비교가 아니다.

최종 테스트/변이 결과 및 파일 해시는 `analysis/review_292/validation.json`에 기록한다. 새 물리/학습/평가 결과가 없으므로 TensorBoard 변환·서버·Drive 작업 없음. 실제 확인 범위는 오프라인 코드 admission과 회귀 검사이며 물리·확증·E2E 성공이 아니다.

최종 관련 검사 + `tests/test_ci_sharding.py`: **309 passed** (114.19초). 파일: `tests/test_zone_pair_v6h.py`, `test_zone_pair_v6.py`, `test_zone_pair_registered_source.py`, `test_pair_stage_probe.py`, `test_pair_chain_probe.py`, `test_ci_sharding.py`. 새 v6h 파일은 105개 검사다.

변이(M3)는 수정 전 64 passed로 놓쳤고, 강화 후 3 failed/101 passed로 잡았다. ArmSequence pin 누락은 1 failed/104 deselected, 예전 잘못된 문구 복원도 1 failed/104 deselected다. 모두 저장소 파일을 수정하지 않는 메모리 변이다. 마지막 정상 테스트는 이 변이와 별도 프로세스에서 통과했다.

빌더 `verify(build())`는 **72건 / 268개 pin**을 확인했고 미봉인 해시 변화 목록을 갱신했다. 원본 소스 104개에서 추가한 것은 보수적인 전이 의존성이며, 모든 파일을 변경했다는 뜻이 아니다. 소스 폐쇄 검사는 일반 Python import를 정적으로 따라가고 비 Python/동적 선택 입력은 명시 pin으로 묶는다. `git diff --check` 통과, 과거 prereg 파일 및 `harness/zone_pair_executor.py` 변경 없음.

## 인수 재생 실패와 시그마 범위 수정

위 지적 5의 좁은 σ 범위는 당시 처리 기록이다. 이후 `claude/v6h1-acceptance-run` `68219d91`의 물리 인수 기록에서 등록 head `3afc61b0`는 lag-on 4/10만 일치했고 6건과 lag-off sanity는 leg 1 pregrasp 시야 후보가 사라져 실패했다. 모든 margin을 1/1로 덮어쓴 원인 확인은 7/7 명령 SHA·leg 일치를 회복했다. 이 작업은 그 기록을 읽었으며 제어기의 물리 인수 재생은 하지 않았다. 확장 pytest에 물리 통합 검사 1건을 포함한 실수로 렌더 초기화(`CGLError`)가 실패한 기록은 보존하고, 기존 no_physics 플러그인으로 그 파일을 재검사해 해당 검사를 제외한다.

조정자 결정에 따라 `door_relax_sigma_scope="probe_all_sweeps"`를 b-v6h1에만 등록한다. probe는 짐 없는/든 팔뿐 아니라 접근·후진·차체 이동과 preclose 자기 위치 여유의 모든 margin 호출을 1/1로 바꾼다. 별도 빔 영상 불확실성·GlobalPairSweepGuard·정합 검사의 K_SIGMA는 2다. [정확한 대응 표와 근거](SIGMA_SCOPE_CORRECTION.md)를 따른다. tS/tR/tX 29/29 탐색을 더 좁힌 제어기의 근거로 넘기지 않는다. 접촉 허용은 기존 사용자 결정이고 penetration >5 mm / tilt >15° 하드 한계는 평가 분류기의 우선 검사다(지적 2의 최종 병합/pin은 별도).

접근용 가드는 작업별 복사본으로 적용하고 own executor 가드를 바꾸지 않는다. preclose도 정책 가드를 쓰게 연결했다. 다른 18개 정책의 필드·정확한 2σ margin·PF·명령/monitor/gate 골든을 유지한다. S03 r2 28.2초의 기록 자세로 실제 시야 후보 필터를 검사한다: 2/2는 후보 0개, 1/1은 7개이며 probe와 후보·점수가 정확히 같다. observability는 양의 고정값이며 영상·PF·물리 재생이 아니다.

새 검증은 `analysis/sigma_scope/validation.json`과 JUnit에 기록한다. 소스 해시 변화 목록과 builder의 범위 선언을 갱신했고 운반 일정·정지 tick 골든은 유지한다. `prereg_v6h.json` 없음, CURRENT_REVISION=v6e, PR draft 유지, 봉인·병합 없음. **새 head SHA에서 조정자의 물리 인수 재생이 필요하다.**

이번 수정의 검사: `test_zone_pair_v6h.py` **140 passed**, `test_zone_pair_registered_source.py` **24 passed**. 검색으로 고른 관련 44개 파일은 **1371 passed / 물리 통합 1 failed(CGLError)**였고, 유일한 실패 파일을 기존 no_physics 플러그인으로 재검사한 결과 **14 passed / 물리 1 skipped**다. 제어기 소스는 두 검사 사이에 바뀌지 않았다. 중복을 뺀 오프라인 통과는 **1535개**이며 실패 시도와 제외 확인을 모두 보존했다. 빌더 두 모드는 **미봉인 72건 / 268개 pin**을 확인했다.
