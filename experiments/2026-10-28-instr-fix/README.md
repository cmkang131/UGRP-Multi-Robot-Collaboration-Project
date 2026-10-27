# HAN-32 계측 재개 (instr-fix) — draccus 인터프리터 정렬 → N=4 계측 → VM 정지

2026-10-28 지시(02:15 KST) 계측 재개 작업의 기록이다. 목적이 **계측(measurement)** 이고 **수리 제안(헤드 분리·위치 추정 헤드·DAgger·재학습)은 미승인이라 시작하지 않았다**. 최종 판정·수치·해시는 [summary.json](summary.json), GPU 사용량은 [gpu-ledger.json](gpu-ledger.json), 계측 집계는 [measurement-aggregate.json](measurement-aggregate.json)에 있다. 상세 보고서는 `outputs/reports/2026-10-28-instr-fix-result.md` §11.

**모든 결과는 SIM이다.** 실물 성능·성공 주장이 아니다.

## 최종 상태

**원인 확정(H1b) → 최소 수리 → N=4 계측 배치 완료 → 계측 레코드 12파일/14,400건 확보 → VM 정지(TERMINATED) 확인.** 계측 목적을 충족했다. 운반 성공은 0/4였고(4개 월드 모두 180 SIM s 에피소드 상한 도달 — 결함 실패가 아니라 시간 상한 종료) **0/4의 원인은 규명하지 않았다.**

| 항목 | 값 |
|---|---|
| 호스트 | `ugrp-act-l4-gcp6` / `asia-northeast1-c` / id `2102818194467198298` / `g2-standard-8` / 프로젝트 `ugrp-sim-f-1016` / 계정 `kcm5781kcm5781@gmail.com` |
| 기동 → 정지 | 2026-10-27T19:13:42.227Z → 20:13:37.130Z |
| 이 작업 GPU | **0.998584 GPU-h** (배치 기동 19:20:15Z 기준 0.889481) — 배치 상한 1.2·작업 상한 2.4 이내 |
| 프로젝트 원장 | 21.822120556 / 25.3 — **이 작업량을 더하지 않고 별도 관리**(지시) |
| 종료 상태 | `TERMINATED` 확인. 서울 동일명 인스턴스(`asia-northeast3-a`, id 6033281434351587170)는 기동하지 않음 |
| 기타 비용 | 인스턴스 생성·삭제 0 · pip 설치 0 · CPU 물리 시뮬 0(초기화/리셋만) |

## 원인과 수리

- **근거**: 실패 배치의 student-eval `python`이 `runs/han32-instrumentation-20261028/ops/eval-python` → `exec /home/ugrp/pairact-p3c2-20261021/venv/bin/python`. 계측 드라이버 `future_driver.py`가 계측된 런처를 **자기 프로세스 안에서 exec**하므로 래퍼의 인터프리터가 곧 actor 로드 인터프리터가 되고 `harness/pairact_r1.py:597`의 `import draccus`에서 `ModuleNotFoundError`가 즉시 발생했다.
- **VM 실측 프로브**: `e2emin-20261021/venv`(draccus 0.11.6 · lerobot 0.6.2 · torch 2.11.0+cu128)·`ugrp-rl1b-act-env`는 import 성공, `pairact-p3c2-20261021/venv`·`.venv-warp`·`.venv-sim`은 실패. → **설치 문제가 아니라 인터프리터 정렬 문제**(2026-10-25 선례와 동일 실패류). H2·H3 배제.
- **수리**: 신규 실행 디렉터리 `han32-instrumentation-20261028-r2`에서 **`ops/eval-python` 1개 파일만** 변경(sha256 `2a77a7837f196e17a3311c189ac7406695f11b1bfac4280e6f42933fe4bf638a`)해 e2emin venv를 가리킨다. `launch.py`·`worker_trace.py`·`runner_trace.py`·`pair_gpu_cpu_guard.py`·`test_equivalence.py`는 sha256 동일. launch-plan diff는 **경로 2줄뿐**(indices 0,5,9,18 · `--cap-s 60` · `source_sha e5620e839907dc69d3b014becae2cbda4bbe27da` · `cases_sha256 3e4bf69caa48f4638eb365aec649e8202948de56390dff37cbd540e542e504dc` · 물리 플래그 전체 동일). 실패 배치는 무수정 보존. **설치 0.**
- **사전 관문**: `scripts/check_current_stack.py` → `ok=true / current_compliant=true / admission=pass`([stack-check.json](stack-check.json)). 동결 자산 verify-before/after `all_match=true`(33파일, trees R/A/T/S 일치). CPU 물리는 INIT_OR_RESET 29,392스텝뿐(롤아웃 CPU 스텝 0, `rollout_cpu_denial_events=[]`).

