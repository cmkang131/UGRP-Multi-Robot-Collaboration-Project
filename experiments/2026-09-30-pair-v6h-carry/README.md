# b-v6h1 등록 제어기 구현 — 봉인 전, 독립 검토 필요

Refs #216. `codex/pair-v6h-register`, base `a8094cc14e098a55483f53a3c49bf6a0b116043d`. 구현과 지정된 오프라인 단위 검증만 했다. 물리·시뮬레이션·실모델 호출 0, 새 실험 결과 0. 기본 체크아웃과 다른 브랜치는 수정하지 않았다. 아래 탐색 raw는 비교 기준을 읽었을 뿐 이 구현의 성능 근거로 합산하지 않았다. UGRP 예외에 따라 Google Drive는 사용하지 않았다.

예약: revision **v6h**, policy **b-v6h1**, bundle **zone-pair-v83-carry-door-gain**, workflow **2.16.0**. `git fetch origin`과 `gh pr list --state open` 뒤 main 및 유일한 열린 #285 브랜치에서 `git grep RUNNABLE_ID ... -- harness/rgb_execution_bundle.py`와 정책·통합·workflow 설정을 확인했다. 실행 중 최대 v81; v82/2.15.0은 기존 계획대로 미사용 유지. #290은 병합됨. 문서에서의 v83 예약 언급은 실행 등록 사용으로 세지 않았다.

## 변경과 경계

b-v6h1 = b-v6g + 다음 다섯 옵션(σ 옵션은 xy/yaw 두 필드). 다른 18개 정책은 새 필드를 모두 기본값으로 갖는다.

- `carry_fwd_gain=0.9483378899463337`: PF의 loaded `gain[0][0]`만 복사 후 한 번 곱한다. 원본 dict·다른 PF·unloaded 프로필은 보존하고 다른 설정으로 바인딩된 provider 재사용은 거부한다. PR #284 적합 입력을 바이트 그대로 복사했으며 SHA-256은 `02884b59026d34710473e97a154e8ffff6132dd388d36f8c893b0f2a616a2f56`이다.
- `loaded_k_xy=loaded_k_yaw=1`: 든 쌍의 **base motion** 중에만 적용한다. 접근·preclose·팔 스윕(든 상태의 팔 스윕 포함)은 2/2다. GlobalPairSweepGuard와 정합 검사 K_SIGMA는 2로 남는다.
- `loaded_gate_yaw_deg=(5,4)`: gate·driver·sweep recheck는 인스턴스별 loaded 프로필을 쓰며 기존 GATE_LOADED·GATE_UNLOADED 싱글턴을 바꾸지 않는다.
- `progress_arm_on_moved_fix=True`: p2f를 쌍의 감시기에만 적용한다. 첫 이동 명령보다 엄격히 뒤의 finite fix로만 baseline을 세운다. 시각 없음·NaN·infinity는 무장하지 않는다. **no reliable stall detection for the loaded pair**: 새 fix가 없으면 fail-open이며 unloaded GuardedDriver 감시기는 그대로다. 새 정책 raw에 `progress_moved_fix` 무장·무시 수를 기록한다.
- `carry_axial_lag=True`: 축 방향 시간 역산도 같은 gain을 쓴 복사본의 lag plant로 계산한다. 이 옵션은 carry_fwd_gain 보정을 요구한다. 옆 이동 시간과 전역 LAG_AXES는 바꾸지 않는다.

GT·접촉·측정 관절·sim 상태를 제어기에 추가하지 않았다. weld는 계속 OFF다. `--env-placements`는 기존 탐색의 `base/coarse` 시트 준비 경로를 그대로 옮긴 stage-probe 설정이며 teacher staging에만 사용한다. b-v6h1은 기존 probe-only `b-v6h`와 별개의 정책 id다.

## 미봉인 빌더와 원본 보존

`REGISTRATION_PLAN.md`, `make_confirmatory_placements.py`, `placements_confirmatory_DRAFT.json`은 #285 `af2afb5b657a81fa88459778afb2cdac35a9aab5`의 바이트 그대로다. `PREREG_DRAFT.md`는 같은 원문 앞에 2026-09-30 조정자의 axial-lag 추가 결정을 한 줄만 붙였다. 배치 재추첨 없이 고정 시드 20260941의 산출물을 검증한다. 필요한 탐색 제외 목록 2개도 #285에서 원본 그대로 복사했다. 문구가 과거의 axial-lag 미결정을 설명하는 부분은 그대로 보존했으며 builder의 `coordinator_decisions`가 현재 선택을 명시한다.

