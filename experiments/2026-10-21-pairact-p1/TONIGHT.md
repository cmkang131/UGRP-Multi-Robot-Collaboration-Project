# pairact P1: gcp6 실행 문서 (DeepSeek용, 오프피크 UTC 16:30–00:30)

관문 tournament(4 arm)와 확인 run(2 arm)을 돌립니다. VM은 gcp6(`ugrp-act-l4-gcp6`)만 쓰고, P0 실행과 겹치지 않게 *순서대로* 진행합니다. 원본 결과는 VM에 보존하고, 출력은 항상 새 디렉터리에 씁니다.

## 0. DeepSeek가 먼저 채울 칸 — 2026-10-20 실행으로 확인함

| 항목 | 확인된 값 |
|---|---|
| `REPO` gcp6 레포 clone 경로 | `/home/ugrp/ugrp-sim/src/nav-v230-r5-219d0877` (remote `https://github.com/kcm0127-dotcom/ugrp.git` = 이 레포와 같은 URL, `git fetch origin dsh/pairact-p0-diag` → `3ca10e122` 성공, 2026-10-20). 그 clone의 worktree로 `src/pairact-{root-05046e9d,adapter-d354468a,teacher-fe6858ec}`가 붙어 있습니다. **`/home/ugrp/ugrp-sim/ugrp`은 git 저장소가 아닙니다**(`.venv-sim`·`.venv-warp`만 있는 디렉터리, `git remote -v`는 `fatal: not a git repository`) |
| r13 adapter/teacher 디렉터리 | 기본값 `src/26f84d0f…`=HEAD `f1cf1926b`, `src/835ccef2…`=HEAD `d4398363e`(둘 다 dirty 0, 오래된 체크아웃) → **원하는 값이 아닙니다.** 실행할 때 `R13_TEACHER_DIR=$SRC/pairact-teacher-fe6858ec`(HEAD `fe6858ec`), `R13_ADAPTER_DIR=$SRC/pairact-adapter-d354468a`(HEAD `d354468a`)로 덮어씁니다. static 실행에서 teacher HEAD `fe6858ec`를 출력으로 확인했습니다 |
| r13 cases 생성 인자 | 아래 §0.1 명령. `--dependency-root`=teacher `fe6858ec`, `--frozen-root`=`src/beamact5-teacher-3170d909`, `--candidate beamact5_r13`, `--no-setup-validity` **없음**. 이 조합으로 `wide-cases.json`을 다시 만들면 `wide-cases-r13.json`과 **byte-identical**(sha256 `3d4e065d…`)이 나옵니다. `-d`=seed 8420000의 4번째 setup 변형(`wide-start-8420000`, `b`, `c`, `d`), `-r4`=round 4부터의 케이스 보관 디렉터리이고 그 안의 `wide-pre-registration.json`·`wide-setup-funnel.json`은 `-r2`와 byte-identical 복사본(`ea37daaa…`/`7d1554e8…`, `reproduce`가 `-r2`를 가리킴)입니다. 케이스 파일 19개는 모두 base world set + `candidate` 라벨만 다릅니다(후처리 없이 `--candidate`로 생성) |
| 새 world용 xml / refs / rejection table | 아래 §0.1 명령으로 seed 9420000 산출물을 실제로 만들었습니다(§0.2 경로·sha). `gate-40-r13/rejection_table.json`은 **생성물이 아니라** gate r2 때 만든 표(`gate_id beamact5-teacher-gate-r2`, `raw gate-run-40-r1`)를 r13 입력으로 복사해 둔 것입니다. 새 seed에는 새 `wide-setup-funnel.json`을 `--rejection-table`로 주면 되고(이번에 그렇게 실행), r13 표를 그대로 재사용해도 문법상 유효합니다 |

### 0.1 확인된 명령 (gcp6, 2026-10-20)

