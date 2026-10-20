# pairact P1: gcp6 실행 문서 (DeepSeek용, 오프피크 UTC 16:30–00:30)

관문 tournament(4 arm)와 확인 run(2 arm)을 돌립니다. VM은 gcp6(`ugrp-act-l4-gcp6`)만 쓰고, P0 실행과 겹치지 않게 *순서대로* 진행합니다. 원본 결과는 VM에 보존하고, 출력은 항상 새 디렉터리에 씁니다.

## 0. DeepSeek가 먼저 채울 칸 [확인 필요]

| 항목 | 기본값 / 현재 값 | 채울 내용 |
|---|---|---|
| `REPO` gcp6 레포 clone 경로 | `/home/ugrp/ugrp-sim/ugrp` | **[확인 필요]** `git -C <경로> remote -v`가 이 레포인지 확인합니다. 아니면 실제 경로를 적거나, clone이 없으면 아래 3개 브랜치 묶음을 fetch할 수 있는 경로를 적습니다 |
| r13 adapter/teacher 디렉터리 | `src/835ccef2…` / `src/26f84d0f…` | **[확인 필요]** preflight의 HEAD 값을 적습니다. 원하는 값은 d354468a / fe6858ec입니다 |
| r13 cases 생성 인자 (확인 run용) | `wide_start.py`(5d906886f) `--seed 8420000 --output … --dependency-root ? --frozen-root ?` | **[확인 필요]** `wide-start-8420000d-r4/`의 생성 기록(manifest, 셸 기록)에서 `--dependency-root`, `--frozen-root`, `--no-setup-validity` 사용 여부, `-d`/`-r4` 접미사의 의미, `wide-cases-r13.json`에 `candidate`를 넣은 후처리를 적습니다 |
| 새 world용 xml / refs / rejection table 생성 명령 | r13 때 `wide-export-old-8420000e`, `native-refs-8420000e`, `gate-40-r13/rejection_table.json` | **[확인 필요]** 같은 절차를 `9420000` 계열에 적용하는 명령을 적습니다 |

## 1. 파일 준비
```bash
cd /home/ugrp/ugrp-sim && git -C "$REPO" fetch origin dsh/pairact-p0-diag
mkdir -p ops-reviews/pairact-p1
for f in 2026-10-21-pairact-p1/run_p1.sh 2026-10-21-pairact-p1/make_arm_cases.py 2026-10-21-pairact-p1/p1_gate.py \
         2026-10-21-pairact-p1/PAIRACT_P1_PREREG_DRAFT.json 2026-10-21-pairact-p0/static_stance_check.py; do
  git -C "$REPO" show origin/dsh/pairact-p0-diag:experiments/$f > ops-reviews/pairact-p1/$(basename $f); done
bash ops-reviews/pairact-p1/run_p1.sh plan     # fetch 3개 후보 묶음 + 새 SHA worktree 명령 출력 + preflight
```
- `plan`은 명령만 출력합니다. preflight는 arm별 root/adapter/teacher HEAD를 원하는 SHA와 비교하고, 결과를 `preflight.txt`에 남깁니다.

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
- `run`은 사전 등록이 FROZEN이 아니거나 `excluded_worlds`가 비어 있으면(null) 시작하지 않습니다.
- `--indices`는 `p1_gate.py`가 계산합니다. 0–39에서 15와 정적 제외 world를 뺀 값입니다.
- 끝나면 `tournament-raw.json`에 arm별 n/40, n/N_eff, need, adopt가 기록됩니다.
- 중간에 끊기면 `ARMS="c2b c3" bash … run`처럼 남은 arm만 다시 돌리고, 그 사실을 보고합니다.

## 4. 확인 run (winner가 있을 때만, 약 1.5 h, 다음 오프피크로 미뤄도 됨)
1. 0번 표의 인자로 `--seed 9420000` cases를 생성하고, 새 xml, refs, rejection table을 만듭니다.
2. seed 겹침 검사를 기록합니다. 대상은 8420000–8420039, 8328xxx, 학습·검증·보류 범위입니다.
3. 정적 검사를 실행합니다.
   ```bash
   CONF_CASES0=<새 cases> bash ops-reviews/pairact-p1/run_p1.sh static-confirm
   ```
   결과를 `static_exclusion.confirmation`에 적고 커밋합니다. 이 두 칸 말고는 아무것도 바꾸지 않습니다.
4. 확인 run을 실행합니다.
   ```bash
   WINNER=<c1|c2b|c3> CONF_CASES0=… CONF_XML=… CONF_REFS=… CONF_REJ=… bash ops-reviews/pairact-p1/run_p1.sh confirm
   ```
   r13 → winner 순서로 돌고, 출력은 `runs/pairact-p1/confirmation-<UTC>/`입니다.
- winner는 사전 등록 `adoption.winner` 규칙으로 정합니다. 동률일 때는 world 27 통과 arm을 고르고, 그래도 같으면 c3 → c1 → c2b 순서입니다.

## 5. 회수
- 회수 대상: `preflight.txt`, `static-*.json`, `cases.jsonl`, `arms.tsv`, `tournament-raw.json`, arm별 `summary.json`, `<arm>.log`의 마지막 200줄
- c2b 진단: summary에 들어 있는 teacher 로그에서 `align_refresh2_begin`과 `align_refresh2_skip`(사유별), `reobserve_end` reason 개수를 셉니다
- 실행 중인 프로세스가 없는지 `nvidia-smi`로 확인한 뒤 VM을 정지합니다. 결과는 Claude 워커에게 전달합니다.
