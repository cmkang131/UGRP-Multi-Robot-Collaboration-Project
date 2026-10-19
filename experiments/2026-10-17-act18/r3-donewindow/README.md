# R3 done-window 재학습 준비 (act18-r3dw)

상태: **준비 완료(PREP), 학습 미실행**. 브랜치 `dsh/act18-r3-donewindow`, base `95e668c59`.
Claude 결정(창민 위임) 2026-10-19: R3은 브랜치·데이터·config diff·오프라인 gate 준비까지만 하고, **학습 실행은 창민 보고·승인 뒤**에 한다. GPU·VM·학습은 이 작업에서 실행하지 않았다(CPU만).

- 사전등록: `experiments/2026-10-17-act18/R3_DONEWINDOW_PREREG.json` (학습 전 커밋)
- 스펙: `outputs/reports/claude-arch-parallel-20261019/act-C2-R3-spec.md` §4–§5, 지시: `claude-directives-20261019T18.md` §2
- 설계: `act-student-failure-design.md` §6 R3(D6로 열림)

## 1. 구현한 default-off 플래그

| 플래그 | 기본 | 의미 |
|---|---|---|
| `--done-window-ticks K` | None → 0 | grasp 완료 행과 같은 에피소드·skill에서 0.1 s 간격으로 연속된 직전 K−1행을 done=1로 확장. K=10이면 grasp 양성 200 → 2,000행 |
| `--done-positive-batch-fraction .5` | None | 기존 B1 플래그. 배치의 50%에서 양성 1행을 강제 |
| `--done-clock-jitter-s s` | None | R3-B. `verify_lift`·`hold` 행에만 입력 시계 2차원에 U(−s,+s) s를 정규화 전에 더하고 0에서 자름. 표적 불변, 행별 고정 offset, RNG seed 20261017 |

변경 파일:

- `scripts/act18_policy.py`: `CANDIDATES['act18-r3dw']=8`, `PILOT_CANDIDATES`/`PILOT_KINDS`에 `act18-r3dw`/`done_window_finetune_v1`, `expand_done_window()`, `extend_targets(done_window_ticks=...)`, `ReferenceDataset(done_window_ticks=0, done_clock_jitter_s=None)`, `__getitem__` jitter 경로(off면 부모 바이트 그대로), `registered_pilot_checkpoint`에 R3 kind 등록·packaging_eligible=false 강제.
- `scripts/act18_train.py`: argparse 2개, `validate_probe_options` 검사, 데이터 생성에 전달, probe provenance에 window receipt·prior·jitter 행 수·seed 기록.
- `scripts/act18_evaluate.py`: `done_window_finetune_v1`을 등록된 short probe로 허용하되 `packaging_eligible=false`·`candidate=act18-r3dw`가 아니면 거부.
- `scripts/act18_r3_data_delta.py`: R3 데이터 dry-run(양성·prior·잘린 행·jitter 행).
- `scripts/act18_r3_offline_gate.py`: 오프라인 gate g1–g5 실행/판정.
- `tests/test_act18_r3_donewindow.py`: 스펙 §4의 CPU 테스트 5종 + 등록 검사.

### 창 의미(중요)

- 창은 **grasp 완료 행에만** 적용한다. TRAIN200은 grasp 완료 200행(pe 11.2–11.3 s)과 release 완료 200행(다른 skill)을 갖는다. release 양성은 그대로 200행이다. 그래서 총 양성은 400 → 2,200이고, 스펙의 “양성 200 → 2,000”은 **grasp 양성** 기준이다.
- 창 행은 chunk 표적이 h=0에서 잘린다(양성 행 2,000 + 앞선 행 1,000 = 3,000행의 유효 horizon이 줄고, 패딩 슬롯 12,600개가 늘어난다). 이는 사전 등록·기록된 결과이며 숨기지 않는다.
- prior는 손실이 실제로 쓰는 **skill별** 값으로 다시 계산했다: grasp `0.0036508 → 0.0365082`, release `0.0114088`(불변). 스펙의 “약 0.0277(1/36)”은 grasp 양성 2,000/전체 72,572행의 pooled 근사(0.02756)이며 손실 prior가 아니다. 두 값을 모두 `data-delta.json`에 남겼다.

## 2. CPU 테스트

```
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest tests/test_act18_r3_donewindow.py -q
# 6 passed
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest tests/test_act18_*.py -q
# 72 passed
```

5종 매핑:

1. `test_zero_flags_are_byte_identical_and_explicit_zero_matches_default` — 0/None이면 데이터·prior·표적·state 바이트 동일, `extend_targets` 기본값 동일.
2. `test_k10_makes_exactly_200x10_grasp_rows_positive` — K=10에서 grasp 양성 정확히 2,000행(200×10), 추가 1,800, release 200 불변.
3. `test_window_stops_at_episode_skill_and_time_gaps` — 에피소드·skill·0.1 s 간격 경계를 넘지 않음.
4. `test_input_whitelist_and_shapes_are_unchanged` — `TRAIN_KEYS`·state 252·action 8×14 불변, 창은 완료 열만 바꿈.
5. `test_r3b_jitter_targets_only_verify_lift_and_hold_clocks` — `verify_lift`/`hold` 외 행 offset 정확히 0, eligible 행은 U(−1,+1) s, 호출마다 고정, 결정적.

