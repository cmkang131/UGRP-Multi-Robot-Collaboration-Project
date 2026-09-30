# b-v6h1 등록 제어기 구현 — 봉인 전, 독립 검토 필요

Refs #216. `codex/pair-v6h-register`, base `a8094cc14e098a55483f53a3c49bf6a0b116043d`. 구현과 지정된 오프라인 단위 검증만 했다. 물리·시뮬레이션·실모델 호출 0, 새 실험 결과 0. 기본 체크아웃과 다른 브랜치는 수정하지 않았다. 아래 탐색 raw는 비교 기준을 읽었을 뿐 이 구현의 성능 근거로 합산하지 않았다. UGRP 예외에 따라 Google Drive는 사용하지 않았다.

예약: revision **v6h**, policy **b-v6h1**, bundle **zone-pair-v83-carry-door-gain**, workflow **2.16.0**. `git fetch origin`과 `gh pr list --state open` 뒤 main 및 유일한 열린 #285 브랜치에서 `git grep RUNNABLE_ID ... -- harness/rgb_execution_bundle.py`와 정책·통합·workflow 설정을 확인했다. 실행 중 최대 v81; v82/2.15.0은 기존 계획대로 미사용 유지. #290은 `claude/b-v6h-gain`에 병합됐으며 이 브랜치에는 분류기가 아직 없다. 문서에서의 v83 예약 언급은 실행 등록 사용으로 세지 않았다.

## 변경과 경계

b-v6h1 = b-v6g + 다음 다섯 옵션(σ 옵션은 xy/yaw 배수와 적용 범위 필드). 다른 18개 정책은 새 필드를 모두 기본값으로 갖는다.

- `carry_fwd_gain=0.9483378899463337`: PF의 loaded `gain[0][0]`만 복사 후 한 번 곱한다. 원본 dict·다른 PF·unloaded 프로필은 보존하고 다른 설정으로 바인딩된 provider 재사용은 거부한다. PR #284 적합 입력을 바이트 그대로 복사했으며 SHA-256은 `02884b59026d34710473e97a154e8ffff6132dd388d36f8c893b0f2a616a2f56`이다.
- `loaded_k_xy=loaded_k_yaw=1`, `door_relax_sigma_scope="probe_all_sweeps"`: probe가 바꾼 모든 margin 호출(짐 없는/든 팔, 접근·후진·차체 이동, preclose의 자기 위치 여유)에 적용한다. 파지 확인(confirmed grasp)을 조건으로 삼지 않는다. 별도 빔 영상 불확실성, GlobalPairSweepGuard와 정합 검사 K_SIGMA는 2로 남는다. 다른 정책은 기본 `loaded_base_motion`/2·2를 유지한다. [정확한 대응 표와 인수 실패 근거](SIGMA_SCOPE_CORRECTION.md).
- `loaded_gate_yaw_deg=(5,4)`: **모든 not approach 단계**(파지 전 align·재파지 포함)에서 gate·driver·sweep recheck는 인스턴스별 프로필을 쓰며 기존 GATE_LOADED·GATE_UNLOADED 싱글턴을 바꾸지 않는다.
- `progress_arm_on_moved_fix=True`: p2f를 쌍 감시기의 **모든 not approach 단계**에 적용한다(align·재파지 포함). 첫 이동 명령보다 엄격히 뒤의 finite fix로만 baseline을 세운다. 시각 없음·NaN·infinity는 무장하지 않는다. **no reliable stall detection for the loaded pair**: 새 fix가 없으면 fail-open이며 unloaded GuardedDriver 감시기는 그대로다. 새 정책 raw에 `progress_moved_fix` 무장·무시 수를 기록한다.
- `carry_axial_lag=True`: 축 방향 시간 역산도 같은 gain을 쓴 복사본의 lag plant로 계산한다. 이 옵션은 carry_fwd_gain 보정을 요구한다. 옆 이동 시간과 전역 LAG_AXES는 바꾸지 않는다.

GT·접촉·측정 관절·sim 상태를 제어기에 추가하지 않았다. weld는 계속 OFF다. `--env-placements`는 기존 탐색의 `base/coarse` 시트 준비 경로를 그대로 옮긴 stage-probe 설정이며 teacher staging에만 사용한다. b-v6h1은 기존 probe-only `b-v6h`와 별개의 정책 id다.

