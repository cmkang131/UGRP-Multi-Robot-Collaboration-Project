# pairact P2: 새 seed 범위용 cases / canonical xml / native refs / rejection table

P2 운반 pilot을 r13 world(seed 8420000–8420039) 밖의 seed(예: 8343000–8343039)로 돌리려면 세 가지가 더 있어야 합니다. 그 seed의 static model용 canonical XML export, 그 export에서 다시 컴파일한 native refs(`per-world-references.json`), rejection table입니다. r13 때 쓴 파일은 8420000 계열만 담고 있습니다. 이 문서는 r13 산출물이 어떻게 만들어졌는지(근거)와 같은 절차를 새 seed에 쓰는 순서를 적습니다. VM 실행은 DeepSeek가 합니다. 여기 코드는 명령을 출력하고 결과를 검증만 합니다.

## 1. r13 산출물의 출처 (근거)

| 산출물 (gcp6) | 만든 방법 | 근거 |
|---|---|---|
| `runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json` (sha `3d4e065d…`) | `beamact5-tools/wide_start.py --seed 8420000 --dependency-root <teacher fe6858ec> --frozen-root src/beamact5-teacher-3170d909 --candidate beamact5_r13`. 후처리 없이 같은 인자로 다시 만들면 바이트가 같습니다. `-d`는 seed 8420000의 4번째 setup 변형이고, `-r4`는 round 4부터 쓴 케이스 보관 디렉터리입니다 | `dsh/pairact-p0-diag` ab84b451d `experiments/2026-10-21-pairact-p1/TONIGHT.md:11,20-24`. 스크립트 레포 사본: d94122ad0 `experiments/2026-10-17-beamact5/teacher/wide_start.py` (`--seed` :433, 40개 고정 `GATE_N` :31·:220, `seed=seed+i` :325, `rng=seed+i*10000+attempt` :235, cases 출력 :377-383) |
| `runs/beamact5/wide-export-old-8420000e/canonical-scene.xml` | `run_warp_flow_teacher_gcp6.py … --export-compiled-only`. mujoco 3.12 venv에서 `--canonical-xml`과 `--warp-native-contact-v1` 없이 실행합니다. world마다 `world-XXX/raw/scene.xml`, `canonical-scene.xml`, `per-world-references.json`(키 = export scene sha)를 씁니다 | TONIGHT.md:25-32. root runner에 같은 코드가 있습니다: `scripts/run_warp_flow_teacher.py:71,254-271` (`mujoco 3.12.0` 강제 :258) |
| `runs/beamact5/native-refs-8420000e/per-world-references.json` | `prepare_native_references_gcp6.py --source src/beamact5-teacher-3170d909 --old-export <export> --out <refs>`. CPU에서 돌고 gcp6 호스트·mujoco 3.12를 assert합니다. export scene에 `warp_native_contact_v1`과 canonical을 적용해 다시 컴파일하고, 키 = native scene sha로 저장합니다. 옛 C312 배열과 같은지 증명해 `proof.json`에 남깁니다 | TONIGHT.md:33-36. 스크립트: d94122ad0 `experiments/2026-10-17-beamact5/teacher/prepare_native_references_gcp6.py:40-88` |
| `runs/beamact5/gate-40-r13/rejection_table.json` | **seed별 생성물이 아닙니다.** gate r2 때 만든 표(`gate_id beamact5-teacher-gate-r2`, sha `16fe662a…`)를 r13 입력으로 복사한 것입니다. gate r1(같은 seed의 첫 실행)은 `wide-start-8420000d/wide-setup-funnel.json`을 `--rejection-table`로 넘겼습니다 | TONIGHT.md:12. `claude/beamact5-r2-t` 376c006f1 `experiments/2026-10-17-beamact5/README-r3.md:21`. 5d906886f `teacher/gate-40-r1/rejection_table.json:31-32`. d94122ad0 `teacher/gate-40-r2/rejection_table.json` (sha `16fe662a…`) |
| r13 gate 실행 인자 | 위 4개 경로 + `--gcp6-isolated-v1 … --batch-per-world-speed-v1` | 376c006f1 `experiments/2026-10-17-beamact5/runs/gate39-r13-run/summary.json` `reproduce` |