추가 `test_r3dw_options_and_probe_registration` — `act18-r3dw`는 `--init-checkpoint`·`--steps`·`--done-window-ticks` 필수, jitter는 window 없이 불가, 다른 후보와 혼용 불가, 평가 등록은 되지만 packaging_eligible=true면 거부.

## 3. 데이터 dry-run (실제 dataset-r1)

원본: `/home/ubuntu/UGRP/outputs/runs/act18-clockaudit-20261019T151956Z/retrieved/act17-v7/dataset-r1` (E0가 회수한 read-only 사본, manifest sha `44c1c460…`, normalization sha `d08f8672…`).
실행:

```
/home/ubuntu/ugrp-e1-venv/bin/python scripts/act18_r3_data_delta.py \
  --dataset <위 dataset-r1> \
  --out <run root>/dryrun/data-delta.json \
  --scratch <run root>/dryrun/derived-dataset
```

결과(`data-delta.json`):

| 항목 | 값 |
|---|---:|
| TRAIN 행 | 72,572 (200 에피소드) |
| grasp 행 / release 행 | 55,042 / 17,530 |
| grasp 양성 | 200 → **2,000** |
| release 양성 | 200 → 200 |
| 총 양성 | 400 → 2,200 |
| grasp prior | 0.0036508 → **0.0365082** |
| release prior | 0.0114088 (불변) |
| chunk가 더 잘린 행 | 3,000 |
| 추가 패딩 슬롯 | 12,600 |
| h=0 done이 바뀐 행 | 1,800 |
| R3-B jitter 행 | 8,200 (verify_lift 2,200 / hold 6,000) |
| jitter offset 범위/평균 | −0.99960 … +0.99962 s / −0.00462 s |

회수본에는 JPEG `frames.json`이 없어(라벨·prior·표적은 이미지와 무관) 도구가 **파생 root**를 만들어 `frames.json` 빈 placeholder로 dataset 초기화만 통과시켰다. tensors/samples는 등록 manifest 해시로 전부 검증했다. 따라서 이 dry-run은 라벨·prior·표적의 완전한 값이지만 **이미지 로딩 검증은 아니다**. VM 전체 데이터에서 학습 전에 같은 명령을 다시 실행해 `derived_root=false`를 확인해야 한다.

## 4. 사전등록

`R3_DONEWINDOW_PREREG.json` — 학습 전에 커밋했다. 고정한 것:

- seed 20261017, 10,000 step, **bf16 autocast**(가중치·옵티마이저 fp32), batch 8, lr 1e-5, chunk 8, episode-uniform sampling, done-positive fraction .5
- init R8 step-100000 `e1ec6592…`(adapter `2b84ac11…`), 읽기 전용, 전후 sha 기록
- 새 체크포인트만 `<run root>/train/step-10000/`에 생성. `packaging_eligible=false`, Release/registry 금지
- TRAIN4 88600–88603은 적합도 진단, HO4 88668–88671은 시연 밖, **VAL8·FINAL40 잠금**
- R8/R100/tune/doneb1/std/b3/doneh/loop/C2/C2c와 **pooling 금지**
- R3-A 기본. C2a FAIL일 때만 R3-B. C2a 결과 미도착이면 R3-A로 두고 launch.json에 조건 기록
- 오프라인 gate g1–g5 전부 PASS가 GPU 평가 조건

## 5. 오프라인 gate g1–g5 준비

`scripts/act18_r3_offline_gate.py` (default OFF, CPU만, 시뮬레이터 없음):

| gate | 정의 | 명령 | 상태 |
|---|---|---|---|
| g1 | 파일럿 teacher V0: hold 끝 ±10틱 TE done ≥ .65가 ≥3/4 | `... --enabled pilot --checkpoint <R3> --prereg ... --out <run>/offline/pilot` | 스크립트·R8 검증 실행 |
| g2 | verify_lift 시작 이전 TE done ≥ .65가 0/4 | 위와 같음 | 스크립트·R8 검증 실행 |
| g3 | lookback onset \|Δ\| ≤ 5틱 ≥3/4 | 위와 같음 | 스크립트·R8 검증 실행 |
| g4 | C2b S2(v7): lift 6개 중 발화 ≥4, 비-lift 대조 2개 중 ≤1 | `... --enabled c2b --c2b-summary <C2b adapter json>` | 스크립트·합성 입력 검증(5/6, 1/2 → PASS). 실제 C2b 산출물 대기 |
| g5 | E0 open-loop TRAIN4 teacher 종료 행 4/4 ≥ .65 | `... --enabled e0 --dataset <dataset-r1> --checkpoint <R3> --out <run>/offline/e0` 또는 `--frames <R3 open-loop frames>` | 스크립트·R8 frames 4/4 검증 |
| report | g1∧g2∧g3∧g4∧g5 | `... --enabled report --gate-dir <run>/offline --out <run>/offline` | 스크립트 준비 |