## 미봉인 빌더와 원본 보존

초기 `REGISTRATION_PLAN.md`와 현재 `make_confirmatory_placements.py`, `placements_confirmatory_DRAFT.json`은 #285 `af2afb5b657a81fa88459778afb2cdac35a9aab5`의 바이트 그대로다. `PREREG_DRAFT.md`는 같은 원문 앞에 2026-09-30 조정자의 axial-lag 추가 결정을 한 줄만 붙였다. 배치 재추첨 없이 고정 시드 20260941의 산출물을 검증한다. 필요한 탐색 제외 목록 2개도 #285에서 원본 그대로 복사했다. 이번 리뷰 대응에서 REGISTRATION_PLAN의 적용 범위·인수 목록을 고쳤다. PREREG_DRAFT의 최신 평가 정의 반영은 지적 2의 후속 작업이며 아직 보류한다. builder의 `coordinator_decisions`는 현재 구현 선택을 명시한다.

```sh
python -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h --dry-run
python -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h --verify
```

두 모드는 파일을 쓰지 않는다. builder는 60개 새 배치(seed 941) + 첫 12개 배치 민감도(seed 943, 주 통과율 분모 제외; 안전 거부 정의는 지적 2 반영 필요), 전이 import를 포함한 소스·입력 해시, predecessor v6e receipt, scene/contact receipt, 원문 전체, loaded fail-open 경계를 메모리에서 구성한다. chain L0/L1 종료, floor_light_v1, contact/PF trace, workers 4/OMP 1, raw 절대 경로, ENOSPC=HOST_ERROR도 명시한다. A=48/60(관측 비율 기준, 모집단 80% 증명 아님), C=보고만이라는 초안 기본값을 유지했다.

**최종 봉인은 하지 않았다.** `prereg_v6h.json` 없음, registration_sha256=null, CURRENT_REVISION은 v6e 그대로다. v6e는 `e510779db7be07be2b54493d52a9c754bd59a5bc`의 blob으로만 감사하고 현재 소스로 prepare/run하지 못한다. v81은 은퇴 목록으로 옮겼다. 독립 검토가 끝난 뒤 조정자가 별도 커밋 **`Seal v6h after independent review`**에서 봉인 JSON 생성과 CURRENT_REVISION 전환을 함께 수행해야 한다. 이 작업에서는 그 커밋을 만들지 않았다.

## 검증

허용된 파일만 실행했다: `tests/test_zone_pair_v6h.py` **64**, `tests/test_zone_pair_registered_source.py` **24**, `tests/test_ci_sharding.py` **66**, 합계 **154 passed**(14.92초; 성능 측정이 아님). `scripts.run_ci_tests.run_locked`로 공용 잠금을 획득·반환하고 pytest를 실행했다. 마지막 JUnit: `/Users/changmin/projects/ugrp/outputs/v6h-register-unit-20260930/pytest-ci-fix-01.xml`. 모든 이전 시도도 같은 폴더에 보존했다. 첫 5개 실패는 잘못된 테스트 역할명과 JSON tuple/list 계약 차이를 고쳤고, 추가 guard golden 준비 오류도 수정했다. 지정되지 않은 테스트는 로컬에서 실행하지 않았다.

18개 기존 정책의 loaded PF 출력은 main `a8094cc1`의 저장된 평균·표준편차 골든과 1e-9 이내다. 입자 bytes와 난수 상태는 같은 호스트에서 동결된 main carry 모듈을 별도 provider로 실행한 값과 정확히 일치한다. localizer/beam-edge 의존성은 그 commit의 blob과 현재 바이트가 같은지도 확인한다. 저장된 Mac 입자 해시는 참고 기록이며 Linux에 그대로 강제하지 않는다. 4개 대표 정책의 PairCommandGuard 명령·monitor·gate 골든도 일치한다. 각 옵션의 on/off, gain 복사/중복 적용/재사용 방지, 당시 loaded-motion 범위, invalid fix, axial 시간, 정책·번들·CI 목록·workflow 조합을 검사했다. 빌더 두 모드와 stage-probe CLI의 `--policies b-v6h1 --stage chain` 계획 모드도 확인했다(새 output 폴더나 물리 생성 없음). `git diff --check` 통과. 단위 검증을 인수 재생·E2E·실물 성공으로 표현하지 않는다. 새 실험 결과가 없으므로 TensorBoard 변환·서버 시작은 하지 않았다.

