**HAN-32 계측 재개 실행 결과 (2026-10-28) — SIM 결과**

원인 확정 → 최소 수리 → N=4 계측 배치 완료 → 계측 레코드 확보 → VM 정지까지 끝냈습니다. 상세는 `outputs/reports/2026-10-28-instr-fix-result.md` §11 (원문: `/home/ubuntu/UGRP/outputs/reports/2026-10-28-instr-fix-result.md`).

**1. 원인 확정 (H1b, 추론 → 근거)**
- 계측 래퍼 `ops/eval-python`이 draccus가 없는 treatment 드라이버 venv(`/home/ugrp/pairact-p3c2-20261021/venv`)를 exec했습니다. 계측 드라이버 `future_driver.py`가 런처를 자기 프로세스 안에서 exec하기 때문에 래퍼의 인터프리터가 곧 actor 로드 인터프리터가 되고, `harness/pairact_r1.py:597`의 `import draccus`에서 즉시 `ModuleNotFoundError`가 났습니다.
- VM 실측: `e2emin-20261021/venv`(draccus 0.11.6·lerobot 0.6.2·torch 2.11.0+cu128)·`ugrp-rl1b-act-env`는 import 성공, `pairact-p3c2-20261021/venv`·`.venv-warp`·`.venv-sim`은 실패. → **설치 문제가 아니라 인터프리터 정렬 문제**(2026-10-25 선례와 동일 실패류). H2·H3는 배제.

**2. 최소 수리**
- 신규 실행 디렉터리 `han32-instrumentation-20261028-r2`에서 **`ops/eval-python` 1개 파일만** 변경(`sha256 2a77a7837f19…`)해 e2emin venv를 가리킵니다. `launch.py`·`worker_trace.py`·`runner_trace.py`·`pair_gpu_cpu_guard.py`·`test_equivalence.py`는 sha256 동일.
- launch-plan diff는 **경로 2줄만** 다르고 indices(0,5,9,18)·cap·source_sha `e5620e83…`·cases_sha256 `3e4bf69c…`·물리 플래그 동일. 실패 배치 원본은 무수정 보존. **설치 0건.**

**3. 사전 관문**
- `check_current_stack.py` → `ok=true / current_compliant=true / admission=pass`(비현재 0건), 결과 `experiments/2026-10-28-instr-fix/stack-check.json`.
- 동결 자산 verify-before/after `all_match=true`(33파일, trees R/A/T/S 일치). CPU 물리는 INIT_OR_RESET 29,392스텝뿐, 롤아웃 CPU 스텝 0.

**4. 배치 결과 (N=4, 시드 8342000/8342005/8342009/8342018)**
- status `complete`, **HOST_ERROR 0**, completed_N 4, **운반 성공 0/4**, `cap_end=4` — 4개 월드 모두 180 SIM s 에피소드 상한(`cap_s 60` + `carry_cap_s 120`) 도달. 결함 실패가 아니라 **시간 상한 종료**로 표기.
- 무결성 오류 0: `held_world_reads=0`·`invisible_measurements=0`·`measurement_rows=0`(4/4), `training_rgb=false`, `gate_eligible=false`.
- 계측 레코드 **12파일 / 14,400건** (worker 4×3,600 + protocol 4 + eval-geometry 4).

**5. 계측 결과**
- stage head가 `approach`에 고정되지 **않음**: 호리존 행 argmax `approach 63,474 / execute 35,989 / ready 8,334 / alignment 7,403`(총 115,200행). 배리어가 쓴 단계(`barrier_after.pair_stage`)도 월드별로 approach/alignment/ready/execute를 지나나 **case 5·9는 ready·execute에 진입하지 못함**.
- done head는 임계 0.65를 월드별 642–2,091레코드에서 넘었고 `done_since`이 469–1,243레코드에서 설정됨. 단 **세그먼트 전환은 `release_instruction`(source `both_own_done_flags`)뿐** — case 0에서 2건(t=72.2 s)·case 18에서 2건(t=101.0 s), case 5·9는 0건(3,600레코드 전부 `grasp` 구간).
- 위치 추정 출력 **14,400/14,400레코드에서 부재**가 명시(`pose_prediction_status=unavailable:frozen_actor_has_no_pose_estimator_output`, `rgb_only_pose_prediction=null`).
- 거부 원장: **거부 4,893건 전부 사유 보유** — `close_before_learned_ready_suppressed` 4,885건 + `execution_without_GO_ACK` 8건, `blocked_object=UNKNOWN:not_observed`, `min_gap_m=null`, `gap_scope=not measured / not available`. 나머지 347건(`READY` 185·`stage_proposal_released_after_GO_ACK` 162)은 거부가 아닌 상태 통지 이벤트라 별도 집계.
- 속도 게이트(기록 전용): 첫 30 SIM초 선언 지표 `wall_s/(sim_s*nworld)` 배치 4.262 / 월드별 중앙값 4.55 → 3.5 경고선 초과, **6.0 중단선 미달이라 중단하지 않음**.

**6. 비용·종료 상태**
- 이 작업 GPU **0.998584 GPU-h**(할당 19:13:42.227Z → 정지 20:13:37.130Z; 배치 기동 기준 0.889481) — 배치 상한 1.2·작업 상한 2.4 **모두 이내**. 프로젝트 원장(21.822120556/25.3)에는 **더하지 않고 별도 관리**(`experiments/2026-10-28-instr-fix/gpu-ledger.json`).
- 도쿄 gcp6(`asia-northeast1-c`, id 2102818194467198298)만 사용 → **정지 후 `TERMINATED` 확인**. 서울 동일명 인스턴스(`asia-northeast3-a`, id 6033281434351587170)는 기동하지 않았고 `TERMINATED` 유지. 인스턴스 생성·삭제 0, pip 설치 0, CPU 물리 시뮬 0.
- 원본 회수: `outputs/reports/2026-10-28-instr-fix-evidence/`(94파일·269 MB, VM sha256 목록 대비 missing 0·mismatch 0·extra 0). VM 영속 디스크 원본은 삭제·수정 없이 보존.

**7. 미해결**
① `configs/gcp_hosts.json:83`의 gcp6 존이 서울로 낡아 있음 — 범위 밖이라 미수정(실행은 exact-ID·exact-zone 우회)
② 운반 0/4의 **원인은 규명하지 않음**(계측은 case 5·9의 ready/execute 미진입과, ready 진입 후에도 닫힘이 억제된다는 사실만 기록) — 수리안(헤드 분리·위치 추정 헤드·DAgger·재학습)은 미승인이라 **시작하지 않음**
③ 조건부 2차 N=4 **미실행**(계획 문서 조건 + 미승인), 잔여 예산 보존
④ 계측 공백(argmax 사전 계산값·stage-head config/temperature/mask)은 계측 코드 수정이 필요해 기록만
⑤ 월드별 `result.json`·`eval-only.jsonl`·`student-eval.jsonl`은 VM 압축·심볼릭 링크로 미회수 — 해시는 회수된 manifest에 보존, 비용 절약 위해 VM 재기동하지 않음
⑥ 재발 방지 가드는 `python3 ~/.hermes/scripts/recurrence_guard.py --tier all`을 부모 호스트 터미널에서 직접 실행 — **이번 실패류에 대한 신규 검사(`check_student_eval_interpreter_has_draccus`)는 PASS**, 전체 FAIL은 폐기된 Hermes 런타임 부재 때문이며 `systemctl --user` 연결 불가로 상태 파일은 갱신하지 않음(`[HOST_RUNTIME_REQUIRED]`)

**모든 결과는 SIM이며 실물 성능·성공 주장이 아닙니다.**
