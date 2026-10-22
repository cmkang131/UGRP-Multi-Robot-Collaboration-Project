# pairact-r1 실행 순서 (DeepSeek용 — 수집 사전 등록 v9, 샤딩 + 정지 barrier)

v9 변경(2026-10-22, 대응표 `CODEX_RESPONSE_V9.md`, 팀장 결정): **위협 모델은 악의적 공격자가 아니라 *실수로 인한 불일치***입니다(prereg `threat_model`). v9가 마지막 강화 라운드이고, 이후 남는 적대적 환경 항목은 아래 운영 규칙으로 처리하고 동결합니다.
- *셸 환경 고정*: 수집 셸에서 `PYTHONPATH`·`PYTHONHOME`을 **설정하지 않습니다**(`unset PYTHONPATH PYTHONHOME`, 확인 `env | grep -E '^(PYTHONPATH|PYTHONHOME)='` → 출력 없음). core·final 관문이 이 둘이 설정된 채로는 `episode pin refused: …`로 즉시 거부합니다(wrapper가 stack 경로를 스스로 넣으므로 필요 없음).
- *수집 중 수정 금지*: wrapper 사본과 그 옆 `gcp6_host.py`(호스트 신원 모듈), teacher/adapter/root 체크아웃, venv(pip install 포함), canonical XML·mesh, rejection table, 기록 디렉터리를 수집 중에 바꾸지 않습니다. runner가 episode마다 wrapper·python·WARP_SOURCE_ROOT pin과 세 체크아웃의 HEAD·clean을 실행 전후에 다시 보고(launch binding `pin`/`pin_post`, `stack`/`stack_post`), check-rows·convert-input이 불일치 산출물을 거부합니다. 검사 직후~execve 사이 교체·실행 중 교체 후 원복은 적대적 행위로 보고 방어를 주장하지 않습니다(운영 규칙).
- *설치 시점 확인(운영)*: `beamact5-tools/`의 wrapper 사본과 `gcp6_host.py`는 최신 커밋에서 한 번만 복사하고, 수집 시작 전에 `sha256sum /home/ugrp/ugrp-sim/src/beamact5-tools/*.py`를 실행해 값을 보고서에 남깁니다(이 디렉터리는 git 검사 밖). `--no-verify-assets`는 probe-episode·convert-input·FROZEN 수집에서 쓰지 않습니다(자산·stack 재검사를 끔).
- *v8 승계*: episode wrapper는 **절대경로·자기 realpath**(symlink·`..` 금지)이고, `readlink -f`가 그 경로와 같아야 합니다. episode python은 **절대경로**입니다(`PY=$(command -v python)`). v9 binding은 pin/stack을 모두 요구하므로 **v8 이전에 만든 probe raw·training raw는 거부**됩니다 — probe-episode·수집을 v9 코드로 다시 실행해야 합니다.

v5 변경(2026-10-21, 대응표 `CODEX_RESPONSE_V5.md`, Codex v4 재검토 1–5 + collector carry_success):
- *녹화 증거 core 결속*: check-rows가 probe source 원장(purpose·core)·`probe-cases.json` sha256·seed 순서를 기록하고, FROZEN gate·freeze final(각 `--vm-recording-dir` 포함)이 check-rows/probe source core == 현재 core, probe-cases ↔ check rows ↔ recording-check seed 일치를 확인합니다. 다른 core에서 만든 check는 거부됩니다(1-4 ④, 1-5).
- *XML 의존 파일 전체*: `assets.mesh_assets_sha256`은 `pairact_r1_freeze.py xml-assets --canonical-xml XML` 출력 그대로(include·mesh·skin·hfield·texture, meshdir/texturedir/assetdir/strippath, 재귀). `--verify-assets`는 누락·무관 등록·해시 변경을 모두 거부합니다(1-3).
- *episode 소스 = 검사한 checkout*: episode 명령의 `--teacher-source`·`--adapter-source`와 `WARP_SOURCE_ROOT`(템플릿 토큰 또는 환경)가 `--dependency-root`·`--adapter-root`·`--frozen-root`와 같은 경로여야 하고 존재해야 합니다. collect와 probe-episode가 검사합니다(1-1, 1-4 ③).
- *원장 확정 prefix*: 마지막 newline까지가 확정입니다. 개행 없는 꼬리는 유효 JSON이라도 읽지 않고, repair가 자르며, merge 봉인(`merge.json` `ledger_seal: committed_prefix_v1`)에 들어가지 않습니다. 끊긴 꼬리 복구 뒤 재merge가 됩니다.
- *완료 attempt 중복 거부*: 같은 batch slot 또는 같은 (split, seed, requeue)가 두 번 있으면 merge·report·convert-input이 거부합니다.
- *carry_success*: summary world에 `carry_success`가 없으면 result `carry_eval.success`로 판정합니다(gcp2 smoke 25 record_error 원인). 값이 있고 다르면 record_error이고, record_error는 S·A가 아닙니다. 레포 gcp6 wrapper(`experiments/2026-10-17-beamact5/teacher/run_warp_flow_teacher_gcp6.py`)도 이제 `carry_success`를 씁니다 — VM의 `/home/ugrp/ugrp-sim/src/beamact5-tools/` 사본을 이 파일로 갱신한 뒤 `assets.wrapper_sha256`을 채웁니다.


v4 변경(2026-10-21, 대응표 `CODEX_RESPONSE_V4.md`, 교차 검토 B1–B3·R1–R8 + Codex H1–H5):
- *정지 barrier*(K>1): 첫 정지가 보이면 새 batch를 계획하지 않고(`train_barrier` hold, `batch_skipped`) 실행 중 batch를 모두 끝낸 뒤 *전체 원장*으로 정지를 한 번 판정해 `train_closed`로 고정합니다. 정지가 아니면(예: STOP_SEEDS인데 실행 중 batch의 HOST_ERROR 재큐가 남음) `release`하고 직렬과 같이 이어갑니다. 정지·학습 판정은 K와 무관하게 같은 함수입니다. 구간 배정 순서는 K>1이면 직렬과 달라질 수 있습니다(공개 유지).
- validation batch가 unclean이면 판정된 world도 같은 seed로 1회 재큐합니다. 재큐 batch도 unclean이면 그 seed는 미채택입니다.
- `bin_limit`은 채택률 A_b/N_b < 0.2(배정과 같은 지표, 물리 성공률은 보고용), 거리 관문은 *전부 제한된 거리 구간*(예: B4·B5 = 0.9–1.2 m)을 분모·칸 검사에서 빼고 요구 비율을 줄인 뒤 결과에 `거리 관문 축소(...)` 표기를 붙입니다.
- STOP_HOST: 연속 2 batch unclean(순서 기준, 나중 clean batch가 지우지 못함) *또는* 한 샤드의 자기 batch가 연속 3개 unclean이거나 6개 이상 중 30% 이상 unclean.
- *오너 결정 D-v4-1*: STOP_DISTANCE는 원거리 구간(B4·B5)이 모두 A_b≥20이거나 제한된 뒤에만 평가합니다(그 전에는 정지 사유 아님). K 상한은 *3*입니다(X7 가짜에서 K=4만 직렬과 판정 클래스가 달랐음, prereg `sharding.K_max`·`K`에 사례 공개). manifest gate와 CLI가 K>3을 거부합니다.
- K(샤드 수, 1–3)는 *FROZEN_CORE 전* measurement 모드 측정(1-2b)으로 정합니다. pilot 26/40은 -c4 결과라 -c5 수율 근거로 쓰지 않습니다.
- convert-input은 merged root만, `merge.json` finished·running 없음·원장 sha 일치·admitted raw 존재를 확인합니다. merge는 샤드 원장이 이전 merge의 append-only 연장인지, seed가 두 번 새로 쓰이지 않았는지 검사합니다. 학습 수집은 `--dependency-root/--adapter-root/--frozen-root`의 git HEAD가 RUN_MANIFEST stack pin과 같고 clean해야 시작합니다.