runner가 rejection table로 하는 일은 두 가지뿐입니다(코드: `scripts/run_warp_flow_teacher.py`). `--batch-per-world-speed-v1`이 켜져 있으면 그 경로가 *절대 경로이고 실제 파일인지* 검사하고(:128-130), `summary.json`의 `prior_rejection_table`에 경로를 기록합니다(:212). 실행이 끝나면 runner가 자기 `rejection_table.json`을 새로 씁니다(:377-383). 그래서 새 seed에는 (a)에서 나온 `wide-setup-funnel.json`을 넘깁니다. r1 선례와 같고, 9420000 확인 run 준비 때도 이렇게 했습니다.

refs를 찾는 방식은 이렇습니다. runner는 world 0의 `raw/scene.xml` sha로 refs를 찾고(`run_warp_flow_teacher.py:272-273`, 없으면 KeyError), backend는 다른 world마다 `refs.get(sha)`로 찾습니다. 없으면 `missing exact-XML C312 per-world reference`를 냅니다(`scripts/warp_act_backend.py` `initialize`). 키는 seed가 아니라 *native scene XML의 sha*입니다.

선례: seed 9420000 세트는 2026-10-20에 이 절차로 이미 만들어져 있습니다(TONIGHT.md:39-49). 경로와 sha는 다음과 같습니다. cases `wide-start-9420000/wide-cases.json` `70fa2e65…`, xml `wide-export-old-9420000e/canonical-scene.xml` `aa0c3efb…`, refs `native-refs-9420000e/per-world-references.json` `0c849f6a…`, funnel `00b1f8a8…`. 이 세트는 P1 확인 run용으로 남겨 둔 world라서 P2에 쓸지는 리드가 정합니다 [확인 필요].

## 2. 순서 (DeepSeek, gcp6)

명령 전체는 `make_seed_refs.py plan`이 출력합니다. 아래는 각 단계의 요약입니다.

```bash
cd $SRC/root    # 이 브랜치(claude/p2-seed-refs-wip 또는 리드가 cherry-pick한 -r-c4) 체크아웃
python3 experiments/2026-10-21-pairact-p2/make_seed_refs.py plan --seed-start 8343000 --n 40 | tee $RUN/seed-refs-8343000-plan.txt
```

| 단계 | 명령 (plan 출력의 step) | 산출물 | sha 기록 |
|---|---|---|---|
| a | `a_cases`: `wide_start.py --seed 8343000 --candidate beamact5_r13` (cwd·PYTHONPATH = adapter `d354468a` 트리, venv-warp) | `runs/beamact5/wide-start-8343000/{wide-cases,wide-setup-funnel,wide-gate-plan,wide-pre-registration,wide-distribution}.json` | stdout의 `cases_sha256`. `sha256sum wide-cases.json wide-setup-funnel.json` |
| b | `b_export`: gcp6 runner `--export-compiled-only` (cwd = root `05046e9d`, venv-sim mujoco 3.12, `--indices 0..n-1`). GPU를 쓰지 않습니다. 9420000 때 40 world에 316.95 s 걸렸습니다 | `runs/beamact5/wide-export-old-8343000e/{summary.json(status initialization_only), canonical-scene.xml, per-world-references.json, world-XXX/raw/scene.xml}` | `sha256sum canonical-scene.xml per-world-references.json summary.json` |
| c | `c_refs`: `prepare_native_references_gcp6.py` (cwd = `beamact5-teacher-3170d909`, venv-sim) | `runs/beamact5/native-refs-8343000e/{per-world-references.json, proof.json, canonical-scene.xml, references/<sha>/…}` | stdout(`compiled_N`, `arrays_exact`). `sha256sum per-world-references.json proof.json` |
| d | `d_manifest`: `make_seed_refs.py manifest` (CPU, 순수 파이썬). export summary의 `cases_sha256`와 `status`, world→seed→export scene sha→proof→native sha→refs 키를 확인하고, compiled 파일이 있는지 봅니다. 하나라도 빠지면 오류로 끝납니다 | `runs/pairact-p2/seed-refs-8343000-manifest.json` (seed별 `native_xml_sha256`, 입력 4종 경로와 sha) | stdout의 `sha256`, `cases_sha256`, `refs_sha256`, `canonical_xml_sha256`, `rejection_table_sha256` |
| e | `e_p2_cases`: `make_p2_cases.py --seed-start 8343000 --n 40 --seed-cases … --seed-refs-manifest … --to pairact_p2_r13_detour` | `runs/pairact-p2/p2-seed8343000-cases.json` (candidate만 바뀜, `source_world_index` = wide-cases 내 위치) | stdout의 `sha256`, `seeds`, `indices`, `seed_refs_manifest_sha256` |
| f | (권장) P2 스택으로 init-only를 돌린 뒤 검사합니다. 실행 명령(SMOKE.md §3 / DETOUR_C3.md)에서 `--cases`=e, `--canonical-xml`·`--per-world-model-references-v1`·`--rejection-table`=manifest의 세 경로로 바꾸고, `--initialize-only`와 새 `--out`을 붙입니다. 그다음 `make_seed_refs.py check-init --manifest … --init-out <그 out>`을 실행합니다 | `ok:true`가 아니면 `MISSING_SEED_REFS` 오류로 끝납니다 | check-init stdout |
| g | 실행: 같은 명령에서 `--initialize-only`를 빼고 `--indices`=e의 `indices`로 씁니다 | `summary.json`의 `cases_sha256`가 e의 sha와 같아야 합니다 | 기존 SMOKE.md §4 |

