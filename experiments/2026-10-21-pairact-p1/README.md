# pairact P1: MJWarp teacher 관문 후보 (2026-10-20, Claude 워커)

r13(37/40)에 후보 3개를 붙여 같은 40 world로 tournament합니다. 모든 후보는 default off이고 관문 결과는 아직 없습니다.
사전 등록은 [PAIRACT_P1_PREREG_DRAFT.json](PAIRACT_P1_PREREG_DRAFT.json)이고 상태는 **READY_FOR_REVIEW**입니다. Codex 검토 뒤 FROZEN으로 바꿉니다.
실행 순서와 DeepSeek가 채울 칸은 [TONIGHT.md](TONIGHT.md)에 있습니다.

## 오너 결정 (2026-10-20)
- **D1:** cand-2b(정렬 refresh v2)를 r13 base `fe6858ec` 위에 구현합니다. tournament는 r13 + c1 + c2b + c3, 4 arm입니다.
- **D2:** 정적 제외는 규칙 A만 씁니다. 한쪽 beam 끝의 인증 파지 자세 91개가 모두 상자와 겹치면 제외합니다. 규칙 B(11.07 mm)는 쓰지 않습니다.
- **D3:** 제외 world는 분모에서 뺍니다. 채택 기준은 통과 수 ≥ ceil(0.95 × N_eff)이고, n/40도 함께 보고합니다. 예를 들어 N_eff가 40이면 38, 39면 38, 38이면 37입니다. 제외 목록은 관문 전에 정적 검사로 확정해 사전 등록에 적습니다.
- **D4:** 확인 run(새 world 40개, seed 9420000)에서 r13도 같은 world로 함께 돌립니다.

## 후보와 스택 (모두 push됨)

| arm | teacher (base fe6858ec) | adapter pin (base d354468a) | root pin (base 05046e9d) | 변경 |
|---|---|---|---|---|
| r13 | `fe6858ec` | `d354468a` | `05046e9d` | 기준 |
| c1 | `dsh/pairact-p1-cand-1` `ee757b91` | `-1-a` `c25a616c` | `-1-r` `6360e972` | `search26_align_rect_guard_v1`: align 펄스 가드를 원형(0.13 m) 대신 185×160 mm 직사각형 sweep으로 판정 |
| c2b | `dsh/pairact-p1-cand-2b` `42fc4eec` | `-2b-a` `63c3b697` | `-2b-r` `f2fd635d` | `search26_align_refresh_v2`: 거부된 정렬 pulse의 경로에 걸린 stale 장애물로 기존 bounded reobserve 시작 |
| c3 | `dsh/pairact-p1-cand-3` `802a19a6` | `-3-a` `9b4c2910` | `-3-r` `7f8bb3c5` | `search26_align_relook_cap_v1`: relook 상한 2→4 |

- `dsh/pairact-p1-cand-2`(`685f7820`, 문서만): peer_yield는 r13에 이미 켜져 있어 arm이 없습니다. c2b가 그 자리를 대신합니다.
- adapter의 `profiles('pairact_p1cN')`는 `beamact5_r13`과 키 1개만 다릅니다(ast로 추출해 로컬에서 확인).
- 후보는 cases 파일의 `candidate` 필드로 고릅니다(root `run_warp_flow_teacher.py:198`). [make_arm_cases.py](make_arm_cases.py)가 이 필드만 바꾼 사본을 만듭니다.
- **c1 주의:** 펄스를 막던 원인이 원형 가드가 지나치게 보수적이어서인지(H27-b), stale 기억 여유 때문인지(H27-a)는 아직 가려지지 않았습니다. c1은 H27-b만 다룹니다.
- **c2b 주의:** H27-a 쪽을 다룹니다. r14 v1(`f1cf1926`)이 실패 회차에서 0회 발동한 원인을 "목표 자세만 봐서 blockers가 비었다"로 가정한 수정입니다. 다른 원인(align 전에 obstacle encounter 2회를 이미 다 씀)일 수도 있어서, `align_refresh2_skip` 로그에 `no_stale_blocker_on_pulse`와 `obstacle_encounters_spent` 중 어느 쪽인지 남깁니다. 어느 쪽인지는 [확인 필요]입니다.
- **c3 주의:** r13diag에서 relook이 stale 막힘을 풀지 못했습니다. 상한 4는 새 상수이고 효과는 불확실합니다.

## c2b 구현 요약 (`sim/grasp_act_align_refresh2.py`)
- 발동 조건: phase가 `align`이고 reobserve가 비활성이며, 제안 명령은 wheels≠0인데 모든 pulse 검사를 거친 발행 명령은 wheels=0일 때입니다. 즉 거부된 pulse에서만 발동하고, 의도한 hold에서는 발동하지 않습니다.
- 판정은 기존 `remembered_blockers`를 그대로 씁니다. stale 관측만 보고, beam_1을 빼고, 같은 반경과 패딩을 씁니다. 바뀐 것은 입력뿐입니다. 거부된 목표 자세 대신 현재 pose와 제안 pulse 경로를 2 mm 간격으로 표본화해 넣습니다(odometry `off`와 `search17` 두 모델).
- 동작은 기존 `ActiveReobserve.begin('obstacle', …)`입니다. `VIEW_S`, `RETREAT_S`, `LIMIT_S`, `MAX_ENCOUNTERS`를 그대로 쓰고 새 상수는 없습니다.

## 테스트 (로컬, mujoco 없음)
- cand-2b: `tests/test_pairact_p1_cand2b.py` 5개 + `test_beamact5_r3_modes.py` 18개 + `test_grasp_act_search15.py` 15개 통과
- cand-1: `tests/test_pairact_p1_cand1.py` 4개 + 18개 통과 / cand-3: `tests/test_pairact_p1_cand3.py` 3개 + 18개 통과
- 이 브랜치: `tests/test_pairact_p1_cases.py` 6개(make_arm_cases, p1_gate 분모·판정·FROZEN 거부) + `test_pairact_p0.py` 7개 통과
- MJWarp에서는 아직 어떤 후보도 실행하지 않았습니다.

## 실행 개요 (DeepSeek, gcp6, 오프피크): 상세는 [TONIGHT.md](TONIGHT.md)
1. `run_p1.sh static`: 규칙 A 정적 검사(CPU). 결과를 사전 등록의 `static_exclusion.tournament`에 적어 커밋합니다.
2. Codex 검토를 받고 `status=FROZEN`으로 커밋합니다.
3. `run_p1.sh run`: 4 arm을 r13 → c1 → c2b → c3 순서로 돌립니다. 약 2.9 h입니다. `p1_gate.py`가 `tournament-raw.json`에 n/40, n/N_eff, 채택 여부를 기록합니다.
4. winner가 있으면 새 world 40개를 생성하고 `static-confirm` → 기입 커밋 → `confirm`(r13 + winner, 약 1.5 h) 순서로 진행합니다.
- `REPO`(gcp6 레포 clone 경로)와 r13 cases 생성 인자는 **[확인 필요]**입니다. DeepSeek가 TONIGHT.md의 표를 채웁니다.