v3s 변경(2026-10-21): 수집을 *샤드 병렬*로 돌립니다(prereg `sharding`, 실행 방식만 바뀌고 판정·집계·정지·배정 공식·seed 규칙은 그대로). 같은 VM 3–4 프로세스와 두 VM 동시 실행은 1-6a·1-6b, 예상 시간 계산식은 1-6c에 있습니다. 스택은 *-c5*(teacher -c4 + c3 admission)로 고정했습니다(1-0).

v3 변경(Codex v2 재검토 HOLD 대응, 대응표 `CODEX_RESPONSE_V3.md`): 동결이 *2-커밋(X·Y) + 2단계(FROZEN_CORE → FROZEN)*로 바뀌었습니다. pre-freeze pilot은 수율 전용(`pilot_yield_only`)이라 녹화 probe·학습 입력으로 쓸 수 없습니다. probe 대상은 FROZEN_CORE에서 새로 돌리는 *probe source* 측정 run에서 고릅니다.
전제: P1 관문(≥38/40)은 수집을 막지 않는 병행 작업입니다. 수집 시작 조건은 *P2 smoke 전 구간 성공 ≥1* 하나이고 smoke-1c(seed 8420001·8420011·8420017) 운반 성공 2/3으로 충족했습니다(증거 해시는 `RUN_MANIFEST.json` `smoke`의 VM 기입 칸).
규칙: 새 run root만 씁니다. 원본·체크포인트는 덮어쓰지 않습니다. 오프피크(UTC 16:30–00:30)에만 실행하고 끝나면 VM을 정지합니다. 브랜치는 `dsh/pairact-carry-r1-v9`입니다(v9 실행 지침, 1-1의 `COL`).

## 0. 사전 확인 (CPU, 수 분)
```
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest -q tests/test_pairact_collect.py tests/test_pairact_r1.py tests/test_pairact_collect_shard.py   # 120 passed 기대 (skip 0)
```
`tests/test_pairact_collect.py`의 고정 스택 admission 테스트는 -c2 세 SHA 커밋이 로컬 저장소에 있어야 합니다(없으면 fail, skip 아님).

## 1. P3 수집 — 성공 시연만 학습 (오프피크)

정본: `COLLECT_PREREG_DRAFT.json`(v3, READY_FOR_REVIEW)과 `RUN_MANIFEST.json`(schema `ugrp.pairact_r1.run_manifest.v2`, DRAFT_VM_FILL). runner `scripts/run_pairact_collect.py`, 제어 로직 `harness/pairact_collect.py`, case 생성 `collect_cases.py`, 동결 `scripts/pairact_r1_freeze.py`.

동결 단계 요약:

| 단계 | prereg·manifest status | 허용 | 원장 purpose |
|---|---|---|---|
| 리뷰 중 | READY_FOR_REVIEW / DRAFT_VM_FILL | pilot 측정 run(수율만) | `pilot_yield_only` — probe-cases·convert-input이 거부 |
| 커밋 Y | FROZEN_CORE / FROZEN_CORE | probe source 측정 run, probe-cases, probe-episode, check-rows | `probe_source` (원장 header에 core_sha256) |
| 커밋 Z | FROZEN / FROZEN | 학습 수집 run, report, convert-input | `training` (header에 FROZEN·core_sha256) |

`core_sha256` = sha256(canonical JSON {prereg에서 status 제외, manifest에서 status·recording_check 3칸 제외}) — `harness.pairact_collect.core_sha256`. 파일에는 저장하지 않고 freeze 스크립트가 출력하며 원장 header가 기록합니다. Z에서 바뀌는 것은 status와 recording_check 3칸뿐이라 core_sha256이 그대로여야 합니다(스크립트가 검사).

### 1-0. 시작 조건과 스택 pin 갱신 절차
1. *P2 smoke 전 구간 성공 ≥1*: 충족(smoke-1c 2/3). smoke 해시 4칸은 VM에서 채웁니다.
2. *스택 pin (-c5, 고정됨)*: `RUN_MANIFEST.json` `stack`에 세 SHA가 들어 있습니다. VM에서 checkout이 같은지만 확인합니다.
   ```bash
   git ls-remote origin dsh/pairact-p2-carrypath-c5 dsh/pairact-p2-carrypath-a-c5 dsh/pairact-p2-carrypath-r-c5
   # 기대: teacher 75929e7719ad98a089e3dda5251f4249d8bae511, adapter 3779d9615ef6dc8e38f57ab968a14a9e45189ecc, root a93082c343ef5f3687851bf4b0c9fb0f2484ada1
   git -C $SRC/teacher grep -n "COLLECT_PROBE_STATUSES" -- harness/grasp_act_admission.py     # 1줄 이상 (c3 admission 포함)
   grep -n "^DEPENDENCY_SHA" $SRC/adapter/harness/beampair_teacher.py                          # = teacher -c5 SHA
   grep -n "^ADAPTER_SHA\|^TEACHER_SHA" $SRC/root/scripts/warp_flow_episode.py                   # = adapter -a-c5 / teacher -c5
   (cd $SRC/teacher && python -m pytest -q tests/test_pairact_p3_collect_admission.py tests/test_grasp_act_admission.py \
      tests/test_pair_carry_route_c4.py tests/test_pair_carry_detour.py tests/test_pair_carry_teacher_warp.py)   # 88 passed
   (cd $SRC/adapter && python -m pytest -q tests/test_pairact_p2_adapter.py)     # 9 passed
   (cd $SRC/root && python -m pytest -q tests/test_pairact_p2_root.py)           # 12 passed
   ```
   -c5 teacher = -c4 `402bbf155` + `c6626187b` cherry-pick(`5d6dab139`, 충돌 없음) + 테스트만 고친 `75929e771`(녹화 승인 바이트 동일 테스트가 -c3/-c4의 `carry_route` 키워드 삽입 3줄을 허용). 스택이 바뀌면 새 FROZEN_CORE입니다(`C5_STACK.md`는 root 브랜치 `experiments/2026-10-21-pairact-p2/`).
   - 선택: adapter가 `PAIRACT_P3_COLLECT_PREREG_CORE_SHA256`를 `collect_recording_admission(..., expected_core_sha256=...)`로 넘기면 teacher가 prereg core도 대조합니다. -a-c5는 넘기지 않으며 파일 sha256 대조는 그대로입니다.