- **PASS = g1∧g2∧g3∧g4∧g5. 하나라도 실패하면 GPU 평가 금지, R3을 FAIL로 닫고 다음 후보는 R3b(별도 command-history head).**
- R8 검증(도구가 실제로 도는지 확인): E0 frames 평가는 **4/4 PASS**(R8은 done head가 정상인 기준선). pilot replay는 R8에서 g1 FAIL·g2 PASS·g3 PASS가 기대값이며 별도 run root에 기록했다(아래 “검증 실행”).
- g4 입력 형식(`ugrp.act18.r3_c2b_gate_input.v1`)은 C2b 담당이 자기 원본에서 변환해 내야 한다. Oracle에서 재추론하지 않는다.

검증 실행 경로:

- `/home/ubuntu/UGRP/outputs/runs/act18-r3-donewindow-prep-20261019T200500Z/offline/r8-validation/e0/` (g5 4/4)
- `/home/ubuntu/UGRP/outputs/runs/act18-r3-donewindow-prep-20261019T200500Z/offline/r8-validation/pilot/` (R8 pilot replay, g1 FAIL·g2/g3 PASS)
- C2b 합성 입력 검증은 `/tmp/r3-gate-c2b/`(임시, 커밋하지 않음).

## 6. 학습 실행 (승인 대기 — 이번에 실행하지 않음)

승인 뒤 VM에서:

```
# queue.json: candidates=['act18-r3dw'], training_precision='bf16_autocast_v1',
#   dataset_manifest_sha256=44c1c460..., protocol_sha256=1db4e223..., source_sha=<clean head>
python3 scripts/check_current_stack.py <run root>/queue.json --flow train --output <run root>/current-stack-check.json
python3 scripts/act18_train.py --enabled --candidate act18-r3dw --precision bf16_autocast_v1 \
  --init-checkpoint /home/ugrp/ugrp-sim/runs/act18/training-r1/R8/step-100000 \
  --steps 10000 --done-window-ticks 10 --done-positive-batch-fraction 0.5 \
  --dataset /home/ugrp/ugrp-sim/runs/act17-v7/dataset-r1 \
  --protocol experiments/2026-10-17-act18/protocol.json \
  --queue <run root>/queue.json --out <run root>/train
# R3-B이면 --done-clock-jitter-s 1.0 추가
```

- 예상 22–24분 + 적재·저장 ≈ 0.75 VM-h. 실행 창·예산·임대 규칙은 C2c와 같다.
- 새 체크포인트: `/home/ugrp/ugrp-sim/runs/act18-r3-donewindow-<UTC TS>/train/step-10000/`.
- 학습 직후 같은 run root의 `diff/`에 `launch.json`, `prereg.json`, `code.diff`, `config.resolved.json`, `data-delta.json`을 복사한다.

## 7. 리스크·미해결

- **C2a 결과 미도착**: R3-A를 기본으로 등록했고 R3-B도 준비했다. C2a FAIL이 확인되면 R3-B로 바꾸는 것은 사전 규칙이며, launch.json에 C2a 산출물 경로·sha를 남겨야 한다.
- **HO4 평가 하네스 없음**: base `act18_evaluate.py`에는 HO4 `diag` stage가 없다. 폐루프 HO4는 E2/C2의 `--stage diag --diag-prereg` 코드가 병합된 뒤에만 가능하다. 그전에는 TRAIN4만 제출 가능이며 HO4는 미제출로 보고한다.
- **이미지 없는 dry-run**: 위 3절. VM 전체 데이터에서 `derived_root=false` 재실행 전에는 학습을 시작하지 않는다.
- **release done 불변**: R3은 grasp done만 겨냥한다. release 단계 병목(B4 전례)은 별개다.
- **K=10의 한계**: student post-lift pe가 10 s에 못 미치면 창을 넓혀도 발화하지 않는다. R3v6은 사전 기대 FAIL이다.
- **prior 불일치 표기**: 스펙의 1/36은 pooled 근사이며 실제 손실 prior는 skill별 0.0365다. 이 차이를 숨기지 않고 기록했다.
- **jitter 구현 해석**: 스펙은 “정규화 전에 더하고 0 이상으로 자름”만 정했다. 이 구현은 행별 offset을 seed 20261017로 고정 생성해 접근 순서와 무관하게 결정적이다(에포크별 재샘플 아님). 이 해석은 기록·테스트로 고정했다.

## 8. 산출물

- `experiments/2026-10-17-act18/R3_DONEWINDOW_PREREG.json`
- `experiments/2026-10-17-act18/r3-donewindow/{README.md,config.resolved.json,data-delta.json,code.diff}`
- 코드: `scripts/act18_policy.py`, `scripts/act18_train.py`, `scripts/act18_evaluate.py`, `scripts/act18_r3_data_delta.py`, `scripts/act18_r3_offline_gate.py`
- 테스트: `tests/test_act18_r3_donewindow.py`