## 계측 결과 (근거)

- stage head는 `approach`에 고정되지 **않는다**: 호리존 행 argmax `approach 63,474 / execute 35,989 / ready 8,334 / alignment 7,403`(총 115,200행 = 14,400레코드 × 8행). 배리어가 쓴 단계(`barrier_after.pair_stage`)는 월드별로 approach/alignment/ready/execute를 지나나 **case 5·9는 ready·execute에 진입하지 못했다**(approach 2,486 / 2,895).
- done head는 임계 0.65(`done_activation = "sigmoid; balanced_bce_v1; not calibrated"`)를 월드별 642–2,091레코드에서 넘었고 `done_since`이 469–1,243레코드에서 설정됐다. 단 **세그먼트 전환은 `release_instruction`(source `both_own_done_flags`)뿐** — case 0에서 2건(로봇별 1건, t=72.2 s)·case 18에서 2건(로봇별 1건, t=101.0 s), case 5·9는 0건.
- 위치 추정 출력은 **14,400/14,400 레코드에서 부재**가 명시(`pose_prediction_status=unavailable:frozen_actor_has_no_pose_estimator_output`, `rgb_only_pose_prediction=null`). 관측 안 됨을 빈 값으로 두지 않았다.
- **거부 원장(빈 사유 금지)**: 전체 5,240건 중 거부 4,893건은 전부 `reason_category` 보유 — `close_before_learned_ready_suppressed` 4,885건 + `execution_without_GO_ACK` 8건. `blocked_object=UNKNOWN:not_observed`, `min_gap_m=null`, `gap_scope="not measured: own-command software gate"` / `"not available in own-command protocol adapter"`. 나머지 347건(`READY` 185 · `stage_proposal_released_after_GO_ACK` 162)은 거부가 아닌 상태 통지 이벤트라 별도 집계.
- 무결성: `held_world_reads=0` · `invisible_measurements=0` · `measurement_rows=0`(4/4 월드), `training_rgb=false`, `gate_eligible=false`.
- 속도 게이트(기록 전용): 첫 30 SIM초 선언 지표 `wall_s/(sim_s*nworld)` 배치 4.262 / 월드별 중앙값 4.55 → 3.5 경고선 초과, **6.0 중단선 미달이라 중단하지 않음**.
- **레코드 단위 주의**: trace 워커 파일 1개는 r1 1,800 + r2 1,800 = 3,600레코드로 두 로봇이 병합된 것이다. 위 틱/레코드 수치는 이 병합 기준(로봇별 1,800틱).

## 산출물과 원본

| 항목 | 경로 |
|---|---|
| 회수 증거(94파일·269 MB, VM sha256 대비 missing 0·mismatch 0·extra 0) | `outputs/reports/2026-10-28-instr-fix-evidence/` (`raw/`·`local-sha256.txt`·`vm-sha256.txt`·`full-journal.txt`) |
| 계측 레코드 12파일 (worker 4·protocol 4·eval-geometry 4) | 위 경로 `raw/trace/*.jsonl` — 파일별 sha256은 [summary.json](summary.json) `measurement.record_file_manifest` |
| 월드 원장·검증 JSON | 위 경로 `raw/s4/summary.json`·`verify-before.json`·`verify-after.json`·`cpu-init.json`·`raw/world-00*/raw/manifest.json` |
| VM 영속 디스크 원본 | `/home/ugrp/ugrp-sim/runs/han32-instrumentation-20261028-r2` — 삭제·수정 없이 보존 |

**미회수(정직하게 기록)**: 월드별 `raw/result.json`·`raw/eval-only.jsonl`·`raw/student-eval.jsonl`은 VM에서 zstd 압축·심볼릭 링크로 저장되어 fetch-lite 목록에서 제외됐다. 해당 해시는 회수된 `raw/manifest.json`에 남아 있고 VM 디스크에 보존되어 있다. VM 재기동 없이 회수할 수 없어 **비용을 늘리지 않기 위해 재기동하지 않았다**. 무결성 판정값은 회수된 `s4/summary.json`의 `worlds[].input_audit`로 로컬 재확인했다.

