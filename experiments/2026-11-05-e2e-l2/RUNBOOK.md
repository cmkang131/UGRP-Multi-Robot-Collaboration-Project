# L2 E2E: LLM 역할 배정 → 학습 공동 운반 (기본 off, 실행 전 초안 v2)

목적: 11/5 데모 A등급(aggressive-replan-1105.md §6). 두 로봇의 LLM이 *주문서 + 자기 카메라 첫 프레임 + 조건별 수신 메시지*만 보고 협력 필요 여부와 맡을 끝(teal band / blue band)을 4조건 채널로 정합니다. 그 결과를 학습 공동 운반 정책의 번호표(role 토큰)로 넘겨 MJWarp에서 실행합니다. 사전 등록 초안은 `E2E_L2_PREREG_DRAFT.json`입니다.

## v2 변경 (오너 검토 10/21)
- seed: 8343000–039는 pairact-r1 v2 pilot(`bcfefaadc`)이라 L2는 *8344000–8344099*로 옮겼습니다. `seeds.json` + `scripts/check_e2e_l2_seeds.py`로 겹침 0을 테스트에 고정했습니다.
- GT 누출 제거: plan 좌표로 계산한 거리 입력을 없앴습니다. plan 좌표는 evaluator(`geometry_record`)에서만 씁니다. 후보 이름은 이미지에 보이는 band 색(`end_teal`/`end_blue`)입니다. 이 색이 곧 학생 role 토큰이라 바인딩에 좌표가 필요 없습니다. west/east는 평가 표기로만 남겼습니다. LLM이 west/east를 고르려면 자기 heading(= plan pose)이 필요하기 때문입니다.
- 실제 LLM: `dsh/l1lite-alloc` `955c967d`의 `e2e_warp_runtime.py`(Channels, Planner), `e2ewarp_l1lite.py`, `e2ewarp_selfnav.py`를 byte 동일하게 가져와 재사용합니다(blob pin 테스트). 별도로 만들었던 채널 코드는 지웠고, structured enum만 `L2Channels` 하위 클래스로 바꿨습니다.
- 후보 이름(오너 승인 10/21): `end_teal`/`end_blue`를 씁니다. east/west 후보와 heading 입력은 넣지 않습니다.
- N-S 사전 제외 *삭제*(오너 10/21): seed 8344000부터 순서대로 6개를 제외 없이 씁니다. 대신 각 seed의 빔 yaw(`beam_yaw_deg`, `abs_cos_yaw`, `ew_ambiguous`)를 evaluator에만 기록하고, `l2-eval.json` aggregate에 `by_beam_direction`으로 방향별 성공 수를 나눠 보여 줍니다.
- P5 cap: 값은 비워 두고, P5 사전 등록의 규칙만 참조합니다.

## 0. 전제 (모두 충족 전에는 실행하지 않음)
| 조건 | 상태 |
|---|---|
| P4 체크포인트 오프라인 gate 통과, P5 prereg(cap 값 포함) 커밋 → 같은 cap을 L2 prereg에 복사 | [미정] |
| L2 후보 case 생성(P3 생성기, seed 8344000–8344099) 명령 | [확인 필요: P3 수집 명령 확정 후] |
| 첫 프레임 run의 `review-2hz` 이미지가 robot_cam native render인지, tick 0 렌더가 `plan.roles`와 무관한지 | [확인 필요] (`scripts/warp_act_backend.py` `capture`) |
| SSH loopback relay가 CoreWeave fp4 pin과 잔액을 `/identity`로 보고 | L1-lite와 같음, 실행 시 `check_relay`가 검사 |
| E2E_L2_PREREG_DRAFT.json → REGISTERED (Codex 검토) | 초안 |

## 1. 스택
| tree | 브랜치 | 고정 |
|---|---|---|
| root | `dsh/e2e-l2` | 이 커밋 (P2 root -r-c2 `612ef643` + L2 파일 + L1-lite 3파일) |
| adapter | `dsh/pairact-p2-carrypath-a-c2` | `warp_flow_episode.ADAPTER_SHA` (`aaabddb1`) |
| teacher | `dsh/pairact-p2-carrypath-c2` | `warp_flow_episode.TEACHER_SHA` (`4b080d35`) |
| 학생 worker | `dsh/pairact-p5-student` | `run_warp_flow_teacher.STUDENT_SHA` (`3c9337d5`) |

번호표: LLM이 고른 band 색(teal/blue)이 그대로 `case.plan.roles`에 들어갑니다. 학생 worker `reset.roles`와 teacher 끝 배정이 모두 `plan['roles']`에서 오는 것은 teacher tree `scripts/run_grasp_act_teacher.py:252,277`에서 확인했습니다. 생성기 끝과 다르게(교차) 배정되면 그대로 실행하고 `assignment_match=false`로 기록합니다.

