# pairact P3 수집 스택 (-c2, 2026-10-21 갱신)

*-c2 갱신(task 11cb2d69)*: Codex 후속 감사에서 adapter `d128984d`의 `run()`에 `runner.run` 호출이 2개라 root bridge AST 감사(`runner_call` 1개 요구)가 VM 진입 전에 ValueError를 내는 것이 재현됐습니다. adapter -a-c2 `aaabddb1`이 호출을 1곳으로 합쳤고(키워드 집합 동일, 테스트), root -r-c2가 pin 두 줄을 바꾸고 고정 adapter의 `run()`을 이 root의 `compile_function`으로 실제 변환하는 테스트를 더했습니다. teacher -c2 `4b080d35`는 테스트만 바뀌었습니다(repo audit ④: 가변 ref 대신 고정 SHA, 없으면 fail). 아래 표의 -c SHA는 이력입니다. 수집에는 `-c2` 세 SHA(`RUN_MANIFEST.json` stack)를 씁니다.

P2 smoke 스택(`-r` 0e60345d / adapter 6843fcaa / teacher 59299f90)은 그대로 둡니다. 수집 녹화용으로만 아래 `-c` 스택을 씁니다.

| tree | 브랜치 | SHA | 바뀐 것 |
|---|---|---|---|
| teacher | `dsh/pairact-p2-carrypath-c` | `01ed171fc93140683227072a10aecff55150b45f` | opt-in `--recording-admission pairact_p3_collect` / `harness.grasp_act_admission.collect_recording_admission`. ≥38/40 관문 요구만 FROZEN 수집 사전등록 sha256 일치로 대체. 640x480 녹화 동등성 check 유지 |
| adapter | `dsh/pairact-p2-carrypath-a-c` | `d128984d2fd3b136f6df1c07bb3d387fef22cd20` | 후보 `pairact_p3_collect` = `pairact_p2_r13` 프로필 + 녹화 on. env `PAIRACT_P3_COLLECT_PREREG`, `PAIRACT_P3_COLLECT_PREREG_SHA256`, `PAIRACT_P3_RECORDING_CHECK`, `PAIRACT_P3_RECORDING_PROBE`(0/1) |
| root | `dsh/pairact-p2-carrypath-r-c` | 이 문서가 든 커밋 | adapter·teacher pin 2줄만 |

- 기존 후보(`pairact_p2_r13` 등)는 -c 스택에서도 `record_training=False, noise=False` 호출이 바이트 동일합니다(각 브랜치 회귀 테스트).
- 녹화 check(`PAIRACT_P3_RECORDING_CHECK`)는 기존 규칙 그대로 `harness.grasp_act_admission.recording_mode_equivalence(기준 rows, 녹화 rows)`로 만듭니다: 같은 시작 ≥3개를 녹화 off(측정 모드)와 녹화 probe(`PAIRACT_P3_RECORDING_PROBE=1`, data_admitted=false)로 같은 VM에서 돌려 둘 다 physical_success여야 하고, 녹화 쪽 `observation_sampling.rgb_size == [640,480]`, `rgb_hz == 10`이어야 합니다. [확인 필요] MJWarp 렌더 경로가 녹화 시 640x480을 실제로 내는지 — 이 check가 바로 그것을 검사합니다.
- root `summary.json`의 `training_rgb=False`는 root 보고 필드(기존 그대로)입니다. 녹화 여부는 world `raw/result.json`의 `recording_mode`, `training_rgb`, `data_admitted`로 판단합니다.