3. *녹화 승인*(teacher -c5 `collect_recording_admission`): prereg 스키마 v2 인정, 녹화 probe는 FROZEN_CORE/FROZEN, 데이터 녹화는 FROZEN만. 640x480 녹화 동등성 check는 그대로이고 *기계에 묶입니다*(`same_machine`) — 두 번째 VM은 자기 check가 따로 필요합니다(1-6b).
4. *대체 경로*: 녹화 경로가 VM에서 처음 실패하면 그 밤은 측정 run만 하고 "수율 측정, 시연 아님"으로 보고합니다.

### 1-1. 준비 (CPU, 수 분)
```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-p3c5      # -c5 스택 (1-0의 세 SHA, 두 VM이면 두 VM 모두 같은 절대경로)
TEACHER_C5=75929e7719ad98a089e3dda5251f4249d8bae511; ADAPTER_C5=3779d9615ef6dc8e38f57ab968a14a9e45189ecc; ROOT_C5=a93082c343ef5f3687851bf4b0c9fb0f2484ada1
mkdir -p $SRC
for t in teacher:$TEACHER_C5 adapter:$ADAPTER_C5 root:$ROOT_C5; do
  git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $SRC/${t%%:*} ${t#*:}      # VM 레포 경로는 [확인 필요]
done
COL=/home/ugrp/ugrp-sim/src/pairact-r1v9      # 이 브랜치 worktree (단계마다 X → Y → Z로 갱신)
git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $COL origin/dsh/pairact-carry-r1-v9
cd $COL && python -m pytest -q tests/test_pairact_*.py   # 기대 수: CODEX_RESPONSE_V9.md 맨 끝 (v9: 297)
unset PYTHONPATH PYTHONHOME          # v9: core·final 관문이 이 둘이 설정된 셸을 거부 (wrapper가 stack 경로를 스스로 넣음)
env | grep -E '^(PYTHONPATH|PYTHONHOME)=' || true   # v9: 기대 출력 없음
export WARP_SOURCE_ROOT=$SRC/root     # v5: gcp6 wrapper의 root 소스. stack 검사가 --frozen-root와 같은 경로인지 확인
cp $COL/experiments/2026-10-17-beamact5/teacher/run_warp_flow_teacher_gcp6.py \
   $COL/experiments/2026-10-17-beamact5/teacher/gcp6_host.py /home/ugrp/ugrp-sim/src/beamact5-tools/   # v9: wrapper + 호스트 신원 모듈을 커밋에서 함께 갱신 (VM 경로 [확인 필요])
readlink -f /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py   # v8: 출력이 위 경로와 같아야 함(경로 성분 symlink 금지)
P=$COL/experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json
M=$COL/experiments/2026-10-21-pairact-r1/RUN_MANIFEST.json
PY=$(command -v python)    # v8: core/final은 절대경로 python만 허용(bare python은 실행 PATH로 해석되므로 거부)
EP="$PY /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py --flow beampair \
 --adapter-source $SRC/adapter --teacher-source $SRC/teacher --cases {cases} --indices {indices} --cap-s 60 --out {out} \
 --vm-hourly-usd 1.096 --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1 \
 --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1 \
 --canonical-xml /home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml \
 --per-world-model-references-v1 /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json \
 --rejection-table /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json --batch-per-world-speed-v1"
printf %s "$EP" | sha256sum      # -> RUN_MANIFEST.json command.episode_template_sha256 ($SRC·$PY가 모두 펼쳐진 문자열을 episode_template에)
```

### 1-2. (선택) pilot 측정 run — READY_FOR_REVIEW, 녹화 off, seed 8343000–039
```bash
RUNP=/home/ugrp/ugrp-sim/runs/pairact-p3-pilot-$(date -u +%Y%m%dT%H%M); mkdir -p $RUNP
python scripts/check_pairact_r1_seeds.py --scan-refs origin/main origin/codex/beamact1 origin/claude/beampair7 \
  origin/claude/beampair8 origin/claude/beampair9 origin/claude/beamact5 origin/dsh/pairact-p0-diag \
  origin/dsh/act18-carry-retrain-r1 origin/dsh/pairact-p2-carrypath origin/dsh/pairact-p2-carrypath-r \
  origin/dsh/pairact-p2-carrypath-a origin/dsh/pairact-p2-carrypath-c origin/dsh/pairact-p2-carrypath-a-c \
  origin/dsh/pairact-p2-carrypath-r-c origin/dsh/pairact-p5-student > $RUNP/seed-check.json   # passed=true -> sha256을 seed_check.vm_seed_check_sha256에
python $COL/scripts/run_pairact_collect.py collect --prereg $P --run-root $RUNP --mode measurement --noise off \
  --batch-size 20 --max-batches 2 --deadline-utc $DEADLINE --run-manifest $M \
  --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter --episode-cmd "$EP"
```
- 원장 purpose는 `pilot_yield_only`입니다. "수율 측정, 시연 아님"으로만 보고하며 probe·학습 입력에 쓰지 않습니다(runner가 거부).
- 이미 있는 READY pilot 26/40(STATUS 2026-10-21)은 *-c4 스택* 결과입니다. -c5 수집의 수율 근거로 쓰지 않습니다(600 상한의 33% 가정은 결정 문서 3의 값). 보고에는 purpose와 스택을 같이 적습니다(`pilot_yield_only -c4`, `probe_source -c5`).

