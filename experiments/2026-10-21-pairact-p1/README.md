# pairact P1: MJWarp teacher 관문 후보 (2026-10-20, Claude 워커)

r13(37/40)에 후보를 붙여 같은 40 world로 tournament합니다. 모든 후보는 default off이고 관문 결과는 아직 없습니다.
사전 등록 초안은 [PAIRACT_P1_PREREG_DRAFT.json](PAIRACT_P1_PREREG_DRAFT.json)이고, 실행 전 오너 결정 D1–D4가 남아 있습니다.

## 후보와 스택 (모두 push됨)

| arm | teacher (base fe6858ec) | adapter pin (base d354468a) | root pin (base 05046e9d) | 변경 |
|---|---|---|---|---|
| r13 | `fe6858ec` | `d354468a` | `05046e9d` | 기준 |
| c1 | `dsh/pairact-p1-cand-1` `ee757b91` | `-1-a` `c25a616c` | `-1-r` `6360e972` | `search26_align_rect_guard_v1`: align 펄스 가드를 원형(0.13 m) 대신 185×160 mm 직사각형 sweep으로 판정 |
| c2 | `dsh/pairact-p1-cand-2` `685f7820` (문서만) | — | — | peer_yield는 r13에 이미 켜져 있어 이식할 것이 없음. 대체 제안 cand-2'는 오너 결정 |
| c3 | `dsh/pairact-p1-cand-3` `802a19a6` | `-3-a` `9b4c2910` | `-3-r` `7f8bb3c5` | `search26_align_relook_cap_v1`: relook 상한 2→4 |

- adapter의 `profiles('pairact_p1cN')`는 `beamact5_r13`과 키 1개만 다릅니다(ast로 추출해 로컬 확인).
- 후보 선택은 cases 파일의 `candidate` 필드로 합니다(root `run_warp_flow_teacher.py:198`). [make_arm_cases.py](make_arm_cases.py)가 이 필드만 바꾼 사본을 만듭니다.
- **c1 주의:** 펄스를 막던 원인이 원형 가드의 과잉 보수인지(H27-b), stale 기억 여유인지(H27-a)는 아직 분리되지 않았습니다. c1은 H27-b만 다룹니다.
- **c3 주의:** r13diag에서 relook이 stale 막힘을 풀지 못했습니다. 상한 4는 새 상수이고 효과는 불확실합니다.

## 테스트 (로컬, mujoco 없음)
- cand-1: `tests/test_pairact_p1_cand1.py` 4개 + `test_beamact5_r3_modes.py` 18개 통과
- cand-3: `tests/test_pairact_p1_cand3.py` 3개 + 18개 통과
- 이 브랜치: `tests/test_pairact_p1_cases.py` 2개 + `test_pairact_p0.py` 7개 통과
- MJWarp에서는 아무 후보도 아직 실행하지 않았습니다.

## 실행 (DeepSeek, gcp6, 오프피크) — 사전 등록 FROZEN 커밋 뒤에만
```bash
cd /home/ugrp/ugrp-sim && git -C ugrp fetch origin dsh/pairact-p0-diag
mkdir -p ops-reviews/pairact-p1
for f in run_p1.sh make_arm_cases.py; do
  git -C ugrp show origin/dsh/pairact-p0-diag:experiments/2026-10-21-pairact-p1/$f > ops-reviews/pairact-p1/$f; done
bash ops-reviews/pairact-p1/run_p1.sh plan   # fetch + 새 SHA worktree 명령 출력 + preflight(HEAD 일치 검사)
bash ops-reviews/pairact-p1/run_p1.sh run    # r13 → c1 → c3 순서, 출력 runs/pairact-p1/tournament-<UTC>/
```
- `REPO`(gcp6의 레포 clone 경로, 기본 `/home/ugrp/ugrp-sim/ugrp`)는 [확인 필요]입니다.
- r13 arm은 이전과 같은 옛 이름 디렉터리(`src/835ccef2…`, `src/26f84d0f…`)를 씁니다. preflight가 HEAD를 기록합니다.
- 예상 GPU 시간은 arm당 약 44 min, 합계 약 2.2 h입니다. 이후 winner 1개만 새 world 40개로 확인합니다(사전 등록 `confirmation`).
- 회수할 것: `preflight.txt`, `cases.jsonl`, `arms.tsv`, `tournament-raw.json`, arm별 `summary.json`. 원본은 VM에 보존합니다.