초기 push CI (`36687347436`)의 shard 3/5/7에서 기존 정책 기본값 표 누락, 역사 봉인의 현재 바이트 검사, Mac/Linux 입자 해시 차이를 발견했다. 앞의 두 테스트는 새 기본값·봉인 commit 감사로 갱신했고, 마지막은 같은 호스트의 이전 소스와 정확한 입자 bytes/난수 상태를 비교하도록 고쳤다(저장된 1e-9 골든 검사는 유지). 실패 로그 3개를 primary outputs에 보존했고 허용된 세 파일 재실행은 154 passed다. 수정 후 CI 결과는 PR에서 별도로 확인한다.

## 봉인 뒤 확증 admission

리뷰 지적 1 대응으로 실제 빌더의 **72건 전체**와 worker 입력을 봉인에 포함한다. `scripts/zone_pair_v6_contract.load_config`는 v6h를 전용 adapter로 보내며, 과거 6건 형식은 거부한다. 실행 CLI는 `scripts.run_pair_stage_probes --prereg`다. `run_zone_pair_dev`는 이 연쇄 형식을 실행하지 않는다.

아래는 **향후 조정자 봉인 뒤 준비만 하는 명령**이다. 현재는 CURRENT_REVISION=v6e와 미봉인 상태이므로 거부되는 것이 정상이다. 봉인에는 `sealed=true`와 전체 등록 내용의 `registration_sha256`이 필요하다. DRAFT는 준비만 가능하다. 빌더 자체에는 저장/봉인 기능이 없다.

```sh
python -m scripts.run_pair_stage_probes \
  --prereg experiments/2026-09-30-pair-v6h-carry/prereg_v6h.json \
  --stage chain --policies b-v6h1 --sources teacher \
  --seeds 941 --nominal-seeds 941 \
  --env-placements experiments/2026-09-30-pair-v6h-carry/placements_confirmatory_DRAFT.json \
  --render-profile floor_light_v1 --chain-stop-leg 1 --pf-track --contact-track \
  --workers 4 --omp-threads 1 --output /Users/changmin/projects/ugrp/outputs/v6h-confirmatory-NEW
```

주 시드 941의 60건과 봉인된 첫 12곳/시드 943를 함께 준비한다. 제한·재배치·prior·정책·렌더·종료 leg·trace·worker/OMP/timeout 옵션 변경은 거부한다. 입력 파일·소스 해시와 실제 파생 case 전체를 검사하며 worker도 물리 import 전에 다시 검사한다. `REGISTERED` 실행은 기존 조정자 승인 봉투(authorization envelope), live GitHub 검증, 깨끗한 고정 HEAD, 잠금과 새 raw 경로가 필요하다. 기존 승인 형식은 run별이므로 `--run-id <봉인 ID> --expected-source-sha <40자리 SHA> --execute --lock-owner <소유자>`로 한 승인 run을 선택한다. 전체 72건 검사는 선택 전에도 유지한다. 승인 없는 probe는 manifest에 `unsealed_stage_probe`로 표시한다.

소스 목록은 기존 명시 입력에 Python 전이 import를 더한 보수적 폐쇄 목록이다. 선택하지 않은 분기의 모듈도 해시로 묶지만 실행하거나 제어 입력으로 전달하지 않는다. `scripts/zone_teacher.py`의 ArmSequence 보간·발행 로직, hold 판정, 스케줄러도 포함한다. 분류기는 지적 2가 끝난 뒤 `V6H_EXTRA_SOURCE_PATHS`에 진입점 한 줄을 추가하면 의존성까지 고정된다. 문서 등 비 Python 입력은 각각 한 줄을 추가한다.

## 조정자의 인수 재생 (이 작업에서는 실행하지 않음)

#294의 **5건**으로 통일했다: **tS S01·S07, tR hR2_04, tX1 X01, tX1b X06; 전부 seed 911**. `analysis/acceptance_replay_DRAFT.json`은 #294 원문, `acceptance_reference_DRAFT.json`은 같은 case의 b-v6h1 실행 입력이다. 각 원본 case/result/commands 해시 15/15를 읽어 확인했다. X01은 #294 원문상 tX1이며 tX1b X01 raw는 없으므로 출처를 바꾸지 않았다. 요청의 tS/tR/tX1b 약칭과 다른 부분은 이 한 건이다.