```sh
python -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h --dry-run
python -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h --verify
```

두 모드는 파일을 쓰지 않는다. builder는 60개 새 배치(seed 941) + 첫 12개 배치 민감도(seed 943, 판정 제외), 104개 소스·입력 해시, predecessor v6e receipt, scene/contact receipt, 원문 전체, loaded fail-open 경계를 메모리에서 구성한다. chain L0/L1 종료, floor_light_v1, contact/PF trace, workers 4/OMP 1, raw 절대 경로, ENOSPC=HOST_ERROR도 명시한다. A=48/60(관측 비율 기준, 모집단 80% 증명 아님), C=보고만이라는 초안 기본값을 유지했다.

**최종 봉인은 하지 않았다.** `prereg_v6h.json` 없음, registration_sha256=null, CURRENT_REVISION은 v6e 그대로다. v6e는 `e510779db7be07be2b54493d52a9c754bd59a5bc`의 blob으로만 감사하고 현재 소스로 prepare/run하지 못한다. v81은 은퇴 목록으로 옮겼다. 독립 검토가 끝난 뒤 조정자가 별도 커밋 **`Seal v6h after independent review`**에서 봉인 JSON 생성과 CURRENT_REVISION 전환을 함께 수행해야 한다. 이 작업에서는 그 커밋을 만들지 않았다.

## 검증

허용된 파일만 실행했다: `tests/test_zone_pair_v6h.py` **64**, `tests/test_zone_pair_registered_source.py` **24**, `tests/test_ci_sharding.py` **66**, 합계 **154 passed**(14.92초; 성능 측정이 아님). `scripts.run_ci_tests.run_locked`로 공용 잠금을 획득·반환하고 pytest를 실행했다. 마지막 JUnit: `/Users/changmin/projects/ugrp/outputs/v6h-register-unit-20260930/pytest-ci-fix-01.xml`. 모든 이전 시도도 같은 폴더에 보존했다. 첫 5개 실패는 잘못된 테스트 역할명과 JSON tuple/list 계약 차이를 고쳤고, 추가 guard golden 준비 오류도 수정했다. 지정되지 않은 테스트는 로컬에서 실행하지 않았다.

18개 기존 정책의 loaded PF 출력은 main `a8094cc1`의 저장된 평균·표준편차 골든과 1e-9 이내다. 입자 bytes와 난수 상태는 같은 호스트에서 동결된 main carry 모듈을 별도 provider로 실행한 값과 정확히 일치한다. localizer/beam-edge 의존성은 그 commit의 blob과 현재 바이트가 같은지도 확인한다. 저장된 Mac 입자 해시는 참고 기록이며 Linux에 그대로 강제하지 않는다. 4개 대표 정책의 PairCommandGuard 명령·monitor·gate 골든도 일치한다. 각 옵션의 on/off, gain 복사/중복 적용/재사용 방지, loaded-motion 범위, invalid fix, axial 시간, 정책·번들·CI 목록·workflow 조합을 검사했다. 빌더 두 모드와 stage-probe CLI의 `--policies b-v6h1 --stage chain` 계획 모드도 확인했다(새 output 폴더나 물리 생성 없음). `git diff --check` 통과. 단위 검증을 인수 재생·E2E·실물 성공으로 표현하지 않는다. 새 실험 결과가 없으므로 TensorBoard 변환·서버 시작은 하지 않았다.

초기 push CI (`36687347436`)의 shard 3/5/7에서 기존 정책 기본값 표 누락, 역사 봉인의 현재 바이트 검사, Mac/Linux 입자 해시 차이를 발견했다. 앞의 두 테스트는 새 기본값·봉인 commit 감사로 갱신했고, 마지막은 같은 호스트의 이전 소스와 정확한 입자 bytes/난수 상태를 비교하도록 고쳤다(저장된 1e-9 골든 검사는 유지). 실패 로그 3개를 primary outputs에 보존했고 허용된 세 파일 재실행은 154 passed다. 수정 후 CI 결과는 PR에서 별도로 확인한다.

## 조정자의 인수 재생 (아직 실행하지 않음)

계획 §6의 기존 sB/cA는 axial_lag=off다. 기본 b-v6h1은 on이므로 이 원본과 **같은 commands.json 해시를 요구하는 것은 조건이 맞지 않는다**. 이는 시간 계산을 바꾸라는 조정자 결정에 따른 의도된 차이다. 비교 기준을 확정하기 전 확증 코호트를 시작하지 않는다.

