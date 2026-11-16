# s3fix16: endpoint visibility, command ownership and coarse servo

2026-10-10. DEV development round, not confirmation. Mac physics/render/replay forbidden;
all replay and physics on `host=oracle-x86`. PR #416 remains draft; no merge/CI wait.

## Before diagnosis

A is classified from s3fix15 original raw, per `beam_obs` timestamp: exact saved
MuJoCo camera pose and qpos, nearest grip-band top centre + four corners projected
into the actual rendered pinhole support (raw fisheye remap cannot restore missing
pinhole pixels). `fov_clipped` means at least one corner is outside support;
`in_fov_rejected` means all corners inside, not proof of absence of occlusion.
No physics step, no image regeneration, no GT enters controller.
Raw: `outputs/oracle-runs/s3fix15-batch-r1/cohort/`; archived source
`4e19382d59a9bb2bbf351a7fca1356cdf480e8a0`.
If FOV loss: freeze own RGB measurement before loss and use only issued-command
calibration in a bounded final open-loop segment. If in-FOV rejection: fix only
the identified detector cause. B: fine alignment owns arm commands exclusively,
PF measured calibration unchanged. C: retain s3fix15 acceptance widths, require
single-axis immediate progress with move-settle-look and hysteresis.
Full 10-case manifest will be committed before physics; no midbatch adaptation.

## References