### 1-2b. K(샤드 수) 경합 측정 — measurement 모드, *FROZEN_CORE 전* (prereg `sharding.K`, 교차 검토 R6)
K는 core 내용이라 FROZEN_CORE에서 고정되고, 학습 run root를 연 뒤에는 바꾸지 않습니다(바꾸려면 새 prereg 개정·오너 결정, 같은 train seed 재수집 금지). 그래서 경합 측정을 *먼저* 합니다.
```bash
# 같은 VM에서 K개 프로세스를 동시에 (각자 다른 run root, 각 20 world, pilot seed 8343000–019 batch 1개; 수율은 보고하지 않음)
for K in 2 3; do      # K 상한 3 (D-v4-1)
  for i in $(seq 1 $K); do
    RUNK=/home/ugrp/ugrp-sim/runs/pairact-p3-kmeas-K$K-p$i-$(date -u +%Y%m%dT%H%M); mkdir -p $RUNK
    nohup python $COL/scripts/run_pairact_collect.py collect --prereg $P --run-root $RUNK --mode measurement --noise off \
      --batch-size 20 --max-batches 1 --deadline-utc $DEADLINE --run-manifest $M \
      --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter --episode-cmd "$EP" > $RUNK.log 2>&1 &
  done; wait      # 프로세스마다 summary.json wall_s·host_loop_s.world_ticks, nvidia-smi 최대 메모리, CPU 사용률 기록
done
```
- 판정: 처리량 ∝ P ÷ s_wt(P)입니다. `K ÷ s_wt(K)`가 `(K−1) ÷ s_wt(K−1)`보다 크고 GPU 메모리 여유가 있을 때만 K를 올립니다(1-6c). 결과로 `RUN_MANIFEST.json` `sharding.count`·`lag_batches`·`assignment`를 정하고 1-3으로 갑니다.
- 이 측정은 *결정성·경합 측정용*입니다. measurement 모드는 구간이 고정(`seed % 6`)이라 K>1의 적응 경로(warmup·deficit·bin_limit·정지 barrier)는 검증하지 못합니다. 그 경로는 가짜 에피소드 테스트(`test_pairact_prereg_xreview.py` X1·X2·X7·X8, `test_pairact_collect_shard.py`)로만 검증되었다고 보고에 적습니다.
- 같은 pilot seed를 여러 run root에서 돌리므로 수율은 보고하지 않고 합산하지 않습니다. warp kernel cache 동시 컴파일 충돌 여부 [확인 필요](첫 프로세스 시작 300 s 뒤 나머지를 띄우는 방식도 기록).
- *중단·재시작*: 같은 명령을 다시 실행하면 `ledger.jsonl`에서 이어갑니다. 최종 summary가 있는 배치는 다시 돌리지 않고 집계만 합니다. 중간에 끊긴 배치는 남은 slot만 `try-2`로 1회 재시도하고 두 번째도 끊기면 환경 실패로 닫습니다. HOST_ERROR world는 같은 seed·구간으로 1회 재배정되고, 그 재배정 slot이 생성기에서 setup 거부되면 대기열에서 빠집니다(다시 고르지 않음).

### 1-3. 커밋 X·Y — FROZEN_CORE (Codex 재검토 통과 뒤)
1. *커밋 X*: Codex가 통과시킨 collector 코드 커밋(`COLLECTOR_FILES` + `collect_cases.py`를 마지막으로 바꾼 커밋). `X=$(git -C $COL rev-parse HEAD)`. 이후 이 파일들은 바꾸지 않습니다(바뀌면 runner가 거부).
2. *샤드 수·VM 배정 결정*(core 내용이라 여기서 확정): `RUN_MANIFEST.json` `sharding` 초안은 한 VM 3샤드(`count` 3, `assignment` {"gcp6": [0,1,2]}, `primary_vm` gcp6)입니다. K 상한 3(D-v4-1). 두 VM이면 합쳐서 3: `count` 3, `lag_batches` 3, `assignment` {"gcp6": [0,1], "gcp2": [2]}로 바꿉니다(gcp2 MJWarp 스택 준비 여부 [확인 필요]). K는 1-2b 측정 결과로 정합니다(측정 전에는 FROZEN_CORE로 가지 않습니다).
3. VM에서 읽기 전용 명령(`RUN_MANIFEST.json` `fill_commands`)으로 VM 기입 칸을 채웁니다. 22칸 = prereg 1 + collector 1 + command 2 + assets 5 + host 5 + smoke 4 + recording_check 3 + seed_check 1이며, *이 단계에서는 recording_check 3칸을 뺀 19칸*을 채우고 stack 세 SHA도 채웁니다. 타입: sha256은 64자리 소문자 hex, 커밋은 40자리, `assets.mesh_assets_sha256`은 {절대경로: sha256}(v5: `python $COL/scripts/pairact_r1_freeze.py xml-assets --canonical-xml <canonical-scene.xml>` 출력 그대로 — canonical XML이 참조하는 파일 집합과 정확히 같아야 함), `smoke.carry_eval_sha256`은 {world-000, world-001, world-002: sha256}. 빈 문자열·`[VM 기입]`·`[확인 필요]`·`<...>`는 gate가 거부합니다.
4. `python $COL/scripts/pairact_r1_freeze.py core --collector-sha $X --verify-assets` → prereg·manifest status FROZEN_CORE, `collector.source_sha`, `prereg.core_sha256`을 쓰고 stage core gate(스키마·타입·placeholder·prereg/limits 교차·X 조상·collector 파일 X..HEAD 불변·자산 재해시)를 통과해야 파일을 씁니다. 출력의 `core_sha256`을 `CORE`로 적어 둡니다.
5. *커밋 Y*: prereg·manifest 두 파일만 커밋하고 메시지에 `CORE`를 적습니다(Claude/Codex 확인 뒤 push). `$COL`을 Y로 갱신합니다(추적 파일이 clean해야 다음 단계가 진행됩니다).

### 1-4. FROZEN_CORE — probe source → 녹화 probe → check (GPU, 오프피크)
```bash
RUNC=/home/ugrp/ugrp-sim/runs/pairact-p3-probesrc-$(date -u +%Y%m%dT%H%M); mkdir -p $RUNC
# ① probe source: FROZEN_CORE 측정 run (녹화 off, pilot seed, 채택 후보 3개가 나올 때까지 1–2 batch)
python $COL/scripts/run_pairact_collect.py collect --prereg $P --run-root $RUNC --mode measurement --noise off \
  --batch-size 20 --max-batches 1 --deadline-utc $DEADLINE --run-manifest $M \
  --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter --episode-cmd "$EP"
# ② probe 대상: probe source 원장(purpose probe_source, header core_sha256 == 현재 core)의 첫 채택 후보 3개
python $COL/scripts/run_pairact_collect.py probe-cases --prereg $P --run-root $RUNC --run-manifest $M --out $RUNC/probe-cases.json
# ③ 녹화 probe 3 world (data_admitted=false, check 불필요; teacher가 FROZEN_CORE를 probe에만 인정)
python $COL/scripts/run_pairact_collect.py probe-episode --prereg $P --run-root $RUNC --run-manifest $M \
  --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter \
  --episode-cmd "$EP" --out $RUNC/probe-1      # v5: stack pin + episode 소스 경로 검사
# ④ check rows(v5: core + probe source 원장 purpose/core/seed + $RUNC/probe-cases.json sha256 기록) → teacher의 기존 함수로 recording check
python $COL/scripts/run_pairact_collect.py check-rows --prereg $P --run-root $RUNC --run-manifest $M --out $RUNC/check-rows.json \
  --baseline-raws <②가 출력한 baseline_raws 3개> --probe-raws $RUNC/probe-1/world-00{0,1,2}/raw
(cd $SRC/teacher && python -c "import json;from harness.grasp_act_admission import recording_mode_equivalence as f;r=json.load(open('$RUNC/check-rows.json'));print(json.dumps(f(r['baseline'],r['recorded'])))") > $RUNC/recording-check.json
```
- ①의 purpose가 `pilot_yield_only`이면(prereg가 아직 READY) ②가 거부합니다. 1-2의 pilot 원장도 ②에서 거부됩니다.
- ②–④ 중 하나라도 실패하거나 `recording-check.json`의 `qualified`가 true가 아니면 FROZEN으로 가지 않고 원인을 로그와 함께 Claude에게 넘깁니다. probe source 수율은 pilot과 합산하지 않습니다.