대안 초안 `acceptance_reference_DRAFT.json`: 같은 gain+p2f+k1g+axial-on 탐색 원본의 tS S01/S02/S03/S07, tR hR2_01(5건), tX1b X06(추가 axial 사례), 전부 seed 911. S07의 lag-off 실패는 그대로 역사 기록이고 lag-on 기준에서는 통과다. 각 원본 `commands.json` 전체 SHA-256·plan 해시·소스 SHA를 읽어 확인했다. 실제 경로는 로컬 보관이며 원격 백업이 아니다. expected leg checks는 **평가 전용**이며 run_worker에는 `case`만 전달한다. raw 스키마는 `scripts/run_pair_stage_probes.py`의 safe_name/finish_result와 `harness/pair_chain_probe.py:leg_checks`를 읽어 확인했다(manifest.source.source_sha, result.row.chain).

조정자가 이 대안을 선택하면, 깨끗한 소스 커밋을 고정하고 새 raw 경로를 정한 뒤 `ugrp_session.py run`으로 자신의 driver를 시작한다. 그 driver의 PID로 `agent_lock.py acquire --owner codex --branch codex/pair-v6h-register --purpose v6h-acceptance --pid <driver PID> --expected-minutes 10` 잠금을 잡는다. driver에서 다음처럼 한 건씩 `run_worker`를 호출한다(SIM 시간, weld OFF, OMP 1; baseline 원본은 쓰지 않음).

```python
import hashlib, json
from pathlib import Path
from scripts.run_pair_stage_probes import run_worker, safe_name
from harness.pair_chain_probe import leg_checks
refs = json.loads(Path('experiments/2026-09-30-pair-v6h-carry/acceptance_reference_DRAFT.json').read_text())
out = Path('/Users/changmin/projects/ugrp/outputs/v6h-acceptance-NEW-SOURCE-SHA')
out.mkdir()                         # 이미 있으면 실패; 원본을 덮어쓰지 않음
(out/'cases').mkdir()
receipts = []
for ref in refs['cases']:
    original = Path(ref['reference_commands_path'])
    assert hashlib.sha256(original.read_bytes()).hexdigest() == ref['reference_commands_sha256']
    case = ref['case']              # expected_*는 제어 입력에 넣지 않음
    dest = out/'cases'/safe_name(case['case_id'])
    row = run_worker(case, dest, timeout_s=1500, omp_threads=1)
    actual = hashlib.sha256((dest/'commands.json').read_bytes()).hexdigest()
    checks = [{'leg': l['leg'], 'checks': leg_checks(l)} for l in row['chain']['legs'] if l['recorded']]
    receipt = {'case_id': case['case_id'], 'commands_sha256': actual,
               'command_match': actual == ref['reference_commands_sha256'],
               'leg_match': checks == ref['expected_leg_checks']}
    receipts.append(receipt)
    (out/'acceptance_receipt.json').write_text(json.dumps(receipts, indent=2)+'\n')
    assert receipt['command_match'] and receipt['leg_match'], receipt
```

종료 시 자신의 자식 정리를 확인하고 잠금을 release한다. 6건 모두 명령 전체 해시 및 leg checks가 일치해야 통과이며, 불일치하면 원인을 찾기 전 확증을 시작하지 않는다. 이 대안은 계획 §6의 비교 사례 변경이므로 조정자 확인이 남는다. 부하·실행 SHA·환경·실패도 기록하고, 새 결과는 기존 스냅샷과 구분해 native TensorBoard에 등록·실제 표시 확인한다.

## 남은 결정과 참고 자료

- 독립 Opus 검토 및 최종 봉인 커밋, 위 인수 기준의 axial-on 정합성 확정, 물리 6건 재생, 확증 60+12건은 조정자 소관이다.
- 초안 A=48/60 유지 또는 B=55/60 선택, 과보수 C를 보고만으로 유지할지는 봉인 전에 결정한다. 접근·팔 스윕 완화와 별도 정지 검출기 구현은 이번 범위가 아니다.
- [#285 탐색 및 등록 계획](https://github.com/kcm0127-dotcom/ugrp/pull/285), [#284 gain 적합](https://github.com/kcm0127-dotcom/ugrp/pull/284), [#286 axial-lag 진단](https://github.com/kcm0127-dotcom/ugrp/pull/286), [#290 분류 보완](https://github.com/kcm0127-dotcom/ugrp/pull/290).
- [실행 버전 관리](../../docs/execution_versioning.md), [고정 원문](PREREG_DRAFT.md), [등록 계획](REGISTRATION_PLAN.md), [미봉인 소스 변화 전체](source_changes_UNSEALED.json), [검증 기록](validation.json).