- Hutchinson, Hager, Corke (1996), [A Tutorial on Visual Servo Control](https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf): position/image visual feedback and look-then-move architecture.
- [ROS2 control command ownership](https://docs.universal-robots.com/Universal_Robots_ROS_Documentation/rolling/doc/ur_robot_driver/ur_robot_driver/doc/usage/controllers.html): one active controller per claimed command interface; explicit handover.

## Diagnosis / frozen physical preregistration (before new physics)

Evaluation source `bc06ec0347cf926055fdde981593d818a2ebd7ac`, Oracle x86, 0 physics steps,
5.88 wall seconds. All band centres remained visible; partial corners matter.

|condition|r1 visible / in-FOV rejected / FOV clipped|r2 visible / in-FOV rejected / FOV clipped|
|---|---:|---:|
|c0|2 / 459 / 0|6 / 0 / 439|
|c1|1 / 463 / 0|43 / 0 / 0|
|c2|3 / 454 / 0|7 / 0 / 434|
|c3|3 / 454 / 0|6 / 0 / 439|
|c4|41 / 0 / 0|42 / 0 / 0|
|c5|41 / 0 / 0|4 / 0 / 449|

Every rejection was `BAND_CLIPPED`. Example c0/r1 at 4.0 s: deepest band
corner y=475.614/480 in ideal rendered image; all four inside. c0/r2 at6.0s:
y=512.267/480, one corner outside. The detector uses a **14-pixel eroded**
valid mask, explaining r1 rejection of a complete near-border band. Candidate
`band_border` uses a 1px sampling margin, retaining complete-band, length20–60mm,
colour and identity checks. A saved RGB replay checks this exact claim separately.
`endpoint_memory`: only a prior fully visible, existing standoff-quality own RGB
fit can start it; accepted issued calibrated forward/turn100ms pulses propagate
that fit, max3 pulses,60mm/.32rad,8s; no timestamp renewal. Partial band evidence
is never re-labelled a fresh visual measurement. No new camera or runtime GT.

B: `posture_ownership` gives own-RGB alignment the arm until that state exits.
Neither a pending PF re-look nor `_v98_restore` may overwrite its pan; measured
PF camera keys remain unchanged. Status, partner abort and arm interpolation
continue in the outer tick. Reset/reentry is scoped by state and open gripper.

C: s3fix15 c3/c4 requested100ms forward pulses, but `real_fine_v1` rewrote them
as60ms before heading admission. Heading replaced these illegal pulses with
alternating yaw; this is command ownership conflict, not an RGB detection loss.
`coarse_axis_ownership` preserves the exact calibrated proposal through that
adapter, one axis at a time, immediate error decrease, .50s minimum settle plus
fresh frame, 1.25x hysteresis exit. Alignment acceptance remains **pair dx18mm,
cyan dx9.6mm, dy3mm about -6mm, yaw.112rad**, two fresh confirmation frames.
A hysteresis latch never grants an aligned receipt.

All four booleans default false. `abc_v1` enables all for this DEV round.
Bundle **zone-s3-alignment-ownership-v162**, workflow7.55.0 reserved after main
and all12 open PR heads scanned (maximum161). Central workflow JSON unchanged.

`batch-plan.json` freezes names, conditions, seeds14201–14206, commands and flags.
Exactly pair c0–c5 plus cyan c0/c3/c4/c5, ten concurrent workers,60SIM each,
OSMesa/LP_NUM_THREADS4/OMP1, dev_light, heading on except coupled carry.
One optional pathcheck5SIM uses pair c0 and the same flags. No batch results
read for tuning until all cases finish; no rerun or threshold change within round.
Command per manifest row:
`python -m scripts.run_s3_alignment_ownership --expected-source-sha SHA --output outputs/NAME/raw --case CASE --condition CONDITION --coarse-fine stopped_base_arm_v1 --refinements abc_v1 --execute`.
Batch: `python -m scripts.run_s3_alignment_ownership_cohort --expected-source-sha SHA --output outputs/s3fix16-batch-r1/cohort --execute`.

Primary outcomes: joint n/10 and per-robot alignment / actual two-finger contact
for>=.20s / contact-supported lift z>.06m / carry>=.02m while lifted. Cyan c0
regression included. Report A missed-end stalls, B restore collisions, C turn
reversals; retain all errors including ENOSPC=HOST_ERROR. Report wall/SIM and
existing nested host timers without performance optimization. These initial
conditions were already viewed: development regression, not confirmation.

Implementation note: the legacy 60ms adapter source is sealed by previous PF
replay evidence. It remains byte-identical. The new S3-only instance class binds
its command conversion to the exact calibrated pulse while this alignment owns
it; all other proposals use the original converter. No shared source/seal change.
[OpenCV erosion semantics](https://docs.opencv.org/4.13.0/d9/d61/tutorial_py_morphological_ops.html)
explain why a14px valid-mask erosion rejects fully visible near-border bands.
- [Nav2 SimpleGoalChecker source](https://github.com/ros-navigation/navigation2/blob/main/nav2_controller/plugins/simple_goal_checker.cpp): stateful XY acceptance with a separate reset buffer is the reference for entry/exit hysteresis. Here the buffer controls axis selection only; final RGB acceptance still requires all original bounds.

Local validation before physics:17 controller/probe tests passed after final
changes;20 catalog/planning tests passed. Both fully visible and endpoint-lost
pair fixtures reach hover through the real outer tick and motor stub; peer abort
still stops, PF measured keys unchanged. Cyan outer step preserves100ms forward,
issues hold at100ms and waits for the fresh settled frame. Central catalog and
sealed common60ms converter are byte-identical to the parent. No Mac physics.


## Completed fixed batch — 2026-10-10 (s3fix16)

실행 소스 **ad844d13e01f2871e39bf9b6a59c2636365bec7e**, host=oracle-x86,
v162/7.55.0, dev_light, LP_NUM_THREADS=4/OMP=1. 사전 등록한 10조건을
동시에 제출했고 중간 변경·재실행·문턱 변경은 없었다. 기본 off 유지, 채택 보류.
새 확증·정식 E2E·실물 성공으로 해석하지 않는다.

|범위|정렬|실제 집기|접촉 지지 상승|실제 운반 ≥20mm|
|---|---:|---:|---:|---:|
|전체 조건|9/10|9/10|9/10|4/10|
|pair 공동 판정|5/6|5/6|5/6|0/6|
|r1 개별|6/6|5/6|5/6|0/6|
|r2 개별|5/6|5/6|5/6|0/6|
|r3 cyan|4/4|4/4|4/4|4/4|

cyan c0 회귀 통과. pair 5조건은 공동 운반 **상태에 진입**했지만 빔 실제 XY
이동은 4.2–8.5mm라 운반 성공으로 세지 않았다. 모든 시각은 시작 후 절대 SIM초,
pair 셀은 r1/r2 순서, 정렬과 hover 진입 시각은 동일하다.

|조건|정렬/hover|하강|닫기|접촉 집기|접촉 상승|운반 상태 진입|실제 운반 mm|운반|wall/SIM초|
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
|pair c0|4.90/6.90|6.40/8.40|9.80/9.80|10.20/10.15|11.95/11.95|30.10/30.10|4.2|X|315.63/60.00|
|pair c1|5.70/6.40|7.20/7.90|9.30/9.30|9.70/9.65|11.45/11.45|29.60/29.60|5.7|X|313.65/60.00|
|pair c2|5.90/7.40|7.40/8.90|10.30/10.30|10.70/10.65|12.45/12.45|30.60/30.60|7.8|X|311.87/60.00|
|pair c3|5.90/—|7.40/—|—/—|—/—|—/—|—/—|0.0|X|139.19/26.35|
|pair c4|4.40/5.40|5.90/6.90|8.30/8.30|8.70/8.65|10.45/10.45|28.60/28.60|8.5|X|319.75/60.00|
|pair c5|4.40/5.90|5.90/7.40|8.80/8.80|9.15/9.15|10.95/10.95|29.10/29.10|8.4|X|317.10/60.00|
|cyan c0|4.85|6.15|7.35|7.75|9.05|30.05|631.6|O|347.87/60.00|
|cyan c3|4.85|6.15|7.35|7.70|9.05|30.05|274.7|O|351.91/60.00|
|cyan c4|4.85|6.15|7.35|7.70|9.05|30.05|575.2|O|365.57/60.00|
|cyan c5|4.85|6.15|7.35|7.75|9.05|30.05|662.0|O|367.24/60.00|

### 원인 분리와 재발

- **A 검출/시야**: 이전 raw의 완전한 밴드가 시야 안인데 거부된 r1 프레임
  1,830/1,830은 1px 유효영역으로 복구됐다. r2 실제 잘린 밴드 1,761/1,761은
  계속 거부됐다. 저장 RGB 전체 재생 13.30wall초, GT 투영은 판정에만 사용.
  새 물리에서 끝점 소실에 따른 정체 후보는 **8/12→1/12(pair c3/r2)**.
  보이는 마지막 자기 RGB와 발행 명령 전파를 사용한 경우도 새 관측으로 위장하지 않았다.
- **B 자세 소유권**: pair 복원 충돌 **4/12(155회)→0/12(0회)**.
  외부 tick 회귀도 통과했다. PF 측정 카메라 키는 바꾸지 않았다.
- **C yaw 진동**: cyan c3/c4 정렬 반전 **116/115→0/0**. 새 라운드 전체
  16개 로봇 사례의 정렬 구간 반전은0; 전 구간은7회(cyan 후속 주행1/4/1/1).
  100ms 요청이60ms로 변환돼 heading 회전으로 대체되던 경로를 제거한 효과이며
  기존 허용 폭을 넓혀 얻은 결과가 아니다.

### 남은 두 문제 — 이번 결과 뒤 수정·물리 재실행하지 않음

1. **pair c3/r2**: 마지막 자체 영상+발행 명령 예측에서 pan1672의 오차는
   dx−9.427mm, dy−0.414mm, yaw0.112553rad로 yaw 한도0.112rad를
   0.000553rad 넘었다. 단일 차체 펄스의 즉시 개선 후보가 없어 정지했고
   8초 기억 유효기간 만료 뒤 r1 `BARRIER_CLOSE_TIMEOUT`으로26.35SIM초에 끝났다.
   Oracle의 저장 수치 기하 진단에서 인접 pan1676(4µs 차이)은
   dx−9.470mm/dy−1.328mm/yaw0.106270rad로 **동일 문턱** 안이다.
   이는 dy 중심을 우선 최소화하는 팔 후보 선택이 공동 허용 영역의 후보를 놓쳤다는
   가설이다. 새 후보 열거를 구현·물리 검증한 결과가 아니며 문턱 변경 근거도 아니다.
2. **pair 운반**: 5조건 모두 운반 구간 로봇당94 drive명령 중59개가0,
   나머지35개는 forward0.043618/left0/turn0,150ms였다. 운반 시작의
   `door_align_gate`가 `pair_neutral=true`로 중립화했고, 이후 전진은
   기존 보정 최소35/100 대비4.36/100으로 작았다. 따라서 전부0 명령이라는
   설명은 틀리다. 예 c0: carry30.1→wait_lower40.1→refix_decide40.2→lower50.5.
   `loaded_gate_check`는 불확실을 기록하고 passed=true였지만 앞선 문 정렬 게이트가
   실제 중립 명령을 남긴다. 이 DEV 경로와 하중 주행 펄스는 다음 단계 probe 대상이다.

HOST_ERROR는 물리 묶음 **0/10**; c3의 공동 닫기 장벽 실패는 위와 같이 별도 보존.
나머지9조건은60SIM초까지 실행했다. 명령18,245, 모델 호출0.
합산 run wall/SIM=3149.789/566.35=**5.562**; 동시 묶음 경과390.31wall초.
기존 중첩 타이머 합계: physics996.72s, RGB render936.32s, capture1013.44s
(render 포함), JSONL append9.06s. 물리·3대 RGB가 기록 I/O보다 크다.
타이머는 더하면 안 되며, baseline6.25와는 종료 시각도 달라 속도 개선 증거가 아니다.
최적화는 하지 않았다.

### 회수·검증·표시

- 관련 pytest **37개 통과**(제어기/probe17 + catalog/planning20) 후 소스 커밋·push.
  Mac에서는 물리·렌더·제어 재생을 실행하지 않았다.
- 첫 pathcheck는 여유9.6GiB <11GiB 사전 검사로 **0SIM 실행 거부**;
  로그를 보존하고 물리10조건 분모와 분리했다. 비활성 immutable 소스 아카이브의
  경로·크기·모드·전체 SHA가 같은 파일만 hardlink로 중복 제거했다.
  raw 삭제·변경이나 다른 프로세스 종료는 없었다. 기록:
  `outputs/oracle-runs/s3fix16-inactive-source-cache/source-dedup.json`.
  이후5SIM pathcheck31.653wall초, 양쪽 pregrasp_descend, HOST_ERROR0.
- 본 묶음 raw **34,338파일**과 pathcheck335파일 회수·전체 해시 일치.
  로컬 루트 `/Users/changmin/projects/ugrp/outputs/oracle-runs/` 아래
  `s3fix16-batch-r1/cohort/*/raw`, `s3fix16-pathcheck-r2/`,
  `s3fix16-visibility-r1/diagnosis`, `s3fix16-band-replay-r1/replay`,
  `s3fix16-eval-r1/evaluation`. 판정 source도ad844d13, GT는평가전용.
  [전체 결과](results.json), [원인별16사례](cause-breakdown.json),
  [회수 검증](retrieval-verification.json), [검출 재생](band-replay-summary.json).
- TensorBoard `1010-s3fix16-alignment-ownership-v1`: **15뷰·253scalar태그·10영상**.
  EventAccumulator/API 값·영상 SHA/Range206 확인, 기존 v161과9개 카드를 고정해
  실제 Chrome Time Series에서2→9 정렬 값을 확인했다. HParams의
  case/policy/seed/source_sha는 재적용했으나 그 플러그인 표는 `Invalid input`으로
  행 로딩을 확인하지 못했다. Time Series의 값·조건 열은 로딩됐다.
  기존 공용 서버는 재시작하지 않았다.
  [대시보드](http://127.0.0.1:6006/?runFilter=%5E%281010-s3fix16-alignment-ownership-v1%7C1010-s3fix15-coarse-fine-v1%29%2F#timeseries),
  [이벤트·영상 검증](tensorboard-verification.json), [화면 검증 범위](display-verification.json).
- 대표4배속 영상: [pair c0](http://127.0.0.1:6007/video/90ed8b23a33b9eb25473),
  [cyan c3](http://127.0.0.1:6007/video/002557afb90db04124b0).
  원본 `s3fix16-eval-r1/evaluation/s3fix16-{pair-c0,cyan-c3}-r1/execution.mp4`;
  각15초,20fps. cyan 영상 실제브라우저 readyState4/1920×480 확인.

다음 제안: 문턱을 유지한 팔 후보 공동 적합성 검사와 pair 하중 운반 게이트·최소 펄스를
오프라인에서 함께 수정한 뒤, 운반 진입 상태의 짧은 묶음 probe로 확인한다.
PR #416은 DRAFT 유지, CI 대기·병합 없음.