### 1-5. 커밋 Z — FROZEN
```bash
python $COL/scripts/pairact_r1_freeze.py final --recording-dir $RUNC --expect-core $CORE --verify-assets
# 두 VM이면: gcp2에서 1-6b ①–④를 먼저 하고 그 디렉터리를 붙입니다
#   ... final --recording-dir $RUNC --vm-recording-dir gcp2=$RUNC_B --expect-core $CORE --verify-assets
```
recording_check 3칸을 `$RUNC/{probe-cases,check-rows,recording-check}.json` sha256으로 채우고 status를 FROZEN으로 바꾼 뒤 stage final gate(세 파일 해시 대조·qualified 포함, v5: check-rows·probe source core == 현재 core, probe-cases ↔ check rows ↔ recording-check seed 일치 — `--vm-recording-dir` 디렉터리도 같음)를 통과해야 씁니다. core_sha256이 `CORE`와 다르면 거부합니다. *커밋 Z*(두 파일만, 메시지에 CORE) → push → `$COL`을 Z로 갱신.

### 1-6. 학습 수집 run (FROZEN, 새 run root, 샤드 병렬)
샤드 규칙(prereg `sharding`, `batch_owner_lag_v1`): 전역 batch k는 shard `k % K`가 계획하고 돌립니다. batch k는 *batch < k의 계획 + batch ≤ k−K의 결과*만 보고 기존 규칙(plan_batch·allocate·정지)으로 계획합니다. 그래서 어느 샤드가 먼저 끝나든 같은 원장이 나옵니다(K=1이면 직렬 원장과 행 단위 동일, 테스트 고정). 진행 중인 batch의 train slot은 시도 상한 600에 미리 잡힙니다. *정지 barrier*(v4): 지연된 view에서 정지가 처음 보이면 `train_barrier`(hold) 행을 쓰고 새 batch를 계획하지 않습니다(`batch_skipped`, seed 소비 없음). 진행 중 batch가 모두 끝나면 전체 원장으로 같은 정지 함수를 한 번 평가해 정지면 `train_closed`로 고정하고, 정지가 아니면 `train_barrier`(release) 뒤 직렬과 같이 이어갑니다(예: STOP_SEEDS였는데 HOST_ERROR 재큐가 남은 경우). 진행 중 batch의 결과는 모두 집계합니다(overshoot 규칙과 같음). validation은 `train_closed` 뒤에만, train batch가 하나도 실행 중이 아닐 때 계획됩니다.
- 샤드마다 원장 `$RUNT/shards/sII/ledger.jsonl`, batch 디렉터리 `$RUNT/shards/sII/batches/bNNN/`. 한 샤드는 한 프로세스만(파일 lock, 두 번째는 즉시 실패). 원장 header에 shard 번호·K·VM이 남아 다른 VM·다른 K로 재시작하면 거부합니다.
- 재시작: 같은 명령을 다시 실행합니다. 끊긴 batch는 직렬과 같은 규칙(try-2 1회, 두 번째도 끊기면 환경 실패로 닫음)으로 이어갑니다.
- 기다림: 다음 batch의 view가 아직 안 찼으면 `--poll-s`(기본 30 s)마다 다시 봅니다. 한 샤드가 죽으면 나머지는 그 batch에서 멈춰 기다립니다(결정성 때문). `--max-wait-s`를 넘기면 `WAITING`으로 끝납니다(누적 대기). `--deadline-utc`를 넘기면 새 batch를 시작하지 않고 `DEADLINE`.
- STOP_HOST: 연속 2 batch unclean 또는 한 샤드의 연속 3 unclean / 6개 이상 중 30% 이상 unclean(prereg `stop_rules.shard_host`). barrier 뒤 `train_closed`(STOP_HOST)가 써지고 모든 샤드가 `STOP_HOST`로 끝납니다(validation은 계획하지 않음). `report.json` `decision.host_stop.shards`에 어느 샤드인지 나옵니다. 호스트 수정 보고 뒤 *모든 샤드*를 `--validation-after-host-fix`로 다시 실행합니다.
- validation batch가 unclean이면 그 batch에서 판정된 world도 환경 실패처럼 같은 seed로 1회 재큐됩니다(`unclean_batch_requeue`, N에 넣지 않음). 재큐 batch도 unclean이면 그 seed는 미채택으로 남고 더 재큐하지 않습니다.

#### 1-6a. 같은 VM 2–3 샤드 (g2-standard-8, L4 1장)
```bash
RUNT=/home/ugrp/ugrp-sim/runs/pairact-p3-train-$(date -u +%Y%m%dT%H%M); mkdir -p $RUNT/logs
K=$(python -c "import json;print(json.load(open('$M'))['sharding']['count'])")     # manifest sharding.count (초안 3, 상한 3)
COMMON="--prereg $P --run-root $RUNT --mode training --noise off --batch-size 20 --max-batches 1000 \
  --deadline-utc $DEADLINE --recording-check $RUNC/recording-check.json --run-manifest $M \
  --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter --poll-s 30"
for i in $(seq 0 $((K-1))); do
  nohup python $COL/scripts/run_pairact_collect.py collect $COMMON --episode-cmd "$EP" --shard $i/$K --vm gcp6 \
    > $RUNT/logs/shard-$i.log 2>&1 &
  [ $i -eq 0 ] && sleep 300      # [확인 필요] warp kernel cache 동시 컴파일 충돌 회피: shard 0의 첫 batch 시작 뒤 나머지
done
wait
python $COL/scripts/run_pairact_collect.py merge --prereg $P --run-root $RUNT --shards $K     # -> $RUNT/merged/
```
- K는 1-2b에서 이미 정했습니다. 첫 밤 첫 batch에서는 샤드별 `summary.json`의 `wall_s`·`host_loop_s.world_ticks`로 1-6c의 `s_wt`를 다시 재서 1-2b 값과 비교만 합니다(K는 바꾸지 않습니다. 호스트가 버티지 못하면 STOP_HOST 경로로 멈추고 보고). GPU 메모리(`nvidia-smi`)와 CPU 사용률을 같이 적습니다.
- 각 샤드 프로세스의 runner가 시작 전에 stage final gate를 다시 돌립니다: `--shard i/K`의 K == `sharding.count`, i ∈ `assignment[--vm]`, `--recording-check` 세 파일 해시 == `recording_check`(primary VM). 직렬(`--shard` 없음) 학습은 `count` 1일 때만 됩니다.

