# pairact P0: 공동 운반 선행 막힘 진단 (2026-10-20, Claude 워커)

범위는 MJWarp teacher 관문(공동 파지 + 3초 유지)을 막는 네 가지입니다: CUDA 700/SIGSEGV, world 27, world 37, world 15. 진단과 default-off 패치만 다루고, 관문 결과는 주장하지 않습니다. 실행은 DeepSeek이 gcp6에서 합니다([TONIGHT.md](TONIGHT.md)).

기반 브랜치는 `origin/claude/beamact5-r2-t`(`376c006f1`)입니다. 이 브랜치의 teacher 코드는 r13 스택 teacher `fe6858ec`와 같고, 그 뒤 커밋은 문서뿐입니다.
r13 스택은 root `05046e9d`, adapter `d354468a`, teacher `fe6858ec`입니다.

## 1. CUDA 700 / SIGSEGV

| 항목 | 기록 |
|---|---|
| 출처 | `origin/claude/warp4:experiments/2026-10-16-warp4/` (README, final-summary.json, mps-fatal-stop.json, environment.json) |
| 실패 | gcp2 L4에서 실패 12건, 실제 프로세스는 3개입니다. beampair 4 world는 tick 10(SIM 1.0 s)에서 exit 1, `Warp CUDA error 700 … wp_memcpy_d2h (warp.cu:1091)`로 끝났습니다. release s1(6 world)과 s3(2 world)은 SIGSEGV(-11)였습니다. 커널 로그(`origin/codex/warp6:…/gcp2-r3-kernel-evidence.txt`)에는 Xid 31 MMU fault(beampair pid)와 libcuda segfault(release pid)가 남아 있습니다 |
| 조건 | private MPS로 3 프로세스가 GPU를 공유했고, nvmax 128(`--full-active-dof-workspace-v1` 없음)이었습니다. nworld는 indices 수(4/6/2)와 같습니다 |
| 지금까지 확인된 것 | warp6: MPS 없이 같은 prefix 15틱을 돌리면 exit 0이고 253틱 연장에서도 재현되지 않았습니다. compute-sanitizer는 첫 step을 끝내지 못했습니다. warp8: step 226에서 NVMAX overflow(할당 128, 활성 156, nv 222)가 났습니다. warp4에서는 overflow 검사가 d2h readback보다 뒤에 있어 실행되지 못했습니다 |
| r13 (gcp6) | MPS 없음, nvmax 222, 1 프로세스, 39 world에서 CUDA 오류 0건 (`gate39-r13-run/summary.json` capacities) |

원인 가설 (미확정):
- H1. nvmax 128 overflow에 따른 정의되지 않은 동작
- H2. MPS의 fatal fault 전파. 한 client의 fault가 세 프로세스 모두를 teardown했습니다
- H3. 둘 다 아닌 다른 원인(Warp, MJWarp 버그) [확인 필요]

재현 매트릭스는 [repro_cuda.sh](repro_cuda.sh)입니다. 한 번에 한 축만 바꿉니다: nworld 1/4/16 × nvmax 222/128, `CUDA_LAUNCH_BLOCKING=1`, compute-sanitizer는 1 world에서만 돌립니다. MPS 축은 `--gcp6-isolated-v1`이 거부하므로 gcp6에서는 재현하지 않습니다. 버전 기대값은 warp-lang 1.15.0, mujoco/mujoco-warp 3.16.0(`57b4692f`), driver 580.178.04입니다.

## 2. world 27: 정렬(align) flake

| 기록 | 결과 |
|---|---|
| r13 5-world, stage1 | PASS 24.0 (align 2.6 s, relook 0) |
| gate attempt 1/2 | FAIL 26.0 / 26.3 `alignment_no_progress` |
| 단독 반복 3회 (r13) | FAIL, FAIL, PASS (1/3) |
| r13diag rep1 (`origin/claude/beamact5-flake`) | FAIL 25.5 |
| r14 align refresh 단독 3회 (`origin/claude/beamact5-flake2`) | PASS, PASS, FAIL (2/3). refresh 훅은 한 번도 발동하지 않았습니다 |

- **실패 단계:** 접근은 r8 wide rescue로 해결됐습니다. 선택 stance는 모든 실행에서 (-18°, 0.209 m)로 같았습니다. 실패는 fine align 단계에서 납니다.
- **확인된 사실:** 6개 저장 실행 모두 첫 tick의 qpos 차이가 0인데, 약 0.5 SIM s 안에 궤적이 갈라집니다. 시뮬레이션이 bit-reproducible하지 않으므로 같은 seed 반복도 같은 결과를 보장하지 않습니다.
- **실패 메커니즘 (r14 prereg, r13diag 근거):** align 중 x 오차가 0.0188 m에서 멈춥니다. SIM 17.6 s부터 `alignment_axes_blocked`가 91회 기록되고, 최종 segment/pulse 안전 검사가 모든 pulse를 hold로 바꿉니다. 3 s 뒤 relook이 일어나고, 3회째에 `alignment_no_progress`로 끝납니다.
- **원인 가설:**
  - H27-a: 기억 속 red_1 여유(stale margin)가 정렬 pulse를 막습니다. r14가 이 가설로 고쳤지만 훅이 발동하지 않았습니다(`remembered_blockers`가 비어 있었을 것으로 추정).
  - H27-b: 원형 정렬 pulse 가드가 너무 보수적입니다. 접힌 상태에서 반경 0.13 m 원을 쓰는데, 실제 차체는 185×160 mm로 반대각 0.122 m, 전후 반폭 0.0925 m입니다. beampair9 8328015(CPU)에서도 같은 `alignment_axes_blocked` 90회가 원형 가드의 최소 틈 -1.538 mm로 설명됐습니다. 코드 경로는 `sim/grasp_act_search20.py alignment_alternative` → `search19.admitted`(원형 `pulse_free`), 그리고 `sim/grasp_act_teacher_v3.py _search20_step`의 최종 가드(원형 `segment_free`/`pulse_free`)입니다. world 27은 비명목 stance라 이 최종 가드가 적용됩니다.
  - 두 가설은 서로 배타적이지 않습니다. 실패 tick에서 원형 틈과 직사각형 틈을 각각 계산한 값은 아직 없습니다 [확인 필요].