## 2. 명령 (DeepSeek, 오프피크, gcp6 또는 gcp2, 새 run root)
```bash
export E2E_L2=on_v1 RUN=/home/ugrp/ugrp-sim/runs/e2e-l2-<TS>
cd $SRC/root      # dsh/e2e-l2 checkout
python scripts/check_e2e_l2_seeds.py --pairact-ref bcfefaadc5ecbc24a65f898e44eabcdf886f7ef5   # passed=true여야 함

# (a) case 6개 선택 (seed 순서 앞 6개, 제외 없음)
python scripts/run_e2e_l2.py select --cases $RUN/l2-candidate-cases.json --out $RUN/l2-base-cases.json

# (b) 첫 프레임: 같은 case 파일로 runner 1 tick (teacher flow, 학생 없음)
python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py \
  --flow beampair --adapter-source $SRC/adapter --teacher-source $SRC/teacher \
  --cases $RUN/l2-base-cases.json --cap-s 60 --diagnostic-ticks 1 --out $RUN/frames --vm-hourly-usd 1.096 \
  <P2 SMOKE.md §3의 physics/contact/scene 플래그 그대로>

# (c) LLM 단계 (4조건, relay는 SSH loopback, 키는 relay에만)
for C in peer_en leader_en structured no_comm; do
  python scripts/run_e2e_l2.py decide --cases $RUN/l2-base-cases.json --frames-run $RUN/frames \
     --condition $C --llm live --relay-url http://127.0.0.1:<PORT>/v1/chat/completions \
     --arm student --out $RUN/$C
done

# (d) 실행: 주 조건 peer_en 먼저. exec-cases.json이 없으면(모두 LLM 실패) 실행하지 않음.
python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py \
  --flow beampair --adapter-source $SRC/adapter --teacher-source $SRC/teacher \
  --cases $RUN/peer_en/exec-cases.json --cap-s 60 --out $RUN/peer_en/run --vm-hourly-usd 1.096 \
  <P2 SMOKE.md §3 플래그> --student-eval $RUN/student-eval.json

# (e) 판정
python scripts/run_e2e_l2.py evaluate --decisions $RUN/peer_en/decisions.json \
  --summary $RUN/peer_en/run/summary.json --out $RUN/peer_en/l2-eval.json
```
- teacher_fallback arm은 LLM을 다시 부르지 않고 같은 결정을 재사용합니다: `run_e2e_l2.py rebind --cases $RUN/l2-base-cases.json --decisions $RUN/peer_en/decisions.json --arm teacher_fallback --out $RUN/peer_en-teacher`. 그다음 runner를 `--student-eval` 없이 돌립니다. 결과에는 `[대체 단계] teacher, NOT a learned result` 라벨이 붙고 학습 결과와 합산하지 않습니다.
- HOST_ERROR: 같은 exec-case(같은 LLM 결정)로 1회 재실행합니다. LLM은 다시 부르지 않습니다.
- `--llm replay`는 건조 실행용입니다. 결과로 보고하지 않습니다.
- `--cap-s 60`과 후보 프로필의 `carry_cap_s`는 P5에 등록된 cap과 같아야 합니다([미정]).

## 3. 출력
| 파일 | 내용 |
|---|---|
| `frames/world-00k/review-2hz/<robot>/000000.jpg` | LLM에 들어간 자기 카메라 첫 프레임 (decisions의 `frames_sha256`과 대조) |
| `$C/decisions.json` | 조건별 LLM 기록(transcript, 메시지, 결정, 오류, usage, planner_ledger) + eval-only geometry |
| `$C/llm/world-XX/<robot>/NNNNN.{request,response}.json` | Planner archive (이미지는 sha256으로 대체, 키 없음) |
| `$C/exec-cases.json` | 실행 가능한 seed만, `plan.roles`만 LLM 결정으로 바꾼 case + `l2_admin` |
| `$C/l2-eval.json` | seed별 L2 판정, 조건×arm n/6, LLM 지표, 빔 yaw·방향별 집계(eval-only) |

## 4. 남은 것
1. 첫 프레임 run의 카메라·roles 독립성 확인 (§0).
2. P3 생성 명령과 P5 cap 값 (외부 의존).
3. L1-lite `run_e2e_warp.py`의 전체 live guard(lease, host receipt, current_stack 검사)는 가져오지 않았습니다. relay pin·loopback·키 env 금지만 `check_relay`로 구현했습니다.