#### 1-6b. 두 VM 동시 실행 (gcp6 shard 0–1, gcp2 shard 2; `count` 3 — K 상한 3이라 두 VM 이득은 작음)
두 VM은 *원장만* 주고받습니다. run root·`$SRC`·`$COL`·자산 경로는 두 VM에서 같은 절대경로여야 합니다(episode 명령 sha256이 같아야 header가 같음).
```bash
# (FROZEN_CORE, gcp2에서) ①–④: gcp2 자기 probe — teacher recording check가 기계에 묶이기 때문
RUNC_B=/home/ugrp/ugrp-sim/runs/pairact-p3-probesrc-gcp2-$(date -u +%Y%m%dT%H%M); mkdir -p $RUNC_B
#   1-4의 ①–④를 RUNC 대신 RUNC_B로 gcp2에서 그대로 실행 (probe source 수율은 따로 보고, 합산 없음)
#   그 다음 gcp6에서 1-5 final에 --vm-recording-dir gcp2=$RUNC_B (RUNC_B 세 파일을 gcp6로 복사한 경로)
# (FROZEN, 양쪽) 학습 샤드
#   gcp6: for i in 0 1: collect $COMMON --episode-cmd "$EP" --shard $i/3 --vm gcp6 --recording-check $RUNC/recording-check.json
#   gcp2: for i in 2: collect $COMMON --episode-cmd "$EP" --shard $i/3 --vm gcp2 --recording-check $RUNC_B/recording-check.json
# 원장 동기화 (gcp6에서, 1분마다; 자기 샤드 원장은 절대 덮지 않음)
while sleep 60; do
  for i in 2; do rsync -a gcp2:$RUNT/shards/s0$i/ledger.jsonl $RUNT/shards/s0$i/ 2>/dev/null; done
  for i in 0 1; do rsync -a $RUNT/shards/s0$i/ledger.jsonl gcp2:$RUNT/shards/s0$i/; done
done
# 끝나면 gcp2 샤드 디렉터리 전체(raw 포함)를 같은 절대경로로 gcp6에 복사한 뒤 merge
for i in 2; do rsync -a gcp2:$RUNT/shards/s0$i/ $RUNT/shards/s0$i/; done
python $COL/scripts/run_pairact_collect.py merge --prereg $P --run-root $RUNT --shards 3
```
- rsync는 임시 파일 뒤 교체라 읽는 쪽은 통째로 바뀐 파일을 봅니다. 마지막 줄이 newline으로 끝나지 않으면(유효 JSON이라도) 확정 전이라 읽기·merge 봉인에서 빠집니다(v5). 동기화가 늦으면 샤드는 기다릴 뿐 결과는 바뀌지 않습니다(테스트 `test_two_vms_with_ledger_sync_equal_one_vm`). VM 사이 ssh 경로·키는 [확인 필요].
- 두 VM의 L4·드라이버·warp/mujoco 버전이 다르면 `host` 칸(primary만 기록)과 맞지 않습니다. gcp2 버전을 RUNBOOK_VENV 검사로 같게 맞춘 뒤 시작합니다(root가 시작 시 버전 고정 검사, fail closed).

#### 1-6c. 예상 시간
```
T_wall ≈ N_attempt × L_tick × s_wt ÷ P   (+ validation 20 × L_tick × s_wt ÷ P)
  N_attempt = 시도 수 (상한 600; STOP_TARGET이 먼저면 ≈ 200 / 채택률)
  L_tick    = 에피소드 평균 tick 수 (≈ 1,200 = 120 SIM s, tick 0.1 s; 성공은 운반 끝까지라 길고 파지 실패는 짧음)
  s_wt      = world·tick당 wall (초기값 0.34 s: -c4 20 world 6.8 s/tick ÷ 20)
  P         = 동시 프로세스 수 (= K; 두 VM이면 합)
측정값으로 갱신: s_wt = Σ(batch summary.json wall_s) / Σ(host_loop_s.world_ticks)   (샤드별·VM별로 따로)
  python -c "import json,glob;r=[json.load(open(f)) for f in glob.glob('$RUNT/shards/*/batches/*/try-*/summary.json')];r=[x for x in r if 'worlds' in x and x.get('host_loop_s')];print(sum(x['wall_s'] for x in r)/sum(x['host_loop_s']['world_ticks'] for x in r))"
  L_tick 갱신: 원장 attempt 행 sim_s 평균 ÷ 0.1
```
예(초기값): 600 × 1,200 × 0.34 s = 244,800 s ≈ 68 h(1 프로세스) → K=2 34 h, K=3 22.7 h(상한, D-v4-1). 오프피크 8 h/밤 기준 K=3은 약 2.8밤입니다(validation 20 × 1,200 × 0.34 s ≈ 2.3 h ÷ P, K=3이면 약 0.8 h 추가). 동시 실행으로 프로세스당 `s_wt`가 커지면(CPU 8 vCPU 경합) 측정값으로 다시 계산합니다. 처리량은 `P ÷ s_wt(P)`이므로 `K ÷ s_wt(K) > (K−1) ÷ s_wt(K−1)`일 때만 K를 늘립니다(v3s의 `s_wt × P` 기준은 식과 맞지 않아 고쳤습니다, Codex other note). K는 1-2b에서 FROZEN_CORE 전에 정합니다.

### 1-7. 볼 것과 보고
```bash
python $COL/scripts/run_pairact_collect.py merge --prereg $P --run-root $RUNT --shards $K    # 샤드 원장 → $RUNT/merged/{ledger.jsonl,report.json,merge.json}
python $COL/scripts/run_pairact_collect.py report --prereg $P --run-root $RUNT/merged     # 같은 파일 sha256 또는 같은 내용(status 제외)이어야 함
```
- merge는 언제든 다시 돌려도 됩니다(파생 파일을 새로 씀, 샤드 원장이 원본). `merge.json`의 `finished`(run_end 있고 계획된 batch가 모두 끝남), `running`, 샤드 원장 sha256을 보고에 적습니다. 보고에는 K와 VM 배정을 적습니다(K>1이면 구간 배정이 최대 K−1 batch 늦은 집계를 읽음, 제한될 구간이 최대 약 (K−1)×batch 시도를 더 받을 수 있음 — prereg `sharding.what_changes_vs_serial`). merged root의 `report`는 `merge.json`의 `sharding` 블록을 유지합니다. 샤드 run root 자체(`$RUNT`)에 report·convert-input을 돌리면 거부합니다. merge는 샤드 원장이 이전 merge가 본 확정 prefix의 append-only 연장이 아니거나(잘못된 방향 rsync) seed가 두 번 새로 계획됐거나 완료 attempt가 중복되면(v5) 거부합니다. 원장의 `train_barrier`(hold/release)·`train_closed` 행(경계 번호·A·N)을 보고에 적습니다.
- `report.json`: `purpose`·`freeze_stage`·`core_sha256`, `A.text`(그대로 인용: 물리 성공 S/시도 N, 최종 채택 A/시도 N), `A.bins`(구간별 N·S·A·성공률·need·환경 실패·생성기 거부·구간 범위 제한·운반 실패 하위 사유), `A.by_seed_phase`, `validation.text`(S/20·A/20), `ks`(세 그룹, pair 단위), `distance_gate`, `decision`, `run_state`.
- 생성기 거부 행(`setup_rejected`): 관문별 누적 통과·거부, 막은 물체 이름(정적 장애물 id·cargo id·`bounds`·`beam_1`·`peer_robot`·인증 stance 차단자), 관문별 최소 틈 또는 `not_measured`, 생성기 SHA·파일 sha256, 절대경로 재현 명령(`collect_cases.py --slot-json ... --stdout`).
- 보고 표기: n/200은 쓰지 않습니다. pilot·probe source는 "수율 측정, 시연 아님"입니다. B(교사 관문 n/40), C(학습 n/20)와 섞지 않습니다.
- 멈춤·판정(사전 등록 `stop_rules`·`training_decision`): STOP_RECORD, STOP_HOST, STOP_DISTANCE, STOP_TARGET, STOP_ALL_BINS_LIMITED, STOP_CAP(시도 600), STOP_SEEDS. 판정 4단계: TRAIN / TRAIN_DATA_RANGE_LIMITED / TRAIN_SMALL_DATA(80≤A<150) / NO_TRAIN_BELOW_FLOOR(A<80) 및 NO_TRAIN_DISTANCE_GATE / NO_TRAIN_VALIDATION_INSUFFICIENT / NO_TRAIN_RECORD_ERROR. MAX_BATCHES·DEADLINE은 다음 밤 같은 명령으로 이어갑니다.
- DART 노이즈는 기본 off입니다.

