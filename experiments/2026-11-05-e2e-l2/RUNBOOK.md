# L2 E2E: LLM 역할 배정 → 학습 공동 운반 (기본 off, 실행 전 초안)

목적: 11/5 데모 A등급(aggressive-replan-1105.md §6). 두 로봇의 LLM이 주문서(큰 빔 1개, 단독 불가 표시 없음)와 자기 관측만 보고 *협력 필요 판단 + 맡을 끝(west/east)* 을 4조건 채널로 정하고, 그 결과를 학습 공동 운반 정책의 번호표(role 토큰)로 넘겨 MJWarp에서 실행합니다. 사전 등록 초안은 `E2E_L2_PREREG_DRAFT.json`입니다.

## 0. 전제 (모두 충족 전에는 실행하지 않음)
| 조건 | 상태 |
|---|---|
| P4 체크포인트가 오프라인 gate 통과, P5 prereg(cap 값 포함) 커밋 | [미정] |
| live planner 연결 (`harness/e2e_l2.planner_ask`) | *미연결*: NotImplementedError. `dsh/l1lite-alloc`의 `Planner`와 합친 뒤 구현 + 기록 응답 테스트 필요 |
| L2 seed 범위 8344000–8344099, `experiments/2026-11-05-e2e-l2/seeds.json` + `scripts/check_e2e_l2_seeds.py` 겹침 0 (테스트 고정) | 완료 |
| P3 생성기로 L2 후보 case 생성 명령 | [확인 필요: P3 수집 명령 확정 후] |
| E2E_L2_PREREG_DRAFT.json → REGISTERED 커밋 (Codex 검토) | 초안 |

## 1. 스택
실행 단계는 이 브랜치의 root runner를 *그대로* 씁니다(P2 root -r-c2 `612ef643` 위에 L2 파일만 추가, 기존 파일 변경은 CI 목록 1줄).
| tree | 브랜치 | 고정 |
|---|---|---|
| root | `dsh/e2e-l2` | 이 커밋 |
| adapter | `dsh/pairact-p2-carrypath-a-c2` | `warp_flow_episode.ADAPTER_SHA` (`aaabddb1`) |
| teacher | `dsh/pairact-p2-carrypath-c2` | `warp_flow_episode.TEACHER_SHA` (`4b080d35`) |
| 학생 worker | `dsh/pairact-p5-student` | `run_warp_flow_teacher.STUDENT_SHA` (`3c9337d5`) |

번호표 연결: LLM이 고른 west/east는 빔 band의 world x로 teal/blue에 대응됩니다(+x = east, teal = 빔 local −0.27, blue = +0.27). 이 값만 `case.plan.roles`에 쓰입니다. 학생 worker의 `reset.roles`와 teacher의 끝 배정이 모두 `plan['roles']`에서 오는 것은 teacher tree `scripts/run_grasp_act_teacher.py:252,277`로 확인했습니다. 원래 생성기 끝과 다르게(교차) 배정되면 그대로 실행하고 `assignment_match=false`로 기록합니다. 이때 시작 위치는 학습 분포 밖일 수 있습니다.

## 2. 명령 (DeepSeek, 오프피크, gcp6 또는 gcp2, 새 run root)
```bash
export E2E_L2=on_v1 RUN=/home/ugrp/ugrp-sim/runs/e2e-l2-<TS>
cd $SRC/root      # dsh/e2e-l2 checkout

# (a) case 6개 선택 (정적, 결과 무관)
python scripts/run_e2e_l2.py select --cases $RUN/l2-candidate-cases.json --out $RUN/l2-base-cases.json

# (b) 조건별 LLM 단계 (4조건 모두, GPU 불필요). live는 연결 후에만.
for C in peer_en leader_en structured no_comm; do
  python scripts/run_e2e_l2.py decide --cases $RUN/l2-base-cases.json --condition $C \
     --llm live --arm student --out $RUN/$C
done

# (c) 실행 단계: 주 조건 peer_en 먼저. exec-cases.json이 없으면(모두 LLM 실패) 실행하지 않음.
python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py \
  --flow beampair --adapter-source $SRC/adapter --teacher-source $SRC/teacher \
  --cases $RUN/peer_en/exec-cases.json --cap-s 60 --out $RUN/peer_en/run --vm-hourly-usd 1.096 \
  <P2 SMOKE.md §3의 physics/contact/scene 플래그 그대로> \
  --student-eval $RUN/student-eval.json          # teacher_fallback arm은 이 줄 없이 (아래 rebind 결과로)

# (d) 판정
python scripts/run_e2e_l2.py evaluate --decisions $RUN/peer_en/decisions.json \
  --summary $RUN/peer_en/run/summary.json --out $RUN/peer_en/l2-eval.json
```
- teacher_fallback arm은 LLM을 다시 부르지 않고 같은 결정을 재사용합니다: `python scripts/run_e2e_l2.py rebind --cases $RUN/l2-base-cases.json --decisions $RUN/peer_en/decisions.json --arm teacher_fallback --out $RUN/peer_en-teacher` → runner를 `--student-eval` 없이 `$RUN/peer_en-teacher/exec-cases.json`으로 돌립니다. 결과 라벨은 자동으로 `[대체 단계] teacher, NOT a learned result`가 붙고 학습 결과와 합산하지 않습니다.
- HOST_ERROR: 같은 exec-case(같은 LLM 결정)로 1회 재실행. LLM은 다시 부르지 않습니다.
- `--llm replay`는 건조 실행용입니다. 결과로 보고하지 않습니다.

## 3. 출력
| 파일 | 내용 |
|---|---|
| `$C/decisions.json` | 조건별 LLM 기록(transcript, 메시지, need_partner, 결정, 오류, usage) + admin geometry(생성기 끝, 거리) |
| `$C/exec-cases.json` | 실행 가능한 seed만, `plan.roles`만 LLM 결정으로 바뀐 case + `l2_admin` |
| `$C/run/summary.json` | root runner 원본 출력(`carry_success`, `teacher_steps`, `student_funnel`) |
| `$C/l2-eval.json` | seed별 L2 판정, 조건×arm n/6, LLM 지표(배정 일치·충돌·환각·토큰·USD), failure_stage |

## 4. 남은 연결 (코드)
1. live planner: `planner_ask` 구현(L1-lite `Planner.decide`), 응답 → `{'need_partner','act','message','usage'}` 파싱, 기록 응답 테스트.
2. 관측: brief의 거리는 plan 좌표에서 계산한 값입니다(`source=plan_geometry_v1`, 대체). 지각 경로 연결은 범위 밖입니다.
3. L1-lite `Channels`와 통합: 지금은 같은 규칙의 자체 in-memory 채널입니다.
4. 생성기 시작 분포는 *생성기 끝* 기준이라 교차 배정 시 학습 분포 밖입니다. 이 영향은 `assignment_match`로만 기록합니다.