- 오늘 밤 같은 seed 3회 반복은 [repeat27.sh](repeat27.sh)로 돌립니다. 동결된 r13 명령을 그대로 씁니다.

## 3. world 37: 구조적 실패

- **실패 단계:** 모든 라운드에서 approach 단계의 `approach_blocked_handoff`(29.5–30.6 s)로 끝납니다. r1부터 r14까지 한 번도 통과하지 못했습니다.
- **원인 (r2 `validation-r2-6.json`):** 91개 인증 자세(±15° × 13 거리) 중 cyan_1과의 최적 틈이 4.87 mm로, 런타임 바닥 여유 11.07 mm(5 mm + K·2 mm, K=3.035)보다 작습니다. admission은 setup 기하에서 5 mm 기준으로 12자세를 승인했습니다. 승인 기준과 런타임 기준이 어긋나 있습니다. 가설로 볼 단계는 지났고, 기록상 확정된 메커니즘입니다. 다만 4.87 mm는 r1/r2 런타임 관측값이고 r3 이후에는 다시 재지 않았습니다.
- **산출물:**
  - [static_stance_check.py](static_stance_check.py): beampair9 방식의 setup 전용 검사입니다. CPU에서 돌고 물리는 0입니다. 기준을 셋으로 나눠 보고합니다: 겹침(>0), admission(≥5 mm), floor(≥11.07 mm). 로컬에서는 합성 case와 단위 테스트로만 확인했고, 실제 wide-cases-r13.json으로는 아직 실행하지 않았습니다.
  - [WORLD37_STATIC_PREREG_DRAFT.json](WORLD37_STATIC_PREREG_DRAFT.json): 상태는 DRAFT입니다. 구속 규칙(A 겹침 / B floor)은 오너가 실행 전에 확정합니다. 실제 setup 기하로 37이 걸리는지는 [확인 필요]입니다. A는 현행 admission보다 약한 기준이라 37을 제외하지 못할 가능성이 큽니다.
- **주의:** 규칙이 확정되기 전에 이 검사를 실행하면 결과를 보고 규칙을 고르는 셈이 됩니다. 그래서 TONIGHT.md에 넣지 않았습니다.

## 4. world 15: 로그 폭주

- **실패 단계:** approach planning 중에 나타납니다. 0.1 s tick마다 91자세 `blocked_goal` 감사가 다시 계산되고 기록됩니다.
  - r2: `search22_log` 47행이 281.5 MB, `goal_set_log` 46행이 274.9 MB였습니다. SIM 6.4 s에서 30 wall-s planning cap에 걸렸습니다.
  - r3: raw 3.2 GB, snapshot 3.0 GB가 쌓이고 batch가 멈췄습니다.
  - r3부터 게이트에서 제외했습니다(deviation).
- **원인:** 1차는 로그 부피와 반복 직렬화입니다. cProfile에서 `write_json`이 75.6%였는데, 대부분 사후 저장이 차지한 값입니다. 2차는 tick당 계산 비용입니다(`body_fallback`, `select_sampled_goal`, `plan_active`).
- **패치 (이 브랜치, default off):** `search26_log_ring_v1` (`sim/grasp_act_log_ring.py`). `goal_set_log`와 `search22_log`에 최신 16행만 남기고, 버린 행 수는 이벤트별로 셉니다. 제어에서 읽는 값은 최신 행(teacher `goal_set_log[-1]`, adapter `goal_set_log[-1:]`)뿐이라 동작은 바뀌지 않습니다.
  - 모드를 켜면 `diagnostic()['candidate_*_counts']`가 남은 행만으로 계산됩니다. `log_ring` 요약에 이 범위를 기록합니다.
  - 모드를 끄면 로그는 예전과 같은 plain list입니다(테스트로 확인).
  - **이 패치로 해결되지 않는 것:** tick당 91자세 재계산 비용은 그대로라, r2의 planning wall cap이 다시 걸릴 수 있습니다. 이 패치만으로 world 15를 관문에 다시 넣을 수 있는지는 [확인 필요]입니다(단독 smoke 필요).
  - adapter 프로필에 이 모드를 넣으려면 adapter와 root의 pin 커밋이 따로 필요합니다(미작성).

## 5. 테스트
- `tests/test_pairact_p0.py` 7개: 모드 등록, default off, runner 배선, ring 동작, teacher 설치, diagnostic, static census의 겹침 판정과 임계값.
- 기존 `tests/test_beamact5_r3_modes.py` 18개 통과.
- venv `/home/ubuntu/ugrp-e1-venv`에는 mujoco가 없습니다. 물리와 렌더는 돌리지 않았습니다.