### 1-8. 변환 입력 (판정 TRAIN·TRAIN_DATA_RANGE_LIMITED·TRAIN_SMALL_DATA, validation 끝난 뒤)
```bash
python $COL/scripts/run_pairact_collect.py convert-input --prereg $P --run-root $RUNT/merged --run-manifest $M \
  --recording-check $RUNC/recording-check.json --teacher-sha $TEACHER_C5 --out $RUNT/convert-input
# -> seed-<seed>/{SOURCE_SHA,EXIT,raw -> 원본 world raw symlink} + protocol.json(core_sha256, decision, data_range_limited, small_data, result_labels)
```
FROZEN 학습 원장이 아니거나(pilot·probe source 포함) core_sha256이 다르거나 판정이 학습 불가면 runner가 거부합니다. v4: merged root만 받고, `merge.json`의 `finished`가 true이고 `running`이 비어 있으며 merged 원장 sha256이 `merge.json`과 같아야 합니다. 채택 world raw 디렉터리가 이 VM에 하나라도 없으면(두 VM에서 raw 복사 누락) 거부합니다. 결과 표기(`result_labels`)에 `거리 관문 축소(...)`가 붙을 수 있습니다. [확인 필요] world result.json의 `source_sha`가 teacher -c3 SHA인지 첫 배치에서 확인합니다.

### 1-9. gcp6 준비·동결 실행 순서 (2026-10-22 DeepSeek 추가, 미커밋 문서)

> 이 절은 동결 후보 `99c877e00`을 바꾸지 않는 **문서 추가**입니다. 커밋 Y는 prereg·manifest 두 JSON만 `git add` 하고 이 RUNBOOK은 함께 add하지 않습니다.
> `gcp6`는 팀장 SSH 답 전까지 시작·접속하지 않습니다. 아래는 답 후 바로 실행할 순서입니다.
> 근거: `outputs/reports/pairact-r1-frozen-candidate-20261022/FROZEN_CANDIDATE_CHECKLIST.md`.

0) 접속·신원
```bash
gcloud compute ssh ugrp-act-l4-gcp6 --account=kcm5781kcm5781@gmail.com --project=ugrp-sim-f-1016 --zone=asia-northeast3-a
hostname; nvidia-smi -L; id -un        # 실행 사용자 확인 (gcp2는 ubuntu → sudo -u ugrp)
```

1) 체크아웃 (gcp6)
```bash
REPO=/home/ugrp/ugrp-sim/ugrp          # [확인 필요]
SRC=/home/ugrp/ugrp-sim/src/pairact-p3c5
COL=/home/ugrp/ugrp-sim/src/pairact-r1v9
for t in teacher:75929e7719ad98a089e3dda5251f4249d8bae511 \
         adapter:3779d9615ef6dc8e38f57ab968a14a9e45189ecc \
         root:a93082c343ef5f3687851bf4b0c9fb0f2484ada1; do
  git -C $REPO worktree add --detach $SRC/${t%%:*} ${t#*:}
done
git -C $REPO worktree add --detach $COL 99c877e005ef6826b07cbd273c9cb0031598e364
for r in teacher adapter root; do
  echo "$r $(git -C $SRC/$r rev-parse HEAD) dirty=$(git -C $SRC/$r status --porcelain --untracked-files=no | wc -l)"
done
git -C $COL rev-parse HEAD                          # 99c877e00…
git -C $COL status --porcelain --untracked-files=no # 비어 있어야 함(이 RUNBOOK 편집은 커밋하지 않음)
```
기대: teacher `75929e77…`, adapter `3779d961…`, root `a93082c3…`, dirty 0.

2) python 고정 (1-1의 `PY=$(command -v python)`를 대체)
```bash
PY=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python   # gcp6 2026-10-21 실제 사용 경로
test -x $PY && $PY -c "import warp,mujoco; print(warp.__version__, mujoco.__version__)"
# 기대 1.15.0 3.16.0 (gcp2는 /home/ugrp/ugrp-sim/clone-20261021-oracle/.venv-warp, 3.12.3/1.15.0/3.16.0)
```
`PY`가 달라지면 `command.episode_template_sha256`이 달라져 header가 갈라집니다(`/usr/bin/python3`이면 `1e0adaa0…`). 절대경로로 고정하고 `host.python`에 기록합니다.

3) wrapper·호스트 모듈 설치 (1회)
```bash
mkdir -p /home/ugrp/ugrp-sim/src/beamact5-tools
cp $COL/experiments/2026-10-17-beamact5/teacher/run_warp_flow_teacher_gcp6.py \
   $COL/experiments/2026-10-17-beamact5/teacher/gcp6_host.py \
   /home/ugrp/ugrp-sim/src/beamact5-tools/
sha256sum /home/ugrp/ugrp-sim/src/beamact5-tools/*.py
readlink -f /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py
```
기대: wrapper `b5f12c9898a18871aec1a3f20ff87d10a45083abb3dc10600cd40d29cf015194`, host `b009e3f32df2b69d2b56f0e081356d0823b3427a0a1680507aa3ba37d6283ff3`, readlink = 같은 절대경로.
gcp2에는 `beamact5-tools/`가 **없습니다**(2026-10-22 확인). 두 VM이면 gcp2에도 같은 복사·해시가 필요합니다.

4) 셸 환경
```bash
unset PYTHONPATH PYTHONHOME
env | grep -E '^(PYTHONPATH|PYTHONHOME)=' || true    # 출력 없음
```

5) canonical 디렉터리 = episode cwd (핵심)
```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-p3c5
XML=/home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml
grep -o '<compiler[^>]*>' "$XML"
ls -ld "$(dirname "$XML")/sim/assets" 2>&1
# 없으면 1회만 (XML 파일은 바꾸지 않음):
test -e "$(dirname "$XML")/sim" || ln -s "$SRC/root/sim" "$(dirname "$XML")/sim"
```
teacher는 `mujoco.MjModel.from_xml_string`으로 컴파일하므로 `texturedir`가 상대경로면 **에피소드 cwd** 기준으로 자산을 읽습니다. `xml-assets`/`core --verify-assets`도 XML 디렉터리 기준이므로, 수집·동결 명령은 모두 `cd "$(dirname "$XML")"`에서 실행합니다(에피소드 cwd = XML 디렉터리).