모두 gain+p2f+k1g+axial ON 원본이며 OFF sB/cA 및 과거 PR #292의 6건 목록을 대체한다. S07의 OFF 실패는 역사 기록에 그대로 남는다. raw는 로컬 보관이고 원격 백업이 아니다. 기준 해시 확인은 새 구현의 인수 통과가 아니다.

조정자는 고정된 깨끗한 커밋·SIM 시간·weld OFF·OMP 1·자기 잠금/driver·새 raw 경로에서 이 목록의 `case`만 `run_worker`에 전달한다. `expected_*`는 평가 전용이다. **commands.json 바이트 및 전체 SHA-256 동일**, leg 검사 동일, **연쇄 전체 접촉/하드 한계 판정 동일**을 모두 확인해야 한다. leg 체크만 같은 것은 통과가 아니다. 마지막 판정의 분류기/정의 병합은 지적 2 TODO가 남아 있다.

연쇄는 최초 접근을 생략하지만 L0 뒤 lower/open/재파지/lift를 실행한다. 기존 head `3afc61b0`의 인수 재생은 10건 중 6건에서 pregrasp 시야 후보가 사라져 실패했다. 이번 σ 범위 수정은 probe와 같은 범위를 등록하지만 **새 SHA의 물리 인수 재생은 조정자가 다시 수행해야 한다**. 결과를 추정하지 않는다. 불일치가 있으면 독립 검토로 원인을 해결하기 전 확증을 시작하지 않는다. 종료 시 자기 자식·잠금만 정리하고 실제 새 결과는 native TensorBoard에 별도 등록·표시 확인한다.

## 남은 결정과 참고 자료

- 독립 Opus 검토 및 최종 봉인 커밋, 최종 분류기/정의 병합, 통일된 물리 5건 재생, 확증 60+12건은 조정자 소관이다.
- 초안 A=48/60 유지 또는 B=55/60 선택, 과보수 C를 보고만으로 유지할지는 봉인 전에 결정한다. 접근·팔 스윕의 σ 범위는 인수 실패 뒤 조정자 결정으로 probe와 맞췄다. 별도 정지 검출기 구현은 이번 범위가 아니다.
- [#285 탐색 및 등록 계획](https://github.com/kcm0127-dotcom/ugrp/pull/285), [#284 gain 적합](https://github.com/kcm0127-dotcom/ugrp/pull/284), [#286 axial-lag 진단](https://github.com/kcm0127-dotcom/ugrp/pull/286), [#290 분류 보완](https://github.com/kcm0127-dotcom/ugrp/pull/290).
- [실행 버전 관리](../../docs/execution_versioning.md), [평가 정의 갱신 대기 초안](PREREG_DRAFT.md), [등록 계획](REGISTRATION_PLAN.md), [미봉인 소스 변화 전체](source_changes_UNSEALED.json), [검증 기록](validation.json).

이번 독립 리뷰 대응의 지적별 재현·시험·남은 의존성은 [REVIEW_RESPONSE.md](REVIEW_RESPONSE.md)를 따른다. 위 154 passed는 최초 구현 당시 기록이다.

리뷰 대응 최종 오프라인 검사는 **309 passed**이며 M3 시간 연결 변이는 새 고정 일정 검사 3개가 실패해 검출했다. 소스 pin은 268개다. 지적 2의 분류기/평가 정의 반영과 조정자의 인수 재생·봉인은 여전히 별도다.

인수 실패 뒤 σ 범위 수정과 정확한 대응 표는 [SIGMA_SCOPE_CORRECTION.md](SIGMA_SCOPE_CORRECTION.md)를 따른다. 이번 필수 검사는 **164 passed**(v6h 140 + 등록 소스 24), 관련 검사는 **1371 passed**다. 확장 검사에 잘못 포함된 물리 통합 1건은 렌더 초기화(CGLError)에서 실패했고, 기존 no_physics 플러그인으로 해당 파일을 재검사해 **14 passed / 물리 1 skipped**를 확인했다. 소스 변경 없이 통과한 오프라인 고유 검사는 **1535개**이며 결과를 중복 합산하지 않았다. 원시 실패·재검사·builder 기록은 `analysis/sigma_scope/validation.json`에 있다. 새 SHA의 물리 인수 재생은 조정자가 다시 수행해야 한다.