- e는 seed의 refs가 manifest에 없거나, refs 파일이 없거나, compiled 파일이 디스크에 없으면 `SystemExit('MISSING_SEED_REFS: seeds [...] …')`로 끝나고 cases 파일을 쓰지 않습니다. seed가 cases 파일에 없으면 `MISSING_SEED_CASES`로 끝납니다.
- 기본 모드(`--r13-cases`, world 1·11·17, r13 sha 고정)는 바뀌지 않았습니다. 테스트 `test_default_mode_bytes_identical_to_base`가 90a99ee98 판과 출력 바이트를 비교합니다.
- `--n`은 1..40입니다. `wide_start.py`는 `--seed`마다 항상 40개를 만들고(world i의 plan은 i와 seed만으로 정해짐), b·e는 앞의 n개만 씁니다. `--seed-start`는 `wide_start.py --seed`와 같은 값이어야 합니다. 다른 시작점(예: 8343010)을 주면 layer·yaw 배정이 다른 별개의 세트가 됩니다.
- seed 겹침: `rng = seed + i*10000 + attempt` (attempt < 5000). 8343000 계열과 9420000 계열은 rng가 겹칠 수 없습니다. 8420000 계열과는 *8343000의 world i = 8420000의 world i−8*이고 8420000 쪽 attempt가 3000 이상 클 때만 겹칩니다(`plan`이 출력합니다). 두 cases 파일의 `plan.proposal_attempts` 최댓값을 기록해 3000 미만임을 확인합니다. 9420000 세트는 40 world에 proposals 109였습니다.

## 3. [확인 필요]

- b와 c는 r13 스택(root `05046e9d`, adapter `d354468a`, teacher `fe6858ec`)으로 export합니다(TONIGHT.md §0.1 절차 그대로). P2 adapter(`30dbc689`)가 같은 seed에서 *같은 scene XML*을 만드는지는 일반적으로 증명되지 않았습니다. r13 world 1·11·17에서는 r13 refs로 P2 smoke·pilot이 초기화를 통과했습니다. 그래서 f(`check-init`)로 실제 키가 맞는지 확인합니다. 맞지 않으면 b를 P2 스택(adapter/teacher/root = P2 SHA, cases = e 결과)으로 다시 export합니다. 이 경우 e를 먼저 만들 수 없으므로 순서를 a→(임시 cases)→b→c로 조정해야 합니다.
- `beamact5-tools/run_warp_flow_teacher_gcp6.py`와 `prepare_native_references_gcp6.py`는 VM 사본입니다. 레포 사본(d94122ad0 `experiments/2026-10-17-beamact5/teacher/`)과 바이트가 같은지 `sha256sum`으로 확인합니다.
- `/home/ugrp/ugrp-sim/src/../ugrp/.venv-{warp,sim}` 경로와 `src/pairact-{root-05046e9d,adapter-d354468a,teacher-fe6858ec}` worktree는 2026-10-20 기준 확인값입니다(TONIGHT.md §0). 지금도 그대로인지 확인합니다.
- `wide-export-old-8420000e`의 `e`, `wide-start-8420000d`의 `d` 접미사(export가 어느 setup 변형의 cases로 만들어졌는지)는 레포 기록으로 끝까지 추적하지 못했습니다. 새 seed에는 위 명령의 디렉터리명(`wide-start-<S>`, `wide-export-old-<S>e`, `native-refs-<S>e`)을 씁니다.
- seed 8343000을 고른 근거와, 다른 실험 seed와 겹치지 않는지는 리드가 확인합니다. 8328xxx와는 rng가 겹치지 않습니다.