6) 자산 해시 (VM 기입)
```bash
cd "$(dirname "$XML")"
PREP=/home/ugrp/ugrp-sim/runs/pairact-r1-prep; mkdir -p $PREP
$PY $COL/scripts/pairact_r1_freeze.py xml-assets --canonical-xml "$XML" > $PREP/xml-assets.json
$PY $COL/scripts/pairact_r1_freeze.py per-world-refs \
  --refs /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json > $PREP/per-world-refs.json
sha256sum "$XML" \
  /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json \
  /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json
```
`xml-assets.json`이 38개(텍스처 37 + mesh 1)인지 확인합니다. gcp2 복사본 기준 38/38, 내용 해시는 `outputs/reports/pairact-r1-frozen-candidate-20261022/ASSETS_PREFILL.json`.

7) smoke·seed-check (기존 증거 해시)
```bash
S=/home/ugrp/ugrp-sim/runs/pairact-p2/smoke-1c
sha256sum $S/summary.json $S/artifact-sha256.json $S/world-000/raw/result.json* \
  $S/world-00{0,1,2}/raw/carry-eval.json
sha256sum <pilot run root>/seed-check.json
```

8) manifest 채우기·FROZEN_CORE
- 채울 칸: prereg.core(계산) 포함 23칸, 그중 VM 기입 22칸(collector 1 + command 2 + assets 6 + host 5 + smoke 4 + recording_check 3 + seed_check 1).
- DeepSeek 사전 채움(로컬, 커밋 금지): `collector.source_sha=99c877e00…`, `command.episode_template`/`sha256=bb98474c63119dc48b57c6e7e097ae3cc27aabc8468e7c76d82769e21087716a`, `assets.wrapper_sha256=b5f12c98…`. 나머지는 VM 출력. `$PREP/xml-assets.json`의 키/값을 `assets.mesh_assets_sha256`에 그대로 넣습니다(키는 cwd 기준 절대경로).
- K(샤드 수)는 1-2b 측정 전에는 FROZEN_CORE로 가지 않습니다. 초안 `count=3`, `assignment={"gcp6":[0,1,2]}`, `primary_vm=gcp6`.
```bash
cd "$(dirname "$XML")"          # 5)의 cwd 유지
$PY $COL/scripts/pairact_r1_freeze.py core \
  --collector-sha 99c877e005ef6826b07cbd273c9cb0031598e364 --verify-assets
# -> core_sha256 기록
git -C $COL add experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json \
  experiments/2026-10-21-pairact-r1/RUN_MANIFEST.json      # 이 RUNBOOK 제외
git -C $COL commit -m "pairact-r1 FROZEN_CORE <core_sha256>"
```
그 다음 1-4: probe source → `probe-cases` → `probe-episode` → `check-rows` → recording-check. **v9 이전 probe raw는 재사용하지 않습니다**(재실행).

9) 정지·비용
- 수집 중 wrapper·`gcp6_host.py`·세 체크아웃·venv(pip install)·canonical XML·mesh·rejection table·기록 디렉터리 수정 금지.
- `--no-verify-assets` 금지(probe-episode·convert-input·FROZEN 수집).
- 끝나면 lease 삭제 → 프로세스 0·GPU 0 → `gcloud compute instances stop` → `describe`로 TERMINATED 확인.

## 2. 변환 + stage sidecar (CPU)
```
# protocol: train_seeds=성공 train seed, validation_seeds=성공 validation seed (heldout 금지)
python -c "from harness.grasp_act_data import convert; import json; convert('$RUNT/convert-input', json.load(open('$RUNT/convert-input/protocol.json')), 'datasets/pairact-r1-<TS>')"
python scripts/build_pairact_r1_stage_targets.py --dataset datasets/pairact-r1-<TS> --output datasets/pairact-r1-<TS>-stage
```
`missing_stages`에 approach·alignment·ready·execute·carry·place·complete 중 하나라도 있으면 멈추고 보고합니다. recover는 teacher 시연에 없을 수 있습니다.

## 3. P4 학습 (gcp2 L4, 학습 4.6 GPU-h 예산)
```
CFG=experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json
ST=datasets/pairact-r1-<TS>-stage/stage-targets.json
COMMON="--dataset datasets/pairact-r1-<TS> --seed 20261020 --beamact3-v1 A --done-loss balanced_bce_v1 \
  --execution-host-profile beamact1_gcp2 --pairact-r1-config $CFG --pairact-r1-stage-targets $ST"
# smoke
python scripts/train_grasp_act.py $COMMON --output runs/pairact-carry-r1-<TS>/smoke --stage smoke --steps 300 --max-wall-s 1800
# approval.json: approved=true, stage=main, source_sha, dataset_manifest_sha256, smoke_summary_sha256,
#   steps=20000, blank_images=false, gate_promotion_authorized_if_all_conditions_pass=false, beamact3_v1="A",
#   pairact_r1_config_sha256, pairact_r1_stage_targets_sha256  (Claude 본체 승인 후 작성)
python scripts/train_grasp_act.py $COMMON --output runs/pairact-carry-r1-<TS>/main --stage main --steps 20000 \
  --checkpoint-every 1000 --max-wall-s 25200 --smoke-summary runs/pairact-carry-r1-<TS>/smoke/summary.json \
  --approval runs/pairact-carry-r1-<TS>/approval.json --profile-timing
# WALL_CAP이면: 같은 명령에 --resume runs/pairact-carry-r1-<TS>/main/step-<마지막>
```
`--profile-timing`으로 step 시간 실측을 남깁니다. GPU-h 실측은 STATUS에 적습니다.

## 4. 오프라인 gate + 선택 (gcp2, 0.5–1.5 GPU-h [확인 필요])
```
python scripts/pairact_r1_offline.py --run runs/pairact-carry-r1-<TS>/main --dataset datasets/pairact-r1-<TS> \
  --stage-targets $ST --output runs/pairact-carry-r1-<TS>/offline
```
`selection.json`의 verdict가 `NOT_READY_NO_CHECKPOINT_PASSES`이면 P5를 돌리지 않고 보고합니다.

## 5. P5 (보류 20 seed, 학생·teacher 같은 seed)
`PAIRACT_R1_EVAL_PREREG_DRAFT.json`의 [확인 필요] 항목(에피소드 cap)을 채워 커밋한 뒤에 실행합니다. 체크포인트 SHA를 커밋한 뒤 보류 20 seed에 규칙 A 정적 검사를 적용하고, 제외 seed 목록을 커밋한 다음에만 rollout합니다(제외 seed는 분모에서 빼고 대체하지 않음). 그 전에는 heldout 결과를 만들거나 읽지 않습니다. 평가 runner는 P2 evaluator와 PairActBarrier 연결이 필요하고, 아직 구현되지 않았습니다(남은 일).