## 재현

```bash
# 사전 관문
python3 scripts/check_current_stack.py experiments/2026-10-28-instr-fix/han32-instrumentation-queue.json \
  --flow beam_pair --output experiments/2026-10-28-instr-fix/stack-check.json
# 계측 집계(로컬 재계산)
python3 aggregate.py outputs/reports/2026-10-28-instr-fix-evidence/raw/trace experiments/2026-10-28-instr-fix/measurement-aggregate.json
# GPU 원장(인스턴스 할당 구간 기준)
python3 build_ledger.py
# 총괄 요약
python3 build_summary.py
# 재발 방지 가드(부모 호스트 터미널에서 직접 실행)
python3 ~/.hermes/scripts/recurrence_guard.py --tier all
```

`aggregate.py`·`build_ledger.py`·`build_summary.py`는 작업 디렉터리 `/home/ubuntu/ugrp-han32-instrumentation-20261028-r2/`에 있다(gitignore 대상 로컬 산출 스크립트).

## 등록·가드

- **Linear HAN-32** 등록 완료: comment id `fbbb39a2-037c-402c-a318-0f395f483ac9`, createdAt 2026-10-27T20:21:33.788Z, 본문 4,352자. GraphQL로 재조회 검증. 본문 사본 [linear_han32_body.md](linear_han32_body.md), 등록 기록 [linear-han32.json](linear-han32.json).
- **재발 방지 가드**: `python3 ~/.hermes/scripts/recurrence_guard.py --tier all`을 **부모 호스트 터미널에서 직접** 실행(위임 아님). 최종 실행 `checked_at=2026-10-27T20:22:38Z`, 종료코드 1. **이번 실패류에 대응하는 신규 검사 `check_student_eval_interpreter_has_draccus`는 PASS**(활성 참조 16건 중 draccus-less 인터프리터 0건). 전체 FAIL의 원인은 이 호스트에서 폐기된 Hermes 런타임(hermes 실행 파일·config.yaml 부재)이다. `systemctl --user`가 "Failed to connect to bus"로 host user-manager에 연결되지 않아 `[HOST_RUNTIME_REQUIRED]`에 따라 정식 `status.json`·`events.jsonl`을 **갱신하지 않았다**(실행 산출물은 격리된 scratch HOME에만 있다). 산출물 [recurrence_guard_stdout.txt](recurrence_guard_stdout.txt)·[recurrence_guard.json](recurrence_guard.json)·[guard-result.json](guard-result.json).

## 미해결

1. `configs/gcp_hosts.json:83`의 gcp6 존이 서울(`asia-northeast3-a`)로 낡아 있다 — **설정 변경은 범위 밖이라 미수정**. 이번 실행은 exact-ID·exact-zone으로 우회했고 서울 인스턴스는 기동하지 않았다.
2. **운반 성공 0/4의 원인은 규명하지 않았다.** 계측이 남긴 것은 ① case 5·9의 ready·execute 미진입(같은 사유 2,942건) ② case 0·18의 ready·execute 진입 후에도 닫힘 억제(같은 사유 1,943건)라는 기록뿐이다.
3. **수리안 미착수**: 헤드 분리·위치 추정 헤드·DAgger·재학습은 사용자 미승인. **조건부 2차 N=4도 미실행**(계획 문서 조건 + 미승인) — 잔여 예산 보존.
4. 계측 공백: argmax 사전 계산값·stage-head config/temperature/mask가 레코드에 없음(사후 계산만 가능). 계측 코드 수정이 수리 범위를 넘어 기록만.
5. 월드별 압축 result/eval ledgers 미회수(위 표 참고).
6. 계측 레코드의 `cohort` 필드는 `worker_trace.py:73`의 하드코딩 상수 `"han32-instrumentation-s4-20261028"`으로, 실제로는 `-r2` 배치를 가리킨다. 출처 판별은 실행 디렉터리·`host-identity.json`·`launch-plan.json`·`student-eval-instrumented.json`으로 한다.
