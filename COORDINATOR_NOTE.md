
## 2026-10-16 12:3x coordinator note — user decision
User (on "일부 배치는 잡을 자세가 하나도 없음"): "그런 배치는 모두 없애줘". Add a placement admission filter for beam-pair (and any cargo placement used by the flows you port): reject at scenario/seed generation any placement where an assigned grasp end has 0 certified grasp poses (beampair6 branch A certified 91 poses per end; beampair9 found 2 scenes with 0/91, earlier seed 8318626 blue end 0/91). Use the existing certification code (beampair6 / beampair9, PR #542), static map + placement only, no runtime ground truth into control. Default-off toggle (e.g. placement_graspable_filter_v1), but ON for all new MJWarp gates and data. Record how many generated placements are rejected (n/N) and which, so the distribution change is visible. Do not pool with earlier distributions.

## 2026-10-16 18:20 coordinator: 8h 상한 다시 넣지 말 것
사용자 결정 "8시간 상한 — 이건 좀 없애라"(PR #558). warp8 프롬프트의 "8h 유지"는 이 결정 전에 쓴 조정자 실수다. gcp3에 다시 넣은 maxRunDuration 28800은 VM이 다음에 정지할 때 조정자 감시가 지운다. 다시 시작할 때 상한을 붙이지 말 것. 유휴20분·budget-stop은 유지.

[조정자 20:04] 충돌 방지 규칙(필수): /Users/changmin/projects/ugrp/outputs/e2e18-admin/agent-ownership.md 를 읽고 따를 것. 자기 VM·자기 파일 범위 밖은 건드리지 말 것. 다음 ops-alert 보고 줄 끝에 'ownership-ack' 를 붙일 것.

[조정자 21:17] 사용자 지시(원문): "아니; 상한 좀 없애라고". 실행 시간 상한을 모두 없앤다. (1) VM 8h 상한: 켜진 VM은 GCP가 변경을 거부함(조정자가 시도·확인: 'Max run duration cannot be changed while the instance is running'). 그래서 지금 단계가 끝나는 경계에서 직접: VM 정지 → gcloud compute instances set-scheduling <VM> --account changmin5781@gmail.com --project <P> --zone asia-northeast3-a --clear-max-run-duration --clear-instance-termination-action → maxRunDuration 비었는지 describe로 확인 → 시작 → 다음 단계 이어서. (2) 작업자 자체 wall 예산/종료 시각(예 13:47Z GPU budget end, 14:05Z 정리)도 없앤다. 유휴 20분 종료와 budget-stop은 유지. 다음 보고 끝에 'cap-ack'.
warp8: 경계 = 빔 40 판정 끝난 뒤·release A/B 제출 전(gcp3 = ugrp-act-l4-gcp3, ugrp-sim-c-1016). gcp3 상한은 16:37Z.

## 2026-10-16 22:17 KST 조정자: 분석은 원본이 있는 자기 VM에서 — CPU VM(ugrp-sim-gcp2) 시작 금지
- ugrp-sim-gcp2(n4-highcpu-64, $3.15/h)가 짧은 스냅샷·재계수 때문에 오늘 세 번 다시 켜졌고 매번 load 0.1 이하로 놀았다. 사용자: "낭비 하지 마".
- AGENTS의 "실패 분석은 gcp1(=CPU VM)에서"는 "원본이 있는 실행 VM의 CPU에서"로 읽는다(규칙 PR로 고친다). warp8=gcp3, warpfit=gcp6, mapbuild4=gcp5, act16w=gcp2 L4 자기 VM에서 분석한다.
- C MuJoCo CPU 비교도 자기 L4 VM의 CPU(8–16코어)에서 한다. ugrp-sim-gcp2를 켜지 않는다. 꼭 그 디스크의 원본만 필요하면 조정자에게 ops-alert로 요청한다.

## 2026-10-16 22:45 KST 조정자 정정: gcp3에 8시간 상한을 다시 넣지 말 것
- 처음 warp8 지시문의 "8h 유지"는 제 잘못이다. 사용자 결정은 "상한 좀 없애라고"이며 이것이 우선한다. 13:4xZ에 다시 넣은 8h STOP은 조정자가 지웠다(현재 maxRunDuration 없음).
- release A40/B40 세션도 상한 없이 시작한다. `--max-run-duration`, `--instance-termination-action`을 넣지 않고 자체 wall 상한도 두지 않는다. idle20·budget-stop은 그대로 둔다.
- 다음 보고에 "nocap-ack"를 적는다.

## 2026-10-16 22:47 KST 조정자: 13:33Z에 ugrp-sim-gcp2를 또 켰다 — 다시 정지함
- 22:17 메모(13:17Z) 뒤에도 beam40-r2 분석 때문에 CPU VM을 켰고 load 0.07로 놀았다. 오늘 네 번째다. 정지했다.
- 앞으로 warp8 분석은 gcp3(원본이 있는 자기 VM)의 CPU에서만 한다. CPU VM에 있는 원본이 꼭 필요하면 ops-alert에 "warp8→조정자: CPU VM 필요 <이유>"를 쓰고 기다린다. 직접 켜지 않는다.
- 조정자 감시가 CPU VM이 10분 놀면 자동으로 끈다. 그 VM에서 돌던 분석은 끊길 수 있다.
- 다음 보고에 "nocap-ack"와 함께 "nocpu-ack"를 적는다.

## 2026-10-17 00:25 KST 조정자 재계수 결과 → 종료 기록에 반영할 것
관문 n/N은 원본과 일치. 다만 기록 정리 필요: (1) 세계별 RUN_META.json의 class/pr/branch/batch가 옛 값(예 pr 484, beampair7-gate40)으로 복사됨 → 이번 배치 값으로 고친 보정 파일을 원본 옆에 추가(원본 덮어쓰기 금지)하고 첫 native 관문 통과 원본은 class milestone. (2) gate_eligible=false 사유(정식 admission 없이 실행)를 summary 옆 기록에 명시. (3) scene.json/장면 기록의 cargo_contact_profile이 cargo_noslip_v1(10)로 남은 경우 실제 적용값(native 0)과 다름을 기록. 재계수: /Users/changmin/projects/ugrp/outputs/e2e18-admin/recounts/