```bash
SRC=/home/ugrp/ugrp-sim/src
PYW=$SRC/../ugrp/.venv-warp/bin/python      # warp 1.15.0 + mujoco 3.16.0
PYS=$SRC/../ugrp/.venv-sim/bin/python       # mujoco 3.12.0 (xml export·refs 전용)
# (a) cases. cwd·PYTHONPATH는 adapter 트리여야 합니다(harness/scripts/scenario-v7.json이 거기 있음).
cd $SRC/pairact-adapter-d354468a
PYTHONPATH=$PWD $PYW $SRC/beamact5-tools/wide_start.py --seed 8420000 --output <새 디렉터리> \
  --dependency-root $SRC/pairact-teacher-fe6858ec --frozen-root $SRC/beamact5-teacher-3170d909 \
  --candidate beamact5_r13
# (b) canonical xml (r13 export와 같은 명령, --canonical-xml 없이 새로 만듦)
cd $SRC/pairact-root-05046e9d
WARP_SOURCE_ROOT=$PWD $PYS $SRC/beamact5-tools/run_warp_flow_teacher_gcp6.py --flow beampair \
  --adapter-source $SRC/pairact-adapter-d354468a --teacher-source $SRC/pairact-teacher-fe6858ec \
  --cases <cases.json> --indices 0,1,…,39 --cap-s 60 --out <새 xml 디렉터리> --vm-hourly-usd 1.096 \
  --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1 \
  --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --export-compiled-only \
  --rejection-table <cases를 만든 wide-setup-funnel.json>
# (c) refs
cd $SRC/beamact5-teacher-3170d909
$PYS $SRC/beamact5-tools/prepare_native_references_gcp6.py --source $SRC/beamact5-teacher-3170d909 \
  --old-export <b의 출력> --out <새 refs 디렉터리>
```

### 0.2 seed 9420000 산출물 (2026-10-20 실행, 원본 불변·새 디렉터리)

| 산출물 | 경로 | sha256 |
|---|---|---|
| cases (40, seeds 9420000–9420039, proposals 109 / rejections 72) | `runs/beamact5/wide-start-9420000/wide-cases.json` | `70fa2e653aec4708f0ed04da70a98c2f082001c446eeaa5ec73663f8808f1ccd` |
| canonical xml (40 world, 316.95 s, physics 없음, status `initialization_only`) | `runs/beamact5/wide-export-old-9420000e/canonical-scene.xml` | `aa0c3efbb5dce2765500dbee72ad8177e0e86f672db57768c89c2af5bbf813fb` |
| refs (`compiled_N` 40, `arrays_exact` true, `physics_steps` 0) | `runs/beamact5/native-refs-9420000e/per-world-references.json` | `0c849f6a9c5ec6b2143b0d38768507c212fc4e2d8b7489e5ca4a0225cb0a2ffa` |
| rejection table로 쓴 setup funnel | `runs/beamact5/wide-start-9420000/wide-setup-funnel.json` | `00b1f8a853fe3a66b27a0071bd7ec954a1d400f41c0169d66ef8019ea37235ae` |
| seed 겹침 검사 | 8328xxx=8328000–8328999, 8420000 계열 rng 8420000–8810049, 9420000 계열 rng 9420000–9810049 | 겹침 없음 |

- 9420000 계열은 아직 **gate run을 돌리지 않았습니다**(tournament `run`·`confirm` 금지). `static-confirm`도 winner가 정해진 뒤에 합니다.

## 1. 파일 준비
```bash
export REPO=/home/ugrp/ugrp-sim/src/nav-v230-r5-219d0877   # §0 확인값 (run_p1.sh 기본값도 이 경로)
cd /home/ugrp/ugrp-sim && git -C "$REPO" fetch origin dsh/pairact-p0-diag
mkdir -p ops-reviews/pairact-p1
for f in 2026-10-21-pairact-p1/run_p1.sh 2026-10-21-pairact-p1/make_arm_cases.py 2026-10-21-pairact-p1/p1_gate.py \
         2026-10-21-pairact-p1/PAIRACT_P1_PREREG_DRAFT.json 2026-10-21-pairact-p0/static_stance_check.py; do
  git -C "$REPO" show origin/dsh/pairact-p0-diag:experiments/$f > ops-reviews/pairact-p1/$(basename $f); done
bash ops-reviews/pairact-p1/run_p1.sh plan     # fetch 3개 후보 묶음 + 새 SHA worktree 명령 출력 + preflight
```
- `plan`은 명령만 출력합니다. preflight는 arm별 root/adapter/teacher HEAD를 원하는 SHA와 비교하고, 결과를 `preflight.txt`에 남깁니다.
- 2026-10-20 확인: `plan`에서 r13 root/adapter/teacher는 `ok`(05046e9d / d354468a / fe6858ec)입니다. c1·c2b·c3는 `run`/`confirm` 때 `prepare`가 worktree를 만들기 전까지 `MISSING`이고, plan 모드에서는 경고만 냅니다(EXEC 모드에서는 fatal).

## 2. 정적 검사 (규칙 A, CPU 수 초, 피크 시간에도 가능)
```bash
bash ops-reviews/pairact-p1/run_p1.sh static   # 출력 runs/pairact-p1/static-tournament-<UTC>.json
```
- 출력의 `RULE_A excluded_worlds = [...]`와 sha256 두 줄을 `PAIRACT_P1_PREREG_DRAFT.json`의 `static_exclusion.tournament`에 적고 커밋합니다. 적을 칸은 `excluded_worlds`, `output_path`, `output_sha256`, `cases_sha256`입니다. 제외가 없으면 `[]`로 적습니다.
- 규칙 B(`flagged['floor']`)와 admission 값도 출력에 함께 나오지만 제외에 쓰지 않습니다(D2).
- 그다음 Codex 검토를 받습니다. 검토가 끝나면 Claude가 `status=FROZEN`으로 커밋하고, DeepSeek는 그 커밋의 사전 등록 파일을 다시 복사합니다.

## 3. tournament (FROZEN 뒤에만, 약 2.9 h)
```bash
bash ops-reviews/pairact-p1/run_p1.sh run      # r13 → c1 → c2b → c3, 출력 runs/pairact-p1/tournament-<UTC>/
```
- `run`은 사전 등록이 FROZEN이 아니거나 `excluded_worlds`가 비어 있으면(null) 시작하지 않습니다. 2026-10-20 static 결과는 `excluded_worlds: []`(N_eff 40, need 38)로 이미 기입돼 있어, 남은 조건은 `status=FROZEN` 하나입니다.
- `--indices`는 `p1_gate.py`가 계산합니다. 0–39에서 15와 정적 제외 world를 뺀 값입니다.
- 끝나면 `tournament-raw.json`에 arm별 n/40, n/N_eff, need, adopt가 기록됩니다.
- 중간에 끊기면 `ARMS="c2b c3" bash … run`처럼 남은 arm만 다시 돌리고, 그 사실을 보고합니다.

## 4. 확인 run (winner가 있을 때만, 약 1.5 h, 다음 오프피크로 미뤄도 됨)
1. 새 world 산출물은 **이미 만들어져 있습니다**(§0.2). 다시 생성하지 마세요 — `wide_start.py`는 같은 출력 디렉터리에 재생성하면 거부하고, 새 디렉터리에 만들면 cases sha가 달라져 §0.2 기록과 어긋납니다.
2. seed 겹침 검사는 §0.2 표에 기록했습니다(8328xxx / 8420000 계열 / 9420000 계열, 겹침 없음).
3. 정적 검사를 실행합니다.
   ```bash
   CONF_CASES0=/home/ugrp/ugrp-sim/runs/beamact5/wide-start-9420000/wide-cases.json \
     bash ops-reviews/pairact-p1/run_p1.sh static-confirm
   ```
   결과를 `static_exclusion.confirmation`에 적고 커밋합니다. 이 두 칸 말고는 아무것도 바꾸지 않습니다.
4. 확인 run을 실행합니다(§0.2 산출물 사용).
   ```bash
   WINNER=<c1|c2b|c3> \
   CONF_CASES0=/home/ugrp/ugrp-sim/runs/beamact5/wide-start-9420000/wide-cases.json \
   CONF_XML=/home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-9420000e/canonical-scene.xml \
   CONF_REFS=/home/ugrp/ugrp-sim/runs/beamact5/native-refs-9420000e/per-world-references.json \
   CONF_REJ=/home/ugrp/ugrp-sim/runs/beamact5/wide-start-9420000/wide-setup-funnel.json \
     bash ops-reviews/pairact-p1/run_p1.sh confirm
   ```
   r13 → winner 순서로 돌고, 출력은 `runs/pairact-p1/confirmation-<UTC>/`입니다.
- winner는 사전 등록 `adoption.winner` 규칙으로 정합니다. 동률일 때는 world 27 통과 arm을 고르고, 그래도 같으면 c3 → c1 → c2b 순서입니다.

## 5. 회수
- 회수 대상: `preflight.txt`, `static-*.json`, `cases.jsonl`, `arms.tsv`, `tournament-raw.json`, arm별 `summary.json`, `<arm>.log`의 마지막 200줄
- c2b 진단: summary에 들어 있는 teacher 로그에서 `align_refresh2_begin`과 `align_refresh2_skip`(사유별), `reobserve_end` reason 개수를 셉니다
- 실행 중인 프로세스가 없는지 `nvidia-smi`로 확인한 뒤 VM을 정지합니다. 결과는 Claude 워커에게 전달합니다.
